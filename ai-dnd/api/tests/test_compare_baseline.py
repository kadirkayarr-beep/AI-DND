"""compare_baseline: the wave gate's baseline comparison tool (debt-zero plan, G0.5)."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[3] / "docs" / "agents" / "kalite-taramasi-20261125" / "compare_baseline.py"


def _load():
    spec = importlib.util.spec_from_file_location("compare_baseline", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base():
    return {"tools": {
        "ruff_extra": {"B023|ai-dnd/x.py": 2, "SIM102|ai-dnd/y.py": 5},
        "deptry": {"DEP001|engine_split": 40},
        "skylos": {"analysis_errors": 0, "circular_dependencies": 3},
        "engine_api_edges": ["a -> api.b"],
        "import_linter_broken_pairs": [["adventure", "api"]],
        "pip_audit": ["certifi==1|PYSEC-1"],
        "pnpm_audit_all": ["body-parser|GHSA-1|high"],
        "gitleaks_new": 0,
    }}


# The test slot syncs only ai-dnd, content, tools, lib, .github, artifacts (not docs/); CI and the host see the tool.
@unittest.skipUnless(TOOL.exists(), "docs/ is not synced into the test slot")
class CompareBaselineTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.base = _base()

    def _new(self):
        return copy.deepcopy(self.base)

    def test_shrink_passes(self):
        new = self._new()
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 1
        new["tools"]["engine_api_edges"] = []
        self.assertEqual(self.mod.compare(self.base, new, set()), [])

    def test_identical_passes(self):
        self.assertEqual(self.mod.compare(self.base, self._new(), set()), [])

    def test_key_growth_in_any_file_fails(self):
        for touched in (set(), {"ai-dnd/x.py"}):
            new = self._new()
            new["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 3
            lines = self.mod.compare(self.base, new, touched)
            self.assertTrue(any("B023|ai-dnd/x.py" in line for line in lines), lines)

    def test_new_key_counts_as_growth(self):
        new = self._new()
        new["tools"]["ruff_extra"]["B023|ai-dnd/z.py"] = 1
        self.assertTrue(self.mod.compare(self.base, new, set()))

    def test_masking_fails(self):
        new = self._new()
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 0  # dead code removed: total shrinks by 5
        new["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 3  # but another key grows
        lines = self.mod.compare(self.base, new, {"ai-dnd/y.py"})
        self.assertTrue(any("B023|ai-dnd/x.py" in line for line in lines), lines)

    def test_total_growth_fails(self):
        new = self._new()
        new["tools"]["ruff_extra"]["NEW|ai-dnd/q.py"] = 1
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 4
        lines = self.mod.compare(self.base, new, set())
        self.assertTrue(any("NEW|ai-dnd/q.py" in line for line in lines), lines)
        new = self._new()
        new["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 5
        lines = self.mod.compare(self.base, new, set())
        self.assertTrue(any("total" in line for line in lines), lines)

    def test_moved_code_growth_allowed_only_when_listed(self):
        new = self._new()
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 2
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y_part.py"] = 3
        self.assertTrue(self.mod.compare(self.base, new, set()))
        self.assertEqual(self.mod.compare(self.base, new, set(), moved=[("ai-dnd/y.py", "ai-dnd/y_part.py")]), [])
        # listed but the source did not shrink enough
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 3
        self.assertTrue(self.mod.compare(self.base, new, set(), moved=[("ai-dnd/y.py", "ai-dnd/y_part.py")]))

    def test_moved_cannot_grow_total(self):
        new = self._new()
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y.py"] = 2
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y_part.py"] = 3
        new["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 1  # total 6 < 7, fine
        self.assertEqual(self.mod.compare(self.base, new, set(), moved=[("ai-dnd/y.py", "ai-dnd/y_part.py")]), [])
        new["tools"]["ruff_extra"]["SIM102|ai-dnd/y_part.py"] = 4  # source shrank by 3 only
        self.assertTrue(self.mod.compare(self.base, new, set(), moved=[("ai-dnd/y.py", "ai-dnd/y_part.py")]))

    def test_deptry_growth_fails(self):
        new = self._new()
        new["tools"]["deptry"]["DEP001|engine_split"] = 41
        self.assertTrue(self.mod.compare(self.base, new, set()))

    def test_skylos_total_growth_fails(self):
        new = self._new()
        new["tools"]["skylos"]["circular_dependencies"] = 4
        self.assertTrue(self.mod.compare(self.base, new, set()))

    def test_new_engine_api_edge_fails(self):
        new = self._new()
        new["tools"]["engine_api_edges"].append("c -> api.d")
        lines = self.mod.compare(self.base, new, set())
        self.assertTrue(any("c -> api.d" in line for line in lines), lines)

    def test_new_broken_pair_fails(self):
        new = self._new()
        new["tools"]["import_linter_broken_pairs"].append(["x", "y"])
        self.assertTrue(self.mod.compare(self.base, new, set()))

    def test_new_vuln_id_fails(self):
        for tool, entry in (("pip_audit", "certifi==2|PYSEC-2"), ("pnpm_audit_all", "ws|GHSA-2|high")):
            new = self._new()
            new["tools"][tool].append(entry)
            lines = self.mod.compare(self.base, new, set())
            self.assertTrue(any(entry in line for line in lines), (tool, lines))

    def test_gitleaks_growth_fails(self):
        new = self._new()
        new["tools"]["gitleaks_new"] = 1
        self.assertTrue(self.mod.compare(self.base, new, set()))

    def test_touched_only_labels_report(self):
        new = self._new()
        new["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 3
        in_touched = self.mod.compare(self.base, new, {"ai-dnd/x.py"})
        outside = self.mod.compare(self.base, new, set())
        self.assertTrue(in_touched and outside)
        self.assertNotEqual(in_touched[0], outside[0])

    def test_command_line_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path, new_path = Path(tmp, "b.json"), Path(tmp, "n.json")
            base_path.write_text(json.dumps(self.base), encoding="utf-8")
            new_path.write_text(json.dumps(self.base), encoding="utf-8")
            ok = subprocess.run([sys.executable, str(TOOL), str(base_path), str(new_path)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            grown = self._new()
            grown["tools"]["ruff_extra"]["B023|ai-dnd/x.py"] = 3
            new_path.write_text(json.dumps(grown), encoding="utf-8")
            bad = subprocess.run([sys.executable, str(TOOL), str(base_path), str(new_path), "--touched", "ai-dnd/x.py"], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("B023|ai-dnd/x.py", bad.stdout)


if __name__ == "__main__":
    unittest.main()
