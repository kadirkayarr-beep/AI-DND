"""Tests for the N2 patch census (scripts/engine_split/patch_census.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.patch_census import (  # noqa: E402
    REPORT_PATH,
    not_called_tests,
    report,
    scan,
    targets,
)

LOCK = Path(__file__).parent / "engine_split_locks" / "patch_census.json"
SURFACE = Path(__file__).parent / "engine_split_locks" / "surface.json"
GAME_NAMES = set(json.loads(SURFACE.read_text(encoding="utf-8")))
# file -> reason: sites whose attribute name is computed and cannot be resolved (target "<dynamic>"). Empty = none allowed.
DYNAMIC_REASONS: dict[str, str] = {
    "api/tests/test_engine_module_alias.py": "setattr(game, name, ...) over every _CHARACTER_GLOBALS alias (Plan 4 Task 1); "
                                             "the aliases are session-core class properties, never moved",
}


class PatchCensusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def fixture(self, src: str, name: str = "test_fixture.py") -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src, encoding="utf-8")
        return self.tmp

    def test_the_lock_equals_a_fresh_scan(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        sites = scan(ROOT, GAME_NAMES)
        self.assertEqual(lock["targets"], targets(sites))
        unexplained = sorted({s["file"] for s in sites if s["target"] == "<dynamic>"} - set(DYNAMIC_REASONS))
        self.assertEqual(unexplained, [], "computed patch names that cannot be resolved; resolve them or list them with a reason")
        self.assertEqual(lock["not_called_tests"], not_called_tests(ROOT))

    def test_the_report_equals_a_fresh_scan(self) -> None:
        """D-427: the report went stale once while only the lock was checked."""
        if not REPORT_PATH.is_file():
            self.skipTest("docs/ is not in the slot tree; CI and the worktree run this")
        sites = scan(ROOT, GAME_NAMES)
        fresh = report(sites, targets(sites), not_called_tests(ROOT))
        self.assertEqual(REPORT_PATH.read_text(encoding="utf-8"), fresh)

    def test_an_unknown_target_is_seen(self):
        sites = scan(self.fixture("import game\nfrom unittest.mock import patch\n"
                                  "def test_x():\n    with patch.object(game, 'brand_new_helper'):\n        pass\n"), {"roll_d20"})
        self.assertEqual([s["target"] for s in sites], ["brand_new_helper"])

    def test_module_level_rebinding_outside_test_files_is_counted(self):
        sites = scan(self.fixture("import game\ngame.system_prompt = 'x'\n", name="live_integration_test.py"), {"system_prompt"})
        self.assertEqual((sites[0]["target"], sites[0]["how"], sites[0]["in_test_function"]), ("system_prompt", "assign", False))

    def test_an_unresolved_alias_is_counted_conservatively(self):
        src = "from unittest.mock import patch\ndef helper(engine):\n    return patch.object(engine, 'roll_d20')\n"
        self.assertEqual([s["target"] for s in scan(self.fixture(src), {"roll_d20"})], ["roll_d20"])

    def test_the_real_tree_lists_the_known_rebinders(self):
        found = {(Path(s["file"]).name, s["target"]) for s in scan(ROOT, GAME_NAMES)}
        for pair in [("live_integration_test.py", "system_prompt"), ("acceptance_test.py", "roll_d20"),
                     ("offline_test_support.py", "ollama"), ("test_sessions.py", "uuid4"),
                     ("test_dialogue_live_context.py", "open"), ("narrative_director.py", "finalize_narration"),
                     ("ollama_adapter.py", "ollama"), ("gameplay_audit.py", "ollama")]:
            self.assertIn(pair, found)

    def test_every_patch_form_is_counted_with_its_how(self):
        src = ("import game as g\nfrom unittest import mock\nfrom unittest.mock import patch\n"
               "def test_x(monkeypatch):\n"
               "    patch('game.a')\n    patch.object(g, 'b')\n    mock.patch.multiple(g, c=1, d=2)\n"
               "    setattr(g, 'e', 1)\n    monkeypatch.setattr('game.f', 1)\n    g.h = 1\n")
        sites = scan(self.fixture(src), set())
        self.assertEqual([(s["target"], s["how"]) for s in sites],
                         [("a", "patch_string"), ("b", "patch_object"), ("c", "patch_multiple"),
                          ("d", "patch_multiple"), ("e", "setattr"), ("f", "setattr"), ("h", "assign")])

    def test_a_nested_target_counts_for_its_first_attribute(self):
        src = "from unittest.mock import patch\nimport game\ndef test_x():\n    patch('game.ollama.chat')\n    patch.object(game.ollama, 'list')\n    game.ollama.chat = 1\n"
        sites = scan(self.fixture(src), set())
        self.assertEqual([s["target"] for s in sites], ["ollama", "ollama", "ollama"])

    def test_assignment_on_other_objects_is_not_counted(self):
        src = "def test_x(self, session):\n    self.world_state = 1\n    session.world_state = 2\n"
        self.assertEqual(scan(self.fixture(src), {"world_state"}), [])

    def test_assignment_through_engine_and_game_module_is_counted(self):
        src = "def f(engine, game_module):\n    engine.a = 1\n    game_module.b = 2\n"
        self.assertEqual([s["target"] for s in scan(self.fixture(src), set())], ["a", "b"])

    def test_docs_pycache_and_engine_split_are_skipped(self):
        src = "import game\ngame.x = 1\n"
        for name in ["docs/e/a.py", "__pycache__/a.py", "game.py", "game_parts/a.py", "scripts/engine_split/a.py"]:
            self.fixture(src, name=name)
        self.assertEqual(scan(self.tmp, set()), [])
        self.fixture(src, name="legacy_debug/a.py")
        self.assertEqual([s["file"] for s in scan(self.tmp, set())], ["legacy_debug/a.py"])

    def test_decorator_patch_counts_as_inside_the_test_function(self):
        src = "from unittest.mock import patch\n@patch('game.a')\ndef test_x(m):\n    pass\n@patch('game.b')\ndef helper(m):\n    pass\n"
        sites = scan(self.fixture(src), set())
        self.assertEqual([(s["target"], s["in_test_function"]) for s in sites], [("a", True), ("b", False)])

    def test_targets_kind_map(self):
        names = {"roll_d20": 0, "system_prompt": 0, "uuid4": 0, "ollama": 0, "GameSession": 0, "Path": 0, "open": 0}
        sites = [{"target": t} for t in names]
        self.assertEqual(targets(sites), {
            "roll_d20": "function", "system_prompt": "data", "uuid4": "import", "ollama": "import",
            "GameSession": "class", "Path": "import", "open": "absent"})

    def test_a_loop_over_literal_names_is_resolved(self):
        src = """import game
