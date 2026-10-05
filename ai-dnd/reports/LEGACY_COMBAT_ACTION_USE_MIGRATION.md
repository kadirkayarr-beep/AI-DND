# Legacy combat action-use compatibility

## Historical audit

The initial V1 writer (`192c0cd`) and the last V2 writer before Combat V3
(`0e751cb^`) stored active combat with `active`, `round`, `initiative_order`,
`current_turn_index`, `participants`, and `target_id`. Neither wrote
`actions_used`, participant action-availability records, or a modern turn-resource
ledger. `actions_used` and participant records first appear with Combat V3 and
save format V3 (`0e751cb`). The save-envelope version and combat schema version
are separate boundaries.

Therefore a fixture with V1/V2 plus spent markers is an explicit additive
compatibility case, not proof that native historical writers emitted it.
Unmarked historical saves remain supported without inventing spending from the
cursor or requiring modern fields.

## Supported migration contract

- Active two-participant legacy encounters accept an omitted `actions_used`
  field (empty default), or a list of unique, nonempty canonical participant IDs.
- Explicit player, enemy, and both-participant spending survives migration.
  Marker order is retained, and the output owns a detached copy.
- Wrong container types, null, nonstring or empty entries, duplicates, and
  nonparticipant IDs fail visibly. Inactive legacy combat cannot discard a
  nonempty marker list; it rejects it instead.
- Participant action availability and initial base-action resources derive from
  the retained markers through their existing owners. No modern resource
  fields are required in legacy input.
- Round, order, participants, target, and cursor remain unchanged. Migration
  alone creates encounter identity, which remains stable through normalization
  and V3 save/reopen. Native V3 still goes through strict native validation.

## Retained-owner regression evidence

`test_combat_v2_authoritative.py` checks save versions 1 and 2, omitted and
explicit legacy schemas, both cursor positions, omitted/empty markers and
player/enemy/both spending. Fixtures omit participant records and modern
resource ledgers. Save/reopen compares complete snapshots, checks identity,
projections and resources, and exercises the real action-resource owner to
reject a second action without dice or state changes.

Malformed active and inactive markers test failed-load rollback, caller-held
character/world/narration references, and RNG preservation. Separate checks
cover detached marker ownership and strict native V3 rejection of malformed or
contradictory markers.

Verification command:

```sh
cd ai-dnd
python -m unittest test_combat_v2_authoritative test_persistence test_sessions \
  api.tests.test_action_economy api.tests.test_combat_lifecycle
```

The first combined run passed all 158 tests before the separate native-marker
regression was added. The latter was checked separately. This is offline engine
and API contract evidence, not historical execution evidence or live-model
acceptance.
