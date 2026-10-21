import json
import uuid

from app.catalog import load_catalog, load_rules
from tests.conftest import ROOT, load_context

FORBIDDEN_KEYS = {"correctOptionIndex", "correct_option_index", "options", "helpIfWrong", "help_if_wrong",
                  "explanation", "feedback", "questions", "quiz", "commonQuestions"}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_catalog_has_no_quiz_questions_or_answers():
    raw = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    assert FORBIDDEN_KEYS.isdisjoint(set(_keys(raw)))


def test_lesson_ids_are_the_backend_seed_ids():
    # SeedIds.For("lesson", key): version 5 UUID of "lesson:<key>" in the seed namespace.
    namespace = uuid.UUID("6f1c3c9e-2b1a-4f7e-9a51-4a1d2c7b9e10")
    functions = load_catalog().lesson("Functions")
    assert functions["id"] == str(uuid.uuid5(namespace, "lesson:functions"))


def test_every_mock_lesson_and_mentor_exists_in_the_catalog():
    catalog = load_catalog()
    for persona in (ROOT / "mock" / "contexts").glob("*.json"):
        ctx = load_context(persona.stem)
        for lesson in (ctx["learning"] or {}).get("lessons", []):
            assert catalog.lesson(lesson["id"]) is not None, persona.stem
        if ctx["mentor"]:
            assert catalog.mentor(ctx["mentor"]["id"]) is not None, persona.stem


def test_track_lookup_accepts_common_spellings():
    catalog = load_catalog()
    assert catalog.track("ui/ux")["code"] == "UIUX"
    assert catalog.track("frontend")["code"] == "FRONTEND"
    assert catalog.track("qa")["code"] == "TESTING"
    assert catalog.track("cooking") is None


def test_every_rules_topic_has_text():
    rules = load_rules()
    for topic in ["xp", "streak", "discovery", "tracks", "lessons", "squad", "mentor", "jobs", "account"]:
        assert rules[topic].startswith("- ")
