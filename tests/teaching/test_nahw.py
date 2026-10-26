"""The grammar coach on the Nahw Coach engine, offline (no Groq or Gemini key): the verified bank and the rules."""

import asyncio

from teaching.fake import FakeTeachingAi
from teaching.nahw.base import AIError
from teaching.nahw.coach import BANK, NahwTeachingAi, to_parsed
from teaching.nahw.mock_provider import MockProvider
from teaching.schemas import FeedbackRequest, LessonRequest, Mistake, ParseRequest, QuickCheckRequest


def coach(provider=None) -> NahwTeachingAi:
    return NahwTeachingAi(FakeTeachingAi(), provider or MockProvider())


def run(coro):
    return asyncio.run(coro)


class BrokenBase(FakeTeachingAi):
    async def parse(self, body):
        raise RuntimeError("down")


def test_bank_sentences_keep_their_verified_parsing():
    result = run(coach().parse(ParseRequest(text="العلمُ نورٌ. الشمسُ مشرقةٌ.")))
    first, _ = result.sentences
    assert [w.role for w in first.words] == ["مبتدأ", "خبر"]
    assert first.words[0].color == "blue" and first.words[0].sign == "الضمة"


def test_a_book_passage_goes_to_the_general_parser():
    result = run(coach().parse(ParseRequest(text="فعلى الأبناءِ أنْ يتسلّحوا بالعلمِ.")))
    assert result.sentences[0].words[0].role == "حرف توكيد ونصب"  # the fake general parser's canned answer


def test_when_the_general_parser_fails_nahw_parses_with_particles_built():
    c = NahwTeachingAi(BrokenBase(), MockProvider())
    second = run(c.parse(ParseRequest(text="إنَّ العلمَ نافعٌ."))).sentences[0]
    assert [w.role for w in second.words] == ["حرف ناسخ", "اسم إنّ", "خبر إنّ"]
    assert second.words[1].color == "green" and second.words[0].case == "مبني" and second.words[0].sign == "مبني"
    assert all(w.explanation for w in second.words)


def test_lesson_gives_the_topic_points_two_examples_and_a_bank_sentence_of_the_level():
    lesson = run(coach().lesson(LessonRequest(topic_title="كان وأخواتها", difficulty=1)))
    assert 3 <= len(lesson.points) <= 4 and len(lesson.examples) == 2
    assert any(w.role == "اسم كان" for w in lesson.practice.words)


def test_an_unknown_topic_goes_to_the_base_ai():
    lesson = run(coach().lesson(LessonRequest(topic_title="التمييز")))
    assert lesson.practice.words[0].role == "حرف توكيد ونصب"  # the fake base AI's canned lesson


def test_feedback_names_the_mistake_without_the_answer_and_leads_to_it():
    sentence = "كانَ البحرُ هادئًا"
    result = run(
        coach().feedback(
            FeedbackRequest(
                topic_title="كان وأخواتها",
                sentence=sentence,
                mistakes=[Mistake(word="البحرُ", expected="اسم كان", given="فاعل")],
            )
        )
    )
    item = result.items[0]
    assert "البحرُ" in item.what and "اسم كان" not in item.what  # US-07: no answer in the message
    assert (
        item.guiding_questions[-1].answer and len(item.guiding_questions) >= 3
    )  # US-08: type → governor → role → sign
    assert any(q.answer == "اسم كان" for q in item.guiding_questions)
    assert result.similar_sentence.words


def test_quick_check_asks_about_the_topic_roles_from_the_bank():
    quiz = run(coach().quick_check(QuickCheckRequest(title="Quick Check: إنّ وأخواتها", count=5)))
    assert len(quiz.questions) == 5
    for q in quiz.questions:
        assert 0 <= q.answer_index < len(q.options) and len(set(q.options)) == len(q.options)
        assert "إنّ" in q.options[q.answer_index] or "حرف ناسخ" in q.options[q.answer_index]


class FlakyGroq(MockProvider):
    supports_generation = True

    def analyze_sentence(self, sentence, tokens):
        raise AIError("down")

    def generate_sentence(self, topic_title, focus_roles, level, avoid):
        raise AIError("down")


