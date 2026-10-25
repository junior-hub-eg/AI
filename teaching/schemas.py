"""Request and response shapes of /v1/teaching/* (contract in docs/teaching/API.md). JSON names are snake_case."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["ar", "en"]


class Meta(BaseModel):
    prompt_version: str
    model_id: str
    latency_ms: int


# ----- Track video ↔ school subject -----------------------------------------------------------------------------

class VideoLinksRequest(BaseModel):
    track_name: str = Field(min_length=1, max_length=120, examples=["Artificial Intelligence"])
    video_title: str = Field(min_length=1, max_length=200, examples=["Computer Vision"])
    video_description: str = Field(default="", max_length=2000)
    subject: str = Field(min_length=1, max_length=60, examples=["Physics"])
    grade: int | None = Field(default=None, ge=1, le=12)
    language: Language = "ar"


class LinkIdea(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=600)


class VideoLinksResponse(BaseModel):
    """The video in 3 points (what it is, how it works, where it is used) and 3 ways to link it to the subject."""

    summary: list[str] = Field(min_length=3, max_length=3)
    ideas: list[LinkIdea] = Field(min_length=3, max_length=3)
    meta: Meta | None = None


# ----- Quick Check (multiple choice) ----------------------------------------------------------------------------

class QuickCheckRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, examples=["Computer Vision and Physics"])
    context: str = Field(default="", max_length=4000, description="What the questions are about.")
    count: int = Field(default=2, ge=1, le=10)
    language: Language = "ar"


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    options: list[str] = Field(min_length=2, max_length=5)
    answer_index: int = Field(ge=0, le=4)
    explanation: str = Field(default="", max_length=600)


class QuickCheckResponse(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=10)
    meta: Meta | None = None


# ----- Grammar coach (Arabic إعراب) --------------------------------------------------------------------------------

Color = Literal["blue", "green", "orange", "purple", "red", "teal", "gray"]


class ParsedWord(BaseModel):
    word: str = Field(min_length=1, max_length=40)
    role: str = Field(min_length=1, max_length=60, description="الموقع الإعرابي، مثل: اسم إنّ")
    case: str = Field(default="", max_length=40, description="مرفوع / منصوب / مجرور / مبني ...")
    sign: str = Field(default="", max_length=60, description="علامة الإعراب، مثل: الفتحة")
    explanation: str = Field(default="", max_length=300)
    color: Color = "gray"


class ParsedSentence(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    words: list[ParsedWord] = Field(min_length=1, max_length=40)


class OcrRequest(BaseModel):
    image_base64: str = Field(min_length=10, max_length=8_000_000)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/jpeg"


class OcrResponse(BaseModel):
    text: str
    meta: Meta | None = None


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


class ParseResponse(BaseModel):
    sentences: list[ParsedSentence] = Field(min_length=1, max_length=30)
    meta: Meta | None = None


class LessonRequest(BaseModel):
    topic_title: str = Field(min_length=1, max_length=80, examples=["إنّ وأخواتها"])
    roles: list[str] = Field(default_factory=list, max_length=20, description="The roles the practice uses.")
    difficulty: int = Field(default=1, ge=1, le=5, description="1 for a new topic, higher after correct answers.")


class LessonPoint(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=400)
    color: Color = "teal"


class LessonResponse(BaseModel):
    """3 to 4 points, two solved sentences and a new sentence for the student (its answers stay with the backend)."""

    points: list[LessonPoint] = Field(min_length=3, max_length=4)
    examples: list[ParsedSentence] = Field(min_length=2, max_length=2)
    practice: ParsedSentence
    meta: Meta | None = None


class Mistake(BaseModel):
    word: str = Field(min_length=1, max_length=40)
    expected: str = Field(min_length=1, max_length=60)
    given: str = Field(default="", max_length=60)


class FeedbackRequest(BaseModel):
    topic_title: str = Field(min_length=1, max_length=80)
    sentence: str = Field(min_length=1, max_length=400)
    mistakes: list[Mistake] = Field(min_length=1, max_length=20)


class GuidingQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=200)


class FeedbackItem(BaseModel):
    word: str
    what: str = Field(min_length=1, max_length=300, description="إيه الغلط")
    why: str = Field(min_length=1, max_length=300, description="السبب")
    guiding_questions: list[GuidingQuestion] = Field(min_length=1, max_length=6)


class FeedbackResponse(BaseModel):
    """For each mistake: what, why, and questions that lead to the right answer; then a similar sentence to try."""

    items: list[FeedbackItem] = Field(min_length=1, max_length=20)
    similar_sentence: ParsedSentence
    meta: Meta | None = None


# ----- Ask the grammar coach -------------------------------------------------------------------------------------

class AskTurn(BaseModel):
    role: Literal["student", "coach"]
    text: str = Field(min_length=1, max_length=600)


class AskRequest(BaseModel):
    """A student's question about a topic; context is the sentence or note they are looking at, if any."""

    topic_title: str = Field(min_length=1, max_length=80, examples=["كان وأخواتها"])
    question: str = Field(min_length=1, max_length=600, examples=["ليه الكلمة دي اسم كان؟"])
    context: str = Field(default="", max_length=600)
    history: list[AskTurn] = Field(default_factory=list, max_length=10)


class AskResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=1200)
    meta: Meta | None = None
