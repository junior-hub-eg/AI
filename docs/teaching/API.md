# Teaching AI — API contract

Part of the AI service (same app and deployment as Discovery and the student assistant). Review notes of 25 Oct 2026:
the track-video ↔ school-subject link and the Arabic grammar coach (مدرّب النحو).

- Auth: every `/v1/teaching/*` call needs `Authorization: Bearer <token>`, RS256 signed by the backend with its own key
  pair (not the Discovery or assistant one): audience `teaching-ai`, issuer `JuniorHub.Api`, at most 5 minutes.
  The service holds the public key in `TEACHING_AUTH_PUBLIC_KEY_PEM`.
- JSON names are snake_case. Texts are Arabic by default (`language: "en"` where offered).
- Errors: `{ "error": { "code", "message", "request_id" } }` — 400 `INVALID_REQUEST`, 401 `UNAUTHENTICATED`,
  503 `PROVIDER_UNAVAILABLE` (show a friendly message), 504 `TIMEOUT`.
- Settings: `TEACHING_LLM_MODEL` (default `groq:openai/gpt-oss-120b`, `fake` for tests), `TEACHING_LLM_FALLBACK_MODEL`,
  `TEACHING_VISION_MODEL` (reads photos, default `groq:meta-llama/llama-4-scout-17b-16e-instruct`), `GROQ_API_KEY`.

## Track video ↔ subject

`POST /v1/teaching/video-links`

```json
{ "track_name": "Artificial Intelligence", "video_title": "Computer Vision", "video_description": "…",
  "subject": "Physics", "grade": 9, "language": "ar" }
```
→ `{ "summary": [3 strings: what it is, how it works, where it is used], "ideas": [3 × { "title", "text" }], "meta" }`

`POST /v1/teaching/quick-check` — `{ "title", "context", "count": 1–10, "language" }`
→ `{ "questions": [{ "question", "options": [2–5], "answer_index", "explanation" }], "meta" }`

## Grammar coach

A parsed sentence: `{ "text", "words": [{ "word", "role", "case", "sign", "explanation", "color" }] }`, with `color`
one of `blue` (مرفوع), `green` (منصوب), `orange` (مجرور), `purple` (مجزوم), `gray` (مبني/حروف), `teal`, `red`.

| Endpoint | Request | Response |
|---|---|---|
| `POST /v1/teaching/grammar/ocr` | `{ "image_base64", "mime_type": "image/png\|jpeg\|webp" }` | `{ "text" }` |
| `POST /v1/teaching/grammar/parse` | `{ "text" }` | `{ "sentences": [parsed sentence] }` |
| `POST /v1/teaching/grammar/lesson` | `{ "topic_title", "roles": [..], "difficulty": 1–5 }` | `{ "points": [3–4 × { "title", "text", "color" }], "examples": [2 parsed], "practice": parsed }` |
| `POST /v1/teaching/grammar/feedback` | `{ "topic_title", "sentence", "mistakes": [{ "word", "expected", "given" }] }` | `{ "items": [{ "word", "what", "why", "guiding_questions": [{ "question", "answer" }] }], "similar_sentence": parsed }` |
| `POST /v1/teaching/grammar/ask` | `{ "topic_title", "question", "context"?, "history"?: [{ "role": "student"\|"coach", "text" }] }` | `{ "answer" }` (2-3 simple Arabic sentences) |

The backend keeps the right answers (the practice sentence's roles, the quiz's `answer_index`) and checks the student's
answers itself; the AI only writes content and explains mistakes.
