# Combat Test Matrix

Bounded contract verification of the current checkout; not exhaustive permutations,
new gameplay, or dedicated Persistence/UI work. Python is the combat authority.
Production source was recorded before test edits. Existing coverage was inventoried
and mapped before selecting the seven additional tests.

## Checkout and evidence

- Checkout: `/home/runner/workspace`; branch: `main`.
- HEAD: `0a0067c7c75c23e9efa43e328a2c82e2d60e88c4`.
- Starting checkout was dirty from the preceding Spell Scope work. Its exact
  status and guarded Python-file hashes are in `evidence/combat-test-matrix/start.json`.
- Focused: **7 passed / 0 failed / 0 errors / 0 skipped**:
  `evidence/suite-runs/20261004T131032Z-6d18828ebb5141cba379c1e7a5c028fe/run.json`.
- Combined: **600 passed / 0 failed / 0 errors / 0 skipped**:
  `evidence/suite-runs/20261004T131140Z-ccce149d074a42d9b70e8977c7b23c84/run.json`.
- These are current-run results, not retroactive certification of historical runs.
  Exact selectors, UTC timestamps, test IDs, logs, full revision, working-tree
  identity and source fingerprints are retained by the existing evidence runner.
- Production comparison: `evidence/combat-test-matrix/production-guard.json`.
- HTTP checks use real FastAPI handlers with ASGI transports and temporary stores;
  model responses are controlled/mocked. This is not live-network/live-Qwen proof.

## Existing inventory and genuine gaps

Existing lifecycle, economy, initiative, weapon, monster, death, spell, time,
campaign and bounded-encounter suites already cover the individual contracts below.
They are reused, not rewritten. Core-resolution and character-creation suites
support shared dice/access validation. Existing narrative-director, model-isolation,
narrative-rebalance and safety-calibration checks cover model authority.

Missing explicit combinations selected before implementation:

1. Lethal spell + surviving opponent + safe initiative continuation.
2. Native monster hit + real player zero-HP damage + scheduled death save.
3. Native Multiattack + first-component NPC death + no further damage + child replay.
4. Open combat with spent spell/action resources + Stable episode + fresh-manager resume.
5. Sequential first/second/third death counters, including counter clearing at Stable.
6. Actual Long Rest entry point + spell recovery hook + authoritative eight-hour duration.
7. Spell HP/slot/action/RNG mutation + failed autosave + rollback + retry/replay/isolation.

New coverage is only `api/tests/test_combat_test_matrix.py`; existing helpers are reused.

## Contract matrix

Test-module shorthand below is `api.tests.test_<name>` unless explicitly marked
legacy. Listed named methods are inside the module's test classes; full IDs are
in the combined run record. Every PASS row was included in that run.

