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
It never returns them to clients. The running game selects `gemma4-12b-dm`; the
engine's internal tag stays `qwen3:8b`, and the adapter translates it.
For a local comparison, the trusted server process may set
`AI_DND_OLLAMA_MODEL` to `gemma4-fast`, `qwen3:8b`, `qwen3.5:4b-q4_K_M` or `qwen3.5:9b-q4_K_M`.
The selected tag must already be installed: there is no automatic download. The only
fallback is `gemma4-12b-dm` to `gemma4-fast` (below). Invalid configuration fails closed. HTTP clients cannot select models.
Health metadata and request logs report the real selected tag; the historical
engine tag is translated only inside the adapter. This does not establish model
quality or authorize deployment. Legacy fixed-8B smoke scripts must not be used
to certify a different model without updating their expected identity.
Remove the optional process setting to return to the default on next startup.
Optional `AI_DND_CAMPAIGN_DB` selects the sqlite campaign file.
Do not use interactive `ollama run`; probe `GET http://127.0.0.1:11434/api/tags`.

## Local Gemma 12B (`gemma4-12b-dm`)

Since November 2026 the last link of the model chain is `gemma4-12b-dm`, an Ollama model the owner built from
Gemma 4 12B IT, IQ3_M GGUF (`hf.co/AtomicChat/gemma-4-12B-it-GGUF:IQ3_M`). In the owner's DM test it did
clearly better than the E4B: it kept the dice rule, remembered the NPC's name and what was said, and kept the
scene consistent. Ollama lists it as `gemma4-12b-dm:latest`.

Measured on the owner's PC (RTX 3060 Ti 8 GB, Ollama 0.40.15): about 45 tok/s generation with thinking off,
a typical reply in 4-5 s, about 7200 MiB of the 8192 MiB card in use. The margin is thin and the driver's
system-memory fallback is off: a model that does not fit fails with an error instead of slowing down. One first
request after loading once took about 38 s (most likely waiting for another model to leave VRAM); it did not repeat.

Modelfile (the two `FROM` lines are the model and its vision projector blobs; the projector stays unused):

```
FROM <gemma-4-12B-it IQ3_M blob>
FROM <projector blob>
TEMPLATE "{{ if .System }}<bos><|turn>system
{{ .System }}<turn|>
{{ end }}{{ if .Prompt }}<|turn>user
{{ .Prompt }}<turn|>
{{ end }}<|turn>model
{{ .Response }}<turn|>
"
RENDERER gemma4
PARSER gemma4
PARAMETER num_gpu 99
PARAMETER stop <turn|>
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

What the adapter does for it (`api/ollama_adapter.py`; Gemini and Claude Haiku and their prompts are untouched):

- The window is 8K (`num_ctx` 8192) on every call to the 12B, the warm-up and the character-note suggestion
  included; a caller cannot change it, because a bigger window does not fit the card and any other value makes
  Ollama load the model again.
- 8K limit: system prompt, world state, history and reply must fit 8192 tokens. At about one token per three
  characters of Turkish, the local prompt may be (8192 − reply) × 3 characters, where the reply keeps at least
  600 tokens (the narration asks for 700). When it is bigger, the oldest RECENT NARRATION lines are dropped
  (never the newest); the cloud models still get the whole prompt. Each call has its own window, so the turn's
  second call (intent or front reading, NPC speech, arrival narration) counts on its own. Measured on a fixed
  town over 96 turns: the largest narration prompt was 17 841 characters, which the 12B counted as 5221 tokens
  (about 3.4 characters a token), so 5921 with the 700-token reply; reading calls stayed under 9300 characters.
- Every request carries `think: false` (unless a caller asks for `True`) and `keep_alive: "30m"`; local calls,
  the suggestion's included, go one at a time through one queue.
- At API start (an adapter built from the environment) one tiny background request loads the model, so the first
  real local answer does not wait for the load. The local timeout is 90 s for every request, the first included.
- If Ollama answers that the 12B cannot run (not installed, out of VRAM, load error), the same call goes to
  `gemma4-fast` with its 16K window, the log says `falling back to gemma4-fast`, and the 12B rests for 10 minutes
  before it is tried again. A dead service or a timeout does not switch models. `gemma4-fast` stays installed.
- The local narration's system prompt ends with the owner's local-only rules (short plain sentences, Turkish NPC
  and place names, no English terms in brackets, rule names in Turkish, "sen" to the player throughout). The
  intent and front readings, and the cloud models, do not get them.

## Local Gemma E4B (`gemma4-fast`, fallback)

`gemma4-fast` is an Ollama model the owner built from `gemma4:e4b`
(Q4_K_M). Ollama lists it as `gemma4-fast:latest`; the adapter and `start_local.ps1` accept that form.
Measured on the owner's PC (RTX 3060 Ti 8 GB, 16 GB RAM, Ollama 0.40.15):
thinking off about 56 tok/s, thinking on about 129 tok/s (speculative decoding), prompt processing about
1200 tok/s, about 5.6 GB VRAM at 8K context and about 6 GB at 16K. The NVIDIA driver's system-memory
fallback is off, so a model that no longer fits VRAM fails with an error instead of slowing down.

Modelfile, as `ollama show gemma4-fast --modelfile` prints it (the `DRAFT` blob is the speculative-decoding
draft model; its origin is not recorded in this repository):

```
FROM gemma4:e4b
DRAFT <draft model blob>
TEMPLATE {{ .Prompt }}
RENDERER gemma4
PARSER gemma4
PARAMETER top_p 0.95
PARAMETER draft_num_predict 3
PARAMETER num_batch 512
PARAMETER num_ctx 16384
PARAMETER num_gpu 99
PARAMETER temperature 1
PARAMETER top_k 64
```

Ollama user environment variables: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`,
`OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`.

What the adapter does for it, as the 12B's fallback or when selected (`api/ollama_adapter.py`):

- Calls go to Ollama's native `/api/chat` through the `ollama` Python client, with `think` set explicitly
  (`False` unless a caller asks for `True`; Gemma 4 thinks by default) and `num_ctx` 16384.
- `keep_alive` is `30m`, so the model is not unloaded five minutes after the last turn.
- Local calls run one at a time (one lock): Ollama serves one request here, so parallel turns queue.
- Local-only: with one loaded model, another local tag (`qwen3*`) reloads the model on every switch.
- The adapter warns in the log when the estimated prompt (about one token per three characters) plus the
  reply budget exceeds the window, and when a reply used the whole window. Before that, the same history cut as
  for the 12B applies against its 16K window (in practice it never triggers there).
- No image or audio field is sent; the model's vision and audio projector stay unused.

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

## Yeni izole serbest diyalog adayı

Güncel kapsam, temiz kampanya, doğrulama ve arşiv durumu: [Oynanabilir diyalog rehberi](../docs/PLAYABLE_DIALOGUE.md). `free_v1` yalnız yeni kampanyada seçilir. Bu adayın hazırlanması canlı kabul, push veya merge anlamına gelmez.
