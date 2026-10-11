# Major Engine Checkpoint — Phase 6: XP / Leveling V1

**Date:** 2026-10-07  
**Result:** Phase 6 gate passed. The next roadmap phase was not started.

Historical `CHECKPOINT_CURRENT.sha256` was not modified.

## What this phase owns

Python owns experience. Narration cannot grant it, and the client cannot send experience, level, or hit points.

Tier 1 thresholds: level 1 at 0 XP, level 2 at 300, level 3 at 900, level 4 at 2,700. Stored XP may pass 2,700. That does not raise the character to level 5, and proficiency stays +2.

Each level after 1 adds the 2024 fixed class hit points plus the Constitution modifier, minimum 1, then Dwarf Toughness +1 and the Tough feat +2 when those apply. Level 1 hit points stay as they were. Current hit points rise by the same amount as the maximum.

Awards come only from a quest definition’s `xp`, once, or from a server `xp_reward` when combat ends with `target_defeated`. The production quest catalog stays empty. `location_changed` and `player_defeated` pay nothing. The same combat ending does not pay twice.

Save format version is 5. Versions 1–4 still load, migrate to 0 XP, and keep their existing level and hit points.

The Fighter and Cleric package longsword, “Uzun Kılıç”, is recognized as the sword used for an attack.

## Gate

- `python run_tests.py`: **20/20 deterministic gates passed**, including `test_xp_v1.py` and the longsword attack check in `test_combat_v2.py`.
- `python -m unittest discover -s api/tests -p "test_*.py"`: **247 tests passed**.
- Experience client tests: **17 passed**.
- Experience and web TypeScript typechecks: **passed**.
- OpenAPI client generation: **passed**.
- Production builds for `ai-dnd-experience` (`PORT=5000 BASE_PATH=/ai-dnd-experience`) and `ai-dnd-web` (`PORT=5000 BASE_PATH=/ai-dnd-web`): **passed**. Vite reported the known non-blocking Tooltip sourcemap warning.

## Browser check

A Dwarf Fighter resumed at 0 XP, level 1, and 13/13 hit points, with a hostile Sentinel (1 hit point, armor class 0, server reward 300). The panel showed `DENEYİM 0`.

The attack `Sentinel'a kılıcımla saldırıyorum` was sent from the character page. The turn returned 200. The panel then showed 300 XP, level 2, and 22/22 hit points, and the notice `Seviye atlandı` / `Seviye 1 → 2. +9 can, +300 deneyim.` The save stored award id `combat:1:npc_xp_sentinel`. Proficiency stayed +2.

The same page then posted a turn that included `xp`, `level`, and `current_hp`. The server returned 422 `extra_forbidden` for all three fields. The panel stayed at 300 XP, level 2, and 22/22.

Chat replies for that award turn came from a local stand-in. The installed `qwen3:8b` runner stayed on one CPU core with about 1.5 GB resident and did not finish a live generation. The stand-in only labeled the attack and returned one narration line. The experience, the level, and the hit points came from the Python rules.

## Scope boundary

The next roadmap phase was not started. Living-world smoke reports were left out of this change.
