# Playable Living World V1 — release review

**Date:** 30 September 2026  
**Release identity:** AI-DND v0.6.0-alpha, Internal Build V14  
**Previous identity:** AI-DND v0.5.0-alpha, Internal Build V13

## Decision

The bounded Playable Living World V1 release gate passed. This milestone does not add spells, XP, an economy, another lore region, or broader game engines.

## Verification

- `python ai-dnd/run_tests.py`: all 18 deterministic gates passed.
- `cd ai-dnd && python -m unittest discover -s api/tests -p 'test_*.py' -v`: 162 API tests passed.
- Disposable real-model smoke: `qwen3:8b`, 36 turns, temporary campaign database.
- Ordinary fallback candidates: 1, within the limit of 2.
- Resume comparisons passed for world state, lore, memory, turn history, and combat history.
- The final return reached the original tavern with its original NPC and feature IDs.
- The unsupported Turkish route-distance request was rejected by the lore guard without changing world/lore state beyond the expected turn-index advance.
- Evidence: `ai-dnd/reports/playable-living-world-v1-smokes/1790732266826650921-2674c06c/summary.json` and the adjacent sanitized turn evidence.

## Manual narration review

All 36 narrations were reviewed from the transient `--review-narrations` output. No narration was copied into this report or the smoke evidence. Unsupported route, ruler/deity, and purchase claims were refused; the loaded Neverwinter canon response matched its retrieved fact. The city-return narration's additional street and guard details were accepted as bounded `PROCEDURAL_LOCAL_FICTION`, not setting canon or a new lore region.

The smoke summary remains `REVIEW_PENDING` with no incomplete evidence because the harness does not provide a separate manual-review finalization command. This report records the completed manual review; it does not alter the append-only smoke summary.