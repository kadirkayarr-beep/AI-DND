# AI-DND FastAPI adapter

This API is a thin HTTP layer over the existing Python `GameSession` engine.
The engine remains authoritative; clients can submit only a natural-language
player message.

## Run

From the repository root:

```sh
cd ai-dnd
python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

The API reads `OLLAMA_HOST` and `OLLAMA_PROXY_TOKEN` from the server environment.
It never returns them to clients. The required model remains `qwen3:8b`.

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