using JuniorHub.Application.Abstractions;
using JuniorHub.Application.Common;
using JuniorHub.Application.Students;
using JuniorHub.Domain.Assistant;
using JuniorHub.Domain.Enums;
using Microsoft.Extensions.Options;

namespace JuniorHub.Application.Assistant;

/// <summary>
/// Ask the assistant: stores the question, sends it with the recent history and the student's context to the Assistant AI
/// service, and stores the reply (or the prepared fallback when the service fails). Starts a conversation when none is given.
/// </summary>
public sealed class SendAssistantMessageHandler(
    ICurrentStudent currentStudent,
    IStudentRepository students,
    IAssistantRepository conversations,
    IAssistantContextReader contextReader,
    IAssistantAiClient ai,
    IUnitOfWork unitOfWork,
    IOptions<AssistantOptions> options,
    TimeProvider clock)
{
    private static readonly HashSet<string> PageKinds = ["squad", "discovery", "achievements", "jobs"];
    private const int MaxSuggestions = 3;
    private const int MaxSuggestionLength = 80;
    private const int MaxLinks = 3;

    public async Task<Result<AssistantReplyResponse>> HandleAsync(SendAssistantMessageRequest request, CancellationToken cancellationToken)
    {
        var text = request.Text?.Trim() ?? "";
        if (text.Length == 0)
            return Error.Validation(new Dictionary<string, string[]> { ["text"] = ["Write your question first."] });
        if (text.Length > AssistantConversation.MaxStudentTextLength)
            return Error.Validation(new Dictionary<string, string[]>
            {
                ["text"] = [$"Keep your message under {AssistantConversation.MaxStudentTextLength} characters."],
            });

        var student = await students.GetWithUserAndSchoolAsync(currentStudent.Id, cancellationToken);
        if (student is null) return StudentErrors.NotFound;

        var now = clock.GetUtcNow().UtcDateTime;
        AssistantConversation conversation;
        if (request.ConversationId is { } id)
        {
            var existing = await conversations.GetAsync(id, student.Id, cancellationToken);
            if (existing is null) return AssistantErrors.NotFound;
            if (existing.IsFull) return AssistantErrors.Full;
            conversation = existing;
        }
        else
        {
            conversation = new AssistantConversation(student.Id, now);
            conversations.Add(conversation);
        }

        var settings = options.Value;
        var history = conversation.Recent(settings.HistoryMessages)
            .Select(m => new AssistantAiHistoryItem(m.Role, m.Text))
            .ToList();
        var context = (await contextReader.GetAsync(student.Id, cancellationToken))!;

        var question = conversation.AddStudentMessage(text, now);
        var call = await ai.ReplyAsync(
            new AssistantAiRequest(conversation.Id, student.StudentRef, question.Text, history, context), cancellationToken);

        var answer = call.Value is { Reply: { Length: > 0 } replyText } value && !string.IsNullOrWhiteSpace(replyText) ? value : null;
        var replyAt = clock.GetUtcNow().UtcDateTime;
        var reply = answer is not null
            ? conversation.AddReply(answer.Reply, ResultSource.Ai, answer.Topic, answer.PromptVersion, answer.ModelId, replyAt)
            : conversation.AddReply(settings.FallbackReply, ResultSource.Fallback, null, null, null, replyAt);

        await unitOfWork.SaveChangesAsync(cancellationToken);

        return new AssistantReplyResponse(
            conversation.Id,
            AssistantViews.Message(question),
            AssistantViews.Message(reply),
            answer is null ? [] : CleanSuggestions(answer.Suggestions),
            answer is null ? [] : CleanLinks(answer.Links),
            IsFallback: answer is null,
            CanContinue: !conversation.IsFull);
    }

    private static List<string> CleanSuggestions(IReadOnlyList<string> suggestions) =>
        suggestions.Select(s => s.Trim())
            .Where(s => s.Length is > 0 and <= MaxSuggestionLength)
            .Distinct()
            .Take(MaxSuggestions)
            .ToList();

    /// <summary>Only links the frontend can open: a known kind, and an id or code of the right shape.</summary>
    private static List<AssistantLink> CleanLinks(IReadOnlyList<AssistantLink> links) =>
        links.Where(l => l.Kind switch
            {
                "lesson" or "mentor" => Guid.TryParse(l.Ref, out _),
                "track" => l.Ref.Length is > 0 and <= 20 && l.Ref.All(char.IsAsciiLetterUpper),
                _ => PageKinds.Contains(l.Kind) && l.Ref.Length == 0,
            })
            .Select(l => l with { Label = l.Label.Length > 60 ? l.Label[..60] : l.Label })
            .DistinctBy(l => (l.Kind, l.Ref))
            .Take(MaxLinks)
            .ToList();
}

/// <summary>The student's latest conversations, newest first.</summary>
public sealed class GetAssistantConversationsHandler(
    ICurrentStudent currentStudent, IAssistantRepository conversations, IOptions<AssistantOptions> options)
{
    public async Task<Result<IReadOnlyList<AssistantConversationSummaryDto>>> HandleAsync(CancellationToken cancellationToken)
    {
        var list = await conversations.ListAsync(currentStudent.Id, options.Value.ConversationsListed, cancellationToken);
        return list.Select(c => new AssistantConversationSummaryDto(c.Id, c.Title, c.StartedUtc, c.LastMessageUtc, c.MessageCount)).ToList();
    }
}

/// <summary>One of the student's conversations with all its messages in order.</summary>
public sealed class GetAssistantConversationHandler(ICurrentStudent currentStudent, IAssistantRepository conversations)
{
    public async Task<Result<AssistantConversationDto>> HandleAsync(Guid conversationId, CancellationToken cancellationToken)
    {
        var conversation = await conversations.GetAsync(conversationId, currentStudent.Id, cancellationToken);
        if (conversation is null) return AssistantErrors.NotFound;

        return new AssistantConversationDto(
            conversation.Id, conversation.Title, conversation.StartedUtc, conversation.LastMessageUtc,
            conversation.InOrder.Select(AssistantViews.Message).ToList(), !conversation.IsFull);
    }
}
