"""D-467: the nine save and move protection tests that every guarded slot run skips must run, unskipped, in CI.

Usage (from ai-dnd/): python scripts/protected_tests_run.py [--load-only]
Exit 0 = all nine ran and passed, 1 = a skip, a failure, or a different count.
--load-only only imports the nine tests (exit 1 if one cannot be imported).
"""
import sys
import unittest
from pathlib import Path

# A script run puts scripts/ on sys.path, not ai-dnd/; the tests import `api` and `game` from ai-dnd/.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTECTED = (
    "api.tests.test_engine_parts_pilot.PilotRollD20.test_both_import_orders_work_in_a_fresh_interpreter",
    "api.tests.test_character_identity_persistence.CharacterIdentityPersistenceTests.test_identity_fields_survive_new_process_resume",
    "api.tests.test_character_identity_persistence.CharacterIdentityPersistenceTests.test_save_without_identity_fields_still_loads",
    "api.tests.test_character_identity_persistence.CharacterIdentityPersistenceTests.test_omitted_save_clears_identity_on_the_same_character",
    "api.tests.test_character_identity_persistence.CharacterIdentityPersistenceTests.test_turkish_empty_and_null_follow_the_input_contract",
    "api.tests.test_f03_fault_chains.F03FaultChains.test_save_rollback_component_recovery_retry_once",
    "api.tests.test_f03_fault_chains.F03FaultChains.test_restore_failure_real_restart_and_precommit_outage",
    "api.tests.test_f03_fault_chains.F03FaultChains.test_healthy_precommit_api_outage_separate_from_restore_failure",
    "api.tests.test_f03_fault_chains.F03FaultChains.test_model_failure_full_invariance",
)


def problems(result: unittest.TestResult, expected: int) -> list[str]:
    out = []
    if result.skipped:
        out.append(f"{len(result.skipped)} skipped")
    if result.failures or result.errors:
        out.append(f"{len(result.failures) + len(result.errors)} failed")
    if result.testsRun != expected:
        out.append(f"ran {result.testsRun}, expected {expected}")
    return out


def _flat(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    return [leaf for part in suite for leaf in (_flat(part) if isinstance(part, unittest.TestSuite) else [part])]


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(PROTECTED)
    if "--load-only" in sys.argv:
        broken = [t.id() for t in _flat(suite) if type(t).__name__ == "_FailedTest"]
        for name in broken:
            print(f"PROTECTED TESTS: cannot load {name}")
        return 1 if broken or len(_flat(suite)) != len(PROTECTED) else 0
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    found = problems(result, len(PROTECTED))
    for line in found:
        print(f"PROTECTED TESTS: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
