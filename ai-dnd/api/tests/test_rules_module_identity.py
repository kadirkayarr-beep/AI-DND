"""core_resolution and model_phase live at the engine root; the old api.* names are gone (shims removed after wave 1)."""
import importlib
import sys
import unittest

MODULES = ("core_resolution", "model_phase")


class RulesModuleIdentityTests(unittest.TestCase):
    def test_the_root_names_import(self):
        for name in MODULES:
            with self.subTest(module=name):
                self.assertEqual(importlib.import_module(name).__name__, name)

    def test_the_old_api_names_no_longer_import(self):
        for name in MODULES:
            with self.subTest(module=name):
                sys.modules.pop(f"api.{name}", None)
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(f"api.{name}")


if __name__ == "__main__":
    unittest.main()
