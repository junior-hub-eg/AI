"""Builds the chat messages sent to the LLM.

Layout keeps the STATIC part (instructions + track list) first and the
conversation last, so provider-side prompt caching can reuse the prefix.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import Settings
from app.providers.base import Message
from app.schemas.common import QA, Track
from app.services.prompts import Prompt
from app.services.question_policy import focus_for
from app.services.text import neutralize_markup, truncate_words


def render_tracks(tracks: Sequence[Track], max_chars: int) -> str:
    return "\n".join(f"- {t.code} ({t.name}): {truncate_words(t.profile, max_chars)}" for t in tracks)


def render_conversation(items: Sequence[QA], max_chars: int) -> str:
    lines: list[str] = []
    for qa in items:
        lines.append(f"Question {qa.order_index}: {neutralize_markup(qa.question_text)}")
        answer = truncate_words(neutralize_markup(qa.transcript), max_chars)
        lines.append(f"<student_answer>{answer}</student_answer>")
    return "\n".join(lines)


def build_turn_messages(
    prompt: Prompt,
    settings: Settings,
    *,
    tracks: Sequence[Track],
    grade: int,
    conversation: Sequence[QA],
    question_number: int,
    max_questions: int,
) -> list[Message]:
    tracks_block = (
        render_tracks(tracks, settings.profile_max_chars_turn)
        if settings.include_tracks_in_turn
        else "(not provided)"
    )
    user = "\n".join(
        [
            f"Student grade: {grade}",
            f"This is question {question_number} of {max_questions}.",
            f"Suggested focus for this question: {focus_for(question_number, max_questions)}.",
            "(Use the suggested focus unless the latest answer calls for a natural follow-up.)",
            "",
            "Conversation so far:",
            render_conversation(conversation, settings.transcript_max_chars_in_prompt),
            "",
            f"Write question {question_number} now. Respond with the JSON object only.",
        ]
    )
    return [
        {"role": "system", "content": prompt.render(tracks_block=tracks_block)},
        {"role": "user", "content": user},
    ]


def build_result_messages(
    prompt: Prompt,
    settings: Settings,
    *,
    tracks: Sequence[Track],
    grade: int,
    responses: Sequence[QA],
) -> list[Message]:
    system = prompt.render(
        tracks_block=render_tracks(tracks, settings.profile_max_chars_result),
        allowed_codes=", ".join(t.code for t in tracks),
    )
    user = "\n".join(
        [
            f"Student grade: {grade}",
            "",
            "Interview transcript:",
            render_conversation(responses, settings.transcript_max_chars_in_prompt),
            "",
            "Produce the recommendation now. Respond with the JSON object only.",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
