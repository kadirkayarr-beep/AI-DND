"""Every test that starts a new campaign runs on a fixed town, and this guard keeps it that way (roadmap row 2b)."""

from __future__ import annotations

import ast
import tempfile
import unittest
import uuid
from pathlib import Path

from api import session_manager
from api.tests.town_seed import default_town, fixed_town

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_PATHS = {"/api/game/campaigns", "/api/campaigns"}
PIN_CALLS = {"fixed_town", "default_town", "_campaign_seeded"}

# (file, function) pairs whose creation is pinned by every caller, not at the site itself.
PINNED_BY_CALLER: dict[tuple[str, str], str] = {
    ("api/tests/journeys/runner.py", "_new_journey_campaign"):
        "every caller wraps it in _campaign_seeded(setup), and test_journeys fails on an unseeded scenario",
}


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _is_pin(expr: ast.AST) -> bool:
    for node in ast.walk(expr):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in PIN_CALLS:
            return True
        if name in {"patch", "object"}:
            text = ast.unparse(node)
            if "session_manager" in text and "uuid" in text:
                return True
    return False


def _path_parameters(function: ast.AST) -> set[str]:
    args = function.args
    positional = args.posonlyargs + args.args
    named = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
    named += list(zip(args.kwonlyargs, args.kw_defaults))
    return {arg.arg for arg, default in named if isinstance(default, ast.Constant) and default.value in CAMPAIGN_PATHS}


def _is_site(call: ast.Call, functions: list[ast.AST]) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "post" and call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant):
            return first.value in CAMPAIGN_PATHS
        return isinstance(first, ast.Name) and any(first.id in _path_parameters(f) for f in functions)
    if func.attr == "create_campaign":
        receiver = ast.unparse(func.value)
        return receiver not in ("self", "cls") and "store" not in receiver and not receiver.endswith("Tests")
    return False


def _sites(root: Path, caller: dict[tuple[str, str], str]) -> list[tuple[str, bool]]:
    """Every creation site under ``root/api/tests`` as (``"<posix path>:<function>"``, pinned?)."""
    found: list[tuple[str, bool]] = []
    for path in sorted((root / "api" / "tests").rglob("*.py")):
        if path.name.startswith("live_"):
            continue
        relative = path.relative_to(root).as_posix()

        def visit(node: ast.AST, functions: list[ast.AST], pins: list[tuple[str, list[int]]]) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions = functions + [node]
                entered = [c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                           and _call_name(c) == "enterContext" and c.args and _is_pin(c.args[0])]
                pins = pins + [("enter", entered)]
            if isinstance(node, (ast.With, ast.AsyncWith)) and any(_is_pin(i.context_expr) for i in node.items):
                for child in node.body:
                    visit(child, functions, pins + [("with", [])])
                return
            if isinstance(node, ast.Call) and _is_site(node, functions):
                name = functions[-1].name if functions else "<module>"
                pinned = (relative, name) in caller or any(
                    kind == "with" or any(line < node.lineno for line in lines) for kind, lines in pins)
                found.append((f"{relative}:{name}", pinned))
            for child in ast.iter_child_nodes(node):
                visit(child, functions, pins)

        visit(ast.parse(path.read_text(encoding="utf-8")), [], [])
    return found


def unpinned_sites(root: Path, caller: dict[tuple[str, str], str] | None = None) -> tuple[list[str], int]:
    """The creation sites that run on a random town (as ``"<posix path>:<function>"``), and how many sites there are."""
    sites = _sites(root, PINNED_BY_CALLER if caller is None else caller)
    return [name for name, pinned in sites if not pinned], len(sites)


def _planted(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        tests = Path(directory) / "api" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_planted.py").write_text(source, encoding="utf-8")
        return unpinned_sites(Path(directory), {})[0]


class DefaultTown(unittest.TestCase):
    def test_alone_it_pins_the_next_campaign_id(self) -> None:
        with default_town(self, 5):
            self.assertEqual(str(session_manager.uuid.uuid4()), "00000000-0000-4000-8000-000000000005")

    def test_an_outer_pin_wins(self) -> None:
        with fixed_town(self, 7):
            with default_town(self, 5):
                self.assertEqual(str(session_manager.uuid.uuid4()), "00000000-0000-4000-8000-000000000007")

    def test_each_creation_takes_the_next_seed(self) -> None:
        with default_town(self, 5):
            first = str(session_manager.uuid.uuid4())
        with default_town(self, 5):
            second = str(session_manager.uuid.uuid4())
        self.assertEqual((first, second), ("00000000-0000-4000-8000-000000000005",
                                           "00000000-0000-4000-8000-000000000006"))

    def test_nothing_stays_patched(self) -> None:
        with default_town(self, 5):
            pass
        self.assertIs(session_manager.uuid, uuid)


class FixedTownNeedsNoRunnerTests(unittest.TestCase):
    def test_the_pin_imports_nothing_from_the_journey_runner(self) -> None:
        """The pin is a helper of its own (D-554): it must not reach for the journey runner's private function."""
        tree = ast.parse((ROOT / "api" / "tests" / "town_seed.py").read_text(encoding="utf-8"))
        modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        self.assertEqual([name for name in modules if name.startswith("api.tests.journeys.runner")], [])


class EveryNewCampaignHasAFixedTown(unittest.TestCase):
    def test_the_scan_knows_each_form(self) -> None:
        planted = _planted(
            "class A:\n"
            "    async def bare_post(self):\n"
            "        await self.client.post('/api/game/campaigns', json={})\n"
            "    async def alias(self):\n"
            "        await self.client.post('/api/campaigns', json={})\n"
            "    async def manager(self):\n"
            "        await self.manager.create_campaign(1)\n"
            "def post_character(client, path='/api/game/campaigns'):\n"
            "    return client.post(path)\n"
            "class B:\n"
            "    async def pinned(self):\n"
            "        with fixed_town(self, 1):\n"
            "            await self.client.post('/api/game/campaigns')\n"
            "    async def defaulted(self):\n"
            "        with default_town(self, 1):\n"
            "            await self.manager.create_campaign(1)\n"
            "    async def entered(self):\n"
            "        self.enterContext(fixed_town(self, 1))\n"
            "        await self.client.post('/api/game/campaigns')\n"
            "    async def store(self):\n"
            "        self.store.create_campaign(1)\n"
            "    async def helper(self):\n"
            "        await self.create_campaign()\n"
            "    async def resume(self, cid):\n"
            "        await self.client.post(f'/api/game/campaigns/{cid}/resume')\n")
        self.assertEqual(planted, ["api/tests/test_planted.py:bare_post", "api/tests/test_planted.py:alias",
                                   "api/tests/test_planted.py:manager",
                                   "api/tests/test_planted.py:post_character"])

    def test_every_caller_pinned_entry_still_creates_a_campaign(self) -> None:
        unpinned, _ = unpinned_sites(ROOT, {})
        for (relative, function), reason in PINNED_BY_CALLER.items():
            with self.subTest(relative=relative, function=function):
                self.assertTrue(reason.strip())
                self.assertTrue((ROOT / relative).is_file())
                self.assertIn(f"{relative}:{function}", unpinned)

    def test_the_scan_still_sees_every_creation(self) -> None:
        self.assertGreaterEqual(unpinned_sites(ROOT)[1], 150)

    def test_no_new_campaign_in_the_tests_runs_on_a_random_town(self) -> None:
        unpinned, _ = unpinned_sites(ROOT)
        self.assertEqual(unpinned, [], "wrap each of these creations in default_town(self, TOWN_SEED):\n"
                         + "\n".join(unpinned))


if __name__ == "__main__":
    unittest.main()
