"""D-218: CI runs every Python test module, split into shards that together cover each module exactly once."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import full_python_suite as suite


def _ci_shards() -> list[int]:
    text = (ROOT.parent / ".github" / "workflows" / "ai-dnd-ci.yml").read_text(encoding="utf-8")
    match = re.search(r"shard: \[([0-9, ]+)\]", text)
    return [int(part) for part in match.group(1).split(",")]


class FullPythonSuite(unittest.TestCase):
    def test_every_test_module_is_listed_by_dotted_name(self):
        listed = suite.modules(ROOT)
        on_disk = sorted("api.tests." + p.stem for p in (ROOT / "api" / "tests").glob("test_*.py"))
        self.assertEqual(listed, on_disk)
        self.assertIn("api.tests.test_full_python_suite", listed)

    def test_only_test_files_directly_in_api_tests_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "api" / "tests"
            (tests / "journeys").mkdir(parents=True)
            for name in ("test_b.py", "test_a.py", "helper.py", "town_seed.py", "test_c.txt"):
                (tests / name).write_text("", encoding="utf-8")
            (tests / "journeys" / "test_nested.py").write_text("", encoding="utf-8")
            self.assertEqual(suite.modules(Path(tmp)), ["api.tests.test_a", "api.tests.test_b"])

    def test_shards_cover_each_module_exactly_once(self):
        names = [f"api.tests.test_{i:03d}" for i in range(23)]
        for count in (1, 2, 4, 7):
            parts = [suite.shard(names, index, count) for index in range(1, count + 1)]
            joined = [name for part in parts for name in part]
            self.assertEqual(sorted(joined), names, count)
            self.assertEqual(len(joined), len(set(joined)), count)
            self.assertTrue(all(parts), count)

    def test_a_shard_outside_the_count_is_refused(self):
        for index, count in ((0, 4), (5, 4), (1, 0)):
            with self.assertRaises(ValueError):
                suite.shard(["api.tests.test_a"], index, count)

    def test_the_real_suite_splits_into_the_ci_shard_count_without_empty_shards(self):
        listed = suite.modules(ROOT)
        count = len(_ci_shards())
        parts = [suite.shard(listed, index, count) for index in range(1, count + 1)]
        self.assertEqual(sorted(name for part in parts for name in part), listed)
        self.assertTrue(all(parts))

    def test_ci_runs_six_shards_and_tells_each_shard_the_same_count(self):
        # Kadir 2026-11-15: 6 shards instead of 4 to shorten the wait on each PR.
        text = (ROOT.parent / ".github" / "workflows" / "ai-dnd-ci.yml").read_text(encoding="utf-8")
        self.assertEqual(_ci_shards(), [1, 2, 3, 4, 5, 6])
        self.assertIn("--shard ${{ matrix.shard }} --of 6", text)
        self.assertNotIn("--of 4", text)


if __name__ == "__main__":
    unittest.main()
