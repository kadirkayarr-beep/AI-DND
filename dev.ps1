# Daily developer entry for AI-DND (Windows).
# UTF-8 is required; without it pipeline tests fail on dice emoji.
param(
    [switch]$List,
    [switch]$ApiDiscover
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

if ($List) {
    python -u ai-dnd/run_tests.py --list
    exit $LASTEXITCODE
}

if ($ApiDiscover) {
    Write-Host "API discover is the rare/full suite: long, log-noisy."
    Write-Host "Expected CampaignStorageError / CombatRequestError lines are negative-path logs, not automatic failures."
    Write-Host "POSIX SIGTERM/SIGKILL cases skip on Windows. Under WSL copy the tree to a native Linux path (not /mnt/c worktree)."
    Write-Host "Live 30-turn smokes are separate; do not treat them as this discover run."
    Set-Location (Join-Path $root "ai-dnd")
    python -u -m unittest discover -s api/tests -p "test_*.py" -q
    exit $LASTEXITCODE
}

Write-Host "Daily release gates (UTF-8)."
python -u ai-dnd/run_tests.py
exit $LASTEXITCODE
