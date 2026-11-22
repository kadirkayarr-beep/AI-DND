# game.py Split, Plan 5 — Appendix (measurements, batches, commands)

Draft measurement, 2026-11-21, read-only, on p4m `0b1dca5ad1e293956742d9c08b5aaaadc0c786e9` (branch
`task/game-py-bolme-p4-moves` after Plan 4 Task 9: `combat_flow`, `coin`, `savefile` moved; Tasks 10-15 not yet run).
Python: WSL Ubuntu-24.04 `python3` 3.12.3 (stdlib only), outside any slot. No test, no `slot.sh`, no `slot_gate.sh` and no
bench ran (Plan 4 Stage B held slots 2 and 4). Raw outputs are in `2026-11-21-game-py-bolme-plan-5-measure/out/`;
scripts at its top; draft batch files in `batches/`; draft M12 reading lists in `writer-expected/`. Plan 5 Task 0 measures
again on `P5BASE` (Ruling M).

Pre-flight fixes (same day, same archive, same Python): `p5_checks.py` now sees class decorators and `batches5.py` cuts
two targets (`turn_front`, `turn`; Ruling H) and counts decorator names as read. Steps 4, 5 and 7 were run again
(`STORE/out-c1/`); `out/p5-checks.out`, `out/p5-batches.out`, `out/p5-batches.json`, `out/writer-scan.out`, `batches/`
and `writer-expected/` hold the new outputs. The other outputs did not change.

## A. Commands

Archives (Git Bash; `<S>` = `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p5`):

```
git -C <p4m or repo> archive 0b1dca5a | tar -x -C <S>/tree/p4m-0b1dca5a     # draft tree (Task 0: P5BASE instead)
git -C <repo> archive 5ea18cc7 ai-dnd | tar -x -C <S>/tree/p3base            # P3BASE: module_map.py's anchors hold only here
```

