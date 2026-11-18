"""N4 probe tools: the patch-hit ledger, the per-test outcome ledger and their diff (game.py split, Plan 2 Task 2)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from api.tests import engine_probe, gate_boot

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split import ledger_diff  # noqa: E402
from engine_split.ledger_diff import drops, lost_tests, merge_ledger, merge_outcomes, noise  # noqa: E402


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


class LedgerCli(unittest.TestCase):
    def test_collect_merges_the_shards_of_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            for shard, seconds, called in ((0, 12.5, False), (1, 40.0, True)):
                run = Path(tmp) / f"20261118T000000-x-n4-{shard}"
                _write_lines(run / "engine-probe" / "ledger-7.jsonl", [
                    {"test": f"t{shard}", "outcome": "ok"},
                    {"test": "t", "target": "roll_d20", "kind": "mock", "called": called},
                ])
                (run / "proof.json").write_text(json.dumps(
                    {"seconds": seconds, "source_identity": {"total_digest_sha256": "abc"}}), encoding="utf-8")
            out = Path(tmp) / "c.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = ledger_diff.main(["--collect", f"{tmp}/*-x-n4-[0-9]*", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {
                "hits": {"t|roll_d20": True}, "outcomes": {"t0": "ok", "t1": "ok"}, "seconds": 40.0, "tree": "abc"})

    def test_the_diff_fails_on_a_drop_and_a_lost_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = {"hits": {"t|roll_d20": True, "u|x": True}, "outcomes": {"t": "ok", "u": "ok"}, "seconds": 1, "tree": "a"}
            base2 = {"hits": {"t|roll_d20": True, "u|x": False}, "outcomes": {"t": "ok", "u": "fail"}, "seconds": 1, "tree": "a"}
            new = {"hits": {"t|roll_d20": False, "u|x": False}, "outcomes": {"t": "skip", "u": "fail"}, "seconds": 1, "tree": "a"}
            paths = []
            for name, data in (("a", base), ("b", base2), ("c", new)):
                paths.append(Path(tmp) / f"{name}.json")
                paths[-1].write_text(json.dumps(data), encoding="utf-8")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = ledger_diff.main(["--diff", "--base", str(paths[0]), "--base2", str(paths[1]), "--new", str(paths[2])])
            self.assertEqual(code, 1)
            self.assertEqual(printed.getvalue().split("\n"), [
                "NOISE 2", "DROPS 1", "  t|roll_d20", "LOST 1", "  t", ""])


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

    def test_the_n4_token_installs_the_ledger_under_the_run_root(self):
        run_root = self.tmp / "20261118T000000-x-n4-0"
        self.assertEqual(gate_boot.boot(str(run_root), {}), {"n4"})
        self.assertTrue((run_root / "engine-probe").is_dir())


if __name__ == "__main__":
    unittest.main()
