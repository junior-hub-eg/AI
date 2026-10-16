"""Mock Discovery AI service: fixed answers, no models, no key, no auth check.

Lets the backend team integrate BEFORE the real models are ready.

    uvicorn mock.mock_server:app --port 8001

Pick a behaviour per request with the header  X-Mock-Scenario:
    ok (default) | slow (12 s) | timeout (40 s) | provider_down (503)
    unauthenticated (401) | audio_unsupported (415) | audio_too_large (413)
    unintelligible (422) | bad_result (only 2 tracks: the backend must reject it)
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

from app.schemas.common import Meta
from app.schemas.result import RecommendationOut, ResultRequest, ResultResponse
from app.schemas.turn import AnsweredOut, QuestionOut, TurnRequest, TurnResponse
from app.services.wav import silent_wav

app = FastAPI(title="Discovery AI - MOCK", version="mock")

_QUESTIONS = json.loads(
    (Path(__file__).resolve().parents[1] / "content" / "fallback_questions.json").read_text(encoding="utf-8")
)["questions"]
_AUDIO = base64.b64encode(silent_wav()).decode()
_ERRORS = {
    "provider_down": (503, "PROVIDER_UNAVAILABLE"),
    "unauthenticated": (401, "UNAUTHENTICATED"),
    "audio_unsupported": (415, "AUDIO_UNSUPPORTED"),
    "audio_too_large": (413, "AUDIO_TOO_LARGE"),
    "unintelligible": (422, "AUDIO_UNINTELLIGIBLE"),
}


async def _scenario(name: str) -> JSONResponse | None:
    if name == "slow":
        await asyncio.sleep(12)
    elif name == "timeout":
        await asyncio.sleep(40)
    elif name in _ERRORS:
        status, code = _ERRORS[name]
        return JSONResponse(
            {"error": {"code": code, "message": f"mock: {name}", "request_id": "mock"}}, status_code=status
        )
    return None


@app.post("/v1/discovery/turns", response_model=TurnResponse)
async def turns(body: TurnRequest, x_mock_scenario: str = Header(default="ok")):
    if failure := await _scenario(x_mock_scenario):
        return failure
    meta = Meta(prompt_version="mock@v1", model_id="mock", latency_ms=5)
    answered = None
    done = len(body.history)
    if body.answer:
        text = body.answer.transcript or "I like drawing and building small games."
        answered = AnsweredOut(order_index=body.answer.order_index, transcript=text)
        done = body.answer.order_index
    if done >= body.max_questions:
        return TurnResponse(
            interview_id=body.interview_id, answered=answered, next_question=None, finished=True, meta=meta
        )
    number = done + 1
    question = QuestionOut(
        order_index=number,
        question_text=_QUESTIONS[(number - 1) % len(_QUESTIONS)],
        audio_base64=_AUDIO if body.speak else None,
        audio_mime_type="audio/wav" if body.speak else None,
    )
    return TurnResponse(
        interview_id=body.interview_id, answered=answered, next_question=question, finished=False, meta=meta
    )


@app.post("/v1/discovery/results", response_model=ResultResponse)
async def results(body: ResultRequest, x_mock_scenario: str = Header(default="ok")):
    if failure := await _scenario(x_mock_scenario):
        return failure
    reasons = (
        "You enjoy making things you can see and click.",
        "You care about how things look and feel.",
        "You like spotting patterns and solving puzzles.",
    )
    picks = [
        RecommendationOut(rank=i, track_code=t.code, match_percent=pct, reason=reason)
        for i, (t, pct, reason) in enumerate(zip(body.tracks, (86, 74, 61), reasons, strict=False), 1)
    ]
    if x_mock_scenario == "bad_result":
        picks = picks[:2]  # invalid on purpose; bypass response model validation below
        return JSONResponse(
            {
                "interview_id": body.interview_id,
                "recommendations": [p.model_dump() for p in picks],
                "summary": "Mock invalid result.",
                "meta": {"prompt_version": "mock@v1", "model_id": "mock", "latency_ms": 5},
            }
        )
    return ResultResponse(
        interview_id=body.interview_id,
        recommendations=picks,
        summary="You like creating things and working out how they behave. Have fun exploring these tracks!",
        meta=Meta(prompt_version="mock@v1", model_id="mock", latency_ms=5),
    )
