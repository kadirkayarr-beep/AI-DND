# Kalite kapısı (yol haritası 4b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CI turns red on any NEW dead code, unused import/variable, leaked secret, or oversized file/function that enters `main`; today's findings are frozen as baselines that can only shrink.

**Architecture:** One shared ratchet module (`ai-dnd/scripts/quality_gate/ratchet.py`) turns every tool's output into line-number-free finding keys, compares counts to a committed baseline, and fails only on new or grown keys. A new workflow `.github/workflows/ai-dnd-quality.yml` runs the tools (report-only first, then blocking). The size ratchet of `size_budget.json` is extended to non-engine Python and the UI by a second lock file. No product code changes; no local hooks.

**Tech Stack:** Python 3.13 stdlib (`json`, `subprocess`, `unittest`), ruff, vulture, skylos, gitleaks, knip, fallow, GitHub Actions. Tests run only through `AI-DND-TOOLS/slot.sh` slot 9.

**Spec:** `docs/superpowers/specs/2026-11-23-kalite-kapisi-design.md` (authority). Roadmap row: `docs/design/YOL_HARITASI.md` 4b (4c, the one-off scan, is a separate plan).

## Global Constraints

Tool verdicts (settled 2026-11-23, verbatim):
- ruff: safe. vulture: safe; whitelist via `--make-whitelist`, `--min-confidence 80`.
- skylos: no `[llm]` extra, always `--no-upload`, never `cloud`/`--upload`.
- knip: pin exact version (JS/TS). fallow (fallow-rs/fallow only; jsgoldman/fallow is not official): `DO_NOT_TRACK=1`, similar-code and coverage features off.
- gitleaks: pin version and checksum, `--baseline-path`.
- Gate runs in CI, not local hooks. Ratchet/baseline: existing findings recorded as baseline, only new ones fail. First task measures noise on current main (report-only) before any job fails.

Rules:
- Never read or print key files (`.env`, `apikeys*`, `*.pem`). Never name the pnpm lock file in git commands (stage files by explicit path, never `git add -A` or `git add .`). No browser tests.
- Tests only via `slot.sh 9 <WT> test <label> <timeout> <modules>`. Every task's targeted run also includes the fixed neighbor set: `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- Pins already in the repo: `ai-dnd/scripts/engine_split/requirements-dev.txt` has `ruff==0.17.5` and `vulture==2.14`. Reuse them; do not add a second pin.
- Dead-code deletion is NOT part of this plan (spec "Riskler": only via debt row, test and commit; that is 4c).
- Raising any number in a baseline or size lock needs an approval-list row and Kadir (same rule as spec decision 10 in `test_engine_size_budget.py`); lowering needs none.
- No push without Kadir's approval. After any push check `gh run list --repo kadirkayarr-beep/AI-DND` for 'AI-DND bounded verification' and the new quality workflow; no "done" before green.

## Review Focus

