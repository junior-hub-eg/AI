using JuniorHub.Infrastructure.DiscoveryAi;
using Microsoft.Extensions.Options;

namespace JuniorHub.Infrastructure.AssistantAi;

/// <summary>A fresh 5-minute RS256 token, audience assistant-ai, for every call to the Assistant AI service.</summary>
internal sealed class AssistantTokenSigner(IOptions<AssistantAiOptions> options) : IDisposable
{
    private readonly ServiceTokenSigner _signer = new(
        options.Value.SigningKeyPem, options.Value.Issuer, options.Value.Audience, AssistantAiOptions.SectionName);

    public string Create(DateTime nowUtc) => _signer.Create(nowUtc);

    public void Dispose() => _signer.Dispose();
}
