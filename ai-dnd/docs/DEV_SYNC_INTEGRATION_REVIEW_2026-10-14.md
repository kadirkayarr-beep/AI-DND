# DEV synchronization integration review — 2026-10-14

## Scope and provenance

- Common development base: `48ccbaaf6b4f3348cef15ae0a6faf945d1cf9e53`.
- Replit clean source snapshot: `52b8e2a6b2f640b746d86584d59f929884c43680`; exactly one parent, the common base.
- Cursor source reviewed: `3b7a440a24fff1b23652158d819b8edaea4ab405`. Its branch was not merged wholesale.
- Integration was prepared in a separate Windows clone; the original dirty development folder was not modified.
- The additional Replit checkpoint history containing the exposed screenshot is not an ancestor of this candidate. Only the clean snapshot and this review commit are used.

## PC work preservation

- Verified all 296 archived PC files still match the original source bytes before and after integration.
- 49 substantive Python test-file changes integrated; 41 non-overlapping, 4 clean three-way merges, 4 manually reconciled overlap files.
- The other 118 stat-dirty files are byte-identical to base, and 126 differ only in line endings or terminal newlines; they remain preserved in the external backup rather than producing source churn.
- All three untracked PC files are preserved as inert text under `integration/preserved-20261014`, not activated as an ownership-changing tool.

## Conflict decisions

- `test_api.py`: preserve Replit's call-budget temporary-store setup and PC's explicit synthetic authenticator for normal API test cases.
- `test_campaign_api.py`: retain replay/autosave assertions and use an explicit, owner-bound temporary store plus matching synthetic authenticator for the shared test fixture.
- `test_campaign_persistence.py`: retain one Replit synthetic test principal consistently across all PC-added reopened-store bindings; no production identity change.
- `test_persistence_idempotency.py`: preserve Replit's explicit fixture and every receipt/replay guard; incorporate PC's matching identity on other reopened temporary stores.
- No Replit method definitions or PC-added definitions were dropped by these merges; no duplicate top-level/class definitions were introduced.

## Cursor accounting

- `api/serializers.py`: Cursor's entire resulting file is already identical to the Replit snapshot. Both validated spell projection helpers are AST-identical.
- `api/tests/test_spells_v1.py`: the legacy v3 projection check already exists alongside current fresh-v4 coverage; keep the current format-aware tests rather than old unconditional v3 assumptions.
- `api/session_manager.py`: retain current preserved-format and ownership behavior, not the old debug-write block.
- `game.py`: current code already has combat/quest XP handling and pending level-up publication. Do not reintroduce duplicate `_publish_level_up`, unconditional debug output, v1–v4 XP resets, or unapproved automatic save promotion. The source proposal is preserved inert for later review.
- `debug-c188f4.log`: not added to this lineage; original branch and external backup remain intact.

## Executed validation

- Python 3.14.2: **63 selected tests ran, 63 passed, 0 errors, 0 skipped, native process exit 0**.
- Selected tests covered synthetic principal/ownership isolation, diagnostics guards, save/restart/RNG, API replay and rollback, narration memory, model timeout/call ceiling, spell resolution, legacy-v5 round trips, and starting-equipment draw.
- The first run had one ERROR in the PC spell test: a direct SessionManager.get call lacked the same synthetic principal supplied through the HTTP fixture. A one-line test-only explicit principal fixed it; no production code or assertion was weakened. First error output remains in the external evidence directory.
- A later PowerShell wrapper status was ambiguous despite a successful unittest result; final verification captured subprocess.returncode directly and returned 0.
- Runner blocked external network, writes outside its dedicated test output directory, and SQLite connections outside fresh disposable test directories. No blocked side-effect attempt was recorded.
- `api.tests.test_http_auth_gate`, real Clerk, live Qwen, production databases and browser acceptance were NOT run.
- Existing temporary-fixture migration test edits are retained as source, but no existing-save migration was performed.
- Frontend source remains byte-identical to the reviewed Replit snapshot. No fresh frontend build/typecheck/browser run is claimed here: the new Windows clone has no installed dependencies, and the workspace overrides explicitly exclude Windows native Vite dependencies. No dependency or lockfile rewrite was made.

## Distribution boundary

This is a bounded source-integration checkpoint, not full F03/LR-00 or production acceptance. Updating GitHub does not automatically update the original dirty PC folder or the running Replit checkout. Those require a separate preserved-state synchronization step. Never reset or overwrite those worktrees to make branch labels appear synchronized.

## Explicit test selectors

- `api.tests.test_auth_diagnostics.AuthDiagnosticsTests`
- `api.tests.test_principal_auth.PrincipalAuthTests`
- `api.tests.test_campaign_ownership.CampaignOwnershipTests`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_campaign_save_and_runtime_rng_survive_manager_restart`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_narrative_memory_survives_campaign_resume_and_manager_restart`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_campaign_ids_are_opaque_and_campaigns_are_isolated`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_invalid_new_state_does_not_replace_the_last_good_save`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_resume_updates_last_played_without_rewriting_save_timestamp`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_completed_combat_result_survives_resume`
- `api.tests.test_campaign_persistence.CampaignPersistenceTests.test_combat_history_is_bounded_isolated_and_not_duplicated_by_save`
- `api.tests.test_campaign_api.CampaignApiTests.test_turn_action_replays_after_resume_and_rejects_reused_payload`
- `api.tests.test_campaign_api.CampaignApiTests.test_failed_autosave_rolls_back_turn_and_keeps_last_good_save`
- `api.tests.test_persistence_idempotency.PersistenceIdempotencyTests.test_unchanged_top_level_target_replays_saved_receipt_after_resume`
- `api.tests.test_persistence_idempotency.PersistenceIdempotencyTests.test_late_receipt_sql_failure_rolls_back_all_writes_then_retry_commits_once`
- `api.tests.test_persistence_idempotency.PersistenceIdempotencyTests.test_independently_loaded_stale_save_cannot_overwrite_newer_truth`
- `api.tests.test_api.ApiContractTests.test_model_call_limit_enforced_by_captured_calls_ignoring_telemetry_claim`
- `api.tests.test_f04_transient_narration_memory.TransientNarrationMemoryAcceptanceTests`
- `api.tests.test_stability_repairs.TurnIntegrityTests.test_model_outage_keeps_deterministic_dialogue_mechanics_safe`
- `api.tests.test_stability_repairs.TurnIntegrityTests.test_model_timeout_on_unknown_input_does_not_apply_mechanics`
- `api.tests.test_stability_repairs.TurnIntegrityTests.test_narration_timeout_preserves_python_skill_check_result`
- `api.tests.test_spell_scope.SpellEngineTests`
- `api.tests.test_spell_scope.SpellApiTests`
- `api.tests.test_spells_v1.SpellApiTests`
- `api.tests.test_legacy_v5_save_compat.HistoricalV5SaveCompatibilityTests`
- `api.tests.test_weapon_attack.WeaponTests.test_new_fighter_package_c_greatsword_identity_and_draw`
- `api.tests.test_weapon_attack.WeaponApiTests.test_receipt_replay_preserves_ammo_damage_effects_rng_after_resume`
- `test_sessions.SessionTests.test_short_rest_does_not_restore_expended_sorcerer_spell_slot`
- `test_sessions.SessionTests.test_overlapping_interrupted_long_rest_keeps_healing_and_spells_session_owned`
