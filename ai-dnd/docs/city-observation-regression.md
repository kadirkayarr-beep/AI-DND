# City observation regression — 2026-10-05

## Authority and diagnosis

The old living-world fixture supplied:

> Şehirde dolanıyorum, etrafımda neler var gözlemliyorum.

This contains two complete first-person clauses separated by a comma.
The **Compound-plan correction — 2026-10-05** section of
[Interaction, Quest & Adventure V1](interaction-quest-adventure-v1.md) requires
source-bound plan routing before scene materialization and action dispatch.
Consequently, `plan_living_world_turn` correctly returns no direct scene result.
It does not call a model to interpret this sentence.

The retained original failure is a fixture/contract mismatch, not evidence that
single-action city observation is broken:

- [Original failure record](evidence/suite-runs/20261005T134021Z-5f59885ef66540e1ba3e8614502911e4/run.json)
- [Original traceback](evidence/suite-runs/20261005T134021Z-5f59885ef66540e1ba3e8614502911e4/output.log)

## Reconciled checks

The observation fixture now uses one complete action clause:

> Şehirde dolanırken etrafımda neler var gözlemliyorum.

It runs in an explicitly synthetic city, rather than the suite's default forest.
Checks require a non-null, successful `explore`/`observed` result, city-specific
response text, and a materialized city scene. Subsequent purpose-based tavern
discovery and typo-tolerant merchant discovery must succeed, return usable text,
and link their locations and shopkeeper to that same city without moving the
player or replacing the materialized scene. Model calls fail the test.

A separate regression preserves the original two-clause sentence: the scene
classifier recognizes observation, but plan routing takes precedence. Exact
source steps are retained and the scene entry point leaves serialized campaign
state and RNG unchanged. This tests deferral, not full plan execution.

Only tests and evidence were changed. Gameplay, release inventory, and unrelated
combat/location-distance checks were not altered.

## New verification evidence

Command:

```sh
python ai-dnd/scripts/run_regression_evidence.py test_playable_living_world
```

**30/30 passed**, zero failures, errors, skips or unexecuted tests; the recorded
source fingerprint was unchanged during the run.

- [Suite record](evidence/suite-runs/20261005T134200Z-442e03419a464e6ba8135691d753f816/run.json)
- [Suite output](evidence/suite-runs/20261005T134200Z-442e03419a464e6ba8135691d753f816/output.log)

The default `python ai-dnd/run_tests.py` invocation also passed all 30
living-world tests. Its overall exit status was **1**, with failures remaining
in `test_combat.py` (historical unconscious expectation versus dead) and
`test_combat_v2_authoritative.py` (missing authoritative attack distance).
Those failures belong to the separate combat-release work and are preserved in
[the full release output](evidence/city-observation-release-20261005.log).
This plain release output is not a fingerprinted suite-run record.

These are new offline regression results, not historical certification, live
HTTP acceptance, browser acceptance, or real-model verification.
