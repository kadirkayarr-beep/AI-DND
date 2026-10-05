#!/usr/bin/env python3
"""Run release gates by default, or explicitly selected historical prototypes."""

import argparse
from pathlib import Path
import subprocess
import sys

from test_definition_preflight import check_test_definitions


ROOT = Path(__file__).resolve().parent
TESTS = (
    "test_definition_preflight_checks.py",
    "test_runner_inventory.py",
    "test_ai_pipeline_port.py",
    "test_ai_pipeline_semantics.py",
    "test_startup.py",
    "test_sessions.py",
    "test_playable_living_world.py",
    "test_persistence.py",
    "test_combat.py",
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

PROTOTYPE_TESTS = (
    "test_combat_v2.py",
    "test_combat_v2_fixed.py",
)


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("release", "prototype"), default="release",
                        help="prototype checks are historical diagnostics, not release gates")
    parser.add_argument("--list", action="store_true", help="list selection without running tests")
    args = parser.parse_args(argv)
    tests = TESTS if args.suite == "release" else PROTOTYPE_TESTS
    label = ("RELEASE DETERMINISTIC GATES" if args.suite == "release"
             else "HISTORICAL PROTOTYPE CHECKS (NOT RELEASE GATES)")
    print(f"{label}: {len(tests)} selected", flush=True)
    if args.suite == "release":
        print("Excluded historical prototypes: " + ", ".join(PROTOTYPE_TESTS), flush=True)
    if args.list:
        for test_name in tests:
            print(test_name)
        return 0

    errors = check_test_definitions(ROOT / test_name for test_name in tests)
    if errors:
        print("TEST DEFINITION PREFLIGHT FAILED:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    failures = []
    for test_name in tests:
        print(f"\n=== {test_name} ===", flush=True)
        result = subprocess.run([sys.executable, str(ROOT / test_name)], cwd=ROOT)
        if result.returncode != 0:
            failures.append(test_name)

    print("\n" + "=" * 54)
    if failures:
        print(f"{label} FAILED:", ", ".join(failures))
        return 1
    if args.suite == "release":
        print(f"ALL {len(tests)} DETERMINISTIC GATES PASSED")
    else:
        print(f"ALL {len(tests)} HISTORICAL PROTOTYPE CHECKS PASSED (NOT RELEASE GATES)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))