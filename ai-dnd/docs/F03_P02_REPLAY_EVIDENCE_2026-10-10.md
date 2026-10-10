# F03-P02 Replay Evidence — 2026-10-10

**Verdict: SCOPED, not a full F03-AC-002 PASS.**

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

## Browser action replay

Machine-readable browser evidence: `.local/evidence/F03/20261010T173851Z/P02-browser-replay/P02-browser-replay.json`

Screenshot: `.local/evidence/F03/20261010T173851Z/P02-browser-replay/browser-1366x768.png`

An isolated Uvicorn process used a fresh `/tmp` SQLite database set through
`AI_DND_CAMPAIGN_DB` before `api.main` import. A separate Vite process proxied to
that API; Chromium 152 used a fresh temporary profile at 1366×768. The player
created one disposable random character through the real creation UI and opened
the resulting adventure screen. The Python model interface was disabled with a
fail-closed guard; no Qwen/model call was made.

The browser sent `/explore look` with a UUIDv4 `action_id` through the temporary
Vite `/api` proxy. This is the Python-owned native exploration resolver, not a
mocked turn result. First request returned HTTP 200. Reusing the identical
payload and ID returned HTTP 200 with an exactly equal response. Reusing the ID
with `/explore begin` returned HTTP 409 `action_id_conflict`. Visible HP (11),
XP (0), inventory, location, combat projection, and quest projection were
unchanged by the replay and conflict.

SQLite was read directly from the temporary store only: history/receipt/combat
rows were `0/0/0` before the first action, `1/1/0` after it, and remained
`1/1/0` after identical replay and changed-payload rejection. The persisted
campaign payload hash changed on the first accepted action, then stayed
unchanged across replay and conflict. The screenshot shows the actual adventure
UI. The evidence records the sanitized request path, method, and body field
names; the CDP request ID itself was not retained.

An earlier attempt to use the phrase-level “end conversation” command returned
HTTP 503 `ollama_unavailable` because that path requires an authenticated model
adapter. It made no turn receipt. The final test used the available native
Python exploration command with the model guard in place.

Harness retries also created two additional UI campaigns in separate temporary
stores: one stopped before the action when the SQLite snapshot helper failed,
and the other stopped at the 503 above. Across retries, three disposable
campaigns were created; only the recorded passing run committed a turn receipt.
All temporary stores and browser profiles were removed.

## Limits and gates

- Browser evidence now covers one non-combat action, identical-payload replay,
  and changed-payload conflict. It does not test UI double-click timing or a
  delayed browser retry.
- This packet did not exercise combat, so it cannot certify no second dice roll,
  damage, or reward. F03-AC-002 is still not fully PASS.
- F03 remains **OPEN**. F03-P01 remains **BLOCKED**; this does not open F10-BASE.
- Only this evidence report was updated. No source code, save schema, migration,
  managed workflow, live service, or owner database was changed or restarted.

## Commands

```text
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_explicit_shop_creation.ShopTransactionTests.test_creation_replay_duplicate_resume_and_session_isolation
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_turn_action_replays_after_resume_and_rejects_reused_payload
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_first_merchant_search_same_id_race_rolls_back_and_replays_winner
cd ai-dnd && timeout 35s python -m unittest -v api.tests.test_campaign_api.CampaignApiTests.test_first_merchant_search_same_id_changed_payload_race_rejects_loser
```
