# C06 starting XP correction — 2026-10-29

## Accepted bounded correction
New Sorcerer characters created at levels 1/2/3 now start with XP 0/300/900. The canonical owner remains xp.LEVEL_THRESHOLDS. Initialization happens only after all level choices succeed inside create_at_level's existing rollback boundary. No earned reward, receipt, HP payment, ordinary apply behavior or save migration changed.

Verified external source: phb-source-recovered-20261029/c06-release_v1/advancement.md, indexed checksum verified. Higher-level creation minimum XP at PDF42/printed43, threshold table PDF40/printed41. Raw source stays outside repository.

## Tests and review
Actual RED: 4 methods, 6 assertion failures, zero errors. Corrected source then 49 scoped tests PASS and 42 related tests PASS. These two runs have 91 distinct class+method IDs, verified from raw logs. No full suite or live Windows/browser run claimed. Independent static review approved exact four-line product insertion and literal-oracle tests; reviewer inspected evidence but did not rerun tests.

Coverage includes literal thresholds, existing HP, absent creation reward receipts, +599/+1 threshold, pending choices without double HP, below-next-level HP stability, duplicate reward receipts, complete late-failure rollback, unsupported targets and HTTP/store/fresh-manager resume.

Evidence: docs/acceptance/evidence/c06-starting-xp-20261029.

## Recovered source identity
Cloud workspace had reverted. Source checkpoint1947 and runtime2004 were restored from delivered verified ZIPs. This new candidate uses genuine existing historical HEAD96e0fec77b628d34ec1e3f2cce904a61efe3a4f3 with a dirty recovered snapshot, not the original a963 base and not synthetic1616. No new commit, push, merge or deployment. Guard pin unchanged; external frozen Python3.13.5 environment and fresh preflight proof.

## Limits
Existing saved characters with underfilled XP are not migrated. Full C06, higher levels/classes and pending class effects remain open. This source correction is NOT yet in the Windows runtime UI bundle; that bundle's startup is being diagnosed separately. Do not claim manual browser acceptance or runtime update until verified.
