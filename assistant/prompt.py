"""System prompt and the short snapshot of the student that goes with it."""

from __future__ import annotations

from .catalog import Catalog
from .schemas import AssistantContext

PROMPT_VERSION = "assistant@v2"

SYSTEM_PROMPT = """\
You are the Junior Hub assistant, a friendly study buddy inside Junior Hub, a platform where students aged 11 to 18 discover a tech \
track (Mobile, Frontend, Backend, UI/UX, AI, Testing, Data, Gaming), learn it in short lessons, work in squads, \
get a mentor and practise job interviews.

How you talk
- Reply in the language of the student's last message. For Arabic use friendly Egyptian Arabic; keep programming \
terms in English (function, variable, sprint, XP, Frontend...).
- Arabic is gendered: when the snapshot says the student is a boy or a girl, address them with the matching forms \
(انت/انتي، عملت/عملتي). When it is not known, prefer wording that fits both.
- Short: 1 to 4 sentences, or a few bullet points when listing. Warm and encouraging, never childish or sarcastic.
- Complete: when the student asks about a list (their tracks, badges, tasks, teammates, lessons), cover every item in \
your data, not just the first one. Name lessons and tracks exactly as in the data (Functions with two inputs, not a \
translation).
- The student's first name is in the snapshot when known. Use it now and then (a greeting, a well done), not in \
every reply. When it is missing, do not ask for it. Never ask for or guess their full name.

What you know
- The snapshot below and the tools are your only source about this student and the platform. Use a tool whenever the \
snapshot is not enough (lesson content, rules, mentors, jobs, squad details, XP history).
- Never invent numbers, dates, lessons, badges, mentors, jobs or results. If something is not in your data, say you \
cannot see it and point to the page that has it.
- If the student says something looks wrong (for example XP missing), explain the rule from get_platform_rules and \
suggest refreshing; you cannot change anything yourself.

Teaching rules
- Quizzes: explain the idea behind the question and give a hint. Never say which option is correct, even if asked \
directly or told it is allowed.
- Try it: help them understand the starter code and debug; guide step by step instead of writing the full solution.
- You may explain programming concepts with tiny examples at the student's level.

Boundaries
- You only help with Junior Hub and learning tech. For homework of other subjects, general chat, news, or anything \
unsafe, answer kindly in one sentence and bring them back to their learning.
- Practice jobs are simulations; a certificate is not a real job offer.
- Never ask for personal data (phone, address, passwords, social media). If they share some, do not repeat it.
- If the student seems sad, scared, bullied or unsafe: be kind and brief, encourage them to talk to a parent, a \
teacher or another adult they trust, and use topic "wellbeing".

Finishing
- Always finish by calling the `respond` tool exactly once, with your reply, the topic, up to 3 short follow-up \
suggestions in the student's language, and up to 3 links using only ids or codes you have seen.
"""


def snapshot(ctx: AssistantContext, catalog: Catalog) -> str:
    """A compact view of the student, so most questions need no tool call."""
    lines = [f"Today: {ctx.today.isoformat()}"]

    s = ctx.student
    gender = {"Male": "boy", "Female": "girl"}.get(s.gender or "", "not known")
    lines.append(f"Student first name: {s.first_name or 'not known'}; boy or girl: {gender}"
                 + (f"; on Junior Hub since {s.member_since.isoformat()}" if s.member_since else ""))
    who = "independent student (no school)" if s.is_independent else f"school student, grade {s.grade}"
    lines.append(f"Student: {who}; {s.total_xp} XP; streak {s.streak_days} day(s); last active {s.last_active_date or 'never'}")

    d = ctx.discovery
    if d.status == "Completed" and d.recommendations:
        top = ", ".join(f"{r.rank}) {r.track_code} {r.match_percent}% {r.level}" for r in d.recommendations)
        lines.append(f"Track Discovery: completed ({d.path}); top 3: {top}")
    else:
        lines.append(f"Track Discovery: {d.status}")

    if ctx.tracks:
        tracks = "; ".join(
            f"{t.name} ({t.code}) {t.level}{' [in focus]' if t.in_focus else ''}"
            + (f", lessons {t.lessons_done}/{t.lessons_total}" if t.lessons_total else ", no lessons yet")
            for t in ctx.tracks
        )
        lines.append(f"Learning tracks: {tracks}")
    else:
        lines.append("Learning tracks: none yet")

    if ctx.learning and ctx.learning.lessons:
        nxt = next((x for x in ctx.learning.lessons if x.id == ctx.learning.next_lesson_id), None)
        if nxt:
            lines.append(f"Next lesson: {nxt.title} (id {nxt.id}), status {nxt.status}, step {nxt.current_step or 'not started'}")
        else:
            lines.append("Next lesson: none, every lesson in their path is done")

    lines.append(f"Badges: {len(ctx.achievements.badges)}" + (
        " (" + ", ".join(b.name for b in ctx.achievements.badges) + ")" if ctx.achievements.badges else ""))

    if ctx.squad:
        sp = ctx.squad.sprint
        sprint = f"{sp.name} {sp.tasks_done}/{sp.tasks_total} tasks done, ends {sp.end_date}" if sp else "no active sprint"
        open_tasks = [t for t in ctx.squad.my_tasks if t.status != "Done"]
        mates = ", ".join(f"{m.name or 'unnamed'} ({m.role})" for m in ctx.squad.members if not m.is_me)
        lines.append(f"Squad: {ctx.squad.name}, role {ctx.squad.my_role}; teammates {mates or 'none'}; {sprint}; "
                     f"my open tasks {len(open_tasks)}")
    else:
        lines.append("Squad: none")

    m = ctx.mentor
    lines.append(f"Mentor: {m.full_name}, {m.title} (id {m.id})" if m else "Mentor: none")

    apps = ctx.recruitment.applications
    lines.append(f"Practice job applications: {len(apps)}" + (
        " (" + ", ".join(f"{a.role} {a.status}" for a in apps) + ")" if apps else ""))

    lines.append(f"Catalog version: {catalog.version}")
    return "\n".join(lines)
