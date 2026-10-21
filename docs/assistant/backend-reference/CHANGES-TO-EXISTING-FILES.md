# Changes to existing backend files

The new files in this folder also need these edits to files that already exist in the backend. Unified diffs against the `prod` branch as of 20 Oct 2026; nothing here was compiled, so treat it as a starting point.

## `src/JuniorHub.Domain/Enums/ResultSource.cs`

```diff
--- a/src/JuniorHub.Domain/Enums/ResultSource.cs
+++ b/src/JuniorHub.Domain/Enums/ResultSource.cs
@@ -1,6 +1,6 @@
 namespace JuniorHub.Domain.Enums;
 
-/// <summary>Where an interview result came from (BR-06).</summary>
+/// <summary>Where an AI result came from: an interview result (BR-06) or an assistant reply.</summary>
 public enum ResultSource
 {
     Ai,
```

## `src/JuniorHub.Application/DependencyInjection.cs`

```diff
--- a/src/JuniorHub.Application/DependencyInjection.cs
+++ b/src/JuniorHub.Application/DependencyInjection.cs
@@ -1,4 +1,5 @@
 using FluentValidation;
+using JuniorHub.Application.Assistant;
 using JuniorHub.Application.Auth;
 using JuniorHub.Application.Auth.Activation;
 using JuniorHub.Application.Auth.PasswordReset;
@@ -57,6 +58,9 @@
         services.AddScoped<GetMentorHandler>();
         services.AddScoped<GetMyMentorHandler>();
         services.AddScoped<ChooseMentorHandler>();
+        services.AddScoped<SendAssistantMessageHandler>();
+        services.AddScoped<GetAssistantConversationsHandler>();
+        services.AddScoped<GetAssistantConversationHandler>();
 
         return services;
     }
```

## `src/JuniorHub.Infrastructure/DependencyInjection.cs`

```diff
--- a/src/JuniorHub.Infrastructure/DependencyInjection.cs
+++ b/src/JuniorHub.Infrastructure/DependencyInjection.cs
@@ -1,4 +1,5 @@
 using JuniorHub.Application.Abstractions;
+using JuniorHub.Application.Assistant;
 using JuniorHub.Application.Auth;
 using JuniorHub.Application.Auth.Activation;
 using JuniorHub.Application.Common;
@@ -8,6 +9,7 @@
 using JuniorHub.Application.Learning;
 using JuniorHub.Application.Mentorship;
 using JuniorHub.Application.Students;
+using JuniorHub.Infrastructure.AssistantAi;
 using JuniorHub.Infrastructure.Auth;
 using JuniorHub.Infrastructure.DiscoveryAi;
 using JuniorHub.Infrastructure.Email;
@@ -108,9 +110,46 @@
         }
         services.AddScoped<IHubReader, HubReader>();
 
+        AddAssistant(services, configuration, isProduction);
+
         return services;
     }
 
+    /// <summary>
+    /// Student assistant (docs/assistant-ai-contract.md): conversations in the database, replies from the Assistant AI
+    /// service. The in-process mock until the service is deployed, then AssistantAi__Mode=Http.
+    /// </summary>
+    private static void AddAssistant(IServiceCollection services, IConfiguration configuration, bool isProduction)
+    {
+        services.Configure<AssistantOptions>(configuration.GetSection(AssistantOptions.SectionName));
+        services.AddScoped<IAssistantRepository, AssistantRepository>();
+        services.AddScoped<IAssistantContextReader, AssistantContextReader>();
+
+        services.AddOptions<AssistantAiOptions>().Bind(configuration.GetSection(AssistantAiOptions.SectionName)).ValidateDataAnnotations();
+        var ai = configuration.GetSection(AssistantAiOptions.SectionName).Get<AssistantAiOptions>() ?? new AssistantAiOptions();
+        if (isProduction)
+        {
+            if (ai.Mode != AssistantAiMode.Http)
+                throw new InvalidOperationException("AssistantAi:Mode must be Http in Production.");
+            if (string.IsNullOrWhiteSpace(ai.BaseUrl) || string.IsNullOrWhiteSpace(ai.SigningKeyPem))
+                throw new InvalidOperationException("AssistantAi:BaseUrl and AssistantAi:SigningKeyPem must be set in Production.");
+        }
+
+        if (ai.Mode == AssistantAiMode.Http)
+        {
+            services.AddSingleton<AssistantTokenSigner>();
+            services.AddHttpClient<IAssistantAiClient, HttpAssistantAiClient>(http =>
+            {
+                http.BaseAddress = new Uri((ai.BaseUrl ?? throw new InvalidOperationException("AssistantAi:BaseUrl is not set.")).TrimEnd('/') + "/");
+                http.Timeout = Timeout.InfiniteTimeSpan; // the client sets its own timeout
+            });
+        }
+        else
+        {
+            services.AddSingleton<IAssistantAiClient, MockAssistantAiClient>();
+        }
+    }
+
     private static void ValidateProductionConnectionString(string connectionString)
     {
         var builder = new System.Data.Common.DbConnectionStringBuilder { ConnectionString = connectionString };
```

