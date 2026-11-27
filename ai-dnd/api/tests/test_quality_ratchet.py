"""Quality gate ratchet core: line-free keys, counts, shrink-only baselines."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

BS = chr(92)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from quality_gate import ratchet  # noqa: E402
from quality_gate.ratchet import (  # noqa: E402
    ToolOutputError,
    baseline_growth,
    compare,
    count_findings,
    finding_key,
    load_baseline,
    parse_radon,
    parse_ruff,
)


def ruff_report(line: int, path: str = "a/b.py", crlf: bool = False) -> str:
    item = {
        "code": "F401",
        "message": "`os` imported but unused",
        "filename": path,
        "location": {"row": line, "column": 1},
    }
    text = json.dumps([item], indent=2)
    return text.replace("\n", "\r\n") if crlf else text


class RatchetCompareTests(unittest.TestCase):
    def test_line_shift_is_not_new(self):
        base = count_findings(parse_ruff(ruff_report(10)))
        cur = count_findings(parse_ruff(ruff_report(90)))
        self.assertEqual(compare(base, cur), [])

    def test_second_identical_finding_is_new(self):
        k = finding_key("ruff", "a/b.py", "F401", "os")
        msgs = compare({k: 1}, {k: 2})
        self.assertEqual(len(msgs), 1)
        self.assertIn(k, msgs[0])

    def test_new_key_fails_and_fixed_key_passes(self):
        old = finding_key("ruff", "a.py", "F401", "os")
        new = finding_key("ruff", "b.py", "F401", "sys")
        self.assertEqual(len(compare({old: 1}, {old: 1, new: 1})), 1)
        self.assertEqual(compare({old: 1}, {}), [])

    def test_windows_path_and_crlf_same_key(self):
        self.assertEqual(
            finding_key("ruff", "a" + BS + "b.py", "F401", "os"),
            finding_key("ruff", "a/b.py", "F401", "os"),
        )
        self.assertEqual(finding_key("ruff", "./a/b.py", "F401", "os"), "ruff|a/b.py|F401|os")
        self.assertEqual(
            parse_ruff(ruff_report(3, crlf=True)),
            parse_ruff(ruff_report(3, path="a" + BS + "b.py")),
        )

    def test_empty_or_garbage_output_is_an_error(self):
        for bad in ("", "   \n", "Traceback (most recent call last): boom"):
            with self.assertRaises(ToolOutputError):
                parse_ruff(bad)
        self.assertEqual(parse_ruff("[]"), [])


class RatchetAbsolutePathTests(unittest.TestCase):
    def keys(self, path: str, root: str) -> list[str]:
        return parse_ruff(ruff_report(1, path=path), root=root)

    def test_absolute_windows_and_linux_paths_give_same_key(self):
        win = self.keys("C:" + BS + "Work" + BS + "ai-dnd" + BS + "a" + BS + "b.py", "C:/Work/ai-dnd")
        lin = self.keys("/home/runner/w/ai-dnd/a/b.py", "/home/runner/w/ai-dnd")
        self.assertEqual(win, lin)
        self.assertEqual(win, ["ruff|a/b.py|F401|os"])

    def test_windows_root_is_case_insensitive(self):
        self.assertEqual(self.keys("c:/work/AI-DND/a/b.py", "C:/Work/ai-dnd"), ["ruff|a/b.py|F401|os"])

    def test_path_outside_root_stays_absolute(self):
        self.assertEqual(self.keys("/other/x.py", "/home/r/ai-dnd"), ["ruff|/other/x.py|F401|os"])

    def test_non_dict_item_is_tool_error(self):
        with self.assertRaises(ToolOutputError):
            parse_ruff("[1, 2]")


class RatchetCliTests(unittest.TestCase):
    def run_cli(self, mode: str, tool: str, report: Path, base_dir: Path):
        """In-process: the test slot blocks child processes."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ratchet.main([mode, tool, str(report), "--baseline-dir", str(base_dir)])
        return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())

    def test_update_refuses_to_grow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = tmp / "r.json"
            base_dir = tmp / "baselines"
            base_dir.mkdir()
            report.write_text(ruff_report(1), encoding="utf-8")
            self.assertEqual(self.run_cli("update", "ruff", report, base_dir).returncode, 0)
            target = base_dir / "ruff.json"
            before = target.read_bytes()
            two = json.loads(ruff_report(1)) * 2
            report.write_text(json.dumps(two), encoding="utf-8")
            res = self.run_cli("update", "ruff", report, base_dir)
            self.assertEqual(res.returncode, 3)
            self.assertIn("baseline may only shrink", res.stdout + res.stderr)
            self.assertEqual(target.read_bytes(), before)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = tmp / "r.json"
            base_dir = tmp / "baselines"
            base_dir.mkdir()
            report.write_text(ruff_report(1), encoding="utf-8")
            self.run_cli("update", "ruff", report, base_dir)
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 0)
            report.write_text(ruff_report(1, path="new.py"), encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 1)
            report.write_text("", encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 2)

    def test_missing_report_file_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(self.run_cli("check", "ruff", tmp / "nope.json", tmp).returncode, 2)

    def test_corrupt_baseline_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "ruff.json").write_text("{not json", encoding="utf-8")
            rep = tmp / "r.json"
            rep.write_text("[]", encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", rep, tmp).returncode, 2)
            self.assertEqual(self.run_cli("update", "ruff", rep, tmp).returncode, 2)

    def test_ruff_key_ignores_line_numbers_in_message(self):
        def key(msg):
            rep = json.dumps([{"filename": "a.py", "code": "F811", "message": msg}])
            return ratchet.parse_ruff(rep, root="/r")
        self.assertEqual(
            key("Redefinition of unused `x` from line 3"),
            key("Redefinition of unused `x` from line 40"),
        )
        self.assertEqual(key("Unquoted thing at line 3"), key("Unquoted thing at line 40"))

    def test_baseline_io_is_sorted_lf_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "b.json"
            ratchet.write_baseline(p, {"b": 1, "a": 2})
            raw = p.read_bytes()
            self.assertNotIn(b"\r", raw)
            self.assertLess(raw.index(b'"a"'), raw.index(b'"b"'))
            self.assertEqual(ratchet.load_baseline(p), {"a": 2, "b": 1})


class BaselineShrinkTests(unittest.TestCase):
    def test_growth_is_listed(self):
        out = baseline_growth({"a": 1, "b": 2}, {"a": 2, "b": 2, "c": 1})
        self.assertEqual(len(out), 2)
        self.assertIn("a", out[0])
        self.assertIn("c", out[1])

    def test_shrink_and_equal_pass(self):
        self.assertEqual(baseline_growth({"a": 2, "b": 1}, {"a": 1, "b": 1}), [])
        self.assertEqual(baseline_growth({"a": 2}, {}), [])

    def test_first_introduction_passes(self):
        self.assertEqual(baseline_growth({}, {}), [])


class CheckShrinkCliTests(unittest.TestCase):
    def run_cli(self, new_counts, git_result):
        """git is mocked: the test slot blocks child processes."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ruff.json"
            f.write_text(json.dumps(new_counts), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(ratchet.subprocess, "run", return_value=git_result) as run, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = ratchet.main(["check-shrink", str(f), "origin/main"])
            return code, out.getvalue() + err.getvalue(), run

    @staticmethod
    def git(code, out="", err=""):
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def test_growth_exits_1(self):
        code, text, run = self.run_cli({"a": 2}, self.git(0, '{"a": 1}'))
        self.assertEqual(code, 1)
        self.assertIn("a", text)
        self.assertIn("origin/main:", " ".join(run.call_args[0][0]))

    def test_shrink_exits_0(self):
        self.assertEqual(self.run_cli({"a": 1}, self.git(0, '{"a": 2}'))[0], 0)

    def test_file_absent_at_base_is_first_introduction(self):
        err = "fatal: path 'x/ruff.json' exists on disk, but not in 'origin/main'"
        self.assertEqual(self.run_cli({"a": 5}, self.git(128, "", err))[0], 0)
        err2 = "fatal: path 'x/ruff.json' does not exist in 'origin/main'"
        self.assertEqual(self.run_cli({"a": 5}, self.git(128, "", err2))[0], 0)

    def test_other_git_error_exits_2(self):
        err = "fatal: invalid object name 'origin/main'."
        self.assertEqual(self.run_cli({"a": 1}, self.git(128, "", err))[0], 2)

    def test_garbage_base_content_exits_2(self):
        self.assertEqual(self.run_cli({"a": 1}, self.git(0, "{not json"))[0], 2)

    def test_non_object_base_content_exits_2(self):
        for body in ("[1, 2]", "null", '{"a": null}', '{"a": [1]}'):
            self.assertEqual(self.run_cli({"a": 1}, self.git(0, body))[0], 2, body)

    def test_non_int_or_negative_base_counts_exit_2(self):
        for body in ('{"a": 1.9}', '{"a": true}', '{"a": "3"}', '{"a": -1}'):
            self.assertEqual(self.run_cli({"a": 1}, self.git(0, body))[0], 2, body)

    def test_git_missing_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "r.json"
            f.write_text("{}", encoding="utf-8")
            with mock.patch.object(ratchet.subprocess, "run", side_effect=OSError("no git")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ratchet.main(["check-shrink", str(f), "origin/main"]), 2)


# Excerpts of real reports (knip 6.48.0 `--reporter json`, fallow 3.45.0 `dead-code --format json`),
# measured 2026-11-24 on this repo; verbose fields trimmed.
KNIP_REAL = json.dumps({"issues": [
    {"file": "artifacts/ai-dnd-experience/src/local-play-main.tsx",
     "files": [{"name": "artifacts/ai-dnd-experience/src/local-play-main.tsx"}]},
    {"file": "artifacts/ai-dnd-experience/src/lib/account-session.ts",
     "exports": [{"namespace": "account", "name": "clearAccountStorage", "line": 47, "col": 17, "pos": 1246}]},
    {"file": "package.json",
     "dependencies": [{"name": "@replit/connectors-sdk", "line": 13, "col": 6, "pos": 419}],
     "devDependencies": [{"name": "prettier", "line": 16, "col": 6, "pos": 486}]},
]})
FALLOW_REAL = json.dumps({
    "kind": "dead-code", "schema_version": 11,
    "unused_files": [{"path": "artifacts/ai-dnd-experience/src/components/ui/accordion.tsx",
                      "effective_severity": "error"}],
    "unused_exports": [{"path": "artifacts/ai-dnd-experience/src/components/action-economy-panel.tsx",
                        "export_name": "RageControl", "is_type_only": False, "line": 9}],
    "unlisted_dependencies": [{"package_name": "@assets/generated_images",
                               "imported_from": [{"path": "artifacts/ai-dnd-experience/src/components/character-creation-screen.tsx",
                                                  "line": 59, "col": 7}]}],
    "next_steps": [{"id": "setup", "command": "fallow agent install --dry-run"}],
})


class KnipFallowParserTests(unittest.TestCase):
    def test_knip_real_shape_keys(self):
        self.assertEqual(sorted(ratchet.parse_knip(KNIP_REAL)), sorted([
            "knip|artifacts/ai-dnd-experience/src/local-play-main.tsx|files|artifacts/ai-dnd-experience/src/local-play-main.tsx",
            "knip|artifacts/ai-dnd-experience/src/lib/account-session.ts|exports|clearAccountStorage",
            "knip|package.json|dependencies|@replit/connectors-sdk",
            "knip|package.json|devDependencies|prettier",
        ]))

    def test_knip_other_categories_have_stable_keys(self):
        # Shapes from knip's documented JSON reporter, NOT from a real artifact (none had these categories).
        report = json.dumps({"issues": [
            {"file": "a.ts", "types": [{"name": "T", "line": 3}],
             "unlisted": [{"name": "left-pad", "line": 1}],
             "unresolved": [{"name": "./gone", "line": 2}],
             "catalog": [{"name": "react", "line": 4}],
             "duplicates": [[{"name": "foo", "line": 5}, {"name": "bar", "line": 6}]],
             "enumMembers": {"Color": [{"name": "Red", "line": 7}]}},
        ]})
        moved = report.replace('"line": 3', '"line": 30').replace('"line": 5', '"line": 50').replace('"line": 7', '"line": 70')
        self.assertEqual(sorted(ratchet.parse_knip(report)), sorted([
            "knip|a.ts|types|T", "knip|a.ts|unlisted|left-pad", "knip|a.ts|unresolved|./gone",
            "knip|a.ts|catalog|react", "knip|a.ts|duplicates|bar+foo", "knip|a.ts|enumMembers.Color|Red",
        ]))
        self.assertEqual(sorted(ratchet.parse_knip(moved)), sorted(ratchet.parse_knip(report)))

    def test_knip_moved_line_keeps_key(self):
        moved = KNIP_REAL.replace('"line": 47', '"line": 99').replace('"pos": 1246', '"pos": 5000')
        self.assertEqual(sorted(ratchet.parse_knip(moved)), sorted(ratchet.parse_knip(KNIP_REAL)))

    def test_knip_clean_run_is_empty_list_not_error(self):
        self.assertEqual(ratchet.parse_knip('{"issues": []}'), [])

    def test_knip_bad_output_is_error(self):
        for bad in ("", "  ", "{}", "[]", "not json", '{"issues": 3}'):
            with self.assertRaises(ToolOutputError, msg=repr(bad)):
                ratchet.parse_knip(bad)

    def test_fallow_real_shape_keys(self):
        self.assertEqual(sorted(ratchet.parse_fallow(FALLOW_REAL)), sorted([
            "fallow|artifacts/ai-dnd-experience/src/components/ui/accordion.tsx|unused_files|",
            "fallow|artifacts/ai-dnd-experience/src/components/action-economy-panel.tsx|unused_exports|RageControl",
            "fallow||unlisted_dependencies|@assets/generated_images",
        ]))

    def test_fallow_moved_line_keeps_key(self):
        moved = FALLOW_REAL.replace('"line": 9', '"line": 77')
        self.assertEqual(sorted(ratchet.parse_fallow(moved)), sorted(ratchet.parse_fallow(FALLOW_REAL)))

    def test_fallow_clean_run_is_empty_list_not_error(self):
        self.assertEqual(ratchet.parse_fallow('{"kind": "dead-code", "next_steps": []}'), [])

    def test_fallow_bad_output_is_error(self):
        for bad in ("", "{}", "[]", "not json", '{"kind": "health"}', '{"kind": "dead-code", "unused_files": [1]}'):
            with self.assertRaises(ToolOutputError, msg=repr(bad)):
                ratchet.parse_fallow(bad)

    def test_fallow_second_identical_finding_counts_twice(self):
        doubled = json.loads(FALLOW_REAL)
        doubled["unused_exports"] = doubled["unused_exports"] * 2
        keys = ratchet.parse_fallow(json.dumps(doubled))
        self.assertEqual(count_findings(keys)[
            "fallow|artifacts/ai-dnd-experience/src/components/action-economy-panel.tsx|unused_exports|RageControl"], 2)


class UiGateBaselineTests(unittest.TestCase):
    BASE = ROOT / "scripts" / "quality_gate" / "baselines"

    def test_knip_new_unused_export_is_new(self):
        baseline = count_findings(ratchet.parse_knip(KNIP_REAL))
        doc = json.loads(KNIP_REAL)
        doc["issues"].append({"file": "artifacts/ai-dnd-web/src/new.ts",
                              "exports": [{"name": "brandNew", "line": 3}]})
        new = compare(baseline, count_findings(ratchet.parse_knip(json.dumps(doc))))
        self.assertEqual(len(new), 1)
        self.assertIn("knip|artifacts/ai-dnd-web/src/new.ts|exports|brandNew", new[0])

    def test_ui_baselines_exist_and_are_counts(self):
        for tool, minimum in (("knip", 50), ("fallow", 80)):
            path = self.BASE / (tool + ".json")
            self.assertTrue(path.is_file(), tool + " baseline missing")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(data), minimum)
            for key, n in data.items():
                self.assertTrue(key.startswith(tool + "|"), key)
                self.assertNotRegex(key.split("|")[1], r"^(/|[A-Za-z]:|\.\./)", key)  # repo-relative, no machine paths
                self.assertIsInstance(n, int)
                self.assertGreaterEqual(n, 1)


class WhitelistShrinkTests(unittest.TestCase):
    """Vulture whitelist: entry names may only shrink versus the base ref (grow-guard)."""

    @staticmethod
    def git(code, out="", err=""):
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def run_cli(self, new_text, git_result):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "vulture_whitelist.py"
            f.write_text(new_text, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(ratchet.subprocess, "run", return_value=git_result), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = ratchet.main(["check-names-shrink", str(f), "origin/main"])
            return code, out.getvalue() + err.getvalue()

    OLD = "# head\na  # unused variable (x.py:1)\nb  # unused import (y.py:2)\n"

    def test_added_name_exits_1(self):
        code, text = self.run_cli(self.OLD + "c  # unused variable (z.py:3)\n", self.git(0, self.OLD))
        self.assertEqual(code, 1)
        self.assertIn("'c'", text)

    def test_removed_and_equal_exit_0(self):
        self.assertEqual(self.run_cli("# head\na  # unused variable (x.py:1)\n", self.git(0, self.OLD))[0], 0)
        self.assertEqual(self.run_cli(self.OLD, self.git(0, self.OLD))[0], 0)

    def test_absent_at_base_is_first_introduction(self):
        err = "fatal: path 'x' exists on disk, but not in 'origin/main'"
        self.assertEqual(self.run_cli(self.OLD, self.git(128, "", err))[0], 0)

    def test_git_failure_exits_2(self):
        self.assertEqual(self.run_cli(self.OLD, self.git(128, "", "fatal: bad ref"))[0], 2)


class FingerprintShrinkTests(unittest.TestCase):
    """Gitleaks baseline: Fingerprint set may only shrink versus the base ref."""

    @staticmethod
    def git(code, out="", err=""):
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    @staticmethod
    def doc(*fps):
        return json.dumps([{"Fingerprint": f} for f in fps])

    def run_cli(self, new_text, git_result):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "gitleaks-baseline.json"
            f.write_text(new_text, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(ratchet.subprocess, "run", return_value=git_result), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = ratchet.main(["check-fingerprints-shrink", str(f), "origin/main"])
            return code, out.getvalue() + err.getvalue()

    def test_added_fingerprint_exits_1(self):
        code, text = self.run_cli(self.doc("a:1", "b:2", "c:3"), self.git(0, self.doc("a:1", "b:2")))
        self.assertEqual(code, 1)
        self.assertIn("c:3", text)

    def test_removed_and_equal_exit_0(self):
        self.assertEqual(self.run_cli(self.doc("a:1"), self.git(0, self.doc("a:1", "b:2")))[0], 0)
        self.assertEqual(self.run_cli(self.doc("a:1"), self.git(0, self.doc("a:1")))[0], 0)

    def test_absent_at_base_is_first_introduction(self):
        err = "fatal: path 'x' exists on disk, but not in 'origin/main'"
        self.assertEqual(self.run_cli(self.doc("a:1"), self.git(128, "", err))[0], 0)

    def test_git_failure_exits_2(self):
        self.assertEqual(self.run_cli(self.doc("a:1"), self.git(128, "", "fatal: bad ref"))[0], 2)

    def test_unusable_json_or_missing_fingerprint_exits_2(self):
        self.assertEqual(self.run_cli("not json", self.git(0, self.doc("a:1")))[0], 2)
        self.assertEqual(self.run_cli(json.dumps([{"RuleID": "x"}]), self.git(0, self.doc("a:1")))[0], 2)


class PythonGateTests(unittest.TestCase):
    WHITELIST = ROOT / "scripts" / "quality_gate" / "vulture_whitelist.py"

    def test_planted_unused_import_is_new(self):
        baseline = count_findings(parse_ruff(ruff_report(1, "known.py"), root="/r"))
        planted = count_findings(parse_ruff(ruff_report(1, "/r/scratch_new.py"), root="/r"))
        self.assertTrue(compare(baseline, planted))

    def test_vulture_whitelist_has_no_string_literals(self):
        self.assertTrue(self.WHITELIST.is_file(), "whitelist missing")
        lines = [ln for ln in self.WHITELIST.read_text(encoding="utf-8").splitlines() if ln.strip()]
        code = [ln for ln in lines if not ln.lstrip().startswith("#")]
        self.assertTrue(code, "whitelist has no entries")
        for ln in code:
            self.assertRegex(ln, r"^[A-Za-z_][\w.]*  # unused .+$", ln)
            self.assertNotIn('"', ln.split("#", 1)[0])
            self.assertNotIn("'", ln.split("#", 1)[0])



# G1.8 (D-592): the radon complexity ratchet. A function of rank E or F may get simpler, never more complex; a new one fails.
def radon_block(name, cc, classname=None, closures=()):
    row = {"type": "method" if classname else "function", "rank": "F", "complexity": cc, "lineno": 1, "endline": 9,
           "name": name, "col_offset": 0, "closures": list(closures)}
    if classname:
        row["classname"] = classname
    return row


def radon_report(**files):
    return json.dumps({path.replace("__", "/"): blocks for path, blocks in files.items()})


class TestRadonRatchet(unittest.TestCase):
    def counts(self, text):
        return count_findings(parse_radon(text))

    def test_only_rank_e_and_f_are_findings(self):
        text = radon_report(a=[radon_block("big", 31), radon_block("edge", 30), radon_block("small", 5)])
        self.assertEqual(self.counts(text), {"radon|a|cc|big": 31})

    def test_class_and_closure_names_are_part_of_the_key(self):
        text = radon_report(a=[radon_block("run", 40, classname="Game", closures=[radon_block("inner", 33)])])
        self.assertEqual(self.counts(text), {"radon|a|cc|Game.run": 40, "radon|a|cc|Game.run.inner": 33})

    def test_a_windows_path_is_the_same_key(self):
        win = json.dumps({"game_parts" + chr(92) + "turn.py": [radon_block("f", 35)]})
        self.assertEqual(self.counts(win), {"radon|game_parts/turn.py|cc|f": 35})

    def test_simpler_is_fine_more_complex_and_new_fail(self):
        base = self.counts(radon_report(a=[radon_block("f", 50), radon_block("g", 40)]))
        self.assertEqual(compare(base, self.counts(radon_report(a=[radon_block("f", 44), radon_block("g", 40)]))), [])
        self.assertEqual(compare(base, self.counts(radon_report(a=[radon_block("f", 51), radon_block("g", 40)]))),
                         ["radon|a|cc|f: 51 found, baseline allows 50"])
        self.assertEqual(compare(base, self.counts(radon_report(a=[radon_block("f", 50), radon_block("g", 40), radon_block("h", 31)]))),
                         ["radon|a|cc|h: 31 found, baseline allows 0"])

    def test_a_function_that_drops_below_the_bar_leaves_the_findings(self):
        base = self.counts(radon_report(a=[radon_block("f", 50)]))
        self.assertEqual(compare(base, self.counts(radon_report(a=[radon_block("f", 30)]))), [])

    def test_a_radon_error_or_garbage_is_a_tool_error(self):
        for text in ("", "not json", "[]", json.dumps({"a.py": "SyntaxError"})):
            with self.subTest(text=text), self.assertRaises(ToolOutputError):
                parse_radon(text)

    def test_the_committed_baseline_is_loadable_and_names_the_three_split_functions(self):
        baseline = load_baseline(ratchet.BASELINE_DIR / "radon.json")
        for key in ("radon|game_parts/turn.py|cc|_run_player_turn_internal",
                    "radon|game_parts/turn.py|cc|_dispatch_player_turn",
                    "radon|game_parts/narration_safety.py|cc|_narration_safety_decision"):
            self.assertIn(key, baseline)
        self.assertTrue(all(v >= ratchet.RADON_MIN_CC for v in baseline.values()))


if __name__ == "__main__":
    unittest.main()
