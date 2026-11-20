# game.py Split, Plan 3 — Appendix: measured module map, batches and checks

Companion to `docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md`. Everything here was measured read-only on `origin/main` `b1150df8` (2026-11-19, Plan 2 merged) with Windows Python 3.14, before the flag-on job (`task/fon-a`, `task/fon-b`; D-369/370/371) was merged. Plan 3 Task 0 and Task 4 measure again on the execution base (main after the flag-on PR) with the slot's Python 3.13. **Measurement wins over this appendix**; every difference is a `Ruling` in the ledger (rules in the plan, Task 4 Step 3).

## A. How the lists were made (commands)

The measurement scripts (`module_map.py`, `batches.py`, `t4_checks.py`; fix wave: `money_scan.py`, `walrus_probe.py`; fix wave 2: `writer_scan.py`) and `overrides-extra.json` are committed next to this file in `docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3-measure/`. They are read-only: they never write into `ai-dnd/`. `<AI>` = an `ai-dnd` root, `<M>` = that measure folder, `<OUT>` = an output folder outside `ai-dnd/`.

```
python <M>/module_map.py <AI> <OUT>/map.json <M>/overrides-extra.json --apply-misfits
python <M>/batches.py    <AI> <OUT>/map.json <OUT>/batches.json 1000
python <M>/t4_checks.py  <AI> <OUT>/map.json <OUT>/t4-checks.json        # about 2 min
python <M>/money_scan.py <AI>/.. <OUT>/batches.json                        # direct calls into equipment_economy/economic_actions/bold_acts; module-level walrus
python <M>/writer_scan.py <AI>/.. <OUT>/batches.json                       # transitive money/death/save writer reach (fix wave 2); expected SUMMARY held=0 missing=0 clean=241; also takes one-name-per-line batch files (fix wave 3)
python <M>/walrus_probe.py <AI>                                            # D-349 M9 shapes (fix wave)
```

Under the plan these run as `SLOTPY` script files with the slot's Python 3.13 against `WTROOT` (`/mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd`). `t4_checks.py` reads `docs/engine-split/source-readers.md`, which `slot.sh` does not sync, so the slot copy is not enough.

