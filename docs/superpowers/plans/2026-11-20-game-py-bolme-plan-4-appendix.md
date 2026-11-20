# game.py Split, Plan 4 — Appendix (measurements, batches, commands)

Measured 2026-11-20, read-only, on `origin/main` `bdeddf2a` (Plan 3 merged, PR #136), with slot 2's Python 3.13.16
(`/root/aidnd-env-2/proj/.venv/bin/python`) outside the guard. The gate wait (`pgrep -af linux_guarded_launcher`) read
`RC=1` before every run. Raw outputs are in `2026-11-20-game-py-bolme-plan-4-measure/out/`; the scripts are in
`2026-11-20-game-py-bolme-plan-4-measure/`. Plan 3's scripts (`module_map.py`, `writer_scan.py`, `t4_checks.py`) are
in `2026-11-19-game-py-bolme-plan-3-measure/` and are used unchanged.

## A. Commands

Archives (Git Bash, repo root; `<W>` = a scratch folder, one sub-folder per tree):

```
git archive 5ea18cc7 ai-dnd | tar -x -C <W>/p3base            # P3BASE: module_map.py's anchors hold only here
git archive bdeddf2a ai-dnd content docs/engine-split | tar -x -C <W>/now
git archive 2e576967 ai-dnd content | tar -x -C <W>/tm0       # TM0 base (cumulative OLD tree)
```

Each run is a script file run as `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash <W>/run<k>.sh` (never `bash -c`).
`PY` = the slot Python, `M3` = Plan 3 measure folder, `M4` = Plan 4 measure folder, all as `/mnt/c/...` paths.

| Step | Command | Output |
|---|---|---|
| 1 | `PY M3/module_map.py <W>/p3base/ai-dnd <W>/topic-map.json M4/overrides-p4.json --apply-misfits` | `out/topic-map.out` |
| 2 | `PY M4/plan4_map.py <W>/now/ai-dnd <W>/topic-map.json <W>/p4-map.json` | `out/p4-map.out` |
| 3 | `PY M4/classify_all.py <W>/now/ai-dnd` | `out/classify.out` |
| 4 | `PY M4/p4_checks.py <W>/now/ai-dnd <W>/p4-map.json <W>/p4-checks.json` (3 min 23 s) | `out/p4-checks.out` |
| 5 | `PY M4/batches4.py <W>/now/ai-dnd <W>/p4-map.json <W>/p4-batches.json 1000` | `out/p4-batches.out`, `out/p4-batches.json` |
| 6 | `cd <W>/now/ai-dnd && PY M4/hook_profile.py <W>/now/ai-dnd` | `out/hook.out` (skill-check prints removed) |
| 7 | `M4/turn_ms.py` on `tm0` and `now`, one warm-up each, 5 pairs O,N,N,O,O,N,N,O,O,N | `out/ab-cum.out` |
| 8 | `PY M4/session_callers.py <W>/now/ai-dnd <W>/p4-map.json` | `out/session-callers.out` |

Why step 1 runs on P3BASE: `module_map.py` asserts Plan 3's region anchors, which moved out of `game.py` in Plan 3.
`plan4_map.py` maps every top-level name of today's `game.py` through that topic map and adds a scope:
`plan4` (a T5 topic or a T4 topic sensitive/held name), `plan5` (`turn`) or `never` (`move_block.NEVER_MOVED`).
`overrides-p4.json` = Plan 3's `overrides-extra.json` minus its 12 `held_plan4` rows, plus four topic rows
(`_commit_travel_action: places`, `_handle_query: intent`, `_settle_spoken_commitment: dialogue`,
`_states_the_failed_check: narration`). Ruling (measurement): topic wins over turn-only callers for a held name, else the
misfit rule sends these four to `turn` (their only callers are turn functions) and Plan 4 would not own them.

## B. Base facts on `bdeddf2a`

- `ai-dnd/game.py` 15 363 lines, 226 top-level names. Parts (11 in `_PART_MODULES`): `character_rules`, `dialogue`,
  `intent`, `living_world_turn`, `lore`, `narration`, `narration_safety`, `new_game`, `places`, `text_rules_a`,
  `text_rules_b`; data parts `tables`, `schemas`; `terminal`.
- Session core (never moved): `_PART_MODULES`, `_ENGINE_FUNCTIONS`, `_CHARACTER_GLOBALS` (22 names) near the end;
  `_session`, `_bind_session_engine`, `create_session`, then `_GameModule` inside `if __name__ != "__main__":`.
- `logging.getLogger(__name__)` in `_repair_dilim1_fields`, `_repair_dilim2_fields` (move to `savefile`) and in
  `GameSession` (stays). `sys.modules[__name__]` and `locals()` only in turn code (Plan 5).
- `COIN_LEFT_BEHIND = money_owner.COIN_LEFT_BEHIND`, a one-line alias read by `test_economic_room` and
  `test_money_cards` (D-378 money list); goes to `coin`.
- Comments: Plan 3 measured 1 094 on P3BASE; Task 0 measures `<C>` on P4BASE again.

## C. Module map and D-355 (`out/p4-map.out`, `out/classify.out`)

Plan 4 scope: **138 names, 7 069 lines**, plus `COIN_LEFT_BEHIND` = **139 / 7 070**. `S` = in `sensitive.json`,
`H` = one of Plan 3's 15 fix-wave holds.

| Topic | Names | Lines |
|---|---|---|
| combat_flow | 61 (9 S) | 2 129 |
| coin | 15 (10 S) + `COIN_LEFT_BEHIND` | 218 |
| savefile | 19 (8 S) | 1 048 |
| schemas | 1 (`_EXPERIMENTAL_NPC_SPEECH_SCHEMA`) | 52 |
| character_rules | 1 S (`perform_skill_check`) | 22 |
| places | 3 S + 7 H | 342 |
| intent | 4 S + 2 H | 635 |
| dialogue | 7 S + 1 H | 218 |
| lore | 1 S (`_lore_entity_names`) | 54 |
| narration | 10 S + 4 H | 1 539 |
| living_world_turn | 1 S + 1 H | 813 |

Plan 5 (`turn`): 38 names / 815 lines plus 32 S / 5 417. `never`: 18 names. All 15 Plan 3 holds are in Plan 4 scope
(`HELD_P3_MISSING []`).

D-355: `sensitivity.classify` over `game.py` and all 15 part files: `FILES 16 FLAGGED 89 LOCKED 88 REMOVED 0`; the only
name not in the lock is `game_parts/terminal.py: run ['save']` (moved in T1 under the strong review, known);
`FLAGGED_IN_PARTS ['run']`; `locked_not_flagged=0`. No Plan 3 move left a flagged name unlisted.

## D. Batches (`out/p4-batches.out`, CAP 1 000 lines; name lists there, in `game.py` order)

| Batch | Part | Names | Lines | S | Prefixed by the mover (census `import`/`absent`) | Census targets moved |
|---|---|---|---|---|---|---|
| combat-1 | combat_flow | 30 | 925 | 5 | `effect_lifecycle`, `uuid4` | 12 |
| combat-2 | combat_flow | 24 | 995 | 4 | `effect_lifecycle`, `resolve_saving_throw`, `uuid4` | 9 |
| combat-3 | combat_flow | 7 | 209 | 0 | `uuid4` | 0 |
| coin | coin | 16 | 218 | 10 | — | 1 (`create_shop_from_proposal`) |
| save-1 | savefile | 18 | 862 | 7 | `effect_lifecycle`, `os` | 3 |
| save-2 | savefile | 1 (`load_game`) | 186 | 1 | — | 1 |
| schemas | schemas | 1 | 52 | 0 | — | 0 |
| cr-s | character_rules | 1 | 22 | 1 | — | 1 |
| places-s | places | 10 | 342 | 3 | — | 2 |
| intent-s | intent | 6 | 635 | 4 | `ollama` | 3 |
| dialogue-s | dialogue | 8 | 218 | 7 | — | 1 |
| lore-s | lore | 1 | 54 | 1 | — | 0 |
| narration-s-1 | narration | 8 | 585 | 6 | — | 4 |
| narration-s-2 | narration | 6 | 954 | 4 | `ollama` | 2 |
| lwt-s | living_world_turn | 2 | 813 | 1 | `effect_lifecycle`, `uuid4` | 2 |

Headers (M5): as printed per batch in `out/p4-batches.out`. `combat-2` reads `from api.core_resolution import (...)`:
under Plan 3's M5 Ruling it lists only the names read and never `resolve_saving_throw` (census target). `coin` header:
`import money_owner`, `import re`. Part sizes after Plan 4 (existing + moved, all ≤ 2 500): narration ≈ 2 049,
intent ≈ 1 811, places ≈ 1 625, dialogue ≈ 1 523, living_world_turn ≈ 1 039, combat_flow 2 129, savefile 1 048,
coin 218. New parts with functions join `_PART_MODULES`: `combat_flow`, `coin`, `savefile`; `schemas` stays data only.

## E. Risk checks (`out/p4-checks.out`)

- None of: decorators, `global`, character-global reads, builtin `open`, engine imports, split clusters.
- Non-constant defaults: only `()` (`_combat_end_if_decided`, `_combat_record_for_actor`, `_death_save_line`); no engine name.
- Identity names: only `__name__` in `_repair_dilim1_fields`, `_repair_dilim2_fields` (the spec T5.3 logger edit).
- Census `import` targets read: `uuid4` (`_apply_player_damage`, `_down_outside_combat_turn`,
  `_migrate_legacy_combat_state`, `_resolve_player_death_turn`, `_start_combat_with_initiative`, `advance_campaign_time`),
  `effect_lifecycle` (`_finish_species_player_turn`, `_validate_species_trait_state`, `advance_campaign_time`,
  `resolve_species_trait_action`), `resolve_saving_throw` (`resolve_species_trait_action`), `ollama`
  (`ask_dungeon_master`, `parse_player_intent`), `os` (`save_game`).
- Reads of never-moved names: `INITIAL_WORLD_STATE` (`_validate_save_payload`), `RULE_ORDER` (`advance_campaign_time`),
  `GameSession` (`_restore_combat_death_checkpoint`), `_session` (many).
- Adapter names: `ask_dungeon_master` calls `build_world_context` and `finalize_narration` (all three move in Plan 4).
- 41 census targets move. Most patched: `resolve_species_trait_action` 72 sites, `heal_player` 49,
  `ask_dungeon_master` 43, `parse_player_intent` 32, `perform_skill_check` 24, `_validate_save_payload` 18,
  `apply_npc_damage` 14, `resolve_enemy_attack` 13, `advance_campaign_time` 12.
- Touching test modules (`inventory.touching_tests`): character_rules 13, coin 294, combat_flow 320, dialogue 10,
  intent 326, living_world_turn 14, lore 0, narration 335, places 12, savefile 34, schemas 3. Over 60 → pattern runs.
- `docs/engine-split/source-readers.md` names `end_combat` (a test reads its source text: Task 7 checks it).
- `getattr` only on session objects; `__import__("grounded_action")` inside `plan_living_world_turn` (moves untouched).

## F. `session=` callers outside `game.py` (`out/session-callers.out`): 19 names, 122 calls

finalize_narration 20, `_resolve_player_death_turn` 15, resolve_enemy_attack 12, build_world_context 10,
`_capture_combat_death_checkpoint` 9, resolve_species_trait_action 8, `_experimental_speech_note` 8,
perform_skill_check 6, ensure_combat_state 5, `_apply_player_damage` 5, ensure_death_state 4, execute_intent 4,
`_restore_combat_death_checkpoint` 4, commit_location_change 4, create_npc_from_ai 3 (one in production:
`grounded_action.py`), `_resolve_enemy_turns_until_player` 2, ask_dungeon_master 1, serialize_game_state 1,
`_begin_combat_actor_turn` 1.

## G. Speed

**Hook profile** (`out/hook.out`, bench commands and seed, offline model, fixed town):
- `HOOK_CALLS_PER_TURN 3050.7` Python-level `_GameModule.__getattribute__` calls per turn. Callers over 12 turns:
  `game_parts/places.py` 24 521, `intent.py` 8 041, `dialogue.py` 1 634, `narration_safety.py` 1 226, `shop_trade.py` 420,
  `narration.py` 329, others below 200.
- `READ_NS hook=134.2 plain=14.0` per `game.X` read; `EST_HOOK_MS_PER_TURN 0.367`; `TURN_MS median=27.56` (this
  process, /mnt/c); `PROFILE_SHARE_PCT 1.63`. The hook is about 1.3-1.6 % of a turn today. Plan 4 moves the hot
  callers' callees (`ask_dungeon_master`, `finalize_narration`, `parse_player_intent`, combat), so the count grows with
  every batch; the cut removes the per-read Python call entirely.
- Plan 3 rehearsal (ledger Task 5 Step 3): the property alternative (local commit `b4b1cd11`) read
  `ALTPROBE _GameModule 22 bad []` and bench mean 22.53 ms vs 22.55 ms (inside noise).

**Cumulative baseline choice: TM0 base `2e576967`** (PR #128 merge, T0, 2026-11-18): the last tree before any part
existed (`ai-dnd/game_parts` absent), `game.py` equal to the BM merge `e8a66d88`, `api/tests/bench_engine_turn.py`
byte-equal to today's. Feature commits to `game.py` since then (for example the flag-on job) count against the split:
stricter, not looser.

**Indicative cumulative A/B** (`out/ab-cum.out`, outside the guard, `turn_ms.py`, not binding): warm-ups old 22.16 /
new 21.16; OLD 23.62, 21.24, 20.96, 21.75, 23.07 → median 21.75; NEW 21.86, 25.75, 22.89, 21.94, 23.42 → median 22.89;
ratio ≈ 1.052. The binding numbers come from slot benches in Tasks 0, 1, 5 and 17.

**Plan 3 history** (ledger): Task 5b fair A/B 1.0379; Task 15 0.9970; TM3 1.0970 (OLD `6657748f`, NEW `a4faef54`, under
foreign `npx expo` load). TM3 suites: flag off 2 123 s (limit 2 155 = 1.10 × TM0 1 959); flag on wall 2 855 s vs
1.10 × base mean 2 900.7; longest-shard ratio 1.104 (information, D-448).

## H. Not measured here (Task 0 steps for the executor)

- A slot bench on the TM0 tree (needs a detached worktree; `slot.sh` syncs a worktree, not an archive).
- `move_check.py --comments-only` count `<C>` on P4BASE.
- The census lock, surface lock and size count byte-equality on P4BASE (Plan 3 Task 0 Step 4 routine).
- Whether `origin/main` moved after `bdeddf2a`; if `game.py` changed, Task 4 measures again and measurement wins.
