"""Tools the assistant can call. Each reads only the request's context and the catalog.

The student is never a parameter: tools get the context of the student who sent the message from the run config,
so a question cannot reach another student's data.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .catalog import Catalog, load_catalog, load_rules
from .schemas import MAX_SUGGESTION, AssistantContext, LinkKind, Topic

RuleTopic = Literal["xp", "streak", "discovery", "tracks", "lessons", "squad", "mentor", "jobs", "account"]


def _ctx(config: RunnableConfig) -> AssistantContext:
    return config["configurable"]["assistant_ctx"]


def _catalog(config: RunnableConfig) -> Catalog:
    return config["configurable"].get("catalog") or load_catalog()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@tool
def get_my_learning(config: RunnableConfig) -> str:
    """The lessons of the student's track in focus: each lesson's status and current step, and the next lesson to do."""
    ctx, catalog = _ctx(config), _catalog(config)
    if ctx.learning is None:
        return _json({"has_track": False, "note": "The student has no track yet. Track Discovery or the tracks page helps choose one."})
    track = catalog.track(ctx.learning.track_code)
    if not ctx.learning.lessons:
        return _json({"track_code": ctx.learning.track_code, "has_lessons": False,
                      "note": f"{track['name'] if track else ctx.learning.track_code} has no lessons yet: only its videos and quiz."})
    next_lesson = next((lesson for lesson in ctx.learning.lessons if lesson.id == ctx.learning.next_lesson_id), None)
    return _json({
        "track_code": ctx.learning.track_code,
        "lessons": [lesson.model_dump(mode="json", exclude_none=True) for lesson in ctx.learning.lessons],
        "next_lesson": next_lesson.model_dump(mode="json", exclude_none=True) if next_lesson else None,
        "all_done": next_lesson is None,
    })


@tool
def get_lesson_help(lesson: str, config: RunnableConfig) -> str:
    """Content of one lesson to explain it: concept, Try it starter code and expected output, the school link
    (what the student saw at school and how it connects), and the student's progress in it.
    `lesson` is a lesson id or title, for example "Functions"."""
    ctx, catalog = _ctx(config), _catalog(config)
    found = catalog.lesson(lesson)
    if found is None:
        titles = [item["title"] for m in catalog.modules for item in m["lessons"]]
        return _json({"found": False, "available_lessons": titles})
    state = None
    if ctx.learning:
        state = next((item for item in ctx.learning.lessons if item.id == found["id"]), None)
    link = found["school_link"]
    # A school link only shows for the student's own grade (BR-09).
    if link and ctx.student.grade is not None and link["grade"] != ctx.student.grade:
        link = None
    return _json({
        "id": found["id"], "title": found["title"], "concept": found["concept"], "level": found["level"],
        "track_code": found["track_code"], "module": found["module"], "video_minutes": round(found["duration_seconds"] / 60, 1),
        "try_it_starter_code": found["try_it_starter_code"], "try_it_expected_output": found["try_it_expected_output"],
        "quiz_question_count": found["quiz_question_count"], "school_link": link,
        "my_progress": state.model_dump(mode="json", exclude_none=True) if state else None,
        "reminder": "Explain and hint. Never give quiz answers or the full Try it solution.",
    })


@tool
def get_discovery_result(config: RunnableConfig) -> str:
    """The student's latest Track Discovery result: summary, top 3 tracks with match %, reasons and levels."""
    return _json(_ctx(config).discovery.model_dump(mode="json", exclude_none=True))


@tool
def get_track_info(track_code: str, config: RunnableConfig) -> str:
    """What a track is about (description, videos, whether it has lessons), its mentors and practice jobs, and how far
    the student got with its videos and quiz. Codes: MOBILE, FRONTEND, BACKEND, UIUX, AI, TESTING, DATA, GAMING."""
    ctx, catalog = _ctx(config), _catalog(config)
    track = catalog.track(track_code)
    if track is None:
        return _json({"found": False, "codes": [t["code"] for t in catalog.tracks]})
    mine = next((t for t in ctx.tracks if t.code == track["code"]), None)
    explored = next((e for e in ctx.exploration if e.track_code == track["code"]), None)
    recommended = next((r for r in ctx.discovery.recommendations if r.track_code == track["code"]), None)
    return _json({
        **track,
        "lesson_titles": [lesson["title"] for lesson in catalog.lessons_of(track["code"])],
        "mentors": [m["full_name"] for m in catalog.mentors_of(track["code"])],
        "practice_jobs": [j["role"] for j in catalog.jobs_of(track["code"])],
        "i_am_learning_it": mine.model_dump(mode="json", exclude_none=True) if mine else None,
        "my_videos_and_quiz": explored.model_dump(mode="json", exclude_none=True) if explored else None,
        "in_my_discovery_result": recommended.model_dump(mode="json", exclude_none=True) if recommended else None,
    })


