using JuniorHub.Domain.Assistant;
using JuniorHub.Domain.Common;
using JuniorHub.Domain.Enums;

namespace JuniorHub.Tests.Domain;

public sealed class AssistantConversationTests
{
    private static readonly DateTime Now = new(2026, 10, 20, 18, 0, 0, DateTimeKind.Utc);

    private static AssistantConversation Conversation() => new(Guid.NewGuid(), Now);

    [Fact]
    public void A_question_and_its_reply_are_numbered_in_order()
    {
        var chat = Conversation();

        var question = chat.AddStudentMessage("  عندي كام XP؟ ", Now);
        var reply = chat.AddReply("معاك 40 XP", ResultSource.Ai, AssistantTopic.MyProgress, "assistant@v1", "model", Now.AddSeconds(2));

        Assert.Equal((1, AssistantRole.Student, "عندي كام XP؟"), (question.OrderIndex, question.Role, question.Text));
        Assert.Equal((2, AssistantRole.Assistant), (reply.OrderIndex, reply.Role));
        Assert.Equal(AssistantTopic.MyProgress, reply.Topic);
        Assert.Equal(Now.AddSeconds(2), chat.LastMessageUtc);
        Assert.Equal("عندي كام XP؟", chat.Title);
    }

    [Fact]
    public void A_second_question_waits_for_the_reply()
    {
        var chat = Conversation();
        chat.AddStudentMessage("hi", Now);

        var error = Assert.Throws<DomainException>(() => chat.AddStudentMessage("hello?", Now));
        Assert.Equal("REPLY_PENDING", error.Code);
    }

    [Fact]
    public void A_reply_needs_a_question()
    {
        var error = Assert.Throws<DomainException>(() => Conversation().AddReply("hi", ResultSource.Fallback, null, null, null, Now));
        Assert.Equal("NOTHING_TO_ANSWER", error.Code);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void An_empty_question_is_refused(string text)
    {
        Assert.Equal("EMPTY_MESSAGE", Assert.Throws<DomainException>(() => Conversation().AddStudentMessage(text, Now)).Code);
    }

    [Fact]
    public void A_long_question_is_refused_and_a_long_reply_is_cut()
    {
        var chat = Conversation();
        Assert.Throws<DomainException>(() => chat.AddStudentMessage(new string('x', AssistantConversation.MaxStudentTextLength + 1), Now));

        chat.AddStudentMessage(new string('q', 200), Now);
        var reply = chat.AddReply(new string('r', 5000), ResultSource.Ai, null, null, null, Now);

        Assert.Equal(AssistantConversation.MaxReplyLength, reply.Text.Length);
        Assert.Equal(AssistantConversation.MaxTitleLength, chat.Title.Length);
    }

    [Fact]
    public void A_full_conversation_takes_no_more_questions()
    {
        var chat = Conversation();
        for (var i = 0; i < AssistantConversation.MaxMessages / 2; i++)
        {
            chat.AddStudentMessage($"q{i}", Now);
            chat.AddReply($"r{i}", ResultSource.Ai, null, null, null, Now);
        }

        Assert.True(chat.IsFull);
        Assert.Equal("CONVERSATION_FULL", Assert.Throws<DomainException>(() => chat.AddStudentMessage("one more", Now)).Code);
    }

    [Fact]
    public void Recent_gives_the_latest_messages_oldest_first()
    {
        var chat = Conversation();
        for (var i = 1; i <= 3; i++)
        {
            chat.AddStudentMessage($"q{i}", Now);
            chat.AddReply($"r{i}", ResultSource.Ai, null, null, null, Now);
        }

        Assert.Equal(["q2", "r2", "q3", "r3"], chat.Recent(4).Select(m => m.Text));
    }
}
