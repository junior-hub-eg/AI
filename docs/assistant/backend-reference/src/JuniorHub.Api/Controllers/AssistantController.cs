using JuniorHub.Api.Http;
using JuniorHub.Application.Assistant;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace JuniorHub.Api.Controllers;

/// <summary>
/// The student assistant: a chat that answers questions about the student's own journey and the platform
/// (docs/assistant-ai-contract.md). Conversations are stored; the AI service keeps nothing.
/// </summary>
[ApiController]
[Route("api/v1/assistant")]
public sealed class AssistantController : ControllerBase
{
    /// <summary>
    /// Ask a question. Without conversationId a new conversation starts. When the AI service fails, a prepared reply is
    /// stored and returned with isFallback true. Messages are 1 to 1000 characters.
    /// </summary>
    [HttpPost("messages")]
    [EnableRateLimiting(RateLimits.Assistant)]
    [ProducesResponseType<AssistantReplyResponse>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Send(
        [FromBody] SendAssistantMessageRequest request, [FromServices] SendAssistantMessageHandler handler, CancellationToken cancellationToken) =>
        (await handler.HandleAsync(request, cancellationToken)).ToActionResult(this);

    /// <summary>The student's latest conversations, newest first.</summary>
    [HttpGet("conversations")]
    [ProducesResponseType<IReadOnlyList<AssistantConversationSummaryDto>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> List([FromServices] GetAssistantConversationsHandler handler, CancellationToken cancellationToken) =>
        (await handler.HandleAsync(cancellationToken)).ToActionResult(this);

    /// <summary>One conversation with all its messages in order.</summary>
    [HttpGet("conversations/{id:guid}")]
    [ProducesResponseType<AssistantConversationDto>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Get(Guid id, [FromServices] GetAssistantConversationHandler handler, CancellationToken cancellationToken) =>
        (await handler.HandleAsync(id, cancellationToken)).ToActionResult(this);
}
