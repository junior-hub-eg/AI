# Junior Hub Student Assistant

> **Inside the AI repo.** This is the chatbot's original README. Here it runs as part of the AI service (`app.main:create_app`, port 8000) next to the Discovery endpoints: the code is in `assistant/`, the data in `assistant/data/` and `assistant/mock/`, the tests in `tests/assistant/`, and every setting starts with `ASSISTANT_` (see `.env.example`). The Windows scripts and Dockerfile below are not part of this repo.


A chat assistant that answers students' questions about their own Junior Hub journey: their tracks and level, the
Track Discovery result, lessons and where they stopped, XP, streak and badges, their squad, teammates and tasks,
their mentor, and practice jobs. It also explains lesson concepts and how the platform works.

Python, FastAPI and LangGraph, with any LLM that supports tool calling (Cohere by default). It is a **stateless HTTP
service with one endpoint**. The Junior Hub backend owns the conversation and the data: it sends the student's data
with every message, and the service never touches the database.

```
Student ──► Frontend ──► Junior Hub backend (.NET) ─────────────► Assistant service (this repo)
                          │ 1. checks the student's login            POST /v1/assistant/replies
                          │ 2. stores the question                   │ reads the student's data from the request
                          │ 3. reads the student's data from the DB  │ asks the LLM, which may look up details
                          │ 4. calls the assistant                   │ with tools over that same data
                          │ 5. stores the reply (or a fallback)      ▼
                          ▼                                          reply + suggestions + links + topic
                       Database
```

