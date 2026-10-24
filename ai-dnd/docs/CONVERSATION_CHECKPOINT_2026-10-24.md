# Conversation development checkpoint — 2026-10-24

Status: DEVELOPMENT CHECKPOINT, NOT RELEASE / FULL ACCEPTANCE.

Base: e03aa0c767e0bc4a28233b665532bd912be32dbc on dev/ai-dnd.
This integrates the approved isolated roadmap candidate and its final conversation fixes. It does not merge into main, deploy, change authentication/access settings, or include personal saves, dependency caches or large evidence archives.

## Scope

Nine existing source/test files are changed and nineteen regression/diagnostic test files are added. The changes cover paired NPC conversation history, structured ordinary speech, grounded Turkish query/action boundaries, visible scene/entity projection, bound speaker labels, public door focus, repair/repetition handling, and door/tool targeting. Final fixes scope mundane personal_detail disclosure to the visible selected NPC, separate weather questions from NPC-day questions, and avoid duplicate normal-speech safety diagnostics. A test-provider binding fix and explicit legacy-test contract alignment are included; world/inventory/privacy assertions were retained.

## Verification and limits

- Daily deterministic gates: 33/33 passed.
- Focused narrative + HTTP contract run: 66/66 passed; source-function checks 42/42.
- UI unit/contract tests: 157 passed, 1 existing skip, 0 failures.
- TS library build, Experience UI typecheck and production build: exit 0.
- Final broad API run: 2,645 executions / 2,588 unique IDs; 77 failure and 49 error occurrences, across 94 failed parent IDs; 0 skip/xfail. This is NOT an all-green repository.
- The paired comparison was against the uploaded isolated candidate (game.py 6d9500b93aef29531773d073c7048e72c776cf471b217b11fc59b68ffae7ba90), NOT a fresh run of GitHub base e03aa0c. No new failed ID was observed against that candidate. Do not infer regression-free relative to e03aa0c from that statement.
- Python 3.13.5 with 22 locked distribution versions matched. API tests used synthetic providers and temporary data; internet sockets were blocked for the test process tree. Real Qwen and current browser/player acceptance are not established by this checkpoint.
- Earlier paired broad runs used a restricted PATH; 12 tooling failures disappeared after exposing already installed Node/pnpm. Separate controls passed 28/28 on both sources, and the final broad run used the corrected PATH. This improvement is not counted as a product-code fix.
- Raw per-ID results, logs and rollback artifacts were delivered separately to the owner; intentionally not added wholesale to this repository.

The tested Windows-form game.py SHA-256 was aa38a53d8c95a91a898e2786ad574f9d5a83b80e2a9217bc3bcb3bece6802869. Git publication normalizes CRLF to LF only; Python AST equivalence was checked. The published Git blob SHA is recorded below. This is a content-preserving Git line-ending conversion, not a different gameplay patch.

## Remaining broad-suite failed parent IDs

These 94 IDs are not proof of 94 distinct player-visible defects. Product behavior, outdated contracts and environment/fixture issues still require individual triage.

