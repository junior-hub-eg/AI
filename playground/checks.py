"""One-click contract checks: send good and bad requests, compare the status codes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from playground.api import DiscoveryApi
from playground.payloads import audio_answer, result_payload, sample_history, text_answer, turn_payload

TURNS, RESULTS = "/v1/discovery/turns", "/v1/discovery/results"


@dataclass(frozen=True)
class Check:
    name: str
    path: str
    payload: Callable[[], dict[str, Any]]
    expected: int
    with_token: bool = True


def build_checks(tracks: list[dict], grade: int, *, auth_enabled: bool) -> list[Check]:
    def turn(**kw: Any) -> dict[str, Any]:
        return (
            turn_payload(
                interview_id="chk",
                tracks=tracks,
                grade=grade,
                history=[],
                answer=None,
                max_questions=10,
                speak=False,
            )
            | kw
        )

    def result(**kw: Any) -> dict[str, Any]:
        return (
            result_payload(interview_id="chk", tracks=tracks, grade=grade, responses=sample_history(6)) | kw
        )

    q = "Q?"
    checks = [
        Check("Turn 1: opening question", TURNS, turn, 200),
        Check(
            "Turn: text answer",
            TURNS,
            lambda: turn(answer=text_answer(1, q, "I like drawing and games.")),
            200,
        ),
        Check(
            "Turn: last answer finishes the interview",
            TURNS,
            lambda: turn(
                history=sample_history(2), max_questions=3, answer=text_answer(3, q, "My last answer.")
            ),
            200,
        ),
        Check(
            "Turn: unsupported audio type -> 415",
            TURNS,
            lambda: turn(answer=audio_answer(1, q, b"abc", "audio/flac")),
            415,
        ),
        Check(
            "Turn: invalid base64 -> 400",
            TURNS,
            lambda: turn(
                answer={
                    "order_index": 1,
                    "question_text": q,
                    "audio_base64": "!!!",
                    "audio_mime_type": "audio/wav",
                }
            ),
            400,
        ),
        Check(
            "Turn: text AND audio together -> 400",
            TURNS,
            lambda: turn(
                answer={
                    "order_index": 1,
                    "question_text": q,
                    "transcript": "hi",
                    "audio_base64": "AAAA",
                    "audio_mime_type": "audio/wav",
                }
            ),
            400,
        ),
        Check(
            "Turn: audio over 10 MB -> 413",
            TURNS,
            lambda: turn(answer=audio_answer(1, q, b"\0" * (10 * 1024 * 1024 + 16), "audio/wav")),
            413,
        ),
        Check("Turn: missing fields -> 400", TURNS, lambda: {"interview_id": "x"}, 400),
        Check("Result: 6 answers", RESULTS, result, 200),
        Check("Result: only 3 answers -> 400", RESULTS, lambda: result(responses=sample_history(3)), 400),
        Check("Result: fewer than 3 tracks -> 400", RESULTS, lambda: result(tracks=tracks[:2]), 400),
        Check("Result: duplicate track codes -> 400", RESULTS, lambda: result(tracks=[tracks[0]] * 3), 400),
    ]
    if auth_enabled:
        checks += [
            Check("Auth: no token -> 401", TURNS, turn, 401, with_token=False),
        ]
    return checks


def run_checks(api: DiscoveryApi, checks: list[Check]) -> list[dict[str, Any]]:
    rows = []
    for check in checks:
        result = api.post(check.path, check.payload(), with_token=check.with_token)
        rows.append(
            {
                "check": check.name,
                "expected": check.expected,
                "got": result.status,
                "seconds": round(result.seconds, 2),
                "result": "PASS" if result.status == check.expected else "FAIL",
            }
        )
    return rows
