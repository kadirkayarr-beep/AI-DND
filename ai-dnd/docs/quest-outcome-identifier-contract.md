# Quest outcome identifier boundary findings

## Scope

`api/tests/test_quest_outcome_identifier_limits.py` exercises real catalog
validation, `GameSession.accept_quest`, `cancel_quest`, `evaluate_quest_events`,
the `TurnResponse` serialization used by the turn endpoint, and actual HTTP
turn and quest-command endpoints. Only model-driven turn orchestration is
replaced; no remote model is called and no outcome array is fabricated.

The published `QuestOutcome` bounds remain unchanged:

- `event_id` and `source_event_id`: 300 characters.
- `quest_id` and non-null `objective_id`: 120 characters.
- `objective_id` is emitted as null for accepted, cancelled and completed
  outcomes.

The runtime `QuestOutcome` intentionally has no string bounds. Runtime code,
canonical IDs, the production catalog and the published API were not modified.

## Passing conformance cases

Tests preserve exact canonical strings, not just their lengths, for all five
transitions. They cover 120-character quest/objective IDs, cancellation of
both offered and accepted quests, null objectives, repeated command outcomes,
and actual turn responses containing progress, objective completion and quest
completion. A 142-character registered location target with a one-digit turn
produces an exactly 300-character objective-completed event ID, which survives
the `TurnResponse` projection unchanged.

## Confirmed contract violation

The engine constructs the composite identifier as:

```
quest:{transition}:{quest_id}:{source_event_id}
```

Independent field limits do not reserve space for that prefix and quest ID.
With a validated 120-character quest ID and 160-character location target,
ordinary one-digit turns generate:

| Transition | Source length | Event length | Published event maximum |
| --- | ---: | ---: | ---: |
| objective_progress | 171 | 317 | 300 |
| objective_completed | 171 | 318 | 300 |
| completed | 171 | 308 | 300 |

These overflow unchanged through `TurnResponse`. The actual HTTP turn endpoint
currently fails earlier with `narrative_memory_error` and restores canonical
state, because narrative memory limits location identifiers to 120 characters.
Thus these particular long-location cases are **not successful HTTP replies**;
the tests distinguish model projection from full endpoint behavior.

The tests also reach the exact 300-character source boundary using very large
but currently legal canonical turn indices (neither the engine nor the
published outcome schema places an upper bound on these integers):

| Transition | Turn digits | Source length | Event length | Verified boundary |
| --- | ---: | ---: | ---: | --- |
| accepted | 164 | 300 | 436 | Actual HTTP quest command |
| cancelled | 164 | 300 | 437 | Actual HTTP quest command |
| objective_progress | 130 | 300 | 446 | Engine and TurnResponse |
| objective_completed | 130 | 300 | 447 | Engine and TurnResponse |
| completed | 130 | 300 | 437 | Engine and TurnResponse |

The command cases prove successful HTTP replies can violate the published
event limit, albeit at extreme turn indices. Source, quest and objective limits
still hold; it is the composite event ID that exceeds its bound.

Overflow tests are explicit characterization tests, **not proof that all
generated outcomes conform**. They intentionally assert the known violation
and full untruncated identity. Once an approved bounded-identity solution is
implemented, replace these overflow assertions with conformance assertions.
Do not silently truncate identifiers: that could merge distinct event identities
or disrupt deduplication.

## Verification

From `ai-dnd`:

```
python -m unittest \
  api.tests.test_quest_outcome_identifier_limits \
  api.tests.test_quest_outcomes \
  api.tests.test_contract_parity.ContractParityTests.test_quest_outcome_schema_matches_runtime_model -v
```
