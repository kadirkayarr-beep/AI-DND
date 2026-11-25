# T3 ledger: narrow or log broad `except Exception` (worktree AI-DND-k2-except, branch task/except-narrow-20261125, slot 9)

Base: main fad9bac9 (T1 #171 and T2 #170 merged). Implementer: Opus. T4 files (world_threads.py, bold_acts.py, living_world.py) untouched.

## Step 0: shim removal
- Grep of ai-dnd (code, tests, function-level imports, JSON locks, tools/, content/, scripts/): no import of `api.core_resolution` / `api.model_phase` was left; only docs mention the old paths (left as history).
- `git rm` ai-dnd/api/core_resolution.py, ai-dnd/api/model_phase.py.
- api/tests/test_rules_module_identity.py now asserts the root names import and the old `api.*` names raise ModuleNotFoundError.
- Red (shims present): RESULT tests 2 skipped 0 failing_ids 2 PAR_EXIT=1 (run 20261125T203026-s0-red).
- Green: RESULT tests 2 skipped 0 failing_ids 0 PAR_EXIT=0 (run 20261125T203037-s0-green).
- T2 set again (global set + identity + test_core_resolution + money_tests.txt + model-phase tests + coin/economic modules):
  - off: RESULT tests 1253 skipped 1 failing_ids 0 PAR_EXIT=0 (20261125T203156-s0-off)
  - fon (gate_boot first): RESULT tests 1253 skipped 1 failing_ids 0 PAR_EXIT=0 (20261125T203625-s0-fon)
- Debt row D-583 added (text as given by the plan owner).
- Commit 8974dd31.

## Rulings
- Ruling: census scope = production .py under ai-dnd excluding tests/, scripts/, docs/, reports/, root test_*.py / live_*.py / acceptance_test.py / run_tests.py scripts, api/live_smoke.py and the T4 files; 126 sites (plan estimate ~128) — the root test_*/live_* files are dev scripts, not served code — if wrong, ~25 script sites stay unlisted, no player effect.
- Ruling: a site that re-raises (rollback then `raise`, or a typed `raise X from None`) is not "swallowing"; it stays unchanged — narrowing or logging there adds nothing the caller does not already see — if wrong, some typed re-raises (campaign_validation, auth) hide the original cause from the server log.
- Ruling: class B keeps one broad catch and classifies by type inside the shared `model_phase.log_fallback` (adapter outage RuntimeError/TimeoutError/OSError -> DEBUG, any other type -> WARNING with trace) instead of two except clauses — the fallback body is identical for both, so two clauses would duplicate it, and the size locks leave little room — if wrong, a reviewer may want literal `except (RuntimeError, TimeoutError, OSError)` clauses; behaviour is the same either way.
- Ruling: RuntimeError/TimeoutError/OSError are the adapter's real types: AuthenticatedOllamaAdapter.chat re-raises every failure as RuntimeError("Ollama request failed."), OllamaUnavailableError/RequiredModelUnavailableError subclass RuntimeError, the budget refusal is RuntimeError; httpx TransportError is caught inside model_chain — if wrong, an outage logs a WARNING instead of DEBUG.
- Ruling: B fallbacks log on their own module logger, never on `ai_dnd.api.ollama`, so the assertNoLogs("ai_dnd.api.ollama", "WARNING") tests are untouched.
- Ruling: three sites parked (D-584): narration.py ask_dungeon_master l.1179 and l.1220 (function at its 299-line lock) and game.py _speech_debug_trail l.340 (game.py at its 1164-line lock). Locks only shrink, so no log line fits — if wrong, two narration fallbacks and one debug-file write stay silent until ask_dungeon_master is split.
- Ruling: grounded_action.resolve_turn had a function-local `import logging` in its second except; my new log line in the first except made `logging` a local referenced before assignment (ruff F823, would raise UnboundLocalError). Removed that local import (module already imports logging) — required by my change, not cleanup.
- Ruling: class-progression A sites log at ERROR via `logging.getLogger(__name__).exception` ("class_progression.<module>"); runtime_recovery logs on "ai_dnd.api.runtime_recovery" — neither logger is under an assertNoLogs in the suite.

## Census (126 sites; class A money/save/Undo, B model or network, C best-effort, D already narrow / typed re-raise)
Counts: A 69 (8 changed), B 19 (5 changed, 1 parked), C 33 (11 changed, 2 parked), D 5 (0 changed). Changed total 24.

| file:function (line at fad9bac9+step0) | caught | class | decision |
|---|---|---|---|
| action_economy.py:execute (l.899) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:accept_thread_job (l.137) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:hand_over (l.290) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:deliver (l.324) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:deliver_late (l.345) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:give_plain (l.367) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:abandon_thread_job (l.407) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/dialogue_jobs.py:cancel_job (l.420) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| adventure/rewards.py:apply_plan (l.81) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/auth.py:authenticate (l.279) | Exception | D | no change: re-raises (typed auth error / closes socket) |
| api/auth.py:_b64url_decode (l.311) | Exception | D | no change: re-raises (typed auth error / closes socket) |
| api/clerk_auth.py:verify (l.145) | Exception | D | no change: re-raises (typed auth error / closes socket) |
| api/clerk_auth.py:authenticate_asgi (l.444) | Exception | D | no change: re-raises (typed auth error / closes socket) |
| api/clerk_jwks.py:key_for (l.234) | BaseException | B | no change: already logs or re-raises a typed error |
| api/clerk_jwks.py:connect_pinned (l.429) | Exception | B | no change: already logs or re-raises a typed error |
| api/identity_suggestion.py:invoke (l.503) | Exception | B | stays broad (turn/job must not crash); model_phase.log_fallback: adapter types DEBUG, any other type WARNING+trace |
| api/local_play.py:bind_loopback_socket (l.169) | BaseException | D | no change: re-raises (typed auth error / closes socket) |
| api/main.py:_store_refusal (l.160) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/main.py:_commit_already_durable (l.179) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/main.py:_adopt_undo_checkpoint (l.225) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/main.py:resolve_ambient_event_action (l.1385) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/main.py:resolve_ambient_event_action (l.1392) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/model_chain.py:_notify (l.504) | Exception | B | no change: already logs or re-raises a typed error |
| api/model_chain.py:chat (l.547) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:from_environment (l.416) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:spend_warning (l.445) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:_note_local_call (l.458) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:ensure_required_model (l.504) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:warm_up (l.567) | Exception | B | no change: already logs or re-raises a typed error |
| api/ollama_adapter.py:chat (l.628) | Exception | B | no change: already logs or re-raises a typed error |
| api/persistence/campaign_store.py:_transaction (l.280) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.372) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.394) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.409) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.420) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.449) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.466) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_initialize (l.484) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:record_refused_action (l.1213) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:_owned_connection (l.1272) | BaseException | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:claim_action_intent (l.1329) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_store.py:compact_receipts (l.1598) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_validation.py:_validate_engine_save (l.87) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_validation.py:_validate_rng_state (l.143) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_validation.py:serialize_campaign_payload (l.157) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/persistence/campaign_validation.py:restore_campaign_session (l.389) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_economic.py:economic_step (l.58) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_economic.py:economic_step (l.104) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_economic.py:economic_step (l.118) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_economic.py:economic_step (l.148) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_level_up_apply.py:apply_earned_level_up (l.133) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_quests.py:_quest_command (l.102) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_quests.py:_quest_command (l.109) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_species.py:resolve_species_trait_action (l.193) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_spells_write.py:prepare_spells (l.158) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:restore_turn_snapshot (l.130) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:play_turn (l.204) | BaseException | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:play_turn (l.214) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:play_turn (l.219) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:_stage_lore_and_memory (l.752) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:_stage_lore_and_memory (l.779) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:_build_response (l.839) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:_build_response (l.880) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_turn.py:_autosave (l.940) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/routes_undo.py:undo_last_turn (l.158) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/runtime_recovery.py:restore_trusted_runtime (l.36) | Exception | A | log added (_logger.exception); stays broad |
| api/session_manager.py:campaign_save_landed (l.693) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| api/usage_ledger.py:record (l.160) | Exception | C | no change: already logged |
| api/usage_ledger.py:today (l.192) | Exception | C | no change: already logged |
| api/usage_ledger.py:warning (l.237) | Exception | C | no change: already logged |
| arrival_narration.py:narrate (l.192) | Exception | B | stays broad (turn/job must not crash); model_phase.log_fallback: adapter types DEBUG, any other type WARNING+trace |
| character_progression.py:create_at_level (l.593) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| class_progression/barbarian.py:_apply_barbarian_three (l.304) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/noncaster.py:apply_subclass_step (l.63) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/noncaster.py:apply_earned_final_step (l.97) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/noncaster.py:apply_asi_step (l.136) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/paladin.py:_apply (l.245) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/prepared_caster.py:apply_level (l.259) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| class_progression/sorcerer.py:_apply_selected_level_four (l.253) | Exception | A | log added (_LOG.exception); stays broad, reject unchanged |
| combat_lifecycle.py:validate_request (l.660) | BaseException | A | no change: rollback then re-raise, or already logged / typed re-raise |
| dialogue_runtime.py:_generate_reply (l.315) | Exception | B | no change: already logs or re-raises a typed error |
| game.py:_speech_debug_trail (l.340) | Exception | C | PARK D-584: game.py at its 1164-line lock; no line can be added (debug-only path) |
| game.py:_receive_xp_award (l.642) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game.py:_forfeit_unrecordable_xp (l.710) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/character_rules.py:perform_skill_check (l.476) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/dialogue.py:_stock_said (l.625) | Exception | C | stays broad; WARNING log + reason comment |
| game_parts/dialogue.py:_town_note (l.843) | Exception | C | no change: already logged |
| game_parts/dialogue.py:_offer_terms_shown (l.866) | Exception | C | no change: already logged |
| game_parts/dialogue.py:_town_fallback (l.964) | Exception | C | no change: already logged |
| game_parts/dialogue.py:_job_fallback (l.1339) | Exception | C | no change: already logged |
| game_parts/dialogue.py:_settle_spoken_commitment (l.1400) | Exception | C | no change: already logged |
| game_parts/dialogue.py:_repair_npc_speech (l.1598) | Exception | B | no change: already logs or re-raises a typed error |
| game_parts/intent.py:_names_present_creature (l.1056) | Exception | C | stays broad; WARNING log + reason comment |
| game_parts/intent.py:parse_player_intent (l.1366) | Exception | B | stays broad (turn/job must not crash); model_phase.log_fallback: adapter types DEBUG, any other type WARNING+trace |
| game_parts/intent.py:execute_intent (l.1503) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/narration.py:ask_dungeon_master (l.1179) | Exception | C | PARK D-584: ask_dungeon_master at its 299-line lock; no line can be added |
| game_parts/narration.py:ask_dungeon_master (l.1220) | Exception | B | PARK D-584: ask_dungeon_master at its 299-line lock; no line can be added |
| game_parts/narration.py:ask_dungeon_master (l.1318) | Exception | B | no change: reports by print (stdout), not silent |
| game_parts/resolved_narration.py:_rn_money_claim_guard (l.198) | Exception | C | no change: already logged |
| game_parts/savefile.py:load_game (l.1123) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/text_rules_a.py:_job_news_line (l.728) | Exception | C | no change: already logged |
| game_parts/text_rules_a.py:_elsewhere_line (l.748) | Exception | C | no change: already logged |
| game_parts/text_rules_a.py:_overheard_work (l.772) | Exception | C | no change: already logged |
| game_parts/turn.py:_run_player_turn_owned (l.120) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/turn.py:_dispatch_player_turn (l.636) | BaseException | A | no change: rollback then re-raise, or already logged / typed re-raise |
| game_parts/turn_front.py:_thread_gate (l.139) | Exception | A | no change: logged (town_knowledge.log_failure) and rolls back (D-011) |
| game_parts/turn_front.py:_front_step (l.1107) | Exception | C | stays broad; WARNING log + reason comment |
| game_parts/turn_front.py:_front_offer_gate (l.1703) | Exception | C | no change: already logged |
| game_parts/turn_front.py:_front_hand_over (l.1887) | Exception | C | no change: already logged |
| game_parts/turn_front.py:_front_work (l.1910) | Exception | C | no change: already logged |
| game_parts/turn_front.py:_front_take (l.1975) | Exception | C | no change: already logged |
| grounded_action.py:spend (l.1176) | Exception | C | stays broad; WARNING log + reason comment |
| grounded_action.py:_campaign_hour (l.1286) | Exception | C | stays broad; WARNING log + reason comment |
| grounded_action.py:_do_knock (l.1720) | Exception | C | stays broad; WARNING log + reason comment |
| grounded_action.py:model_ground (l.2775) | Exception | B | stays broad (turn/job must not crash); model_phase.log_fallback: adapter types DEBUG, any other type WARNING+trace |
| grounded_action.py:resolve_turn (l.3422) | Exception | C | stays broad; WARNING log + reason comment |
| grounded_action.py:resolve_turn (l.3436) | Exception | C | no change: already logged |
| grounded_action.py:_decide (l.3557) | Exception | C | no change: already logged |
| grounded_action.py:_bookkeeping (l.3709) | Exception | C | no change: already logged |
| incidents/arbiter.py:calls_used (l.34) | Exception | C | stays broad; WARNING log + reason comment |
| incidents/attempts.py:run (l.195) | Exception | B | stays broad (turn/job must not crash); model_phase.log_fallback: adapter types DEBUG, any other type WARNING+trace |
| incidents/npcs.py:_registry (l.27) | Exception | C | stays broad; WARNING log + reason comment |
| incidents/profiles.py:_pack_coverage (l.102) | Exception | C | stays broad; WARNING log + reason comment |
| incidents/profiles.py:_pack_entities (l.120) | Exception | C | stays broad; WARNING log + reason comment |
| initiative.py:atomic (l.32) | Exception | A | no change: rollback then re-raise, or already logged / typed re-raise |
| town_knowledge.py:note_mention (l.993) | Exception | C | no change: already logged |

