# Offline dialogue and receipt validation

This evidence contains synthetic test results only; no live model call or personal data was used.

## Source

- Task branch: `fix/npc-default-dialogue-path-20261020`
- Tested code commit: `d3d66f551448b549f9834c373b9638b832b7f504`
- PR22 base: `edb3389301cd3017c1c3dd11c3299679729d65ab`
- Older call-phase comparison base: `da2b4cf1ee7d670de7e751bd96c6f69383270ca3`

## Model-call phase comparison

Instrumented `game.ollama.chat` with a fake provider on the older base and candidate `cc96c13`. Both executed the same bounded phases:

| Source | Call 1 | Call 2 | Telemetry |
| --- | --- | --- | --- |
| `da2b4cf1ee7d670de7e751bd96c6f69383270ca3` | intent-only schema | narrator-only schema | 1 intent + 1 narration = 2 |
| `cc96c13` | intent-only schema | narrator-only schema | 1 intent + 1 narration = 2 |

The F04 helper had returned narrator JSON for every schema and stopped at `call_count == 1`, before reaching its safety assertions. The helper now returns a valid intent-phase packet and a separate narrator packet, asserts the exact phase order and the bounded two-call total, and retains all seven prior safety assertions unchanged. The F04 module passed on both the older base and candidate code.

## Backend selectors

The following final-source selection ran on `d3d66f551448b549f9834c373b9638b832b7f504`:

```text
api.tests.test_f04_greeting_agency_quality
api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_default_npc_reply_uses_direct_speaker_prompt_over_http
api.tests.test_default_npc_targeting.DefaultNpcTargetingTests.test_failed_investigation_http_keeps_result_and_rejects_player_agency_claims
api.tests.test_campaign_api.CampaignApiTests.test_npc_conversation_save_failure_rolls_back_and_receipt_replay_skips_model
api.tests.test_campaign_api.CampaignApiTests.test_turn_action_replays_after_resume_and_rejects_reused_payload
api.tests.test_campaign_api.CampaignApiTests.test_journal_survives_explicit_save_and_a_new_session_manager
api.tests.test_campaign_api.CampaignApiTests.test_death_checkpoint_is_json_safe_and_external_restore_is_atomic
api.tests.test_campaign_ownership.CampaignOwnershipTests.test_two_players_cannot_read_or_write_each_other
```

Result: **14 tests passed**.

The failed-Investigation fixture asserts DC `15`, raw/selected roll `1`, and `failure` in the HTTP response. It also checks that the newly committed procedural-entity references exactly equal the difference between the pre-turn and final world-state entity sets, and that the same additions are persisted.

The save-failure rollback selector now additionally compares the pre/post lore-authority receipt and persisted campaign payload. It also retains checks for serialized game state, RNG, narrative memory, and absence of a turn-action receipt after the failed save; retry succeeds and replay does not spend another model call.

## Frontend controls

The branch artifact tree `artifacts/ai-dnd-experience` is unchanged between `cc96c13` and `d3d66f5`. Controls ran against the artifact extracted from the final source commit:

- Frontend tests: **152 total, 151 passed, 0 failed, 1 skipped**.
- `pnpm run typecheck`: passed.
- `PORT=5173 BASE_PATH=/ai-dnd-experience pnpm run build`: passed.
- Build emitted warnings for the tooltip sourcemap and a minified chunk over 500 kB.

## Scope

No CI result was queried or run. No live model, PR metadata update, merge, or deployment was performed. This report does not claim P6 or a quality PASS.
