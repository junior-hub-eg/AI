import io
import wave

import pytest

from app.providers.errors import ProviderExhausted
from app.services.question_policy import focus_for, validate_question
from app.services.result_service import parse_result
from app.services.text import chunk_text, clean_transcript, truncate_words
from app.services.wav import join_wavs, silent_wav

CODES = {"FRONTEND", "BACKEND", "UIUX", "DATA"}


def rec(code, pct, reason="You like it."):
    return {"track_code": code, "match_percent": pct, "reason": reason}


def test_question_cleaning_and_limits():
    assert validate_question("**Nice!** What games do you love? 🎮") == "Nice! What games do you love?"
    with pytest.raises(ValueError):
        validate_question("")
    with pytest.raises(ValueError):
        validate_question("word " * 60 + "?")


@pytest.mark.parametrize(
    "bad",
    [
        "What's your name?",
        "Where do you live?",
        "Which school do you go to?",
        "What is your phone number?",
        "How old are you?",
        "Can I get your email?",
    ],
)
def test_personal_info_questions_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_question(bad)


def test_school_subject_question_is_allowed():
    assert validate_question("What school subjects do you like?")


def test_focus_plan_ends_with_dream_project():
    assert focus_for(10, 10).startswith("dream project")
    assert focus_for(2, 10).startswith("school")
    assert focus_for(3, 4).startswith("making things")


def test_chunking_respects_limit_and_keeps_words():
    text = "First sentence here. " * 30
    chunks = chunk_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert " ".join(chunks).split() == text.split()
    assert chunk_text("a" * 10 + " " + "b" * 10, 200) == ["a" * 10 + " " + "b" * 10]


def test_truncate_words():
    out = truncate_words("one two three four five six", 15)
    assert len(out) <= 15 and out.endswith("…")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Thank you.", ""),
        ("you", ""),
        (".", ""),
        ("I like robots", "I like robots"),
    ],
)
def test_clean_transcript(text, expected):
    assert clean_transcript(text) == expected


def test_join_wavs_concatenates_frames():
    joined = join_wavs([silent_wav(0.1), silent_wav(0.1)])
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnframes() == 3200


def test_parse_result_sorts_ranks_and_trims():
    recs, summary, _speech = parse_result(
        {
            "recommendations": [rec("data", "61%"), rec("FRONTEND", 86, "x" * 500), rec("UIUX", 74.4)],
            "summary": "One. Two. Three. Four. Five.",
        },
        CODES,
    )
    assert [(r.rank, r.track_code, r.match_percent) for r in recs] == [
        (1, "FRONTEND", 86),
        (2, "UIUX", 74),
        (3, "DATA", 61),
    ]
    assert len(recs[0].reason) <= 300
    assert summary == "One. Two. Three. Four."


@pytest.mark.parametrize(
    "recs",
    [
        [rec("FRONTEND", 80), rec("UIUX", 70)],  # only two
        [rec("FRONTEND", 80), rec("FRONTEND", 70), rec("DATA", 60)],  # duplicate
        [rec("FRONTEND", 80), rec("UIUX", 70), rec("GAMES", 60)],  # unknown code
    ],
)
def test_parse_result_rejects_invalid(recs):
    with pytest.raises(ValueError):
        parse_result({"recommendations": recs, "summary": "ok."}, CODES)


def test_fallback_content_files_are_valid():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "content"
    questions = json.loads((root / "fallback_questions.json").read_text())["questions"]
    assert len(questions) == 10
    for q in questions:
        assert validate_question(q) == q
    result = json.loads((root / "fallback_result.json").read_text())
    assert len(result["recommendations"]) == 3
    assert all(len(r["reason"]) <= 300 for r in result["recommendations"])


def test_exhausted_is_an_exception():
    assert issubclass(ProviderExhausted, Exception)