def test_when_groq_fails_the_coach_still_answers_from_the_bank_and_the_rules():
    c = NahwTeachingAi(BrokenBase(), FlakyGroq())
    assert run(c.lesson(LessonRequest(topic_title="المفعول به"))).practice.words
    parsed = run(c.parse(ParseRequest(text="ذهبَ الطالبُ إلى المدرسةِ")))
    assert any(w.role == "حرف جر" for w in parsed.sentences[0].words)


class GoodGroq(MockProvider):
    supports_generation = True

    def generate_sentence(self, topic_title, focus_roles, level, avoid):
        return {
            "text": "كانَ الجوُّ جميلًا",
            "words": [
                {"text": "كانَ", "type": "فعل", "role": "فعل ناسخ", "sign": "مبني"},
                {"text": "الجوُّ", "type": "اسم", "role": "اسم كان", "sign": "الضمة", "case": "مرفوع"},
                {"text": "جميلًا", "type": "اسم", "role": "خبر كان", "sign": "الفتحة", "case": "منصوب"},
            ],
        }

    def verify(self, sentence, tokens, words):
        return True


def test_a_generated_sentence_is_used_once_a_second_analysis_agrees():
    lesson = run(coach(GoodGroq()).lesson(LessonRequest(topic_title="كان وأخواتها", difficulty=1)))
    assert lesson.practice.text == "كانَ الجوُّ جميلًا"
    assert [w.color for w in lesson.practice.words] == ["gray", "blue", "green"]


def test_every_bank_sentence_maps_to_the_backend_shape():
    for words in BANK.values():
        parsed = to_parsed(" ".join(w["text"] for w in words), words)
        assert len(parsed.words) == len(words)


def test_the_service_runs_the_grammar_coach_on_nahw(monkeypatch):
    from types import SimpleNamespace

    from teaching import main
    from teaching.config import Settings

    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setattr(main, "create_model", lambda model_id, settings: object())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(teaching_settings=Settings(llm_model="groq:x", llm_fallback_model=""))
        )
    )
    ai = main.get_ai(request)
    assert isinstance(ai, NahwTeachingAi) and isinstance(ai.provider, MockProvider)


def test_the_general_parser_answer_is_made_consistent_with_the_role():
    from teaching.nahw.coach import consistent
    from teaching.schemas import ParsedWord

    w = consistent(ParsedWord(word="العلمَ،", role="اسم إنّ", case="مرفوع", sign="الضمة", color="blue"))
    assert (w.word, w.case, w.sign, w.color) == ("العلمَ", "منصوب", "الفتحة", "green")
    w = consistent(ParsedWord(word="بالعلمِ؛", role="الباء حرف جر، العلمِ اسم مجرور", case="مجرور", sign="الكسرة", color="orange"))
    assert (w.word, w.case) == ("بالعلمِ", "مجرور")
    w = consistent(ParsedWord(word="المعلمونَ", role="مبتدأ", case="منصوب", sign="الواو", color="green"))
    assert (w.case, w.sign, w.color) == ("مرفوع", "الواو", "blue")  # the case is fixed, a long sign is kept
    w = consistent(ParsedWord(word="إنّ", role="حرف توكيد ونصب", case="مبني", sign="مبني على الفتح", color="blue"))
    assert w.color == "gray"


def test_a_word_with_an_attached_letter_is_split_into_its_two_parts():
    from teaching.nahw.coach import consistent, split_attached
    from teaching.schemas import ParsedWord

    parts = split_attached(consistent(ParsedWord(word="بالعلمِ؛", role="الباء حرف جر، العلمِ اسم مجرور", case="مجرور", sign="الكسرة", color="orange")))
    assert [(p.word, p.role, p.color) for p in parts] == [("بـ", "الباء حرف جر", "gray"), ("العلمِ", "اسم مجرور", "orange")]
    parts = split_attached(consistent(ParsedWord(word="ويسهمُ", role="واو حرف عطف، فعل مضارع مرفوع", case="مرفوع", sign="الضمة", color="blue")))
    assert [(p.word, p.role) for p in parts] == [("وـ", "واو حرف عطف"), ("يسهمُ", "فعل مضارع مرفوع")]
    parts = split_attached(consistent(ParsedWord(word="فعلى", role="الفاء حرف استئناف، على حرف جر", case="مبني", sign="مبني على السكون", color="gray")))
    assert [p.word for p in parts] == ["فـ", "على"]
    single = split_attached(ParsedWord(word="الوطنِ", role="مضاف إليه", case="مجرور", sign="الكسرة", color="orange"))
    assert len(single) == 1