1. A baselined finding whose line number moved (edit above it) must stay "old"; keys carry no line numbers. Pinned in Task 1.
2. A second identical finding in the same file (same key) must fail: baseline stores counts, not a set. Task 1.
3. A tool that crashes or prints nothing must be red, never "zero findings". Task 1 and Task 5.
4. A baseline edited upward in a PR must fail (baseline only shrinks versus `origin/main`). Task 2.
5. Windows `\` paths and CRLF in tool output must give the same key as Linux. Task 1.
6. gitleaks output must never echo the secret (`--redact`). Task 6.
7. Tool telemetry, upload and postinstall must be off: a policy test greps the workflow. Task 3.

## File Structure

- Create `ai-dnd/scripts/quality_gate/`: `__init__.py`, `ratchet.py` (finding keys, compare, baseline IO, shrink check, CLI), `tools.json` (exact pins), `baselines/` (one JSON per tool), `vulture_whitelist.py` (generated), `size_lock.json`, `gitleaks-baseline.json`.
- Create tests `ai-dnd/api/tests/test_quality_ratchet.py`, `test_quality_policy.py`, `test_quality_size_budget.py`.
- Create `.github/workflows/ai-dnd-quality.yml`.
- Create `docs/agents/kalite-kapisi.md` (how to read a red job, how to lower a baseline) and `docs/agents/kalite-kapisi-olcum.md` (noise numbers from Task 4).
- Modify `docs/design/YOL_HARITASI.md` (row 4b status) at the end only.
- Spec gap: the spec says the UI is under `ai-dnd/artifacts/`; the real folder is `artifacts/` at repo root (`ai-dnd-web`, `ai-dnd-experience`, `api-server`, `mockup-sandbox`). The plan uses the real folders.

---

### Task 1: Ratchet core

**Files:**
- Create: `ai-dnd/scripts/quality_gate/__init__.py`, `ai-dnd/scripts/quality_gate/ratchet.py`
- Test: `ai-dnd/api/tests/test_quality_ratchet.py`

**Interfaces:**
- Produces:
  - `finding_key(tool: str, path: str, rule: str, name: str) -> str` returns `"tool|posix/path|rule|name"` (backslashes to `/`, strip leading `./`, no line number).
  - `Counts = dict[str, int]`; `count_findings(keys: list[str]) -> Counts`.
  - `compare(baseline: Counts, current: Counts) -> list[str]`: one message per key whose current count exceeds its baseline count (missing = 0); sorted.
  - `load_baseline(path: Path) -> Counts`, `write_baseline(path: Path, counts: Counts) -> None` (sorted keys, `\n` newlines, UTF-8).
  - `parse_ruff(text: str) -> list[str]` (ruff `--output-format json`), `parse_knip(text: str) -> list[str]` (knip `--reporter json`), `parse_fallow(text: str) -> list[str]`: each returns finding keys and raises `ToolOutputError` on empty or non-JSON text.
  - CLI `python -m scripts.quality_gate.ratchet check|update <tool> <report-file>`: `check` exits 1 listing new keys, 2 on `ToolOutputError`; `update` rewrites `baselines/<tool>.json` only when every new count is <= the old one (first creation allowed), else exits 3 "baseline may only shrink".

- [ ] **Step 1: Write failing tests** in `test_quality_ratchet.py`:
  - `test_line_shift_is_not_new`: same ruff finding at line 10, then line 90: `compare(base, cur) == []`.
  - `test_second_identical_finding_is_new`: baseline `{k: 1}`, current `{k: 2}` gives one message naming `k`.
  - `test_new_key_fails_and_fixed_key_passes`.
  - `test_windows_path_and_crlf_same_key`: `finding_key("ruff", "a\\b.py", "F401", "os")` equals the `/` form; a CRLF report parses to the same keys.
  - `test_empty_or_garbage_output_is_an_error`: `parse_ruff("")` and `parse_ruff("Traceback ...")` raise `ToolOutputError`; `parse_ruff("[]")` returns `[]` (a clean run counts only as valid JSON).
  - `test_update_refuses_to_grow`: `update` with a larger count exits 3 and leaves the file unchanged.
- [ ] **Step 2: Run to verify fail.** `slot.sh 9 <WT> test qg1-red 600 api.tests.test_quality_ratchet` plus the neighbor set. Expected: ERROR (module missing).
- [ ] **Step 3: Implement** the interfaces above in `ratchet.py`. Ruff key: `rule` = `code`, `name` = the quoted symbol in `message` (fallback: the message text). Knip/fallow keys: issue type as `rule`, symbol or file as `name`; their real JSON shapes are not verified, so Task 4 fixes those two parsers against real output before Task 7 relies on them.
- [ ] **Step 4: Run to verify pass.** Same command. Expected: all PASS.
- [ ] **Step 5: Commit** the three files by explicit path: `git commit -m "Quality gate: ratchet core (line-free keys, counts, shrink-only baseline)"`.

### Task 2: Baseline-only-shrinks check

**Files:**
- Modify: `ai-dnd/scripts/quality_gate/ratchet.py`
- Test: `ai-dnd/api/tests/test_quality_ratchet.py`

**Interfaces:**
- Consumes: `Counts`, `load_baseline`.
- Produces: `baseline_growth(old: Counts, new: Counts) -> list[str]` (keys added or with a higher count); CLI `check-shrink <baseline-file> <base-ref>` reads the file at `<base-ref>` with `git show <base-ref>:<path>` and exits 1 on growth. File absent at the base ref = first introduction, passes; any other git error exits 2.

- [ ] **Step 1: Write failing tests**: `test_growth_is_listed`, `test_shrink_and_equal_pass`, `test_first_introduction_passes`.
- [ ] **Step 2: Run to verify fail**, label `qg2-red`.
- [ ] **Step 3: Implement** `baseline_growth` and the `check-shrink` subcommand (`subprocess.run([...], check=False)`).
- [ ] **Step 4: Run to verify pass**, label `qg2-green`.
- [ ] **Step 5: Commit** `git commit -m "Quality gate: baselines may only shrink"`.

### Task 3: Tool pins and policy test

**Files:**
- Create: `ai-dnd/scripts/quality_gate/tools.json`
- Test: `ai-dnd/api/tests/test_quality_policy.py`

**Interfaces:**
- Produces: `tools.json` = `{"ruff":"0.17.5","vulture":"2.14","skylos":"x.y.z","knip":"x.y.z","fallow":"x.y.z","gitleaks":{"version":"x.y.z","sha256":"<64 hex>"}}`. skylos, knip, fallow and gitleaks versions are the latest stable release at execution time, looked up in the official repos (`duriantaco/skylos`, `webpro-nl/knip`, `fallow-rs/fallow`, `gitleaks/gitleaks`); the gitleaks sha256 is copied from that release's own `checksums.txt`, never computed from an unverified download.

- [ ] **Step 1: Write failing tests** in `test_quality_policy.py`:
  - `test_pins_are_exact`: every version matches `^\d+\.\d+\.\d+$` (no `^`, `~`, `latest`, range); the sha256 matches `^[0-9a-f]{64}$`; ruff and vulture equal the lines in `scripts/engine_split/requirements-dev.txt`.
  - `test_workflow_forbids_upload_paths`: the text of `.github/workflows/ai-dnd-quality.yml` has no `skylos cloud`, no `--upload`, no `skylos[`, no `jsgoldman`; every `skylos` line has `--no-upload`; every `fallow` step sets `DO_NOT_TRACK: "1"`; the gitleaks line has `--redact` and `--baseline-path` once Task 6 lands; every vulture line has `--min-confidence 80`. Until Task 4 the file is absent and this test is skipped with a message; Task 4 makes absence a failure.
  - `test_no_hooks_added`: no `.pre-commit-config.yaml`, `lefthook.yml` or `.husky/` exists in the repo.
- [ ] **Step 2: Run to verify fail** (`qg3-red`). Expected: FAIL (`tools.json` missing).
- [ ] **Step 3: Write `tools.json`** with the looked-up pins. A version that cannot be verified is written as `KADIR_DOLDURACAK: <tool> exact version` and parked in the debt register; never guessed.
- [ ] **Step 4: Run to verify pass** (`qg3-green`).
- [ ] **Step 5: Commit** `git commit -m "Quality gate: exact tool pins and policy test"`.

### Task 4: Report-only measurement job and noise numbers

**Files:**
- Create: `.github/workflows/ai-dnd-quality.yml`, `docs/agents/kalite-kapisi-olcum.md`
- Modify: `ai-dnd/api/tests/test_quality_policy.py`, `ai-dnd/scripts/quality_gate/ratchet.py` (knip/fallow parsers)

**Interfaces:**
- Consumes: `tools.json`.
- Produces: workflow `AI-DND quality gate` on `pull_request` and `push` to `main`, `permissions: contents: read`, `fetch-depth: 0`, one job `measure` with `continue-on-error: true` that runs every tool and uploads the raw reports as artifact `quality-reports-${{ github.sha }}`. Commands: `ruff check ai-dnd --select F,E9 --output-format json`; `vulture ai-dnd --min-confidence 80`; `skylos ai-dnd --no-upload --trace`; `gitleaks detect --redact --no-banner --report-format json`; knip and fallow via `pnpm dlx <tool>@<pin>` with `npm_config_ignore_scripts=true` (fallow also `DO_NOT_TRACK: "1"`, duplicates/similar-code and coverage not enabled). The gitleaks binary is downloaded at the pinned version and verified with `sha256sum -c` before it runs.

- [ ] **Step 1: Tighten the policy test**: workflow absence now fails. Run (`qg4-red`): FAIL.
- [ ] **Step 2: Write the workflow** (same checkout/python/node/pnpm setup lines as `ai-dnd-ci.yml`; no tests inside). If vulture or skylos errors on Python 3.13, the measurement doc records it and that tool stays report-only.
- [ ] **Step 3: Run the policy test** (`qg4-green`). Pass.
- [ ] **Step 4: Commit** workflow and test, then ask Kadir to approve pushing a draft PR (push needs approval). After approval push, let the workflow run, download the artifact.
- [ ] **Step 5: Write `kalite-kapisi-olcum.md`**: per tool: finding count, top five rule types, how many of at least 20 spot-checked findings (read the cited lines) are false alarms from `game.X` or `sys.modules` patches, run time, whether it ran on Python 3.13, whether any postinstall ran, whether gitleaks printed any value; then one verdict per tool: gate, report-only, or drop. A tool still above 50% false alarms after whitelisting stays report-only. Commit the doc.
- [ ] **Step 6: Fix the knip and fallow parsers** against the real artifact JSON; add one test per parser using a 3-finding excerpt of that JSON. Run (`qg4-parsers`) and commit.

### Task 5: Python gates (ruff and vulture) with baselines

**Files:**
- Create: `ai-dnd/scripts/quality_gate/baselines/ruff.json`, `ai-dnd/scripts/quality_gate/vulture_whitelist.py`
- Modify: `.github/workflows/ai-dnd-quality.yml`, `ai-dnd/api/tests/test_quality_ratchet.py`

**Interfaces:**
- Consumes: `parse_ruff`, `compare`, `check`, `check-shrink`.
- Produces: blocking job `python-gate`. Ruff (rules F and E9 only, no style rules) goes through `ratchet check ruff <report>`. Vulture runs as `vulture ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 80` and must exit 0; the whitelist, generated once with `--make-whitelist`, is the baseline. Real dead code stays whitelisted (deletion is 4c); section comments at the top of the file mark dynamic-call entries (`game.X`, `sys.modules`) versus frozen real findings. The job also runs `check-shrink` on `baselines/ruff.json` against `origin/main`.

- [ ] **Step 1: Write failing tests**: `test_planted_unused_import_is_new` (a ruff JSON with `import os` in a file absent from the baseline gives a non-empty `compare`); `test_vulture_whitelist_has_no_string_literals` (every non-comment line is a bare `name  # unused ...` expression).
- [ ] **Step 2: Run to verify fail** (`qg5-red`).
- [ ] **Step 3: Implement**: wire the job; create `baselines/ruff.json` with `ratchet update ruff <Task-4 report>`; generate the whitelist.
- [ ] **Step 4: Run to verify pass**, then prove the gate bites: on a throwaway branch (never merged) add `import os` to a scratch file under `ai-dnd/`; expect `python-gate` red; a missing or empty tool report must also be red (run once with ruff pointed at a missing path).
- [ ] **Step 5: Commit** by explicit path: `git commit -m "Quality gate: ruff and vulture blocking with baselines"`.

### Task 6: Secret scan gate

**Files:**
- Create: `ai-dnd/scripts/quality_gate/gitleaks-baseline.json`; `.gitleaks.toml` only if Task 4 showed false positives
- Modify: `.github/workflows/ai-dnd-quality.yml`, `ai-dnd/api/tests/test_quality_policy.py`

**Interfaces:**
- Produces: blocking job `secrets-gate`: `gitleaks detect --redact --no-banner --baseline-path ai-dnd/scripts/quality_gate/gitleaks-baseline.json --report-format json --report-path <runner temp>`; any finding outside the baseline exits non-zero. Baseline built from the Task 4 report (made with `--redact`, so no values). Full history (`fetch-depth: 0`).

- [ ] **Step 1: Write failing tests**: `test_gitleaks_baseline_has_no_secret_values` (every `Secret` and `Match` field is `REDACTED` or empty) and `test_gitleaks_step_pinned` (download URL contains the `tools.json` version; a `sha256sum -c` line with the pinned checksum comes before the run). Run (`qg6-red`): FAIL.
- [ ] **Step 2: Add the job and baseline.** If the baseline has any non-redacted value, do not commit it, delete it from the worktree and tell Kadir (a real leaked key must be rotated by its owner; I never read key files).
- [ ] **Step 3: Run to verify pass** (`qg6-green`).
- [ ] **Step 4: Prove it bites** on a throwaway branch that is never merged: commit an obviously fake token-shaped string in a scratch file; expect `secrets-gate` red and the log showing `REDACTED`, not the string.
- [ ] **Step 5: Commit** `git commit -m "Quality gate: gitleaks with pinned binary and baseline"`.

### Task 7: UI gates (knip blocking, fallow and skylos report-only)

**Files:**
- Create: `ai-dnd/scripts/quality_gate/baselines/knip.json`, `ai-dnd/scripts/quality_gate/baselines/fallow.json`
- Modify: `.github/workflows/ai-dnd-quality.yml`, `ai-dnd/api/tests/test_quality_policy.py`, `ai-dnd/api/tests/test_quality_ratchet.py`

**Interfaces:**
- Consumes: `parse_knip`, `parse_fallow`, `check`, `check-shrink`.
- Produces: blocking job `ui-gate`: knip over the `artifacts/*` workspaces (`pnpm dlx knip@<pin> --reporter json`, ratcheted against `baselines/knip.json`, shrink-checked). Non-blocking steps (`continue-on-error: true`): fallow compared with its own `baselines/fallow.json`, and skylos, both printed only.

- [ ] **Step 1: Write failing tests**: `test_knip_new_unused_export_is_new` (Task 4 fixture plus one extra issue gives one new key); `test_report_only_steps_are_marked` (fallow and skylos steps have `continue-on-error: true`; the knip step does not). Run (`qg7-red`): FAIL.
- [ ] **Step 2: Implement** the job; generate both baselines with `ratchet update` from the Task 4 artifact.
- [ ] **Step 3: Run to verify pass** (`qg7-green`).
- [ ] **Step 4: Prove knip bites** on a throwaway branch with an unused exported function in `artifacts/ai-dnd-web/src/`; knip runs by `dlx`, so the workspace lock file is untouched and never named in a git command.
- [ ] **Step 5: Commit.**

### Task 8: Size ratchet for non-engine Python and the UI

**Files:**
- Create: `ai-dnd/scripts/quality_gate/size_lock.json`, `ai-dnd/api/tests/test_quality_size_budget.py`

**Interfaces:**
- Consumes: `budget_findings`, `long_function_findings` imported from `api.tests.test_engine_size_budget` (not copied); `top_level_index` from `engine_split.inventory`.
- Produces: `size_lock.json` shaped like `size_budget.json` (`files`, `part_max` 2500, `slack` 50, `long_function_min` 151, `long_functions` keyed `<file>::<name>`) plus `ts_files` (line count only). Covers every `ai-dnd/**/*.py` outside the engine lock (engine = `game.py` and `game_parts/*.py`; exclude `scripts/engine_split/batches`) and `artifacts/*/src/**/*.ts(x)`. Test helpers: `real_python_sizes() -> dict[str, int]`, `real_python_function_lengths() -> dict[str, int]`, `real_ts_sizes() -> dict[str, int]`.

- [ ] **Step 1: Write failing tests**: `test_non_engine_python_fits_its_lock`; `test_ui_ts_fits_its_lock`; `test_one_line_over_is_red` (a Python and a TS file); `test_a_budget_cannot_hoard_room` (slack 50, both sides); `test_new_big_file_without_entry_is_red` (2501 lines); `test_new_long_function_is_red` (151 red, 150 ok); `test_lock_values_match_spec` asserting `(2500, 50, 151)`; `test_engine_files_not_double_counted`.
- [ ] **Step 2: Run to verify fail** (`qg8-red`): lock file missing.
- [ ] **Step 3: Generate `size_lock.json`** with a throwaway script run once and not committed: it measures today's sizes with the test's own `real_*` helpers and writes budgets equal to current sizes. Commit only the JSON.
- [ ] **Step 4: Run to verify pass**, together with `api.tests.test_engine_size_budget` (engine lock unaffected).
- [ ] **Step 5: Commit** `git commit -m "Quality gate: size ratchet for non-engine Python and UI"`.

### Task 9: Flip to blocking, docs, handoff

**Files:**
- Modify: `.github/workflows/ai-dnd-quality.yml`, `docs/design/YOL_HARITASI.md`
- Create: `docs/agents/kalite-kapisi.md`

- [ ] **Step 1: Remove any leftover `continue-on-error`** from `python-gate`, `secrets-gate` and the knip step; remove the `measure` job; fallow and skylos stay report-only. Run the policy test (`qg9-green`).
- [ ] **Step 2: Write `kalite-kapisi.md`** in short plain Turkish: which job guards what; how to read a red job; how to lower a baseline (`ratchet update` refuses growth); raising needs Kadir; real dead code goes only through a debt row, a test and a commit.
- [ ] **Step 3: Run the final set** `slot.sh 9 <WT> test qg9-final 900 api.tests.test_quality_ratchet api.tests.test_quality_policy api.tests.test_quality_size_budget api.tests.test_engine_size_budget` plus the neighbor set; also the structural health check if it runs in the slot. Show the output before claiming done.
- [ ] **Step 3b: Required check.** Ask Kadir to mark the three quality jobs as required status checks (repo setting, owner action); until then the gate warns but cannot block a merge.
- [ ] **Step 4: Update `YOL_HARITASI.md` row 4b** status to "kod tamam, PR bekliyor" (no play needed: S9). Commit.
- [ ] **Step 5: With Kadir's push approval**, push, open the PR, check `gh run list` for both workflows; no "done" before green. Copy the Task 4 answers on the spec's unverified items (postinstall, Python 3.13, telemetry) into the debt register.
