# C06 ASI record boundary — preparation only

2026-10-29. Independent static review approved production rejection/compatibility guards and a separate private hypothetical replay validator. No nonempty ASI record is admitted and actual level4 remains blocked.

Production accepts only absent/exact empty asi_choices. Malformed/nonempty records reject even without progression markers. Writer validates before output instead of silently dropping claims. Loader validates before mutation, then clears stale owned asi_choices when absent/empty; legitimate creation removes that owned field with one line. Unrelated general feats are untouched. No save version is promoted and no future v4/v5 admission is implemented.

The private helper takes explicit normalized future context, validates complete baseline through existing creation constraints, delegates ASI mechanics to C03, replays from original base+background and compares all six current scores. It returns internal consistency only, not a ready token or entitlement. Rolled/missing provenance rejection is confined to this hypothetical path; legacy absent saves are not retrofitted. A record is a consistency-checked claim, not cryptographic provenance.

Actual targeted RED1 assertion preceded implementation; focused9 PASS and final related143 executions PASS with unchanged guard. First attempted run was BLOCKED during guard setup because PATH selected an untrusted Git executable; corrected invocation PATH=/usr/bin:/bin only, no guard edits. Counts overlap earlier suites. Independent reviewer inspected code/raw evidence but did not rerun. See docs/acceptance/evidence/c06-asi-persistence-preparation-20261029.

Real evidence covers absent/empty compatibility, rejection immutability and stale cleanup. Detached future +2/split/baseline/cap/type/double-delta cases are not successful level4 save roundtrips. Future integration still needs explicit live/saved provenance adapters, class-slot admission, version policy, derived stats and atomic application. No public API/UI change, new store/receipt/healing owner, full C06 acceptance, commit/push/merge/deployment.
