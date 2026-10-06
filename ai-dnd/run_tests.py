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
    "api/tests/test_death_bounded.py",
    "api/tests/test_initiative.py",
    "test_regression.py",
    "test_migration.py",
    "test_migration_harden.py",
    "test_door_enter.py",
    "test_query.py",
    "test_self_query.py",
    "test_actual_logic.py",
    "test_npc_query.py",
    "test_narrative_rebalance.py",
    "test_narrative_safety_calibration.py",
)

PROTOTYPE_TESTS = (
    "test_combat_v2.py",
    "test_combat_v2_fixed.py",
)


def run_unittest_gate(module):
    """Require both successful assertions and evidence of executed tests."""
    import unittest

    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
        result = unittest.TextTestRunner().run(suite)
    except SystemExit as exc:
        # An import or loading hook can exit with status zero before testsRun
        # is available. That is not evidence of a successful gate.
        print(
            f"UNITTEST GATE FAILED: {module} exited before completing tests "
            f"(SystemExit: {exc.code!r})",
            file=sys.stderr,
        )
        return 1
    if result.testsRun == 0:
        print(f"UNITTEST GATE FAILED: {module} ran no tests", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


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
        # API suites import from the project root and have no script entrypoint.
        # Keep script execution for existing gates with custom main functions.
        if Path(test_name).parent != Path("."):
            module = ".".join(Path(test_name).with_suffix("").parts)
            command = [
                sys.executable, "-c",
                "import sys; from run_tests import run_unittest_gate; "
                "sys.exit(run_unittest_gate(sys.argv[1]))",
                module,
            ]
        else:
            command = [sys.executable, str(ROOT / test_name)]
        result = subprocess.run(command, cwd=ROOT)
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