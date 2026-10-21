using JuniorHub.Application.Assistant;
using JuniorHub.Application.Discovery;
using JuniorHub.Domain.Enums;

namespace JuniorHub.Infrastructure.AssistantAi;

/// <summary>
/// Stands in for the Assistant AI service until it is deployed, with the same contract: short Arabic replies built from
/// the context by simple keywords, so the frontend can be built against real data. Never sends anything anywhere.
/// </summary>
internal sealed class MockAssistantAiClient : IAssistantAiClient
{
    public const string PromptVersion = "mock@v1";

    public Task<AiCallResult<AssistantAiReply>> ReplyAsync(AssistantAiRequest request, CancellationToken cancellationToken)
    {
        var text = request.Message.ToLowerInvariant();
        var ctx = request.Context;
        var reply = Has(text, "xp", "نقط", "نقاط", "ستريك", "streak")
            ? Reply($"معاك {ctx.Student.TotalXp} XP، والـ streak بتاعك {ctx.Student.StreakDays} يوم. كمّل كده! 💪", AssistantTopic.MyProgress,
                ["أزوّد الـ XP إزاي؟"], [new AssistantLink("achievements", "", "إنجازاتي")])
            : Has(text, "درس", "lesson", "الجاي", "next")
                ? NextLesson(ctx)
                : Has(text, "فريق", "squad", "sprint", "سبرنت", "تاسك", "task")
                    ? Squad(ctx)
                    : Has(text, "منتور", "mentor")
                        ? Mentor(ctx)
                        : Reply("أنا مساعد Junior Hub (نسخة تجريبية). اسألني عن الدرس الجاي، الـ XP، فريقك أو المنتور بتاعك.",
                            AssistantTopic.SmallTalk, ["الدرس الجاي إيه؟", "عندي كام XP؟"], []);

        return Task.FromResult(AiCallResult<AssistantAiReply>.Ok(reply));
    }

    private static AssistantAiReply NextLesson(AssistantContext ctx)
    {
        if (ctx.Learning is null)
            return Reply("لسه ما اخترتش track. ابدأ بـ Track Discovery وهيرشحلك أنسب 3 tracks ليك.", AssistantTopic.Learning,
                ["يعني إيه Track Discovery؟"], [new AssistantLink("discovery", "", "Track Discovery")]);

        var next = ctx.Learning.Lessons.FirstOrDefault(l => l.Id == ctx.Learning.NextLessonId);
        return next is null
            ? Reply("خلّصت كل الدروس المتاحة في الـ track ده 🎉", AssistantTopic.Learning, [], [])
            : Reply($"الدرس الجاي: {next.Title} ({next.Concept}).", AssistantTopic.Learning, ["اشرحلي الدرس ده"],
                [new AssistantLink("lesson", next.Id.ToString(), next.Title)]);
    }

    private static AssistantAiReply Squad(AssistantContext ctx)
    {
        if (ctx.Squad is null) return Reply("إنت مش في squad لسه.", AssistantTopic.Squad, [], []);
        var open = ctx.Squad.MyTasks.Count(t => t.Status != SquadTaskStatus.Done);
        var sprint = ctx.Squad.Sprint is { } s ? $"، والـ {s.Name} خلص منه {s.TasksDone} من {s.TasksTotal} tasks" : "";
        return Reply($"إنت في {ctx.Squad.Name} بدور {ctx.Squad.MyRole}{sprint}. عندك {open} task لسه مفتوحة.", AssistantTopic.Squad, [],
            [new AssistantLink("squad", "", ctx.Squad.Name)]);
    }

    private static AssistantAiReply Mentor(AssistantContext ctx) => ctx.Mentor is { } m
        ? Reply($"المنتور بتاعك {m.FullName}، {m.Title}.", AssistantTopic.Mentor, [], [new AssistantLink("mentor", m.Id.ToString(), m.FullName)])
        : Reply("لسه ما عندكش منتور. تقدر تختار واحد من صفحة Mentorship.", AssistantTopic.Mentor, [], []);

    private static bool Has(string text, params string[] words) => words.Any(text.Contains);

    private static AssistantAiReply Reply(string text, AssistantTopic topic, List<string> suggestions, List<AssistantLink> links) =>
        new(text, suggestions, links, topic, PromptVersion, "mock");
}