**Rule (Ruling R1 of the plan).** `game.py` is ordered by topic. `module_map.py` walks the top-level names in file order. An *anchor* name starts a region that runs to the next anchor (the `REGIONS` table in the script: 57 anchors mapped to spec §5 modules). `OVERRIDES` (26, in the script) and `overrides-extra.json` (74: 62 topic exceptions plus the twelve fix-wave holds below) name single exceptions. `NEVER_MOVED` names stay. Then measurement corrects the region guess:
- a constant follows its readers' module when every reader sits in one module (`const_moves`; 0 on `b1150df8`);
- a *misfit* is a non-sensitive function whose engine callers all sit in one other module; with `--apply-misfits` it moves there (20 applied, list at the end of section E);
- a misfit whose callers are all in `turn` or `new_game` keeps its topic module (`overrides-extra.json`): topic wins over "only the turn core calls it", because Plan 5 moves the turn core and every helper would otherwise land in `turn.py`;
- `_has_session` → `turn` (session core, Plan 5); `_SOMEONE_ELSES_PURSE` → `coin` (money); `_EXPERIMENTAL_NPC_SPEECH_SCHEMA`, `_EXPERIMENTAL_NPC_SPEECH_OPTIONS` → `schemas`;
- `sensitive.json` (87 functions) decides the tier: a sensitive name never moves in Plan 3 (Plan 4/5, strong).
- **Fix-wave holds (2026-11-19, review finding 1; measured with `money_scan.py` in the measure folder):** `create_npc_from_ai` (calls `equipment_economy.give_person_purse`, which writes `world["currency"][npc_id]`), `commit_location_change` (calls `economic_actions.cancel_prepared`) and `advance_campaign_time` (calls `equipment_economy.process_supply_days`, which can return `condition_death`; it also reads `ensure_death_state`, `heal_player`, `stabilize_player`, `_resolve_player_death_turn`) map to `held_plan4` in `overrides-extra.json`. N8 sees only a function's own text, so these two-hop money/death writers pass it (D-355 class). The misfit rule then sends their only-callee helpers `generate_npc_id` and `_ensure_location_entities` to `held_plan4` too. `held_plan4` is not a T4 module, so `batches.py` leaves all five in `game.py` for Plan 4 (strong).
- **Fix-wave 2 holds (2026-11-19, re-review; controller Ruling: transitive, any number of hops; measured with `writer_scan.py`).** `writer_scan.py` builds one call graph over the whole engine (231 modules under `ai-dnd/`; tests, scripts, `legacy_debug` and docs left out; 5 796 functions and methods) and marks a *writer*: a function whose own body stores into or mutates a money key (`currency`, purse, coin, `cp`/`sp`/`gp`, ledger, `economic_ledger`, offer records) or a local bound from one, a player death key (`death_state`, `dead`, `stable`, death saves, `condition_death`, `death_results`), or save/Undo state (the N8 save and snapshot names, file writes, SQL writes). Log writers (usage ledger, Haiku spend counter, route log, debug trail) are not save state. Measured: 93 writers in 32 modules, among them `equipment_economy`, `economic_actions`, `bold_acts`, `shop_trade`, `item_transfers`, `equipment_native`, `world_reactions`, `world_happenings`, `adventure/rewards.py`, `adventure/dialogue_jobs.py`, `incidents/rewards.py`, `api/persistence`, and in `game.py` `_finalize_player_death`, `ensure_death_state`, `perform_skill_check`, `execute_intent`, `GameSession._forfeit_unrecordable_xp`. `timed_gameplay` and `weapon_attack` write nothing themselves but lead to writers (`weapon_attack.add_exhaustion` → `session._finalize_player_death` through `GameSession.__getattr__`; `_advance` → `equipment_economy.process_supply_days` → `consume_daily_supplies`). Eight batch names reach a writer and map to `held_plan4`:
  - `_commit_travel_action` → `commit_location_change` → `economic_actions.cancel_prepared`; also `timed_gameplay.start_travel` → `continue_travel` → `_advance` → `advance_walking` → `weapon_attack.add_exhaustion` → `_finalize_player_death`, and → `process_supply_days` → `consume_daily_supplies` (`condition_death`);
  - `_adventure_travel_reply` → `timed_gameplay.start_travel` → `perform_skill_check` (snapshot/restore); the same travel death and supply paths; and `session.evaluate_quest_events` → `adventure.play.after_turn` → `settle_session` → `adventure.rewards.apply_plan` (pays gold; verified by reading: `after_turn` calls `settle_session`, which calls `apply_plan`) and → `incidents.hooks.after_turn` → `incidents.rewards.grant`;
  - `_promote_scene_referent`, `_handle_query` → `create_npc_from_ai` → `equipment_economy.give_person_purse`;
  - `update_world_state_from_player` → `execute_intent` (runtime snapshot and restore: Undo);
  - `_settle_spoken_commitment` → `town_knowledge.settle_reply` → `economic_actions.npc_gift` → `apply_resolution` (coin from an NPC purse to the player; `api/tests/test_money_path_repair.py` names it);
  - `_fallback_for_action_result`, `_states_the_failed_check` → `_combat_narration` → `_death_closing` → `ensure_death_state` (writes the default death state into the world).
  Misfit rule: `_fallback_narration` (only caller `_fallback_for_action_result`) goes to `held_plan4` by `--apply-misfits`; `_stands_by_their_words` (only caller `_fallback_narration`, same module, so one misfit pass does not catch it) is mapped by hand (Ruling: a helper whose callers are all held waits with them). Totals: 15 held names, 577 lines. Rerun on the measured batches: `SUMMARY held=0 missing=0 clean=241`. Blind spots: calls through `getattr`/strings, callbacks stored in data, methods whose name is a builtin container method or is defined in more than three classes.

`batches.py` cuts each module's non-sensitive names, in `game.py` file order, into batches of at most 1 000 lines (CAP); a name over CAP is a batch of its own. For each batch it lists three things: the `game.py` import statements the batch's code reads (header); the census `import`/`absent` targets the mover prefixes as `game.<x>` instead; the census targets among the moved names.

## B. Measured totals (b1150df8)

`game.py` 22 670 lines; 468 top-level names (437 functions, 5 classes, 26 assignments); 228 names already re-exported from parts; 18 `NEVER_MOVED`; 87 sensitive.

| Module (spec §5) | Plan 3 moves (non-sensitive) | lines | stays for later (sensitive) | lines |
|---|---|---|---|---|
| character_rules | 19 | 427 | 1 | 22 |
| places | 58 | 1 213 | 3 | 119 |
| intent | 44 | 1 120 | 4 | 573 |
| dialogue | 65 | 1 227 | 7 | 195 |
| lore | 14 | 999 | 1 | 54 |
| narration | 21 | 484 | 10 | 1 358 |
| narration_safety | 15 | 1 480 | 0 | 0 |
| living_world_turn | 4 | 216 | 1 | 725 |
| new_game | 1 | 197 | 0 | 0 |
| **T4 total** | **241** | **7 363** | 27 | 3 046 |
| held for Plan 4 (fix waves 1 and 2: names that reach a money, death or save/Undo writer, and helpers whose callers are all held) | 15 | 577 | — | — |
| schemas (`_EXPERIMENTAL_NPC_SPEECH_OPTIONS`, D-376 live proof) | 1 | 15 | — | — |
| combat_flow (Plan 4) | 52 | 1 656 | 9 | 473 |
| coin (Plan 4) | 5 | 28 | 10 | 189 |
| savefile (Plan 4) | 11 | 208 | 8 | 840 |
| turn (Plan 5) | 38 | 815 | 31 | 5 362 |
| never | 16 | 576 | 2 | 42 |

Expected `game.py` after Plan 3: about 22 670 − 7 378 + re-export lines ≈ 15 300 lines. This is an estimate; `size_budget.json` takes the real count.

