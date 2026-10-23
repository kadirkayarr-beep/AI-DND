# AI-DND FastAPI adapter

This API is a thin HTTP layer over the existing Python `GameSession` engine.
The engine remains authoritative; clients can submit only a natural-language
player message.

This is the **player-path game API**. `artifacts/api-server` (Express) is a
separate Node artifact and must not receive campaign routes.

## Run

From the repository root, prefer `.\start_local.ps1` (default listen `:8008`).

Manual:

```sh
cd ai-dnd
python -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT:-8008}"
```

Health: `GET /api/game/health` (also aliased as `/api/health`).

The API reads `OLLAMA_HOST` and `OLLAMA_PROXY_TOKEN` from the server environment.
It never returns them to clients. The default model remains `qwen3:8b`.
For an isolated local comparison, the trusted server process may set
`AI_DND_OLLAMA_MODEL` to `qwen3.5:4b-q4_K_M` or `qwen3.5:9b-q4_K_M`.
The selected tag must already be installed: there is no automatic download or
fallback. Invalid configuration fails closed. HTTP clients cannot select models.
Health metadata and request logs report the real selected tag; the historical
engine tag is translated only inside the adapter. This does not establish model
quality or authorize deployment. Legacy fixed-8B smoke scripts must not be used
to certify a different model without updating their expected identity.
Remove the optional process setting to return to the default on next startup.
Optional `AI_DND_CAMPAIGN_DB` selects the sqlite campaign file.
Do not use interactive `ollama run`; probe `GET http://127.0.0.1:11434/api/tags`.

## Deterministic API tests

From the repository root:

```sh
python -m unittest discover -s ai-dnd/api/tests -v
```

These unit tests use a fake model client. They are not live-model validation.

## Live HTTP-to-Qwen smoke

Start the FastAPI server, then run:

```sh
python ai-dnd/api/live_smoke.py
```

The smoke sends real HTTP requests through FastAPI and uses the configured
authenticated Ollama service; it does not mock the parser or model.