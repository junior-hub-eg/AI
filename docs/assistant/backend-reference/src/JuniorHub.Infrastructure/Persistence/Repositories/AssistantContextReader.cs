using JuniorHub.Application.Assistant;
using JuniorHub.Application.Common;
using JuniorHub.Domain.Enums;
using JuniorHub.Domain.Learning;
using Microsoft.EntityFrameworkCore;

namespace JuniorHub.Infrastructure.Persistence.Repositories;

/// <summary>
/// Read-only queries for the assistant's context (docs/assistant-ai-contract.md). Nothing is tracked or changed.
/// Only what the student may see about themselves leaves here: teammates by first name only, no quiz answers.
/// </summary>
internal sealed class AssistantContextReader(JuniorHubDbContext db, TimeProvider clock) : IAssistantContextReader
{
    public const int RecentXpCount = 20;

    public async Task<AssistantContext?> GetAsync(Guid studentId, CancellationToken cancellationToken)
    {
        var student = await db.Students.AsNoTracking().SingleOrDefaultAsync(s => s.Id == studentId, cancellationToken);
        if (student is null) return null;
        var today = SchoolCalendar.Today(clock);

        // Tracks and lessons ----------------------------------------------------------------------------------------
        var studentTracks = await db.StudentTracks.AsNoTracking()
            .Where(t => t.StudentId == studentId && t.Status == StudentTrackStatus.Active)
            .OrderBy(t => t.SelectedUtc)
            .Select(t => new TrackRow(t.TrackId, t.Track.Code, t.Track.Name, t.Level, t.Source, t.SelectedUtc))
            .ToListAsync(cancellationToken);
        var trackIds = studentTracks.Select(t => t.TrackId).ToList();

        var lessons = await db.Lessons.AsNoTracking()
            .Where(l => trackIds.Contains(l.Module.TrackId))
            .OrderBy(l => l.Module.SortOrder).ThenBy(l => l.SortOrder)
            .Select(l => new LessonRow(
                l.Id, l.Module.TrackId, l.Module.Title, l.Title, l.Concept, l.Level,
                // BR-09: only a link to a school lesson of the student's grade counts.
                l.Links.Where(k => k.SchoolLesson.Grade == student.Grade)
                    .Select(k => new AssistantSchoolLinkFacts(k.SchoolLesson.Subject, k.SchoolLesson.Title))
                    .FirstOrDefault()))
            .ToListAsync(cancellationToken);

        var progress = await db.LessonProgress.AsNoTracking()
            .Where(p => p.StudentId == studentId)
            .Select(p => new ProgressRow(p.LessonId, p.CurrentStep, p.QuizAttempts, p.CompletedUtc != null))
            .ToDictionaryAsync(p => p.LessonId, cancellationToken);

        var focus = studentTracks.FirstOrDefault(t => t.TrackId == student.ActiveTrackId) ?? studentTracks.FirstOrDefault();
        var tracks = studentTracks
            .Select(t =>
            {
                var ofTrack = lessons.Where(l => l.TrackId == t.TrackId).ToList();
                return new AssistantTrackFacts(t.Code, t.Name, t.Level, t.Source, t == focus, t.SelectedUtc,
                    ofTrack.Count(l => progress.TryGetValue(l.Id, out var p) && p.Done), ofTrack.Count);
            })
            .ToList();

        AssistantLearningFacts? learning = null;
        if (focus is not null)
        {
            var ofTrack = lessons.Where(l => l.TrackId == focus.TrackId).ToList();
            var path = LessonPath.FromLevel(ofTrack, l => l.Level, focus.Level);
            var inPath = path.Select(l => l.Id).ToHashSet();
            var next = path.FirstOrDefault(l => !(progress.TryGetValue(l.Id, out var p) && p.Done));
            learning = new AssistantLearningFacts(focus.Code, next?.Id, ofTrack.Select(l =>
            {
                var p = progress.GetValueOrDefault(l.Id);
                return new AssistantLessonFacts(
                    l.Id, l.Module, l.Title, l.Concept, l.Level,
                    p is null ? "NotStarted" : p.Done ? "Done" : "InProgress",
                    p?.CurrentStep, p?.QuizAttempts ?? 0, inPath.Contains(l.Id), l.SchoolLink);
            }).ToList());
        }

        // Track videos and quizzes ----------------------------------------------------------------------------------
        var views = await db.TrackVideoViews.AsNoTracking()
            .Where(v => v.StudentId == studentId)
            .Select(v => new { v.TrackVideo.TrackId, Completed = v.CompletedUtc != null })
            .ToListAsync(cancellationToken);
        var attempts = await db.TrackQuizAttempts.AsNoTracking()
            .Where(a => a.StudentId == studentId)
            .Select(a => new { a.TrackId, a.Score, a.Passed })
            .ToListAsync(cancellationToken);
        var touched = trackIds.Concat(views.Select(v => v.TrackId)).Concat(attempts.Select(a => a.TrackId)).Distinct().ToList();
        var touchedTracks = await db.Tracks.AsNoTracking()
            .Where(t => touched.Contains(t.Id))
            .OrderBy(t => t.SortOrder)
            .Select(t => new { t.Id, t.Code, Videos = t.Videos.Count(), Questions = t.QuizQuestions.Count() })
            .ToListAsync(cancellationToken);
        var exploration = touchedTracks
            .Select(t => new AssistantExplorationFacts(
                t.Code,
                views.Count(v => v.TrackId == t.Id && v.Completed),
                t.Videos,
                attempts.Any(a => a.TrackId == t.Id && a.Passed),
                attempts.Where(a => a.TrackId == t.Id).Select(a => (int?)a.Score).Max(),
                t.Questions))
            .ToList();

        // Discovery -------------------------------------------------------------------------------------------------
        var latest = await db.DiscoveryInterviews.AsNoTracking()
            .Where(i => i.StudentId == studentId && i.Status == InterviewStatus.Completed)
            .OrderByDescending(i => i.CompletedUtc)
            .Select(i => new
            {
                i.Path,
                i.CompletedUtc,
                i.AiSummary,
                Recommendations = i.Recommendations.OrderBy(r => r.Rank)
                    .Select(r => new AssistantRecommendationFacts(r.Rank, r.Track.Code, r.MatchPercent, r.Reason, r.Level, r.LevelReason))
                    .ToList(),
            })
            .FirstOrDefaultAsync(cancellationToken);
        var inProgress = latest is null && await db.DiscoveryInterviews.AsNoTracking()
            .AnyAsync(i => i.StudentId == studentId && i.Status == InterviewStatus.InProgress, cancellationToken);
        var discovery = latest is not null
            ? new AssistantDiscoveryFacts("Completed", latest.Path, latest.CompletedUtc, latest.AiSummary, latest.Recommendations)
            : new AssistantDiscoveryFacts(inProgress ? "InProgress" : "NotStarted", null, null, null, []);

        // XP and badges ---------------------------------------------------------------------------------------------
        var badges = await db.StudentBadges.AsNoTracking()
            .Where(b => b.StudentId == studentId)
            .OrderByDescending(b => b.EarnedUtc)
            .Select(b => new AssistantBadgeFacts(b.Badge.Code, b.Badge.Name, b.Badge.Type, b.EarnedUtc))
            .ToListAsync(cancellationToken);
        var recentXp = await db.XpTransactions.AsNoTracking()
            .Where(x => x.StudentId == studentId)
            .OrderByDescending(x => x.CreatedUtc)
            .Take(RecentXpCount)
            .Select(x => new AssistantXpFacts(x.Reason, x.Points, x.CreatedUtc))
            .ToListAsync(cancellationToken);

        // Squad, mentor, practice jobs ------------------------------------------------------------------------------
        var squad = await ReadSquadAsync(studentId, cancellationToken);

        var mentor = await db.MentorAssignments.AsNoTracking()
            .Where(a => a.StudentId == studentId && a.EndedUtc == null)
            .Select(a => new AssistantMentorFacts(
                a.Mentor.Id, a.Mentor.FullName, a.Mentor.Title, a.Mentor.Track.Code, a.Mentor.Languages, a.Mentor.Availability, a.StartedUtc))
            .FirstOrDefaultAsync(cancellationToken);

        var applications = await db.JobApplications.AsNoTracking()
            .Where(a => a.StudentId == studentId)
            .OrderByDescending(a => a.AppliedUtc)
            .Select(a => new AssistantApplicationFacts(
                a.JobPosting.Role, a.JobPosting.CompanyName, a.JobPosting.Track.Code, a.JobPosting.Level, a.Status,
                a.Attempts.Count(),
                a.Attempts.Max(t => (int?)t.ScorePercent),
                a.Attempts.Where(t => t.Certificate != null).Select(t => t.Certificate!.CertificateCode).FirstOrDefault()))
            .ToListAsync(cancellationToken);

        return new AssistantContext(
            today,
            new AssistantStudentFacts(student.Grade, student.IsIndependent, student.TotalXp, student.CurrentStreak(today), student.LastActiveDate),
            discovery,
            tracks,
            exploration,
            learning,
            new AssistantAchievementFacts(badges, recentXp),
            squad,
            mentor,
            new AssistantRecruitmentFacts(applications));
    }

