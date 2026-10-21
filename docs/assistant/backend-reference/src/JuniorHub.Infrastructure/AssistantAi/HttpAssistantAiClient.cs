using System.Diagnostics;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using JuniorHub.Application.Assistant;
using JuniorHub.Application.Discovery;
using JuniorHub.Domain.Enums;
using JuniorHub.Infrastructure.DiscoveryAi;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace JuniorHub.Infrastructure.AssistantAi;

/// <summary>
/// The real Assistant AI service (docs/assistant-ai-contract.md). Snake_case JSON, a fresh service token per call, one
/// timeout and no retry. Messages and replies are never logged, only prompt version, model, latency and topic.
/// </summary>
internal sealed class HttpAssistantAiClient(
    HttpClient http,
    AssistantTokenSigner tokens,
    IOptions<AssistantAiOptions> options,
    TimeProvider clock,
    ILogger<HttpAssistantAiClient> logger) : IAssistantAiClient
{
    // Same JSON as the Discovery AI service: snake_case names, enums as text.
    private static JsonSerializerOptions Json => HttpDiscoveryAiClient.Json;

    public async Task<AiCallResult<AssistantAiReply>> ReplyAsync(AssistantAiRequest request, CancellationToken cancellationToken)
    {
        var body = new RequestWire(
            request.ConversationId, request.StudentRef, request.Message,
            request.History.Select(h => new HistoryWire(h.Role == AssistantRole.Student ? "student" : "assistant", h.Text)).ToList(),
            request.Context);

        var timeoutSeconds = options.Value.TimeoutSeconds;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));

        using var message = new HttpRequestMessage(HttpMethod.Post, "v1/assistant/replies") { Content = JsonContent.Create(body, options: Json) };
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tokens.Create(clock.GetUtcNow().UtcDateTime));
        message.Headers.Add("X-Request-Id", Activity.Current?.TraceId.ToString() ?? Guid.NewGuid().ToString("N"));

        try
        {
            using var response = await http.SendAsync(message, timeout.Token);
            if (!response.IsSuccessStatusCode)
            {
                logger.LogWarning("Assistant AI answered {Status}", (int)response.StatusCode);
                return AiCallResult<AssistantAiReply>.Failed($"status {(int)response.StatusCode}");
            }

            var reply = await response.Content.ReadFromJsonAsync<ResponseWire>(Json, timeout.Token);
            if (reply is null || string.IsNullOrWhiteSpace(reply.Reply))
                return AiCallResult<AssistantAiReply>.Failed("empty reply");

            var topic = ParseTopic(reply.Topic);
            logger.LogInformation("Assistant AI reply: prompt {PromptVersion}, model {ModelId}, {LatencyMs} ms, topic {Topic}",
                reply.Meta?.PromptVersion, reply.Meta?.ModelId, reply.Meta?.LatencyMs, topic);

            return AiCallResult<AssistantAiReply>.Ok(new AssistantAiReply(
                reply.Reply,
                reply.Suggestions?.Where(s => !string.IsNullOrWhiteSpace(s)).Select(s => s!).ToList() ?? [],
                reply.Links?.Where(l => !string.IsNullOrWhiteSpace(l.Kind))
                    .Select(l => new AssistantLink(l.Kind!, l.Ref ?? "", l.Label ?? "")).ToList() ?? [],
                topic, reply.Meta?.PromptVersion, reply.Meta?.ModelId));
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            logger.LogWarning("Assistant AI timed out after {Seconds} s", timeoutSeconds);
            return AiCallResult<AssistantAiReply>.Failed("timeout");
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException or NotSupportedException)
        {
            logger.LogWarning("Assistant AI failed: {Error}", ex.GetType().Name);
            return AiCallResult<AssistantAiReply>.Failed(ex.GetType().Name);
        }
    }

    /// <summary>"my_progress" → MyProgress. Null for a topic this backend does not know.</summary>
    internal static AssistantTopic? ParseTopic(string? topic) =>
        Enum.TryParse<AssistantTopic>((topic ?? "").Replace("_", ""), ignoreCase: true, out var parsed) && Enum.IsDefined(parsed)
            ? parsed
            : null;

    // Wire shapes of docs/assistant-ai-contract.md. Names become snake_case.
    internal sealed record HistoryWire(string Role, string Text);
    internal sealed record RequestWire(Guid ConversationId, Guid StudentRef, string Message, List<HistoryWire> History, AssistantContext Context);

    internal sealed record LinkWire(string? Kind, string? Ref, string? Label);
    internal sealed record MetaWire(string? PromptVersion, string? ModelId, int? LatencyMs);
    internal sealed record ResponseWire(string? Reply, List<string?>? Suggestions, List<LinkWire>? Links, string? Topic, MetaWire? Meta);
}
