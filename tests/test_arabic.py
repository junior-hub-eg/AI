"""Arabic interview: display vs speech text, Arabic privacy checks, Arabic text helpers."""

import pytest

from app.services.question_policy import validate_turn
from app.services.result_service import parse_result
from app.services.text import chunk_text, clean_transcript, split_sentences
from tests.conftest import TRACKS, turn_body


def test_turn_keeps_english_terms_on_screen_and_arabic_for_speech():
    q = validate_turn(
        {"question_text": "هل تحب Frontend أم Backend؟", "speech_text": "هَلْ تُحِبُّ فرونت إند أَمْ باك إند؟"}
    )
    assert "Frontend" in q.text and "فرونت إند" in q.speech


def test_turn_without_speech_text_reads_the_display_text():
    q = validate_turn({"question_text": "ما الـ Games التي تحبها؟"})
    assert q.speech == q.text


@pytest.mark.parametrize(
    "bad",
    [
        "ما اسمك؟",
        "اسمك ايه؟",
        "ساكن فين؟",
        "أين تسكن؟",
        "عندك كام سنة؟",
        "كم عمرك؟",
        "ما رقم موبايلك؟",
        "ما اسم مدرستك؟",
    ],
)
def test_arabic_personal_info_questions_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_turn({"question_text": bad})


def test_arabic_personal_info_in_speech_text_is_rejected():
    with pytest.raises(ValueError):
        validate_turn({"question_text": "ما الذي تحبه؟", "speech_text": "مَا اسْمُك؟"})


def test_arabic_subject_question_is_allowed():
    assert validate_turn({"question_text": "ما المواد الدراسية التي تحبها في المدرسة؟"}).text


@pytest.mark.parametrize("text", ["شكرا", "شكراً.", "اشتركوا في القناة", "ترجمة نانسي قنقر"])
def test_arabic_whisper_hallucinations_are_dropped(text):
    assert clean_transcript(text) == ""


def test_real_arabic_answer_is_kept():
    assert clean_transcript("بحب ألعب Minecraft وأبني حاجات") == "بحب ألعب Minecraft وأبني حاجات"


def test_arabic_question_mark_splits_sentences_for_tts():
    assert split_sentences("رائع! ما الذي تحبه؟ احكِ لي.") == ["رائع!", "ما الذي تحبه؟", "احكِ لي."]
    chunks = chunk_text("جملة قصيرة هنا؟ " * 30, 200)
    assert all(len(c) <= 200 for c in chunks)


def test_result_returns_separate_speech_summary():
    codes = {"FRONTEND", "UIUX", "DATA"}
    data = {
        "recommendations": [
            {"track_code": c, "match_percent": p, "reason": "سبب"}
            for c, p in (("FRONTEND", 80), ("UIUX", 70), ("DATA", 60))
        ],
        "summary": "شكرًا لك! أنت تناسب Frontend.",
        "summary_speech": "شُكْرًا لَك! أَنْتَ تُنَاسِبُ فرونت إند.",
    }
    _, summary, speech = parse_result(data, codes)
    assert "Frontend" in summary and "فرونت إند" in speech


def test_first_turn_is_arabic(client):
    q = client.post("/v1/discovery/turns", json=turn_body()).json()["next_question"]
    assert "؟" in q["question_text"]


def test_result_can_include_spoken_summary(client):
    responses = [
        {"order_index": i, "question_text": f"س{i}؟", "transcript": "بحب الرسم"} for i in range(1, 6)
    ]
    body = {"interview_id": "iv", "student_ref": "s", "grade": 8, "tracks": TRACKS, "responses": responses}
    plain = client.post("/v1/discovery/results", json=body).json()
    assert plain["summary_audio_base64"] is None
    spoken = client.post("/v1/discovery/results", json={**body, "speak": True}).json()
    assert spoken["summary_audio_base64"] and spoken["summary_audio_mime_type"] == "audio/wav"
