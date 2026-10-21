using JuniorHub.Domain.Common;
using JuniorHub.Domain.Enums;

namespace JuniorHub.Domain.Assistant;

/// <summary>One message of an assistant conversation. Created by <see cref="AssistantConversation"/>; never changed.</summary>
public sealed class AssistantMessage : Entity
{
    private AssistantMessage() { }

    internal AssistantMessage(
        Guid conversationId, int orderIndex, AssistantRole role, string text, ResultSource? source, AssistantTopic? topic,
        string? promptVersion, string? modelId, DateTime createdUtc)
    {
        ConversationId = conversationId;
        OrderIndex = orderIndex;
        Role = role;
        Text = text;
        Source = source;
        Topic = topic;
        PromptVersion = promptVersion;
        ModelId = modelId;
        CreatedUtc = createdUtc;
    }

    public Guid ConversationId { get; private set; }

    /// <summary>1, 2, 3… without gaps within a conversation.</summary>
    public int OrderIndex { get; private set; }
    public AssistantRole Role { get; private set; }
    public string Text { get; private set; } = "";

    /// <summary>Replies only: the AI service, or the prepared fallback when the service failed.</summary>
    public ResultSource? Source { get; private set; }

    /// <summary>Replies from the AI service only.</summary>
    public AssistantTopic? Topic { get; private set; }
    public string? PromptVersion { get; private set; }
    public string? ModelId { get; private set; }
    public DateTime CreatedUtc { get; private set; }
}
