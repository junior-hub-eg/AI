# Student Assistant API

The contract between the Junior Hub backend and the Student Assistant service. The assistant is a chat helper that
answers what a student asks about their own journey (tracks, lessons, XP, badges, squad, mentor, practice jobs) and
about the platform. It follows the same rules as the Discovery AI service (`docs/discovery-ai-contract.md` in the
backend repo). How to connect it step by step: [INTEGRATION.md](INTEGRATION.md).

## Endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| `POST /v1/assistant/replies` | Service token | Reply to one student message (below) |
| `GET /health` | None | `{ "status": "ok", "model", "catalog_version" }` |
| `GET /docs`, `GET /openapi.json` | None | Interactive docs and the OpenAPI schema |
| `GET /v1/dev/personas`, `GET /v1/dev/personas/{name}`, `POST /v1/dev/chat` | None | Development only (`DEV_ENDPOINTS=true`): chat as a mock student; 404 otherwise |

Full examples: [examples/reply-request.json](examples/reply-request.json) and
[examples/reply-response.json](examples/reply-response.json).

## Who calls whom

```
Student ──► Backend (.NET) ──► Assistant AI service
               │                (POST /v1/assistant/replies)
               ▼
            Database   (conversations and messages are stored only by the backend)
```

- The backend owns the conversation: it stores every message (suggested tables in [INTEGRATION.md](INTEGRATION.md))
  and sends the recent history with each call. The AI service is stateless and stores nothing.
- The AI service never calls the backend and never touches the database. Everything it needs about the student
  arrives in `context`; everything about the platform's content is in its own catalog (see *Catalog*).
