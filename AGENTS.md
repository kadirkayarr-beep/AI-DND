# Agent guide

## Canonical copy

- Folder: `C:\Users\Kadir\Desktop\AI - DND`
- Branch: `recovery/a1-freeze-288f5de`
- Other Desktop trees (`AI-DND-pre04-wave3`, `AI-DND-pre04-repair`, `AI-DND old`, …) are read-only archives. Do not delete them unless the user names the folder.
- Two chats must not write the same folder at once.
- Do not merge to `main` unless the user asks.

## Canonical docs

Read these first:

- `replit.md` — player path vs Replit/Node workspace
- `ai-dnd/README.md` — terminal, saves, verify
- `ai-dnd/api/README.md` — FastAPI adapter
- `.agents/memory/` — bounded owner notes
- `.cursor/rules/ai-dnd-owners.mdc`

`attached_assets/` is a historical prompt archive. Do not treat it as the current spec unless the user points at a file.

## Branches (no merge implied)

- `recovery/a1-freeze-288f5de` — product tree: stability, Spells V1, XP V1
- `repair/pre04-wave3-conversation-ux` — Wave3 conversation UX (other folder)
- `main` — behind; not the daily base

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
