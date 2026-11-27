"""D-445 / D-492: the engine header may not collect unused imports or orphan notes.

game.py re-exports its moved names on purpose (the `game.<name>` surface, D-343);
every such name is recorded in engine_split_locks/surface.json. An import that
nothing reads and that is not on the surface is dead and must go. The same
holds for every game_parts module. One import is kept on purpose (S27, owner
answer a, overruled where an engine lock needs it): `import game`. test_engine_routing
(R2, R13) wants it in the __main__ guard and in game_parts/__init__.py, and
test_engine_surface wants `game` in the globals of every part that holds a moved function.
"""
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE = json.loads((Path(__file__).parent / "engine_split_locks" / "surface.json").read_text(encoding="utf-8"))
BANNER = "# ---------------------------------------------------------"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def unused_imports(path: Path) -> list[tuple[str, int]]:
    """Imports nothing reads, except the engine hook `import game` (see the module note)."""
    tree = ast.parse(_text(path))
    read = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound not in {"*", "game"} and bound not in read:
                    found.append((bound, node.lineno))
    return found


def empty_banners(lines: list[str]) -> list[str]:
    titles = []
    for i, line in enumerate(lines[:-2]):
        if line == BANNER and lines[i + 2] == BANNER and lines[i + 1].startswith("# "):
            after = i + 3
            while after < len(lines) and not lines[after].strip():
                after += 1
            if after >= len(lines) or lines[after] == BANNER:
                titles.append(lines[i + 1])
    return titles


class GameHeaderGateTests(unittest.TestCase):
    def test_game_py_unused_imports_are_all_on_the_recorded_surface(self):
        stray = [(name, line) for name, line in unused_imports(ROOT / "game.py") if name not in SURFACE]
        self.assertEqual(stray, [])

    def test_game_parts_modules_have_no_unused_imports(self):
        stray = {p.name: unused_imports(p) for p in sorted((ROOT / "game_parts").glob("*.py")) if unused_imports(p)}
        self.assertEqual(stray, {})

    def test_the_gate_flags_an_unlisted_unused_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.py"
            sample.write_text("import os\nimport sys\nprint(sys.argv)\n", encoding="utf-8")
            self.assertEqual(unused_imports(sample), [("os", 1)])

    def test_game_py_has_no_empty_section_banners(self):
        self.assertEqual(empty_banners(_text(ROOT / "game.py").split("\n")), [])

    def test_security_note_sits_directly_above_untrusted_player_block(self):
        lines = _text(ROOT / "game_parts" / "text_rules_a.py").split("\n")
        at = next(i for i, line in enumerate(lines) if line.startswith("def _untrusted_player_block"))
        above = lines[max(0, at - 12):at]
        self.assertTrue(any(line.startswith("# SECURITY: LLM01/LLM07") for line in above), above)
        self.assertNotIn("# SECURITY: LLM01/LLM07", _text(ROOT / "game.py"))