Each script: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- python3 <script> <args> < /dev/null > <out> 2>&1`, all paths as
`/mnt/c/...`. `M3` = Plan 3 measure folder, `M4` = Plan 4 measure folder, `M5` = this plan's measure folder,
`T` = `<S>/tree/<tree>/ai-dnd`. In Task 0 run them with the slot Python (`SLOTPY`) instead; the outputs must agree.

| Step | Command | Output |
|---|---|---|
| 1 | `M3/module_map.py <S>/tree/p3base/ai-dnd <S>/topic-map.json M4/overrides-p4.json --apply-misfits` | `out/topic-map.out` (topic map byte-equal to Plan 4's `p4/topic-map.json`) |
| 2 | `M4/plan4_map.py T <S>/topic-map.json <S>/p4m-map.json` | `out/p4m-map.out` (scope `plan5` = topic `turn`) |
| 3 | `M4/classify_all.py T` | `out/classify.out` |
| 4 | `M5/p5_checks.py T <S>/p4m-map.json <S>/p5-checks.json` (39 s) | `out/p5-checks.out` |
| 5 | `M5/batches5.py T <S>/p4m-map.json <S>/p5-batches.json 1000` | `out/p5-batches.out`, `out/p5-batches.json` |
| 6 | `M5/session_callers5.py T <S>/p4m-map.json` | `out/session-callers.out` |
| 7 | `M3/writer_scan.py <S>/tree/<tree> <S>/p5-batches.json` (13 s; exit 1 by design) | `out/writer-scan.out` |

`p5_checks.py` and `session_callers5.py` are Plan 4's `p4_checks.py` and `session_callers.py` with the scope `plan4`
changed to `plan5`, plus a class-decorator check. `batches5.py` is Plan 4's `batches4.py` for two target parts (`CORE` =
spec §5's `turn.py` content → `turn`, the rest → `turn_front`; move order `turn_front` batches, `turn` batches, the name
over CAP last), plus the never-moved misfit rule (Ruling I), decorator names counted as read, and the M5 list of
`from X import (...)` names read.

## B. Base facts on `0b1dca5a`

- `ai-dnd/game.py` 11 971 lines, 130 top-level names. Parts: Plan 3's 11 plus `combat_flow`, `coin`, `savefile`
  (all in `_PART_MODULES`); data parts `tables`, `schemas`; `terminal`.
- Still in `game.py` for Plan 4 Tasks 10-15: 43 names, about 3 675 lines (`schemas` 1, `cr-s` 1, `places-s` 10,
  `intent-s` 6, `dialogue-s` 8, `lore-s` 1, `narration-s` 14, `lwt-s` 2). They leave before `P5BASE`.
- Never moved: 18 names, 618 lines (`GameSession` 439).
- `size_budget.json`: `files` = `game.py` 11 971, `game_parts/narration_safety.py` 1 505 (frozen at arrival);
  `part_max` 2 500, `slack` 50, `long_function_min` 151. Long `turn` functions: `_run_player_turn_internal` 2 756,
  `_execute_intent_internal` 548, `_dispatch_player_turn` 493, `_narrate_resolved_turn` 351, `_front_step` 235.
- `identity_allowlist.json` is `[]`. `move_block` refuses `__name__`, `__file__`, `globals(`, `locals(`, `vars(`,
  `sys.modules` (N3 rule 6). `routing_audit` R6 flags them in a part unless a row `(file, function, name, reason)`
  matches; R12 flags `game` used as a value.
- `test_engine_size_budget.test_long_functions_cannot_grow_or_appear` names `"game.py::_run_player_turn_internal"`
  literally (Task 11 rewrites the key).
- Sensitivity: `classify_all.py` → `FILES 19 FLAGGED 89 LOCKED 89`, `DIFF not_in_lock=0 locked_not_flagged=0`
  (`run` joined the lock in Plan 4 Task 2).

## C. Module map (`out/p4m-map.out`)

`turn` topic: **69 names, 6 231 lines** = 37 names / 814 lines plus 32 sensitive / 5 417 lines. Plan 4's outline said
38 / 815; the difference is `COIN_LEFT_BEHIND` (moved to `coin` in Plan 4). No name is NEW (`NAMES x|NEW (0)`).

**Stay in `game.py` (Ruling I, `batches5.py` `STAY`):** `NEVER_READERS` = `_restore_in_place` (24 lines, sensitive) and
`_dynamic_engine_transitions` (54 lines) are read inside `game.py` only by `GameSession`. Move set after that:
**67 names, 6 153 lines, 31 sensitive.**

Names in file order (start line on `0b1dca5a`, lines, S = sensitive):
`ResolvedTurn` 23, `_has_session` 2, `_carry_out_thread_turn` 75 S, `_thread_gate` 42 S, `DEBUG_MODE` 1,
`_world_snapshot` 27 S, `_changed_state_fields` 21 S, `_execute_intent_internal` 548 S, `TurnResolved` 4,
`_hideout_check` 12, `_adventure_scene_turn` 32, `_adventure_check_reply` 30, `_everyday_action_turn` 60,
`_local_place_turn` 90, `_intent_infrastructure_result` 14, `_clear_turn_transients` 17 S, `turn_source_key` 7,
`run_player_turn` 11, `_run_player_turn_owned` 47 S, `_tell_the_coin` 45 S, `_run_player_turn` 28,
`_run_player_turn_keyed` 137 S, `_the_rest_of_the_line` 84 S, `_person_answers_stock` 40 S, `_last_call` 15,
`combat_refusal_turn` 13, `_approach_turn` 20, `player_cannot_act_turn` 22, `_reads_as_address` 3, `_addressed_in` 8,
`_front_recovery` 32, `_front_step` 235 S, `_defer_spoken_coin_offer` 18 S, `_record_spoken_coin_response` 10 S,
`_economic_listing` 5 S, `_front_economic_offer` 103 S, `_purchase_refused` 37 S, `_hand_over_coin` 44 S,
`_coin_without_a_reading` 37 S, `_blow_stands` 10, `_blow_in_the_words` 8, `_ask_about_the_blow` 11,
`_heavy_allowed` 5, `_ask_before_the_heavy` 18, `_answered_heavy_question` 13, `_ask_which_move` 13,
`_narrated_person` 17, `front_read_ahead` 19 S, `_front_offer_gate` 27 S, `_line_gives` 10 S, `_front_consume` 22,
`_front_wield` 65, `_coin_not_parcel` 11 S, `_names_no_parcel` 14 S, `_front_hand_over` 56 S, `_front_work` 22,
`_take_names_a_job` 15, `_front_take` 50, `_dispatch_player_turn` 493 S, `_dispatch_turn_body` 22,
`_sleep_after_walk` 32 S, `_spoken_rest_of_turn` 23, `_current_procedural_entity_ids` 23 S, `_keep_town_portrait` 29 S,
`_narrate_resolved_turn` 351 S, `_owner_module_reply` 19, `_run_player_turn_internal` 2 756 S;
staying: `_restore_in_place` 24 S, `_dynamic_engine_transitions` 54.

## D. Batches (`out/p5-batches.out`, CAP 1 000; files in `-measure/batches/`)

Two parts (Ruling H). Move order as listed.

| Batch | Part | Task | Names | Lines | S | Census targets moved | `from X import` names (M5) |
|---|---|---|---|---|---|---|---|
| front-1 | `turn_front` | 6 | 13 | 970 | 6 | `_thread_gate`, `_adventure_scene_turn`, `_local_place_turn`, `_clear_turn_transients` | — |
| front-2 | `turn_front` | 7 | 30 | 944 | 14 | `_the_rest_of_the_line`, `_coin_without_a_reading`, `front_read_ahead` | — |
| front-3 | `turn_front` | 8 | 8 | 265 | 4 | `_front_hand_over`, `_front_take`, `_sleep_after_walk` | — |
| turn-1 | `turn` | 9 | 13 | 848 | 5 | `run_player_turn`, `_run_player_turn`, `_dispatch_player_turn` | `typing`: `Any, Dict, List, Optional`; `dataclasses`: `dataclass`; `api.core_resolution`: `resolution_action_scope` |
| turn-2 | `turn` | 10 | 2 | 370 | 1 | `_narrate_resolved_turn` | — |
| turn-3 | `turn` | 11 | 1 | 2 756 | 1 | — | — |

Total 67 names, 6 153 lines, 31 sensitive: `turn_front` 51 / 2 179 / 24, `turn` 16 / 3 974 / 7. No census
`import`/`absent` target is read by any batch (nothing for the mover to prefix besides engine names). Header module lines
per batch are printed in `out/p5-batches.out` (`header:`; the `from X import (...)` lines there are shown whole, M5 lists
only the names in the last column). `field` from `dataclasses` is not read.

Part sizes as the batches arrive (moved lines plus header lines plus about 1.1 separator lines per name, the Plan 4
rate): `turn_front.py` about 1 000, 1 975, 2 255 (whole; ≤ 2 500, no `files` entry); `turn.py` about 885, 1 260, 4 020
(`files` entry created at `turn-3`, frozen). Task 4 and Task 11 record the real numbers.

## E. Risk checks (`out/p5-checks.out`) and writer scan (`out/writer-scan.out`)

- Decorators: one, `ResolvedTurn` `@dataclass` (`decorated 1`; the draft check looked at functions only, pre-flight C2;
  Ruling L).
- None of: `global`, non-constant defaults, character-global reads, builtin `open`, engine imports (in-function
  imports: 145 sites, none of `game` or `game_parts`), census `import` targets read, split constant clusters,
  free non-engine reads.
- Identity names: `_local_place_turn` `sys.modules[__name__]`; `_run_player_turn_internal` `sys.modules[__name__]` and
  `locals()` (`locals().get("preparsed_scene_intent")`). Ruling J.
- Reads of never-moved names: `_session` (50 names), `_ACTIVE_SESSION` (`_has_session`), `_speech_debug_trail`
  (`_run_player_turn_internal`, D-344).
- Adapter names: `_narrate_resolved_turn` calls `ask_dungeon_master`, `finalize_narration`; `_run_player_turn_internal`
  calls `finalize_narration`.
- Patched census sites: `run_player_turn` 167, `_dispatch_player_turn` 17, `_thread_gate` 4, `_clear_turn_transients` 3,
  `_run_player_turn` 3, `_coin_without_a_reading` 2, `_adventure_scene_turn` 2, one each for `_front_take`,
  `_the_rest_of_the_line`, `_local_place_turn`, `_narrate_resolved_turn`, `_sleep_after_walk`, `front_read_ahead`,
  `_front_hand_over`.
- Touching test modules (`inventory.touching_tests`, session readers included since D-446): 398 for the whole `turn` set.
  Every batch is a pattern run.
- `docs/engine-split/source-readers.md` names `combat_refusal_turn` (Task 7 checks the reader).
- `DEBUG_MODE`: written nowhere; read by `_run_player_turn_internal` and `game_parts/narration_safety.py`
  (`game.DEBUG_MODE`). `_has_session`: read only by `game_parts/dialogue.py`.
- **Writer scan** (`SUMMARY held=36 missing=0 clean=31`, money 9, save 15, death 12; `NO_CODE turn-1 ResolvedTurn`):
  HELD per batch, the draft M12 reading lists (`writer-expected/`):
  - front-1 (8): `_carry_out_thread_turn`, `_thread_gate`, `_execute_intent_internal`, `_hideout_check`,
    `_adventure_scene_turn`, `_adventure_check_reply`, `_everyday_action_turn`, `_local_place_turn`;
  - front-2 (14): `_tell_the_coin`, `_the_rest_of_the_line`, `_person_answers_stock`, `_last_call`, `_approach_turn`,
    `player_cannot_act_turn`, `_front_step`, `_record_spoken_coin_response`, `_front_economic_offer`,
    `_coin_without_a_reading`, `_narrated_person`, `front_read_ahead`, `_front_offer_gate`, `_front_consume`;
  - front-3 (5): `_front_wield`, `_front_hand_over`, `_front_work`, `_front_take`, `_sleep_after_walk`;
  - turn-1 (7): `run_player_turn`, `_run_player_turn_owned`, `_run_player_turn`, `_run_player_turn_keyed`,
    `_dispatch_player_turn`, `_dispatch_turn_body`, `_spoken_rest_of_turn`;
  - turn-2 (1): `_narrate_resolved_turn`;
  - turn-3 (1): `_run_player_turn_internal`.
  Death writers sit in front-2, front-3, turn-1 and turn-3 (the plan's `DEATH` list goes to Tasks 7, 8, 9, 11).
  The scan's `HELD` line is `HELD <batch> <name> <kinds> hops=<n> <path>`: compare by the third field.
  On the TM4 tree some paths will start in the Plan 4 parts (for example `perform_skill_check` in `character_rules`);
  the names should not change, Task 0 Step 3 checks it.

## F. `session=` callers outside `game.py` (`out/session-callers.out`): 7 names, 12 calls

`_sleep_after_walk` 4 (`test_coin_writers`, `test_economic_room`, `test_money_routes`), `_tell_the_coin` 2
(`test_economic_dialogue`, `test_economic_room`), `_narrate_resolved_turn` 2 (`test_f04_frozen_narrator_faults`),
`_the_rest_of_the_line` 1 (`test_economic_dialogue`), `run_player_turn` 1, `_front_work` 1 (`test_engine_parts_pilot`),
`_front_recovery` 1 (`test_front_failed_fallback`). Review Focus 5 is built on the money ones.

## G. Speed history (Plan 4 ledger; no bench ran for this draft)

Cumulative fair A/B against `TM0BASE` `2e576967`: Plan 4 Task 0 `p4t0cum` 1.0183 (before the hook cut); Task 1
`p4t1cum` 1.0009 (hook cut); Task 5 rehearsal `p4t5cum` 1.0252 (all T5 batches moved). Plan 4 Stage B M10b (OLD = Stage
A tip): Task 7 1.0104, Task 8 1.0091, Task 9 0.9892. `CUM_TM4` (Plan 4 Task 17) is not known yet; it is Plan 5's start
value. The turn core is the hottest code left; Task 4's rehearsal is the first binding reading of its cost.

## H. Not measured here (Task 0 steps)

- The whole measurement on `P5BASE` (Ruling M), with the slot Python.
- The touching list per batch (`inventory.py --touching`), the comment count `<C>`, lock byte-equality.
- Which input reaches the `locals()` branch (Task 2 Step 1).
- The R6 `function` key `routing_audit` reports for each identity use (Task 1 measures it with a fixture).
- Any bench.

## I. `game.py` after Plan 4 and Plan 5 (pre-flight I5)

Measured on `0b1dca5a` (WSL `python3`, read-only): every top-level node whose names are all Plan 4 (`plan4`, 43) or
Plan 5 (`plan5` minus the two `STAY` names) removed, decorator lines included. Result: 11 971 → **2 148 lines** = 1 292
blank + 97 comment-only + 759 code (never-moved names 618 lines, Ruling I's 78 lines, imports, existing re-export lines,
module setup). Plan 5 adds its own re-export lines on top. A pure move leaves each block's separator blank lines behind,
so most of the 1 292 blank lines are leftovers of Plans 1-5. `game.py` ≤ 1 500 is reachable only by removing those
blank lines (spec §2 non-goal "biçim düzeltme": Plan 6 needs a Ruling and an approval row first) or by a spec decision;
see the plan's "Plan 6 outline" and D-473. The pre-flight review measured 2 147 with its own script; the one-line
difference was not traced.
