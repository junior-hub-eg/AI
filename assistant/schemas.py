"""Wire shapes of docs/API.md (snake_case JSON)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Level = Literal["Beginner", "Intermediate", "Advanced"]
Topic = Literal[
    "my_progress", "learning", "tracks", "discovery", "squad", "mentor", "jobs",
    "platform", "concept_help", "small_talk", "out_of_scope", "wellbeing",
]
LinkKind = Literal["lesson", "track", "mentor", "squad", "discovery", "achievements", "jobs"]
Gender = Literal["Male", "Female"]

MAX_MESSAGE = 1000
MAX_HISTORY = 20
MAX_REPLY = 2000
MAX_SUGGESTION = 80
MAX_FIRST_NAME = 30


class Model(BaseModel):
    # Unknown fields are ignored, so the backend can add context without breaking the service.
    model_config = ConfigDict(extra="ignore")


# ----- context ---------------------------------------------------------------------------------------------------

class StudentFacts(Model):
    # Profile: the first name only (never the full name), to greet the student, and boy or girl, so Arabic replies
    # address them correctly. Both may be missing (an older backend, or a student who has not set the gender yet).
    first_name: str | None = None
    gender: Gender | None = None
    member_since: date | None = None
    grade: int | None = None
    is_independent: bool = False
    total_xp: int = 0
    streak_days: int = 0
    last_active_date: date | None = None

    @field_validator("first_name", mode="before")
    @classmethod
    def first_word(cls, value):
        # The name goes into the prompt: keep one short word, so a full name or a long text cannot get in.
        if not isinstance(value, str):
            return None
        word = next(iter(value.split()), "")[:MAX_FIRST_NAME]
        return word or None


class Recommendation(Model):
    rank: int
    track_code: str
    match_percent: int
    reason: str = ""
    level: Level = "Beginner"
    level_reason: str = ""


class Discovery(Model):
    status: Literal["NotStarted", "InProgress", "Completed"] = "NotStarted"
    path: str | None = None
    completed_utc: datetime | None = None
    summary: str | None = None
    recommendations: list[Recommendation] = []


class StudentTrack(Model):
    code: str
    name: str
    level: Level = "Beginner"
    source: str | None = None
    in_focus: bool = False
    selected_utc: datetime | None = None
    lessons_done: int = 0
    lessons_total: int = 0


class Exploration(Model):
    track_code: str
    videos_completed: int = 0
    videos_total: int = 0
    quiz_passed: bool = False
    best_quiz_score: int | None = None
    quiz_total: int = 0


class SchoolLinkRef(Model):
    subject: str
    title: str


class LessonState(Model):
    id: str
    module: str | None = None
    title: str
    concept: str | None = None
    level: Level = "Beginner"
    status: Literal["NotStarted", "InProgress", "Done"] = "NotStarted"
    current_step: str | None = None
    quiz_attempts: int = 0
    in_path: bool = True
    school_link: SchoolLinkRef | None = None


class Learning(Model):
    track_code: str
    next_lesson_id: str | None = None
    lessons: list[LessonState] = []


class Badge(Model):
    code: str
    name: str
    type: str | None = None
    earned_utc: datetime | None = None


class XpItem(Model):
    reason: str
    points: int
    created_utc: datetime | None = None


class Achievements(Model):
    badges: list[Badge] = []
    recent_xp: list[XpItem] = []


class SquadMember(Model):
    role: str
    is_me: bool = False
    # A teammate's first name; not sent for the student themself.
    name: str | None = None


class Sprint(Model):
    name: str
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None
    tasks_done: int = 0
    tasks_total: int = 0


class SquadTask(Model):
    title: str
    status: str
    story_points: int = 0


class Squad(Model):
    name: str
    project_title: str | None = None
    project_description: str | None = None
    my_role: str | None = None
    members: list[SquadMember] = []
    sprint: Sprint | None = None
    my_tasks: list[SquadTask] = []


class Mentor(Model):
    id: str | None = None
    full_name: str
    title: str | None = None
    track_code: str | None = None
    languages: str | None = None
    availability: str | None = None
    started_utc: datetime | None = None


class Application(Model):
    role: str
    company_name: str
    track_code: str | None = None
    level: str | None = None
    status: str
    attempts: int = 0
    best_score_percent: int | None = None
    certificate_code: str | None = None


class Recruitment(Model):
    applications: list[Application] = []


class AssistantContext(Model):
    today: date
    student: StudentFacts = StudentFacts()
    discovery: Discovery = Discovery()
    tracks: list[StudentTrack] = []
    exploration: list[Exploration] = []
    learning: Learning | None = None
    achievements: Achievements = Achievements()
    squad: Squad | None = None
    mentor: Mentor | None = None
    recruitment: Recruitment = Recruitment()

    @property
    def focus_track(self) -> StudentTrack | None:
        return next((t for t in self.tracks if t.in_focus), self.tracks[0] if self.tracks else None)


# ----- request / response ----------------------------------------------------------------------------------------

class HistoryItem(Model):
    role: Literal["student", "assistant"]
    text: str


class ReplyRequest(Model):
    conversation_id: UUID
    student_ref: UUID
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)
    context: AssistantContext

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message is empty")
        return value


class Link(Model):
    kind: LinkKind
    ref: str = ""
    label: str = ""


class Meta(Model):
    prompt_version: str
    model_id: str | None = None
    latency_ms: int | None = None


class ReplyResponse(Model):
    reply: str
    suggestions: list[str] = []
    links: list[Link] = []
    topic: Topic = "small_talk"
    meta: Meta
