"""Building blocks shared by the request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    # Unknown fields are ignored so the backend can add fields without breaking us.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class Track(ApiModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    profile: str = Field(min_length=1, max_length=2000)


class QA(ApiModel):
    """One answered question."""

    order_index: int = Field(ge=1, le=50)
    question_text: str = Field(min_length=1, max_length=600)
    transcript: str = Field(min_length=1, max_length=4000)


class Meta(ApiModel):
    prompt_version: str
    model_id: str
    latency_ms: int
