using JuniorHub.Application.Common;
using JuniorHub.Domain.Assistant;

namespace JuniorHub.Application.Assistant;

/// <summary>Student assistant settings, in the "Assistant" section.</summary>
public sealed class AssistantOptions
{
    public const string SectionName = "Assistant";

    /// <summary>How many earlier messages are sent to the AI service with each question.</summary>
    public int HistoryMessages { get; init; } = 20;

    /// <summary>How many conversations the list returns.</summary>
    public int ConversationsListed { get; init; } = 20;

    /// <summary>Stored and shown when the AI service fails or is slow. No automatic retry.</summary>
    public string FallbackReply { get; init; } =
        "معلش، مش قادر أرد دلوقتي 🙏 جرّب تاني كمان شوية، ولحد ما أرجع تقدر تكمّل درسك من صفحة Courses.";
}

/// <summary>A question. Without <see cref="ConversationId"/> a new conversation starts.</summary>
public sealed record SendAssistantMessageRequest(Guid? ConversationId, string? Text);

/// <param name="Role">Student or Assistant.</param>
public sealed record AssistantMessageDto(Guid Id, int OrderIndex, string Role, string Text, DateTime CreatedUtc);

/// <summary>
/// The stored question and its reply. <see cref="IsFallback"/>: the AI service did not answer and the prepared reply
/// was used. <see cref="CanContinue"/>: false when the conversation is full and a new one must be started.
/// </summary>
public sealed record AssistantReplyResponse(
    Guid ConversationId, AssistantMessageDto Message, AssistantMessageDto Reply, IReadOnlyList<string> Suggestions,
    IReadOnlyList<AssistantLink> Links, bool IsFallback, bool CanContinue);

public sealed record AssistantConversationSummaryDto(Guid Id, string Title, DateTime StartedUtc, DateTime LastMessageUtc, int MessageCount);

public sealed record AssistantConversationDto(
    Guid Id, string Title, DateTime StartedUtc, DateTime LastMessageUtc, IReadOnlyList<AssistantMessageDto> Messages, bool CanContinue);

public static class AssistantErrors
{
    public static readonly Error NotFound = new("CONVERSATION_NOT_FOUND", "We could not find this chat.", ErrorType.NotFound);
    public static readonly Error Full = new("CONVERSATION_FULL", "This chat is full. Start a new one.", ErrorType.Conflict);
}

internal static class AssistantViews
{
    public static AssistantMessageDto Message(AssistantMessage m) => new(m.Id, m.OrderIndex, m.Role.ToString(), m.Text, m.CreatedUtc);
}
