# Combat release fixture reconciliation

## Scope

This is fixture/contract reconciliation only. No production combat, death,
initiative, perception, weapon, or release-selection code was changed.
The retired `test_combat_v2.py` and `test_combat_v2_fixed.py` remain outside
the release selection.

## Reconciled assumptions

- Ordinary lethal NPC damage at zero HP now asserts Policy A (`dead`) in
  the result and canonical NPC, retaining HP and damage assertions.
- Scheduler fixtures explicitly author five-foot geometry, typed NPC damage,
  enemy visibility, and the player's equipped/proficient longsword. The second
  hostile NPC has its own geometry, damage type, and visibility facts.
- Strict ordered session-owned dice scripts remain intact. Stabilization's
  recovery roll is explicitly scripted as 1d4 hours and its result asserted.
- Negative damage modifiers floor at zero, not one; target HP must remain
  unchanged and cannot be healed by the attack.
- Normal travel during combat asserts the authoritative `combat_travel`
  rejection, including unchanged world, character, and RNG.
- Narration, duplicate-definition, and player-unconscious checks run separately
  so one failure cannot hide the others. Direct execution no longer stops
  at the first failed test.
- Existing cross-campaign state/RNG assertions, refusal checks, forged target
  checks, save/resume checks, snapshots, and natural-one/twenty checks remain.

## Executed checks

- `cd ai-dnd && python test_combat.py`: passed all scenarios, including
  missing geometry and nonparticipant refusal without state/RNG mutation.
- `cd ai-dnd && python test_combat_v2_authoritative.py`: 34 tests executed;
  32 passed, one failure and one error. Exit status 1 is intentional evidence
  of the remaining production contracts, not a passing release claim.
- `cd ai-dnd && python test_runner_inventory.py`: all 8 tests passed.
- `check_test_definitions` across every source selected by `run_tests.TESTS`:
  passed. Source selection assertions confirmed both retained combat suites
  remain selected and neither retired prototype is selected.

The complete multi-suite release runner was not executed; these results certify
only the checks above, not the other release suites or live HTTP behavior.

## Preserved production failures

### Active legacy migration loses combat identity

`test_V3_legacy_turn_boundary_migrates_without_losing_cursor` still errors:

```text
ValueError: Etkin çatışmanın kimliği eksik.
```

The valid legacy two-participant fixture supplies its round, participants,
target, and turn cursor. `_migrate_legacy_combat_state` builds an active V3
state without a `combat_id`; `ensure_combat_state` then validates that state
and rejects the missing identity. Injecting an ID into the fixture or expecting
the valid legacy boundary to fail would hide the migration contract violation.
All original cursor/order/round/schema assertions are retained.

### Death narration omits the resolved mortality outcome

`test_W_npc_death_narration` still fails:

```text
AssertionError: 'ölür' not found in 'Sentinel, kritik bir darbe alır: 9 hasar.'
```

The lethal attack correctly records `dead` in its result and canonical NPC.
The old unconsciousness sentence expectation is now the equivalent Policy A
death sentence expectation. `_combat_narration` renders the critical hit and
damage but only has an NPC status suffix for `unconscious`, not `dead`.
The assertion remains a normal failure: no skip, xfail, catch-and-pass, or
weakened outcome requirement was added.

Production remediation for these two contracts is separate follow-up work.
