# Agent guide

## Current work (2026-11-03): read this first, it overrides the older sections below

- Active folder: `C:\Users\Kadir\Desktop\AI-DND-c-merge`, branch `task/c-series-merge`. Do not use `C:\Users\Kadir\Desktop\AI - DND` or `dev/ai-dnd` for current work. Never push or merge to `main` or `dev/ai-dnd`.
- Plan and decisions: `C:\Users\Kadir\Desktop\AI-DND-b01-isolated\YOL_HARITASI_ONERI_20261031.md` (top section) and `HANDOFF.md` (top section). The owner, Kadir, approves plan, scope and spending changes.
- Agent contract and test commands: `C:\Users\Kadir\Desktop\AI-DND-TOOLS\NIGHT_BRIEF.md`.
- Python product tests run only through the guarded WSL launcher, using `bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <slot> AI-DND-c-merge test|par|node|codegen ...` from Git Bash. Never run product tests with plain Windows Python or `dev.ps1`, and never modify `linux_guarded_launcher.py` or the guard.
- Models: a chain of Gemini, then Claude Haiku, then local Gemma, on only in local play (`.\start_local.ps1 -LocalPlay`). Keys live outside the repo and must never be printed or committed.
- One writer at a time in this folder. If another agent is writing here, work in your own worktree and branch.

The sections below are historical (Cursor and Replit era) and are kept for reference only.

## Canonical copy

- Primary Windows development workspace: `C:\Users\Kadir\Desktop\AI - DND`
- Shared active development branch for Cursor and Replit: `dev/ai-dnd` (upstream `origin/dev/ai-dnd`; GitHub `kadirkayarr-beep/AI-DND`)
- `main` is the stable integration branch. Promotion requires validation and explicit owner approval.
- `recovery/a1-freeze-288f5de` and previous Phase 8 worktrees (`AI-DND-phase8`, `AI-DND-phase8-expansion`) are historical, not the active development base.
- Other Desktop trees (`AI-DND-pre04-wave3`, `AI-DND-pre04-repair`, `AI-DND old`, …) are read-only archives. Do not delete them unless the user names the folder.
- Two chats must not write the same folder at once. Neither Cursor nor Replit may overwrite the other's uncommitted work.
- Exchange changes only from the same verified `dev/ai-dnd` commit. GitHub synchronization is controlled; do not force-push, reset, or otherwise destructively sync.

## Canonical docs

Read these first:

- `replit.md` — player path vs Replit/Node workspace
- `ai-dnd/README.md` — terminal, saves, verify
- `ai-dnd/api/README.md` — FastAPI adapter
- `.agents/memory/` — bounded owner notes
- `.cursor/rules/ai-dnd-owners.mdc`

`attached_assets/` is a historical prompt archive. Do not treat it as the current spec unless the user points at a file.

## Branches (no merge implied)

- `dev/ai-dnd` — shared active development branch for Cursor and Replit
- `main` — stable integration target; promote only after validation and explicit owner approval
- `recovery/a1-freeze-288f5de` — historical freeze line (stability, Spells V1, XP V1); not the active base
- `repair/pre04-wave3-conversation-ux` — historical Wave3 conversation UX (other folder)
- Phase 8 worktrees — historical; not the active development base

## How to run

- Player path: `.\start_local.ps1` (Ollama tags, FastAPI `:8008`, experience UI)
- Daily tests: `.\dev.ps1`
- Rare API discover: `.\dev.ps1 -ApiDiscover`
- Live 30-turn smoke: `ai-dnd/api/tests/live_playable_living_world_v1_1_smoke.py` (Ollama required; missing model is BLOCKED, not a daily fail)
- POSIX HttpEvidence: WSL + native Linux copy only

## UI

- Campaign / play UI: `artifacts/ai-dnd-experience`
- `artifacts/ai-dnd-web`: session surface only; no campaign features
- `artifacts/api-server`: not the game API


## Yeni izole serbest diyalog adayı

Güncel kapsam, temiz kampanya, doğrulama ve arşiv durumu: [Oynanabilir diyalog rehberi](ai-dnd/docs/PLAYABLE_DIALOGUE.md). `free_v1` yalnız yeni kampanyada seçilir. Bu adayın hazırlanması canlı kabul, push veya merge anlamına gelmez.

## Çalışma ve test kuralları

Çalışma, test ve ajan disiplini için `CLAUDE.md` ("Çalışma ve test disiplini") ve `docs/agents/implementer-preamble.md` geçerlidir.
