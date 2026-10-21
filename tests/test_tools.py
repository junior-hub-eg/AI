import json

from app.catalog import load_catalog
from app.tools import (
    find_mentors, find_practice_jobs, get_lesson_help, get_my_achievements, get_my_learning, get_my_squad,
    get_platform_rules, get_track_info,
)


def run(tool, ctx, **args):
    config = {"configurable": {"assistant_ctx": ctx, "catalog": load_catalog()}}
    return json.loads(tool.invoke(args, config=config))


def test_learning_shows_the_next_lesson_of_the_track_in_focus(context):
    result = run(get_my_learning, context("frontend_beginner"))
    assert result["next_lesson"]["title"] == "Functions"
    assert result["next_lesson"]["current_step"] == "TryIt"
    assert [lesson["status"] for lesson in result["lessons"]] == ["Done", "InProgress", "NotStarted", "NotStarted"]


def test_learning_without_a_track_says_so(context):
    assert run(get_my_learning, context("new_student"))["has_track"] is False


def test_learning_in_a_track_without_lessons(context):
    result = run(get_my_learning, context("uiux_no_lessons"))
    assert result["has_lessons"] is False and "UI/UX" in result["note"]


def test_lesson_help_has_try_it_and_school_link_but_no_quiz(context):
    result = run(get_lesson_help, context("frontend_beginner"), lesson="functions")
    assert result["title"] == "Functions"
    assert "return 2 * x + 3" in result["try_it_starter_code"]
    assert result["school_link"]["title"] == "Linear functions"
    assert result["my_progress"]["status"] == "InProgress"
    assert "options" not in json.dumps(result) and "correct" not in json.dumps(result).lower()


def test_lesson_help_hides_a_school_link_of_another_grade(context):
    ctx = context("frontend_beginner")
    ctx.student.grade = 7
    assert run(get_lesson_help, ctx, lesson="Functions")["school_link"] is None


def test_unknown_lesson_lists_the_real_ones(context):
    result = run(get_lesson_help, context("frontend_beginner"), lesson="Quantum loops")
    assert result["found"] is False and "Variables" in result["available_lessons"]


def test_achievements_list_only_badges_still_to_earn(context):
    result = run(get_my_achievements, context("frontend_beginner"))
    assert result["total_xp"] == 100
    assert result["recent_xp_by_reason"]["TaskDone"] == 40
    to_earn = [b["by_passing_lesson"] for b in result["badges_to_earn"]]
    assert "Variables" not in to_earn and "Functions" in to_earn


def test_squad_counts_days_left_and_shows_roles_only(context):
    result = run(get_my_squad, context("frontend_beginner"))
    assert result["sprint"]["days_left"] == 4
    names = {m.get("name") for m in result["members"] if not m["is_me"]}
    assert names == {"Nour", "Mohammed", "Youssef"}
    assert "name" not in next(m for m in result["members"] if m["is_me"])


def test_no_squad(context):
    assert run(get_my_squad, context("intermediate_two_tracks")) == {"in_squad": False}


def test_mentors_default_to_the_track_in_focus(context):
    result = run(find_mentors, context("frontend_beginner"))
    assert result["my_mentor"]["full_name"] == "Sara El-Masry"
    assert {m["track_code"] for m in result["mentors"]} == {"FRONTEND"}
    assert result["mentors"][0]["full_name"] == "Sara El-Masry"  # best rated first


def test_mentors_of_another_track(context):
    result = run(find_mentors, context("frontend_beginner"), track_code="ui/ux")
    assert [m["full_name"] for m in result["mentors"]] == ["Layla Adel"]


def test_jobs_are_simulations_with_my_results(context):
    result = run(find_practice_jobs, context("intermediate_two_tracks"), track_code="FRONTEND")
    assert "not real jobs" in result["disclaimer"]
    assert [j["company_name"] for j in result["jobs"]] == ["Pixel Lane Studio"]
    assert result["my_applications"][0]["certificate_code"] == "JH-SIM-4F7K2Q"


def test_track_info_combines_catalog_and_my_progress(context):
    result = run(get_track_info, context("frontend_beginner"), track_code="FRONTEND")
    assert result["has_lessons"] is True
    assert result["in_my_discovery_result"]["rank"] == 1
    assert result["my_videos_and_quiz"]["quiz_passed"] is True
    assert "Sara El-Masry" in result["mentors"]


def test_rules_tool_returns_the_section():
    assert "40 XP" in get_platform_rules.invoke({"topic": "xp"})