## `src/JuniorHub.Infrastructure/DiscoveryAi/ServiceTokenSigner.cs`

```diff
--- a/src/JuniorHub.Infrastructure/DiscoveryAi/ServiceTokenSigner.cs
+++ b/src/JuniorHub.Infrastructure/DiscoveryAi/ServiceTokenSigner.cs
@@ -6,30 +6,41 @@
 
 namespace JuniorHub.Infrastructure.DiscoveryAi;
 
-/// <summary>JH-SRS §6.3: a fresh 5-minute RS256 token, audience discovery-ai, for every call to the AI service.</summary>
+/// <summary>
+/// JH-SRS §6.3: a fresh 5-minute RS256 token for every call to an AI service. Audience discovery-ai for the Discovery AI
+/// service; the assistant uses its own key and audience (assistant-ai) through <see cref="AssistantAi.AssistantTokenSigner"/>.
+/// </summary>
 internal sealed class ServiceTokenSigner : IDisposable
 {
     private static readonly TimeSpan Lifetime = TimeSpan.FromMinutes(5);
 
-    private readonly DiscoveryAiOptions _options;
+    private readonly string _issuer;
+    private readonly string _audience;
     private readonly RSA _rsa = RSA.Create();
     private readonly SigningCredentials _credentials;
     private readonly JsonWebTokenHandler _handler = new();
 
     public ServiceTokenSigner(IOptions<DiscoveryAiOptions> options)
+        : this(options.Value.SigningKeyPem, options.Value.Issuer, options.Value.Audience, DiscoveryAiOptions.SectionName)
     {
-        _options = options.Value;
-        if (string.IsNullOrWhiteSpace(_options.SigningKeyPem))
-            throw new InvalidOperationException("DiscoveryAi:SigningKeyPem is not set. It is needed in Http mode.");
+    }
+
+    /// <param name="sectionName">The settings section, named in the error when the key is missing.</param>
+    internal ServiceTokenSigner(string? signingKeyPem, string issuer, string audience, string sectionName)
+    {
+        if (string.IsNullOrWhiteSpace(signingKeyPem))
+            throw new InvalidOperationException($"{sectionName}:SigningKeyPem is not set. It is needed in Http mode.");
 
-        _rsa.ImportFromPem(_options.SigningKeyPem.Replace("\\n", "\n"));
+        _issuer = issuer;
+        _audience = audience;
+        _rsa.ImportFromPem(signingKeyPem.Replace("\\n", "\n"));
         _credentials = new SigningCredentials(new RsaSecurityKey(_rsa), SecurityAlgorithms.RsaSha256);
     }
 
     public string Create(DateTime nowUtc) => _handler.CreateToken(new SecurityTokenDescriptor
     {
-        Issuer = _options.Issuer,
-        Audience = _options.Audience,
+        Issuer = _issuer,
+        Audience = _audience,
         IssuedAt = nowUtc,
         NotBefore = nowUtc,
         Expires = nowUtc + Lifetime,
```

## `src/JuniorHub.Infrastructure/Persistence/JuniorHubDbContext.cs`

