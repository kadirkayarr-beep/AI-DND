---
name: ai-dnd-testing
description: How to run AI-DND tests on Windows (daily gates, API discover, live smoke). Use when running, debugging or interpreting tests in ai-dnd/.
---

# AI-DND testing

Run from the repo root `C:\Users\Kadir\Desktop\AI - DND` in PowerShell.

| Goal | Command |
|------|---------|
| Daily release gates | `.\dev.ps1` |
| List daily tests | `.\dev.ps1 -List` |
| Full API suite (rare, long, noisy) | `.\dev.ps1 -ApiDiscover` |
| Live 30-turn smoke | `python ai-dnd/api/tests/live_playable_living_world_v1_1_smoke.py` (Ollama required) |

## Rules
- UTF-8 is mandatory (`PYTHONUTF8=1`); `dev.ps1` sets it. Without it tests fail on dice emoji.
- `CampaignStorageError` / `CombatRequestError` log lines in discover are negative-path logs, not failures.
- POSIX SIGTERM/SIGKILL tests skip on Windows; run them only in WSL on a native Linux copy (not `/mnt/c`).
- Live smoke with a missing Ollama model is BLOCKED, not a daily failure.
- Never push or reset git to "fix" tests; branch is `dev/ai-dnd`.
