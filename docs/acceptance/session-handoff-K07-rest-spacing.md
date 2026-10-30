# K07 Long Rest start spacing — 2026-10-28

## Decision
Independent static review ACCEPTED the narrow `K07.long_rest_start_spacing` leaf. Bounded source: K07v2 glossary PDF369. Full K07/C06 and ability-score restoration remain OPEN.

## Behavior
Store optional `world_state.last_long_rest_completed_at` after completed Long Rest benefits, using actual authoritative campaign elapsed seconds. Reject another start before57600seconds have elapsed since that completion. A requested long duration cannot bypass the pre-start gate. First legacy save without recorded completion remains compatible; no historical time is invented. Interrupted rests and Short Rest do not update completion time. The separate interrupted-rest resume/progress policy remains OPEN.

Present markers must be exact integers, nonnegative and no later than the campaign clock. Save validation checks before mutation. Existing full-world snapshots/persistence own serialization and rollback; no new save version or external migration.

## Evidence
- `rest-spacing-red`:6methods,12assertionfailures,zeroerrors beforeimplementation.
- `rest-spacing-green`:59relatedexecutionsPASS.
- `rest-spacing-oracle-red`:12methods, one missing-binding assertion failure; actualbehavior and SQLrollback/retry/replay assertionspassed.
- `rest-spacing-regression`:invalid test module selector, NOTpassing.
- `rest-spacing-regression-fixed`:149executionsPASS after correcting root `test_save_migration` selector; source unchanged.
- Final broad related checkpoint:781executions/765uniquequalifiedmethods, allPASS, exit0. Includes previousdeath/Dodge/Invisible/session/regressions, not fullrelease. Four oldconcurrentsnapshot subtest failures were solely the newcompletedmarker missing from explicitexpectedworld; diagnosedwithfulldiff, addedliteral28800onlytocompletedbranch. Interruptedbranchandallownershipassertionspreserved.

Existing realSQLreceiptfailure test now proves completionstamp exists before failure, disappears onrollback, retrycommits, replaydoesnotrerun, reopeningpreserves. Other coveredcases: immediateand57599refusal,57600acceptance, requested24hbypassrefused,shortrestpreservesstamp,interruptionwithShortRestbenefitsdoesnotstamp,legacyloadandinvalidload.

Review is static, not an independent execution. Nonblocking: explicit marker0 and marker-without-clock tests. No push/merge/deployment. Local imported source history limitation and guard restrictions are unchanged; see death checkpoint.

B02 EvidenceRecord validated and bound to independentreview, rawlogdigest and scopedsourcehashes in `evidence/k07-rest-spacing-20261028/`. No independent test rerun claimed.