## C. Batches (CAP 1 000 lines; one move commit each)

| Batch | Part | Names | Lines | Task |
|---|---|---|---|---|
| `cr` | character_rules (exists) | 19 | 427 | 7 |
| `places-1` | places (new) | 43 | 991 | 8 |
| `places-2` | places | 15 | 222 | 8 |
| `intent-1` | intent (new) | 39 | 932 | 9 |
| `intent-2` | intent | 5 | 188 | 9 |
| `schemas-options` | schemas (exists) | 1 | 15 | 9 |
| `dialogue-1` | dialogue (new) | 54 | 995 | 10 |
| `dialogue-2` | dialogue | 11 | 232 | 10 |
| `lore` | lore (new) | 14 | 999 | 11 |
| `narration` | narration (new) | 21 | 484 | 12 |
| `nsafety-1` | narration_safety (new) | 14 | 426 | 13 |
| `nsafety-2` | narration_safety | 1 | 1 054 | 13 |
| `lwt` | living_world_turn (new) | 4 | 216 | 14 |
| `newgame` | new_game (new) | 1 | 197 | 15 |

Name lists in `game.py` file order. The batch files of Task 4 copy them, one name per line.

**cr** (`character_rules`, 19 names, 427 lines): `get_modifier`, `roll_stat`, `choose_option`, `create_random_character`, `assign_stats`, `choose_skill_proficiencies`, `calculate_hp`, `calculate_ac`, `_perform_skill_check`, `_new_species_trait_state`, `_new_persisted_species_trait_state`, `initialize_species_trait_state`, `calculate_attack_bonus`, `roll_attack`, `roll_damage`, `_species_trait_state`, `roll_initiative`, `roll_initiative_npc`, `roll_initiative_player`

- header (as game.py spells it): `from api.core_resolution import ( resolution_action_scope, resolve_attack_roll, resolve_death_save, resolve_saving_throw, resolve_skill_check, )` ; `import copy` ; `import timed_gameplay` ; `import weapon_attack`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `roll_attack`, `roll_damage`, `roll_initiative`, `roll_initiative_npc`, `roll_initiative_player`

**places-1** (`places`, 43 names, 991 lines): `_tavern_door_notice`, `_venue_door_id`, `_venue_door_for`, `_venue_entry_door`, `_locked_door_refusal`, `_mark_lock_seen`, `_lock_known_to_player`, `_current_door`, `_normalize_ground_items`, `location_features`, `feature_descriptions`, `active_npcs`, `_clean_world_text_list`, `_has_unregistered_person_name`, `validate_npc_proposal`, `create_local_feature`, `_valid_local_feature_parent_id`, `_legacy_hidden_feature_name_collision`, `_local_detail_claims_unsupported_mechanics`, `_feature_proposal_conflicts_with_canonical_door`, `location_display_name`, `_location_alias_values`, `_reference_token_matches`, `_entity_reference_in_text`, `resolve_location_reference`, `_location_reference_in_text`, `normalize_location_id`, `validate_location_proposal`, `_local_place_recommendation_options`, `_local_place_access`, `_attributed_place_note`, `_ground_local_place_recommendation_reply`, `_ground_local_place_recommendation_stage`, `_explicit_sword_drop`, `update_inventory_from_player`, `apply_check_outcome_to_world_state`, `_names_current_local_exit`, `_engine_location_parent`, `_existing_local_tavern`, `_resolve_explicit_local_scene_parent`, `_scene_detail_parent`, `_anchored_structure_features`, `_ensure_local_tavern`

- header (as game.py spells it): `import attributed_claims` ; `import equipment_economy` ; `import held_weapon` ; `import living_world` ; `import local_dialogue` ; `import name_catalog` ; `import npc_statements` ; `import re` ; `import scheduled_events`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `_current_door`, `active_npcs`, `_local_place_recommendation_options`, `apply_check_outcome_to_world_state`

**places-2** (`places`, 15 names, 222 lines): `_scene_feature_match`, `_scene_names`, `_variation_index`, `_look_opening`, `_scene_look_text`, `_look_scene_changed`, `_keep_people_in_look`, `_set_scene_active_npc`, `_reopen_public_doors`, `_a_walk`, `_walked_there`, `_may_propose_local_place`, `_accepted_local_place`, `_settle_local_place`, `_is_canonical_city_id`

- header (as game.py spells it): `import living_world` ; `import re` ; `import talk_mode`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: none

