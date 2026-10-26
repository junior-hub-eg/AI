"""The grammar coach on the Nahw Coach engine, behind the same /v1/teaching/grammar/* contract the backend calls.

    ocr       Gemini (GEMINI_API_KEY), else Groq vision, else the base teaching AI
    parse     each sentence: the verified bank, else Groq analysis checked against the role catalog, else the rule analyzer
    lesson    the topic's colored points and two solved examples from the bank, and a practice sentence written by Groq
              and verified by a second, independent analysis (else a bank sentence of the level)
    feedback  for each mistake: a message that names the mistake without giving the answer (US-07), the reason, and the
              guided questions with their answers (US-08); then a similar sentence
    quick-check (grammar topics) five "what is the إعراب of …" questions from the verified bank (US-09)

Video links, other quick checks and "ask the coach" stay on the base teaching AI. Without GROQ_API_KEY everything runs
offline on the bank and the rules, so the coach never stops answering.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
import re
import time

from teaching import prompts
from teaching.nahw.arabic import normalize, split_sentences, tokenize
from teaching.nahw.base import AIError, AIProvider
from teaching.nahw.catalog import ROLE_FAMILIES, ROLES, UNKNOWN_ROLE
from teaching.nahw.gemini_ocr import GeminiOCR
from teaching.nahw.grammar import (
    full_irab,
    loose_words,
    mistake_message,
    reason_for,
    rule_analyze,
    validate_words,
)
from teaching.nahw.groq_provider import GroqProvider
from teaching.nahw.guidance import build_steps
from teaching.nahw.mock_provider import MockProvider
from teaching.nahw.seed_data import TOPICS
from teaching.schemas import (
    AskRequest,
    AskResponse,
    FeedbackItem,
    FeedbackRequest,
    FeedbackResponse,
    GuidingQuestion,
    LessonPoint,
    LessonRequest,
    LessonResponse,
    Meta,
    OcrRequest,
    OcrResponse,
    ParsedSentence,
    ParsedWord,
    ParseRequest,
    ParseResponse,
    Question,
    QuickCheckRequest,
    QuickCheckResponse,
    VideoLinksRequest,
    VideoLinksResponse,
)

logger = logging.getLogger("teaching.nahw")

ENGINE = "nahw-coach"
CASE_COLOR = {"مرفوع": "blue", "منصوب": "green", "مجرور": "orange", "مجزوم": "purple"}
MAX_LEVEL = 3


def _topic(title: str) -> dict | None:
    key = normalize(title)
    return next((t for t in TOPICS if normalize(t["title"]) == key), None) or next(
        (t for t in TOPICS if normalize(t["title"]) in key or key in normalize(t["title"])), None
    )


def _bank() -> dict[str, list[dict]]:
    return {normalize(s["text"]): s["words"] for t in TOPICS for s in t["sentences"]}


BANK = _bank()


def _level(difficulty: int) -> int:
    return 1 if difficulty <= 2 else 2 if difficulty == 3 else MAX_LEVEL


def _color(word: dict) -> str:
    return "gray" if word.get("sign") == "مبني" else CASE_COLOR.get(word.get("case") or "", "gray")


CASE_SIGN = {"مرفوع": "الضمة", "منصوب": "الفتحة", "مجرور": "الكسرة"}
SHORT_SIGNS = {"الضمة", "الفتحة", "الكسرة"}
PUNCT = ".,،؛;:!?؟\"'«»()[]{}-–—…"


def consistent(word: ParsedWord) -> ParsedWord:
    """The general parser's answer checked against the role catalog: a role that has one case always gets it (اسم إنّ is
    منصوب, مضاف إليه مجرور …) with the matching color and short sign, and punctuation leaves the word."""
    text = word.word.strip(PUNCT) or word.word
    main = word.role.split("،")[-1].strip()
    role = max((r for r in ROLES if main.endswith(r)), key=len, default=None)
    case, sign, color = word.case, word.sign, word.color
    fixed = ROLES[role]["case"] if role else None
    if fixed and case != fixed:
        case = fixed
        if sign in SHORT_SIGNS:
            sign = CASE_SIGN[fixed]
    if case in CASE_COLOR:
        color = CASE_COLOR[case]
    elif case == "مبني" or (sign or "").startswith("مبني"):
        color = "gray"
    return word.model_copy(update={"word": text, "case": case, "sign": sign, "color": color})


PREFIX_SIGN = {"و": "مبني على الفتح", "ف": "مبني على الفتح", "ك": "مبني على الفتح", "ب": "مبني على الكسر", "ل": "مبني على الكسر"}
GRAMMAR_WORDS = {"حرف", "فعل", "اسم", "ضمير", "مبتدأ", "خبر", "فاعل", "مفعول", "نائب", "مضاف", "نعت", "صفة", "توكيد", "بدل"}


def split_attached(word: ParsedWord) -> list[ParsedWord]:
    """A word with a letter attached in front (وَ، فَ، بِ، لِ، كَ) whose إعراب has two parts («الباء حرف جر، ناشئة اسم مجرور»)
    becomes two words: the letter with its own إعراب, then the rest of the word with the rest of the إعراب."""
    parts = [p.strip() for p in re.split(r"[،,+]", word.role) if p.strip()]
    letter = word.word[:1]
    if len(parts) < 2 or letter not in PREFIX_SIGN or "حرف" not in parts[0] or len(word.word) < 3:
        return [word]
    rest_role = "، ".join(parts[1:])
    tokens = rest_role.split()
    if len(tokens) >= 3 and tokens[0] not in GRAMMAR_WORDS:  # «العلمِ اسم مجرور» → «اسم مجرور»
        rest_role = " ".join(tokens[1:])
    prefix = ParsedWord(word=letter + "ـ", role=parts[0][:60], case="مبني", sign=PREFIX_SIGN[letter],
                        explanation="حرف ملزوق في أول الكلمة، وله إعرابه لوحده.", color="gray")
    return [prefix, consistent(word.model_copy(update={"word": word.word[1:], "role": rest_role[:60]}))]


def _outside_catalog(w: dict) -> str:
    """The إعراب of a role the catalog doesn't teach (حال، ظرف، معطوف …), as the AI gave it."""
    if w.get("note"):
        return w["note"]
    if w.get("sign") == "مبني":
        return f"{w['role']} مبني"
    case = "" if (w.get("case") or "") in w["role"] else w.get("case") or ""  # «حال منصوب» not «حال منصوب منصوب»
    return " ".join(x for x in (w["role"], case, f"وعلامته {w['sign']}" if w.get("sign") else "") if x)


