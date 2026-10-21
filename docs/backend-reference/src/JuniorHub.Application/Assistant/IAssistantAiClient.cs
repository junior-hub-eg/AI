using JuniorHub.Application.Discovery;
using JuniorHub.Domain.Enums;

namespace JuniorHub.Application.Assistant;

/// <summary>
/// The Assistant AI service (docs/assistant-ai-contract.md). Stateless: every call carries the history and the student's
/// context. Failures and timeouts come back as a failed result, never as an exception, so the chat can fall back.
/// </summary>
public interface IAssistantAiClient
{
    Task<AiCallResult<AssistantAiReply>> ReplyAsync(AssistantAiRequest request, CancellationToken cancellationToken);
}

/// <summary>One question. The student is only <see cref="StudentRef"/>: no name, email or school (BR-15).</summary>
/// <param name="History">The messages before <see cref="Message"/>, oldest first.</param>
public sealed record AssistantAiRequest(
    Guid ConversationId, Guid StudentRef, string Message, IReadOnlyList<AssistantAiHistoryItem> History, AssistantContext Context);

public sealed record AssistantAiHistoryItem(AssistantRole Role, string Text);

/// <param name="Topic">Null when the service sent a topic this backend does not know.</param>
public sealed record AssistantAiReply(
    string Reply, IReadOnlyList<string> Suggestions, IReadOnlyList<AssistantLink> Links, AssistantTopic? Topic,
    string? PromptVersion, string? ModelId);

/// <summary>A page the reply points to. Kind: lesson, track, mentor, squad, discovery, achievements or jobs.</summary>
/// <param name="Ref">Lesson id, track code or mentor id; empty for the pages without one.</param>
public sealed record AssistantLink(string Kind, string Ref, string Label);

// ----- The student's data sent with every question (docs/assistant-ai-contract.md, "AssistantContext") ------------
// Only what the student may see about themselves. No name, email, school, class or parent; teammates by first name only,
// and never a quiz's correct answer (DR-11).

public sealed record AssistantContext(
    DateOnly Today,
    AssistantStudentFacts Student,
    AssistantDiscoveryFacts Discovery,
    IReadOnlyList<AssistantTrackFacts> Tracks,
    IReadOnlyList<AssistantExplorationFacts> Exploration,
    AssistantLearningFacts? Learning,
    AssistantAchievementFacts Achievements,
    AssistantSquadFacts? Squad,
    AssistantMentorFacts? Mentor,
    AssistantRecruitmentFacts Recruitment);

public sealed record AssistantStudentFacts(int? Grade, bool IsIndependent, int TotalXp, int StreakDays, DateOnly? LastActiveDate);

/// <param name="Status">NotStarted, InProgress or Completed. A completed result is shown even if a newer interview is in progress.</param>
public sealed record AssistantDiscoveryFacts(
    string Status, DiscoveryPath? Path, DateTime? CompletedUtc, string? Summary, IReadOnlyList<AssistantRecommendationFacts> Recommendations);

public sealed record AssistantRecommendationFacts(int Rank, string TrackCode, int MatchPercent, string Reason, TrackLevel Level, string LevelReason);

public sealed record AssistantTrackFacts(
    string Code, string Name, TrackLevel Level, TrackChoiceSource Source, bool InFocus, DateTime SelectedUtc, int LessonsDone, int LessonsTotal);

/// <summary>The track's intro videos and quiz, for every track the student has touched.</summary>
public sealed record AssistantExplorationFacts(
    string TrackCode, int VideosCompleted, int VideosTotal, bool QuizPassed, int? BestQuizScore, int QuizTotal);

/// <summary>The lessons of the track in focus.</summary>
public sealed record AssistantLearningFacts(string TrackCode, Guid? NextLessonId, IReadOnlyList<AssistantLessonFacts> Lessons);

/// <param name="Status">NotStarted, InProgress or Done.</param>
/// <param name="InPath">False for lessons below the student's starting level: open, but not where they are sent next.</param>
public sealed record AssistantLessonFacts(
    Guid Id, string Module, string Title, string Concept, TrackLevel Level, string Status, LessonStep? CurrentStep, int QuizAttempts,
    bool InPath, AssistantSchoolLinkFacts? SchoolLink);

public sealed record AssistantSchoolLinkFacts(SchoolSubject Subject, string Title);

public sealed record AssistantAchievementFacts(IReadOnlyList<AssistantBadgeFacts> Badges, IReadOnlyList<AssistantXpFacts> RecentXp);

public sealed record AssistantBadgeFacts(string Code, string Name, BadgeType Type, DateTime EarnedUtc);

public sealed record AssistantXpFacts(XpReason Reason, int Points, DateTime CreatedUtc);

/// <summary>The student's squad. Teammates by first name and role; the student by role only.</summary>
public sealed record AssistantSquadFacts(
    string Name, string ProjectTitle, string ProjectDescription, SquadRole MyRole, IReadOnlyList<AssistantSquadMemberFacts> Members,
    AssistantSprintFacts? Sprint, IReadOnlyList<AssistantTaskFacts> MyTasks);

/// <param name="Name">A teammate's first name; null for the student themself.</param>
public sealed record AssistantSquadMemberFacts(SquadRole Role, bool IsMe, string? Name);

public sealed record AssistantSprintFacts(string Name, DateOnly StartDate, DateOnly EndDate, SprintStatus Status, int TasksDone, int TasksTotal);

public sealed record AssistantTaskFacts(string Title, SquadTaskStatus Status, int StoryPoints);

/// <summary>The current mentor. Mentors are seeded profiles, not students, so their names may be sent.</summary>
public sealed record AssistantMentorFacts(
    Guid Id, string FullName, string Title, string TrackCode, string Languages, string Availability, DateTime StartedUtc);

public sealed record AssistantRecruitmentFacts(IReadOnlyList<AssistantApplicationFacts> Applications);

public sealed record AssistantApplicationFacts(
    string Role, string CompanyName, string TrackCode, JobLevel Level, ApplicationStatus Status, int Attempts, int? BestScorePercent,
    string? CertificateCode);
