from tests.conftest import make_settings


def test_arabic_is_the_default_preset():
    s = make_settings()
    assert s.interview_language == "ar"
    assert (s.prompt_turn_version, s.prompt_result_version, s.stt_language) == ("v2", "v2", "ar")
    assert s.tts_model == "canopylabs/orpheus-arabic-saudi" and s.tts_voice == "lulwa"
    assert "؟" in s.opening_question


def test_english_preset_switches_everything():
    s = make_settings(interview_language="en")
    assert (s.prompt_turn_version, s.prompt_result_version, s.stt_language) == ("v1", "v1", "en")
    assert s.tts_model == "canopylabs/orpheus-v1-english" and s.tts_voice == "autumn"
    assert s.opening_question.startswith("Hi there") and s.opening_question_speech == ""
    assert "Minecraft" in s.stt_prompt


def test_explicit_values_win_over_the_preset():
    s = make_settings(interview_language="en", tts_voice="daniel", stt_prompt="")
    assert s.tts_voice == "daniel" and s.stt_prompt == ""


def test_call_config_reports_the_language():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(make_settings(interview_language="en"))) as c:
        assert c.get("/call-config").json() == {"language": "en"}
        first = c.post("/v1/discovery/turns", json=__import__("tests.conftest").conftest.turn_body()).json()
        assert first["next_question"]["question_text"].startswith("Hi there")
        assert first["meta"]["prompt_version"] == "discovery_turn@v1"