def to_parsed(text: str, words: list[dict]) -> ParsedSentence:
    """A Nahw sentence in the backend's shape: role, case, sign, the reason and the color of its case."""
    out = []
    for i, w in enumerate(words):
        known = w.get("role") in ROLES
        if known and ROLES[w["role"]]["type"] == "حرف":  # particles are always مبني, whatever sign the model gave
            w = {**w, "sign": "مبني", "case": None}
        out.append(
            ParsedWord(
                word=w["text"][:40],
                role=(w.get("role") or UNKNOWN_ROLE)[:60],
                case=("مبني" if w.get("sign") == "مبني" else (w.get("case") or ""))[:40],
                sign=(w.get("sign") or "")[:60],
                explanation=(reason_for(words, i) if known else full_irab(w) if w.get("role") in (None, UNKNOWN_ROLE)
                             else _outside_catalog(w))[:300],
                color=_color(w) if known or w.get("role") != UNKNOWN_ROLE else "gray",
            )
        )
    return ParsedSentence(text=text[:400], words=out)


PIECE_WORDS = 30  # words per call to the parser
PARSE_CONCURRENCY = 3
PARSE_BUDGET_SECONDS = 32  # the API answers within 40 s
NAHW_RESERVE_SECONDS = 8  # left for Nahw Coach when the general parser fails


