"""Tests for the golden surface of the `game` module (scripts/engine_split/surface.py)."""
from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import game  # noqa: E402
from engine_split import routing_audit  # noqa: E402
from engine_split.surface import diff_rule, new_engine_functions, normal_signature, snapshot  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "engine_split_locks" / "surface.json"


class SurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    def test_live_surface_equals_the_golden_file(self):
        # api/main.py startup replaces three game functions in the imported module (F1), and the guarded
        # test launcher blocks child processes (B06), so run a fresh copy of game.py under the name "game".
        import importlib.util
        import types
        spec = importlib.util.spec_from_file_location("game", ROOT / "game.py")
        fresh = importlib.util.module_from_spec(spec)
        saved = sys.modules.get("game")
        # the fresh copy loads its own parts: a cached part module would still read the original engine as `game`
        saved_parts = {key: sys.modules.pop(key) for key in list(sys.modules) if key == "game_parts" or key.startswith("game_parts.")}
        sys.modules["game"] = fresh
        try:
            spec.loader.exec_module(fresh)
            live = snapshot(fresh)
        finally:
            if saved is None:
                sys.modules.pop("game", None)
            else:
                sys.modules["game"] = saved
            for key in [key for key in sys.modules if key == "game_parts" or key.startswith("game_parts.")]:
                del sys.modules[key]
            sys.modules.update(saved_parts)
        self.assertIsInstance(fresh, types.ModuleType)
        for name, value in vars(fresh).items():  # every moved function reads the fresh engine through `game`
            if isinstance(value, types.FunctionType) and (value.__module__ or "").startswith("game_parts"):
                self.assertIs(getattr(value, "__wrapped__", value).__globals__["game"], fresh, name)
        self.assertEqual(live, self.golden)

    def test_every_re_export_is_the_parts_own_object(self):
        # Task 4: proves "game.X is <part>.X" at run time (R8 proves it statically); tests may not import game_parts (R2)
        parts = {name: module for name, module in sys.modules.items() if name.startswith("game_parts.")}
        for part, names in routing_audit.re_exports(ROOT).items():
            module = parts["game_parts." + part]
            for name in names:
                own, seen = vars(module)[name], getattr(game, name)
                if inspect.isfunction(own):
                    self.assertIs(seen.__wrapped__, own, name)
                    self.assertTrue(seen._session_bound, name)
                    self.assertIn(module.__name__, game._PART_MODULES, name)
                else:
                    self.assertIs(seen, own, name)

    def test_a_missing_name_is_reported(self):
        live = dict(self.golden)
        del live["roll_d20"]
        self.assertIn("roll_d20", "\n".join(diff_rule(self.golden, live, moved=set())))

    def test_only_the_module_of_a_moved_name_may_change(self):
        live = copy.deepcopy(self.golden)
        live["roll_d20"]["module"] = "game_parts.another_part"  # T2.4: the golden now says game_parts.character_rules
        self.assertNotEqual(live["roll_d20"]["module"], self.golden["roll_d20"]["module"])
        self.assertEqual(diff_rule(self.golden, live, moved={"roll_d20"}), [])
        self.assertNotEqual(diff_rule(self.golden, live, moved=set()), [])
        live["roll_d20"]["signature"] = "(x)"
        self.assertNotEqual(diff_rule(self.golden, live, moved={"roll_d20"}), [])

    def test_losing_the_session_wrapper_is_a_violation(self):
        live = copy.deepcopy(self.golden)
        live["roll_d20"]["session_bound"] = False
        self.assertNotEqual(diff_rule(self.golden, live, moved={"roll_d20"}), [])

    def test_a_new_top_level_function_in_game_is_refused(self):
        live = copy.deepcopy(self.golden)
        live["brand_new"] = {"kind": "function", "module": "game", "signature": "()", "session_bound": True}
        self.assertEqual(new_engine_functions(self.golden, live), ["brand_new"])

    def test_an_added_name_may_not_be_a_new_function_in_game(self):  # F19
        live = copy.deepcopy(self.golden)
        live["brand_new"] = {"kind": "function", "module": "game", "signature": "()", "session_bound": True}
        self.assertNotEqual(diff_rule(self.golden, live, moved=set(), added={"brand_new"}), [])
        live["brand_new"]["module"] = "game_parts.x"
        self.assertEqual(diff_rule(self.golden, live, moved=set(), added={"brand_new"}), [])

    def test_defaults_never_put_a_path_or_address_in_the_signature(self):  # Review Focus 5
        def f(a=1, b="x", p=Path("/root/x"), fn=print, n=None): ...
        self.assertEqual(
            normal_signature(f),
            f"(a=1, b='x', p=<{type(Path()).__name__}>, fn=<builtin_function_or_method>, n=None)",
        )


if __name__ == "__main__":
    unittest.main()
