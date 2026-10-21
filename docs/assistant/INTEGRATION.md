# Connecting the Student Assistant to the Junior Hub backend

For the backend team. The assistant service is ready and tested on its own; this guide is what the backend needs to
add so students can chat with it. The wire contract is [API.md](API.md); what the bot knows and answers is [CAPABILITIES.md](CAPABILITIES.md).

```
Frontend ──POST /api/v1/assistant/messages──► Backend (.NET)
                                                 1. checks the student's access token
                                                 2. stores the question
                                                 3. builds the student's context from the database
                                                 4. signs a service token
                                                 ──POST /v1/assistant/replies──► Assistant service (Python)
                                                 5. stores the reply (or the fallback)
Frontend ◄─────────── question + reply ──────────┘
```

The service never reads the database and keeps no state, exactly like the Discovery AI service. Everything the backend
needs to add follows patterns already in the codebase (`DiscoveryAi/`, `HubReader`, `DiscoveryInterview`).

A full reference implementation in the backend's style is in [backend-reference/](backend-reference/): entities,
EF configurations, context reader, HTTP and mock clients, handlers, controller and tests, plus the edits to existing
files in [CHANGES-TO-EXISTING-FILES.md](backend-reference/CHANGES-TO-EXISTING-FILES.md). **It was written without a
.NET SDK and never compiled**: use it as a starting point and expect small fixes.

## 1. Run the service

Locally:

```bash
cd assistant-ai
python -m venv .venv && .venv\Scripts\activate        # source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt langchain-cohere       # or the package of your provider
copy .env.example .env                                 # set LLM_MODEL and the provider key
uvicorn app.main:app --port 8010
```

On Windows `powershell -ExecutionPolicy Bypass -File .\run.ps1 -Api` does all of that. Interactive docs:
http://localhost:8010/docs.

With Docker:

```bash
docker build -t junior-hub-assistant .                     # Cohere by default; --build-arg PROVIDER_PACKAGE=langchain-openai for OpenAI
docker run -p 8010:8010 -e LLM_MODEL=cohere:command-a-03-2025 -e COHERE_API_KEY=... \
  -e AUTH_PUBLIC_KEY_PEM="$(cat assistant-ai-public.pem)" junior-hub-assistant
```

| Setting | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | `fake` | `provider:model`, for example `cohere:command-a-03-2025`, `openai:gpt-4.1-mini`, `google_genai:gemini-2.5-flash`. `fake` answers without a model (wiring checks only) |
| `<PROVIDER>_API_KEY` | | The provider's key, for example `COHERE_API_KEY`, `OPENAI_API_KEY` or `GOOGLE_API_KEY` |
| `AUTH_PUBLIC_KEY_PEM` or `AUTH_PUBLIC_KEY_FILE` | | Public key that checks the backend's service token |
| `AUTH_AUDIENCE`, `AUTH_ISSUER` | `assistant-ai`, `JuniorHub.Api` | Expected token audience and issuer |
| `REPLY_TIMEOUT_SECONDS` | `18` | The service answers 504 after this; the backend's own timeout should be 20 s |
| `MAX_STEPS` | `4` | Data lookups per reply before the model must answer |
| `LLM_TOOL_CHOICE` | `any` | `auto` for a provider that cannot force tool calls |
| `AUTH_DISABLED`, `DEV_ENDPOINTS` | `false` | Local testing only. Never in production |

## 2. Keys