- `api.tests.test_ai_freedom_resolution_boundary.EngineResolutionBoundaryTests.test_described_person_dialogue_counts_intent_and_narration_calls`
- `api.tests.test_api.ApiContractTests.test_browser_proxy_routes_reach_the_same_python_api`
- `api.tests.test_api.ApiContractTests.test_client_cannot_submit_authoritative_state`
- `api.tests.test_api.ApiContractTests.test_completed_narration_call_is_not_retried`
- `api.tests.test_api.ApiContractTests.test_different_sessions_can_process_turns_independently`
- `api.tests.test_api.ApiContractTests.test_engine_exception_becomes_safe_error_and_rolls_back`
- `api.tests.test_api.ApiContractTests.test_missing_required_model_returns_safe_503`
- `api.tests.test_api.ApiContractTests.test_model_call_error_returns_safe_503_and_rolls_back`
- `api.tests.test_api.ApiContractTests.test_preflight_is_not_counted_as_generation`
- `api.tests.test_api.ApiContractTests.test_provider_timeout_is_one_failure_and_rolls_back`
- `api.tests.test_api.ApiContractTests.test_real_engine_evidence_with_telemetry_succeeds_without_500`
- `api.tests.test_api.ApiContractTests.test_secret_values_are_redacted_from_responses`
- `api.tests.test_api.ApiContractTests.test_session_state_is_isolated`
- `api.tests.test_api.ApiContractTests.test_species_action_returns_authoritative_result_and_state`
- `api.tests.test_api.ApiContractTests.test_state_endpoint_is_a_canonical_public_projection`
- `api.tests.test_api.ApiContractTests.test_turn_delegates_to_existing_game_session_pipeline`
- `api.tests.test_api.ApiContractTests.test_turn_is_rolled_back_if_model_call_limit_is_exceeded`
- `api.tests.test_api.ApiContractTests.test_turns_in_one_session_are_serialized`
- `api.tests.test_campaign_api.CampaignApiTests.test_changed_door_invalidates_focus_and_legacy_focus_defaults`
- `api.tests.test_campaign_api.CampaignApiTests.test_entry_reference_rolls_back_when_blocked_entry_save_fails`
- `api.tests.test_campaign_api.CampaignApiTests.test_focus_does_not_resurrect_after_topic_or_speaker_change`
- `api.tests.test_campaign_api.CampaignApiTests.test_free_http_profile_purpose_is_owned_by_personal_topic`
- `api.tests.test_campaign_api.CampaignApiTests.test_free_npc_profile_statement_uses_shared_resolution_without_forced_target`
- `api.tests.test_campaign_api.CampaignApiTests.test_model_owned_personal_purpose_phrasings_do_not_need_lexical_gate`
- `api.tests.test_campaign_api.CampaignApiTests.test_named_non_tavern_building_does_not_inherit_tavern_focus_over_http`
- `api.tests.test_campaign_api.CampaignApiTests.test_npc_occupation_and_origin_share_validated_profile_resolution`
- `api.tests.test_campaign_api.CampaignApiTests.test_profile_why_does_not_bypass_unverified_lore_safety`
- `api.tests.test_campaign_api.CampaignApiTests.test_reopened_personal_questions_stay_bound_to_saved_npcs`
- `api.tests.test_campaign_api.CampaignApiTests.test_targetless_entry_reuses_failed_door_target_through_http`
- `api.tests.test_campaign_api.CampaignApiTests.test_unpunctuated_locked_followup_reaches_same_npc_door_context`
- `api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_default_new_place_is_campaign_scoped_replayable_and_cold_loadable`
- `api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_default_npc_place_statement_keeps_attribution_after_resume_and_respects_locked_target`
- `api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_default_npc_reply_uses_direct_speaker_prompt_over_http`
- `api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_local_place_recommendation_reaches_focused_npc_in_default_mode`
- `api.tests.test_equipment_native.NativeEquipmentHttpTests.test_real_conversation_still_requires_conversation_proposal`
- `api.tests.test_f03_fault_chains.F03FaultChains.test_healthy_precommit_api_outage_separate_from_restore_failure`
- `api.tests.test_f03_fault_chains.F03FaultChains.test_model_failure_full_invariance`
- `api.tests.test_f03_fault_chains.F03FaultChains.test_restore_failure_real_restart_and_precommit_outage`
- `api.tests.test_f03_fault_chains.F03FaultChains.test_save_rollback_component_recovery_retry_once`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_explicit_player_greeting_action_is_not_erased`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_greeting_does_not_ask_npc_to_revisit_old_claim`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_greeting_meta_editorial_aside_is_not_accepted`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_lore_rejection_preserves_greeting_in_final_player_turn`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_recorded_live_greeting_cannot_invent_player_reply_or_meta_summary`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_recorded_live_lore_prose_rejection_keeps_final_greeting`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_repair_rejects_a_second_invented_claim_in_the_remainder`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_repaired_npc_answer_keeps_safe_text_after_invented_feeling`
- `api.tests.test_f04_greeting_agency_quality.F04GreetingAndAgencyTests.test_short_genuine_npc_greeting_remains_model_accepted`
- `api.tests.test_f04_n08_empty_narration_source.EmptyNarrationSourceRegression.test_empty_model_narration_is_not_accepted_as_qwen`
- `api.tests.test_f04_n08_empty_narration_source.EmptyNarrationSourceRegression.test_valid_model_narration_remains_qwen_accepted`
- `api.tests.test_f04_n08_live_prose_guard.N08UnverifiedProseRegression.test_elara_is_not_promoted_to_active_npc_when_neris_owns_scene`
- `api.tests.test_f04_n08_live_prose_guard.N08UnverifiedProseRegression.test_nonempty_model_echo_of_unverified_history_is_fallback`
- `api.tests.test_http_acceptance_evidence.HttpEvidenceTests.test_complete_scenario_success_preserves_acceptance_details`
- `api.tests.test_http_two_player_isolation.TwoPlayerIsolationTests.test_a_saved_but_inactive_campaign_is_409_for_its_owner_and_404_for_everyone_else`
- `api.tests.test_http_two_player_isolation.TwoPlayerIsolationTests.test_a_signed_in_stranger_gets_the_same_answer_as_for_a_missing_record`
- `api.tests.test_incident_gate_a.SqliteClaimTests.test_v5_table_and_concurrent_claim_has_one_winner`
- `api.tests.test_local_person_persistence.LocalPersonPersistenceTests.test_new_local_person_becomes_campaign_content_through_http`
- `api.tests.test_lr00_process_restart.LR00ProcessRestartTests.test_spent_action_survives_actual_process_restart_and_resume`
- `api.tests.test_narration_evidence_acceptance.NarrationEvidenceTests.test_empty_claims_drop_loaded_fact_at_current_guard`
- `api.tests.test_narration_evidence_acceptance.NarrationEvidenceTests.test_exact_evidence_rejects_private_nonfact_and_foreign_npc_rows`
- `api.tests.test_narration_evidence_acceptance.NarrationEvidenceTests.test_npc_bound_turn_does_not_borrow_narrator_evidence`
- `api.tests.test_narration_receipt_contract.ReceiptContractTests.test_typed_selected_lore_citation_conflict_is_diagnostic_not_receipt_authority`
- `api.tests.test_npc_dialogue_stage_a_diagnostic.StageADiagnosticTests.test_guard_scene_without_any_inn`
- `api.tests.test_npc_dialogue_stage_a_diagnostic.StageADiagnosticTests.test_partial_reply_probe_reports_completion_status`
- `api.tests.test_npc_dialogue_stage_a_diagnostic.StageADiagnosticTests.test_unsafe_model_outputs_are_still_blocked`
- `api.tests.test_npc_p2_continuity.NpcP2ContinuityTests.test_guard_exact_repeat_of_previous_speech_still_falls_back`
- `api.tests.test_npc_p2_continuity.NpcP2ContinuityTests.test_live_t5_repeated_speech_gets_in_character_line_not_robotic`
- `api.tests.test_npc_transcript_replay_baseline.ProposalSalvage.test_plain_speech_keeps_the_reply`
- `api.tests.test_phase7_package.Phase7PackageTests.test_prompt_omits_unknown_names_and_private_npc_fields`
- `api.tests.test_quest_outcome_identifier_limits.QuestOutcomeIdentifierApiTests.test_boundary_command_sources_expose_http_composite_id_overflow`
- `api.tests.test_quest_outcome_identifier_limits.QuestOutcomeIdentifierApiTests.test_command_projection_preserves_boundary_ids_and_null_objective`
- `api.tests.test_quest_outcome_identifier_limits.QuestOutcomeIdentifierApiTests.test_long_canonical_target_is_rejected_before_http_outcome_projection`
- `api.tests.test_quest_outcome_identifier_limits.QuestOutcomeIdentifierApiTests.test_turn_endpoint_preserves_boundary_quest_and_objective_ids`
- `api.tests.test_quest_outcomes.QuestOutcomeTests.test_v1_save_migrates_without_replacing_held_state_or_rng`
- `api.tests.test_skill_result_pipeline_regression.RejectedLoreSkillFallbackTests.test_real_final_turn_skill_success_and_failure_preserve_python_outcome`
- `api.tests.test_stability_repairs.ApiRecoveryTests.test_failed_restore_closes_the_session_and_skips_save`
- `api.tests.test_stability_repairs.CrossSessionTests.test_attack_lore_and_reload_do_not_cross_write`
- `api.tests.test_stability_repairs.NarrationAndCoreTests.test_location_cap_is_explicit`
- `api.tests.test_stability_repairs.NarrationAndCoreTests.test_repeated_attacks_do_not_drop_hp_below_zero`
- `api.tests.test_stability_repairs.NarrationAndCoreTests.test_second_sword_drop_does_not_duplicate`
- `api.tests.test_stability_repairs.NarrationAndCoreTests.test_texture_and_feature_names_are_not_people`
- `api.tests.test_stability_repairs.TurnIntegrityTests.test_malformed_intent_json_is_not_an_unknown_success`
- `api.tests.test_stability_repairs.TurnIntegrityTests.test_ruler_question_answers_from_lore_without_scene_writes`
- `api.tests.test_untrusted_player_input.UntrustedPlayerInputHttpTests.test_accepted_quote_and_visible_npc_reply_over_http`
- `api.tests.test_untrusted_player_input.UntrustedPlayerInputHttpTests.test_single_line_http_behaviour_is_unchanged`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_active_combat_rejects_speech_modes_without_effects`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_ask_dm_ignores_client_npc_target_before_engine_routing`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_conversation_projection_uses_identity_and_visibility_without_learning`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_mode_is_part_of_receipt_identity_and_replay_has_no_effects`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_omitted_mode_keeps_legacy_receipt_hash_and_null_replay`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_say_target_is_validated_by_python_and_returned_as_active_conversation`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_speech_modes_do_not_run_attack_prevalidation`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_structured_action_keeps_combat_owner_even_in_speech_mode`
- `api.tests.test_wave3_interaction_modes.Wave3InteractionModeApiTests.test_turn_request_accepts_only_supported_modes`

