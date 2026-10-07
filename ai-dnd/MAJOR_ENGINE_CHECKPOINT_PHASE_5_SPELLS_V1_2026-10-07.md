# Major Engine Checkpoint — Phase 5: Spells V1

**Date:** 2026-10-07  
**Result:** Phase 5 gate passed. Phase 6 was not started.

Historical `CHECKPOINT_CURRENT.sha256` was not modified.

## What this phase owns

Python resolves four known spells: Fire Bolt, Sacred Flame, Magic Missile, and Cure Wounds. A character can cast one only when it is in that character’s saved cantrips or spells. Other catalog spells are rejected with no HP change, no slot spend, and no combat start.

Leveled casts spend one 1st-level slot after a legal resolution, including a miss or a successful save. Cantrips do not spend a slot. There is no rest recovery. Save format version is 4. Versions 1–3 still load and migrate to an empty spell list and zero remaining slots.

## Gate

- `python run_tests.py`: **19/19 deterministic gates passed**, including Combat V3 weapon attacks and `test_spells_v1.py`.
- `python -m unittest discover -s api/tests -p "test_*.py"`: **245 tests passed**.
- Experience client tests: **17 passed**.
- Experience and web TypeScript typechecks: **passed**.
- OpenAPI client generation: **passed**.
- Production builds for `ai-dnd-experience` (`PORT=5000 BASE_PATH=/ai-dnd-experience`) and `ai-dnd-web` (`PORT=5000 BASE_PATH=/ai-dnd-web`): **passed**. Vite reported the known non-blocking Tooltip sourcemap warning.

## Browser check

A local authenticated-adapter session with Ollama `qwen3:8b` resumed a cleric who knew Cure Wounds.

- The cast button sent `I cast Cure Wounds on myself`. The server healed 14, then 13, spent both 1st-level slots, and the combat record showed the spell, the healing, and that a slot was spent. Hit points stayed capped at maximum.
- The next cast was rejected: the record showed “Yuva yok” and “yuva harcanmadı”, and the remaining slot count stayed 0.

## Scope boundary

Phase 6 (XP / leveling) was not started. Living-world smoke reports were left out of this change.
