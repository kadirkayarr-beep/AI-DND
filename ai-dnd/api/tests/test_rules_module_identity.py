"""core_resolution and model_phase live at the engine root; the old api.* names are the same module objects."""
import importlib
import unittest
from unittest import mock

MODULES = ("core_resolution", "model_phase")


class RulesModuleIdentityTests(unittest.TestCase):
    def pair(self, name):
        return importlib.import_module(name), importlib.import_module(f"api.{name}")

    def test_both_names_are_one_module_object(self):
        for name in MODULES:
            with self.subTest(module=name):
                root, old = self.pair(name)
                self.assertIs(root, old)

    def test_a_patch_through_either_name_reaches_the_other(self):
        targets = {"core_resolution": "roll_d20", "model_phase": "in_front_call"}
        for name, attr in targets.items():
            root, old = self.pair(name)
            for patched, seen in ((old, root), (root, old)):
                with self.subTest(module=name, patched=patched.__name__):
                    sentinel = object()
                    with mock.patch.object(patched, attr, sentinel):
                        self.assertIs(getattr(seen, attr), sentinel)

    def test_a_context_variable_set_through_one_name_is_read_through_the_other(self):
        root, old = self.pair("core_resolution")
        token = old._ACTIVE_ACTION.set("probe")
        try:
            self.assertEqual(root._ACTIVE_ACTION.get(), "probe")
        finally:
            old._ACTIVE_ACTION.reset(token)
        root_phase, old_phase = self.pair("model_phase")
        with old_phase.front_call():
            self.assertTrue(root_phase.in_front_call())
        with root_phase.repair_call():
            self.assertTrue(old_phase.in_repair_call())


if __name__ == "__main__":
    unittest.main()
