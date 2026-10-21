using System.ComponentModel.DataAnnotations;

namespace JuniorHub.Infrastructure.AssistantAi;

public enum AssistantAiMode
{
    /// <summary>An in-process stand-in with the same contract, until the real service is deployed.</summary>
    Mock,

    /// <summary>The real Assistant AI service over HTTP (docs/assistant-ai-contract.md).</summary>
    Http,
}

/// <summary>How the backend reaches the Assistant AI service, in the "AssistantAi" section.</summary>
public sealed class AssistantAiOptions
{
    public const string SectionName = "AssistantAi";

    public AssistantAiMode Mode { get; init; } = AssistantAiMode.Mock;

    /// <summary>For example http://localhost:8010 (Http mode).</summary>
    public string? BaseUrl { get; init; }

    /// <summary>
    /// RSA private key (PEM) that signs the service token (RS256). The AI service holds the public key.
    /// Never committed: set AssistantAi__SigningKeyPem on the server. A different key from DiscoveryAi.
    /// </summary>
    public string? SigningKeyPem { get; init; }

    public string Issuer { get; init; } = "JuniorHub.Api";
    public string Audience { get; init; } = "assistant-ai";

    /// <summary>One reply, no automatic retry. On timeout the prepared fallback reply is shown.</summary>
    [Range(1, 120)] public int TimeoutSeconds { get; init; } = 20;
}
