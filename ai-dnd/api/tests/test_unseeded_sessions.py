"""Every test that builds a game session directly pins its dice (D-393).

``game.create_session()`` without a seed gives the session an unseeded ``rng``: any roll in the test is random, which
is how a test turns into a flake. Pass ``seed=`` (the engine's own argument). The live scripts (``live_*``) play a real
model and are not part of the suite.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from typing import TypeGuard

ROOT = Path(__file__).resolve().parents[2]
ENGINE_NAMES = {"game", "engine", "live_engine"}


def _is_unseeded_session(node: ast.AST) -> TypeGuard[ast.Call]:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_session"):
        return False
    receiver = node.func.value
    return (isinstance(receiver, ast.Name) and receiver.id in ENGINE_NAMES
            and not node.args and not any(keyword.arg == "seed" for keyword in node.keywords))


def unseeded_sessions(root: Path) -> list[str]:
    """``"<posix path>:<line>"`` of each ``<engine>.create_session()`` call under ``root/api/tests`` with no seed."""
    paths = [path for path in sorted((root / "api" / "tests").rglob("*.py")) if not path.name.startswith("live_")]
    return [f"{path.relative_to(root).as_posix()}:{node.lineno}" for path in paths
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if _is_unseeded_session(node)]


class UnseededSessionsTests(unittest.TestCase):
    def test_the_scan_knows_each_form(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory) / "api" / "tests"
            tests.mkdir(parents=True)
            (tests / "test_planted.py").write_text(
                "import game\n"
                "a = game.create_session()\n"
                "b = game.create_session(seed=5)\n"
                "c = game.create_session(5)\n"
                "d = self.create_session()\n", encoding="utf-8")
            (tests / "live_planted.py").write_text("import game\ne = game.create_session()\n", encoding="utf-8")
            self.assertEqual(unseeded_sessions(Path(directory)), ["api/tests/test_planted.py:2"])

    def test_no_test_builds_a_session_with_random_dice(self) -> None:
        self.assertEqual(unseeded_sessions(ROOT), [], "pass seed= to each of these game.create_session() calls")


if __name__ == "__main__":
    unittest.main()
