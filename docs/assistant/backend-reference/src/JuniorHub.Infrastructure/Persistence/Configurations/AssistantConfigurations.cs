using JuniorHub.Domain.Assistant;
using JuniorHub.Domain.People;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace JuniorHub.Infrastructure.Persistence.Configurations;

// Student assistant (docs/assistant-ai-contract.md). Not in JH-DCS v0.1.

internal sealed class AssistantConversationConfiguration : IEntityTypeConfiguration<AssistantConversation>
{
    public void Configure(EntityTypeBuilder<AssistantConversation> builder)
    {
        builder.Property(x => x.Title).HasMaxLength(AssistantConversation.MaxTitleLength);
        builder.Ignore(x => x.InOrder);
        builder.Ignore(x => x.Last);
        builder.Ignore(x => x.IsFull);

        builder.HasOne<Student>().WithMany().HasForeignKey(x => x.StudentId);
        builder.HasMany(x => x.Messages).WithOne().HasForeignKey(x => x.ConversationId);

        // The student's chats, newest first.
        builder.HasIndex(x => new { x.StudentId, x.LastMessageUtc });
    }
}

internal sealed class AssistantMessageConfiguration : IEntityTypeConfiguration<AssistantMessage>
{
    public void Configure(EntityTypeBuilder<AssistantMessage> builder)
    {
        builder.Property(x => x.Text).HasMaxLength(AssistantConversation.MaxReplyLength);
        builder.Property(x => x.PromptVersion).HasMaxLength(60);
        builder.Property(x => x.ModelId).HasMaxLength(80);

        builder.HasIndex(x => new { x.ConversationId, x.OrderIndex }).IsUnique();
    }
}
