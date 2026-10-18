"""POST /v1/discovery/results."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.schemas.common import QA, ApiModel, Meta, Track


class ResultRequest(ApiModel):
    interview_id: str = Field(min_length=1, max_length=64)
    student_ref: str = Field(min_length=1, max_length=64)
    grade: int = Field(ge=1, le=13)
    tracks: list[Track] = Field(min_length=3, max_length=20)
    # The 5..10 bounds are enforced by the service (they are configurable).
    responses: list[QA] = Field(min_length=1, max_length=50)
    # true = also return the summary as speech (used by the call-style interview page).
    speak: bool = False

    @model_validator(mode="after")
    def _unique_codes(self) -> Self:
        codes = [t.code for t in self.tracks]
        if len(codes) != len(set(codes)):
            raise ValueError("track codes must be unique")
        return self


class RecommendationOut(ApiModel):
    rank: int = Field(ge=1, le=3)
    track_code: str
    match_percent: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=300)


class ResultResponse(ApiModel):
    interview_id: str
    recommendations: list[RecommendationOut]
    summary: str
    # Only when the request had speak=true and speech synthesis worked.
    summary_audio_base64: str | None = None
    summary_audio_mime_type: str | None = None
    meta: Meta