**For the developer connecting it:** read [What the backend needs to do](#what-the-backend-needs-to-do) and
[The data the bot needs](#the-data-the-bot-needs). Everything else is reference.

| Document | What it has |
|---|---|
| [docs/API.md](docs/API.md) | The full contract: every field, value and rule |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Step by step for the backend, with the SQL tables and checklist |
| [docs/backend-reference/](docs/backend-reference/) | A C# implementation of the backend side in the Junior Hub style. **Never compiled**: a starting point |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | What the bot knows and answers, its limits, the mock students (Arabic) |
| [docs/examples/](docs/examples/) | A complete request and response |
| http://localhost:8000/docs | Interactive OpenAPI docs while the service runs |

---

## Try it in 2 minutes

Windows, from this folder:

```powershell
python -m venv .venv                       # or: & "C:\path\to\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env                     # then set ASSISTANT_LLM_MODEL and the key, see Configuration
start.bat                                  # opens http://localhost:8010 and reloads on code changes
```

(Linux/macOS: `source .venv/bin/activate`, then `uvicorn app.main:create_app --factory --port 8000 --reload`.)

With `ASSISTANT_DEV_ENDPOINTS=true`, http://localhost:8000/assistant/ is a **test chat page**: pick one of 8 mock students, see all their
data at the top, ask questions, and under every reply see the topic, the tools used, the time, and the exact data the
bot had, to check it did not make anything up. `python chat_cli.py` is the same in the terminal.

Tests, no API key needed: `.venv\Scripts\python.exe -m pytest`

---

## How it answers

```
system prompt + student snapshot + recent history + the new message
        │
        ▼
      LLM ──(needs details)──► tool (reads the request's data) ──► LLM ...   at most ASSISTANT_MAX_STEPS lookups
        │
        └──(respond tool)──► reply, suggestions, links, topic ──► cleaned ──► response
```

1. **Snapshot.** A short summary of the student (XP, streak, tracks, next lesson, squad and teammates, mentor) goes
   in the system prompt, so simple questions take one LLM call and no tool.
2. **Tools.** For details the LLM calls a tool. Every tool reads only the data in this request and the bundled
   catalog; the student is never a tool parameter, so one student can never reach another's data.
3. **Respond.** The LLM must finish by calling `respond` with the reply, a topic, up to 3 follow-up suggestions and up
   to 3 links. After `ASSISTANT_MAX_STEPS` lookups only `respond` is offered, so a reply always comes.
4. **Clean.** Before returning: the reply is cut to 2000 characters, model markup (like Cohere's `<co>` citations) is
   removed, suggestions over 80 characters are dropped, and links to lessons, tracks or mentors that do not exist are
   dropped.

| Tool | Answers questions like |
|---|---|
| `get_my_learning` | "What's my next lesson?", "Where did I stop?" |
| `get_lesson_help` | "Explain functions", "My Try it doesn't work" (concept, starter code, school link; never quiz answers) |
| `get_discovery_result` | "Why was Frontend recommended to me?" |
| `get_track_info` | "What is Data?", "Does UI/UX have lessons?" |
| `get_my_achievements` | "How much XP do I have and from what?", "How do I get the next badge?" |
| `get_my_squad` | "Who is in my squad?", "What are my tasks?", "When does the sprint end?" |
| `find_mentors` | "Who is my mentor?", "Mentors for Backend?" |
| `find_practice_jobs` | "Are there practice jobs for my track?", "Where is my certificate?" |
| `get_platform_rules` | "How is XP counted?", "Why did my streak reset?" |

Rules the bot keeps (in `app/prompt.py`): Egyptian Arabic with programming terms in English (English if the student
writes English); short; only facts from its data, never invented; hints for quizzes, never the answer; no full Try it
solutions; kind redirect for homework of other subjects or anything off-platform; gentle `wellbeing` reply that points
to a trusted adult when a student sounds sad or unsafe; never asks for personal data.

---

## The API

### `POST /v1/assistant/replies`

Headers: `Authorization: Bearer <service token>` (see [Security](#security)), `Content-Type: application/json`,
optional `X-Request-Id`.

```json
{
  "conversation_id": "1d0c2f6e-8a4b-4c1e-9f2a-3b5d7e9a1c20",
  "student_ref": "8f1c4b2a-6d3e-4f5a-9b7c-0e2d4f6a8b1c",
  "message": "ليه اترشحلي Frontend؟",
  "history": [
    { "role": "student", "text": "عندي كام XP؟" },
    { "role": "assistant", "text": "معاك 100 XP والـ streak بتاعك 3 أيام 👏" }
  ],
  "context": { "...": "the student's data, next section" }
}
```

| Field | Rule |
|---|---|
| `conversation_id` | Your conversation's id (any UUID) |
| `student_ref` | `Students.StudentRef`, **not** the student's id (BR-15) |
| `message` | 1 to 1000 characters |
| `history` | The conversation's last messages before `message`, oldest first, at most 20. `role` is `student` or `assistant` |
| `context` | The student's data at this moment (next section) |

Response `200`:

```json
{
  "reply": "اترشحلك Frontend لأنك بتحب تشوف شغلك على الشاشة على طول (86% match)...",
  "suggestions": ["اشرحلي الـ functions", "مين المنتور بتاعي؟"],
  "links": [{ "kind": "lesson", "ref": "dab266be-e6a4-5efd-a5f4-503784941482", "label": "Functions" }],
  "topic": "discovery",
  "meta": { "prompt_version": "assistant@v1", "model_id": "cohere:command-a-03-2025", "latency_ms": 2140 }
}
```

| Field | Use |
|---|---|
| `reply` | Show it and store it. Up to 2000 characters, plain text with line breaks |
| `suggestions` | 0 to 3 short questions; show as chips the student can tap to send |
| `links` | 0 to 3 pages to open. `kind`: `lesson` (ref = lesson id), `track` (ref = track code), `mentor` (ref = mentor id), or `squad`, `discovery`, `achievements`, `jobs` (ref empty) |
| `topic` | Store for reporting: `my_progress`, `learning`, `tracks`, `discovery`, `squad`, `mentor`, `jobs`, `platform`, `concept_help`, `small_talk`, `out_of_scope`, `wellbeing` |
| `meta` | Store `prompt_version` and `model_id` with the reply |

Errors always have the body `{ "error": { "code", "message", "request_id" } }`:

| Status | Code | Meaning | Backend action |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | A field is missing or out of range; the message names the fields | Fix the request |
| 401 | `UNAUTHENTICATED` | Bad, expired or missing service token (checked before the body) | Check keys and server clock |
| 503 | `PROVIDER_UNAVAILABLE` | The LLM failed or could not start | Show and store the fallback reply |
| 504 | `TIMEOUT` | No reply within `ASSISTANT_REPLY_TIMEOUT_SECONDS` (18 s) | Show and store the fallback reply |

Other endpoints: `GET /assistant/health` (no token: status, model, catalog version), `GET /docs` and `GET /openapi.json`.
Development only, with `ASSISTANT_DEV_ENDPOINTS=true`: `GET /assistant/` (test page), `GET /v1/dev/personas`,
`GET /v1/dev/personas/{name}`, `POST /v1/dev/chat` (`{ persona, message, history }`, answers with an extra `debug`
block showing what the bot saw). They answer 404 otherwise.

---

## The data the bot needs

`context` is everything the bot knows about the student. **Build it fresh for every message** (read-only queries for
the signed-in student). Names are snake_case, enums are sent as their text (`Beginner`, `ToDo`, `UIUX`), dates as ISO
8601, ids as GUID strings. Every section must be present: use `null` or `[]` for "none". A full example is
[`mock/contexts/frontend_beginner.json`](mock/contexts/frontend_beginner.json).

| Field | What | Source in the Junior Hub database |
|---|---|---|
| `today` | The school's date | `SchoolCalendar.Today` (Cairo) |
| `student.grade`, `.is_independent` | School grade, or a student without a school | `Students.Grade`, `Students.SchoolId IS NULL` |
| `student.total_xp`, `.streak_days`, `.last_active_date` | XP and streak | `Students.TotalXp`, `Student.CurrentStreak(today)`, `Students.LastActiveDate` |
| `discovery.status` | `NotStarted`, `InProgress` or `Completed` | `DiscoveryInterviews.Status` (latest completed wins) |
| `discovery.path`, `.completed_utc`, `.summary` | How it was taken, when, the AI summary | `DiscoveryInterviews.Path`, `.CompletedUtc`, `.AiSummary` |
| `discovery.recommendations[]` | Top 3: `rank`, `track_code`, `match_percent`, `reason`, `level`, `level_reason` | `DiscoveryRecommendations` + `Tracks.Code` |
| `tracks[]` | Each active track: `code`, `name`, `level`, `source`, `in_focus`, `selected_utc`, `lessons_done`, `lessons_total` | `StudentTracks` (`Status = Active`) + `Tracks`; `in_focus` = `Students.ActiveTrackId`; counts from `Lessons` and `LessonProgress.CompletedUtc` |
| `exploration[]` | Per touched track: `videos_completed`, `videos_total`, `quiz_passed`, `best_quiz_score`, `quiz_total` | `TrackVideoViews`, `TrackQuizAttempts`, counts of `TrackVideos` and `TrackQuizQuestions` |
| `learning.track_code`, `.next_lesson_id` | Track in focus and the next lesson to do | First unfinished lesson of `LessonPath.FromLevel(lessons, level)`; `null` when all are done |
| `learning.lessons[]` | Every lesson of that track in order: `id`, `module`, `title`, `concept`, `level`, `status` (`NotStarted`/`InProgress`/`Done`), `current_step`, `quiz_attempts`, `in_path`, `school_link {subject, title}` | `Modules` + `Lessons` + `LessonProgress`; `school_link` only for a `SchoolLesson` of the student's grade (BR-09) |
| `achievements.badges[]` | `code`, `name`, `type`, `earned_utc` | `StudentBadges` + `Badges` |
| `achievements.recent_xp[]` | Latest 20: `reason`, `points`, `created_utc` | `XpTransactions` newest first |
| `squad` | `name`, `project_title`, `project_description`, `my_role` | `SquadMembers` → `Squads`; `null` without a squad |
| `squad.members[]` | `role`, `is_me`, `name` (**first name**, teammates only) | `SquadMembers` + `Users.FullName` |
| `squad.sprint` | `name`, `start_date`, `end_date`, `status`, `tasks_done`, `tasks_total` | The squad's `Sprints` with `Status = Active` + `SquadTasks` counts |
| `squad.my_tasks[]` | `title`, `status`, `story_points` | `SquadTasks` of that sprint assigned to the student |
| `mentor` | `id`, `full_name`, `title`, `track_code`, `languages`, `availability`, `started_utc` | `MentorAssignments` with `EndedUtc IS NULL` + `Mentors`; `null` without one |
| `recruitment.applications[]` | `role`, `company_name`, `track_code`, `level`, `status`, `attempts`, `best_score_percent`, `certificate_code` | `JobApplications` + `JobPostings` + `SimulationAttempts` + `SimulationCertificates` (empty while the app has no recruitment feature) |

**Never send:** the student's own name, email, phone, school or class; parents; full names of other students; any
quiz question, option or `CorrectOptionIndex` (DR-11). Unknown extra fields are ignored, so the backend can add
fields before the bot uses them.

The bot also has its own copy of the platform's content in `data/catalog.json` (tracks, lessons with concepts and Try
it code, mentors, practice jobs; **no quiz questions or answers**), built from the backend's seed content, and the
platform rules in `data/platform_rules.md`. Lesson and mentor ids in the catalog are the backend's seed ids. After
Product edits the seed content: `python scripts/sync_catalog.py <backend>/src/JuniorHub.Infrastructure/Seeding/Content`.

---

## What the backend needs to do

This is the expected setup on the Junior Hub side. It follows the same pattern as the Discovery AI service
(`DiscoveryAi/`, `HubReader`, `DiscoveryInterview`). A C# version of every piece is in
[docs/backend-reference/](docs/backend-reference/).

**1. Store conversations.** Two tables in the `jh` schema:

```
AssistantConversations  Id, StudentId (FK Students), Title nvarchar(80), StartedUtc, LastMessageUtc
                        index (StudentId, LastMessageUtc)
AssistantMessages       Id, ConversationId (FK), OrderIndex, Role ('Student'|'Assistant'), Text nvarchar(2000),
                        Source ('Ai'|'Fallback', replies), Topic, PromptVersion, ModelId, CreatedUtc
                        unique (ConversationId, OrderIndex)
```

A question and exactly one reply alternate; start a new conversation after 200 messages.

**2. Endpoints for the frontend** (student's access token, under `/api/v1`):

| Endpoint | Does |
|---|---|
| `POST /assistant/messages` `{ conversationId?, text }` | Stores the question, builds `context`, calls the service, stores and returns `{ conversationId, message, reply, suggestions, links, isFallback, canContinue }`. No `conversationId` starts a new conversation |
| `GET /assistant/conversations` | The student's latest conversations |
| `GET /assistant/conversations/{id}` | One conversation with its messages (404 if it is another student's) |

Rate limit the POST per signed-in session (about 20 per minute), not per IP: a school class shares one IP.

**3. Build `context`** with read-only queries, as in the table above (`AssistantContextReader.cs` in the reference
does it in one round of queries).

**4. Call the service**: `POST {BaseUrl}/v1/assistant/replies` with a fresh service token, the last 20 messages as
`history`, a **20-second timeout and no retry**. The same JSON settings as `HttpDiscoveryAiClient` (snake_case,
string enums) produce the right shape.

**5. Handle the result.** On 200: store `reply`, `topic`, `meta.prompt_version`, `meta.model_id`; pass `suggestions` and
`links` to the frontend; keep only links of a known `kind` whose `ref` is a GUID (`lesson`, `mentor`), an upper-case
track code (`track`) or empty. On any error or timeout: store and return a fallback reply with `isFallback: true`,
for example "معلش، مش قادر أرد دلوقتي 🙏 جرّب تاني كمان شوية، ولحد ما أرجع تقدر تكمّل درسك من صفحة Courses."

**6. Configure**: `AssistantAi:BaseUrl`, `AssistantAi:SigningKeyPem` (private key), in the secret store, never in
`appsettings`. In production refuse to start without them, like `DiscoveryAi`.

Checklist once connected:

- [ ] A question without `conversationId` creates a conversation; the next one with its id continues it.
- [ ] The service receives the previous messages as `history`, oldest first.
- [ ] The serialized `context` of a seeded student has no student's own name, email, school, or `correct`.
- [ ] Stopping the service gives the fallback reply with `isFallback: true`, stored as `Source = Fallback`.
- [ ] A token signed with another key, or with audience `discovery-ai`, gets 401.
- [ ] Another student's conversation id gives 404.

---

## Security

- **Service token.** The backend signs every call with RS256: `iss` `JuniorHub.Api`, `aud` `assistant-ai`, `iat`, `nbf`,
  `exp` 5 minutes later. Use a key pair of its own, not the Discovery one. The service holds only the public key.

  ```bash
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out assistant-ai-private.pem
  openssl rsa -in assistant-ai-private.pem -pubout -out assistant-ai-public.pem
  ```

- **Privacy.** The student is only `student_ref`. Teammates come by first name and role (a product decision beyond
  BR-15 as written in JH-SRS v0.1: confirm it). Messages and replies are never logged; logs hold the request id,
  prompt version, model, latency, topic and tool names only.
- `ASSISTANT_AUTH_DISABLED` and `ASSISTANT_DEV_ENDPOINTS` are for a developer's machine only. Never set them in production.

---

## Configuration

Environment variables, or a `.env` file in the folder the service runs from (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ASSISTANT_LLM_MODEL` | `fake` | `provider:model`: `cohere:command-a-03-2025`, `openai:gpt-4.1-mini`, `google_genai:gemini-2.5-flash`, `anthropic:claude-haiku-4-5`, `groq:llama-3.3-70b-versatile`. `fake` gives canned answers without a key (wiring checks only) |
| `COHERE_API_KEY` (or the provider's key) | | The LLM provider's API key |
| `ASSISTANT_LLM_TEMPERATURE` | `0.3` | |
| `ASSISTANT_LLM_TOOL_CHOICE` | `any` | `any` forces a tool call each step; `auto` for providers that cannot force tools |
| `ASSISTANT_MAX_STEPS` | `4` | Data lookups per reply before the bot must answer |
| `ASSISTANT_REPLY_TIMEOUT_SECONDS` | `18` | After this the service answers 504 |
| `ASSISTANT_AUTH_PUBLIC_KEY_PEM` or `ASSISTANT_AUTH_PUBLIC_KEY_FILE` | | Public key that checks the service token |
| `ASSISTANT_AUTH_AUDIENCE`, `ASSISTANT_AUTH_ISSUER` | `assistant-ai`, `JuniorHub.Api` | |
| `ASSISTANT_AUTH_DISABLED` | `false` | Skip the token check (local testing only) |
| `ASSISTANT_DEV_ENDPOINTS` | `false` | Test page and `/v1/dev/*` (local testing only) |

Each provider needs its LangChain package: `langchain-cohere` (in `requirements-dev.txt`), `langchain-openai`,
`langchain-google-genai`, `langchain-anthropic` or `langchain-groq`. Cohere gets the tools with their full JSON
schema and citations turned off (`app/providers.py`).

## Deploy

```bash
docker build -t junior-hub-assistant .            # Cohere by default; --build-arg PROVIDER_PACKAGE=langchain-openai for OpenAI
docker run -p 8010:8010 \
  -e ASSISTANT_LLM_MODEL=cohere:command-a-03-2025 -e COHERE_API_KEY=... \
  -e ASSISTANT_AUTH_PUBLIC_KEY_PEM="$(cat assistant-ai-public.pem)" junior-hub-assistant
```

Health check: `GET /assistant/health`. One process handles many conversations; each reply is one to five LLM calls, usually
2 to 8 seconds.

## Project layout

```
app/
  main.py          FastAPI app: endpoints, errors, the dev test page
  assistant.py     One request → one reply: messages, the loop, cleaning
  graph.py         The LangGraph loop (LLM ↔ tools, finish with respond)
  tools.py         The 9 data tools and respond
  prompt.py        System prompt and the student snapshot
  schemas.py       Request, response and context models (the contract in code)
  catalog.py       Platform content and rules
  providers.py     Binding tools per LLM provider (Cohere)
  llm.py           Creating the LLM from ASSISTANT_LLM_MODEL; fake_llm.py: the no-key stand-in
  auth.py, config.py
  static/playground.html   The test chat page
data/              catalog.json, platform_rules.md
mock/contexts/     8 mock students
scripts/           sync_catalog.py
tests/             48 tests, no API key needed
docs/              API, integration guide, capabilities, examples, C# reference
chat_cli.py        Terminal chat; start.bat, run.ps1: Windows helpers
```