**intent-1** (`intent`, 39 names, 932 lines): `is_dialogue_or_emotion`, `_is_negated_dialogue_action`, `_reads_as_question`, `_people_speak_for_themselves`, `_asked_of_the_one_at_hand`, `is_npc_dialogue_input`, `_is_conversation_start_input`, `_is_local_place_question`, `_unverified_past_event_assertion`, `_report_of_someone_else`, `is_npc_historical_claim`, `_reported_npc_claim_followed_by_player_inspection`, `named_skill`, `open_scare_try`, `_stealth_skill`, `_word_check_for_action`, `known_player_action_narration`, `known_character_answer`, `_model_query_type_is_plausible`, `_detect_query_type`, `_detect_explore_type`, `_query_location_candidates`, `resolve_python_world_action`, `analyze_player_action`, `_travel_destination_reference_in_text`, `_intent_scene_npc_candidates`, `_recent_player_visible_narration`, `_validated_scene_npc_id`, `_named_word_of`, `_validated_local_person_proposal`, `_scene_detail_proposals_allowed`, `_scene_observation_proposal_turn`, `_local_person_request_key`, `_experimental_speech_final_line`, `_local_place_recommendation_guidance`, `IntentInfrastructureError`, `_has_travel_language`, `_travel_completion`, `_normalize_turkish_location`

- header (as game.py spells it): `import equipment_economy` ; `import hashlib` ; `import json` ; `import living_world` ; `import local_dialogue` ; `import re`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: none

**intent-2** (`intent`, 5 names, 188 lines): `validate_intent`, `_names_present_creature`, `_has_explicit_attack_verb`, `_is_explicitly_negated_attack`, `primal_knowledge_check_admission`

- header (as game.py spells it): `import adventure.play as adventure_play` ; `import campaign_time` ; `import combat_lifecycle` ; `import living_world` ; `import re` ; `import timed_gameplay`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `validate_intent`, `primal_knowledge_check_admission`

**dialogue-1** (`dialogue`, 54 names, 995 lines): `_claimed_completed_outcome`, `_conversation_npcs`, `_active_interlocutor`, `_clear_active_interlocutor`, `_is_end_conversation_request`, `_without_place_names`, `_words_fit_person`, `most_plausible_addressee`, `_absent_described_person`, `_absent_person_text`, `_settle_address`, `_word_for_nobody_here`, `resolve_npc_reference`, `_interaction_proposal_applies`, `_grounded_item_request_proposal`, `_explicit_addressee`, `_is_spoken_to`, `_is_short_conversation_continuation`, `_is_object_inspection`, `_is_door_inspection_request`, `record_npc_interaction`, `_remember_owner_locked_tavern_focus`, `_remember_accepted_profile_focus`, `npc_memory_supports_claim`, `npc_memory_supporting_entry`, `_STOCK_SAID`, `_stock_said`, `_stock`, `_is_stock`, `_only_stock`, `_without_lines_already_said`, `historical_claim_denial`, `named_by_sight`, `_npc_speech_enabled`, `_experimental_recent_exchanges`, `_speech_answer_rules`, `_remember_experimental_npc_speech`, `_clean_npc_speech`, `_render_experimental_npc_speech`, `_npc_speech_is_claim_refusal`, `_npc_name_stance`, `_town_note`, `_has_spoken_to_player`, `_job_talk_with`, `_offer_terms_shown`, `_nobody_here`, `_thread_person`, `_physical_line`, `_job_gate`, `_town_in_play`, `_named_elsewhere_line`, `_town_fallback`, `_person_fallback`, `_experimental_npc_dialogue_context`

- header (as game.py spells it): `import collections` ; `import combat_lifecycle` ; `import hashlib` ; `import interaction_adventure` ; `import living_world` ; `import local_dialogue` ; `import npc_statements` ; `import re` ; `import talk_front` ; `import talk_mode` ; `import tr_case`
- census import targets the mover prefixes (`game.<x>`, no header line): `os`
- census targets moved: `_conversation_npcs`, `_active_interlocutor`, `resolve_npc_reference`, `_is_door_inspection_request`, `record_npc_interaction`, `_remember_owner_locked_tavern_focus`, `_is_stock`, `_experimental_npc_dialogue_context`

**dialogue-2** (`dialogue`, 11 names, 232 lines): `_is_player_name_inquiry_to_npc`, `_is_historical_player_name_query`, `_hero_first_name`, `_explicit_player_name_disclosure`, `_known_player_name`, `_historical_player_name_from_npc_memory`, `_historical_player_name_from_claims`, `_direct_npc_smalltalk_response`, `_conversation_opening_line`, `_stock_hearer`, `_said_to_someone_here`

- header (as game.py spells it): `import living_world` ; `import local_dialogue` ; `import re` ; `import talk_mode`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `_direct_npc_smalltalk_response`

**lore** (`lore`, 14 names, 999 lines): `_filter_unsupported_lore_paragraphs`, `_empty_lore_authority_context`, `_prepare_lore_authority_context`, `_is_registered_lore_name`, `_has_unregistered_narrative_entity`, `_stage_within_the_street`, `_shown_stage_direction`, `_unverified_lore_response`, `_names_the_district_here`, `_narration_has_unsupported_lore_claim`, `_repair_unsupported_lore_narration`, `_scene_has_registered_craft_role`, `_supported_lore_question_response`, `_player_question_has_unverified_lore_claim`

- header (as game.py spells it): `import interaction_adventure` ; `import json` ; `import living_world` ; `import local_dialogue` ; `import re` ; `import scheduled_events`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: none

