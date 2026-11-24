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
                is_plain_pip_install = re.search(r"pip\s+install", line) and "[" not in line
                if "--no-upload" not in line and not is_plain_pip_install:
                    bad.append("skylos without --no-upload: " + where)
            if "skylos==" in line and not re.search(
                    r"skylos==\d[\d.]*(\s|$)|print\('skylos=='\+t\['skylos'\]\)", line):
                bad.append("skylos pin line not plain: " + where)
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
            if re.search(r"\bfallow\b", line) and "scripts.quality_gate.ratchet" not in line \
                    and re.search(r"(dlx|npx|npm|pnpm|fallow\s+\S)", line):
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

    def test_skylos_pip_install_needs_no_upload_flag_but_no_extra(self):
        self.assertEqual(workflow_violations("      - run: python -m pip install skylos==4.1.0"), [])
        self.assertTrue(workflow_violations("      - run: python -m pip install skylos[llm]==4.1.0"))
        self.assertTrue(workflow_violations("      - run: skylos ai-dnd --json"))

    def test_skylos_pkg_one_liner_has_no_extra(self):
        good = "          PKG=$(python -c \"import json;t=json.load(open('x.json'));print('skylos=='+t['skylos'])\")"
        self.assertEqual(workflow_violations(good), [])
        for bad in (good.replace("'skylos=='", "'skylos[llm]=='"),
                    good.replace("'skylos=='+", "'skylos[llm]=='+"),
                    good.replace("+t['skylos']", "+t['skylos']+'[llm]'"),
                    good.replace("print('skylos=='+t['skylos'])", "print('skylos==' + t['x'])")):
            self.assertTrue(workflow_violations(bad), bad)

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


def _job_text(name: str) -> str:
    """Text of one top-level job of the quality workflow ('' when absent)."""
    out: list[str] = []
    inside = False
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if re.match(r"^  \S[^:]*:\s*$", line):
            inside = line.strip() == name + ":"
            continue
        if re.match(r"^\S", line):
            inside = False
        if inside:
            out.append(line)
    return chr(10).join(out)


class QualitySecretGateTest(unittest.TestCase):
    def test_gitleaks_baseline_has_no_secret_values(self):
        data = json.loads(GITLEAKS_BASELINE.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        for f in data:
            self.assertIn(f.get("Secret", ""), ("REDACTED", ""))
            match = f.get("Match", "")
            self.assertTrue(match == "" or re.fullmatch(r"""[A-Za-z0-9_ .\-"']*[=:] ?["']REDACTED["']""", match), "Match not of the form NAME = REDACTED")

    def test_gitleaks_step_pinned(self):
        job = _job_text("secrets-gate")
        self.assertTrue(job, "secrets-gate job missing")
        pins = _tools()["gitleaks"]
        self.assertIn("fetch-depth: 0", job)
        self.assertNotIn("continue-on-error", job)
        self.assertIn("tools.json", job)  # version is read from the single pin file
        self.assertRegex(job, r"releases/download/v\$\{V\}/gitleaks_\$\{V\}_linux_x64\.tar\.gz")
        self.assertIn("sha256sum -c", job)
        self.assertLess(job.index("sha256sum -c"), re.search(r"/gitleaks\" detect ", job).start())
        run = next(l for l in job.splitlines() if "/gitleaks" in l and " detect " in l)
        for flag in ("--redact", "--no-banner", "--baseline-path ai-dnd/scripts/quality_gate/gitleaks-baseline.json"):
            self.assertIn(flag, run)
        self.assertTrue(pins["sha256"] and pins["version"])

    def test_gitleaks_baseline_may_only_shrink_in_ci(self):
        job = _job_text("secrets-gate")
        self.assertIn("git fetch --no-tags origin main", job)
        step = next((l for l in job.splitlines() if "check-fingerprints-shrink" in l), "")
        self.assertIn("scripts/quality_gate/gitleaks-baseline.json origin/main", step)
        self.assertLess(job.index("check-fingerprints-shrink"), job.index("commits scanned"))

    def test_gitleaks_gate_rejects_zero_commits_scanned(self):
        job = _job_text("secrets-gate")
        self.assertRegex(job, r"commits scanned")
        self.assertIn("exit 2", job)

    def test_gitleaks_measure_step_moved_into_gate(self):
        self.assertNotIn("gitleaks detect", _job_text("measure"))


def _job_steps(job: str) -> list[str]:
    """Split a job's text into its steps (each starts with a '      - ' line)."""
    steps: list[str] = []
    for line in job.splitlines():
        if line.startswith("      - "):
            steps.append(line)
        elif steps:
            steps[-1] += chr(10) + line
    return steps


class QualityUiGateTest(unittest.TestCase):
    def _step(self, needle: str) -> str:
        job = _job_text("ui-gate")
        self.assertTrue(job, "ui-gate job missing")
        hits = [s for s in _job_steps(job) if needle in s]
        self.assertEqual(len(hits), 1, needle)
        return hits[0]

    def test_job_is_blocking(self):
        job = _job_text("ui-gate")
        self.assertTrue(job, "ui-gate job missing")
        self.assertNotIn("continue-on-error", job.split("steps:")[0])
        self.assertIn("fetch-depth: 0", job)

    def test_knip_step_is_blocking_and_ratcheted(self):
        knip = self._step("dlx \"knip@")
        self.assertNotIn("continue-on-error", knip)
        self.assertIn("--reporter json", knip)
        self.assertIn("ignore_scripts=true", knip)
        self.assertIn("ratchet check knip", knip)
        self.assertIn("exit 2", knip)  # a crashed knip is red, not zero findings

    def test_knip_baseline_may_only_shrink_in_ci(self):
        shrink = self._step("check-shrink")
        self.assertNotIn("continue-on-error", shrink)
        self.assertIn("scripts/quality_gate/baselines/knip.json origin/main", shrink)
        self.assertIn("git fetch --no-tags origin main", shrink)

    def test_report_only_steps_are_marked(self):
        fallow = self._step("fallow@")
        skylos = self._step("skylos ")
        for step in (fallow, skylos):
            self.assertIn("continue-on-error: true", step)
        self.assertIn("ratchet check fallow", fallow)
        self.assertIn("--no-upload", skylos)
        self.assertNotIn("[llm]", skylos)
        self.assertNotIn("--trace", skylos)
        self.assertIn("pip install --only-binary=:all: ", skylos)

    def test_nothing_in_ui_gate_pushes_or_uploads(self):
        job = _job_text("ui-gate")
        for bad in ("--upload", "skylos cloud", "upload-artifact"):
            self.assertNotIn(bad, job)


if __name__ == "__main__":
    unittest.main()
