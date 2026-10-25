"""Canned answers with the real shapes, for tests and wiring checks without an API key (TEACHING_LLM_MODEL=fake)."""

from __future__ import annotations

from .prompts import PROMPT_VERSION
from .schemas import (
    FeedbackItem,
    FeedbackRequest,
    FeedbackResponse,
    GuidingQuestion,
    LessonPoint,
    LessonRequest,
    LessonResponse,
    LinkIdea,
    Meta,
    OcrRequest,
    OcrResponse,
    ParsedSentence,
    ParsedWord,
    ParseRequest,
    ParseResponse,
    Question,
    QuickCheckRequest,
    QuickCheckResponse,
    VideoLinksRequest,
    VideoLinksResponse,
)

META = Meta(prompt_version=PROMPT_VERSION, model_id="fake", latency_ms=0)


def inna_sentence(name: str = "محمدًا", khabar: str = "مجتهدٌ") -> ParsedSentence:
    return ParsedSentence(text=f"إنّ {name} {khabar}", words=[
        ParsedWord(word="إنّ", role="حرف توكيد ونصب", case="مبني", sign="الفتح", explanation="من الحروف الناسخة", color="gray"),
        ParsedWord(word=name, role="اسم إنّ", case="منصوب", sign="الفتحة", explanation="الاسم بعد إنّ اسمها", color="green"),
        ParsedWord(word=khabar, role="خبر إنّ", case="مرفوع", sign="الضمة", explanation="خبر إنّ مرفوع", color="blue"),
    ])


class FakeTeachingAi:
    async def video_links(self, body: VideoLinksRequest) -> VideoLinksResponse:
        return VideoLinksResponse(
            summary=[f"(تجربة) {body.video_title}: إيه هو.", "بيشتغل إزاي.", "بنستخدمه فين."],
            ideas=[LinkIdea(title=f"{body.subject} {i}", text=f"(تجربة) فكرة ربط رقم {i} بين {body.video_title} و{body.subject}.")
                   for i in (1, 2, 3)],
            meta=META,
        )

    async def quick_check(self, body: QuickCheckRequest) -> QuickCheckResponse:
        return QuickCheckResponse(questions=[
            Question(question=f"(تجربة) سؤال {i + 1} عن {body.title}؟", options=["أ", "ب", "ج"], answer_index=i % 3,
                     explanation="لأن ده اللي في الشرح.")
            for i in range(body.count)
        ], meta=META)

    async def ocr(self, body: OcrRequest) -> OcrResponse:
        return OcrResponse(text="إنّ محمدًا مجتهدٌ", meta=META)

    async def parse(self, body: ParseRequest) -> ParseResponse:
        sentences = [s.strip() for s in body.text.replace(".", "\n").splitlines() if s.strip()] or [body.text]
        return ParseResponse(sentences=[inna_sentence() for _ in sentences], meta=META)

    async def lesson(self, body: LessonRequest) -> LessonResponse:
        return LessonResponse(
            points=[LessonPoint(title="الموضوع", text=f"(تجربة) {body.topic_title}"),
                    LessonPoint(title="العلامة", text="الاسم منصوب والخبر مرفوع", color="green"),
                    LessonPoint(title="مثال", text="إنّ العلمَ نورٌ", color="blue")],
            examples=[inna_sentence(), inna_sentence("العلمَ", "نورٌ")],
            practice=inna_sentence("الطالبَ", "نشيطٌ"),
            meta=META,
        )

    async def feedback(self, body: FeedbackRequest) -> FeedbackResponse:
        return FeedbackResponse(items=[
            FeedbackItem(word=m.word, what=f"{m.word} مش {m.given or 'كده'}", why=f"لأنه {m.expected}",
                         guiding_questions=[GuidingQuestion(question="إيه نوع الكلمة الأولى؟", answer="حرف"),
                                            GuidingQuestion(question="إيه الحرف ده؟", answer="إنّ، من الحروف الناسخة")])
            for m in body.mistakes
        ], similar_sentence=inna_sentence("الجوَّ", "جميلٌ"), meta=META)
