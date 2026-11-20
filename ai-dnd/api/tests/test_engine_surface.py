"""Tests for the golden surface of the `game` module (scripts/engine_split/surface.py)."""
from __future__ import annotations

import ast
import contextlib
import copy
import inspect
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import game  # noqa: E402
from api.tests import engine_sources  # noqa: E402
from engine_split import inventory, routing_audit  # noqa: E402
from engine_split.inventory import top_level_index  # noqa: E402
from engine_split.move_block import MOVABLE_KINDS, NEVER_MOVED, MoveRefused, prefix_names  # noqa: E402
from engine_split.surface import diff_rule, new_engine_functions, normal_signature, snapshot  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "engine_split_locks" / "surface.json"
SENSITIVE_PATH = Path(__file__).parent / "engine_split_locks" / "sensitive.json"
CENSUS_PATH = Path(__file__).parent / "engine_split_locks" / "patch_census.json"
# Plan 2 batch file -> the part it moves into, in move order (Tasks 9-14)
T3_BATCHES = {"tables": "tables", "schemas": "schemas", "text-a1": "text_rules_a", "text-a2": "text_rules_a",
              "text-b1": "text_rules_b", "text-b2": "text_rules_b"}
# Plan 3 batch file -> the part it moves into, in move order (Tasks 7-15)
T4_BATCHES = {"cr": "character_rules", "places-1": "places", "places-2": "places", "intent-1": "intent",
              "intent-2": "intent", "schemas-options": "schemas", "dialogue-1": "dialogue",
              "dialogue-2": "dialogue", "lore": "lore", "narration": "narration", "nsafety-1": "narration_safety",
              "nsafety-2": "narration_safety", "lwt": "living_world_turn", "newgame": "new_game"}


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
        self.assert_surface(live)

    def assert_surface(self, live):
        # exact equality as before; the message is diff_rule's lines (every missing, new and changed name)
        if live != self.golden:
            self.fail("\n".join(diff_rule(self.golden, live, moved=set())) or "the surface differs from surface.json")

    def test_a_missing_re_export_is_named_in_the_failure(self):
        # D-351: the failure names the lost name (diff_rule lines), not a dict diff cut at maxDiff
        live = copy.deepcopy(self.golden)
        del live["_inside_speech"]
        with self.assertRaises(AssertionError) as caught:
            self.assert_surface(live)
        self.assertIn("missing: _inside_speech", str(caught.exception))

    def test_every_re_export_is_the_parts_own_object(self):
        # Task 4: proves "game.X is <part>.X" at run time (R8 proves it statically); tests may not import game_parts (R2)
        parts = {name: module for name, module in sys.modules.items() if name.startswith("game_parts.")}
        re_exports = routing_audit.re_exports(ROOT)
        self.assertTrue(re_exports)     # zero re-exports would pass with zero iterations (stage A review finding 9)
        for part, names in re_exports.items():
            module = parts["game_parts." + part]
            for name in names:
                own, seen = vars(module)[name], getattr(game, name)
                if inspect.isfunction(own):
                    self.assertIs(seen.__wrapped__, own, name)
                    self.assertTrue(seen._session_bound, name)
                    self.assertIn(module.__name__, game._PART_MODULES, name)
                else:
                    self.assertIs(seen, own, name)

    def test_t3_batches_are_movable(self):
        # Plan 2 T3 batches (Tasks 9-14) against game.py before each move; a moved batch is checked by its re-exports
        self._batches_are_movable(T3_BATCHES)

    def _batches_are_movable(self, batches):  # one set of rules for the T3 and the T4 test (Plan 3 Task 4, D-364)
        game_py = ROOT / "game.py"
        index = top_level_index(game_py)
        entries: dict[str, list[dict]] = {}
        for entry in index:
            entries.setdefault(entry["name"], []).append(entry)
        re_exports = routing_audit.re_exports(ROOT)
        sensitive = set(json.loads(SENSITIVE_PATH.read_text(encoding="utf-8"))["functions"])
        census = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))["targets"]
        surface_targets = {name for name, kind in census.items() if kind != "absent"}
        # engine names as move_block.move() builds them (preflight finding 5: module imports are not engine names)
        engine_names = ({e["name"] for e in index if e["kind"] in MOVABLE_KINDS}
                        | {n for names in re_exports.values() for n in names} | surface_targets)
        game_lines = game_py.read_text(encoding="utf-8").split("\n")
        # directed edges of inventory.constant_clusters: which top-level statement's value reads which names
        reads = [(node.lineno, {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)},
                  set(inventory.bound_names(node)[1]))
                 for node in ast.parse("\n".join(game_lines)).body
                 if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None]
        seen: dict[str, str] = {}
        part_constants: dict[str, set[str]] = {}
        for batch, part in batches.items():
            names = engine_sources.batch_names(batch)
            moved = set(re_exports.get(part, []))
            part_py = ROOT / "game_parts" / f"{part}.py"
            if part_py.exists():
                part_constants.setdefault(part, set()).update(
                    e["name"] for e in top_level_index(part_py) if e["kind"] == "assign")
            for name in names:
                with self.subTest(batch=batch, name=name):
                    self.assertNotIn(name, NEVER_MOVED)
                    self.assertNotIn(name, sensitive)
                    self.assertNotIn(name, seen)
                    seen[name] = batch
                    if name not in moved:
                        self.assertEqual([e["kind"] in MOVABLE_KINDS for e in entries.get(name, [])], [True])
            staying = [n for n in names if n not in moved and n in entries]
            if not staying:
                continue
            constants = {n for n in staying if entries[n][0]["kind"] == "assign"}
            keep_bare = (part_constants.get(part, set()) | constants) - surface_targets
            for name in sorted(constants):  # the mover's F6: a batch constant reads no engine name left in game.py
                entry = entries[name][0]
                block = "\n".join(game_lines[entry["start"] - 1:entry["end"]]) + "\n"
                with self.subTest(batch=batch, constant=name):
                    try:
                        prefix_names(block, engine_names, keep_bare)
                    except MoveRefused as refused:
                        self.fail(f"{batch}: {refused}")
            # unreachable through import order; kept as a guard
            first_cut = min(entries[n][0]["start"] for n in staying)  # the re-export line takes its place
            for line, read, bound in reads:
                if bound & set(names) or not read & set(staying):
                    continue
                with self.subTest(batch=batch, staying=sorted(bound)):
                    self.assertGreater(line, first_cut, f"{sorted(bound)} reads {sorted(read & set(staying))} "
                                                        f"above the first cut block of {batch}")
            part_constants.setdefault(part, set()).update(constants)

    def test_surface_diff_is_silent_when_clean(self):  # D-364: no finding, no output (not even an empty line)
        from engine_split import surface
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps(self.golden), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = surface.main(["--diff", "--old", str(path), "--new", str(path)])
        self.assertEqual((code, out.getvalue()), (0, ""))

    def test_t4_batches_are_movable(self):
        # Plan 3 T4 batches (Tasks 7-15), same rules as the T3 test
        self._batches_are_movable(T4_BATCHES)

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
