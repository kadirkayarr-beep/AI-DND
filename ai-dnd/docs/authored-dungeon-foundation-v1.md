# Authored room/exit foundation V1

Only an opt-in, deterministic local-fiction fixture, not setting lore or a
procedural dungeon generator. No geometry, pathfinding, DCs, traps, spells,
doors/locks, pace/distance rules or Living World expansion are introduced.

## Existing browser / public turn API

Send these through the existing message/turn controls:

- `/dungeon enter`: bind the fixture to the current registered location and enter
  `authored_dungeon_entry` (Taş Eşik).
- `/dungeon exits`: Python describes only the current room's authored exits.
- `/dungeon exit entry_hall`: move from entry to `authored_dungeon_hall`.
- `/dungeon exit hall_entry`: return to entry.
- `/dungeon exit entry_origin`: leave entry for the original campaign location.
- `hall_vault` is explicitly blocked. `authored_dungeon_vault` exists but is not
  reachable from the hall in this foundation.

Exits are directed facts; reverse routes are separately authored. Unknown,
wrong-room, blocked or nonadjacent transitions fail before gameplay mutation.
Natural travel cannot bypass the fixture graph. Outside this opt-in fixture,
the existing location/travel behavior remains unchanged.

## Authority, persistence and scope

Python owns the optional `world_state.authored_dungeon_v1` definition; the single
position owner remains `world_state.location`. The existing
`commit_location_change` handles successful scene/arrival transitions and the
campaign journal records canonical location changes.

The native commands use deterministic Python narration and zero model calls.
Qwen does not author the graph, room IDs, destinations or results. The existing
frontend presents the server-projected location and returned narration; no new
frontend mechanics, API endpoint or UI redesign is required.

Room traversal in this fixture has no authored time/distance cost; it does not
invent a travel duration. This is not a change to ordinary travel conventions.
Combat, active tasks and interrupted travel/pending decisions prevent entry or
traversal rather than silently canceling adjacent gameplay.

The existing campaign save, atomic action receipt and rollback owners persist
the graph and location. Replay precedes current-room validation, including
after restart; changed-payload action-ID reuse remains 409. No new receipt
store or save version is introduced. Legacy saves lacking the optional graph
still load without installing it. Invalid authored topology in a save is
rejected rather than repaired or regenerated.

Focused coverage: api.tests.test_authored_dungeon, using public turn APIs and
the production fixture, not injected room definitions.
