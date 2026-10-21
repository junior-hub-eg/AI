using JuniorHub.Domain.Assistant;

namespace JuniorHub.Application.Assistant;

public interface IAssistantRepository
{
    /// <summary>The student's conversation with all its messages, tracked, or null (also when it is someone else's).</summary>
    Task<AssistantConversation?> GetAsync(Guid conversationId, Guid studentId, CancellationToken cancellationToken);

    /// <summary>The student's latest conversations, newest first.</summary>
    Task<IReadOnlyList<AssistantConversationSummary>> ListAsync(Guid studentId, int take, CancellationToken cancellationToken);

    void Add(AssistantConversation conversation);
}

public sealed record AssistantConversationSummary(Guid Id, string Title, DateTime StartedUtc, DateTime LastMessageUtc, int MessageCount);

/// <summary>Reads everything the assistant may know about a student, in one round of read-only queries.</summary>
public interface IAssistantContextReader
{
    /// <summary>The student's context, or null when there is no such student.</summary>
    Task<AssistantContext?> GetAsync(Guid studentId, CancellationToken cancellationToken);
}
