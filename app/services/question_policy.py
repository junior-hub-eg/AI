"""What each question should explore, and the checks every question must pass."""

from __future__ import annotations

import re

from app.services.text import clean_spoken_text

MAX_WORDS = 45

# One focus per question. Question 1 is the fixed opener (free time).
FOCUS_PLAN = (
    "free time: what they enjoy doing when they are not at school",
    "school: which school subjects they like and what they enjoy about them",
    "making things: do they prefer making things look good (drawing, designing, "
    "decorating) or figuring out how things work (fixing, building, puzzles)",
    "problem solving: a time something was hard or did not work, and what they did",
    "games and apps: games, apps or websites they love and what they like about them",
    "teamwork: whether they like working in a team or alone, and what role they take",
    "following a spark: dig deeper into the interest that has shown up most strongly so far",
    "numbers and patterns: whether they enjoy puzzles, numbers, collecting information or spotting patterns",
    "curiosity: something they have wondered how it works (phones, websites, robots, games)",
    "dream project: what they would love to create if they could make anything with technology",
)

_PERSONAL_INFO = re.compile(
    r"\b(?:what(?:'s| is) your (?:full |first |last )?name|your (?:full |first |last |sur)name"
    r"|where do you live|your (?:home )?address|(?:phone|mobile|telephone) (?:number|no)"
    r"|e-?mail|(?:which|what) school (?:do|are) you|name of your school|school name"
    r"|your school'?s? name|how old are you|your birthday|date of birth|password"
    r"|(?:instagram|snapchat|tiktok|facebook|whatsapp|social media) "
    r"(?:account|handle|username|name))\b",
    re.IGNORECASE,
)


def focus_for(question_number: int, max_questions: int) -> str:
    if question_number >= max_questions:
        return FOCUS_PLAN[-1]
    return FOCUS_PLAN[min(max(question_number - 1, 0), len(FOCUS_PLAN) - 2)]


def validate_question(raw: str) -> str:
    """Return the cleaned question or raise ValueError (the model will be asked to repair)."""
    text = clean_spoken_text(raw)
    if not text:
        raise ValueError("question_text is empty")
    if len(text.split()) > MAX_WORDS:
        raise ValueError("the question is too long: use at most 35 words")
    if text.count("?") > 2:
        raise ValueError("ask exactly one question")
    if _PERSONAL_INFO.search(text):
        raise ValueError("the question asks for personal information; ask about interests instead")
    return text
