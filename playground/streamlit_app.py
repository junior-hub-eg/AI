"""Discovery AI Playground (Streamlit).

Talk to the interview with your voice, try every endpoint and run contract checks,
against the real service (port 8000) or the mock (port 8001).

    streamlit run playground/streamlit_app.py
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import streamlit as st

from playground.api import ApiResult, DiscoveryApi
from playground.checks import RESULTS, TURNS, build_checks, run_checks
from playground.payloads import (
    audio_answer,
    result_payload,
    sample_history,
    text_answer,
    turn_payload,
)
from playground.sample_data import TRACKS

MIN_RESPONSES_TO_FINISH = 5
MIME_BY_EXTENSION = {
    "wav": "audio/wav",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "m4a": "audio/mp4",
}

st.set_page_config(page_title="Discovery AI Playground", page_icon="🎙️", layout="wide")


# ------------------------------------------------------------------ state
@dataclass
class Interview:
    id: str = field(default_factory=lambda: f"pg_{uuid.uuid4().hex[:10]}")
    history: list[dict[str, Any]] = field(default_factory=list)
    question: dict[str, Any] | None = None
    finished: bool = False
    result: dict[str, Any] | None = None
    error: ApiResult | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    input_n: int = 0
    play_audio: bool = True


@dataclass(frozen=True)
class Config:
    api: DiscoveryApi
    grade: int
    max_questions: int
    speak: bool
    tracks: list[dict[str, str]]
    auth_enabled: bool


# ---------------------------------------------------------------- helpers
def redact(value: Any) -> Any:
    """Replace long base64 audio strings so JSON stays readable."""
    if isinstance(value, dict):
        return {
            k: (f"<{len(v)} base64 chars>" if k == "audio_base64" and isinstance(v, str) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def show_error(result: ApiResult) -> None:
    if result.error:
        st.error(result.error)
        return
    st.error(f"HTTP {result.status}")
    st.json(redact(result.body))
    code = (result.body or {}).get("error", {}).get("code") if isinstance(result.body, dict) else None
    if code == "AUDIO_UNINTELLIGIBLE":
        st.info("Nothing could be understood. The product should offer 'type your answer instead'.")


def play(audio_b64: str | None, mime: str | None, *, autoplay: bool = False) -> None:
    if audio_b64:
        st.audio(base64.b64decode(audio_b64), format=mime or "audio/wav", autoplay=autoplay)
    else:
        st.caption(
            "No audio returned (text only). If speech was requested, the TTS call failed: look for "
            "'tts_failed' in the service terminal, or run: python scripts/check_groq.py"
        )


def audio_input_widget(prefix: str, mode: str, n: int) -> tuple[bytes, str] | None:
    """Return (audio_bytes, mime_type) from the microphone or an uploaded file."""
    if mode.startswith("🎙️"):
        clip = st.audio_input("Record your answer (max 2 minutes)", key=f"{prefix}_mic_{n}")
        return (clip.getvalue(), clip.type or "audio/wav") if clip else None
    upload = st.file_uploader("Audio file", type=list(MIME_BY_EXTENSION), key=f"{prefix}_file_{n}")
    if upload is None:
        return None
    return upload.getvalue(), MIME_BY_EXTENSION[upload.name.rsplit(".", 1)[-1].lower()]


# ---------------------------------------------------------------- sidebar
def sidebar() -> Config:
    st.session_state.setdefault("base_url", os.getenv("DISCOVERY_URL", "http://127.0.0.1:8000"))
    st.sidebar.title("🎙️ Playground")
    st.sidebar.text_input("Service URL", key="base_url")
    left, right = st.sidebar.columns(2)
    left.button(
        "Real :8000",
        width="stretch",
        on_click=st.session_state.update,
        kwargs={"base_url": "http://127.0.0.1:8000"},
    )
    right.button(
        "Mock :8001",
        width="stretch",
        on_click=st.session_state.update,
        kwargs={"base_url": "http://127.0.0.1:8001"},
    )
    token = st.sidebar.text_input(
        "JWT (empty when AUTH_DISABLED=true)", type="password", value=os.getenv("TOKEN", "")
    )
    api = DiscoveryApi(st.session_state.base_url, token)

    if st.sidebar.button("Check health", width="stretch"):
        health = api.get("/healthz")
        if health.ok:
            st.sidebar.success(f"Service is up ({health.seconds * 1000:.0f} ms)")
        else:
            st.sidebar.error(health.error or f"HTTP {health.status}")

    st.sidebar.divider()
    grade = st.sidebar.slider("Student grade", 5, 12, 8)
    max_questions = st.sidebar.slider("Max questions", 3, 20, 10)
    speak = st.sidebar.checkbox("Ask for spoken questions (TTS)", value=True)
    auth_enabled = st.sidebar.checkbox("Service has auth enabled", value=bool(token))

    with st.sidebar.expander("Tracks sent to the service (JSON)"):
        st.session_state.setdefault("tracks_json", json.dumps(TRACKS, indent=2))
        st.text_area("tracks", key="tracks_json", height=300, label_visibility="collapsed")
    try:
        tracks = json.loads(st.session_state.tracks_json)
    except json.JSONDecodeError as exc:
        st.sidebar.error(f"Tracks JSON is invalid: {exc}")
        st.stop()
    return Config(api, grade, max_questions, speak, tracks, auth_enabled)


# ----------------------------------------------------------- interview tab
def log_call(iv: Interview, endpoint: str, result: ApiResult) -> None:
    meta = result.body.get("meta", {}) if result.ok and isinstance(result.body, dict) else {}
    iv.calls.append(
        {
            "endpoint": endpoint,
            "status": result.status or "no connection",
            "round_trip_s": round(result.seconds, 2),
            "service_ms": meta.get("latency_ms"),
            "model": meta.get("model_id"),
            "request_id": result.request_id,
        }
    )


def send_turn(cfg: Config, iv: Interview, answer: dict[str, Any] | None) -> None:
    payload = turn_payload(
        interview_id=iv.id,
        tracks=cfg.tracks,
        grade=cfg.grade,
        history=iv.history,
        answer=answer,
        max_questions=cfg.max_questions,
        speak=cfg.speak,
    )
    result = cfg.api.post(TURNS, payload)
    log_call(iv, "turns", result)
    iv.error = None if result.ok else result
    if not result.ok:
        return
    body = result.body
    if body["answered"] and answer:
        iv.history.append(
            {
                "order_index": body["answered"]["order_index"],
                "question_text": answer["question_text"],
                "transcript": body["answered"]["transcript"],
            }
        )
    iv.question, iv.finished, iv.play_audio = body["next_question"], body["finished"], True
    if iv.finished:
        fetch_result(cfg, iv)


def fetch_result(cfg: Config, iv: Interview) -> None:
    payload = result_payload(interview_id=iv.id, tracks=cfg.tracks, grade=cfg.grade, responses=iv.history)
    result = cfg.api.post(RESULTS, payload)
    log_call(iv, "results", result)
    iv.error = None if result.ok else result
    if result.ok:
        iv.result, iv.finished, iv.question = result.body, True, None


def show_result(cfg: Config, result: dict[str, Any]) -> None:
    names = {t["code"]: t["name"] for t in cfg.tracks}
    st.subheader("🎯 Your top 3 tracks")
    for rec in result["recommendations"]:
        with st.container(border=True):
            st.markdown(
                f"**#{rec['rank']}  {names.get(rec['track_code'], rec['track_code'])}**"
                f"  ·  {rec['match_percent']}% match"
            )
            st.progress(rec["match_percent"] / 100)
            st.write(rec["reason"])
    st.info(result["summary"])
    st.caption(
        f"model: {result['meta']['model_id']} · prompt: {result['meta']['prompt_version']} "
        f"· {result['meta']['latency_ms']} ms"
    )


def interview_tab(cfg: Config) -> None:
    if st.button("▶ Start a new interview", type="primary"):
        iv = Interview()
        st.session_state.interview = iv
        send_turn(cfg, iv, None)
        st.rerun()

    iv: Interview | None = st.session_state.get("interview")
    if iv is None:
        st.info(
            "Press **Start a new interview**. The first question is fixed; the next ones are "
            "written by the LLM from your answers."
        )
        return

    for item in iv.history:
        with st.chat_message("assistant"):
            st.write(item["question_text"])
        with st.chat_message("user"):
            st.write(item["transcript"])

    if iv.question and not iv.finished:
        question = iv.question
        with st.chat_message("assistant"):
            st.write(f"**Q{question['order_index']}.** {question['question_text']}")
            play(question["audio_base64"], question["audio_mime_type"], autoplay=iv.play_audio)
        iv.play_audio = False
        answer_panel(cfg, iv, question)

    if iv.error:
        show_error(iv.error)
    if iv.finished and iv.result is None and iv.history and st.button("Retry the result call"):
        fetch_result(cfg, iv)
        st.rerun()
    if iv.result:
        show_result(cfg, iv.result)

    with st.expander(f"Call log ({len(iv.calls)})"):
        st.dataframe(iv.calls, width="stretch")


def answer_panel(cfg: Config, iv: Interview, question: dict[str, Any]) -> None:
    mode = st.radio(
        "Answer with", ["🎙️ Microphone", "📁 Audio file", "⌨️ Typing"], horizontal=True, key="answer_mode"
    )
    index, text = question["order_index"], question["question_text"]
    answer: dict[str, Any] | None = None

    if mode.startswith("⌨️"):
        typed = st.text_area("Your answer", key=f"typed_{iv.input_n}", max_chars=1000)
        if st.button("Send answer", disabled=not typed.strip(), type="primary"):
            answer = text_answer(index, text, typed.strip())
    else:
        audio = audio_input_widget("iv", mode, iv.input_n)
        if st.button("Send voice answer", disabled=audio is None, type="primary") and audio:
            answer = audio_answer(index, text, *audio)

    if answer:
        send_turn(cfg, iv, answer)
        if iv.error is None:
            iv.input_n += 1
        st.rerun()

    if len(iv.history) >= MIN_RESPONSES_TO_FINISH and st.button("⏭ Finish now and get my result"):
        fetch_result(cfg, iv)
        st.rerun()


# --------------------------------------------------------------- voice tab
def voice_tab(cfg: Config) -> None:
    st.caption("Test speech-to-text on its own: one recording in, transcript + next question out.")
    mode = st.radio("Source", ["🎙️ Microphone", "📁 Audio file"], horizontal=True, key="voice_mode")
    audio = audio_input_widget("vc", mode, 0)
    if st.button("Transcribe", disabled=audio is None, type="primary") and audio:
        payload = turn_payload(
            interview_id=f"pg_voice_{uuid.uuid4().hex[:6]}",
            tracks=cfg.tracks,
            grade=cfg.grade,
            history=[],
            answer=audio_answer(1, "What do you enjoy doing?", *audio),
            max_questions=cfg.max_questions,
            speak=cfg.speak,
        )
        result = cfg.api.post(TURNS, payload)
        if not result.ok:
            show_error(result)
            return
        body = result.body
        st.success(f"Transcript: **{body['answered']['transcript']}**")
        st.caption(f"round trip {result.seconds:.1f} s · service {body['meta']['latency_ms']} ms")
        if body["next_question"]:
            st.write(f"Next question: {body['next_question']['question_text']}")
            play(body["next_question"]["audio_base64"], body["next_question"]["audio_mime_type"])


# ------------------------------------------------------- endpoint tester
def samples(cfg: Config) -> dict[str, tuple[str, dict[str, Any]]]:
    def turn(**kw: Any) -> dict[str, Any]:
        return (
            turn_payload(
                interview_id="pg_sample",
                tracks=cfg.tracks,
                grade=cfg.grade,
                history=[],
                answer=None,
                max_questions=cfg.max_questions,
                speak=False,
            )
            | kw
        )

    return {
        "turns · first question": (TURNS, turn()),
        "turns · text answer": (
            TURNS,
            turn(answer=text_answer(1, "What do you enjoy?", "I like drawing and games.")),
        ),
        "turns · last answer (finished)": (
            TURNS,
            turn(
                history=sample_history(2),
                max_questions=3,
                answer=text_answer(3, "Q3?", "I would build a drawing game."),
            ),
        ),
        "results · 6 answers": (
            RESULTS,
            result_payload(
                interview_id="pg_sample", tracks=cfg.tracks, grade=cfg.grade, responses=sample_history(6)
            ),
        ),
    }


def load_sample(cfg: Config) -> None:
    path, payload = samples(cfg)[st.session_state.sample_choice]
    st.session_state.raw_path = path
    st.session_state.raw_body = json.dumps(payload, indent=2)


def attach_audio_to_body(audio: tuple[bytes, str]) -> None:
    body = json.loads(st.session_state.raw_body)
    answer = body.get("answer") or text_answer(1, "What do you enjoy doing?", "x")
    body["answer"] = audio_answer(answer["order_index"], answer["question_text"], *audio)
    st.session_state.raw_body = json.dumps(body, indent=2)


def endpoint_tab(cfg: Config) -> None:
    st.session_state.setdefault("raw_path", TURNS)
    st.session_state.setdefault("raw_body", json.dumps(samples(cfg)["turns · first question"][1], indent=2))
    top = st.columns([2, 1])
    top[0].selectbox("Load a sample request", list(samples(cfg)), key="sample_choice")
    top[1].button("Load sample", on_click=load_sample, args=(cfg,), width="stretch")

    st.radio(
        "Endpoint",
        ["GET /healthz", "GET /readyz", f"POST {TURNS}", f"POST {RESULTS}"],
        index=2,
        horizontal=True,
        key="raw_endpoint",
    )
    with st.expander("Insert an audio file into `answer` (tests speech-to-text)"):
        file = audio_input_widget("ep", "📁 Audio file", 0)
        if st.button("Insert into body", disabled=file is None) and file:
            attach_audio_to_body(file)
            st.rerun()
    st.text_area("Request body (JSON)", key="raw_body", height=320)

    if not st.button("Send request", type="primary"):
        return
    method, path = st.session_state.raw_endpoint.split(" ", 1)
    if method == "GET":
        result = cfg.api.get(path)
    else:
        try:
            result = cfg.api.post(path, json.loads(st.session_state.raw_body))
        except json.JSONDecodeError as exc:
            st.error(f"Body is not valid JSON: {exc}")
            return
    (st.success if result.ok else st.error)(
        result.error
        or f"HTTP {result.status} · {result.seconds * 1000:.0f} ms · request id {result.request_id}"
    )
    st.json(redact(result.body))
    question = result.body.get("next_question") if isinstance(result.body, dict) else None
    if question:
        play(question.get("audio_base64"), question.get("audio_mime_type"))


# ----------------------------------------------------------- checks tab
def checks_tab(cfg: Config) -> None:
    st.caption("Sends valid and invalid requests and compares the HTTP status with what the SRS expects.")
    if st.button("Run all checks", type="primary"):
        rows = run_checks(cfg.api, build_checks(cfg.tracks, cfg.grade, auth_enabled=cfg.auth_enabled))
        passed = sum(r["result"] == "PASS" for r in rows)
        (st.success if passed == len(rows) else st.warning)(f"{passed} / {len(rows)} checks passed")
        st.dataframe(rows, width="stretch", hide_index=True)
        if rows and rows[0]["got"] == 0:
            st.error("Could not connect. Start the service first (see the sidebar URL).")


# ------------------------------------------------------------------- main
def main() -> None:
    config = sidebar()
    st.title("Discovery AI Playground")
    interview, voice, endpoints, checks = st.tabs(
        ["🧭 Full interview", "🎙️ Voice check", "🔌 Endpoint tester", "✅ Automatic checks"]
    )
    with interview:
        interview_tab(config)
    with voice:
        voice_tab(config)
    with endpoints:
        endpoint_tab(config)
    with checks:
        checks_tab(config)


main()