## Steps 2-4: tests and mutation proofs
New/changed tests:
- api/tests/test_except_logging.py (new): LogFallback (model_phase.log_fallback), ModelFallbacksLog (intent reading, grounded_action.model_ground, identity suggestion job), LevelStepRollbackLogs (all 7 class-progression A sites as subtests: an UnexpectedState(RuntimeError) raised after the snapshot; asserts the same `resulting_state_invalid` reject, the snapshot restored, and an ERROR log carrying that exception), TrustedRestoreLogs (runtime_recovery: a restore raising UnexpectedState answers False, closes the session, logs).
- api/tests/test_arrival_narration.py: Narrate.test_a_model_outage_logs_at_debug_and_any_other_type_warns.
- api/tests/test_incident_gate_a.py: AttemptTests.test_a_failed_proposal_call_logs_at_debug_and_any_other_type_warns.
- Each B test drives RuntimeError, TimeoutError, OSError (expected: same fallback, one DEBUG record) and a KeyError subclass (same fallback, one WARNING record).

Runs (slot 9):
- Red before production code: RESULT tests 63 skipped 0 failing_ids 23 PAR_EXIT=1 (20261125T204139-t3-red; all failures "no logs triggered" or "model_phase has no attribute log_fallback").
- Green: RESULT tests 112 skipped 0 failing_ids 0 PAR_EXIT=0 (20261125T204435-t3-green, with engine surface/sources/size/layout locks).
- Mutation 1 (all new A/B log lines deleted): RESULT tests 63 skipped 0 failing_ids 20 PAR_EXIT=1 (20261125T204504-t3-mut-logs); every A subtest (7 class steps + runtime_recovery) and every B module test failed. Restored from a scratch tar copy.
- Mutation 2 (log_fallback never treats a type as outage): failing_ids 8 (20261125T204526-t3-mut-outage): every expected-type case failed.
- Mutation 3 (log_fallback treats every type as outage): failing_ids 6 (20261125T204541-t3-mut-bug): every unexpected-type case failed.
- After mutations: model_phase.py restored, grep confirms the isinstance line is back.

