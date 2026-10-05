# Legacy combat identity migration

## Production repair

Valid active V1/V2 two-participant combat receives a new encounter UUID inside
`game._migrate_legacy_combat_state`, after the legacy boundary and target checks.
The migration retains the saved round, initiative order, participant list,
target, and current turn index, and derives the current actor from that index.
Repeated normalization and V3 save/reopen retain the migrated identity.

Native active V3 saves still require their own identity. No validator relaxation,
fixture identity injection, or change to inactive combat identity was made.
Malformed legacy boundaries and missing targets remain visible failures.

## Executed evidence

Command:

```sh
cd ai-dnd
python -m unittest test_combat_v2_authoritative test_persistence test_sessions api.tests.test_combat_lifecycle
```

102 tests ran: 101 passed and the sole failure was the independently tracked
`test_W_npc_death_narration` contract already recorded in
`COMBAT_RELEASE_FIXTURE_RECONCILIATION.md`. The original
`test_V3_legacy_turn_boundary_migrates_without_losing_cursor` passed unchanged.
This is not a passing full-release-suite claim.

Added retained-owner checks cover both save versions, explicit and omitted
legacy schema versions, both cursor positions, differently ordered participant
lists, identity stability through V3 save/reopen, native V3 missing identity
rejection, and malformed legacy boundary rollback. Failed loads retain
caller-held character/world/narration references, their contents, and RNG state.
The existing missing-target rollback and native midround persistence tests passed.

The enhanced save/reopen check also advances the reopened scheduler through its
existing owner, without initiative rerolls, retaining identity and advancing from
the saved cursor rather than restarting the encounter.
That enhanced test was rerun independently and passed. The retained release
test-definition preflight and CRLF-aware diff whitespace check also passed.

The FastAPI artifact service started cleanly; `/api/health` returned HTTP 200 both
directly and through the development preview proxy. The unchanged primary
campaign frontend rendered its landing screen. No live model gameplay or
production deployment was performed.
