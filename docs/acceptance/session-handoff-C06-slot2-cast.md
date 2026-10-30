# C06 selected castability dependency: Magic Missile slot 2

2026-10-28. Bounded implementation independently statically accepted; combined regression still running at this checkpoint. Full C05/C06/C19 and release acceptance remain OPEN.

Actual earned Sorcerer3 can explicitly cast single-target Magic Missile from slot2: four darts, one slot2 debit, no slot1 fallback. Omission remains slot1. Unsupported other upcasts, invalid types and unearned/empty pools reject without resource/RNG changes. Existing action/mitigation/turn limits, request hashing, receipt, replay, rollback and persistence owners remain authoritative.

Existing canonical and legacy turn request schemas expose optional nullable strict integer slot_level1..9. Runtime rejects nonmagic selection; that cross-field rule is not automatically exported by OpenAPI/Zod. Orval generated the client/Zod changes, and typecheck:libs passed. No new endpoint or UI slot selector. A typed request field is not a completed browser choice flow.

Evidence so far: c06-slot2-red10methods/11assertionfailures/0errors; c06-slot2-focused108PASS; additional11methodrunPASS (overlap, not additive). Four executable generated-validator tests failed against stale artifacts and passed after actual generation. Actual ASGI+syntheticSQLite replay/reopen and changed-slot sameUUID conflict passed. The save failure is a mocked post-cast CampaignStorageError: callback verifies pool debit/HP change, exactly one save call, then failure; rollback/retry/replay verified. It is not a real SQL insertion failure claim.

Expanded190test run exposed a new test fixture missing initial scene (fixed through commit_location_change) and two old concurrency expectations permitting consecutive Long Rests. The latter now first asserts 409 and unchanged state/rows/receipt, advances16h through the real clock owner, saves and resends the sameUUID, retaining secondcommit/replay assertions. Three corrected rest methods PASS. No rest policy weakened.

Frontend default package test initially161/130pass/30fail/1skip because imported snapshot omitted three portrait assets. Original user-supplied assets restored with exact manifest SHA256/size; rerun161/160pass/0fail/1skip. This is Node/harness coverage, not real browser/Clerk. Provenance: ai-dnd-takeover-work/ui-original-assets-restored-20261028.json. Generated-validator4tests are separate.

Source facts from official D&D Beyond2024BasicRules URLs in decisions/C05-magic-missile-slot2-plan.md. Not PHB page-scan acceptance or redistribution permission. Original per-dart policy retained, no multi-target/Shield adjudication added.

Downgrade requires matching prechange code/client/schema and prechange save snapshots; olderMAX2 backend rejects new level3 saves/slot selection. Changes remain uncommitted, no push/merge/deploy. Root snapshot base is synthetic import1616c7f, not pushable upstream history.

## Final checkpoint 18:22 UTC
Final guarded fast regression:921executions/905uniquePASS, exit0. Full persistence_idempotency module split into two disjoint41-method runs:82uniquePASS, exit0 in each. New source/record hashes validated with existing B02 schema under evidence/c06-slot2-cast-20261028. Earlier combined run ended without a terminal record after process-handle loss; retained INCOMPLETE and never counted as PASS. Cause unverified, retry results above are complete.

Default frontend package161tests160PASS/0FAIL/1SKIP; generated validator4PASS; full workspace typecheckPASS; repeated Orval generation preserves all three generated artifact SHA256s. Browser/realClerk/fullAPI discovery still not run. Historical NPC and globalapp contract-parity issues not declared fixed. Scoped leaf is ACCEPTED; fullK07/C05/C06/C19 remainsOPEN.
