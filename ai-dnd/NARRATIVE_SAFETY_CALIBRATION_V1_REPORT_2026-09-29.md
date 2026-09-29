# AI-DND Narrative Safety Calibration V1

**Date:** 2026-09-29  
**Status:** Complete

## Scope

Calibrate narrator output safety while keeping Python authoritative for game state, player agency, and continuity. Keep the existing two-model-call-per-turn ceiling. No Combat V3, canon, spells, XP, factions, lore, deployment, authentication, or multiplayer roadmap work was started.

The forensic report `NARRATIVE_SAFETY_FORENSIC_REPORT_2026-09-29.md` was not changed. Its uncertainty about runtime safety reasons for original turns 1–4 and 11 remains unresolved; results below describe a new live run and do not reinterpret that trace.

## Changes

- Safety decisions now retain internal reason codes and trigger spans; diagnostics are not added to player-facing responses or world state.
- Unsafe narration can be repaired by removing a sentence that introduces an unsupported player action while preserving surrounding safe scene text. Unrepairable claims use deterministic Python responses.
- Added narrow checks for player agency, canonical state contradictions, and unsupported persistent objects. Temporary atmospheric detail and NPC/background texture remain allowed.
- Added a regression for the Turkish inflection “ilerliyorsun,” which must not be treated as part of an already completed travel action.
- Classified direct queries and skill checks separately for Narrative Director context budgeting.
- Made the narrow “did I tell you my name?” response deterministic. Python uses the latest explicit player-originated disclosure in canonical NPC memory first; if absent, it may use only a selected, post-budget player utterance tagged as narrative continuity and bound to the same stable NPC ID. Model narration and summaries do not establish memory.
- Extended the live Qwen smoke to cover a name recall, travel, skill checks, controlled combat, post-combat narration, and safe state summaries.

World-update authority was reviewed against the live travel flow. A model can propose NPC creation, but Python decides whether travel permits it, validates and sanitizes each proposal, assigns IDs and defaults, and performs the state merge. NPC creation remains a Python-committed update, not a consequence of narration text alone.

## Verification

| Check | Result |
| --- | --- |
| `python -m py_compile game.py api/narrative_director.py live_phase_c_narrative_smoke.py` | Passed |
| Focused safety, Narrative Director, pipeline-port, and authoritative-combat tests | 68 passed |
| `python -m unittest discover -s api/tests` | 125 passed |
| `python test_ai_pipeline_semantics.py` | Passed: 87 semantic, 24 query-grounding, and 18 narrator-safety checks |
| Live Qwen smoke | Passed: 14 turns, 27 model calls, maximum 2 per turn |
| Live smoke token ceilings | Maximum prompt evaluation 3,577; output evaluation 419; Narrative Director estimated total 10,586 |
| Live name-recall continuity | Selected 1 NPC and 2 interactions; deterministic response retained the supported player name |
| FastAPI health endpoints | `/api/health` returned HTTP 200 on ports 8000 and 8008 after restart |
| `git diff --check` | Passed |

The final live smoke reported no issues and recorded six narration replacements. Internal reasons included one invented player action, one combat-result contradiction, one supported player-name recall, one repeated narration, and two unregistered named entities.

## Verification limitation

Root-level `python -m unittest discover` is not a reliable single-process gate in this repository: legacy test modules replace `sys.stdout`, causing closed-stream errors during later test imports, and some script-style checks execute assertions at import time. The two calibration-related semantic assertions surfaced during that attempt were corrected and the semantic script was rerun successfully. The focused Python suites and the full API test discovery passed independently.

Automated architect review was unavailable because subagent review is disabled in the current Free mode. The working diff was reviewed manually.

## Checkpoint handling

The existing `CHECKPOINT_MAJOR_PHASE_D_20260929.sha256` and `CHECKPOINT_CURRENT.sha256` were left unchanged. A separate calibration manifest records hashes for the implementation, tests, report, and the untouched forensic/checkpoint records.