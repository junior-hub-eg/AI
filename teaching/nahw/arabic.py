"""Arabic text helpers: normalization, tokenization, sentence splitting, reading the final diacritic."""
import re

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
PUNCT = ".,،؛;:!?؟\"'«»()[]{}-–—…"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!؟?؛])\s+|\n+")


def strip_tashkeel(text: str) -> str:
    return TASHKEEL.sub("", text)


def normalize(text: str) -> str:
    t = strip_tashkeel(text)
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = "".join(ch for ch in t if ch not in PUNCT)
    return re.sub(r"\s+", " ", t).strip()


def tokenize(sentence: str) -> list[str]:
    tokens = []
    for raw in sentence.split():
        tok = raw.strip(PUNCT)
        if tok:
            tokens.append(tok)
    return tokens


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text or "")]
    return [p for p in parts if tokenize(p)]


def final_mark(word: str) -> str | None:
    """Return the sign implied by the word's ending, or None if it can't be read."""
    bare = strip_tashkeel(word)
    if re.search(r"ون$", bare) and len(bare) > 4:
        return "الواو"
    if re.search(r"ان$", bare) and word.endswith("ِ") and len(bare) > 4:
        return "الألف"
    if re.search(r"ين$", bare) and len(bare) > 4:
        return "الياء"
    for ch in reversed(word):
        if ch in "ٌُ":
            return "الضمة"
        if ch in "ًَ":
            return "الفتحة"
        if ch in "ٍِ":
            return "الكسرة"
        if ch == "ْ":
            return "السكون"
        if ch == "ّ":
            continue
        if not TASHKEEL.match(ch):
            break
    if word.endswith("ًا") or word.endswith("اً"):
        return "الفتحة"
    return None
