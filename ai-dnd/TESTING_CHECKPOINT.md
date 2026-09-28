# Post-V2 Testing Checkpoint

## Production
- **game.py** - Verified SHA256: `07be801d3fb8cfaa26a09b3fc624e831f5f913cbb899f12662d808dffd919cf7`

## Protected Backups
- **game_backup.py** - SHA256: `b68fbc56606255611ad33e7e9d1518ca255f5315e85ebf938682b03755611e5b`
- **game_v10_backup_20260927.py** - SHA256: `b68fbc56606255611ad33e7e9d1518ca255f5315e85ebf938682b03755611e5b`
- **game_v10_backup_before_v11_20260927.py** - SHA256: `b68fbc56606255611ad33e7e9d1518ca255f5315e85ebf938682b03755611e5b`

## Authoritative Deterministic Gates
- `test_combat_v2_authoritative.py` - Combat V2: 24/24
- `test_combat_v2.py` - V2 turn pipeline: 15 deterministic scenarios using session RNG
- `test_combat_v2_fixed.py` - Compatibility command for the same 15 scenarios (not additional coverage)
- `test_combat.py` - Combat V1: 10/10 (5/5 repeated deterministic runs)
- `test_regression.py` - Regression: 22/22
- `acceptance_test.py` - Acceptance: 20/20

## Live-Model Gates
- `live_intent_test.py`
- `live_memory_test.py`

## Historical/Debug Artifacts
Moved to: `legacy_debug/`

## Deferred/Non-Release Diagnostics (still in root)
- `test_door_enter.py` - Door mechanics
- `test_migration.py` - Migration test
- `test_migration_harden.py` - Migration hardening
- `test_npc_query.py` - NPC query test
- `test_query.py` - Query test
- `test_query_logic.py` - Query logic
- `test_self_query.py` - Self query
- `test_actual_logic.py` - Actual logic test
- `test_door_enter.py` - Door enter test

## Expected Verified Results
- **Combat V2**: 24/24 PASS
- **Combat V2 turn pipeline**: 15/15 PASS via either historical command
- **Combat V1**: 10/10 PASS (5/5 deterministic repeated runs)
- **Regression**: 22/22 PASS
- **Acceptance**: 20/20 PASS

---

**PYTHON DECIDES REALITY. QWEN DESCRIBES REALITY.**