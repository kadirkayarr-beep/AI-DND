---
name: ai-dnd-local-run
description: Start and troubleshoot the AI-DND player path in local play (model chain, FastAPI, experience UI :22785). Use when launching the game locally or diagnosing NOT READY.
---

# AI-DND local run

Current way (2026-11-03): from `C:\Users\Kadir\Desktop\AI-DND-c-merge` in PowerShell run `.\start_local.ps1 -LocalPlay`.

## What it does
1. Turns on the model chain: Gemini first, then Claude Haiku, then local Gemma (`gemma4:e4b` through Ollama). Keys are read from files outside the repo and are never printed.
2. Starts the game API through `python -m api.local_play` (cwd `ai-dnd`), bound to loopback. Plain `uvicorn api.main:app` refuses requests without auth, by design.
3. Starts the UI at `http://127.0.0.1:22785/ai-dnd-experience/`.
4. Saves go to `%LOCALAPPDATA%\AI-DND\local-play.sqlite3`. These are the owner's real saves: agents must use their own temp `AI_DND_CAMPAIGN_DB` and never touch this file.

## Troubleshooting
- Gemini rate limited: the chain falls back to Haiku, then Gemma; this is expected.
- Gemma fallback needs Ollama running with `gemma4:e4b`; never use `ollama run`.
- UI NOT READY: run `pnpm install` at the root.
- The game API is FastAPI. `artifacts/api-server` is NOT the game API; `artifacts/ai-dnd-web` is a session surface only.