**narration** (`narration`, 21 names, 484 lines): `_narration_fact_packet`, `_repair_internal_marks`, `_filter_unaccepted_proposal_mentions`, `_drop_absent_counter_sentences`, `_narrator_fact_view`, `create_location_from_proposal`, `_current_npc_name`, `_quiet_place_line`, `_generic_no_change_response`, `_natural_unresolved_action_response`, `_unseen_speaker_repaired`, `should_generate_npcs`, `should_generate_features`, `_rejected_lore_narration`, `_feature_refs_are_visible`, `_ensure_venue_window`, `_bound_on_a_named_word`, `_found_on_a_pass`, `_inspection_findings`, `_repair_attributed_speech`, `_narration_contradicts_supported_name_memory`

- header (as game.py spells it): `import living_world` ; `import re` ; `import tr_case`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `should_generate_npcs`

**nsafety-1** (`narration_safety`, 14 names, 426 lines): `_unregistered_persistent_object_claim`, `_unregistered_held_object`, `_resolve_campaign_npc_reference`, `_unsupported_npc_history_or_relationship_claim`, `_unverified_player_mental_state_trigger`, `_authorized_item_transfer_matches`, `_is_explicitly_negated_transfer`, `_experimental_private_npc_disclosure`, `_unseen_self_introductions`, `_narration_is_unsafe`, `is_player_world_assertion`, `_record_narration_safety`, `_remove_trigger_sentence`, `_unsupported_available_quest_claim`

- header (as game.py spells it): `import interaction_adventure` ; `import json` ; `import living_world` ; `import local_dialogue` ; `import re`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: none

**nsafety-2** (`narration_safety`, 1 names, 1054 lines): `_narration_safety_decision`

- header (as game.py spells it): `import campaign_time` ; `import combat_lifecycle` ; `import living_world` ; `import local_dialogue` ; `import npc_statements` ; `import re`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `_narration_safety_decision`

**lwt** (`living_world_turn`, 4 names, 216 lines): `ensure_campaign_clock`, `_living_world_prompt_context`, `_observe_anchored_structure`, `resolve_scene_seating`

- header (as game.py spells it): `import campaign_time` ; `import interaction_adventure` ; `import json` ; `import living_world`
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: none

**newgame** (`new_game`, 1 names, 197 lines): `initialize_game`

- header (as game.py spells it): none
- census import targets the mover prefixes (`game.<x>`, no header line): none
- census targets moved: `initialize_game`

**schemas-options** (`schemas`, 1 name, 15 lines): `_EXPERIMENTAL_NPC_SPEECH_OPTIONS`

- header: none. It is a dict of numbers (data only).
- reader: `parse_player_intent` only (sensitive, stays). Content: model sampling options, no money key (read at `b1150df8`). Plan 2 held it only because of the D-376 false alarm. Its move in Task 9 is the live proof that D-376 is fixed.

**Header notes.**
- `cr`: `routing_audit` R3 refuses a part that imports a census-target name. The `api.core_resolution` statement binds `resolve_saving_throw` (census kind `import`). The batch reads only `resolve_skill_check` from it (measured). The plan's M5 Ruling: copy a multi-name `from X import (...)` in the same form and order, with only the names the batch reads, and never a census target.
- `dialogue-1` reads `os` (census `import`, in `_npc_speech_enabled`). The mover writes `game.os`. (`effect_lifecycle` and `uuid4` were read only by `advance_campaign_time`, now held.) They get no header line.

## D. Risk checks on the T4 move set (`t4_checks.py`, b1150df8)

Absent (0 found):
- `global` statements;
- identity names (`__name__`, `__file__`, `globals`, `locals`, `vars`, `__builtins__`, `sys.modules`);
- reads of the 22 character globals;
- decorators;
- builtin `open`;
- annotated assignments;
- constant clusters split across modules;
- free reads that are neither engine nor builtin names;
- T4 callers of the narrative-adapter names (`build_world_context`, `ask_dungeon_master`, `finalize_narration`): their callers are all sensitive and stay;
- names inside a top-level `if`/`try` (D-363 not triggered);
- mentions of T4 names in `docs/engine-split/source-readers.md`.

Present:
- **Non-constant defaults:** `_has_unregistered_person_name` (`()`), `initialize_game` (`input`, `print`: builtins, not engine names).
- **`_session` reads:** 107 T4 functions read `_session` (NEVER_MOVED, census target). Each read becomes `game._session()`, one `_GameModule.__getattribute__` call per read. This is a speed risk (plan Review Focus 1). One T4 function reads `RULE_ORDER`.
- **In-function imports:** 56 functions hold them. They move with the function, untouched.
- **Census targets that move (23), with their patch sites** (`patch_census.scan`):
  - `roll_attack` 131, `roll_damage` 65, `roll_initiative` 59, `roll_initiative_player` 55;
  - `_experimental_npc_dialogue_context` 8, `roll_initiative_npc` 6;
  - 4 each: `_current_door`, `apply_check_outcome_to_world_state`, `validate_intent`, `resolve_npc_reference`, `active_npcs`;
  - held by the fix waves (not moved): `advance_campaign_time` 12, `commit_location_change` 4, `_promote_scene_referent` 2, `_fallback_narration` 1;
  - `_narration_safety_decision` 3;
  - 2 each: `initialize_game`, `_direct_npc_smalltalk_response`;
  - 1 each: `_local_place_recommendation_options`, `_is_stock`, `record_npc_interaction`, `_is_door_inspection_request`, `_conversation_npcs`, `should_generate_npcs`, `primal_knowledge_check_admission`, `_active_interlocutor`, `_remember_owner_locked_tavern_focus`.