Fix found by the targeted run: test_engine_routing R6 forbids `__name__` in game_parts (functions run under the game namespace); game_parts loggers now use literal names "game_parts.dialogue" / "game_parts.intent" / "game_parts.turn_front" (the file's existing style, see dialogue._repair_npc_speech).

## Step 5: targeted set
Module set (286 modules): global set + every api/tests module that names a touched module or class (class_progression, barbarian, paladin, sorcerer, Wizard, Cleric, runtime_recovery, arrival_narration, incidents, grounded_action, identity_suggestion, model_phase, turn_front, game_parts intent/dialogue, front_proposal, parse_player_intent) + money_tests.txt + test_persistence_idempotency, test_campaign_api, test_engine_parts_pilot, test_local_gemma_fast, test_model_chain, test_engine_sensitivity + path-text readers (test_coin_writers, test_d053_product_no_test_imports, test_narration_source_record, test_talk_mode_writers, test_engine_surface).
- First off run (t3off, 278 modules because the money list was mis-joined): tests 6021 skipped 38 failing_ids 1 PAR_EXIT=1 — the R6 failure above; fixed.
- Off (t3off2, 10 shards): tests 5486 skipped 38 failing_ids 0 PAR_EXIT=3 — shard 8 hit the 540 s cap (NO_SUMMARY), no failure.
- Off, shard 8's 28 modules again in 6 shards (t3off3): tests 826 skipped 0 failing_ids 0 PAR_EXIT=0.
- Off total: tests 6312 skipped 38 failing_ids 0.

## docs/agents/implementer-preamble.md checklist
- graphify: graphify-out/ does not exist in this worktree; grep used (allowed by the brief). `graphify update .` not run for the same reason.
- (a) All callers: the changed catches keep the same type (broad) and the same body; only a log call was added, so every caller (turn, combat, level-up HTTP, front step) gets identical results. The B helper is called from each of the five call sites.
- (b) Old saves: not applicable — no save field or format touched.
- (c) Undo/reload: unchanged — A sites still restore the same snapshot and reject/raise the same way (tests assert the restore and the reject).
- (d) Fixed town: the one new test that builds a campaign session (intent reading) uses fixed_town(self, 20261351); the others use fakes or existing fixtures (graveyard, incident _world).
- (e) Player text: unchanged; logs carry only error type names and fixed sentences, never player or model text.
- (f) Red first: shown (t3-red, s0-red); no test loosened; the identity test was rewritten to the new rule (old names gone) as the plan asks.
- (g) Money/inventory: no economic path changed; money_tests.txt run in both flags.
- (h) Reuse: reused town_knowledge's pattern (module logger + exception) and the existing `model_phase` module for the shared B helper; one new function (log_fallback) because five B sites need the same outage-vs-bug split; stdlib logging only.
- (i) Engine file: game.py not changed (parked, at its 1164 lock); game_parts changes add no function; engine size/layout/surface/sources/routing/patch-census/sensitivity locks in the set.
- Fon (flag on, api.tests.gate_boot first; same 286 modules in 18 sequential `slot.sh test` runs: test_campaign_api alone, test_persistence_idempotency alone, 16 round-robin chunks t3fc0..t3fc15): every run exit 0; total tests 6312 skipped 36 failing_ids 0 PAR_EXIT=0. (`par` cannot put gate_boot first, so fon ran through `test`.)
- test_contract_parity alone, cap 900 s: off RESULT tests 114 skipped 0 failing_ids 0 PAR_EXIT=0 (20261125T214922-t3cp-off); fon RESULT tests 114 skipped 0 failing_ids 0 PAR_EXIT=0 (20261125T215708-t3cp-fon).
- Quality gate before each commit (Windows python, pinned ruff 0.17.5 / vulture 2.14, base `main`): ruff=0 ruffshrink=0 names=0 size=0 vulture=0.

## Commits
- 8974dd31 step 0 (shims, identity test, D-583)
- 2142057d classes A/B/C logging, tests, D-584
- Ruling: one commit for A, B and C — grounded_action.py and game_parts/intent.py hold both B and C sites, so a split commit would need partial hunks — if wrong, the reviewer reads one larger diff.

## RESULT
- failing_ids 0 in both flags; no class A or B site swallows silently except the two parked B/C sites in ask_dungeon_master (D-584, size lock); every changed C site logs with a reason comment; census complete (126 sites).
- Park: D-584 (owner Kadir, trigger: ask_dungeon_master split).
- Not run: browser tests, full suite (not in scope); CI not run (no push).
