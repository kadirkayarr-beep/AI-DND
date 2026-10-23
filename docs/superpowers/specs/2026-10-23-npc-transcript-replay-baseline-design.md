# NPC transcript replay baseline (design)

Date: 2026-10-23. Scope: measurement only. No product code changes.

## Intent
Find out, per turn, whether the engine or the model produced what the player
saw, using a real player transcript (Quenna / Orryn Hanı session) as the first
scenario. Success: every replayed turn has an owner (deterministic engine,
model, or fallback), repeated and generic outputs are flagged, and the
lockpick loop is reproduced or shown absent.

## Approach (chosen: transcript-first)
- Reuse the Stage A harness pattern (`test_npc_dialogue_stage_a_diagnostic.py`):
  isolated sqlite, ASGI client, scripted model, per-turn engine telemetry.
- New module `api/tests/test_npc_transcript_replay_baseline.py`.
- The scripted model returns the NPC lines the real model produced in the
  transcript, so the engine's acceptance of them is what is measured.
- Each turn is classified: `owner` (deterministic / model / fallback),
  `generic` (fallback or lore-refusal sentence), `clarification`, `repeat`
  (same narration as an earlier turn).
- Output: per-turn JSON plus `summary.json` in `NPC_STAGE_A_EVIDENCE_DIR`.
- Diagnostic only: asserts harness integrity (HTTP 200, protected fields),
  never that a known defect is absent. Known defects are tagged, not failed.

## Out of scope
Real Qwen run (needs the owner's machine and Ollama), fixes to the engine,
the "creativity" workstream (separate design, uses this data).

## Known limits
Model text is scripted, so this shows engine behaviour, not Qwen quality.
