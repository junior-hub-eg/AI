# Backend changes: student profile

The assistant now reads the student's first name, gender and join date (tool `get_my_profile`, and the snapshot it
greets from). The service already accepts these fields; until the backend sends them, the bot simply does not know the
name, as before. The reply language needs no backend change: the bot answers in the language of the student's message.

Written against `prod` as of 22 Oct 2026. Not compiled: treat it as a starting point.

## 1. `src/JuniorHub.Application/Assistant/IAssistantAiClient.cs`

New fields go last with defaults, so the existing calls keep compiling.

```diff
-public sealed record AssistantStudentFacts(int? Grade, bool IsIndependent, int TotalXp, int StreakDays, DateOnly? LastActiveDate);
+/// <param name="FirstName">The first name only, never the full name.</param>
+public sealed record AssistantStudentFacts(
+    int? Grade, bool IsIndependent, int TotalXp, int StreakDays, DateOnly? LastActiveDate,
+    string? FirstName = null, Gender? Gender = null, DateOnly? MemberSince = null);
```

Serialized with the existing options (snake_case, enums as text) this becomes
`"student": { "first_name": "Omar", "gender": "Male", "member_since": "2026-10-10", ... }`.

## 2. `src/JuniorHub.Infrastructure/Persistence/Repositories/AssistantContextReader.cs`

```diff
-        var student = await db.Students.AsNoTracking().SingleOrDefaultAsync(s => s.Id == studentId, cancellationToken);
+        var student = await db.Students.AsNoTracking().Include(s => s.User)
+            .SingleOrDefaultAsync(s => s.Id == studentId, cancellationToken);
```

```diff
-            new AssistantStudentFacts(student.Grade, student.IsIndependent, student.TotalXp, student.CurrentStreak(today), student.LastActiveDate),
+            new AssistantStudentFacts(student.Grade, student.IsIndependent, student.TotalXp, student.CurrentStreak(today), student.LastActiveDate,
+                Names.FirstName(student.User.FullName), student.Gender, DateOnly.FromDateTime(student.User.CreatedUtc)),
```

Nothing else about the student leaves: no full name, email, phone, school, class or photo.

## Checks

- [ ] The serialized `context` of a seeded student has `first_name` (one word), `gender` and `member_since`, and still
      no full name, email, school or `correct`.
- [ ] Product confirms sending the student's first name (beyond BR-15 as written, like teammates' first names).
