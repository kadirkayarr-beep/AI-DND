# Start the player path: Ollama check, FastAPI, experience UI.
# Does not start artifacts/api-server. Does not run `ollama run`.
param(
    [int]$ApiPort = 8008,
    [int]$UiPort = 22785,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$requiredModel = if ($env:AI_DND_OLLAMA_MODEL) { $env:AI_DND_OLLAMA_MODEL } else { "qwen3.5:9b-q4_K_M" }
if ($requiredModel -cnotin @("qwen3:8b", "qwen3.5:4b-q4_K_M", "qwen3.5:9b-q4_K_M")) {
    Write-Host "NOT READY: unsupported AI_DND_OLLAMA_MODEL. No services were started."
    exit 1
}
$root = $PSScriptRoot
Set-Location $root

function Test-HttpOk([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-SelectedGameApi([string]$Url) {
    try {
        $h = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        return ($h.status -ceq "ok" -and $h.engine -ceq "AI-DND" -and $h.model -ceq $requiredModel)
    } catch {
        return $false
    }
}

Write-Host "Checking Ollama http://127.0.0.1:11434/api/tags (do not use 'ollama run')"
if (-not (Test-HttpOk "http://127.0.0.1:11434/api/tags")) {
    Write-Host "NOT READY: Ollama is not answering /api/tags. Start the Ollama service, then retry."
    exit 1
}
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    $names = @($tags.models | ForEach-Object { if ($_.name) { $_.name } else { $_.model } })
    if ($names -cnotcontains $requiredModel) {
        Write-Host "NOT READY: selected model $requiredModel is not in /api/tags. No model will be downloaded."
        exit 1
    }
} catch {
    Write-Host "NOT READY: could not parse /api/tags"
    exit 1
}
Write-Host "Ollama OK (selected model $requiredModel present)."

if (-not $env:OLLAMA_HOST) {
    $env:OLLAMA_HOST = "http://127.0.0.1:11434"
}
# The API selects a model only through its Ollama adapter, which needs a token.
# On loopback the project's smokes use the placeholder "loopback"; Ollama ignores it.
if (-not $env:OLLAMA_PROXY_TOKEN -and $env:OLLAMA_HOST -match '^https?://(127\.0\.0\.1|localhost|\[::1\])(:|/|$)') {
    $env:OLLAMA_PROXY_TOKEN = "loopback"
}
$env:AI_DND_OLLAMA_MODEL = $requiredModel
$env:AI_DND_API_ORIGIN = "http://127.0.0.1:$ApiPort"

$health = "http://127.0.0.1:$ApiPort/api/game/health"
$existingApi = Test-HttpOk $health
if ($existingApi -and -not (Test-SelectedGameApi $health)) {
    Write-Host "NOT READY: the existing API does not report AI-DND with selected model $requiredModel. It was not restarted. Check the running instance before continuing."
    exit 1
}
if (-not $existingApi) {
    Write-Host "Starting FastAPI on :$ApiPort"
    $apiArgs = @(
        "-m", "uvicorn", "api.main:app",
        "--host", "127.0.0.1",
        "--port", "$ApiPort"
    )
    Start-Process -FilePath "python" -ArgumentList $apiArgs -WorkingDirectory (Join-Path $root "ai-dnd") -WindowStyle Minimized
}

$uiUrl = "http://127.0.0.1:$UiPort/ai-dnd-experience/"
$uiHealth = "http://127.0.0.1:$UiPort/api/game/health"
$uiListening = Test-HttpOk $uiUrl
if (-not $uiListening) {
    Write-Host "Starting experience UI on :$UiPort"
    $env:PORT = "$UiPort"
    $env:BASE_PATH = "/ai-dnd-experience/"
    Start-Process -FilePath "corepack" -ArgumentList @(
        "pnpm", "--filter", "@workspace/ai-dnd-experience", "run", "dev"
    ) -WorkingDirectory $root -WindowStyle Minimized
}

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$apiOk = $false
$uiOk = $false
while ((Get-Date) -lt $deadline) {
    $apiOk = Test-SelectedGameApi $health
    $uiOk = ((Test-HttpOk $uiUrl) -and (Test-SelectedGameApi $uiHealth))
    if ($apiOk -and $uiOk) { break }
    Start-Sleep -Seconds 2
}

Write-Host "FastAPI  $health  $(if ($apiOk) { 'READY' } else { 'NOT READY' })"
Write-Host "UI       $uiUrl  $(if ($uiOk) { 'READY' } else { 'NOT READY' })"
if ($apiOk -and $uiOk) {
    Write-Host "READY within $WaitSeconds s. Game API is FastAPI, not artifacts/api-server."
    exit 0
}
Write-Host "NOT READY within $WaitSeconds s."
exit 1
