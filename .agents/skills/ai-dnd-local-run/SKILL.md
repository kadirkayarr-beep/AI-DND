---
name: ai-dnd-local-run
description: Start and troubleshoot the AI-DND player path (Ollama, FastAPI :8008, experience UI :22785). Use when launching the game locally or diagnosing NOT READY.
---

# AI-DND local run

Start everything: `.\start_local.ps1` (params: `-ApiPort 8008 -UiPort 22785 -WaitSeconds 30`).

## What it does
1. Checks Ollama at `http://127.0.0.1:11434/api/tags` and requires model `qwen3:8b`. Never use `ollama run`.
2. Starts FastAPI (`python -m uvicorn api.main:app`, cwd `ai-dnd`) on `:8008`; health: `/api/game/health`.
3. Starts UI via `corepack pnpm --filter @workspace/ai-dnd-experience run dev` at `http://127.0.0.1:22785/ai-dnd-experience/`.

## Troubleshooting
- "Ollama is not answering": start the Ollama service, retry.
- "qwen3:8b is not in /api/tags": `ollama pull qwen3:8b`.
- UI NOT READY: run `pnpm install` at the root.
- The game API is FastAPI. `artifacts/api-server` is NOT the game API; `artifacts/ai-dnd-web` is a session surface only.