## Published file identity map

- `ai-dnd/api/tests/test_experimental_npc_dialogue.py`: Git blob `64c42ce5691b1508e54b4018cf5ac02d15845667`, LF SHA-256 `193a2a008b3df491c6596472f0482471e066852d812dac339b51ba62623fe6f0`.
- `ai-dnd/game.py`: Git blob `aabc6cf76f76d7c356c408128f58f8aae3e68eb4`, LF SHA-256 `d91750c152c1cd78c45bcb5f8b0c7053342a6a72b1a14740ccee2f99e86bfac0`.
- `ai-dnd/grounded_action.py`: Git blob `c8840f2d9969e7e8ab4cd456cb31707494f6e1ca`, LF SHA-256 `8335148bc28e15d1bd0fde682725cfd38f7af08eb3e7f35658a5fa07f4f2c2dd`.
- `ai-dnd/interaction_adventure.py`: Git blob `309d9b39013cab83139bf84e944b1b5b1aca48c2`, LF SHA-256 `c4bbfacc453d49d50c63c0e1df93a8c08f2bd68e9563d9cb24e30c7d66167ad2`.
- `ai-dnd/living_world.py`: Git blob `aa8d21cabecb33518608cfcef43a0fd38b6c2afd`, LF SHA-256 `a0d1bf82a31235cee4476ed8c5bf1f6c609cd7c7e633b9c9d6526d8ac6da0897`.
- `ai-dnd/local_dialogue.py`: Git blob `34d98a89cfc4f9a4b36d0fe89268708d99115da6`, LF SHA-256 `108e378e89b9d72c2299bb56a574f658a4f05e3fdb19c96a94d2eaf0bf15d1ae`.
- `ai-dnd/npc_speech_boundary.py`: Git blob `9bd447af0a29da99f293296f7760d57e52fb68c8`, LF SHA-256 `65918bab0bcc6094cbd7011483390b3119d7ba2035ea4422985f73347953af47`.
- `ai-dnd/test_narrative_rebalance.py`: Git blob `d81b8f8670ba1e24ad204531f989e3c1af23f2dd`, LF SHA-256 `bfd0af49efed9e3640cbfe569e5472727cdc8a7fe44a4ff18ccc4ee519e6b199`.
- `artifacts/ai-dnd-experience/tests/play-screen-ui-regression.test.mjs`: Git blob `d28911be11bd32f6da1ce2d067b6c2a93983fdef`, LF SHA-256 `e536cd9a888c93d729a7ad341a109f3a664a314e18b9362185fd87481cff6123`.
- `ai-dnd/api/tests/test_bound_speech_label.py`: Git blob `0c62957ed8d8593a2b1ea4973555a4be8884cb19`, LF SHA-256 `cfcf4d60fefede8cbaf2f810add9b6746034b2f76056d830af5d59fff7ef38b5`.
- `ai-dnd/api/tests/test_compound_smalltalk_acceptance.py`: Git blob `a96257c3312dbba0c694635114ef3d67654b1e4b`, LF SHA-256 `0dad4328c2d44d75f656fb00b7ab0a09a959ceb5b210a365fc7635f9b70560a3`.
- `ai-dnd/api/tests/test_default_focus_acceptance.py`: Git blob `6dcdcd17d715702ff04a320d040578cc2b330be6`, LF SHA-256 `7b2db7b780d4d94694c5365371e14f864ab86b441a2bd65649d5ef87fd5b81ce`.
- `ai-dnd/api/tests/test_door_tool_acceptance.py`: Git blob `e43f2dafcd77d06dd87ad886b037fee537ff2c93`, LF SHA-256 `2ee9d1cd2dff1d356654d9874fe28bba6809de2924bd9a9853250dfc264d0033`.
- `ai-dnd/api/tests/test_identity_entity_acceptance.py`: Git blob `2d7116ad9df1f87a5204a0d17cb941c14fba3255`, LF SHA-256 `68079ce0336fdfca3c3eb29786dca039c05d071d6f24f542ac2d20cd114664f7`.
- `ai-dnd/api/tests/test_job6_compound_trace.py`: Git blob `d01fd375d1c039720fdaf5fe0e5683d229777783`, LF SHA-256 `d47f5c461dbe70b799a0fce5ac3e576cf63d42921d9a8e37c75fbb9ac82767aa`.
- `ai-dnd/api/tests/test_job7_texture_diagnostic.py`: Git blob `107e34009214e8555698d98d79146b29561a3d35`, LF SHA-256 `a6903e80da31b87ef3b51f689bb23917f4122586808f9e759fa53a18517eb82f`.
- `ai-dnd/api/tests/test_meaning_boundary_acceptance.py`: Git blob `7b83e594094a4cee13d139cd9dc8528b425e1940`, LF SHA-256 `67538215804481d24e0c569b4a393be9c50794d474c93f547fe2a09051397ee6`.
- `ai-dnd/api/tests/test_narration_evidence_acceptance.py`: Git blob `d5bcb2e6537c62c2a37f8d40c672f6b376ca3bf9`, LF SHA-256 `13ba9b504a9b35c4812448c9586cfc401372716365fb3263becd04dfd936d88b`.
- `ai-dnd/api/tests/test_narration_prompt_contract.py`: Git blob `f8dee4fdd6a4c50fc1b6db59423663fe47c0023b`, LF SHA-256 `8ddb910aa64fffa03c5cddde70c392433801451cf78b4e7954da1b8b549944ef`.
- `ai-dnd/api/tests/test_narration_receipt_contract.py`: Git blob `d4fc1d92405e41ed2e5f43f9d58a871a57057a70`, LF SHA-256 `db55f931aaf110cc8650cf1d721fd943ab42f069f15c2d4af2f2c9eed4939396`.
- `ai-dnd/api/tests/test_npc_paired_history.py`: Git blob `dbb901c5a4cdad6d4732a538face4e23de83dc7b`, LF SHA-256 `c404239313f268e4d2c1ffb83f9ba7b12ccc89d6ad30e1cb43bb1a484c0d521b`.
- `ai-dnd/api/tests/test_public_door_focus.py`: Git blob `68050d1e589fe1b72f68cfe9d8368057cfe9d3ca`, LF SHA-256 `415436de48ad12434eb37a65d69d35ea15cf78658ba17c57fc6bec14d500bb90`.
- `ai-dnd/api/tests/test_query_request_acceptance.py`: Git blob `3c4817f201ff2b10712618daa6a73383b96b359f`, LF SHA-256 `cecea2f334baf3845e63b0edee39a5f8c0d8c09aeea91f1feb346628823e10fb`.
- `ai-dnd/api/tests/test_query_review_acceptance.py`: Git blob `8226c2917b7578047b6f6d74eb3365163192949a`, LF SHA-256 `74bcb9c52932b1c3d8ca07f138648da6e4235bf39b6967c96461928a28ce1ef3`.
- `ai-dnd/api/tests/test_repair_repetition_acceptance.py`: Git blob `2879d8283b19796a9e5eff6208bc3be5c6bab17d`, LF SHA-256 `56a1debfb419d46f6fe2d6215743b3edc323543944cac5644c2b28a10597a4d1`.
- `ai-dnd/api/tests/test_route_focus_regressions.py`: Git blob `582d1963948626d696eb084098676c9ff601682f`, LF SHA-256 `00fcd5aebdf4f72ee303e9025125eca222c79413817a5b595922344775f71ab2`.
- `ai-dnd/api/tests/test_stage_profile_contract.py`: Git blob `6a6bc7d65d9ea8a5603103575e1aead81ce847cc`, LF SHA-256 `fa1e2b1849df01acf8f303f664ca4164703a5ec8edd63307f74c609bd0ad4c64`.
- `ai-dnd/api/tests/test_personal_weather_scope.py`: Git blob `4832644b2ccefb45778ab43690f24e369c12d87a`, LF SHA-256 `ab8d445867e59c8dcfcd46e36c821caa52117e92e3066a128f6df27a08e56dfc`.