A key pair of its own, not the Discovery one:

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out assistant-ai-private.pem
openssl rsa -in assistant-ai-private.pem -pubout -out assistant-ai-public.pem
```

The private key goes to the backend's secret store (for example `AssistantAi__SigningKeyPem`), the public key to the
service (`AUTH_PUBLIC_KEY_PEM`). The token is the same as Discovery's with another audience: RS256, `iss`
`JuniorHub.Api`, `aud` `assistant-ai`, `iat`, `nbf`, `exp` 5 minutes later, a `jti`. `ServiceTokenSigner` can sign it
if it takes the key, issuer and audience as parameters (see the diff in CHANGES-TO-EXISTING-FILES.md).

## 3. Store the conversations

The service is stateless, so the backend keeps the chat. Suggested tables in the `jh` schema:

**AssistantConversations**

| Column | Type | Notes |
|---|---|---|
| `Id` | uniqueidentifier PK | |
| `StudentId` | uniqueidentifier FK → Students | |
| `Title` | nvarchar(80) | Start of the first question, for the chat list |
| `StartedUtc`, `LastMessageUtc` | datetime2 | Index `(StudentId, LastMessageUtc)` for the list |

**AssistantMessages**

| Column | Type | Notes |
|---|---|---|
| `Id` | uniqueidentifier PK | |
| `ConversationId` | uniqueidentifier FK → AssistantConversations | Unique `(ConversationId, OrderIndex)` |
| `OrderIndex` | int | 1, 2, 3… |
| `Role` | nvarchar(30) | `Student` or `Assistant` |
| `Text` | nvarchar(2000) | Question 1–1000 characters, reply up to 2000 |
| `Source` | nvarchar(30) null | Replies: `Ai` or `Fallback` (the existing `ResultSource`) |
| `Topic` | nvarchar(30) null | Replies: the `topic` from the service, for reporting |
| `PromptVersion`, `ModelId` | nvarchar(60), nvarchar(80) null | From `meta` |
| `CreatedUtc` | datetime2 | |

Rules: a question and exactly one reply alternate; at most 200 messages per conversation (then start a new one).
Nothing cascades, as everywhere else.

## 4. Endpoints for the frontend

Suggested, all under `/api/v1` with the student's access token:

| Endpoint | Body / result |
|---|---|
| `POST /assistant/messages` | `{ "conversationId": null \| "<id>", "text": "..." }` → `{ conversationId, message, reply, suggestions, links, isFallback, canContinue }` |
| `GET /assistant/conversations` | The student's latest 20: `{ id, title, startedUtc, lastMessageUtc, messageCount }` |
| `GET /assistant/conversations/{id}` | `{ id, title, startedUtc, lastMessageUtc, messages: [{ id, orderIndex, role, text, createdUtc }], canContinue }` |

A conversation of another student is 404. Rate limit the POST per session, not per IP: a whole school class shares
one IP (the reference uses 20 per minute, keyed on the Authorization header because the limiter runs before
authentication in `Program.cs`).

## 5. Build the context

Read-only queries for the signed-in student, every call. Field by field (names in the JSON are snake_case):

| Context field | Source | Rule |
|---|---|---|
| `today` | `SchoolCalendar.Today` | Cairo date |
| `student.grade`, `is_independent`, `total_xp`, `last_active_date` | `Students` | |
| `student.streak_days` | `Student.CurrentStreak(today)` | 0 if a day was missed |
| `discovery` | Latest `DiscoveryInterviews` with `Status = Completed`, its `DiscoveryRecommendations` by `Rank` (+ `Tracks.Code`) | `status`: `Completed`, else `InProgress` if one is in progress, else `NotStarted` |
| `tracks[]` | `StudentTracks` with `Status = Active` + `Tracks` | `in_focus` = `Students.ActiveTrackId`; `lessons_done` / `lessons_total` over that track's `Lessons` and the student's `LessonProgress.CompletedUtc` |
| `exploration[]` | `TrackVideoViews` (completed = `CompletedUtc` set), `TrackQuizAttempts` (`Passed`, best `Score`), counts of `TrackVideos` and `TrackQuizQuestions` | Every track the student is learning or touched |
| `learning` | Track in focus: `Modules` → `Lessons` in order, `LessonProgress` | `next_lesson_id`: first unfinished lesson of `LessonPath.FromLevel(lessons, level)`; `in_path` false for lessons before it; `school_link` only for a `SchoolLesson` of the student's grade (BR-09); `null` with no track |
| `achievements.badges` | `StudentBadges` + `Badges`, newest first | |
| `achievements.recent_xp` | `XpTransactions`, newest 20 | |
| `squad` | `SquadMembers` → `Squads`, active `Sprints` with done/total `SquadTasks`, the student's own tasks | Teammates by **first name** and role; the student themself by role only. Confirm against BR-15 |
| `mentor` | `MentorAssignments` with `EndedUtc = null` + `Mentors` + `Tracks.Code` | Mentor names are fine: they are seeded profiles |
| `recruitment.applications` | `JobApplications` + `JobPostings` + `SimulationAttempts` (count, best `ScorePercent`) + `SimulationCertificates.CertificateCode` | |

Never send: full names, emails, phones, school or class of any student (teammates' first names only), parents, any `CorrectOptionIndex` or quiz options
(DR-11). Enums as text (`Beginner`, `ToDo`, `UIUX`), dates as ISO 8601, ids as GUID strings. The same JSON options as
`HttpDiscoveryAiClient` (snake_case, `JsonStringEnumConverter`) produce exactly this shape. `AssistantContextReader.cs`
in backend-reference does all of it in one round of queries.

## 6. Call the service

```
POST {BaseUrl}/v1/assistant/replies
Authorization: Bearer <service token>
X-Request-Id: <trace id>
Content-Type: application/json

{ "conversation_id", "student_ref", "message", "history": [{ "role": "student|assistant", "text" }], "context": { … } }
```

- `student_ref` is `Students.StudentRef`, never the student id.
- `history`: the conversation's last 20 messages before this question, oldest first.
- Timeout 20 s, no retry. On any non-200, timeout or exception: store the fallback reply with `Source = Fallback`
  and return `isFallback: true`. The reference fallback is
  "معلش، مش قادر أرد دلوقتي 🙏 جرّب تاني كمان شوية، ولحد ما أرجع تقدر تكمّل درسك من صفحة Courses."
- On 200 store `reply`, `topic`, `meta.prompt_version`, `meta.model_id`. Pass `suggestions` (tap-to-ask chips) and
  `links` to the frontend. Keep only links of a known `kind` whose `ref` is a GUID (`lesson`, `mentor`), an upper-case
  track code (`track`) or empty (`squad`, `discovery`, `achievements`, `jobs`).
- Map `topic` from snake_case (`my_progress`) to your enum (`MyProgress`); unknown values become null.

## 7. Test

Without the backend, with the service's mock students (`DEV_ENDPOINTS=true`):

```bash
curl http://localhost:8010/v1/dev/personas
curl -X POST http://localhost:8010/v1/dev/chat -H "Content-Type: application/json" \
  -d '{"persona": "frontend_beginner", "message": "الدرس الجاي إيه؟"}'
```

With a full request (`AUTH_DISABLED=true` locally, or a real token):

```bash
curl -X POST http://localhost:8010/v1/assistant/replies -H "Content-Type: application/json" \
  -d @docs/examples/reply-request.json
```

Checklist once connected:

- [ ] A question without `conversationId` creates a conversation; the next one with its id continues it.
- [ ] The service receives the last messages as `history`, oldest first.
- [ ] Stopping the service gives the fallback reply with `isFallback: true`, stored with `Source = Fallback`.
- [ ] A token signed with another key, or with audience `discovery-ai`, gets 401.
- [ ] The serialised context of a seeded student contains no student names, emails or `correct`.
- [ ] Another student's conversation id gives 404.
- [ ] Production refuses to start without the service URL and the signing key, like DiscoveryAi.
