"""N4/N7 probe tools: the patch-hit ledger, the per-test outcome ledger and their diff (game.py split, Plan 2 Task 2);
the executed-lines probe and per-function counts (Task 3)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from api.tests import engine_probe, gate_boot

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split import coverage_by_function, ledger_diff  # noqa: E402
from engine_split.coverage_by_function import function_hits, unequal  # noqa: E402
from engine_split.ledger_diff import drops, lost_tests, merge_ledger, merge_outcomes, noise, sublost  # noqa: E402


def _hooks():
    return (unittest.TestCase.run, mock._patch.__enter__, mock._patch.__exit__)


def _records(out_dir: Path) -> list[dict]:
    lines = []
    for path in sorted(out_dir.glob("ledger-*.jsonl")):
        lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return lines


def _patch_records(out_dir: Path) -> list[dict]:
    return [r for r in _records(out_dir) if "target" in r]


def _fake_game() -> types.ModuleType:
    fake = types.ModuleType("game")
    fake.x = lambda: 1
    fake.y = lambda: 2
    return fake


def _write_lines(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _write_proof(run: Path, digest: str = "abc", seconds: float = 1.0) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "proof.json").write_text(json.dumps(
        {"seconds": seconds, "source_identity": {"total_digest_sha256": digest}}), encoding="utf-8")


def _cli(tool, *argv: str) -> tuple[int, list[str]]:
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = tool.main(list(argv))
    return code, printed.getvalue().split("\n")


def _diff_files(tmp: str, *datas: dict) -> list[str]:
    paths = []
    for name, data in zip("abc", datas):
        paths.append(str(Path(tmp) / f"{name}.json"))
        Path(paths[-1]).write_text(json.dumps(data), encoding="utf-8")
    return ["--diff", "--base", paths[0], "--base2", paths[1], "--new", paths[2]]


class LedgerMath(unittest.TestCase):
    def test_merge_keeps_true_over_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_lines(Path(tmp) / "ledger-1.jsonl", [
                {"test": "t", "target": "roll_d20", "kind": "mock", "called": False},
                {"test": "t", "target": "roll_d20", "kind": "mock", "called": True},
                {"test": "t", "outcome": "ok"},
            ])
            self.assertEqual(merge_ledger(Path(tmp)), {"t|roll_d20": True})

    def test_a_non_ok_outcome_wins_over_ok_for_the_same_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_lines(Path(tmp) / "ledger-1.jsonl", [
                {"test": "a", "outcome": "ok"},
                {"test": "a", "outcome": "fail"},
                {"test": "b", "outcome": "skip"},
                {"test": "b", "target": "roll_d20", "kind": "mock", "called": True},
            ])
            self.assertEqual(merge_outcomes(Path(tmp)), {"a": "fail", "b": "skip"})

    def test_noise_is_what_two_equal_runs_disagree_on(self):
        self.assertEqual(noise({"t|roll_d20": True, "u|x": True}, {"t|roll_d20": True, "u|x": False}), ["u|x"])

    def test_a_patch_that_stopped_firing_is_a_drop(self):
        self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, set()), ["t|roll_d20"])
        self.assertEqual(drops({"t|roll_d20": True}, {}, set()), ["t|roll_d20"])
        self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, {"t|roll_d20"}), [])

    def test_a_test_that_stopped_passing_is_lost(self):
        self.assertEqual(lost_tests({"a": "ok"}, {"a": "skip"}, set()), ["a"])
        self.assertEqual(lost_tests({"a": "ok"}, {}, set()), ["a"])
        self.assertEqual(lost_tests({"a": "skip"}, {}, set()), [])

    def test_a_test_that_failed_in_one_base_is_never_lost(self):
        self.assertEqual(lost_tests({"a": "ok", "b": "ok"}, {"a": "fail", "b": "fail"}, {"b"}), ["a"])

    def test_a_subtest_failed_in_new_and_in_neither_base_is_sublost(self):  # stage A review finding 1
        self.assertEqual(sublost({"t": ["t (n=1)"]}, {"t": ["t (n=2)"]},
                                 {"t": ["t (n=1)", "t (n=2)", "t (n=3)"], "u": ["u (k=1)"]}), ["t (n=3)", "u (k=1)"])
        self.assertEqual(sublost({"t": ["t (n=1)"]}, {}, {"t": ["t (n=1)"]}), [])


class LedgerCli(unittest.TestCase):
    def test_collect_merges_the_shards_of_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            for shard, seconds, called in ((0, 12.5, False), (1, 40.0, True)):
                run = Path(tmp) / f"20261118T000000-x-n4-{shard}"
                _write_lines(run / "engine-probe" / "ledger-7.jsonl", [
                    {"test": f"t{shard}", "outcome": "ok"},
                    {"test": "t", "target": "roll_d20", "kind": "mock", "called": called},
                    {"test": "s", "outcome": "fail", "subtests": [f"s (n={shard})"]},
                ])
                (run / "proof.json").write_text(json.dumps(
                    {"seconds": seconds, "source_identity": {"total_digest_sha256": "abc"}}), encoding="utf-8")
            out = Path(tmp) / "c.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = ledger_diff.main(["--collect", f"{tmp}/*-x-n4-[0-9]*", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {
                "hits": {"t|roll_d20": True}, "outcomes": {"s": "fail", "t0": "ok", "t1": "ok"},
                "subtests": {"s": ["s (n=0)", "s (n=1)"]}, "seconds": 40.0, "tree": "abc"})

    def test_the_diff_fails_on_a_drop_and_a_lost_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = {"hits": {"t|roll_d20": True, "u|x": True}, "outcomes": {"t": "ok", "u": "ok"}, "subtests": {},
                    "seconds": 1, "tree": "a"}
            base2 = {"hits": {"t|roll_d20": True, "u|x": False}, "outcomes": {"t": "ok", "u": "fail"}, "subtests": {},
                     "seconds": 1, "tree": "a"}
            new = {"hits": {"t|roll_d20": False, "u|x": False}, "outcomes": {"t": "skip", "u": "fail"}, "subtests": {},
                   "seconds": 1, "tree": "a"}
            paths = []
            for name, data in (("a", base), ("b", base2), ("c", new)):
                paths.append(Path(tmp) / f"{name}.json")
                paths[-1].write_text(json.dumps(data), encoding="utf-8")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = ledger_diff.main(["--diff", "--base", str(paths[0]), "--base2", str(paths[1]), "--new", str(paths[2])])
            self.assertEqual(code, 1)
            self.assertEqual(printed.getvalue().split("\n"), [
                "NOISE 2", "DROPS 1", "  t|roll_d20", "LOST 1", "  t", "SUBLOST 0", ""])

    def test_the_diff_fails_on_a_new_red_subtest_inside_a_test_that_was_already_red(self):  # review finding 1
        base = {"hits": {}, "outcomes": {"t": "fail"}, "subtests": {"t": ["t (n=1)"]}, "seconds": 1, "tree": "a"}
        new = {"hits": {}, "outcomes": {"t": "fail"}, "subtests": {"t": ["t (n=1)", "t (n=5)"]}, "seconds": 1, "tree": "b"}
        with tempfile.TemporaryDirectory() as tmp:
            code, printed = _cli(ledger_diff, *_diff_files(tmp, base, base, new))
        self.assertEqual(code, 1)
        self.assertEqual(printed, ["NOISE 0", "DROPS 0", "LOST 0", "SUBLOST 1", "  t (n=5)", ""])

    def test_collect_refuses_a_run_with_no_outcome_record(self):  # review finding 2: an n7-only run, a dead shard
        with tempfile.TemporaryDirectory() as tmp:
            for shard, records in ((0, [{"test": "t", "outcome": "ok"}]),
                                   (1, [{"test": "t", "target": "x", "kind": "mock", "called": True}])):
                run = Path(tmp) / f"20261118T000000-x-n4-{shard}"
                _write_lines(run / "engine-probe" / "ledger-7.jsonl", records)
                _write_proof(run)
            (Path(tmp) / "20261118T000000-x-n4-2" / "engine-probe").mkdir(parents=True)
            _write_proof(Path(tmp) / "20261118T000000-x-n4-2")
            out = Path(tmp) / "c.json"
            code, printed = _cli(ledger_diff, "--collect", f"{tmp}/*-x-n4-[0-9]*", "--out", str(out))
            self.assertEqual(code, 2)
            self.assertEqual(printed, ["NO_OUTCOMES runs=3", str(Path(tmp) / "20261118T000000-x-n4-1"),
                                       str(Path(tmp) / "20261118T000000-x-n4-2"), ""])
            self.assertFalse(out.exists())

    def test_collect_refuses_a_run_without_proof(self):  # review finding 2
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20261118T000000-x-n4-0"
            _write_lines(run / "engine-probe" / "ledger-7.jsonl", [{"test": "t", "outcome": "ok"}])
            code, printed = _cli(ledger_diff, "--collect", f"{tmp}/*-x-n4-[0-9]*", "--out", str(Path(tmp) / "c.json"))
        self.assertEqual(code, 2)
        self.assertEqual(printed, ["NO_PROOF runs=1", str(run), ""])

    def test_collect_refuses_shards_on_different_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            for shard, digest in ((0, "abc"), (1, "def")):
                run = Path(tmp) / f"20261118T000000-x-n4-{shard}"
                _write_lines(run / "engine-probe" / "ledger-7.jsonl", [{"test": f"t{shard}", "outcome": "ok"}])
                _write_proof(run, digest)
            code, printed = _cli(ledger_diff, "--collect", f"{tmp}/*-x-n4-[0-9]*", "--out", str(Path(tmp) / "c.json"))
        self.assertEqual(code, 2)
        self.assertEqual(printed, ["TREES_DIFFER", "abc", "def", ""])

    def test_the_diff_refuses_two_bases_on_different_trees(self):  # review finding 2
        base = {"hits": {}, "outcomes": {"t": "ok"}, "subtests": {}, "seconds": 1, "tree": "a"}
        with tempfile.TemporaryDirectory() as tmp:
            code, printed = _cli(ledger_diff, *_diff_files(tmp, base, dict(base, tree="z"), base))
        self.assertEqual(code, 2)
        self.assertEqual(printed, ["TREES_DIFFER", "a", "z", ""])

    def test_the_diff_refuses_two_bases_with_different_tests_and_names_them(self):  # review finding 2: a dead shard
        names = [f"t{n:02}" for n in range(25)]
        base = {"hits": {}, "outcomes": {n: "ok" for n in names}, "subtests": {}, "seconds": 1, "tree": "a"}
        base2 = dict(base, outcomes={"t00": "ok", "extra": "ok"})
        with tempfile.TemporaryDirectory() as tmp:
            code, printed = _cli(ledger_diff, *_diff_files(tmp, base, base2, base))
        self.assertEqual(code, 2)
        self.assertEqual(printed, ["KEYS_DIFFER 25", *(f"  {n}" for n in (["extra"] + names[1:])[:20]), "  ... 5 more", ""])


class PatchLedger(unittest.TestCase):
    def setUp(self):
        depth = len(engine_probe._STACK)

        def restore():          # a failed assertion must not leave a hook installed in this guarded process
            while len(engine_probe._STACK) > depth:
                engine_probe.uninstall()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(restore)
        self.tmp = Path(tmp.name)

    def test_a_record_is_written_when_the_test_body_raises(self):
        fake = _fake_game()

        class Tiny(unittest.TestCase):
            def test_tiny(self):
                with mock.patch.object(fake, "x"):
                    raise ValueError("boom")

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        self.assertEqual(_patch_records(self.tmp),
                         [{"test": Tiny("test_tiny").id(), "target": "x", "kind": "mock", "called": False}])
        self.assertIn({"test": Tiny("test_tiny").id(), "outcome": "error"}, _records(self.tmp))

    def test_a_patch_on_another_object_writes_nothing(self):
        other = types.ModuleType("other")
        other.x = lambda: 1

        class Tiny(unittest.TestCase):
            def test_tiny(self):
                with mock.patch.object(other, "x"):
                    other.x()

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        self.assertEqual(_patch_records(self.tmp), [])
        self.assertEqual(_records(self.tmp), [{"test": Tiny("test_tiny").id(), "outcome": "ok"}])

    def test_an_autospec_patch_is_kind_mock_and_a_plain_function_is_kind_other(self):
        fake = _fake_game()

        class Tiny(unittest.TestCase):
            def test_tiny(self):
                with mock.patch.object(fake, "x", autospec=True), mock.patch.object(fake, "y", new=lambda: 3):
                    fake.x()
                    fake.y()

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        tid = Tiny("test_tiny").id()
        self.assertEqual(sorted(_patch_records(self.tmp), key=lambda r: r["target"]), [
            {"test": tid, "target": "x", "kind": "mock", "called": True},
            {"test": tid, "target": "y", "kind": "other", "called": None},
        ])

    def test_uninstall_restores_the_state_before_its_own_install(self):
        first = _hooks()
        engine_probe.install_ledger(self.tmp / "outer")
        before = _hooks()
        self.assertNotEqual(before, first)
        engine_probe.install_ledger(self.tmp / "inner")
        self.assertNotEqual(_hooks(), before)
        engine_probe.uninstall()
        self.assertEqual(_hooks(), before)
        engine_probe.uninstall()
        self.assertEqual(_hooks(), first)
        with mock.patch.object(engine_probe, "_STACK", []):
            with self.assertRaises(RuntimeError):
                engine_probe.uninstall()

    def test_an_outer_ledger_still_records_after_an_inner_install_and_uninstall(self):
        fake = _fake_game()
        outer_dir, inner_dir = self.tmp / "outer", self.tmp / "inner"

        class First(unittest.TestCase):
            def test_first(self):
                with mock.patch.object(fake, "x"):
                    pass

        class Second(unittest.TestCase):
            def test_second(self):
                with mock.patch.object(fake, "x"):
                    fake.x()

        engine_probe.install_ledger(outer_dir)
        outer_hooks = _hooks()
        engine_probe.install_ledger(inner_dir)
        First("test_first").run(unittest.TestResult())
        engine_probe.uninstall()
        Second("test_second").run(unittest.TestResult())
        second = {"test": Second("test_second").id(), "target": "x", "kind": "mock", "called": True}
        self.assertIn(second, _patch_records(outer_dir))
        self.assertNotIn(second, _patch_records(inner_dir))
        self.assertIn({"test": First("test_first").id(), "target": "x", "kind": "mock", "called": False},
                      _patch_records(inner_dir))
        self.assertEqual(_hooks(), outer_hooks)
        engine_probe.uninstall()

    def test_a_patch_after_an_inner_test_run_is_filed_under_the_outer_test(self):
        fake = _fake_game()

        class Inner(unittest.TestCase):
            def test_inner(self):
                pass

        class Outer(unittest.TestCase):
            def test_outer(self):
                Inner("test_inner").run(unittest.TestResult())
                with mock.patch.object(fake, "x"):
                    pass

        engine_probe.install_ledger(self.tmp)
        Outer("test_outer").run(unittest.TestResult())
        self.assertEqual(_patch_records(self.tmp),
                         [{"test": Outer("test_outer").id(), "target": "x", "kind": "mock", "called": False}])

    def test_failed_and_errored_subtests_are_named_in_the_outcome_record(self):  # stage A review finding 1
        class Tiny(unittest.TestCase):
            def test_tiny(self):
                for n in (1, 2, 3):
                    with self.subTest(n=n):
                        self.assertNotEqual(n, 2)
                        if n == 3:
                            raise ValueError("boom")

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        tid = Tiny("test_tiny").id()
        self.assertEqual(_records(self.tmp), [{"test": tid, "outcome": "error", "subtests": [f"{tid} (n=2)", f"{tid} (n=3)"]}])

    def test_a_patch_entered_outside_any_test_is_filed_under_its_file(self):  # stage A triage T2
        fake = _fake_game()
        engine_probe.install_ledger(self.tmp)       # installed inside this test's run: the ledger's own test stack is empty
        with mock.patch.object(fake, "x"):
            fake.x()
        self.assertEqual(_patch_records(self.tmp), [
            {"test": "<outside-test>:test_engine_probe_tools.py", "target": "x", "kind": "mock", "called": True}])

    def test_a_string_patch_target_is_recorded(self):  # stage A triage T2
        fake = _fake_game()

        class Tiny(unittest.TestCase):
            def test_tiny(self):
                with mock.patch.dict(sys.modules, {"game": fake}), mock.patch("game.x"):
                    fake.x()

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        self.assertEqual(_patch_records(self.tmp),
                         [{"test": Tiny("test_tiny").id(), "target": "x", "kind": "mock", "called": True}])

    def test_a_patch_started_and_stopped_by_hand_is_recorded(self):  # stage A triage T2
        fake = _fake_game()

        class Tiny(unittest.TestCase):
            def test_tiny(self):
                patcher = mock.patch.object(fake, "x")
                patcher.start()
                self.addCleanup(patcher.stop)
                fake.x()

        engine_probe.install_ledger(self.tmp)
        Tiny("test_tiny").run(unittest.TestResult())
        self.assertEqual(_patch_records(self.tmp),
                         [{"test": Tiny("test_tiny").id(), "target": "x", "kind": "mock", "called": True}])

    def test_the_n4_token_installs_the_ledger_under_the_run_root(self):
        run_root = self.tmp / "20261118T000000-x-n4-0"
        self.assertEqual(gate_boot.boot(str(run_root), {}), {"n4"})
        self.assertTrue((run_root / "engine-probe").is_dir())


SELF_TEST_ID = 4        # never COVERAGE_ID: in an n7 shard the gate holds it (sys.monitoring reserves 0, 1, 2, 5)
TWO_FUNCTIONS = "def f():\n    a = 1\n    return a + 1\n\n\ndef g():\n    return 0\n"       # f body 2-3, g body 7


def _load(path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"n7_self_test_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FunctionCounts(unittest.TestCase):
    def test_function_hits_follow_the_function_across_files(self):
        self.assertEqual(function_hits({"game.py": [2, 3]}, {"game.py": [{"name": "f", "def_line": 1, "end": 3}]}), {"f": 2})
        self.assertEqual(function_hits({"game.py": [2], "game_parts/p.py": [5, 6]},
                                       {"game.py": [{"name": "f", "def_line": 1, "end": 3}],
                                        "game_parts/p.py": [{"name": "f", "def_line": 4, "end": 6}]}), {"f": 3})

    def test_unequal_ignores_only_the_noise_names(self):
        self.assertEqual(unequal({"f": 3, "g": 2}, {"f": 2, "g": 1}, {"g"}), ["f"])

    def test_a_moved_name_keeps_its_count_and_its_re_export_import_is_not_counted(self):
        base = function_hits({"game.py": [1, 2, 3, 5]},
                             {"game.py": [{"name": "f", "kind": "function", "def_line": 1, "end": 3},
                                          {"name": "_T", "kind": "assign", "def_line": 5, "end": 5}]})
        new = function_hits({"game.py": [1], "game_parts/p.py": [1, 3, 4, 5, 7]},
                            {"game.py": [{"name": "f", "kind": "import", "def_line": 1, "end": 1},
                                         {"name": "_T", "kind": "import", "def_line": 1, "end": 1}],
                             "game_parts/p.py": [{"name": "re", "kind": "import", "def_line": 1, "end": 1},
                                                 {"name": "f", "kind": "function", "def_line": 3, "end": 5},
                                                 {"name": "_T", "kind": "assign", "def_line": 7, "end": 7}]})
        self.assertEqual(base, {"f": 3, "_T": 1})
        self.assertEqual(new, base)


class FunctionCountsCli(unittest.TestCase):
    def test_collect_counts_the_lines_of_all_shards_on_the_given_engine_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ai-dnd"
            (root / "game_parts").mkdir(parents=True)
            (root / "game.py").write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n", encoding="utf-8")
            (root / "game_parts" / "p.py").write_text("def h():\n    return 3\n", encoding="utf-8")
            for shard, seconds, lines in ((0, 3.0, {"game.py": [2]}), (1, 9.5, {"game.py": [2, 6], "game_parts/p.py": [2]})):
                run = Path(tmp) / f"20261118T000000-x-n7-{shard}"
                (run / "engine-probe").mkdir(parents=True)
                (run / "engine-probe" / "lines-7.json").write_text(json.dumps(lines), encoding="utf-8")
                (run / "proof.json").write_text(json.dumps(
                    {"seconds": seconds, "source_identity": {"total_digest_sha256": "abc"}}), encoding="utf-8")
            out = Path(tmp) / "c.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = coverage_by_function.main(["--collect", f"{tmp}/*-x-n7-[0-9]*", "--engine-root", str(root),
                                                  "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")),
                             {"functions": {"f": 1, "g": 1, "h": 1}, "seconds": 9.5, "tree": "abc"})

    def test_the_diff_fails_on_a_function_that_ran_fewer_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, functions in (("a", {"f": 3, "g": 2, "h": 1}), ("b", {"f": 3, "g": 1, "h": 1}),
                                    ("c", {"f": 2, "g": 0, "h": 4})):
                paths.append(Path(tmp) / f"{name}.json")
                paths[-1].write_text(json.dumps({"functions": functions, "seconds": 1, "tree": "a"}), encoding="utf-8")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = coverage_by_function.main(["--diff", "--base", str(paths[0]), "--base2", str(paths[1]),
                                                  "--new", str(paths[2])])
            self.assertEqual(code, 1)
            self.assertEqual(printed.getvalue().split("\n"), ["NOISE 1", "DOWN 1", "  f", "UP 1", "  h", ""])

    def test_a_move_that_shifts_line_numbers_is_no_drop(self):
        # Before: f at game.py 1-3, a top-level `if` at 5-6. After: f's body in a part, game.py re-exports it and the
        # `if` (a line-numbered name) moved up to 3-4. Same lines ran, so nothing is DOWN or UP.
        base = function_hits({"game.py": [1, 2, 3, 5, 6]},
                             {"game.py": [{"name": "f", "kind": "function", "def_line": 1, "end": 3},
                                          {"name": "<If@5>", "kind": "other", "def_line": 5, "end": 6}]})
        new = function_hits({"game.py": [1, 3, 4], "game_parts/p.py": [1, 2, 3]},
                            {"game.py": [{"name": "f", "kind": "import", "def_line": 1, "end": 1},
                                         {"name": "<If@3>", "kind": "other", "def_line": 3, "end": 4}],
                             "game_parts/p.py": [{"name": "f", "kind": "function", "def_line": 1, "end": 3}]})
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, functions in (("a", base), ("b", base), ("c", new)):
                paths.append(Path(tmp) / f"{name}.json")
                paths[-1].write_text(json.dumps({"functions": functions, "seconds": 1, "tree": "a"}), encoding="utf-8")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = coverage_by_function.main(["--diff", "--base", str(paths[0]), "--base2", str(paths[1]),
                                                  "--new", str(paths[2])])
            self.assertEqual(printed.getvalue().split("\n"), ["NOISE 0", "DOWN 0", "UP 0", ""])
            self.assertEqual(code, 0)

    def collect(self, tmp: str, shards: dict[int, tuple[dict | None, str | None]]) -> tuple[int, list[str], Path]:
        # shard -> (lines file or None, proof digest or None) on a one-function engine root
        root = Path(tmp) / "ai-dnd"
        (root / "game_parts").mkdir(parents=True)
        (root / "game.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        for shard, (lines, digest) in shards.items():
            run = Path(tmp) / f"20261118T000000-x-n7-{shard}"
            (run / "engine-probe").mkdir(parents=True)
            if lines is not None:
                (run / "engine-probe" / "lines-7.json").write_text(json.dumps(lines), encoding="utf-8")
            if digest is not None:
                _write_proof(run, digest)
        out = Path(tmp) / "c.json"
        code, printed = _cli(coverage_by_function, "--collect", f"{tmp}/*-x-n7-[0-9]*", "--engine-root", str(root),
                             "--out", str(out))
        return code, printed, out

    def test_collect_refuses_a_run_without_a_lines_file(self):  # stage A triage T3
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, out = self.collect(tmp, {0: ({"game.py": [2]}, "abc"), 1: (None, "abc")})
            self.assertEqual((code, printed), (2, ["NO_LINES runs=2", str(Path(tmp) / "20261118T000000-x-n7-1"), ""]))
            self.assertFalse(out.exists())

    def test_collect_refuses_a_run_without_proof(self):  # stage A review finding 2
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, _ = self.collect(tmp, {0: ({"game.py": [2]}, "abc"), 1: ({"game.py": [2]}, None)})
            self.assertEqual((code, printed), (2, ["NO_PROOF runs=2", str(Path(tmp) / "20261118T000000-x-n7-1"), ""]))

    def test_collect_refuses_shards_on_different_trees(self):  # stage A triage T3
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, _ = self.collect(tmp, {0: ({"game.py": [2]}, "abc"), 1: ({"game.py": [2]}, "def")})
        self.assertEqual((code, printed), (2, ["TREES_DIFFER", "abc", "def", ""]))

    def test_collect_refuses_a_lines_file_that_names_a_file_outside_the_engine_root(self):  # stage A triage T3
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, out = self.collect(tmp, {0: ({"game.py": [2], "src/ai-dnd/game.py": [2]}, "abc")})
            self.assertEqual((code, printed), (2, ["UNKNOWN_FILE", "src/ai-dnd/game.py", ""]))
            self.assertFalse(out.exists())

    def test_collect_refuses_a_run_that_counts_no_function(self):  # stage A review finding 2
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, out = self.collect(tmp, {0: ({}, "abc")})
            self.assertEqual((code, printed), (2, ["NO_FUNCTIONS", ""]))
            self.assertFalse(out.exists())

    def test_the_diff_refuses_two_bases_on_different_trees(self):  # stage A review finding 2
        with tempfile.TemporaryDirectory() as tmp:
            base = {"functions": {"f": 1}, "seconds": 1, "tree": "a"}
            code, printed = _cli(coverage_by_function, *_diff_files(tmp, base, dict(base, tree="z"), base))
        self.assertEqual((code, printed), (2, ["TREES_DIFFER", "a", "z", ""]))


class LineProbe(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(engine_probe.stop_lines, SELF_TEST_ID)     # runs before tmp.cleanup (LIFO)
        self.tmp = Path(tmp.name)
        self.path = self.tmp / "mod.py"
        self.path.write_text(TWO_FUNCTIONS, encoding="utf-8")
        self.module = _load(self.path)

    def test_only_the_lines_of_a_called_function_are_recorded(self):
        engine_probe.install_lines(self.tmp / "probe", [self.path], tool_id=SELF_TEST_ID)
        self.module.f()
        self.assertEqual(engine_probe.stop_lines(SELF_TEST_ID), {"mod.py": [2, 3]})

    def test_the_exit_writer_writes_the_lines_file_and_stop_unregisters_it(self):
        with mock.patch.object(engine_probe.atexit, "register") as register, \
                mock.patch.object(engine_probe.atexit, "unregister") as unregister:
            engine_probe.install_lines(self.tmp / "probe", [self.path], tool_id=SELF_TEST_ID)
            self.module.g()
            writer = register.call_args.args[0]
            writer()
            engine_probe.stop_lines(SELF_TEST_ID)
        unregister.assert_called_once_with(writer)
        written = list((self.tmp / "probe").glob("lines-*.json"))
        self.assertEqual([p.name for p in written], [f"lines-{os.getpid()}.json"])
        self.assertEqual(json.loads(written[0].read_text(encoding="utf-8")), {"mod.py": [7]})

    def test_a_second_install_is_an_error_not_silence(self):
        engine_probe.install_lines(self.tmp / "a", [self.path], tool_id=SELF_TEST_ID)
        with self.assertRaisesRegex(RuntimeError, "engine-split-n7 already installed"):
            engine_probe.install_lines(self.tmp / "b", [self.path], tool_id=SELF_TEST_ID)
        self.module.f()
        self.assertEqual(engine_probe.stop_lines(SELF_TEST_ID), {"mod.py": [2, 3]})

    def test_the_n7_token_installs_the_line_probe(self):
        run_root = self.tmp / "20261118T000000-x-n7-0"
        self.assertEqual(gate_boot.boot(str(run_root), {}, tool_id=SELF_TEST_ID), {"n7"})
        self.assertEqual(sys.monitoring.get_tool(SELF_TEST_ID), "engine-split-n7")
        self.assertTrue((run_root / "engine-probe").is_dir())

    def test_a_self_test_probe_leaves_the_gate_probe_running(self):
        outer = sys.monitoring.COVERAGE_ID
        holder = sys.monitoring.get_tool(outer)
        if holder is not None:
            self.skipTest(f"tool id {outer} is held by {holder!r}: the gate itself is the outer probe here")
        engine_probe.install_lines(self.tmp / "gate", [self.path], tool_id=outer)
        self.addCleanup(engine_probe.stop_lines, outer)
        # the three self-test patterns on the free id, while the outer probe runs
        engine_probe.install_lines(self.tmp / "inner", [self.path], tool_id=SELF_TEST_ID)
        with self.assertRaises(RuntimeError):
            engine_probe.install_lines(self.tmp / "inner2", [self.path], tool_id=SELF_TEST_ID)
        self.module.g()
        self.assertEqual(engine_probe.stop_lines(SELF_TEST_ID), {"mod.py": [7]})
        gate_boot.boot(str(self.tmp / "20261118T000000-x-n7-0"), {}, tool_id=SELF_TEST_ID)
        engine_probe.stop_lines(SELF_TEST_ID)
        self.assertEqual(sys.monitoring.get_tool(outer), "engine-split-n7")
        self.module.f()
        self.assertEqual(engine_probe.stop_lines(outer), {"mod.py": [2, 3, 7]})


if __name__ == "__main__":
    unittest.main()
