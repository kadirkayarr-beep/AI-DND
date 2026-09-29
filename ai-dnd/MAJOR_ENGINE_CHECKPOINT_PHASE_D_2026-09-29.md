# Major Engine Checkpoint — Phase D: Combat V3

**Date:** 2026-09-29  
**Result:** Phase C and Phase D gates passed; protected engine snapshot created.

## Protected engine snapshot

- Current `game.py` SHA-256: `be99d1e0f99482715ecff124ebca7d4023baed6129d9378dd1b72e418e4818a4`.
- Snapshot: `game_checkpoint_major_phase_d_20260929.py`; verified byte-identical to `game.py`.
- Manifest: `CHECKPOINT_MAJOR_PHASE_D_20260929.sha256`; records the source and snapshot hashes.
- Historical `CHECKPOINT_CURRENT.sha256` was not modified. It continues to preserve the original pre-engine checkpoint.

## Phase C — Narrative Director V1

- Authenticated live smoke: **PASS** against current `game.py`, using real `qwen3:8b` calls in a disposable in-memory session.
- 11 turns, 21 model calls, maximum 2 calls per turn; zero reported issues.
- Maximum prompt tokens: 3,298; maximum output tokens: 393; maximum estimated Narrative Director total: 10,517, below the 32,768-token gate.
- The return visit restored the canonical tavern location. Relevant NPC-interaction context was selected for the old-memory callback.
- Eight narration responses were replaced by the existing safety fallback. The callback context was selected, but the final response did not explicitly repeat the player name. Neither was reported as a smoke issue; these are retained as quality observations.
- Full sanitized run record: `LIVE_QWEN_SMOKE.md`.

## Phase D — Combat V3 validation

- `cd ai-dnd && python run_tests.py`: **17/17 deterministic gates passed**, including the authoritative Combat V3 tests.
- `cd ai-dnd && python -m unittest discover -s api/tests -p 'test_*.py'`: **124 tests passed**.
- `pnpm --filter @workspace/ai-dnd-experience test`: **10 tests passed**.
- Frontend TypeScript typecheck: **passed**.
- Production build with `PORT=5000 BASE_PATH=/ai-dnd-experience`: **passed**. Vite reported the known non-blocking Tooltip sourcemap warning.
- Python compilation and `git diff --check`: **passed**.
- After refreshing the Replit bearer secret, the artifact-owned FastAPI service was restarted; `/api/game/health` returned HTTP 200 and identified engine `AI-DND`, model `qwen3:8b`.

## Scope boundary

Phases A–D are complete. Spells V1 and later roadmap work were not started.