def passage_pieces(text: str) -> list[str]:
    """A photographed page in pieces of whole sentences of up to PIECE_WORDS words. The page's own line breaks join back
    into sentences (a blank line stays a paragraph); a longer sentence is cut at its commas, else every PIECE_WORDS words."""
    text = re.sub(r"[ \t]*\n(?![ \t]*\n)[ \t]*", " ", (text or "").replace("\r", ""))
    parts: list[str] = []
    for sentence in split_sentences(text):
        if len(tokenize(sentence)) <= PIECE_WORDS:
            parts.append(sentence)
            continue
        for clause in re.split(r"(?<=[،,])\s+", sentence):
            words = clause.split()
            parts += [" ".join(words[i : i + PIECE_WORDS]) for i in range(0, len(words), PIECE_WORDS)]
    pieces: list[str] = []
    for part in parts:
        if pieces and len(tokenize(pieces[-1])) + len(tokenize(part)) <= PIECE_WORDS:
            pieces[-1] += " " + part
        else:
            pieces.append(part)
    return pieces


class NahwTeachingAi:
    """Grammar on Nahw Coach; everything else on `base` (the LLM teaching AI or the fake one)."""

    def __init__(self, base, provider: AIProvider, ocr_engine=None) -> None:
        self.base, self.provider, self.ocr_engine = base, provider, ocr_engine

    @classmethod
    def from_env(cls, base) -> NahwTeachingAi:
        groq_key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("TEACHING_NAHW_MODEL", "openai/gpt-oss-120b")
        fast = os.getenv("TEACHING_NAHW_FAST_MODEL", "openai/gpt-oss-20b")
        vision = os.getenv("TEACHING_NAHW_VISION_MODEL", "qwen/qwen3.8-27b")
        provider: AIProvider = (
            GroqProvider(groq_key, model, fast, vision, timeout=35, max_retries=1)
            if groq_key
            else MockProvider(reason="GROQ_API_KEY is not set")
        )
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        ocr_engine = (
            GeminiOCR(
                gemini_key,
                os.getenv("TEACHING_NAHW_OCR_MODEL", "gemini-3.8-flash"),
                timeout=35,
                max_retries=1,
            )
            if gemini_key
            else None
        )
        return cls(base, provider, ocr_engine)

    @staticmethod
    def _meta(started: float, model: str = ENGINE) -> Meta:
        return Meta(
            prompt_version=prompts.PROMPT_VERSION,
            model_id=model,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    # ----- not grammar: the base AI ------------------------------------------------------------------------------
    async def video_links(self, body: VideoLinksRequest) -> VideoLinksResponse:
        return await self.base.video_links(body)

    async def ask(self, body: AskRequest) -> AskResponse:
        return await self.base.ask(body)

    # ----- analysis ----------------------------------------------------------------------------------------------
    async def _analyze(self, sentence: str, loose: bool = False) -> list[dict]:
        """`loose` (a passage from a book): the AI's word answers are kept one by one, so one role outside the catalog
        doesn't turn the whole sentence into «غير محدد»."""
        tokens = tokenize(sentence)
        key = normalize(" ".join(tokens))
        if key in BANK and len(BANK[key]) == len(tokens):
            return [dict(w, text=t) for w, t in zip(BANK[key], tokens)]
        try:
            raw = await asyncio.to_thread(self.provider.analyze_sentence, sentence, tokens)
            words = validate_words(tokens, raw) if raw is not None else None
            if not words and loose and raw is not None:
                words = loose_words(tokens, raw, rule_analyze(sentence, BANK))
            if words:
                return words
        except AIError as exc:
            logger.warning("nahw analysis failed: %s", exc)
        return rule_analyze(sentence, BANK)

    async def parse(self, body: ParseRequest) -> ParseResponse:
        """A passage from a book, in short pieces of whole sentences (two or three at a time, so a long page fits the
        reply time): a piece from the verified bank as it is; otherwise the general parser, which handles attached
        letters (بـ، لـ، فـ…) and every role, with Nahw Coach as the fallback."""
        started = time.perf_counter()
        deadline = started + PARSE_BUDGET_SECONDS
        gate = asyncio.Semaphore(PARSE_CONCURRENCY)
        pieces = passage_pieces(body.text) or [body.text]
        parsed = await asyncio.gather(*(self._parse_piece(piece, gate, deadline) for piece in pieces))
        return ParseResponse(sentences=[s for piece in parsed for s in piece][:30], meta=self._meta(started))

    async def _parse_piece(self, text: str, gate: asyncio.Semaphore, deadline: float) -> list[ParsedSentence]:
        sentences = split_sentences(text) or [text]
        async with gate:
            if not all(normalize(" ".join(tokenize(s))) in BANK for s in sentences):
                try:
                    left = deadline - time.perf_counter() - NAHW_RESERVE_SECONDS
                    result = await asyncio.wait_for(self.base.parse(ParseRequest(text=text)), timeout=max(left, 1))
                    return [
                        ParsedSentence(text=x.text, words=[part for w in x.words for part in split_attached(consistent(w))][:40])
                        for x in result.sentences
                    ]
                except Exception as exc:  # noqa: BLE001 - any failure of the general parser falls back to Nahw Coach
                    logger.warning("general parse failed, using Nahw Coach: %s", type(exc).__name__)
            out = []
            for sentence in sentences:
                try:
                    left = max(deadline - time.perf_counter(), 0.5)
                    words = await asyncio.wait_for(self._analyze(sentence, loose=True), timeout=left)
                except TimeoutError:
                    words = rule_analyze(sentence, BANK)
                if words:
                    out.append(to_parsed(" ".join(w["text"] for w in words), words))
            return out

    async def ocr(self, body: OcrRequest) -> OcrResponse:
        started = time.perf_counter()
        image = base64.b64decode(body.image_base64)
        for engine in (self.ocr_engine, self.provider if self.provider.supports_ocr else None):
            if engine is None:
                continue
            try:
                result = await asyncio.to_thread(engine.ocr, image, body.mime_type)
                return OcrResponse(
                    text=result["text"], meta=self._meta(started, getattr(engine, "name", ENGINE))
                )
            except AIError as exc:
                logger.warning("nahw OCR failed on %s: %s", getattr(engine, "name", "?"), exc)
        return await self.base.ocr(body)

    # ----- lesson and practice -----------------------------------------------------------------------------------
    async def _practice(self, topic: dict, level: int, avoid: list[str]) -> tuple[str, list[dict]]:
        """A new sentence from Groq that a second analysis agrees with, word by word; else one from the bank."""
        if self.provider.supports_generation:
            for _ in range(2):
                try:
                    data = await asyncio.to_thread(
                        self.provider.generate_sentence, topic["title"], topic["focus_roles"], level, avoid
                    )
                    if not data or not data.get("text"):
                        continue
                    tokens = tokenize(data["text"])
                    words = validate_words(tokens, data.get("words"))
                    if not words or not any(w["role"] in topic["focus_roles"] for w in words):
                        continue
                    if hasattr(self.provider, "verify") and not await asyncio.to_thread(
                        self.provider.verify, " ".join(tokens), tokens, words
                    ):
                        continue
                    return " ".join(tokens), words
                except AIError as exc:
                    logger.warning("nahw generation failed: %s", exc)
                    break
        practice = [s for s in topic["sentences"] if s["kind"] == "practice"]
        pool = (
            [
                s
                for s in practice
                if s["level"] == level and normalize(s["text"]) not in {normalize(a) for a in avoid}
            ]
            or [s for s in practice if s["level"] == level]
            or practice
        )
        chosen = random.choice(pool)
        return chosen["text"], chosen["words"]

    async def lesson(self, body: LessonRequest) -> LessonResponse:
        topic = _topic(body.topic_title)
        if topic is None:  # a topic the admin added that Nahw has no content for
            return await self.base.lesson(body)
        started = time.perf_counter()
        points = [
            LessonPoint(
                title=(p["role"] or "القاعدة")[:80],
                text=p["text"][:400],
                color=_color(
                    {"case": ROLES[p["role"]]["case"], "sign": "" if ROLES[p["role"]]["case"] else "مبني"}
                )
                if p["role"] in ROLES
                else "teal",
            )
            for p in topic["points"][:4]
        ]
        examples = [s for s in topic["sentences"] if s["kind"] == "example"][:2]
        text, words = await self._practice(topic, _level(body.difficulty), [s["text"] for s in examples])
        return LessonResponse(
            points=points,
            examples=[to_parsed(s["text"], s["words"]) for s in examples],
            practice=to_parsed(text, words),
            meta=self._meta(started),
        )

    async def feedback(self, body: FeedbackRequest) -> FeedbackResponse:
        started = time.perf_counter()
        words = await self._analyze(body.sentence)
        items = []
        for m in body.mistakes:
            i = next((k for k, w in enumerate(words) if normalize(w["text"]) == normalize(m.word)), None)
            if i is None or words[i].get("role") not in ROLES:
                items.append(
                    FeedbackItem(
                        word=m.word,
                        what=f"«{m.word}» مش {m.given or 'كده'}.",
                        why="راجع موقعها في الجملة.",
                        guiding_questions=[
                            GuidingQuestion(
                                question=f"إيه اللي قبل «{m.word}» في الجملة؟", answer=m.expected[:200]
                            )
                        ],
                    )
                )
                continue
            given = m.given if m.given in ROLES else None
            answer = {
                "type": ROLES[given]["type"] if given else words[i]["type"],
                "role": m.given,
                "sign": words[i]["sign"],
            }
            default = mistake_message(words, i, answer)
            try:
                what = await asyncio.to_thread(
                    self.provider.rephrase_mistake, body.sentence, words[i], answer, default
                )
            except AIError:
                what = default
            steps = build_steps(words, i)
            items.append(
                FeedbackItem(
                    word=m.word,
                    what=what[:300],
                    why=reason_for(words, i)[:300],
                    guiding_questions=[
                        GuidingQuestion(question=s["question"][:200], answer=s["answer"][:200])
                        for s in steps[:6]
                    ],
                )
            )
        topic = _topic(body.topic_title)
        if topic is not None:
            level = max(
                (s["level"] for s in topic["sentences"] if normalize(s["text"]) == normalize(body.sentence)),
                default=1,
            )
            text, similar = await self._practice(topic, level, [body.sentence])
        else:
            text, similar = body.sentence, words
        return FeedbackResponse(
            items=items, similar_sentence=to_parsed(text, similar), meta=self._meta(started)
        )

    # ----- Quick Check -------------------------------------------------------------------------------------------
    async def quick_check(self, body: QuickCheckRequest) -> QuickCheckResponse:
        title = body.title.removeprefix("Quick Check:").strip()
        topic = _topic(title)
        if topic is None:
            return await self.base.quick_check(body)
        started = time.perf_counter()
        rng = random.Random()
        candidates = [
            (s, i)
            for s in topic["sentences"]
            for i, w in enumerate(s["words"])
            if w["role"] in topic["focus_roles"]
        ]
        rng.shuffle(candidates)
        seen, questions = set(), []
        for s, i in candidates:
            w = s["words"][i]
            if (w["role"], s["text"]) in seen:
                continue
            seen.add((w["role"], s["text"]))
            label = full_irab({**w, "note": None})
            pool = (
                [r for fam in ROLE_FAMILIES if w["role"] in fam for r in fam]
                + list(topic["focus_roles"])
                + list(ROLES)
            )
            wrong = [
                full_irab(
                    {
                        "text": "",
                        "role": r,
                        "type": ROLES[r]["type"],
                        "sign": "مبني"
                        if ROLES[r]["case"] is None and ROLES[r]["type"] != "اسم"
                        else w["sign"],
                        "case": ROLES[r]["case"] or w.get("case"),
                    }
                )
                for r in dict.fromkeys(pool)
                if r != w["role"]
            ]
            wrong = [x for x in dict.fromkeys(wrong) if x != label][:3]
            options = wrong + [label]
            rng.shuffle(options)
            questions.append(
                Question(
                    question=f"ما إعراب «{w['text']}» في: «{s['text']}»؟"[:400],
                    options=[o[:200] for o in options],
                    answer_index=options.index(label),
                    explanation=reason_for(s["words"], i)[:600],
                )
            )
            if len(questions) == body.count:
                break
        if not questions:
            return await self.base.quick_check(body)
        return QuickCheckResponse(questions=questions, meta=self._meta(started))
