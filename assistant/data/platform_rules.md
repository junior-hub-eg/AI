# Junior Hub platform rules

Facts the assistant may state about how Junior Hub works. Taken from the backend (BusinessRules.cs, XpOptions.cs,
README, handlers). Keep in sync when the backend changes. Each "## key" is one section the rules tool can return.

## xp
- XP is earned once per source; doing the same thing again gives no extra XP.
- Watching a track video to 90% or more: 5 XP (once per video).
- Passing a track's quiz for the first time: 10 XP.
- Passing a lesson (all quiz answers correct): 40 XP, plus the lesson's school-link badge if it has one.
- Moving your own squad task to Done: 20 XP (once per task).
- Passing a practice job interview (Simulation): 30 XP.
- Total XP is always the sum of everything earned.

## streak
- The streak counts days in a row with learning activity: watching a track video, taking a track quiz, finishing a lesson step or taking a lesson quiz.
- Learning on the day after your last active day adds 1. Missing a full day resets the streak; the next learning day starts it again at 1.
- Days follow Cairo time.

## discovery
- Track Discovery is a short AI interview (voice or typing) that recommends your top 3 tracks, each with a match % and your level (Beginner, Intermediate or Advanced).
- At most 10 questions. You can see your result after at least 5 answers; it also ends after 15 minutes.
- Three ways to start: "I know my track" (a quick check of your level in it; it comes first), "I have some ideas" (the normal interview), "I have no idea" (short fun challenges; every level is Beginner).
- You can start the interview again; the newest result is the one shown.
- Your voice is never stored.

## tracks
- There are 8 tracks: Mobile, Frontend, Backend, UI/UX, AI, Testing, Data, Gaming.
- Each track has intro videos and a 3-question quiz. The quiz unlocks after you finish at least one video of that track. You pass with 2 correct answers or more, and you can try again.
- You can learn several tracks at the same time, each at its own level. One track is "in focus": it is the one Courses opens. You can switch focus any time.
- A track chosen from the Discovery result starts at the level the interview gave; a track chosen without the interview starts at Beginner.
- Some tracks do not have lessons yet (only videos and the quiz). Today only Frontend has lessons.

## lessons
- Lessons are in modules. Your starting lesson depends on your level (in Frontend: Beginner starts at Variables, Intermediate at Conditions, Advanced at Functions with two inputs). Earlier lessons stay open if you want to review.
- A lesson has steps in order: School link (only when the lesson links to a lesson from your school grade), Video, Try it (run the starter code and get the expected output), Quiz, then Done.
- The lesson quiz is done when every answer is correct. You can retry it as many times as you need; wrong answers show a hint.
- "Try on Subject": some lessons link to something you studied at school (for example Math functions) and earn a badge.

## squad
- Interns work in squads on a school project in sprints. A student is in one squad at most; a squad has one active sprint.
- Tasks move on the board: To do, In progress, Review, Done. Only the student a task is assigned to can move it, one step forward or back at a time.
- Sprint progress is done tasks out of all tasks. The leaderboard shows the school's top 5 squads plus yours.

## mentor
- Mentors are professionals in a track. You have at most one mentor at a time; you can change mentor whenever you want, and the old one is kept in your history.
- The mentors list shows mentors of your track in focus by default; you can look at other tracks or all mentors.

## jobs
- Recruitment is a Simulation: practice jobs with fictional companies. They are never real jobs.
- Each practice job has a 5-question interview. You pass with 60% or more; if you do not pass you can try again.
- Passing gives a certificate with a code (like JH-SIM-4F7K2Q). The certificate says it is practice, not a job offer.

## account
- Sign in with your email and password. "Remember me" keeps you signed in for 7 days.
- Forgot your password: use "Forgot password" and the code sent to your email.
- After 5 wrong passwords the account is locked for 5 minutes.
- School students activate their account with the code or link from their school.
