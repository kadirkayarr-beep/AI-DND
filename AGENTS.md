# Agent guide

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
