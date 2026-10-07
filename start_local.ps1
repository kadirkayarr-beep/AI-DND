# Start the player path: Ollama check, FastAPI, experience UI.
# Does not start artifacts/api-server. Does not run `ollama run`.
param(
    [int]$ApiPort = 8008,
    [int]$UiPort = 22785,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
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

Write-Host "Checking Ollama http://127.0.0.1:11434/api/tags (do not use 'ollama run')"
if (-not (Test-HttpOk "http://127.0.0.1:11434/api/tags")) {
    Write-Host "NOT READY: Ollama is not answering /api/tags. Start the Ollama service, then retry."
    exit 1
}
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -notcontains "qwen3:8b" -and -not ($names | Where-Object { $_ -like "qwen3:8b*" })) {
        Write-Host "NOT READY: qwen3:8b is not in /api/tags. Models: $($names -join ', ')"
        exit 1
    }
} catch {
    Write-Host "NOT READY: could not parse /api/tags"
    exit 1
}
Write-Host "Ollama OK (qwen3:8b present)."

if (-not $env:OLLAMA_HOST) {
    $env:OLLAMA_HOST = "http://127.0.0.1:11434"
}
$env:AI_DND_API_ORIGIN = "http://127.0.0.1:$ApiPort"

$health = "http://127.0.0.1:$ApiPort/api/game/health"
if (-not (Test-HttpOk $health)) {
    Write-Host "Starting FastAPI on :$ApiPort"
    $apiArgs = @(
        "-m", "uvicorn", "api.main:app",
        "--host", "127.0.0.1",
        "--port", "$ApiPort"
    )
    Start-Process -FilePath "python" -ArgumentList $apiArgs -WorkingDirectory (Join-Path $root "ai-dnd") -WindowStyle Minimized
}

$uiUrl = "http://127.0.0.1:$UiPort/ai-dnd-experience/"
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
    $apiOk = Test-HttpOk $health
    $uiOk = Test-HttpOk $uiUrl
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
