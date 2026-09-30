# AI-DND

Türkçe doğal dil ile oynanan, Python kurallar motoru ve Qwen anlatıcısı kullanan bir D&D macera oyunu.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `python main.py` — start the AI-DND terminal game
- `python ai-dnd/run_tests.py` — run the deterministic AI-DND gates
- `python ai-dnd/acceptance_test.py` — run the live Qwen acceptance suite when Ollama and `qwen3:8b` are available
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

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
- The live suites require a reachable Ollama server with `qwen3:8b`; a missing server is an environment limitation, not a deterministic test failure.
- Do not use the prototype `test_combat_v2.py` or `test_combat_v2_fixed.py` as release gates; the authoritative suite is `test_combat_v2_authoritative.py`.
- Keep model output out of mechanical state mutation paths.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
