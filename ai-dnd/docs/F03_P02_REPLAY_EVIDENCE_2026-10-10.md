# F03-P02 Replay Evidence — 2026-10-10

**Verdict: SCOPED (API-only), not a full F03-AC-002 PASS.**

Machine-readable evidence: `.local/evidence/F03/20261010T171045Z/P02/evidence.json`

## Isolated probe

All requests ran through in-process FastAPI `ASGITransport` against a temporary SQLite store created by the existing `ShopTransactionTests` fixture. The fixture used the Python game engine and a mocked Ollama client; there were no external model calls and no owner campaign data. Temporary databases were removed during teardown.

One redacted `action_id` was submitted to campaign A, replayed unchanged, then reused with changed content. The same ID was also submitted once to campaign B to verify campaign-scoped identity. Raw IDs are not retained; a short SHA-256 prefix in the JSON binds this probe without exposing the ID. The existing race tests generated their own IDs and did not emit or retain them.

| Campaign | Before: history / combat rows / receipts | After relevant requests |
|---|---:|---:|
| A | `0 / 0 / 0` | After first request and identical replay: `1 / 0 / 1`; after changed-payload rejection: unchanged at `1 / 0 / 1` |
| B | `0 / 0 / 0` | Same action ID accepted independently: `1 / 0 / 1` |

Observed responses: first POST `200`; identical replay `200` with the exact same response; changed payload `409 action_id_conflict`; the same ID in the other campaign `200`. This non-combat merchant-discovery action did not create combat-history rows. Dice, damage, and rewards were not exercised and are not claimed as verified.

## Bounded test runs

Each test ran separately with a 35-second process timeout. All returned exit code `0`; none timed out.

| Test | Result | Time |
|---|---|---:|
| `ShopTransactionTests.test_creation_replay_duplicate_resume_and_session_isolation` | PASS | 1.463 s |
| `CampaignApiTests.test_turn_action_replays_after_resume_and_rejects_reused_payload` | PASS | 0.472 s |
| `CampaignApiTests.test_first_merchant_search_same_id_race_rolls_back_and_replays_winner` | PASS | 0.972 s |
| `CampaignApiTests.test_first_merchant_search_same_id_changed_payload_race_rejects_loser` | PASS | 1.072 s |

Per-run stdout/stderr and exit records are retained beside the JSON evidence. The concurrent race tests exercised a same-ID winner/loser path; their logged `CampaignStaleError` is the injected losing autosave path and both tests completed `OK`.

## Limits and gates

- No browser interaction/evidence was obtained. The Bible’s browser-evidence requirement therefore remains unmet; F03-AC-002 is API-only and not fully PASS.
- This packet did not exercise combat, so it cannot certify no second dice roll, damage, or reward.
- F03 remains **OPEN**. F03-P01 remains **BLOCKED**; this does not open F10-BASE.
- No source code, save schema, migration, workflow, or live service was changed or restarted.

## Commands

```text
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_explicit_shop_creation.ShopTransactionTests.test_creation_replay_duplicate_resume_and_session_isolation
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_turn_action_replays_after_resume_and_rejects_reused_payload
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_first_merchant_search_same_id_race_rolls_back_and_replays_winner
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_first_merchant_search_same_id_changed_payload_race_rejects_loser
```
