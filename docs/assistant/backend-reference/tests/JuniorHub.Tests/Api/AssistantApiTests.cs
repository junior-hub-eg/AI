using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using JuniorHub.Application.Assistant;
using JuniorHub.Application.Discovery;
using JuniorHub.Domain.Enums;
using JuniorHub.Infrastructure.AssistantAi;
using JuniorHub.Infrastructure.DiscoveryAi;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace JuniorHub.Tests.Api;

internal static class AssistantTestClient
{
    public static Task<HttpResponseMessage> AskAsync(this HttpClient client, string token, string text, string? conversationId = null) =>
        client.SendAsync(HttpMethod.Post, "/api/v1/assistant/messages", token, JsonContent.Create(new { conversationId, text }));
}

/// <summary>The student assistant against the in-process mock AI.</summary>
public sealed class AssistantApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client = factory.CreateApiClient();

    [Fact]
    public async Task A_question_starts_a_conversation_and_both_messages_are_stored()
    {
        var token = await _client.LoginForTokenAsync();

        var response = await _client.AskAsync(token, "عندي كام XP؟");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.JsonAsync();
        Assert.False(body.GetProperty("isFallback").GetBoolean());
        Assert.Contains("40 XP", body.GetProperty("reply").GetProperty("text").GetString());
        Assert.Equal("Student", body.GetProperty("message").GetProperty("role").GetString());
        Assert.Equal(2, body.GetProperty("reply").GetProperty("orderIndex").GetInt32());

        var id = body.GetProperty("conversationId").GetString()!;
        var chat = await (await _client.GetAsync($"/api/v1/assistant/conversations/{id}", token)).JsonAsync();
        Assert.Equal(["عندي كام XP؟", body.GetProperty("reply").GetProperty("text").GetString()],
            chat.GetProperty("messages").EnumerateArray().Select(m => m.GetProperty("text").GetString()));
    }

    [Fact]
    public async Task A_conversation_continues_and_is_listed()
    {
        var token = await _client.LoginForTokenAsync("youssef.adel@juniorhub.demo");
        var first = await (await _client.AskAsync(token, "مين المنتور بتاعي؟")).JsonAsync();
        var id = first.GetProperty("conversationId").GetString()!;

        var second = await (await _client.AskAsync(token, "الدرس الجاي إيه؟", id)).JsonAsync();

        Assert.Equal(id, second.GetProperty("conversationId").GetString());
        Assert.Equal(4, second.GetProperty("reply").GetProperty("orderIndex").GetInt32());
        var list = await (await _client.GetAsync("/api/v1/assistant/conversations", token)).JsonAsync();
        var item = Assert.Single(list.EnumerateArray());
        Assert.Equal(("مين المنتور بتاعي؟", 4), (item.GetProperty("title").GetString(), item.GetProperty("messageCount").GetInt32()));
    }

    [Fact]
    public async Task Another_students_conversation_cannot_be_read_or_continued()
    {
        var mine = await _client.LoginForTokenAsync("omar.khaled@juniorhub.demo");
        var id = (await (await _client.AskAsync(mine, "hi")).JsonAsync()).GetProperty("conversationId").GetString()!;
        var other = await _client.LoginForTokenAsync("nour.hassan@juniorhub.demo");

        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/v1/assistant/conversations/{id}", other)).StatusCode);
        var response = await _client.AskAsync(other, "hello", id);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("CONVERSATION_NOT_FOUND", (await response.JsonAsync()).GetProperty("code").GetString());
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task An_empty_question_is_refused(string text)
    {
        var response = await _client.AskAsync(await _client.LoginForTokenAsync(), text);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task A_question_over_1000_characters_is_refused()
    {
        var response = await _client.AskAsync(await _client.LoginForTokenAsync(), new string('x', 1001));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task The_assistant_needs_a_signed_in_student()
    {
        var response = await _client.PostAsJsonAsync("/api/v1/assistant/messages", new { text = "hi" });
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Theory]
    [InlineData("my_progress", AssistantTopic.MyProgress)]
    [InlineData("concept_help", AssistantTopic.ConceptHelp)]
    [InlineData("wellbeing", AssistantTopic.Wellbeing)]
    [InlineData("something_new", null)]
    [InlineData("3", null)]
    [InlineData(null, null)]
    public void Topics_from_the_service_are_read_from_snake_case(string? wire, AssistantTopic? expected)
    {
        Assert.Equal(expected, HttpAssistantAiClient.ParseTopic(wire));
    }
}

/// <summary>Records what the backend sends to the AI service, and can pretend the service is down.</summary>
public sealed class RecordingAssistantApiFactory : ApiFactory
{
    public RecordingAssistantClient Ai { get; } = new();

    protected override void ConfigureTestServices(IServiceCollection services)
    {
        services.RemoveAll<IAssistantAiClient>();
        services.AddSingleton<IAssistantAiClient>(Ai);
    }
}

public sealed class RecordingAssistantClient : IAssistantAiClient
{
    public List<AssistantAiRequest> Requests { get; } = [];
    public bool Down { get; set; }

    public Task<AiCallResult<AssistantAiReply>> ReplyAsync(AssistantAiRequest request, CancellationToken cancellationToken)
    {
        lock (Requests) Requests.Add(request);
        return Task.FromResult(Down
            ? AiCallResult<AssistantAiReply>.Failed("timeout")
            : AiCallResult<AssistantAiReply>.Ok(new AssistantAiReply(
                "تمام", ["سؤال تاني؟", new string('s', 81)],
                [new AssistantLink("lesson", Guid.NewGuid().ToString(), "Functions"), new AssistantLink("lesson", "not-an-id", ""),
                 new AssistantLink("squad", "", "Squad"), new AssistantLink("track", "frontend", "")],
                AssistantTopic.SmallTalk, "assistant@v1", "test-model")));
    }
}

/// <summary>What reaches the AI service: the student's own data, teammates by first name only, nothing else that identifies anyone.</summary>
public sealed class AssistantContextApiTests(RecordingAssistantApiFactory factory) : IClassFixture<RecordingAssistantApiFactory>
{
    private readonly HttpClient _client = factory.CreateApiClient();

    private async Task<(AssistantAiRequest Request, JsonElement Response)> AskAsync(string email, string text = "hi", string? conversationId = null)
    {
        var token = await _client.LoginForTokenAsync(email);
        var response = await _client.AskAsync(token, text, conversationId);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.JsonAsync();
        lock (factory.Ai.Requests) return (factory.Ai.Requests[^1], body);
    }

    [Fact]
    public async Task A_frontend_student_gets_their_lessons_mentor_and_squad_by_role()
    {
        var (request, _) = await AskAsync("omar.khaled@juniorhub.demo");
        var ctx = request.Context;

        var focus = Assert.Single(ctx.Tracks, t => t.InFocus);
        Assert.Equal(("FRONTEND", TrackLevel.Beginner, 1), (focus.Code, focus.Level, focus.LessonsDone));
        Assert.Equal("FRONTEND", ctx.Learning!.TrackCode);
        Assert.Equal("Functions", ctx.Learning.Lessons.Single(l => l.Id == ctx.Learning.NextLessonId).Title);
        Assert.Equal("Done", ctx.Learning.Lessons.Single(l => l.Title == "Variables").Status);
        Assert.Equal("Sara El-Masry", ctx.Mentor!.FullName);
        Assert.Equal("Completed", ctx.Discovery.Status);
        Assert.Equal(3, ctx.Discovery.Recommendations.Count);
        Assert.NotNull(ctx.Squad);
        Assert.Single(ctx.Squad.Members, m => m.IsMe);
    }

    [Fact]
    public async Task The_demo_student_has_no_track_yet()
    {
        var (request, _) = await AskAsync(ApiFactory.DemoEmail);

        Assert.Empty(request.Context.Tracks);
        Assert.Null(request.Context.Learning);
        Assert.Null(request.Context.Mentor);
        Assert.Equal(40, request.Context.Student.TotalXp);
        Assert.Equal("Code Hunters", request.Context.Squad!.Name);
        Assert.NotEmpty(request.Context.Squad.MyTasks);
    }

    [Fact]
    public async Task No_own_name_email_school_full_names_or_quiz_answer_is_sent()
    {
        var (request, _) = await AskAsync("omar.khaled@juniorhub.demo");

        // Serialised exactly as the HTTP client sends it.
        var json = JsonSerializer.Serialize(request.Context, HttpDiscoveryAiClient.Json);
        foreach (var forbidden in new[] { "Omar", "Khaled", "Hassan", "juniorhub.demo", "correct", "school_id", "email" })
            Assert.DoesNotContain(forbidden, json, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("\"in_focus\":true", json);
        Assert.Contains("\"name\":\"Nour\"", json); // teammates by first name
        Assert.Contains("\"next_lesson_id\":", json);
    }

    [Fact]
    public async Task The_history_of_the_conversation_is_sent_oldest_first()
    {
        var (_, first) = await AskAsync("hamza.ayman@juniorhub.demo", "first");
        var id = first.GetProperty("conversationId").GetString()!;
        var (request, _) = await AskAsync("hamza.ayman@juniorhub.demo", "second", id);

        Assert.Equal("second", request.Message);
        Assert.Equal([(AssistantRole.Student, "first"), (AssistantRole.Assistant, "تمام")], request.History.Select(h => (h.Role, h.Text)));
    }

    [Fact]
    public async Task Only_valid_suggestions_and_links_reach_the_student()
    {
        var (_, response) = await AskAsync("youssef.adel@juniorhub.demo");

        Assert.Equal(["سؤال تاني؟"], response.GetProperty("suggestions").EnumerateArray().Select(s => s.GetString()));
        Assert.Equal(["lesson", "squad"], response.GetProperty("links").EnumerateArray().Select(l => l.GetProperty("kind").GetString()));
    }
}

/// <summary>The AI service is down: the prepared reply is stored and shown.</summary>
public sealed class AssistantAiDownApiTests : IClassFixture<RecordingAssistantApiFactory>
{
    private readonly RecordingAssistantApiFactory _factory;
    private readonly HttpClient _client;

    public AssistantAiDownApiTests(RecordingAssistantApiFactory factory)
    {
        _factory = factory;
        _factory.Ai.Down = true;
        _client = factory.CreateApiClient();
    }

    [Fact]
    public async Task The_fallback_reply_is_stored_and_flagged()
    {
        var token = await _client.LoginForTokenAsync();
        var body = await (await _client.AskAsync(token, "hi")).JsonAsync();

        Assert.True(body.GetProperty("isFallback").GetBoolean());
        Assert.Equal(new AssistantOptions().FallbackReply, body.GetProperty("reply").GetProperty("text").GetString());
        Assert.Empty(body.GetProperty("suggestions").EnumerateArray());

        var id = body.GetProperty("conversationId").GetString()!;
        var chat = await (await _client.GetAsync($"/api/v1/assistant/conversations/{id}", token)).JsonAsync();
        Assert.Equal(2, chat.GetProperty("messages").GetArrayLength());
    }
}
