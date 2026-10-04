# Exit and return command regression evidence

These are **new offline Python regression runs**, not live HTTP acceptance or
certification of any historical result. The live HTTP archive and verifier are
unchanged.

## Authoritative expectations

The tests in `test_regression.py` run complete player turns with a mocked model.
They assert action, status, success, committed location, pending destination,
journey state and both receipt time and campaign elapsed time.

- **Local exit:** `buradan çıkıyorum` follows a registered `exit_location_id`
  or `parent_location_id`. The existing scene transition is instant (zero
  seconds), leaves an unrelated pending destination intact and does not create
  a journey. No exit, or an unregistered exit, returns `exit / unresolved /
  success=False` without moving. A pending cross-region goal is not a local exit.
- **Return without a destination:** `geri dönüyorum`, with no active journey or
  pending destination, returns `travel / clarification / success=False`, with
  no location, destination or time change.
- **Return to a pending destination:** a fixture-owned `[420]` route arrives,
  charges exactly 420 seconds, marks the journey `ARRIVED`, and clears the
  pending destination. A location name alone does not authorize a route.
- **Return during a journey:** interrupted and stopped journeys retrace 210
  seconds of actual progress; a completed first stage of a multi-stage journey
  retraces 420 seconds. The recorded origin wins over the pending goal. Return
  does not reroll travel encounters.
- **Route refusals:** bare and named returns preserve location, pending goal,
  time and absence of a journey on `unverified` or `blocked` results.
- **Combat refusal:** bare exit and return raise the existing `combat_travel`
  request error without movement, time, journey or combat-state changes.
  Fixtures include a real player-turn combat, a usable local exit and an
  interrupted journey, rather than merely setting an `active` flag.

The existing named-location return and invalid-target checks remain in the
legacy suite. The only runtime repairs are deterministic bare-return handling
in `timed_gameplay.py` and closing the bare-exit/return gap in the existing
`combat_lifecycle.py` travel guard. Local-scene exit behavior in `game.py`
remains unchanged.

## Passing retained runs

Run from `ai-dnd/` in separate processes:

```sh
python scripts/run_regression_evidence.py test_regression
python scripts/run_regression_evidence.py \
  api.tests.test_campaign_time api.tests.test_campaign_time_edges \
  api.tests.test_combat_lifecycle test_playable_living_world
```

- **29/29 legacy regression functions:** [run.json](evidence/suite-runs/20261004T094212Z-5a44350b488b4120936c36b31c5a123e/run.json)
  and [output.log](evidence/suite-runs/20261004T094212Z-5a44350b488b4120936c36b31c5a123e/output.log).
- **80/80 adjacent campaign-time, interruption, combat and local-scene tests:**
  [run.json](evidence/suite-runs/20261004T094221Z-3cbe52ac6b194a7bbc9a0b7370c77d16/run.json)
  and [output.log](evidence/suite-runs/20261004T094221Z-3cbe52ac6b194a7bbc9a0b7370c77d16/output.log).

Both records report no source change during execution, no unexecuted selected
tests, zero failures/errors/skips and exit status 0. These are two independent
passing runs, **not a passing combined 109-test invocation**.

## Retained development attempts and limitations

Do not replace these records with the passing results:

- [Initial contract probe](evidence/suite-runs/20261004T093828Z-f209a8f67c2b4729a5155ad58ac4d5ab/run.json):
  7 tests, 1 pass, 5 failures, 1 error. It demonstrated bare-return narrative
  no-ops, but also incorrectly assumed local exits were timed travel and used
  an incomplete combat fixture. Those assumptions were corrected against the
  existing local-scene contract.
- [First combined development run](evidence/suite-runs/20261004T094010Z-7ace580dbe7f4c5398c79bea9cdd7d8c/run.json):
  109 tests, 100 passes, 9 errors. This included a repaired module-access error
  in the new combat guard and shared-model-mock contamination.
- [Combined run after that repair](evidence/suite-runs/20261004T094110Z-20b07c75956044349f0cb5450d73b2e5/run.json):
  109 tests, 106 passes, 3 errors. Importing the API suites mutates the shared
  legacy model mock's `chat` method; three unrelated tests then cannot set
  `return_value` or `side_effect`. Separate processes avoid this existing
  test-isolation defect without changing unrelated tests or the evidence runner.

Each linked failed run has its complete sibling `output.log`.