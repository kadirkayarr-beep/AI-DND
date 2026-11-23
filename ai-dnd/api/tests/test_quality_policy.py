"""Quality gate policy: exact tool pins, no upload/telemetry paths, no local hooks."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

AI_DND = Path(__file__).resolve().parents[2]
REPO = AI_DND.parent
TOOLS = AI_DND / "scripts" / "quality_gate" / "tools.json"
REQ_DEV = AI_DND / "scripts" / "engine_split" / "requirements-dev.txt"
WORKFLOW = REPO / ".github" / "workflows" / "ai-dnd-quality.yml"
EXACT = re.compile(r"^\d+\.\d+(\.\d+)?$")  # vulture is pinned as 2.14 (two parts)


def _tools() -> dict:
    return json.loads(TOOLS.read_text(encoding="utf-8"))


class QualityPinsTest(unittest.TestCase):
    def test_pins_are_exact(self):
        tools = _tools()
        for name in ("ruff", "vulture", "skylos", "knip", "fallow"):
            self.assertRegex(tools[name], EXACT, name)
        self.assertRegex(tools["gitleaks"]["version"], EXACT)
        self.assertRegex(tools["gitleaks"]["sha256"], r"^[0-9a-f]{64}$")
        reqs = REQ_DEV.read_text(encoding="utf-8").split()
        self.assertIn("ruff==" + tools["ruff"], reqs)
        self.assertIn("vulture==" + tools["vulture"], reqs)


class QualityWorkflowPolicyTest(unittest.TestCase):
    def _lines(self) -> list[str]:
        if not WORKFLOW.exists():
            self.skipTest("ai-dnd-quality.yml not created yet (Task 4)")
        return WORKFLOW.read_text(encoding="utf-8").splitlines()

    def test_workflow_forbids_upload_paths(self):
        lines = self._lines()
        text = "\n".join(lines)
        for bad in ("skylos cloud", "--upload", "skylos[", "jsgoldman"):
            self.assertNotIn(bad, text)
        for line in lines:
            if re.search(r"\bskylos\b", line) and not line.lstrip().startswith("#"):
                if re.search(r"(pip|pipx|uvx?)\s+(install|run)|skylos\s+\S", line):
                    self.assertIn("--no-upload", line, line)
            if re.search(r"\bvulture\b", line) and "==" not in line \
                    and not line.lstrip().startswith("#") and re.search(r"vulture\s+\S", line):
                self.assertIn("--min-confidence 80", line, line)
            if "gitleaks" in line and "detect" in line:
                self.assertIn("--redact", line, line)
                self.assertIn("--baseline-path", line, line)
        if re.search(r"\bfallow\b", text):
            self.assertIn('DO_NOT_TRACK: "1"', text)

    def test_no_hooks_added(self):
        for name in (".pre-commit-config.yaml", "lefthook.yml"):
            self.assertFalse((REPO / name).exists(), name)
        self.assertFalse((REPO / ".husky").exists())


if __name__ == "__main__":
    unittest.main()
