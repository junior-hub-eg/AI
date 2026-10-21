using JuniorHub.Domain.Common;
using JuniorHub.Domain.Enums;

namespace JuniorHub.Domain.Assistant;

/// <summary>
/// A chat between a student and the Junior Hub assistant. The backend owns it; the Assistant AI service keeps nothing
/// (docs/assistant-ai-contract.md). Messages alternate: a student message, then exactly one reply (from the AI service
/// or the prepared fallback). Messages are changed only through this class.
/// </summary>
public sealed class AssistantConversation : Entity
{
    /// <summary>100 questions and their replies. A longer chat starts a new conversation.</summary>
    public const int MaxMessages = 200;
    public const int MaxStudentTextLength = 1000;
    public const int MaxReplyLength = 2000;
    public const int MaxTitleLength = 80;

    private readonly List<AssistantMessage> _messages = [];

    private AssistantConversation() { }

    public AssistantConversation(Guid studentId, DateTime startedUtc)
    {
        StudentId = studentId;
        StartedUtc = startedUtc;
        LastMessageUtc = startedUtc;
    }

    public Guid StudentId { get; private set; }

    /// <summary>The start of the first question, shown in the list of conversations.</summary>
    public string Title { get; private set; } = "";
    public DateTime StartedUtc { get; private set; }
    public DateTime LastMessageUtc { get; private set; }

    public IReadOnlyList<AssistantMessage> Messages => _messages;

    /// <summary>By order index, because rows loaded from the database have no guaranteed order.</summary>
    public IReadOnlyList<AssistantMessage> InOrder => _messages.OrderBy(m => m.OrderIndex).ToList();

    public AssistantMessage? Last => _messages.MaxBy(m => m.OrderIndex);

    /// <summary>True when there is no room for one more question and its reply.</summary>
    public bool IsFull => _messages.Count + 2 > MaxMessages;

    public AssistantMessage AddStudentMessage(string text, DateTime nowUtc)
    {
        text = (text ?? "").Trim();
        if (text.Length == 0) throw new DomainException("EMPTY_MESSAGE", "The message is empty.");
        if (text.Length > MaxStudentTextLength)
            throw new DomainException("MESSAGE_TOO_LONG", $"Keep your message under {MaxStudentTextLength} characters.");
        if (IsFull) throw new DomainException("CONVERSATION_FULL", "This chat is full. Start a new one.");
        if (Last is { Role: AssistantRole.Student })
            throw new DomainException("REPLY_PENDING", "The previous message has not been answered yet.");

        if (Title.Length == 0) Title = text.Length <= MaxTitleLength ? text : text[..(MaxTitleLength - 1)].TrimEnd() + "…";
        return Add(new AssistantMessage(Id, NextIndex, AssistantRole.Student, text, null, null, null, null, nowUtc));
    }

    /// <summary>The reply to the last student message. A reply longer than the limit is cut.</summary>
    public AssistantMessage AddReply(
        string text, ResultSource source, AssistantTopic? topic, string? promptVersion, string? modelId, DateTime nowUtc)
    {
        text = (text ?? "").Trim();
        if (text.Length == 0) throw new DomainException("EMPTY_REPLY", "The reply is empty.");
        if (Last is not { Role: AssistantRole.Student })
            throw new DomainException("NOTHING_TO_ANSWER", "There is no student message to answer.");
        if (text.Length > MaxReplyLength) text = text[..(MaxReplyLength - 1)].TrimEnd() + "…";

        return Add(new AssistantMessage(Id, NextIndex, AssistantRole.Assistant, text, source, topic, promptVersion, modelId, nowUtc));
    }

    /// <summary>The latest messages, oldest first: what is sent to the AI service as history.</summary>
    public IReadOnlyList<AssistantMessage> Recent(int count) =>
        _messages.OrderByDescending(m => m.OrderIndex).Take(Math.Max(0, count)).OrderBy(m => m.OrderIndex).ToList();

    private int NextIndex => (Last?.OrderIndex ?? 0) + 1;

    private AssistantMessage Add(AssistantMessage message)
    {
        _messages.Add(message);
        LastMessageUtc = message.CreatedUtc;
        return message;
    }
}
