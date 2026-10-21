<#
  Sets up and runs the assistant on Windows in one step.

    .\run.ps1                              # setup (first time), tests, then chat as a mock student
    .\run.ps1 -Persona frontend_beginner   # chat as this student directly
    .\run.ps1 -Api                         # run the HTTP service on port 8010 for the backend
    .\run.ps1 -Reconfigure                 # choose the model provider and key again

  The first run asks which provider to use and for its API key, and writes them to .env (never committed).
#>
param(
    [string]$Persona = "",
    [switch]$Api,
    [switch]$Reconfigure
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`n$text" -ForegroundColor Red; exit 1 }

$providers = [ordered]@{
    "1" = @{ Name = "Cohere";    Model = "cohere:command-a-03-2025";          Package = "langchain-cohere";       KeyVar = "COHERE_API_KEY" }
    "2" = @{ Name = "OpenAI";    Model = "openai:gpt-4.1-mini";               Package = "langchain-openai";       KeyVar = "OPENAI_API_KEY" }
    "3" = @{ Name = "Gemini";    Model = "google_genai:gemini-2.5-flash";     Package = "langchain-google-genai"; KeyVar = "GOOGLE_API_KEY" }
    "4" = @{ Name = "Anthropic"; Model = "anthropic:claude-haiku-4-5";        Package = "langchain-anthropic";    KeyVar = "ANTHROPIC_API_KEY" }
    "5" = @{ Name = "Groq";      Model = "groq:llama-3.3-70b-versatile";      Package = "langchain-groq";         KeyVar = "GROQ_API_KEY" }
    "6" = @{ Name = "Fake (no key, wiring check only)"; Model = "fake"; Package = $null; KeyVar = $null }
}

# 1. Python ----------------------------------------------------------------------------------------------------------
Step "Checking Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Fail "Python is not installed or not on PATH. Install Python 3.10+ from python.org and run again." }
$version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$version -lt [version]"3.10") { Fail "Python $version found; 3.10 or newer is needed." }
Write-Host "Python $version"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Step "Creating the virtual environment (.venv)"
    & python -m venv .venv
    if ($LASTEXITCODE) { Fail "Could not create .venv." }
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Step "Installing packages"
& $py -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt
if ($LASTEXITCODE) { Fail "pip install failed. Check your internet connection and run again." }

# 2. Model provider and key -----------------------------------------------------------------------------------------
function Read-EnvValue($name) {
    if (-not (Test-Path ".env")) { return $null }
    $line = Get-Content ".env" -Encoding UTF8 | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
    if ($line) { return ($line -split "=", 2)[1].Trim().Trim('"') }
    return $null
}

if ($Reconfigure -or -not (Test-Path ".env")) {
    Step "Choose the model provider"
    foreach ($k in $providers.Keys) { Write-Host "  $k. $($providers[$k].Name)  ($($providers[$k].Model))" }
    $choice = Read-Host "Number"
    if (-not $providers.Contains($choice)) { Fail "Unknown choice '$choice'." }
    $p = $providers[$choice]

    $lines = @(
        "LLM_MODEL=$($p.Model)",
        "LLM_TEMPERATURE=0.3",
        "LLM_TOOL_CHOICE=any",
        "MAX_STEPS=4",
        "REPLY_TIMEOUT_SECONDS=18",
        "# Local testing without the backend's service token. Remove when the backend calls this service.",
        "AUTH_DISABLED=true",
        "# Chat as a mock student at /v1/dev/chat and http://localhost:8010/docs. Never in production.",
        "DEV_ENDPOINTS=true"
    )
    if ($p.KeyVar) {
        $secure = Read-Host "Paste your $($p.Name) API key (hidden)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if (-not $key) { Fail "No key entered." }
        $lines += "$($p.KeyVar)=$key"
    }
    # UTF-8 without BOM, so the first key is read correctly.
    [System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Saved .env (it is in .gitignore)."
}

$model = Read-EnvValue "LLM_MODEL"
if (-not $model) { Fail ".env has no LLM_MODEL. Run .\run.ps1 -Reconfigure." }
$provider = $providers.Values | Where-Object { $_.Model.Split(":")[0] -eq $model.Split(":")[0] } | Select-Object -First 1
if ($provider -and $provider.Package) {
    Step "Installing $($provider.Package) for $model"
    & $py -m pip install --quiet --disable-pip-version-check $provider.Package
    if ($LASTEXITCODE) { Fail "Could not install $($provider.Package)." }
}

# 3. Tests ----------------------------------------------------------------------------------------------------------
Step "Running the tests (no API calls)"
& $py -m pytest -q
if ($LASTEXITCODE) { Fail "Some tests failed. Send the output above to fix it." }

# 4. Run ------------------------------------------------------------------------------------------------------------
if ($Api) {
    Step "Starting the service on http://localhost:8010 (Ctrl+C to stop)"
    & $py -m uvicorn app.main:app --port 8010
}
else {
    Step "Chat with $model  (/reset, /persona, /quit)"
    if ($Persona) { & $py chat_cli.py --persona $Persona } else { & $py chat_cli.py }
}
