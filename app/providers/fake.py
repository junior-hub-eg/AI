"""Offline providers: no network, deterministic. For tests and UI work (FAKE_MODELS=true)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.providers.base import LlmResult, LlmTask, Message, SpeechAudio, T
from app.services.wav import silent_wav

# (shown on screen, read aloud)
_QUESTIONS = (
    (
        "رائع! ما المواد الدراسية التي تحبها أكثر، ولماذا؟",
        "رَائِع! مَا المَوَادُّ الدِّرَاسِيَّةُ الَّتِي تُحِبُّهَا أَكْثَر، وَلِمَاذَا؟",
    ),
    (
        "هل تحب أن تجعل الأشياء تبدو جميلة، أم تحب أن تفهم كيف تعمل؟",
        "هَلْ تُحِبُّ أَنْ تَجْعَلَ الأَشْيَاءَ تَبْدُو جَمِيلَة، أَمْ تُحِبُّ أَنْ تَفْهَمَ كَيْفَ تَعْمَل؟",
    ),
    ("احكِ لي عن مرة كان فيها شيء صعب، وماذا فعلت؟", "احْكِ لِي عَنْ مَرَّةٍ كَانَ فِيهَا شَيْءٌ صَعْب، وَمَاذَا فَعَلْت؟"),
    (
        "ما الـ Games أو الـ Apps التي تحبها، وما الممتع فيها؟",
        "مَا الجيمز أَوِ الآبس الَّتِي تُحِبُّهَا، وَمَا المُمْتِعُ فِيهَا؟",
    ),
    ("هل تحب العمل في فريق أم وحدك؟", "هَلْ تُحِبُّ العَمَلَ فِي فَرِيقٍ أَمْ وَحْدَك؟"),
    ("ما الشيء الذي تتساءل كيف يعمل؟", "مَا الشَّيْءُ الَّذِي تَتَسَاءَلُ كَيْفَ يَعْمَل؟"),
    ("لو تستطيع أن تصنع أي شيء بالـ Coding، ماذا ستصنع؟", "لَوْ تَسْتَطِيعُ أَنْ تَصْنَعَ أَيَّ شَيْءٍ بِالكودينج، مَاذَا سَتَصْنَع؟"),
)


class FakeLlm:
    model_id = "fake-llm"

    async def generate_json(
        self,
        *,
        task: LlmTask,
        messages: list[Message],
        parse: Callable[[dict[str, Any]], T],
        context: Mapping[str, Any] | None = None,
    ) -> LlmResult[T]:
        if task is LlmTask.TURN:
            answers = messages[-1]["content"].count("<student_answer>")
            text, speech = _QUESTIONS[answers % len(_QUESTIONS)]
            data: dict[str, Any] = {"question_text": text, "speech_text": speech}
        else:
            codes = list((context or {}).get("track_codes", []))[:3]
            data = {
                "recommendations": [
                    {
                        "track_code": code,
                        "match_percent": pct,
                        "reason": f"أظهرت اهتمامًا حقيقيًا يناسب {code.title()}.",
                    }
                    for code, pct in zip(codes, (86, 74, 61), strict=False)
                ],
                "summary": (
                    "شكرًا لك على هذه الدردشة الجميلة! "
                    "أنت تحب الإبداع وحل المشكلات، وهذه الـ Tracks تناسب ما قلته لنا. استمتع باستكشافها!"
                ),
                "summary_speech": (
                    "شُكْرًا لَكَ عَلَى هَذِهِ الدَّرْدَشَةِ الجَمِيلَة! "
                    "أَنْتَ تُحِبُّ الإِبْدَاعَ وَحَلَّ المُشْكِلَات، وَهَذِهِ التراكس تُنَاسِبُ مَا قُلْتَهُ لَنَا. اسْتَمْتِعْ بِاسْتِكْشَافِهَا!"
                ),
            }
        return LlmResult(parse(data), self.model_id)


class FakeStt:
    """Audio starting with b'TEXT:' is returned as that text; anything else is canned."""

    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        if audio.startswith(b"TEXT:"):
            return audio[5:].decode("utf-8", errors="ignore")
        return "بحب أعمل Games صغيرة وأصلح الكمبيوتر."


class FakeTts:
    async def speak(self, text: str) -> SpeechAudio:
        return SpeechAudio(silent_wav(), "audio/wav")
