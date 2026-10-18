"""Small, dependency-free text helpers."""

from __future__ import annotations

import re

_MARKDOWN = re.compile(r"[*_`#>~|]+")
_EMOJI = re.compile("[\U0001f000-\U0001ffff\u2600-\u27bf\ufe0f\u200d]")
_SENTENCE_END = re.compile(r"(?<=[.!?\u061f\u06d4])\s+")  # also Arabic ؟ and ۔
_ARABIC_DIACRITICS = re.compile("[\u064b-\u0652\u0640]")  # tashkeel + tatweel

# Whisper tends to invent these phrases when it is given silence or noise.
_HALLUCINATIONS = frozenset(
    {
        "thank you",
        "thanks",
        "thanks for watching",
        "thank you for watching",
        "you",
        "bye",
        "bye bye",
        "subtitles by the amaraorg community",
        # Arabic phrases Whisper invents on silence (diacritics removed).
        "شكرا",
        "شكرا لكم",
        "شكرا للمشاهدة",
        "اشتركوا في القناة",
        "اشترك في القناة",
        "ترجمة نانسي قنقر",
        "موسيقى",
        "السلام عليكم",
    }
)


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def truncate_words(text: str, limit: int) -> str:
    """Shorten to at most `limit` characters on a word boundary."""
    text = collapse_whitespace(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{cut or text[: limit - 1]}…"


def neutralize_markup(text: str) -> str:
    """Remove angle brackets so student text cannot close our prompt tags."""
    return collapse_whitespace(text.replace("<", " ").replace(">", " "))


def clean_spoken_text(text: str) -> str:
    """Make model output safe to display and to read aloud."""
    text = _EMOJI.sub("", text)
    text = _MARKDOWN.sub("", text)
    return collapse_whitespace(text).strip(" \"'“”‘’")


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks of at most `max_chars`, preferring sentence bounds."""
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        pieces = [sentence]
        if len(sentence) > max_chars:
            pieces, line = [], ""
            for word in sentence.split():
                if line and len(line) + 1 + len(word) > max_chars:
                    pieces.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
            if line:
                pieces.append(line)
        for piece in pieces:
            if current and len(current) + 1 + len(piece) > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks


def clean_transcript(text: str) -> str:
    """Normalise speech-to-text output; return '' when it is not a real answer."""
    text = collapse_whitespace(text)
    if sum(ch.isalnum() for ch in text) < 2:
        return ""
    plain = _ARABIC_DIACRITICS.sub("", text.lower())
    normalised = collapse_whitespace(re.sub(r"[^a-z\u0621-\u064a ]", "", plain))
    return "" if normalised in _HALLUCINATIONS else text


def question_marks(text: str) -> int:
    """Count question marks in English and Arabic."""
    return text.count("?") + text.count("\u061f")
