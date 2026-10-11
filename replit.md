# AI-DND

Türkçe doğal dil ile oynanan, Python kurallar motoru ve Qwen anlatıcısı kullanan bir D&D macera oyunu.

## Player path (canonical)

The playable loop is Python FastAPI over `GameSession`, a local sqlite campaign store, Ollama `qwen3:8b`, and the campaign UI in `artifacts/ai-dnd-experience`.

- Start everything: `.\start_local.ps1` (Ollama `11434/api/tags`, FastAPI default `:8008`, experience Vite).
- Daily tests: `.\dev.ps1` (UTF-8, `python -u ai-dnd/run_tests.py`).
- Health: `GET http://127.0.0.1:8008/api/game/health` and `GET http://127.0.0.1:11434/api/tags`.
- Do not use interactive `ollama run`; it is not the API the game calls.
- `artifacts/api-server` (Express `:5000`) is **not** the game API. Do not add campaign routes there.
- `DATABASE_URL` / Postgres is **not** required for this player path. Campaign state uses `AI_DND_CAMPAIGN_DB` (sqlite) when set.
- Product UI: `artifacts/ai-dnd-experience`. `artifacts/ai-dnd-web` is a session-only surface; do not add campaign features there.

## Run & Operate (Replit / Node workspace)

These commands belong to the Node/pnpm workspace. They do not replace the FastAPI player path above.

- `pnpm --filter @workspace/api-server run dev` — Node artifact service (port 5000), not the game engine
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `python main.py` — start the AI-DND terminal game
- `python ai-dnd/run_tests.py` — run the deterministic AI-DND gates (prefer `.\dev.ps1` on Windows)
- `python ai-dnd/run_tests.py --list` — list release gates without executing them
- `python ai-dnd/run_tests.py --suite prototype` — run historical prototype diagnostics, not release gates
- `python ai-dnd/acceptance_test.py` — run the live Qwen acceptance suite when Ollama and `qwen3:8b` are available
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env for the Node db package only: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `ai-dnd/game.py` — current game engine and terminal entry point
- `ai-dnd/run_tests.py` — portable deterministic test runner
- `ai-dnd/test_combat_v2_authoritative.py` — authoritative combat contract
- `ai-dnd/legacy_debug/` — historical debugging scripts, not release gates
- `ai-dnd/_source_backup/` — uploaded source archive kept as a recovery copy
- `main.py` — workspace-level launcher for the game

## Architecture decisions

- Python owns HP, AC, dice, combat, inventory, doors, locations, NPC IDs, and committed world changes.
- Qwen parses Turkish intent and produces narration; model output is validated before it can affect persistent state.
- `game.py` is import-safe: importing it creates a quiet deterministic default state; interactive character creation runs only through the program entry point.
- Deterministic tests do not require an Ollama service; live suites are separate and require `qwen3:8b`.
- Canonical IDs and validation are preferred over trusting model-provided entity data.

## Product

AI-DND is a Turkish-language terminal D&D game. Players create a character, describe actions naturally, explore canonical or dynamically proposed locations, speak with NPCs, inspect environments, manage items, and resolve combat through deterministic D&D mechanics.

## Release versioning

- Current release identity: AI-DND v0.6.1-alpha, Internal Build V15.
- Do not increase the public version for implementation work alone.
- Playable Living World V1 passed its deterministic, real-Qwen, continuity, fallback, and manual narration review gates; see `ai-dnd/PLAYABLE_LIVING_WORLD_V1_RELEASE_REPORT_2026-09-30.md`.
- Playable Living World V1.1 passed final solo web-client verification; see `ai-dnd/PLAYABLE_LIVING_WORLD_V1_1_FINAL_REPORT_2026-09-30.md`.
- Tie future public version bumps to a meaningful playable milestone and document them in the phase report or changelog.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- Run deterministic gates from the repository root with `python ai-dnd/run_tests.py`.
- On Windows run daily gates with `.\dev.ps1` so UTF-8 is set; raw `python ai-dnd/run_tests.py` can fail on emoji encode.
- The deterministic runner scans every configured gate before execution and rejects duplicate module functions and class methods with file and definition-line diagnostics. Control-flow blocks share their enclosing namespace; nested local functions and separate module/class scopes do not collide.
- Full `unittest discover` under `ai-dnd/api/tests` is optional and noisy; expected negative-path ERROR logs are not suite failures.
- The live suites require a reachable Ollama server with `qwen3:8b`; a missing server is an environment limitation, not a deterministic test failure.
- Do not use the prototype `test_combat_v2.py` or `test_combat_v2_fixed.py` as release gates; the authoritative suite is `test_combat_v2_authoritative.py`.
- The runner defaults to `--suite release`, retaining `test_combat.py` and the authoritative combat suite. Prototype checks require `--suite prototype`; their failures stay nonzero but separate from release results.
- Keep model output out of mechanical state mutation paths.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
