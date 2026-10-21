using JuniorHub.Application.Assistant;
using JuniorHub.Domain.Assistant;
using Microsoft.EntityFrameworkCore;

namespace JuniorHub.Infrastructure.Persistence.Repositories;

internal sealed class AssistantRepository(JuniorHubDbContext db) : IAssistantRepository
{
    public Task<AssistantConversation?> GetAsync(Guid conversationId, Guid studentId, CancellationToken cancellationToken) =>
        db.AssistantConversations.Include(c => c.Messages)
            .SingleOrDefaultAsync(c => c.Id == conversationId && c.StudentId == studentId, cancellationToken);

    public async Task<IReadOnlyList<AssistantConversationSummary>> ListAsync(Guid studentId, int take, CancellationToken cancellationToken) =>
        await db.AssistantConversations.AsNoTracking()
            .Where(c => c.StudentId == studentId)
            .OrderByDescending(c => c.LastMessageUtc)
            .Take(take)
            .Select(c => new AssistantConversationSummary(c.Id, c.Title, c.StartedUtc, c.LastMessageUtc, c.Messages.Count()))
            .ToListAsync(cancellationToken);

    public void Add(AssistantConversation conversation) => db.AssistantConversations.Add(conversation);
}
