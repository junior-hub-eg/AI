namespace JuniorHub.Domain.Enums;

/// <summary>
/// What a student's question was about, as judged by the Assistant AI service (docs/assistant-ai-contract.md).
/// Stored with each reply for reporting. Wellbeing marks a reply to a student who said something worrying about themselves.
/// </summary>
public enum AssistantTopic
{
    MyProgress,
    Learning,
    Tracks,
    Discovery,
    Squad,
    Mentor,
    Jobs,
    Platform,
    ConceptHelp,
    SmallTalk,
    OutOfScope,
    Wellbeing,
}
