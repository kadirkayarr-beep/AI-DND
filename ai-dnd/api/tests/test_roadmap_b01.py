"""B01 source-identity contract; synthetic git repos only, no game/model/server calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
CANDIDATE_SHA = "78b380384e70832156d2d9aa2785192bbbbdb74b"
VERIFIED_FILES = (
    "pyproject.toml",
    "ai-dnd/api/main.py",
    "artifacts/ai-dnd-experience/src/App.tsx",
)
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import source_identity as owner
from api.tests.guard_bound import CHILD_PROCESS, guard_bound


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crlf_sha256(path):
    """Digest of the CRLF rendering, whatever line ending this checkout has.

    The lockfile pins were recorded on a CRLF working copy; git stores them
    with LF, so a plain digest depends on the checkout.
    """
    data = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(data).hexdigest()


@guard_bound(CHILD_PROCESS)
class RoadmapB01Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q", "-b", "main")
        (self.repo / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.13"\n', encoding="utf-8")
        (self.repo / "package.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        self.commit("main base")
        self.main_sha = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "-b", "candidate")
        (self.repo / "feature.txt").write_text("candidate\n", encoding="utf-8")
        self.commit("candidate change")
        self.source_sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.repo, stderr=subprocess.PIPE,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).decode()

    def commit(self, message):
        self.git("add", ".")
        self.git("-c", "user.name=B01 Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", message)

    def observe(self):
        """Test-local observations measured from the real owner, never from a copy of it."""
        unknown = owner.inspect_source_identity(self.repo, None)
        baseline = owner.load_baseline(REPO)
        return {
            "candidate_sha": baseline["candidate_sha"],
            "runtime_sha_status": unknown["runtime_sha_status"],
            "python_3_14_2_supported": owner.python_supported(self.repo, (3, 14, 2)),
            "python_3_12_supported": owner.python_supported(self.repo, (3, 12, 9)),
        }

    def test_manifest_rejects_runtime_sha_mismatch(self):
        obs = self.observe()
        assert obs["candidate_sha"] == "78b380384e70832156d2d9aa2785192bbbbdb74b"
        assert obs["runtime_sha_status"] == "UNKNOWN"
        assert obs["python_3_14_2_supported"] is True
        assert obs["python_3_12_supported"] is False

        unknown = owner.inspect_source_identity(self.repo, None)
        self.assertIsNone(unknown["runtime_sha"])
        self.assertFalse(unknown["accepted"])

        mismatch = owner.inspect_source_identity(self.repo, {"sha": "0" * 40})
        self.assertEqual(mismatch["runtime_sha_status"], "MISMATCH")
        self.assertEqual(mismatch["runtime_sha"], "0" * 40)
        self.assertFalse(mismatch["accepted"])

        match = owner.inspect_source_identity(self.repo, {"sha": self.source_sha})
        self.assertEqual(match["runtime_sha_status"], "MATCH")
        self.assertTrue(match["accepted"])

    def test_candidate_and_main_are_separate_records(self):
        result = owner.inspect_source_identity(self.repo, None)
        self.assertEqual(result["source_sha"], self.source_sha)
        self.assertEqual(result["main_sha"], self.main_sha)
        self.assertNotEqual(result["source_sha"], result["main_sha"])
        self.assertIsNone(result["origin_main_sha"])

    def test_dirty_tree_lists_changed_paths(self):
        clean = owner.inspect_source_identity(self.repo, None)
        self.assertTrue(clean["tree_state"]["clean"])
        self.assertEqual(clean["tree_state"]["changed_paths"], [])
        (self.repo / "feature.txt").write_text("edited\n", encoding="utf-8")
        (self.repo / "staged.txt").write_text("staged\n", encoding="utf-8")
        self.git("add", "staged.txt")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        dirty = owner.inspect_source_identity(self.repo, {"sha": self.source_sha})
        self.assertFalse(dirty["tree_state"]["clean"])
        self.assertEqual(dirty["tree_state"]["changed_paths"],
                         ["feature.txt", "staged.txt", "untracked.txt"])
        self.assertFalse(dirty["accepted"])

    def test_environment_fields_are_separate(self):
        result = owner.inspect_source_identity(self.repo, None)
        for key in ("source_sha", "tree_state", "runtime_sha", "os", "python",
                    "node", "package_manager"):
            self.assertIn(key, result)
        self.assertEqual(result["package_manager"]["name"], "pnpm")
        self.assertEqual(result["package_manager"]["lockfile"], "pnpm-lock.yaml")
        self.assertEqual(result["python"]["requires"], ">=3.13")
        self.assertIsInstance(result["python"]["supported"], bool)

    def test_python_support_comes_from_requires_python(self):
        self.assertTrue(owner.python_supported(self.repo, (3, 13, 0)))
        (self.repo / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.15"\n', encoding="utf-8")
        self.assertFalse(owner.python_supported(self.repo, (3, 14, 2)))
        (self.repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            owner.python_supported(self.repo, (3, 14, 2))

    def test_baseline_pins_verified_sources_and_locks(self):
        baseline = owner.load_baseline(REPO)
        self.assertEqual(baseline["requires_python"], ">=3.13")
        for name in VERIFIED_FILES[1:]:
            self.assertIn(name, baseline["entrypoints"])
            self.assertTrue((REPO / name).is_file(), name)
        for name, digest in baseline["lockfiles"].items():
            self.assertEqual(crlf_sha256(REPO / name), digest, name)
        self.assertEqual(set(baseline["lockfiles"]), {"pnpm-lock.yaml", "uv.lock"})

    def test_readonly_inventory_leaves_product_files_unchanged(self):
        before = {name: sha256(REPO / name) for name in VERIFIED_FILES}
        owner.inspect_source_identity(REPO, None)
        owner.load_baseline(REPO)
        after = {name: sha256(REPO / name) for name in VERIFIED_FILES}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
