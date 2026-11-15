"""D-053: product code never imports the test package.

The K07 oracle harness (`rule_oracles`) runs the real engine resolvers on test fixtures (`api.tests.test_spell_scope.caster`,
`test_weapon_attack`, `test_species_traits`...), so it is test code and lives under `api/tests/`. This guard scans every
product module (the `ai-dnd/` top level and every package beside it, such as `api/` outside `api/tests/`,
`adventure/`, `class_progression/`, `incidents/`) for an import of `api.tests`; a name
in a string (capabilities' test-owner path) is not an import and is not caught.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

AI_DND = Path(__file__).resolve().parents[2]
TEST_IMPORT = re.compile(r"^\s*(?:from\s+api\.tests\b|import\s+api\.tests\b|from\s+api\s+import\s+tests\b)", re.MULTILINE)


def _product_modules():
    for path in sorted(AI_DND.glob("*.py")):
        if not path.name.startswith("test_"):
            yield path
    for package in sorted(init.parent for init in AI_DND.glob("*/__init__.py")):  # api, adventure, class_progression...
        for path in sorted(package.rglob("*.py")):
            relative = path.relative_to(AI_DND).as_posix()
            if relative.startswith("api/tests/") or path.name.startswith("test_"):
                continue
            yield path


class ProductNeverImportsTests(unittest.TestCase):
    def test_no_product_module_imports_the_test_package(self):
        scanned = list(_product_modules())
        self.assertTrue(any(p.name == "game.py" for p in scanned))  # the scan must look at the real package
        for package in ("adventure", "class_progression", "incidents"):  # product sub-packages are product code too
            self.assertTrue(any(p.parent == AI_DND / package for p in scanned), package)
        importers = [
            path.relative_to(AI_DND).as_posix()
            for path in scanned
            if TEST_IMPORT.search(path.read_text(encoding="utf-8", errors="replace"))
        ]
        self.assertEqual(importers, [])

    def test_the_oracle_harness_lives_in_the_test_package(self):
        self.assertFalse((AI_DND / "rule_oracles.py").exists())
        from api.tests import rule_oracles

        self.assertTrue(rule_oracles.ORACLE_PATH.is_file(), rule_oracles.ORACLE_PATH)


if __name__ == "__main__":
    unittest.main()
