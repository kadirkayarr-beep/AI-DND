#!/usr/bin/env python3
"""Run the portable deterministic gates for AI-DND."""

from pathlib import Path
import subprocess
import sys

from test_definition_preflight import check_test_definitions


ROOT = Path(__file__).resolve().parent
TESTS = (
    "test_definition_preflight_checks.py",
    "test_ai_pipeline_port.py",
    "test_ai_pipeline_semantics.py",
    "test_startup.py",
    "test_sessions.py",
    "test_playable_living_world.py",
    "test_persistence.py",
    "test_combat.py",
    "test_combat_v2.py",
    "test_combat_v2_fixed.py",
    "test_combat_v2_authoritative.py",
    "test_regression.py",
    "test_migration.py",
    "test_migration_harden.py",
    "test_door_enter.py",
    "test_query.py",
    "test_self_query.py",
    "test_actual_logic.py",
    "test_npc_query.py",
)


def main():
    errors = check_test_definitions(ROOT / test_name for test_name in TESTS)
    if errors:
        print("TEST DEFINITION PREFLIGHT FAILED:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    failures = []
    for test_name in TESTS:
        print(f"\n=== {test_name} ===", flush=True)
        result = subprocess.run([sys.executable, str(ROOT / test_name)], cwd=ROOT)
        if result.returncode != 0:
            failures.append(test_name)

    print("\n" + "=" * 54)
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print(f"ALL {len(TESTS)} DETERMINISTIC GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())