from unittest.mock import patch
def test_x(self):
    for name in ('a', 'b'):
        self.enterContext(patch.object(game, name, 1))
"""
        self.assertEqual([s["target"] for s in scan(self.fixture(src), set())], ["a", "b"])

    def test_a_loop_over_literal_pairs_is_resolved(self):
        src = """import game
from unittest.mock import patch
def test_x():
    for name, result in (("a", {}), ("b", 1)):
        patch.object(game, name, return_value=result)
"""
        self.assertEqual([s["target"] for s in scan(self.fixture(src), set())], ["a", "b"])

    def test_a_computed_name_is_recorded_as_dynamic(self):
        src = """import game
from unittest.mock import patch
def test_x(names):
    for name in names:
        patch.object(game, name, 1)
"""
        self.assertEqual([s["target"] for s in scan(self.fixture(src), set())], ["<dynamic>"])
        self.assertEqual(targets([{"target": "<dynamic>"}]), {"<dynamic>": "dynamic"})

    def test_class_and_moved_module_kinds(self):
        surface = {"f": {"kind": "function", "module": "game_parts.x"}, "C": {"kind": "class", "module": "game_parts.y"},
                   "K": {"kind": "class", "module": "game"}, "u": {"kind": "function", "module": "uuid"},
                   "Path": {"kind": "class", "module": "pathlib._local"}}
        sites = [{"target": t} for t in surface]
        self.assertEqual(targets(sites, surface), {"f": "function", "C": "class", "K": "class", "u": "import", "Path": "import"})

    def test_sites_keep_the_full_dotted_path_and_the_report_prints_it(self):
        src = """from unittest.mock import patch
import game
def test_x():
    patch('game.ollama.chat')
    patch.object(game.ollama, 'list')
    game.ollama.show = 1
    patch.object(game, 'x')
"""
        sites = scan(self.fixture(src), set())
        self.assertEqual([s["path"] for s in sites], ["game.ollama.chat", "game.ollama.list", "game.ollama.show", "game.x"])
        text = report(sites, targets(sites), [])
        for path in ("game.ollama.chat", "game.ollama.list", "game.ollama.show"):
            self.assertIn(path, text)

    def test_not_called_tests_finds_the_known_blind_spot(self):
        found = not_called_tests(ROOT)
        self.assertIn("api/tests/test_dialogue_live_context.py::test_disabled_trace_does_not_open_output_file", found)
        self.assertTrue(all("\\" not in item and not Path(item.split("::")[0]).is_absolute() for item in found))

    def test_not_called_tests_needs_a_game_patch_and_the_assertion(self):
        src = ("import game\nfrom unittest.mock import patch\n"
               "def test_a():\n    with patch.object(game, 'x') as m:\n        pass\n    m.assert_not_called()\n"
               "def test_b():\n    with patch.object(game, 'x') as m:\n        pass\n    m.assert_called()\n"
               "def test_c():\n    with patch.object(self, 'x') as m:\n        pass\n    m.assert_not_called()\n"
               "def test_d():\n    with patch('game.y'):\n        pass\n    game.y.assert_not_called()\n")
        self.assertEqual(not_called_tests(self.fixture(src)), ["test_fixture.py::test_a", "test_fixture.py::test_d"])


if __name__ == "__main__":
    unittest.main()