- The student is known only by `student_ref` (BR-15). No name, email, phone, school, class or parent is ever sent.
  Teammates in the squad are sent by first name and role only (never the student's own name). Mentors are seeded
  profiles, so their full names are sent. Sending teammates' first names is a product decision beyond BR-15 as
  written in JH-SRS v0.1; the backend team should confirm it.
- Every call carries `Authorization: Bearer <JWT>` signed by the backend with RS256, audience `assistant-ai`,
  issuer `JuniorHub.Api`, valid 5 minutes. The service holds only the public key and rejects any other token with 401.
- Correct quiz answers (`CorrectOptionIndex` of track quizzes, lesson quizzes and recruitment questions) never reach the
  AI service (DR-11). The assistant gives hints, not answers.

## POST /v1/assistant/replies

Request:

```json
{
  "conversation_id": "1d0c…",
  "student_ref": "8f1c…",
  "message": "ليه اترشحلي فرونت إند؟",
  "history": [
    { "role": "student", "text": "عندي كام XP؟" },
    { "role": "assistant", "text": "معاك 100 XP…" }
  ],
  "context": { "…": "see AssistantContext" }
}
```

| Field | Rule |
|---|---|
| `message` | 1 to 1000 characters, trimmed |
| `history` | Oldest first, at most the last 20 messages before `message`. `role` is `student` or `assistant` |
| `context` | The student's data at the time of the message (below) |

Response:

```json
{
  "reply": "اترشحلك Frontend لأنك بتحب تشوف شغلك على الشاشة على طول…",
  "suggestions": ["أبدأ أول درس إزاي؟", "مين المنتور المناسب ليا؟"],
  "links": [{ "kind": "lesson", "ref": "6b2e…", "label": "Functions" }],
  "topic": "tracks",
  "meta": { "prompt_version": "assistant@v1", "model_id": "…", "latency_ms": 2100 }
}
```

| Field | Rule |
|---|---|
| `reply` | 1 to 2000 characters, written to the student |
| `suggestions` | 0 to 3 follow-up questions the student can tap, each at most 80 characters |
| `links` | 0 to 3. `kind` is one of `lesson`, `track`, `mentor`, `squad`, `discovery`, `achievements`, `jobs`. `ref` is a lesson id, track code or mentor id from the request or the catalog; empty for the pages without one. The backend drops a link whose `ref` it does not know |
| `topic` | One of `my_progress`, `learning`, `tracks`, `discovery`, `squad`, `mentor`, `jobs`, `platform`, `concept_help`, `small_talk`, `out_of_scope`, `wellbeing` |

`topic` is stored with the reply for reporting. `wellbeing` means the student said something worrying about themselves
(sad, bullied, unsafe); the reply is kind, short, and encourages talking to a parent, a teacher or another trusted adult.

## AssistantContext

All fields are present; empty lists and `null` mean "none". Dates are UTC ISO 8601, `today` is the school's local date.

```json
{
  "today": "2026-10-20",
  "student": { "grade": 9, "is_independent": false, "total_xp": 95, "streak_days": 3, "last_active_date": "2026-10-19" },
  "discovery": {
    "status": "Completed",
    "path": "Unsure",
    "completed_utc": "2026-10-12T09:30:00Z",
    "summary": "…",
    "recommendations": [
      { "rank": 1, "track_code": "FRONTEND", "match_percent": 86, "reason": "…", "level": "Beginner", "level_reason": "…" }
    ]
  },
  "tracks": [
    { "code": "FRONTEND", "name": "Frontend", "level": "Beginner", "source": "Recommended", "in_focus": true,
      "selected_utc": "…", "lessons_done": 1, "lessons_total": 4 }
  ],
  "exploration": [
    { "track_code": "FRONTEND", "videos_completed": 2, "videos_total": 2, "quiz_passed": true, "best_quiz_score": 3, "quiz_total": 3 }
  ],
  "learning": {
    "track_code": "FRONTEND",
    "next_lesson_id": "6b2e…",
    "lessons": [
      { "id": "6b2e…", "module": "Module 1: Thinking in code", "title": "Functions", "concept": "functions",
        "level": "Beginner", "status": "InProgress", "current_step": "TryIt", "quiz_attempts": 0, "in_path": true,
        "school_link": { "subject": "Math", "title": "Linear functions" } }
    ]
  },
  "achievements": {
    "badges": [{ "code": "math-variables", "name": "Linked to Math · Variables", "type": "SubjectLink", "earned_utc": "…" }],
    "recent_xp": [{ "reason": "LessonPassed", "points": 40, "created_utc": "…" }]
  },
  "squad": {
    "name": "Code Hunters",
    "project_title": "School Events App",
    "project_description": "…",
    "my_role": "Frontend",
    "members": [{ "role": "Frontend", "is_me": true }, { "role": "Backend", "is_me": false, "name": "Omar" }],
    "sprint": { "name": "Sprint 04", "start_date": "2026-10-11", "end_date": "2026-10-24", "status": "Active", "tasks_done": 5, "tasks_total": 8 },
    "my_tasks": [{ "title": "Build the sign-up form", "status": "Review", "story_points": 3 }]
  },
  "mentor": {
    "id": "…", "full_name": "Sara El-Masry", "title": "Senior Frontend Engineer", "track_code": "FRONTEND",
    "languages": "Arabic, English", "availability": "…", "started_utc": "…"
  },
  "recruitment": {
    "applications": [
      { "role": "Junior Frontend Developer", "company_name": "Pixel Lane Studio", "track_code": "FRONTEND", "level": "Beginner",
        "status": "InterviewPassed", "attempts": 1, "best_score_percent": 80, "certificate_code": "JH-SIM-4F7K2Q" }
    ]
  }
}
```

| Section | Values |
|---|---|
| `discovery.status` | `NotStarted`, `InProgress`, `Completed` (the latest completed result wins over an abandoned one) |
| `discovery.path` | `KnowsTrack`, `Unsure`, `Exploring` |
| `tracks[]` | Active tracks only. `source` is `Recommended` or `ManualChoice`; exactly one has `in_focus: true` |
| `learning` | The track in focus. `null` when the student has no track. `lessons` is empty when the track has no lessons yet |
| `learning.lessons[].status` | `NotStarted`, `InProgress`, `Done`. `current_step` is `SchoolLink`, `Video`, `TryIt`, `Quiz` or `Done`, `null` when not started |
| `learning.lessons[].in_path` | `false` for lessons below the student's starting level: open, but not where they are sent next |
| `achievements.recent_xp` | The latest 20 XP transactions, newest first. `reason` is `VideoWatched`, `TrackQuizPassed`, `LessonPassed`, `TaskDone`, `SimulationCompleted` |
| `squad` | `null` when the student is in no squad; `sprint` is `null` when no sprint is active. Task `status` is `ToDo`, `InProgress`, `Review`, `Done` |
| `mentor` | The current mentor or `null` |
| `recruitment.applications[].status` | `Applied`, `InterviewPassed`, `InterviewNotPassed` |

## Catalog

The tracks, lessons (concepts, Try it starter code, school links), mentors and practice jobs are the seed content in
`src/JuniorHub.Infrastructure/Seeding/Content/`. The AI service keeps its own copy built from those files by its sync
script (`python scripts/sync_catalog.py <path to Seeding/Content>`), with every quiz question and correct answer
removed. Run the sync after Product edits the content. Lesson and mentor ids in the catalog are the backend's seed ids
(`SeedIds.For`), so the ids in `context` match them.

## Behaviour

- Language: Egyptian Arabic, short and friendly, for students aged 11 to 18. Programming terms stay in English.
  If the student writes in English, answer in English.
- Answer from `context` and the catalog only. When the data is not there, say so and point to the page that has it.
  Never invent XP, lessons, dates, mentors or results.
- Quizzes: explain the idea and give a hint; never give the option to choose. Try it: guide, do not write the full solution.
- Practice jobs are always simulations (BR-12): a certificate is not a job offer.
- Out of scope (homework of other subjects, general chat, anything unsafe): one kind sentence and a way back to Junior Hub.
- Never ask for or repeat personal data (phone, address, passwords, social accounts).

## Errors and limits

Every error has the body `{ "error": { "code", "message", "request_id" } }`. `request_id` echoes the `X-Request-Id`
header when sent.

| Status | Code | When | What the backend does |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | A field is missing or out of range; `message` names the fields, never their values | Fix the request |
| 401 | `UNAUTHENTICATED` | Token missing, expired, wrong audience or issuer, or signed with another key. Checked before the body | Check the key pair and the clock |
| 503 | `PROVIDER_UNAVAILABLE` | The model provider failed | Store and show the fallback reply |
| 504 | `TIMEOUT` | No reply within `REPLY_TIMEOUT_SECONDS` (18 s by default) | Store and show the fallback reply |

Call with a client timeout of 20 s and no automatic retry. Messages and replies are never logged by the service: only
request id, prompt version, model, latency, topic and tool names.