```diff
--- a/src/JuniorHub.Infrastructure/Persistence/JuniorHubDbContext.cs
+++ b/src/JuniorHub.Infrastructure/Persistence/JuniorHubDbContext.cs
@@ -1,5 +1,6 @@
 using JuniorHub.Application.Abstractions;
 using JuniorHub.Domain.Activity;
+using JuniorHub.Domain.Assistant;
 using JuniorHub.Domain.Common;
 using JuniorHub.Domain.Discovery;
 using JuniorHub.Domain.Interns;
@@ -72,6 +73,10 @@
     // M7 Activity
     public DbSet<ActivityEvent> ActivityEvents => Set<ActivityEvent>();
 
+    // Student assistant (docs/assistant-ai-contract.md), not in JH-DCS v0.1
+    public DbSet<AssistantConversation> AssistantConversations => Set<AssistantConversation>();
+    public DbSet<AssistantMessage> AssistantMessages => Set<AssistantMessage>();
+
     // Technical tables, not in JH-DCS
     internal DbSet<StoredRefreshToken> RefreshTokens => Set<StoredRefreshToken>();
     internal DbSet<StoredOneTimeCode> OneTimeCodes => Set<StoredOneTimeCode>();
```

## `src/JuniorHub.Api/Http/RateLimits.cs`

```diff
--- a/src/JuniorHub.Api/Http/RateLimits.cs
+++ b/src/JuniorHub.Api/Http/RateLimits.cs
@@ -8,14 +8,18 @@
 /// <summary>
 /// Limits on the sign-in and sign-up endpoints, per client IP, so passwords, activation codes and email
 /// codes cannot be guessed by trying many times. Set in "RateLimiting:AuthPerMinute".
+/// The assistant is limited per signed-in session ("RateLimiting:AssistantPerMinute"), not per IP, because a whole
+/// school class shares one IP.
 /// </summary>
 internal static class RateLimits
 {
     public const string Auth = "auth";
+    public const string Assistant = "assistant";
 
     public static IServiceCollection AddAuthRateLimits(this IServiceCollection services, IConfiguration configuration)
     {
         var perMinute = configuration.GetValue("RateLimiting:AuthPerMinute", 30);
+        var assistantPerMinute = configuration.GetValue("RateLimiting:AssistantPerMinute", 20);
 
         return services.AddRateLimiter(options =>
         {
@@ -23,6 +27,12 @@
                 context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                 _ => new FixedWindowRateLimiterOptions { PermitLimit = perMinute, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
 
+            // The limiter runs before authentication, so the session is told apart by its access token. A request
+            // without a token is rejected by authorization anyway.
+            options.AddPolicy(Assistant, context => RateLimitPartition.GetFixedWindowLimiter(
+                context.Request.Headers.Authorization.ToString() is { Length: > 0 } token ? token : "anonymous",
+                _ => new FixedWindowRateLimiterOptions { PermitLimit = assistantPerMinute, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
+
             options.OnRejected = async (context, cancellationToken) =>
             {
                 var error = new Error("TOO_MANY_REQUESTS", "Too many tries. Please wait a minute and try again.", ErrorType.TooManyRequests);
```

## `tests/JuniorHub.Tests/Infrastructure/PersistenceModelTests.cs`

```diff
--- a/tests/JuniorHub.Tests/Infrastructure/PersistenceModelTests.cs
+++ b/tests/JuniorHub.Tests/Infrastructure/PersistenceModelTests.cs
@@ -26,8 +26,9 @@
         var mapped = Model.GetEntityTypes().Select(e => e.ClrType).ToHashSet();
         var technical = mapped.Where(t => t.Assembly == typeof(JuniorHubDbContext).Assembly).Select(t => t.Name);
 
-        // The 34 JH-DCS entities, plus ActivationInvite for the school activation pages.
-        Assert.Equal(35, domainEntities.Count);
+        // The 34 JH-DCS entities, plus ActivationInvite for the school activation pages and the assistant's
+        // AssistantConversation and AssistantMessage.
+        Assert.Equal(37, domainEntities.Count);
         Assert.Subset(mapped, domainEntities);
         Assert.Equal(["StoredOneTimeCode", "StoredRefreshToken"], technical.Order());
     }
@@ -68,6 +69,7 @@
         { "ActivationInvites", ["Code"], null },
         { "ActivationInvites", ["LinkToken"], null },
         { "RefreshTokens", ["TokenHash"], null },
+        { "AssistantMessages", ["ConversationId", "OrderIndex"], null },
     };
 
     [Theory]
```

## Migration

```bash
dotnet ef migrations add AddAssistantConversations --project src/JuniorHub.Infrastructure --startup-project src/JuniorHub.Api --output-dir Persistence/Migrations
```
