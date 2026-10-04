# Read-only spell presentation

## Ownership and contract

`spell_scope` owns initialization, validation, consumption and restoration of
`world_state["spellcasting_v1"]`. This follow-up changes none of those owners.

`api.serializers.serialize_session_state` now exposes one optional public
`GameState.spellcasting` projection, with deep-copied values:

- `cantrips`
- `prepared`
- `slots` — remaining counts, not inferred capacity
- `slot_turn` — existing `[combat_id, round, turn_index]` marker or null

The field is null when the authoritative state is absent. Older responses may
omit it. Neither case creates grants or preparation. `GameCharacter` stays
unchanged to avoid a duplicate representation. OpenAPI and generated client/Zod
types describe the additive optional field.

## Presentation boundaries

The experience artifact renders the same read-only panel in character reveal,
desktop character information and the mobile character drawer. It lists supplied
cantrips/prepared spells, displays zero slots without replacing them, and shows
the last slot-use round/turn without exposing the combat ID.

There are no casting controls, client resource stores, optimistic decrements,
inferred preparation or cast-legality calculations. Listed access does not promise
that a deferred or context-invalid mode can be cast. Wizard spellbook selections
remain distinct from actual preparation.

## Evidence

- API/regression: 36 passed, no failures/errors/skips.
  `evidence/suite-runs/20261004T163056Z-475a7d7a99cc40169dfc4622dd4389df/run.json`
- Frontend: 46 passed, no failures/skips.
  `evidence/spell-presentation/frontend-tests.log`
- Codegen, typecheck and build logs:
  `evidence/spell-presentation/`
- Starting checkout and exact source comparison:
  `evidence/spell-presentation/start.json` and `production-guard.json`
- Intermediate attempts are retained; the first 71-test run included redundant
  discovery of an imported test class and is not the final selection.

The native API test verifies actual cast consumption, unchanged replay and resume
projection. `evidence/spell-presentation/browser.json` records the live eight-step
Sorcerer creation, reveal, desktop adventure and 390×844 character drawer pass.
The observed projection contained four cantrips, two prepared spells, two level-1
slots and a null slot-turn marker, unchanged across read-only checks.
This bounded projection fix does not certify the unfinished broader UI lock.