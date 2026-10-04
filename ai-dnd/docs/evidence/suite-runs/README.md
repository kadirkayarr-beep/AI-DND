# NEW suite-run evidence

These are new development/validation runs, not recovered historical evidence.
None certify the missing historical 563/563 run. JSON and matching `output.log`
are retained together; failures are not removed or rewritten as successes.
See [the evidence contract](../../regression-evidence.md).

## Completed validation of the evidence runner

`20261004T091911Z-7fd21e30fb6140f4a5e448cf3f367cac/run.json`

- Exact command: `python ai-dnd/scripts/run_regression_evidence.py
  api.tests.test_regression_evidence api.tests.test_bounded_encounter test_regression`
  (the manifest retains the interpreter's absolute argv and working directory).
- 58 unique selected/executed tests: 56 pass, 1 failure, 1 error, 0 skips.
- Evidence contracts: 8/8 pass. Bounded encounter: 27/27 pass.
- Existing plain regression functions: 21 pass, 1 failure, 1 error.
- `test_regression.test_named_location_return` fails with forest instead of tavern.
- `test_regression.test_unsupported_attack` errors with `CombatRequestError`.
- Direct execution of the unchanged `test_regression.py` reproduced both
  non-passing results. This task does not change those game/test expectations.
- Source fingerprint unchanged between start/end. Suite exit status is **1**;
  the complete combined selection is **not PASS**.

## Earlier development attempts (also retained)

- `20261004T091514Z-d143c1c1fdfb49bd8bf44e588bc24741/run.json`:
  57 executed, 54 pass, 2 failures, 1 error. One failure is the fingerprint
  contract detecting incorrectly resolved Git-relative paths. **Its source
  fingerprint is invalid**, so do not use this attempt to certify source content.
  The original record is retained, not retroactively corrected.
- `20261004T091621Z-0db2505eb056459689ab1bf4ce956b47/run.json`:
  58 executed, 55 pass, 1 failure, 2 errors. One error is discovery rejecting
  the namespace-only test directory in Python 3.13; discovery was subsequently
  fixed and verified in the completed validation above.

HTTP acceptance evidence remains at `../bounded-encounter-http.json`, unchanged
and separate from these suite records. No live acceptance was rerun.

## Interrupted return persistence and replay

- `20261004T095418Z-52c801b635484251a21a0b42858db8ea/run.json`:
  **35/35 pass**, no skips, exit status **0**. Command (from `ai-dnd`):
  `python scripts/run_regression_evidence.py api.tests.test_campaign_time api.tests.test_campaign_time_edges`.
  The matching `output.log` and manifest retain exact test IDs and source fingerprints.
- The two new offline API regressions combine an interrupted return with campaign
  autosave, explicit save, a fresh store/manager/API resume, same-action replay,
  encounter resolution, and completion of the remaining 240 seconds. Receipt
  replay changes only the transport session ID after resume and never reruns
  the engine, saves another turn, changes current state/history, or rolls dice.
- The failed-autosave case proves the engine already advanced the return before
  the save failed, then checks restoration of engine state, clock, RNG, messages,
  journal, narrative memory, persisted history, and absence of a failed receipt.
  Retrying the same action ID succeeds once and remains replayable after reload.
- `20261004T095355Z-4c5b5895978245098bdad2359282745f/run.json`:
  focused development run, **2/2 pass**, exit status **0**.
- `20261004T095304Z-055bf818da4a41fe952bb98c2c551c43/run.json`:
  initial development run, **0/2 pass**, two fixture expectation failures, exit
  status **1**. The fixture initially assumed travel created a pending goal;
  it now explicitly sets that goal before travel and checks its persistence.
  This failed attempt is retained, not replaced by the passing runs.

These runs use an in-process API, temporary campaign databases, and a model
adapter that rejects model calls. They are not live HTTP acceptance evidence;
no live acceptance or provenance work was run or changed.