@tool
def get_my_achievements(config: RunnableConfig) -> str:
    """The student's XP (total, where it came from, latest gains), streak and badges, plus the badges they can still earn."""
    ctx, catalog = _ctx(config), _catalog(config)
    by_reason: dict[str, int] = defaultdict(int)
    for item in ctx.achievements.recent_xp:
        by_reason[item.reason] += item.points
    earned = {b.code for b in ctx.achievements.badges}
    lessons = catalog.lessons_of(ctx.learning.track_code) if ctx.learning else []
    to_earn = [
        {"badge": lesson["school_link"]["badge"]["name"], "by_passing_lesson": lesson["title"]}
        for lesson in lessons
        if lesson["school_link"] and lesson["school_link"]["badge"]["code"] not in earned
    ]
    return _json({
        "total_xp": ctx.student.total_xp, "streak_days": ctx.student.streak_days,
        "last_active_date": ctx.student.last_active_date,
        "recent_xp_by_reason": by_reason, "recent_xp": [x.model_dump(mode="json", exclude_none=True) for x in ctx.achievements.recent_xp[:10]],
        "badges": [b.model_dump(mode="json", exclude_none=True) for b in ctx.achievements.badges],
        "badges_to_earn": to_earn,
    })


@tool
def get_my_squad(config: RunnableConfig) -> str:
    """The student's squad: project, teammates (first name and role), the active sprint (dates, progress) and the student's own tasks."""
    ctx = _ctx(config)
    if ctx.squad is None:
        return _json({"in_squad": False})
    squad = ctx.squad.model_dump(mode="json", exclude_none=True)
    if ctx.squad.sprint and ctx.squad.sprint.end_date:
        squad["sprint"]["days_left"] = max(0, (ctx.squad.sprint.end_date - ctx.today).days)
    return _json({"in_squad": True, **squad})


@tool
def find_mentors(config: RunnableConfig, track_code: str | None = None) -> str:
    """The student's current mentor, and mentors to choose from: of `track_code`, or of the track in focus when empty."""
    ctx, catalog = _ctx(config), _catalog(config)
    focus = ctx.focus_track
    code = catalog.track(track_code)["code"] if track_code and catalog.track(track_code) else (focus.code if focus else None)
    return _json({
        "my_mentor": ctx.mentor.model_dump(mode="json", exclude_none=True) if ctx.mentor else None,
        "track_code": code,
        "mentors": catalog.mentors_of(code),
    })


@tool
def find_practice_jobs(config: RunnableConfig, track_code: str | None = None) -> str:
    """Practice jobs (Simulation) of `track_code` or all of them, and the student's own applications and results."""
    ctx, catalog = _ctx(config), _catalog(config)
    code = catalog.track(track_code)["code"] if track_code and catalog.track(track_code) else None
    return _json({
        "disclaimer": catalog.jobs["disclaimer"],
        "jobs": catalog.jobs_of(code),
        "my_applications": [a.model_dump(mode="json", exclude_none=True) for a in ctx.recruitment.applications],
    })


@tool
def get_platform_rules(topic: RuleTopic) -> str:
    """How Junior Hub works for one topic: xp, streak, discovery, tracks, lessons, squad, mentor, jobs or account."""
    return load_rules().get(topic, "")


class LinkArg(BaseModel):
    kind: LinkKind
    ref: str = Field("", description="Lesson id, track code or mentor id. Empty for squad, discovery, achievements, jobs.")
    label: str = ""


@tool
def respond(
    reply: str,
    topic: Topic,
    suggestions: list[str] | None = None,
    links: list[LinkArg] | None = None,
) -> str:
    """Send the final answer to the student. Always finish with this tool.
    reply: the answer, in the student's language, short and friendly.
    topic: what the question was about.
    suggestions: up to 3 short follow-up questions the student may tap (each under 80 characters), in their language.
    links: up to 3 pages to open, only with ids or codes you saw in tool results or the snapshot."""
    return "sent"


DATA_TOOLS = [
    get_my_learning, get_lesson_help, get_discovery_result, get_track_info, get_my_achievements,
    get_my_squad, find_mentors, find_practice_jobs, get_platform_rules,
]
ALL_TOOLS = [*DATA_TOOLS, respond]
RESPOND = respond.name

__all__ = ["ALL_TOOLS", "DATA_TOOLS", "RESPOND", "MAX_SUGGESTION"]
