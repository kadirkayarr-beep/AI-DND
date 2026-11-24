"""Size ratchet for the Python outside the engine lock and for the UI source (Quality gate, Task 8).

Same rules as test_engine_size_budget.py (its helpers are imported, not copied): a file may not pass its budget,
a budget may not hoard more than `slack` lines of room, a file with no entry may not pass `part_max`, and a top-level
function of `long_function_min` lines or more must be listed and may not grow.
Raising any number in scripts/quality_gate/size_lock.json needs an approval-list row and Kadir. Lowering needs none.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.inventory import top_level_index  # noqa: E402
from api.tests.engine_sources import engine_source_files  # noqa: E402
from api.tests.test_engine_size_budget import budget_findings, long_function_findings  # noqa: E402

LOCK_PATH = ROOT / "scripts" / "quality_gate" / "size_lock.json"
SKIP_DIRS = {"__pycache__", ".ruff_cache", "node_modules", ".venv", "venv", "batches", "dist", ".git"}


def _walk(base: Path, patterns: tuple[str, ...]) -> list[Path]:
    found = []
    for pattern in patterns:
        for p in base.rglob(pattern):
            if p.is_file() and not (SKIP_DIRS & set(p.relative_to(base).parts)):
                found.append(p)
    return sorted(set(found))


def _non_engine_python() -> list[Path]:
    engine = {p.resolve() for p in engine_source_files(ROOT)}
    return [p for p in _walk(ROOT, ("*.py",)) if p.resolve() not in engine]


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def real_python_sizes() -> dict[str, int]:
    return {p.relative_to(ROOT).as_posix(): _lines(p) for p in _non_engine_python()}


def real_python_function_lengths() -> dict[str, int]:
    """`<file>::<name>` -> lines, same key shape as the engine lock."""
    out: dict[str, int] = {}
    for p in _non_engine_python():
        try:
            rows = top_level_index(p)
        except SyntaxError:  # e.g. a BOM file under reports/: still counted by line, no function lengths
            continue
        for row in rows:
            if row["kind"] == "function":
                key = f"{p.relative_to(ROOT).as_posix()}::{row['name']}"
                out[key] = max(out.get(key, 0), row["lines"])
    return out


def real_ts_sizes() -> dict[str, int]:
    base = REPO / "artifacts"
    files = [p for p in _walk(base, ("*.ts", "*.tsx")) if "src" in p.relative_to(base).parts[1:2]]
    return {p.relative_to(REPO).as_posix(): _lines(p) for p in files}


LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8")) if LOCK_PATH.exists() else {}


def _ts_lock() -> dict:
    return {"files": LOCK["ts_files"], "part_max": LOCK["part_max"], "slack": LOCK["slack"]}


class SizeRatchetTests(unittest.TestCase):
    def test_lock_file_exists(self):
        self.assertTrue(LOCK_PATH.exists(), "size_lock.json is missing")

    def test_non_engine_python_fits_its_lock(self):
        self.assertEqual(budget_findings(real_python_sizes(), LOCK), [])
        self.assertEqual(long_function_findings(real_python_function_lengths(), LOCK), [])

    def test_ui_ts_fits_its_lock(self):
        self.assertEqual(budget_findings(real_ts_sizes(), _ts_lock()), [])

    def test_one_line_over_is_red(self):
        py = next(iter(LOCK["files"]))
        self.assertNotEqual(budget_findings({py: LOCK["files"][py] + 1}, LOCK), [])
        ts = next(iter(LOCK["ts_files"]))
        self.assertNotEqual(budget_findings({ts: LOCK["ts_files"][ts] + 1}, _ts_lock()), [])

    def test_a_budget_cannot_hoard_room(self):
        py, ts = next(iter(LOCK["files"])), next(iter(LOCK["ts_files"]))
        big_py = max(LOCK["files"], key=LOCK["files"].get)
        self.assertNotEqual(budget_findings({big_py: LOCK["files"][big_py] - 51}, LOCK), [])
        self.assertEqual(budget_findings({big_py: LOCK["files"][big_py] - 50}, LOCK), [])
        big_ts = max(LOCK["ts_files"], key=LOCK["ts_files"].get)
        self.assertNotEqual(budget_findings({big_ts: LOCK["ts_files"][big_ts] - 51}, _ts_lock()), [])
        self.assertEqual(budget_findings({big_ts: LOCK["ts_files"][big_ts] - 50}, _ts_lock()), [])
        self.assertTrue(py and ts)

    def test_new_big_file_without_entry_is_red(self):
        self.assertNotEqual(budget_findings({"brand_new_module.py": 2501}, LOCK), [])
        self.assertEqual(budget_findings({"brand_new_module.py": 2500}, LOCK), [])
        self.assertNotEqual(budget_findings({"artifacts/x/src/brand_new.tsx": 2501}, _ts_lock()), [])

    def test_new_long_function_is_red(self):
        self.assertNotEqual(long_function_findings({"brand_new_module.py::brand_new": 151}, LOCK), [])
        self.assertEqual(long_function_findings({"brand_new_module.py::brand_new": 150}, LOCK), [])
        if LOCK["long_functions"]:
            key = next(iter(LOCK["long_functions"]))
            self.assertNotEqual(long_function_findings({key: LOCK["long_functions"][key] + 1}, LOCK), [])

    def test_lock_values_match_spec(self):
        self.assertEqual((LOCK["part_max"], LOCK["slack"], LOCK["long_function_min"]), (2500, 50, 151))

    def test_engine_files_not_double_counted(self):
        engine = {p.relative_to(ROOT).as_posix() for p in engine_source_files(ROOT)}
        self.assertTrue(engine)
        self.assertFalse(engine & set(real_python_sizes()))
        self.assertFalse(engine & set(LOCK["files"]))
        self.assertFalse(any(key.split("::")[0] in engine for key in LOCK["long_functions"]))

    def test_the_walk_sees_real_files(self):
        # an empty walk must not pass as "everything fits"
        self.assertGreater(len(real_python_sizes()), 100)
        self.assertGreater(len(real_ts_sizes()), 50)
        self.assertFalse(any(k.startswith("scripts/engine_split/batches/") for k in real_python_sizes()))


if __name__ == "__main__":
    unittest.main()