| Contract ID | System / scenario | Authoritative owner | Test(s) | Expected canonical result | Evidence/result | Status |
|---|---|---|---|---|---|---|
| CTM-LIFE-001 | Start, threat/model proposal, identity/membership/current actor | `combat_lifecycle`, `game.start_combat` | `combat_lifecycle`: hostility/model-proposal, active-identity, current-actor and explicit-start checks | Only authoritative start creates valid combat; proposals do not | Combined | PASS |
| CTM-LIFE-002 | Invalid/stale request; wrong actor; no weapon | `validate_request`, action/attack owners | `combat_lifecycle`: `test_invalid_stale_and_malformed_requests_do_not_mutate`, `test_wrong_actor_and_no_weapon_do_not_roll` | No dice/resource/time/history mutation | Combined | PASS |
| CTM-LIFE-003 | Closure, closed actions, stale-context replay | Lifecycle + campaign receipts | `combat_lifecycle`: `test_closed_identity_is_retained_and_close_is_idempotent`, `test_verified_hit_end_preserves_history_without_extra_time` | Closure idempotent; new closed-context action rejects; receipt replay succeeds first | Combined | PASS |
| CTM-LIFE-004 | Uncommitted outcome / autosave failure | API snapshot + campaign transaction | `combat_lifecycle`: `test_persistence_failure_rolls_back_result_history_rng_and_time` | No uncommitted combat outcome sent to Qwen | Combined | PASS |
| CTM-AE-001 | Action, supported Bonus Action, movement, prone/Dash | `action_economy` | `action_economy`: action/bonus order, bonus-only-once, move-attack-move, movement-condition checks | One shared budget; feature-backed bonuses only | Combined | PASS |
| CTM-AE-002 | Reaction and Ready boundary | `action_economy` | `action_economy`: correct-reset-boundary, round-does-not-reset, Ready-expiration checks | Reaction resets on actor turn, not global round | Combined | PASS |
| CTM-AE-003 | Incapacity/wrong actor/invalid compound action | Existing condition/Death owners + atomic execution | `action_economy`: `test_conditions_and_death_cannot_bypass_any_resource_path`, `test_compound_invalid_request_rolls_back_prior_step` | Invalid sequence cannot partially consume budgets | Combined | PASS |
| CTM-AE-004 | Partial-turn save/replay | Campaign store + economy ledger | `action_economy`: `test_campaign_resume_keeps_partial_turn_and_replay` | Save/load and retry do not refresh/spend twice | Combined | PASS |
| CTM-AE-005 | Supported simple interactions | Current action/weapon interfaces | `weapon_attack`: existing equip/ammunition/thrown and interaction checks; `action_economy` supported sequences | Only implemented interactions; no new general free-action family | Combined | PASS |
| CTM-INIT-001 | Dice/modifier, advantage/disadvantage, 2024 Surprise, ties/groups | `initiative`, shared d20 resolver | `initiative`: modifier, advantage/cancellation, surprise, tie and explicit-group tests | Authoritative rolls; deterministic ties; Surprise does not skip first turn | Combined | PASS |
| CTM-INIT-002 | Join/leave/progress/dead and unconscious slots | Initiative + lifecycle/Death | `initiative`: newcomer/removal, zero/unconscious/Stable slot and death-save-owner tests | No reroll or extra turn; dead actors cannot act | Combined | PASS |
| CTM-INIT-003 | Resume, replay, isolation | Campaign serialization + receipts | `initiative`: `test_campaign_resume_has_exact_cursor_results_and_receipts`, receipt/start replay and isolation tests | Exact order/cursor/RNG preserved | Combined | PASS |
| CTM-ATK-001 | Melee/ranged/thrown, target/range/proficiency/ability | `weapon_attack.prepare/resolve` | `weapon_attack`: `test_melee_ranged_thrown_shared_path`, proficiency/non-proficiency and invalid geometry checks | Legal attack uses sourced modifiers; invalid attack has no consumption | Combined | PASS |
| CTM-ATK-002 | Natural 1/20, critical, advantage/disadvantage/conditions | Shared attack resolver + attack owner | `weapon_attack`: natural-one/twenty, critical-dice, unseen/condition tests; `core_resolution` | Attack outcome/damage follow shared rules | Combined | PASS |
| CTM-ATK-003 | Damage handoff and replay | Existing HP/Death owners + receipts | `weapon_attack` HTTP replay; `death_system` unconscious melee critical; `death_bounded` actual damage-at-zero replay | Exactly one real HP/death handoff per committed action | Combined | PASS |
| CTM-MON-001 | Legal targets/incapacity/perception/missing geometry | `monster_combat`, perception + attack owners | `monster_combat`: target filters, down-to-zero reprioritization, route and geometry checks | No invented visibility/path/attack or dead target | Combined | PASS |
| CTM-MON-002 | Exact Multiattack and exhausted/unsupported components | Capability validation + native executors | `monster_combat`: exact-slot, choice-combination, no-invented-Multiattack and limited-use checks | Only available configured components execute | Combined | PASS |
| CTM-MON-003 | Limited uses/recharge/combat identity/Opportunity Attack | Monster resources + reaction/route owners | `monster_combat`: resource, recharge, new-combat identity, native route and reaction checks | No combat-ID resource refresh; unknown routes fail safely | Combined | PASS |
| CTM-MON-004 | Morale/parley/acceptance/model independence | Python planner + lifecycle | `monster_combat`: player accept/reject/question and native HTTP replay checks | No forced acceptance or Qwen-authored mechanics | Combined | PASS |
| CTM-DEATH-001 | Counters, natural 1/20, Stable/Dead | `_resolve_player_death_turn`, Death owner | `death_system`, `death_bounded`; new sequential-counter test | First/second progress; third success clears counters into Stable; third failure Dead | Combined + focused | PASS |
| CTM-DEATH-002 | Massive/zero-HP/critical damage, temporary HP, self-damage | Shared player damage + species/Death owners | `death_system`, `death_bounded`, `species_traits` damage/Inner Radiance checks | Same Death owner; correct boundary/cause/dice, not final-state-only proof | Combined | PASS |
| CTM-DEATH-003 | Healing, stabilization, Prone | `heal_player`, stabilization primitives | `death_bounded`: medicine/healing/natural-twenty checks | Correct transitions; supported primitive is not certification of an absent external actor route | Combined | PASS |
| CTM-DEATH-004 | Persisted episode/deadline, no wall clock, no reroll | Death recovery + Campaign Time | `death_bounded`: recovery cancellation, duration sources, Stable resume/replay; new Stable composite | One recovery episode; time-driven recovery exactly once | Combined + focused | PASS |
| CTM-DEATH-005 | Modes, rollback/no auto deletion, NPC Policy A/history | Death owner + campaign metadata | `death_system`, `death_bounded`, `campaign_api` death tests | Normal rollback preserved; Permadeath/Ironman persist without deletion; historical NPC unconscious canon retained | Combined | PASS |
| CTM-SPELL-001 | Access, cantrip/slot/action, invalid cast/target/range | `spell_scope`, existing creation/action owners | `spell_scope`: access, scaling, atomic rejection, per-turn slot checks | Only declared compatible selections/modes; rejection consumes nothing | Combined | PASS |
| CTM-SPELL-002 | Attack/save/DC/damage/healing/death | Shared attack/save/damage/healing owners | `spell_scope`: attack/critical, save/DC/cover, mitigation/Policy A and healing-owner checks | Python resolves exact declared modes through existing owners | Combined | PASS |
| CTM-SPELL-003 | Save/resume/replay/isolation/zero calls | Existing campaign persistence + receipts | `spell_scope`: `test_http_replay_save_restart_and_isolation_zero_models` | No recast/reroll/reconsume; fresh-manager resources preserved | Combined | PASS |
| CTM-X-001 | Lethal spell with remaining enemy | Spell → damage → Death → initiative | New `test_spell_lethal_damage_preserves_surviving_opponent_and_cursor` | One damage handoff; NPC Dead; same combat continues to survivor | Focused + combined | PASS |
| CTM-X-002 | Native monster hit → player zero → scheduled save | Planner → weapon → Death → initiative | New `test_native_monster_damage_keeps_player_slot_and_schedules_death_save` | Verified positive HP damage; retained slot; one save at player boundary | Focused + combined | PASS |
| CTM-X-003 | Multiattack kills NPC first component | Native Multiattack → NPC Death → child checkpoint | New `test_multiattack_stops_after_first_component_kills_npc` | Planned three components; only one resolved damage; replay inert | Focused + combined | PASS |
| CTM-X-004 | Stable + spent resources + restart equivalent | Campaign store + Death/time + action/spell ledgers | New `test_stable_resume_preserves_spent_spell_action_and_recovery_episode` | Open combat/cursor/slots/action/deadline/RNG survive fresh manager | Focused + combined | PASS |
| CTM-X-005 | Spell mutation + autosave failure + retry | API snapshot + existing store/receipts | New `test_spell_autosave_failure_restores_damage_healing_slots_rng_and_receipt` | Actual damage/healing executed before failed save; fully rolled back; retry commits once; B unchanged | Focused + combined | PASS |
| CTM-X-006 | Long Rest reaches spell hook | Species/rest entry → spell resources → clock | New `test_long_rest_reaches_spell_resource_hook_and_authoritative_clock` | Slot restored, turn marker retained, exactly eight authoritative hours | Focused + combined | PASS |
| CTM-X-007 | Weapon → NPC death → continuation | Existing weapon/Death/initiative | `combat_lifecycle` verified-hit/end; `initiative` safe dead removal/last-departure; `weapon_attack` damage tests | Existing supported transitions compose; spell continuation adds a separate cross-owner check | Combined | PASS |
| CTM-TIME-001 | Round, closure, rejected action and replay | Existing turn scheduler + Campaign Time | `combat_lifecycle`: round/partial-end and verified closure; `initiative` last-actor wrap; time-edge combat interruption checks | One six-second completed round; no duplicate exit/retry/rejection time | Combined | PASS |
| CTM-TIME-002 | Stable recovery uses authoritative time | Death recovery + clock | `death_bounded`, new Stable composite | Not wall-clock; exact deadline; no duplicate recovery entropy | Combined + focused | PASS |
| CTM-PERSIST-001 | Combat/order/HP/Death/economy/resources resume | Existing campaign serializer/store/manager | `initiative`, `action_economy`, `monster_combat`, `death_bounded`, `spell_scope` resume checks | Restore canonical truth, not regeneration | Combined | PASS |
| CTM-PERSIST-002 | Receipt before stale validation; no second effects | API receipt owner | Lifecycle/economy/initiative/monster/spell HTTP replay tests | Identical result; no repeated dice, HP, resource or time mutation | Combined | PASS |
| CTM-PERSIST-003 | Failed save and campaign isolation | Existing snapshots and atomic campaign store | Existing lifecycle/economy/death failure checks; new spell failure check | Runtime and persistence retain last good state; other campaign untouched | Combined + focused | PASS |
| CTM-MODEL-001 | Mechanics without Qwen authority | Native Python executors | Native lifecycle/monster/bounded/spell HTTP tests; new spell failure/continuation | Zero-call behavior valid; Qwen cannot roll/set HP/consume resources/decide death | Combined + focused | PASS |
| CTM-MODEL-002 | Read-only context and rejected combat claims | Context builder + existing safety guard | `narrative_director`: request-scoped context/no mutation; legacy safety calibration combat-target/damage test | Context remains unchanged; prose cannot contradict Python outcome | Combined | PASS |
| CTM-MODEL-003 | Ceiling, fallback, no retry, no prose mutation | Existing model-budget/narration owners | Legacy narrative-rebalance `test_03`, `test_04`, `test_05`; `model_isolation` | At most two calls; deterministic fallback; no rejection retry/canonical prose mutation | Combined | PASS |

