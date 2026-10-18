# Start the player path: Ollama check, FastAPI, experience UI.
# Does not start artifacts/api-server. Does not run `ollama run`.
param(
    [int]$ApiPort = 8008,
    [int]$UiPort = 22785,
    [int]$WaitSeconds = 30,
    # By default an API/UI already listening on these ports is stopped and started
    # again, because a running process keeps the settings it started with.
    [switch]$KeepRunning
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

# Logs of the background processes: they run hidden, so without these a failure
# would be invisible. Shown automatically when something is NOT READY.
$logDir = Join-Path $env:TEMP "ai-dnd-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$apiOut = Join-Path $logDir "api.out.log"
$apiErr = Join-Path $logDir "api.err.log"
$uiOut = Join-Path $logDir "ui.out.log"
$uiErr = Join-Path $logDir "ui.err.log"

function Stop-PortListener([int]$Port) {
    try {
        $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        return
    }
    foreach ($ownerId in $owners) {
        if ($ownerId -gt 4) {
            try {
                Stop-Process -Id $ownerId -Force -ErrorAction Stop
                Write-Host "Stopped old process $ownerId listening on :$Port"
            } catch {
                Write-Host "Could not stop process $ownerId on :$Port (close it by hand, then retry)"
            }
        }
    }
}

function Test-PythonModules {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & python -c "import uvicorn, fastapi, httpx, ollama" 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Show-Logs {
    foreach ($log in @($apiOut, $apiErr, $uiOut, $uiErr)) {
        if ((Test-Path $log) -and ((Get-Item $log).Length -gt 0)) {
            Write-Host "--- $log (last lines)"
            Get-Content $log -Tail 15
        }
    }
}

# Local settings that must not be committed (Clerk sign-in) live in .env.local at
# the repository root: one NAME=value per line, # for comments. A value already
# set in this window wins. See .env.example.
$envFile = Join-Path $root ".env.local"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        # Trim also drops a UTF-8 byte-order mark that some editors put on line 1.
        $text = $line.Trim().TrimStart([char]0xFEFF)
        if ($text -eq "" -or $text.StartsWith("#")) { continue }
        $index = $text.IndexOf("=")
        if ($index -lt 1) { continue }
        $name = $text.Substring(0, $index).Trim()
        $value = $text.Substring($index + 1).Trim().Trim('"')
        if (-not (Test-Path "Env:$name")) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
    Write-Host "Loaded local settings from $envFile"
}
if (-not $env:VITE_CLERK_PUBLISHABLE_KEY -or -not $env:AI_DND_AUTH_MODE) {
    Write-Host "NOT READY: sign-in is not configured. The game shows 'Giris su anda kullanilamiyor' without it."
    Write-Host "Create $envFile with the Clerk settings listed in .env.example, then run this script again."
    exit 1
}

# The API refuses to open any campaign storage unless AI_DND_CAMPAIGN_DB is set
# (without it every campaign request answers 503 and the game cannot start a
# campaign or open the saves list). Default: a database inside THIS checkout.
# To play your existing campaigns, set AI_DND_CAMPAIGN_DB in .env.local to that file.
if (-not $env:AI_DND_CAMPAIGN_DB) {
    $savesDir = Join-Path $root "ai-dnd\saves"
    New-Item -ItemType Directory -Force -Path $savesDir | Out-Null
    $env:AI_DND_CAMPAIGN_DB = Join-Path $savesDir "campaigns.sqlite3"
}
Write-Host "Campaign database: $env:AI_DND_CAMPAIGN_DB"

if (-not $KeepRunning) {
    Stop-PortListener $ApiPort
    Stop-PortListener $UiPort
    Start-Sleep -Seconds 1
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

# First-person NPC speech for "Say" turns is on by default for the player path.
# To turn it off, set AI_DND_NPC_SPEECH=0 in this PowerShell window before
# running this script. It only reaches a FastAPI process started by this script:
# if the API is already running, stop it first so it restarts with this setting.
if (-not $env:AI_DND_NPC_SPEECH) {
    $env:AI_DND_NPC_SPEECH = "1"
}
Write-Host "NPC speech (AI_DND_NPC_SPEECH): $env:AI_DND_NPC_SPEECH"

$health = "http://127.0.0.1:$ApiPort/api/game/health"
if (-not (Test-HttpOk $health)) {
    if (-not (Test-PythonModules)) {
        Write-Host "NOT READY: Python (python) is missing or lacks uvicorn/fastapi/httpx/ollama."
        Write-Host "Try: python -m pip install fastapi uvicorn httpx ollama pyjwt pyyaml cryptography"
        exit 1
    }
    Write-Host "Starting FastAPI on :$ApiPort (logs: $logDir)"
    $apiArgs = @(
        "-m", "uvicorn", "api.main:app",
        "--host", "127.0.0.1",
        "--port", "$ApiPort"
    )
    Start-Process -FilePath "python" -ArgumentList $apiArgs -WorkingDirectory (Join-Path $root "ai-dnd") -WindowStyle Hidden -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
}

$uiUrl = "http://127.0.0.1:$UiPort/ai-dnd-experience/"
$uiListening = Test-HttpOk $uiUrl
if (-not $uiListening) {
    Write-Host "Starting experience UI on :$UiPort"
    $env:PORT = "$UiPort"
    $env:BASE_PATH = "/ai-dnd-experience/"
    $pnpmLauncher = $null
    if (Get-Command corepack -ErrorAction SilentlyContinue) {
        $pnpmLauncher = @("corepack", "pnpm")
    } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $pnpmLauncher = @("pnpm")
    }
    if (-not $pnpmLauncher) {
        Write-Host "NOT READY: neither corepack nor pnpm was found. Install pnpm, then run 'pnpm install' once in $root."
        exit 1
    }
    if (-not (Test-Path (Join-Path $root "node_modules"))) {
        Write-Host "NOT READY: node_modules is missing. Run 'pnpm install' once in $root, then retry."
        exit 1
    }
    # cmd.exe /c: pnpm and corepack are .cmd shims that Start-Process cannot run directly.
    $uiArgs = @("/c") + $pnpmLauncher + @(
        "--filter", "@workspace/ai-dnd-experience", "run", "dev"
    )
    Start-Process -FilePath "cmd.exe" -ArgumentList $uiArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $uiOut -RedirectStandardError $uiErr
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
Show-Logs
exit 1
