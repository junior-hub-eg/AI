"""Builders for the request bodies of the two endpoints."""

from __future__ import annotations

import base64
from typing import Any

from playground.sample_data import ANSWERS

STUDENT_REF = "stu_playground"


def text_answer(order_index: int, question_text: str, text: str) -> dict[str, Any]:
    return {"order_index": order_index, "question_text": question_text, "transcript": text}


def audio_answer(order_index: int, question_text: str, audio: bytes, mime_type: str) -> dict[str, Any]:
    return {
        "order_index": order_index,
        "question_text": question_text,
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "audio_mime_type": mime_type,
    }


def turn_payload(
    *,
    interview_id: str,
    tracks: list[dict],
    grade: int,
    history: list[dict],
    answer: dict | None,
    max_questions: int,
    speak: bool,
) -> dict[str, Any]:
    return {
        "interview_id": interview_id,
        "student_ref": STUDENT_REF,
        "grade": grade,
        "tracks": tracks,
        "history": history,
        "answer": answer,
        "max_questions": max_questions,
        "speak": speak,
    }


def result_payload(
    *, interview_id: str, tracks: list[dict], grade: int, responses: list[dict]
) -> dict[str, Any]:
    return {
        "interview_id": interview_id,
        "student_ref": STUDENT_REF,
        "grade": grade,
        "tracks": tracks,
        "responses": responses,
    }


def sample_history(count: int) -> list[dict[str, Any]]:
    return [
        {
            "order_index": i,
            "question_text": f"Sample question {i}?",
            "transcript": ANSWERS[(i - 1) % len(ANSWERS)],
        }
        for i in range(1, count + 1)
    ]