## Scope and evidence limitations

- Actual Spell Scope is `spell-scope.md` plus `spell_scope.py`, not its original
  implementation prompt. Cure Wounds is conscious self-healing only. A zero-HP
  player spell recipient via an external caster is **not supported**; existing
  engine healing-at-zero and spell self-cast rejection are tested separately.
- Deferred preparation, concentration, AoE, persistent conditions/duration,
  ritual/material economy, summons, transformations, reaction/Bonus Action spell
  catalogs, object ignition and external-caster architecture are not claimed.
- Multiattack composition uses the existing explicit capability fixture and
  native weapon executor. It does not certify a newly sourced monster catalog.
- Stable/stabilization engine primitives do not create an allied-NPC control route.
  Trusted clock advancement does not certify a user wait command during active combat.
- Fresh campaign-manager restore is restart-equivalent persistence proof. The
  legacy bare engine JSON snapshot is not the campaign RNG persistence envelope;
  the initial wrong harness assumption was corrected, not the production format.
- Initial failed focused runs and the selector-loading failure remain retained.
  Fixture repairs corrected namespace/scene/perception/dice/result-shape assumptions
  and the documented Stable counter reset. No gameplay assertion was weakened.
- No production fix, new feature, #11/#12 implementation, Git mutation or publishing.