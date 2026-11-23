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
GITLEAKS_BASELINE = AI_DND / "scripts" / "quality_gate" / "gitleaks-baseline.json"
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


def _steps(lines: list[str]) -> list[list[str]]:
    steps: list[list[str]] = [[]]
    for line in lines:
        if re.match(r"^\s*-\s+\w[\w-]*:", line):
            steps.append([])
        steps[-1].append(line)
    return steps


def workflow_violations(text: str, baseline_required: bool | None = None) -> list[str]:
    """Per-line / per-step policy checks; returns one message per violation.

    --baseline-path is required on gitleaks lines only once the baseline file
    exists (Task 6); --redact is always required."""
    if baseline_required is None:
        baseline_required = GITLEAKS_BASELINE.exists()
    bad: list[str] = []
    for word in ("skylos cloud", "--upload", "skylos[", "jsgoldman"):
        if word in text:
            bad.append("forbidden text: " + word)
    for step in _steps(text.splitlines()):
        step_text = chr(10).join(step)
        for line in step:
            if line.lstrip().startswith("#") or re.match(r"^\s*(-\s+)?name:", line):
                continue
            where = line.strip()
            if re.search(r"\bskylos\b", line) and re.search(
                    r"(pip|pipx|uvx?)\s+(install|run)|skylos\s+\S", line):
                if "--no-upload" not in line:
                    bad.append("skylos without --no-upload: " + where)
            if re.search(r"\bvulture\s+(?!==)[^=\s]", line) \
                    and "--min-confidence 80" not in line:
                bad.append("vulture without --min-confidence 80: " + where)
            if re.search(r"\bgitleaks\s+(detect|git|dir)\b", line):
                flags = ("--redact", "--baseline-path") if baseline_required else ("--redact",)
                for flag in flags:
                    if flag not in line:
                        bad.append("gitleaks without " + flag + ": " + where)
            if re.search(r"\b(pnpm\s+(dlx|add|install|i)|npx|npm\s+(install|i|ci|exec))\b", line):
                if "ignore_scripts=true" not in line and "--ignore-scripts" not in line \
                        and 'npm_config_ignore_scripts: "true"' not in step_text:
                    bad.append("npm/pnpm run without ignore-scripts: " + where)
            if re.search(r"\bfallow\b", line) and re.search(r"(dlx|npx|npm|pnpm|fallow\s+\S)", line):
                if "DO_NOT_TRACK=1" not in line and 'DO_NOT_TRACK: "1"' not in step_text:
                    bad.append("fallow step without DO_NOT_TRACK: " + where)
                if re.search(r"fallow(@\S+)?\"?\s+\S", line) \
                        and not re.search(r"fallow(@\S+)?\"?\s+dead-code\b", line):
                    bad.append("fallow must run only the dead-code subcommand: " + where)
                if re.search(r"(similar-code|dupes|--coverage|health\b|mutation)", line):
                    bad.append("fallow similar-code/duplication/coverage feature on: " + where)
    return bad


class QualityWorkflowPolicyTest(unittest.TestCase):
    def test_workflow_forbids_upload_paths(self):
        self.assertTrue(WORKFLOW.exists(), "ai-dnd-quality.yml must exist")
        self.assertEqual(workflow_violations(WORKFLOW.read_text(encoding="utf-8")), [])

    def test_checker_catches_bad_lines(self):
        cases = {
            "skylos": "      - run: skylos .",
            "vulture": "      - run: pip install vulture==2.14 && vulture src",
            "gitleaks git": "      - run: gitleaks git --no-banner",
            "gitleaks dir": "      - run: gitleaks dir --baseline-path b.json",
            "pnpm": "      - run: pnpm dlx knip@6.48.0",
            "npx": "      - run: npx knip@6.48.0",
            "fallow": "      - run: pnpm dlx fallow@3.47.0 --ignore-scripts",
        }
        for name, text in cases.items():
            self.assertTrue(workflow_violations(text), name)

    def test_gitleaks_baseline_only_when_required(self):
        measure = "      - run: gitleaks detect --redact --no-banner --report-format json"
        self.assertEqual(workflow_violations(measure, baseline_required=False), [])
        self.assertTrue(workflow_violations(measure, baseline_required=True))
        self.assertTrue(workflow_violations("      - run: gitleaks detect --no-banner", baseline_required=False))

    def test_step_names_are_not_commands(self):
        self.assertEqual(workflow_violations("      - name: skylos scan" + chr(10) + "      - name: fallow report"), [])

    def test_fallow_only_dead_code(self):
        env = "      - run: DO_NOT_TRACK=1 npm_config_ignore_scripts=true pnpm dlx "
        for sub in ("similar-code", "dupes --format json", "health", "dead-code --coverage x.json", "--format json"):
            self.assertTrue(workflow_violations(env + "fallow@3.45.0 " + sub), sub)
        self.assertEqual(workflow_violations(env + "fallow@3.45.0 dead-code --format json --quiet"), [])
        quoted = env + chr(34) + "fallow@${V}" + chr(34) + " dead-code --format json"
        self.assertEqual(workflow_violations(quoted), [])
        self.assertTrue(workflow_violations(env + chr(34) + "fallow@${V}" + chr(34) + " dupes"))

    def test_checker_passes_good_lines(self):
        good = chr(10).join([
            "      - run: skylos . --no-upload",
            "      - run: pip install vulture==2.14",
            "      - run: vulture src --min-confidence 80",
            "      - run: gitleaks git --redact --baseline-path b.json",
            "      - run: npm_config_ignore_scripts=true pnpm dlx knip@6.48.0",
            "      - name: fallow",
            "        env:",
            "          DO_NOT_TRACK: \"1\"",
            "        run: npm_config_ignore_scripts=true pnpm dlx fallow@3.47.0",
        ])
        self.assertEqual(workflow_violations(good, baseline_required=True), [])

    def test_no_hooks_added(self):
        for name in (".pre-commit-config.yaml", "lefthook.yml"):
            self.assertFalse((REPO / name).exists(), name)
        self.assertFalse((REPO / ".husky").exists())


if __name__ == "__main__":
    unittest.main()
