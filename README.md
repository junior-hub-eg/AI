# Junior Hub - Discovery AI service

Stateless service behind the **Track Discovery interview**. The backend (.NET) owns the
interview, the data and the fallback. This service only does the AI work:

| Endpoint | Does | Models (Groq) |
|---|---|---|
| `POST /v1/discovery/turns` | answer (audio or text) in -> transcript + next spoken question out | Whisper (STT), gpt-oss-20b (question), Orpheus (TTS) |
| `POST /v1/discovery/results` | whole interview in -> exactly 3 ranked tracks with match % | gpt-oss-120b |
| `GET /healthz`, `/readyz` | probes (never call Groq) | - |

## Run it in 3 steps

1. **Put your Groq key in `.env`** (replace `PASTE_YOUR_GROQ_KEY_HERE`; key from https://console.groq.com/keys).
2. Start:
   - Linux/macOS: `./scripts/run_dev.sh`
   - Windows: `scripts\run_dev.bat`
3. **Check that every Groq model works:** `python scripts/check_groq.py` (tells you exactly what to fix, e.g. Orpheus terms).
4. Try a full interview: `python scripts/smoke_test.py` (add `--audio file.webm --mime audio/webm` to test voice).

The service auto-reloads when you edit `app/` or `prompts/`. **After editing `.env`, stop it (Ctrl+C) and start it again.**

Docs UI: http://127.0.0.1:8000/docs (disabled when `APP_ENV=production`).
No key yet? `FAKE_MODELS=true` runs everything with fake answers.

## Playground (Streamlit): try everything from a browser

Two terminals:

```bash
# 1) the service
./scripts/run_dev.sh              # Windows: scripts\run_dev.bat
# 2) the playground
./scripts/run_playground.sh       # Windows: scripts\run_playground.bat   (opens http://localhost:8501)
```

If Streamlit asks for an email on first start, just press Enter. Use Chrome or Edge on `localhost`
(microphone access needs `localhost` or HTTPS; allow the mic when the browser asks).

| Tab | What you can do |
|---|---|
| **Full interview** | Answer by microphone, audio file or typing. You hear each question, see the transcript, press "Finish now" after 5 answers, get the top-3 result. Call log shows status, round-trip time, service time and model per call. |
| **Voice check** | One recording in -> transcript + next spoken question. Best place to judge Whisper on real voices. |
| **Endpoint tester** | Send raw JSON to `/healthz`, `/readyz`, `/turns`, `/results`. Sample requests, edit the body, attach an audio file, see status/latency/request-id and play returned audio. |
| **Automatic checks** | One click: 12 good/bad requests (415, 413, 400 cases, ...) and PASS/FAIL against the SRS status codes (+ the 401 check when auth is on). |

Sidebar: service URL (buttons for real `:8000` and mock `:8001`), JWT, grade, max questions, speech on/off,
editable tracks JSON. With auth on: `TOKEN=$(python scripts/make_dev_token.py) ./scripts/run_playground.sh`.

## Arabic voice-call interview (v2)

**One switch for the language:** `INTERVIEW_LANGUAGE=ar` (default) or `INTERVIEW_LANGUAGE=en` in `.env`.
It picks the prompts (v2 / v1), the speech-to-text language, the Orpheus voice model and voice
(`lulwa` / `autumn`), the opening question and the call page language (RTL Arabic / LTR English).
Any of `PROMPT_*_VERSION`, `STT_LANGUAGE`, `STT_PROMPT`, `TTS_MODEL`, `TTS_VOICE`, `OPENING_QUESTION`
set explicitly in `.env` still overrides the language preset.

The interview now runs **in Arabic** (simple MSA) while programming terms stay in **English**
(Frontend, Data, Game...). Prompts `@v2` are the default; `@v1` (English) is unchanged
(`PROMPT_TURN_VERSION=v1`, `PROMPT_RESULT_VERSION=v1`, `STT_LANGUAGE=en`, `TTS_MODEL=canopylabs/orpheus-v1-english`).

- **Display vs speech text:** each question has `question_text` (shown, English terms in Latin letters)
  and `speech_text` (read aloud, 100% Arabic script, e.g. `فرونت إند`) so the Arabic voice pronounces terms correctly.
- **STT:** `STT_PROVIDER=groq` (Whisper `whisper-large-v3`, `STT_LANGUAGE=ar`, with a hint prompt) or
  `STT_PROVIDER=elevenlabs` (Scribe v2 + `STT_KEYTERMS`; much better on Egyptian Arabic mixed with English).
  With ElevenLabs, Groq Whisper is used automatically if it fails.
- **TTS:** `TTS_PROVIDER=groq` (Orpheus `canopylabs/orpheus-arabic-saudi`, voices fahad/sultan/abdullah/noura/lulwa/aisha;
  accept the model terms once in the Groq console) or `TTS_PROVIDER=elevenlabs` (`ELEVENLABS_VOICE_ID`).
  Orpheus is the fallback. Question 1 audio is generated at startup; network blips are retried once.
- **Results:** reasons/summary in Arabic, track names in English. `POST /v1/discovery/results` accepts
  `"speak": true` and then also returns `summary_audio_base64` / `summary_audio_mime_type`.
- **Privacy checks** also catch Arabic personal-data questions (اسمك، ساكن فين، عمرك...); Arabic Whisper
  hallucinations on silence are dropped.

### Call page (`/call/`, development only)

`http://127.0.0.1:<port>/call/` is a hands-free call: the AI speaks, captions are shown, recording starts
automatically and is sent after ~2.6 s of silence (voice-activity detection with noise calibration and
hysteresis), 7 questions, then the top-3 tracks with the summary read aloud. A **debug panel** on the left shows
every transcript, question, request/latency/model, TTS/STT status and the live server logs (`GET /debug/logs`,
metadata only, disabled in production).

### Windows quick start

`START_HERE.bat` creates a dedicated `.venv` (Python 3.12 via `uv` if needed), installs packages and starts the
API on port 8010 plus the Streamlit playground, then opens the call page. `SET_GROQ_KEY.bat` and
`SET_ELEVENLABS_KEY.bat` write the keys into `.env` (never committed).

## Folder map

```
app/
  main.py            app factory (uvicorn app.main:create_app --factory)
  container.py       builds everything once (composition root)
  core/              config, errors, JWT auth, logging, middleware
  api/               HTTP layer only (routes + dependencies)
  schemas/           request/response contracts (Pydantic)
  services/          interview logic: turn_service, result_service, prompt builder,
                     question policy (PII + length checks), audio validation, text helpers
  providers/
    base.py          interfaces (LLM / STT / TTS)
    groq/            the ONLY code that talks to Groq: client, llm (repair + fallback), speech
    fake.py          offline providers for tests
prompts/             versioned prompts: discovery_turn@v1.md, discovery_result@v1.md
content/             DRAFT fixed fallback questions + static fallback result (for the backend)
mock/                mock server with fixed answers + failure scenarios (for the backend team)
scripts/             smoke_test, dev keys/tokens, openapi export, run_dev
contracts/           openapi.json (regenerate: python -m scripts.export_openapi)
playground/          Streamlit test app: voice interview, endpoint tester, automatic checks
tests/               94 tests (no network, no key needed)
```

## Where to change things

| I want to... | Edit |
|---|---|
| set the Groq key | `.env` -> `GROQ_API_KEY` |
| change a model | `.env` -> `LLM_*_MODEL`, `STT_MODEL`, `TTS_MODEL`, `TTS_VOICE` |
| change how questions/results are written | `prompts/*.md` - **add a new file `@v2` and set `PROMPT_*_VERSION=v2`**, do not edit a version that was already tested |
| change the opening question | `.env` -> `OPENING_QUESTION` (never calls the LLM; its audio is cached) |
| change the interview topics order | `app/services/question_policy.py` -> `FOCUS_PLAN` |
| use another provider | implement `LlmProvider/SttProvider/TtsProvider` in `app/providers/`, wire it in `app/container.py` |

## Authentication

Backend -> service calls carry `Authorization: Bearer <JWT>` (RS256, audience `discovery-ai`,
5 min expiry). This service only needs the backend's **public** key (`JWT_PUBLIC_KEY_FILE` or `JWT_PUBLIC_KEY`).
Locally `.env` has `AUTH_DISABLED=true`; the service **refuses to start** with that in production.

To test real auth locally: `python scripts/gen_dev_keys.py`, set `AUTH_DISABLED=false` and
`JWT_PUBLIC_KEY_FILE=.keys/jwt_public.pem`, then
`curl -H "Authorization: Bearer $(python scripts/make_dev_token.py)" ...`.

## Errors

JSON body: `{"error": {"code", "message", "request_id"}}`.
`UNAUTHENTICATED` 401 - `INVALID_REQUEST` 400 - `AUDIO_UNSUPPORTED` 415 - `AUDIO_TOO_LARGE` 413 -
`PROVIDER_UNAVAILABLE` 503 - `TIMEOUT` 504 - **`AUDIO_UNINTELLIGIBLE` 422 (addition, see below)**.

## Decisions that go beyond the SRS (please confirm with the team)

1. **`AUDIO_UNINTELLIGIBLE` (422)** when speech recognition returns nothing usable (silence, noise,
   Whisper "thank you" hallucinations). The backend should treat it like any failed turn
   (`retryAsText: true`). It is not in the SRS error table.
2. **Question 1 is a fixed opener** (no LLM call, audio cached). Faster, free of quota use, deterministic.
3. **When all models fail the service returns 503**; the backend owns the fixed-question fallback
   (`content/fallback_*.json` are drafts for it).
4. `results` accepts **5 to 20** responses (`RESULT_MIN/MAX_RESPONSES`); the SRS text says 5 to 10.
5. Every question is checked (<= 45 words, no personal-data requests); a bad one is sent back to the
   model once, then the next model is tried.

## Reliability & privacy built in

- Per-request deadlines (turn 18 s, result 28 s) under the backend's 20 s / 30 s.
- Model fallback on 429 / 5xx / timeout / invalid JSON (gpt-oss-20b <-> 120b: separate quotas on Groq free plan).
- Audio is decoded in memory only; **nothing is stored; logs hold metadata only** (ids, models, latency, status),
  never audio, transcripts or questions. Validation errors never echo submitted values.
- Student text is wrapped in `<student_answer>` tags and treated as data (prompt-injection resistant).
- `student_ref` and `interview_id` are never sent to the model.
- TTS failure never fails a turn (text is always returned, audio is `null`).

## Groq free plan notes (demo)

Limits are per model and per organization (check https://console.groq.com/settings/limits).
Roughly 8,000 tokens/minute and 200,000/day per LLM; Orpheus has far smaller limits (about 100 requests/day;
verify). Keep track profiles short (`PROFILE_MAX_CHARS_*`), do not let the whole team test against the same key,
and use the mock server for backend integration. When you move to production: enable billing, then re-check
model names at https://console.groq.com/docs/models.

## Production checklist

- [ ] `APP_ENV=production`, `AUTH_DISABLED=false`, `JWT_PUBLIC_KEY[_FILE]` set, `FAKE_MODELS=false`
- [ ] Groq billing enabled (data terms read; users are minors), key in a secret manager
- [ ] Model names verified in Groq docs; Orpheus terms accepted in the Groq console
- [ ] Real voice test: kids' voices / Egyptian & Saudi English accents on Whisper; tune `STT_MODEL`
- [ ] Run `python scripts/smoke_test.py` on staging; check latency (<10 s turn, <20 s result)
- [ ] Alert on 429 rate, `PROVIDER_UNAVAILABLE`, p95 latency; run behind TLS, accept calls from the backend only
- [ ] Backend fallback rehearsed (kill the key, confirm students see fixed questions / static result)

## Honest status

All 62 tests pass, including the Groq adapters against a simulated HTTP API, and the service ran end to end
in fake mode and with real JWT auth. **It has not been run against the real Groq API** (no network access when it
was built): the request shapes follow Groq's OpenAI-compatible API, but the first real call may need small
tweaks (e.g. `reasoning_effort` values, Orpheus voice names / terms). Run `python scripts/smoke_test.py` first.

## Tests

`pip install -r requirements-dev.txt && pytest`