- **Patch sites on the 27 sensitive leftovers** (they stay; listed for Plan 4): `ask_dungeon_master` 42, `parse_player_intent` 30, `perform_skill_check` 24, `plan_living_world_turn` 8, `finalize_narration` 6, `normalize_intent` 4, `_bind_world_update_mentions` 2, `execute_intent` 2, `validate_world_updates` 2, `build_world_context` 1, `_job_fallback` 1.
- **Money/save/death/Undo test files that patch a moved name** (`review_patch_scan.py`, rerun in the fix wave; reviewer check in the move task, named in its M10):
  - `test_persistence_idempotency` patches `roll_attack`, `roll_damage` (cr) and the held `_promote_scene_referent` (fix wave 2);
  - `test_death_system` and `test_dilim4a_death_audit` patch `roll_damage` (cr); `test_roadmap_k07_condition_persistence` patches `roll_attack` (cr);
  - `test_d207_written_purse` calls `create_npc_from_ai` and `give_person_purse` (the name is held; the file stays in Task 8's M10 as the purse guard);
  - held, so no longer a moved-name patch: `test_economic_room` (`commit_location_change`), `test_death_bounded` (`advance_campaign_time`); fix wave 2: `test_money_path_repair` (`_settle_spoken_commitment`), `test_ambient_actions` (`_promote_scene_referent`), `test_last_play_blockers` (`_states_the_failed_check`), `test_npc_p2_continuity` (`_fallback_for_action_result`), `test_job6_compound_trace` (`_fallback_narration`), `test_query_review_acceptance` (`_handle_query`);
  - `test_shops` patches `validate_intent` (intent-2);
  - `test_equipment_economy` patches `resolve_npc_reference` (dialogue-1);
  - `test_action_economy*` patch `roll_attack`/`roll_damage`; this is combat action economy, not money.
- **Touching test modules** (`inventory.touching_tests`) per module:
  - character_rules 114, places 300, intent 10, dialogue 301, lore 306, narration 6 (7 before fix wave 2), narration_safety 296;
  - living_world_turn 6 after the holds (`api.tests.test_attack_narration_api_integration`, `api.tests.test_f04_frozen_narrator_faults`, `api.tests.test_identity_entity_acceptance`, `api.tests.test_model_isolation`, `test_regression`, `test_sessions`); 19 before, and the 13 dropped ones, among them `test_economic_dialogue` and `test_death_bounded`, read only `advance_campaign_time`;
  - new_game 2 (`test_sessions`, `test_startup`).
  - Over 60 modules → M10 runs through `slot_gate.sh` (Plan 2 rule).
- **`session=` callers:** 42 engine names are called with `session=` from outside `game.py` (192 calls). 15 of them move in Plan 3 (plan Review Focus 4; `commit_location_change` is held):
  - character_rules: `initialize_species_trait_state`, `roll_stat`;
  - places: `_walked_there`, `resolve_location_reference`, `update_inventory_from_player`;
  - intent: `is_npc_historical_claim`, `known_character_answer`;
  - dialogue: `_direct_npc_smalltalk_response`, `_npc_speech_is_claim_refusal`, `record_npc_interaction`, `resolve_npc_reference`;
  - narration: `_generic_no_change_response`, `_inspection_findings`;
  - living_world_turn: `_living_world_prompt_context`, `ensure_campaign_clock`.
- **`game.X` reads outside `game.py`:** 84 T4 movers are read this way (counted before the fix-wave holds; Task 4 Step 2 measures it again).
- **Production rebinding of a moved name:**
  - `trace_ai_pipeline.py` assigns `game.validate_intent`. Its caller `_run_player_turn_internal` stays; its caller `analyze_player_action` moves to `intent`; `update_world_state_from_player` is held (fix wave 2). No mover reads `execute_intent` any more.
  - `api/narrative_director.install_narrative_context_adapter` wraps only sensitive names that stay.
  - `api/ollama_adapter.install_for_engine` sets attributes on the `ollama` module object. No T4 mover reads `ollama`.
  - So the spec's T4.6-9 "adapter" test is measured as the `validate_intent` rebinding test (plan Task 9). The narrative-adapter test moves with its names to Plan 4/5.
- **`test_talk_mode_writers` pins:**
  - `test_no_product_call_passes_a_people_list_to_current` pins the files that call `talk_mode.current` to `["api/serializers.py", "game.py"]`. Callers `_active_interlocutor` and `_said_to_someone_here` move to `game_parts/dialogue.py`; `_run_player_turn_internal` stays (plan Task 10, approval list §21).
  - `test_every_interlocutor_clear_names_its_reason` expects `("game.py","combat")` and `("game.py","ended")`. Its callers `_start_combat_with_initiative` and `_dispatch_player_turn` stay, so it is unchanged.

## E. Later plans and the leftovers (informational; Plans 4-5 measure again)

**character_rules** sensitive (1): `perform_skill_check`

**places** sensitive (3): `clean_location_description`, `_ensure_local_merchant`, `_scene_presence_text`

**intent** sensitive (4): `deterministic_check_for_action`, `parse_player_intent`, `normalize_intent`, `execute_intent`

**dialogue** sensitive (7): `_npc_answers_to`, `_offer_talk_with`, `_job_fallback`, `_coin_persuasion`, `_show_coin_roll`, `_with_only_backed_money`, `_experimental_speech_note`

**lore** sensitive (1): `_lore_entity_names`

**narration** sensitive (10): `validate_world_updates`, `_bind_world_update_mentions`, `merge_world_updates`, `_narrator_shop_record`, `build_world_context`, `_dm_response_schema_for_turn`, `ask_dungeon_master`, `_finding_says_too_much`, `_narrated_money_can_lie`, `finalize_narration`

**narration_safety** sensitive (0): 

**living_world_turn** sensitive (1): `plan_living_world_turn`

**new_game** sensitive (0): 

**combat_flow** non-sensitive (52): `long_rest_gap_seconds`, `_death_state_defaults`, `ensure_death_state`, `PlayerCannotAct`, `require_player_can_act`, `stabilize_player`, `attempt_player_stabilization`, `heal_player`, `set_player_max_hp`, `apply_npc_damage`, `_apply_player_damage`, `_combat_defaults`, `_combat_record_for_actor`, `_sync_combat_participant_records`, `person_fight_kind`, `_person_fight`, `ensure_npc_enemy_stats`, `ensure_npc_combat_stats`, `resolve_combat_target`, `_set_temporary_hit_points`, `grant_temporary_hit_points`, `_species_bonus_action`, `_species_player_turn_id`, `_apply_species_on_hit_effects`, `_finish_species_player_turn`, `resolve_species_trait_action`, `resolve_attack`, `register_attack_hook`, `_combat_participant_can_act`, `_spares_the_fallen`, `_combat_end_if_decided`, `_resolve_enemy_turns_until_player`, `find_weapon_in_inventory`, `start_combat`, `resolve_enemy_attack`, `_reduce_attack_damage_to_player`, `_storm_thunder_reaction`, `_apply_attack_damage_to_player`, `end_combat`, `join_combat_participants`, `remove_combat_participant`, `register_initiative_hook`, `advance_combat_turn`, `_combat_snapshot`, `_finish_combat_result`, `_public_combatant_label`, `_combat_narration`, `_enemy_exchange_text`, `_death_closing`, `_death_save_line`, `_down_outside_combat_turn`, `_death_resolution_from_actions`

**combat_flow** sensitive (9): `_capture_combat_death_checkpoint`, `_restore_combat_death_checkpoint`, `_finalize_player_death`, `_migrate_legacy_combat_state`, `ensure_combat_state`, `_mark_combat_action_used`, `_resolve_player_death_turn`, `_start_combat_with_initiative`, `_begin_combat_actor_turn`

**coin** non-sensitive (5): `_SOMEONE_ELSES_PURSE`, `_SHOP_ECONOMY_PATTERN`, `_SHOP_TRANSACTION_REQUEST_PATTERN`, `_SHOP_ENTITY_QUERY_PATTERN`, `_SHOP_CREATION_ACTION_PATTERN`

**coin** sensitive (10): `_is_shopkeeper_role`, `_runs_a_shop`, `_campaign_has_shopkeeper`, `_explicit_campaign_shop_request`, `_shop_economy_request`, `_explicit_campaign_shop_negative_request`, `_shop_presence_question`, `generate_shop_id`, `validate_shop_proposal`, `create_shop_from_proposal`

**savefile** non-sensitive (11): `SAVE_FORMAT_VERSION`, `_SUPPORTED_SAVE_VERSIONS`, `_validate_species_trait_state`, `_origin_choices_valid`, `_PERSISTED_PLAYER_CONDITION_FIELDS`, `_validate_player_condition_state`, `_validate_player_weapon_proficiencies`, `_validate_long_rest_history`, `_repair_dilim1_fields`, `_known_happenings`, `_repair_dilim2_fields`

**savefile** sensitive (8): `_origin_choices_for_save`, `_player_state_for_save`, `serialize_game_state`, `_validate_combat_v3_payload`, `_validate_saved_multilevel_slots`, `_validate_save_payload`, `save_game`, `load_game`

**turn** non-sensitive (38): `ResolvedTurn`, `_has_session`, `DEBUG_MODE`, `TurnResolved`, `_hideout_check`, `_adventure_scene_turn`, `_adventure_check_reply`, `_everyday_action_turn`, `_local_place_turn`, `_intent_infrastructure_result`, `turn_source_key`, `run_player_turn`, `COIN_LEFT_BEHIND`, `_run_player_turn`, `_last_call`, `combat_refusal_turn`, `_approach_turn`, `player_cannot_act_turn`, `_reads_as_address`, `_addressed_in`, `_front_recovery`, `_blow_stands`, `_blow_in_the_words`, `_ask_about_the_blow`, `_heavy_allowed`, `_ask_before_the_heavy`, `_answered_heavy_question`, `_ask_which_move`, `_narrated_person`, `_front_consume`, `_front_wield`, `_front_work`, `_take_names_a_job`, `_front_take`, `_dispatch_turn_body`, `_spoken_rest_of_turn`, `_owner_module_reply`, `_dynamic_engine_transitions`

**turn** sensitive (31): `_carry_out_thread_turn`, `_thread_gate`, `_world_snapshot`, `_changed_state_fields`, `_execute_intent_internal`, `_clear_turn_transients`, `_run_player_turn_owned`, `_tell_the_coin`, `_run_player_turn_keyed`, `_the_rest_of_the_line`, `_person_answers_stock`, `_front_step`, `_defer_spoken_coin_offer`, `_record_spoken_coin_response`, `_economic_listing`, `_front_economic_offer`, `_purchase_refused`, `_hand_over_coin`, `front_read_ahead`, `_front_offer_gate`, `_line_gives`, `_coin_not_parcel`, `_names_no_parcel`, `_front_hand_over`, `_dispatch_player_turn`, `_sleep_after_walk`, `_current_procedural_entity_ids`, `_keep_town_portrait`, `_narrate_resolved_turn`, `_run_player_turn_internal`, `_restore_in_place`

**schemas** sensitive (0): 

**misfits applied:** `_claimed_completed_outcome` intent->dialogue, `_conversation_opening_line` places->dialogue, `_drop_absent_counter_sentences` dialogue->narration, `_ensure_location_entities` intent->places (fix wave: ->held_plan4, its only caller `commit_location_change` is held), `generate_npc_id` places->held_plan4 (fix wave; only caller `create_npc_from_ai`), `_fallback_narration` narration->held_plan4 (fix wave 2; only caller `_fallback_for_action_result`), `_experimental_speech_final_line` dialogue->intent, `_local_place_recommendation_guidance` places->intent, `_narration_contradicts_supported_name_memory` dialogue->narration, `_observe_anchored_structure` places->living_world_turn, `_rejected_lore_narration` lore->narration, `_repair_attributed_speech` narration_safety->narration, `_travel_destination_reference_in_text` places->intent, `_unseen_speaker_repaired` narration_safety->narration, `_unsupported_available_quest_claim` places->narration_safety, `_validate_species_trait_state` character_rules->savefile, `create_location_from_proposal` places->narration, `long_rest_gap_seconds` savefile->combat_flow, `named_by_sight` places->dialogue, `resolve_scene_seating` places->living_world_turn

`COIN_LEFT_BEHIND` lands in the `turn` region by file position, but Plan 2's held table sends it to Plan 4 (money); Plan 4's own M2 decides.

**Plan 2's held names (D-378) that Plan 3 moves:**
- cr: `get_modifier`, `choose_option`, `choose_skill_proficiencies`, `calculate_hp`, `calculate_ac`, `_new_species_trait_state`, `roll_attack`, `roll_initiative`, `roll_initiative_npc`;
- places: `_venue_door_id`, `_mark_lock_seen`, `_lock_known_to_player`, `_local_place_access`, `_a_walk`, `_is_canonical_city_id` (`_adventure_travel_reply` is held for Plan 4 by fix wave 2);
- dialogue: `_town_in_play` (measured: dialogue, not places — its callers are dialogue helpers), `_said_to_someone_here`, `_STOCK_SAID` (with `_stock_said`);
- lore: `_empty_lore_authority_context`, only when `F_fon` is empty (plan Task 0);
- schemas: `_EXPERIMENTAL_NPC_SPEECH_OPTIONS`.

**Still held after Plan 3:**
- Plan 5: `turn_source_key`, `_intent_infrastructure_result`, `_dynamic_engine_transitions`, `DEBUG_MODE`, `_has_session`;
- Plan 4: `_EXPERIMENTAL_NPC_SPEECH_SCHEMA` and the savefile, death and money rows;
- Plan 4 (fix-wave holds, money/death two-hop writers): `create_npc_from_ai`, `commit_location_change`, `advance_campaign_time`, with their only-callee helpers `generate_npc_id`, `_ensure_location_entities`;
- Plan 4 (fix-wave 2 holds, transitive writer scan): `_commit_travel_action`, `_adventure_travel_reply`, `_promote_scene_referent`, `_handle_query`, `update_world_state_from_player`, `_settle_spoken_commitment`, `_fallback_for_action_result`, `_states_the_failed_check`, with the helpers `_fallback_narration` and `_stands_by_their_words`.