    private async Task<AssistantSquadFacts?> ReadSquadAsync(Guid studentId, CancellationToken cancellationToken)
    {
        var membership = await db.SquadMembers.AsNoTracking()
            .Where(m => m.StudentId == studentId)
            .Select(m => new { m.SquadId, m.Role, m.Squad.Name, m.Squad.ProjectTitle, m.Squad.ProjectDescription })
            .FirstOrDefaultAsync(cancellationToken);
        if (membership is null) return null;

        // Teammates by first name only; the student themself by role only.
        var rows = await db.SquadMembers.AsNoTracking()
            .Where(m => m.SquadId == membership.SquadId)
            .OrderBy(m => m.JoinedUtc)
            .Select(m => new { m.Role, IsMe = m.StudentId == studentId, m.Student.User.FullName })
            .ToListAsync(cancellationToken);
        var members = rows
            .Select(m => new AssistantSquadMemberFacts(m.Role, m.IsMe, m.IsMe ? null : m.FullName.Split(' ', 2)[0]))
            .ToList();

        var sprint = await db.Sprints.AsNoTracking()
            .Where(s => s.SquadId == membership.SquadId && s.Status == SprintStatus.Active)
            .Select(s => new
            {
                s.Id,
                Facts = new AssistantSprintFacts(s.Name, s.StartDate, s.EndDate, s.Status,
                    s.Tasks.Count(t => t.Status == SquadTaskStatus.Done), s.Tasks.Count()),
            })
            .FirstOrDefaultAsync(cancellationToken);

        List<AssistantTaskFacts> myTasks = sprint is null
            ? []
            : await db.SquadTasks.AsNoTracking()
                .Where(t => t.SprintId == sprint.Id && t.AssigneeStudentId == studentId)
                .OrderBy(t => t.SortOrder)
                .Select(t => new AssistantTaskFacts(t.Title, t.Status, t.StoryPoints))
                .ToListAsync(cancellationToken);

        return new AssistantSquadFacts(membership.Name, membership.ProjectTitle, membership.ProjectDescription, membership.Role,
            members, sprint?.Facts, myTasks);
    }

    private sealed record TrackRow(Guid TrackId, string Code, string Name, TrackLevel Level, TrackChoiceSource Source, DateTime SelectedUtc);

    private sealed record LessonRow(
        Guid Id, Guid TrackId, string Module, string Title, string Concept, TrackLevel Level, AssistantSchoolLinkFacts? SchoolLink);

    private sealed record ProgressRow(Guid LessonId, LessonStep CurrentStep, int QuizAttempts, bool Done);
}
