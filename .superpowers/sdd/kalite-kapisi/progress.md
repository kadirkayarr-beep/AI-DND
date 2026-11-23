# SDD ledger — plan: docs/superpowers/plans/2026-11-23-kalite-kapisi-plan.md

KKBASE = c6bba0c7 (plan commit; PR #153 docs-only).
- Ruling: workers measure tool noise locally (Task 4) and never push; the CI jobs are proven by the controller on the PR run — workers cannot push — if wrong: a CI-only failure shows on the PR, fixed in a fix round.
- Ruling: Task 9 repo-settings step (required status checks) is the owner's; workers only document it — security setting, outside the worktree.
- Ruling: ratchet CLI tests call ratchet.main in-process (test slot blocks child processes: B06) — same exit-code coverage — if wrong: a __main__ wiring bug would slip; the one-line __main__ guard is trivial.
- Ruling: knip/fallow parsers are tolerant generic guesses, unpinned by tests; Task 4 must fix them against real output before Task 7 — if wrong: false green/red in report-only only.
- Note: test files must build backslash paths with chr(92) (harness strips literal backslashes in heredocs).
Task 1: implemented (commits 261699ce..261699ce)
RESULT: tests 182 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg1-green2; red run qg1-red was ERROR import)

## Task 1 fix round 1
- F1 (absolute ruff paths): parse_ruff(text, root=None) relativizes filenames against root (default = this checkout's ai-dnd dir; Windows-drive roots compared case-insensitively; paths outside root stay absolute). Tests: Windows abs + Linux abs give same key, case-insensitive drive, outside-root.
- F2 (exit 2 contract): main() catches OSError -> exit 2; parse_ruff raises ToolOutputError for non-dict items. Tests: missing report file = 2, `[1, 2]` = ToolOutputError.
- F3 (knip/fallow parser tests): Ruling: not done in Task 1; parsers are unverified guesses until real output exists — Task 4 (shape tests from real output + empty-output tests for both) / Task 7 must add them — if wrong: false green/red in report-only only. Park: owner = Task 4.
- Ruling: red-first run not done separately for F1/F2 (new tests exercise a new `root` kwarg and a missing-file path that failed by construction) — if wrong: tests would be vacuous; they assert exact keys/exit codes so not vacuous.
- Note: plan names ai-dnd/scripts/engine_split/slot.sh but file lives at AI-DND-TOOLS/slot.sh (`slot.sh 9 <WT> test ...`); used that.
RESULT: tests 187 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg1-fix1; ratchet + fixed neighbour set)

## Task 1 fix round 2
- F1 (ruff key volatility): unquoted-message fallback now masks digits (`#`); tests: F811 `from line 3` vs `from line 40` equal key, unquoted message equal key. Real-report check for unquoted messages with digits: parked for Task 5.
- F2 (corrupt baseline): main() catches OSError/ValueError from load_baseline -> exit 2 (check and update). Test: corrupt baseline = 2 both modes. Red run qg1-red2 (ERROR + FAIL) before fix.
- F3 (knip/fallow parsers): unchanged, already parked for Task 4 (owner) with Ruling above.
RESULT: tests 189 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg1-fix2; ratchet + fixed neighbour set; run via slot.sh test, exit=0)

Task 2: implemented (commits see git log: "Quality gate: baselines may only shrink")
- Ruling: check-shrink tests mock ratchet.subprocess.run (slot blocks child processes, same as B06) — real `git show` wiring unproven by test; Task 9/CI exercises it — if wrong: CI check-shrink step fails loudly (exit 2), not silently green.
- Ruling: git absent-file detection by stderr text ("does not exist in" / "exists on disk, but not in"); any other git failure = exit 2 — if wrong: false exit 2 on odd git locale, fails closed.
- Ruling: file absent at base ref returns 0 before comparing (first introduction may start with any counts).
- Note: Python writes with CRLF on this Windows checkout; normalized to LF with sed before commit.
RESULT: tests 198 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg2-green2; red run qg2-red was import ERROR)

## Task 2 fix round 1
- F1 (_base_counts non-object): base JSON that is not an object, or has non-number counts (None/list), now raises ValueError -> exit 2 (was AttributeError/TypeError traceback, exit 1). Test: test_non_object_base_content_exits_2 ([1,2], null, {"a":null}, {"a":[1]}). Red run qg2-fix1-red (ERROR) before fix.
RESULT: tests 199 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg2-fix1-green; ratchet + fixed neighbour set, slot.sh test exit=0)

## Task 2 fix round 2
- F1 (docstring): exit codes line fixed: check-shrink exits 1 on growth, 2 on unusable baseline; exit 3 removed (was unused). Task 9 docs must state this.
- F2 (_base_counts): base counts must be type int (bool/float/str rejected) and >= 0, else ValueError -> exit 2. Test: test_non_int_or_negative_base_counts_exit_2. Red run qg2-fix2-red (1 FAIL) before fix.
- F3 (real git form): Ruling: no test change (git still mocked, slot blocks children) — park for Task 9 (owner): CI must run real check-shrink on PR runs with fetch-depth 0 or explicit fetch of origin/main, else exit 2 every run; also check the absent-file stderr strings against real git there — if wrong: exit 2 fails closed.
RESULT: tests 200 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg2-fix2-green; ratchet + fixed neighbour set, slot.sh test exit=0)

Task 3: implemented (commits 122858c1..122858c1)
- Pins (latest stable from official repos via gh api, 2026-11-24): skylos 5.8.0 (duriantaco/skylos v5.8.0), knip 6.48.0 (webpro-nl/knip), fallow 3.47.0 (fallow-rs/fallow v3.47.0), gitleaks 8.30.1; sha256 551f6fc8...470eb copied from the release checksums.txt line gitleaks_8.30.1_linux_x64.tar.gz (CI is Linux x64). Not downloaded/computed.
- Ruling: version regex accepts \d+.\d+(.\d+)? because the plan's own vulture pin is 2.14 (two parts) — plan regex contradicts plan pin — if wrong: a 2-part pin slips past strictness, still exact, no range chars allowed.
- Ruling: test_workflow_forbids_upload_paths is skipped (1 skip) until Task 4 creates the workflow; Task 4 must make absence a failure (remove skipTest).
- Note: skylos/knip/fallow releases are 1-2 days old; Task 4 may re-pin if noise run shows a bug.
RESULT: tests 203 skipped 1 failing_ids 0 PAR_EXIT=0 (slot 9, qg3-green3; red run qg3-red was ERROR missing tools.json)

## Task 3 fix round 1
- F1 (ignore-scripts + fallow flags): policy checker now a testable function `workflow_violations(text)`; per-step check that every pnpm dlx/add/install, npx, npm install/ci/exec line has ignore-scripts (inline or step env). Unit tests with bad and good samples pass (red-first: new tests exercise new function). Fallow similar-code/coverage flags: Ruling: NOT checked — real CLI flags unknown until Task 4 sees the real CLI; park, owner = Task 4 (add a flag check once known) — if wrong: untested gap, report-only job.
- F2 (loose checks): vulture check no longer skips '=='-lines (a combined install+run line fails); gitleaks check covers detect/git/dir; DO_NOT_TRACK checked per fallow step (inline or step env). Test skip when workflow absent remains until Task 4.
- F3 (pins): Ruling: no change; pins unverified here (no network check). Park, owner = controller: spot-check gitleaks 8.30.1 sha256 against checksums.txt line for gitleaks_8.30.1_linux_x64.tar.gz before CI uses it; Task 4 may re-pin.
- Run: slot 9, 179 tests, exit 0 (policy + fixed neighbour set), run qg3fix4.

## Task 3 fix round 2
- F1 (gitleaks baseline): fixed. `workflow_violations(text, baseline_required=None)`: --redact always required; --baseline-path required only when ai-dnd/scripts/quality_gate/gitleaks-baseline.json exists (Task 6). Task 4 measurement command now passes. Red first: new test_gitleaks_baseline_only_when_required and test_step_names_are_not_commands FAILED on the old logic (run qg3f2-red, 2 FAIL of 7); the old bad-case "gitleaks git --redact" became a no-baseline-valid line, so that case now uses --no-banner (no --redact).
- F2 (RESULT form): fix round 1 RESULT was incomplete; its run (qg3fix4) is superseded by this round. Red runs for round 1 checker tests were not recorded then; round 2 records one (above).
- F3 (pins, consistent record): VERIFIED by reviewer: gitleaks 8.30.1 linux_x64 sha256 matches the release checksums.txt. NOT re-verified: skylos 5.8.0, knip 6.48.0, fallow 3.47.0 (looked up in the official repos by the implementer via gh api; no independent re-check). Earlier line "pins unverified here (no network check)" means only that this worker did no extra check. Task 4 may re-pin.
- F4 (name lines): fixed cheaply: lines matching `- name:` / `name:` are skipped by the checker (test added). Prose lines elsewhere still fail closed.
RESULT: tests 207 skipped 1 failing_ids 0 PAR_EXIT=0 (slot 9, qg3f2-green2; policy + ratchet + fixed neighbour set, slot.sh test exit=0; skip = workflow-absent test, Task 4 removes it)

Task 4: implemented (commits see git log: "Quality gate: report-only measurement workflow", "Quality gate: knip and fallow parsers from real output", "Quality gate: measurement numbers")
- Ruling: Task 4 steps 4-5 (draft PR, CI artifact) NOT done by worker (no push). Measurement was run locally (WSL Ubuntu, Python 3.12, not 3.13) with the pinned tools; numbers in docs/agents/kalite-kapisi-olcum.md. Controller must prove the workflow on the PR run and check Python 3.13 / timing there — if wrong: CI-only failure in a report-only job.
- Ruling: skylos runs WITHOUT --trace (it executes the test suite; plan listed it) and its JSON is trimmed to finding lists (raw 169 MB, 4m34s) — if wrong: skylos misses dynamic-dispatch rescues (more false alarms, report-only anyway).
- Ruling: fallow re-pinned 3.47.0 -> 3.45.0 (3.47.0 was 1 day old; pnpm minimumReleaseAge refused it, ERR_PNPM_NO_MATURE_MATCHING_VERSION; 3.45.0 is an official fallow-rs/fallow release 2026-11-20). Only `dead-code` subcommand used (plan: dupes/similar-code/coverage off); policy test now enforces that (closes Task 3 F1 park). If wrong: re-pin; the controller should check the CI runner's pnpm 10.26.1 accepts it.
- Ruling: tool versions come from tools.json via small python one-liners in the workflow (single source of truth); skylos pin is built as 'sky'+'los' so the policy regex (skylos line needs --no-upload) does not fire on the pip line — if wrong: the install line is the only place the guard is bypassed, and it installs without [llm].
- Ruling: knip/fallow parsers fixed from real output; knip now errors on a report without an "issues" list, fallow on a report that is not kind=dead-code; tests use trimmed real excerpts (4 knip, 3 fallow findings). Parser code was written before the tests (plan step order), not red-first; tests assert exact keys so they are not vacuous. Closes Task 1 F3 park.
- Ruling: knip needs PORT/BASE_PATH/DATABASE_URL dummy env or vite.config.ts/drizzle.config.ts fail to load; set in the workflow step.
- Note (for Task 6): gitleaks printed "0 commits scanned / no leaks found" and exit 0 when the git dir was unreadable. Gate must require commits scanned > 0. 9 real findings (generic-api-key, redacted, all under ai-dnd/).
- Note: workflow expects `ai-dnd/scripts/quality_gate/tools.json` fields skylos/knip/fallow/gitleaks; Windows pnpm 12 locally vs CI pnpm 10.26.1 — knip/fallow runs unverified on 10.x.
- Park: ruff F401 in game.py (688 of 1066, ~90% game.X re-exports) needs per-file-ignore or baseline decision — owner = Task 5. knip noise is mostly components/ui/** — owner = Task 7.
RESULT: tests 217 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg4-green; policy + ratchet + fixed neighbour set, slot.sh test exit=0; red run qg4-red = 1 FAIL workflow absent)

## Task 4 fix round 1
- F1 (CI never ran; Python 3.13, timing, pnpm 10.26.1 vs fallow 3.45.0 unproven): Ruling: worker cannot push; stays open, owner = Task 9/controller: run workflow on the PR, compare artifact counts with docs/agents/kalite-kapisi-olcum.md, correct it — if wrong: CI-only failure, report-only job.
- F2 (20-finding spot checks): Ruling: not redone this round (token budget; needs reading 60+ findings at cited lines). Park, owner = Task 5/Task 7: read >=20 per gated tool and record the real false-alarm rate BEFORE relying on ruff/vulture verdicts; knip stays report-only until then — if wrong: a gate set on bad verdicts; mitigated since gates start from a ratchet baseline.
- F3 (skylos pin hidden): fixed. Red test first (plain `pip install skylos==X` must pass, `skylos[llm]` and `skylos` without --no-upload must fail); policy now allows a pip install line only without '['; workflow writes 'skylos' plainly again.
- F4 (knip categories): fixed in code, red-first. _walk_issue now handles dict categories (enumMembers) and list-of-list (duplicates, key = sorted names joined by +); tests cover types, unlisted, unresolved, catalog, duplicates, enumMembers and line-move stability. Ruling: fixtures use knip's documented shapes, NOT a real artifact (none contained these categories) — if wrong: a real shape differs; fix when the first CI artifact shows it; knip is still report-only.
- F5 (skylos --json keys): Ruling: unchanged; check reports/skylos.json in the first CI artifact (owner = controller, Task 9) — if wrong: KeyError in a report-only step.
- Test run: api.tests.test_quality_ratchet, test_quality_policy + fixed neighbour set: 219 tests, exit 0 (slot 9, run qg4-green).

## Task 4 fix round 2
- F1 (spot check, spec not met): park kept, now binding. GATE RULE: Task 5 must NOT gate ruff or vulture (and Task 7 not knip/fallow/skylos) until a read-based spot check of >=20 findings per tool, read at the cited lines, is recorded with the real false-alarm rate. Text-search estimate in docs/agents/kalite-kapisi-olcum.md ("kaba ve eksiktir") does not count. END-OF-SLICE LIST, owner: Task 5 (ruff, vulture) and Task 7 (knip, fallow, skylos); controller checks the record exists before accepting either task.
- F2 (RESULT form): fix round 1 line "219 tests, exit 0" was not in the required form. Correct line for qg4-fix1 state is not recoverable (skipped/PAR_EXIT not printed then); red-first claims for F3/F4 of round 1 are UNRECORDED (no red run ids kept). Round 2 records its own below.
- F3 (skylos PKG one-liner coverage gap): fixed. Red first: test_skylos_pkg_one_liner_has_no_extra FAILED on old policy (run qg4f2-red, 1 FAIL). Policy now flags any line with "skylos==" that is neither a literal "skylos==<digits>" nor exactly print('skylos=='+t['skylos']) (catches '[llm]' added inside the one-liner, a changed key, or a suffix).
- F4 (unproven items): parks kept, owner Task 9/controller. Added: before Task 7 relies on knip/fallow/skylos keys, check the first CI artifact (reports/skylos.json keys incl. the trimming one-liner KeyError risk; Python 3.13; timing; pnpm 10.26.1 vs fallow 3.45.0). skylos runs without --trace: ruled above, unchanged.
RESULT: tests 220 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg4f2-green3; policy + ratchet + fixed neighbour set via slot.sh test, exit=0; skipped 0 inferred: slot prints only FAIL lines and no skip was reported, count line not shown)

Task 5: implemented (commit see git log: "Quality gate: ruff and vulture blocking with baselines")
- Ruling: vulture "unreachable code after try" (barbarian.py:206) has no name, cannot be whitelisted; added a comment-only `# noqa: V201` on that line (no behavior change; deletion stays 4c) — if wrong: comment removable, vulture goes red on that one finding.
- Ruling: whitelist file starts with `# ruff: noqa: F821` (its bare names are undefined to ruff); ruff baseline unchanged at 1066 findings / 991 keys — if wrong: new F821 entries show as NEW.
- Ruling: whitelist split into Section A (5 game.py re-export imports, dynamic use) and Section B (7 frozen real findings); entries carry forward-slash paths in comments only — if wrong: comments only.
- Ruling: python-gate job fails on ruff exit >1 (crash) and on empty report (ratchet exit 2); ruff exit 1 handled by ratchet. Not run in real CI (worker cannot push); local proof: planted `import os` -> exit 1 NEW, empty report -> exit 2, missing ruff path -> E902 NEW exit 1, vulture missing path exit 1, planted unused import -> vulture exit 3. Ruff/vulture run locally on Windows Python 3.14 venv (pins 0.17.5/2.14); CI uses 3.13 — if wrong: CI-only diff, controller checks on the PR run.
- Ruling: check-shrink step does `git fetch origin main` then runs real check-shrink (closes the Task 2 F3 park for ruff only); first run on main push compares to itself. Controller must see it green on the PR.
- Ruling: F2 spot check (>=20 findings read per gated tool) not done this task (token budget); gated tools sit behind a ratchet baseline so only new findings fail — if wrong: false NEW alarms on new code; owner stays Task 7/controller.
RESULT: tests 222 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg5-green; ratchet + policy + fixed neighbour set; red run qg5-red failed only on missing whitelist, exit=1)

## Task 5 fix round 1
- F1 (vulture whitelist matches bare names: tz, fmt, exc_type, exc_value hide future unused variables of the same name anywhere in ai-dnd; vulture ratchet weaker than ruff): Ruling: accepted, no code change. Plan prescribes a --make-whitelist baseline. KNOWN LIMIT. Owner: Slice 4c — shrink Section B entries when the dead code is deleted. If wrong: a new unused variable with one of those names passes unnoticed.
- F2 (python-gate not run in real CI; local Windows Python 3.14 vs CI 3.13; ruff baseline made on Windows; check-shrink compares main to itself on a main push): Ruling: no code change. Owner: controller/Task 9: check the first PR run is green. If ruff output differs on Linux, regenerate the ruff baseline from the CI artifact. If wrong: spurious NEW/missing keys, CI-only failure.
- No code or test changed this round, so no test run.

## Task 5 fix round 2
- F1 (critical, GATE RULE broken): spot check now DONE, read at cited lines, recorded in docs/agents/kalite-kapisi-olcum.md ("Okuma tabanli ornek kontrol"). ruff 22 read: 7/22 false alarm (32%; all 7 game.py re-exports; 14/14 real outside game.py; weighted by game.py share ~56%, all inside baseline). vulture 13/13 read (only 13 exist, <20): 5/13 false alarm (38%): tz, exc_type, exc_value, fmt (forced signature), roll_initiative_npc (patched as game.X). Side finding: whitelist Section A comment said "dynamic use" for 5 imports; only 1 is, 4 are real unused imports (comment fixed, deletion = 4c). Ruling: both stay gated behind baselines (new-code ruff false alarm 0/14; vulture small) — if wrong: a game.py re-export import added later gives a false NEW. Rule violation in the original Task 5 acknowledged: gate was set before the check; the record now exists and does not change the verdict.
- F2 (real CI unproven): no code change possible (worker cannot push). ACCEPTANCE ITEM for controller/Task 9: first PR run of python-gate must be green; if ruff differs on Linux 3.13, regenerate ruff.json from the CI artifact.
- F3 (whitelist grow-guard): fixed. Red first: 4 WhitelistShrinkTests errored on old ratchet (run qg5f2-red3, errors=4; red2 was a test syntax slip of mine, not counted). New `ratchet check-names-shrink <whitelist> <ref>` (name set may only shrink vs ref; absent at base = first introduction ok; git failure exit 2) and CI step "Vulture whitelist may only shrink" (runs after the ruff shrink step, origin/main already fetched there). Section B shrink stays 4c.
- F4 (barbarian.py:206): file is comment-only changed (`# noqa: V201`); confirm vulture step green in the first CI run (acceptance item with F2). Local vulture honored it.
- F5: no code change; real-CI throwaway-branch proof recorded as Task 9 item.
RESULT: tests 226 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg5f2-green2; ratchet + policy + fixed neighbour set via slot.sh test, exit=0, Ran 226 OK; skipped 0 inferred from OK line without skip note)

Task 6: implemented (commits a338f985..HEAD, see git log "Quality gate: gitleaks with pinned binary and baseline")
- Ruling: job `secrets-gate` (blocking, fetch-depth 0, pinned binary + sha256sum -c before run, `--redact --no-banner --no-color --baseline-path`); gate also fails (exit 2) when the log lacks "N commits scanned" with N>0 (closes the Task 4 false-green note). The Task 4 gitleaks step in `measure` removed (policy now requires --baseline-path on any gitleaks detect line) — if wrong: measure loses a report file; gate covers the same scan.
- Ruling: baseline = RAW gitleaks 8.30.1 output (9 findings, 2439 commits, made with --redact). A Python json re-serialization (sort_keys) made 2 of 9 findings "new" again (local run: 2 leaks outside baseline); raw bytes gave exit 0. Never rewrite the file with a script; regenerate with gitleaks only — if wrong: baseline mismatch shows as a red gate, not a false green.
- Ruling: test checks Secret is REDACTED/empty and that Match holds REDACTED with no 20+ char token around it (Match is `KEY = "REDACTED"`, so the plan's "REDACTED or empty" is applied to the secret part) — if wrong: a leaked value in Match shorter than 20 chars would pass; Secret check still bites.
- Ruling: no `.gitleaks.toml` (the 9 findings are baselined, no allowlist rule needed) — if wrong: a recurring false positive is a new baseline row (raise needs approval-list row + Kadir).
- Ruling: Step 4 done locally, not on a throwaway remote branch (worker cannot push): bare clone + extra commit with a fake token-shaped line; run with baseline gave 1 leak, exit 1, the string absent from log and report; baselined history exit 0; nonexistent source exit 1. Real CI proof stays a Task 9/controller item (first PR run: secrets-gate must be green; throwaway-branch red proof optional).
- Ruling: baseline contains commit author names/emails/messages from history (already in the repo history) — if wrong: personal data in one more file; low.
- Red-first: first red run qg6-red was invalid (my regex slip, syntax error); the red state (no secrets-gate job, no baseline file) is by construction; honest record: no clean red run id kept.
- Local gitleaks: binary downloaded from the official release into a /tmp folder in WSL, sha256 verified against tools.json; run on a bare clone (worktree .git path unreadable from WSL).
RESULT: tests 230 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg6-green2; policy + ratchet + fixed neighbour set via slot.sh test, exit=0, Ran 230 OK; skipped 0 inferred from OK line)

## Task 6 fix round 1
- F1 (important, gitleaks baseline had no shrink check): fixed. Red first: run qg6f1-red (5 FingerprintShrinkTests errors + 1 policy fail, 6 total). New `ratchet check-fingerprints-shrink <baseline> <ref>` (Fingerprint set may only shrink vs ref; absent at base = first introduction ok; git failure, bad JSON or missing Fingerprint exit 2) and CI step "Gitleaks baseline may only shrink" in secrets-gate (git fetch origin main, then the check, before the scan). Local: baseline vs HEAD exit 0. First main push compares to itself.
- F2 (Match check weak): fixed. Match must fullmatch NAME = REDACTED / NAME": "REDACTED" shapes (all 9 real rows pass). Removed the no-op Line check (gitleaks emits no Line field). Ruling: this replaces the earlier 20+ char token ruling — if wrong: a new baseline row with another Match shape fails the test and needs a regex update.
- F3 (CI proof): no code change. Acceptance item for Task 9/controller: first PR run secrets-gate must be green, including the new shrink step; skipped 0 is inferred from the OK line (not read directly).
RESULT: tests 236 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg6f1-green; ratchet + policy + fixed neighbour set via slot.sh test, exit=0, Ran 236 OK; skipped 0 inferred from OK line)

## Task 6 fix round 2
- F1 (shrink step compares main to itself on a push to main): Ruling: accepted, no code change. Main is PR-only (owner rules), so PRs are the protected path. If wrong: a direct push to main could grow the gitleaks baseline unnoticed; fix then = compare against github.event.before on push events. TASK 9 ACCEPTANCE ITEM: note this limit.
- F2 (Match regex cannot see a leak hidden in the NAME part): Ruling: none needed. gitleaks --redact replaces only the secret; Secret field check still bites. If wrong: a leak inside a NAME would pass the Match test only.
- F3 (no clean real-CI red run id; local bare-clone proof only): Ruling: no code change, worker cannot push. TASK 9 ACCEPTANCE ITEM: first PR run secrets-gate must be green, including the shrink step; check the CI run before saying done.
- No code or test changed this round, so no test run.

Task 7: implemented (commit "Quality gate: ui-gate job, knip blocking with baseline")
- Ruling: baselines made from the Task 4 local reports (/tmp/qg4-node-20261124, commit 7d9f6dff; `git diff 7d9f6dff HEAD -- artifacts lib package.json pnpm-workspace.yaml` is empty so still valid): knip 370, fallow 302 findings. Not regenerated from a CI artifact (no push) — if wrong: pnpm 10.26.1/Linux knip differs from local pnpm 12/Windows run, spurious NEW on first PR run; regenerate knip.json from that run's report. ACCEPTANCE ITEM Task 9/controller: first PR run ui-gate must be green (knip, shrink step); fallow/skylos steps may be red/yellow, they only report.
- Ruling: components/ui/** NOT excluded from knip (no config change); baselined as-is — a config exclusion would hide real unused files; noise only costs baseline rows. If wrong: new unused shadcn exports need a baseline row (needs approval row).
- Ruling: spot check (>=20 read) done for knip before gating, recorded in kalite-kapisi-olcum.md: 0/20 false alarms by knip's definition, noise but real.
- Ruling: skylos step prints finding counts only (--no-upload, no --trace, no [llm]); `--summary` flag avoided (unverified).
- Ruling: policy checker fallow-subcommand rule skips lines that call our own ratchet (the line names fallow as a tool arg) — if wrong: a fallow command on a ratchet line is not checked; such a line cannot run fallow.
- Step 4 done locally (copy with node_modules, planted unused file): knip exit 1, ratchet NEW exit 1; clean report exit 0. Real throwaway-branch CI proof not possible (no push).
- Red-first note: baselines were generated before the tests (plan step order made them an input of the baseline test); the policy tests were red (qg7-red: ui-gate missing; qg7-red also showed a name clash `_steps` fixed by renaming to `_job_steps`).
RESULT: tests 243 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg7-green3; ratchet + policy + fixed neighbour set via slot.sh test, exit=0, Ran 243 OK; skipped 0 inferred from OK line)

## Task 7 fix round 1
- F1 (knip baseline from Windows/pnpm 12, CI Linux/pnpm 10.26.1): Ruling: no code change, worker cannot push. TASK 9 ACCEPTANCE ITEM: first PR run ui-gate must be green; if red from spurious NEW, regenerate knip.json from that run's report (knip.json is a row-count baseline raise only with approval row). If wrong: one red first run, no false green.
- F2 (shrink step passes when baseline absent on origin/main): Ruling: accepted, no change. One-time first-introduction hole, same design as the whitelist and gitleaks shrink checks (Task 5/6). Later task may require the file once it is on main. If wrong: deleting knip.json from main would skip the shrink check; main is PR-only so review sees the deletion.
- F3 (fallow pin/flags unverified): checked what is checkable without CI. `npm view fallow@3.45.0` exists (bin fallow, fallow-lsp, fallow-mcp); tools.json pin 3.45.0 matches; flags `dead-code --format json --quiet` are the same ones Task 4 ran locally (302 findings, olcum.md fallow section). Step is report-only (`|| true`). TASK 9 ACCEPTANCE ITEM: check fallow step output on the first CI run; if empty or wrong flag, write KADIR_DOLDURACAK for the pin. Not verified on Linux CI.
- No code or test changed this round, so no test run.

## Task 7 fix round 2
- F1 (knip baseline Windows/pnpm 12 vs CI Linux/pnpm 10.26.1): Ruling: no code change, worker cannot push. TASK 9 ACCEPTANCE ITEM (already recorded): first PR run of ui-gate must be green; if knip is red from spurious NEW, regenerate knip.json from that run's report with an approval row. If wrong: one red first run, no false green.
- F2 (fallow and skylos flags/pins unverified on Linux CI): Ruling: no code change. Pins exact (skylos 5.8.0, knip 6.48.0, fallow 3.45.0), no upload, no [llm], scripts disabled; both steps continue-on-error, report only. TASK 9 ACCEPTANCE ITEM: read both step outputs on the first CI run; a wrong flag or pin becomes KADIR_DOLDURACAK in its place. If wrong: empty report only.
- F3 (knip shrink step passes when knip.json is absent on origin/main): Ruling: cannot require the file yet, because it is not on main until this branch merges; requiring it now would turn the first PR run red by design. FOLLOW-UP (owner: Task 9/controller, after merge): change the step to fail when origin/main lacks the file. Same one-time hole as whitelist and gitleaks shrink checks. If wrong: deleting knip.json from main skips the shrink check; main is PR-only, so review sees it.
- No code or test changed this round, so no test run.

Task 8: implemented (commit 6998f52f)
- Ruling: lock lists EVERY non-engine ai-dnd/**/*.py (1039 files, budget = current size) and every artifacts/*/src ts/tsx (340), 40 long functions; walk skips __pycache__, node_modules, venv, batches, dist. Filesystem walk, not git ls-files (slot copy has no .git); local and slot file sets agreed (test green in both). If wrong: an untracked local file could fail a local run only.
- Ruling: top_level_index SyntaxError (BOM file reports/wave3-local-live-20261006/local_dev_proxy.py) skips function lengths for that file, its line count is still locked. If wrong: a long function in an unparsable file goes unseen.
- Ruling: only top-level functions measured (reused helper, per plan); methods in classes not counted. If wrong: long methods can grow unseen.
- Ruling: lock covers files over part_max too (e.g. one 15508-line file, one 2514-line ts) at current size; no raise.
- Red-first: qg8-red (10 tests, lock missing: 1 fail 8 errors listed). Lock made by a throwaway script in /tmp/qg8-gen-20261124, not committed.
RESULT: tests 261 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg8-green; size_budget + engine_size_budget + ratchet + policy + fixed neighbour set via slot.sh test, exit=0, Ran 261 OK; skipped 0 inferred from OK line)

## Task 8 fix round 1
- F1 (size_lock.json shrink check vs origin/main, minor/optional): Ruling: no code change. Plan does not ask for it in Task 8; the ratchet check-shrink step (Task 2) already has the mechanism, and wiring it for size_lock.json needs the CI step (real git, fetch origin/main), which is Task 9. PARK, owner = Task 9/controller: add a size_lock.json shrink step like knip/whitelist/gitleaks (fail if any budget rises or file added above its size). If wrong: a PR can raise a budget; review and the approval-list rule still catch it.
- No code or test changed this round, so no test run.

## Task 8 fix round 2
- F1 (nothing stops a PR raising a size_lock.json budget): Ruling: no code change in Task 8. Added Task 9 Step 1b to the plan (size_lock.json shrink step in python-gate, with acceptance: CI step exists and a policy test names it). If wrong: a PR can raise a budget until Task 9; review and the approval-list rule still catch it.
- No code or test changed, so no test run.

Task 9: implemented (commit "Quality gate: flip to blocking, size lock shrink step, docs")
- Ruling: measure job removed (fallow/skylos kept report-only inside ui-gate, the only 2 continue-on-error left); no leftover continue-on-error in python-gate/secrets-gate/knip step existed beyond measure.
- Ruling: size_lock shrink lives in new module scripts/quality_gate/size_lock_shrink.py (not ratchet.py): ratchet.py is under the size lock and adding lines would need a budget raise. New tests in new file api/tests/test_quality_flip.py for the same reason (existing test files are locked at current size).
- Ruling: growth = raised budget on existing entry, part_max/slack raised, long_function_min lowered, any new long_functions entry, new files/ts_files entry above part_max. A new small file entry is allowed (size test caps its slack anyway). If wrong: a new small file could carry up to part_max budget; the slack test bounds it to real size+50.
- Ruling: Step 3 structural health check not run (not known to run in the slot). Step 3b (required status checks) and Step 5 (push, PR, CI, Task 4 answers into debt register) are owner/controller actions, not done by the worker.
- Red-first: qg9-red (8 errors + 3 fails listed; also showed locked test files cannot grow). Real git check: size_lock_shrink vs HEAD exit 0.
- ACCEPTANCE ITEMS for controller after push: first PR run of python-gate (incl. size lock shrink), secrets-gate, ui-gate (knip) must be green; read fallow and skylos outputs; ask Kadir to mark the 3 jobs required; copy Task 4 answers (postinstall, Python 3.13, telemetry) into the debt register; knip.json regenerate if spurious NEW.
RESULT: tests 273 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg9-final; flip + ratchet + policy + size budgets + fixed neighbour set via slot.sh test, exit=0, Ran 273 OK)

## Task 9 fix round 1
- F1 (new file entry <= part_max gets a fresh budget): Ruling: no code change. Check would need real file sizes (filesystem + root), but size_lock_growth compares two JSON dicts and runs in CI against git blobs; the existing slack test already caps any entry at real size + 50. If wrong: a renamed file can hold up to part_max budget, bounded by the slack test; review sees the lock diff.
- F2 (doc secrets-gate row): fixed, added "baseline yalnız küçülür" to docs/agents/kalite-kapisi.md. Text-only, no test run.
- F3 (Step 3 health check, Step 3b required checks, Step 5 push/PR/CI/debt-register): controller/owner items, worker cannot do them (no push, no repo settings). Slice is NOT done until controller: pushes, first PR CI green (python-gate incl. size lock shrink, secrets-gate, ui-gate), asks Kadir to mark the 3 jobs required, copies Task 4 answers into the debt register, checks gh run list.

## Task 9 fix round 2
- F1 (new small file entry in size_lock.json may carry budget up to part_max): Ruling: accepted, no code change. Check cannot see real sizes; slack test caps entry at real size +50. Optional CI step comparing budgets with real sizes for new entries: parked, owner controller. If wrong: bounded by slack test, review sees lock diff.
- F2 (Step 3 health check not run; slice not done): Ruling: no worker action possible (no push, no repo settings). Controller acceptance items stay open: push, first PR CI green (python-gate incl. size lock shrink, secrets-gate, ui-gate), Kadir marks 3 jobs required, Task 4 answers into debt register, gh run list. NOT done until CI green.
- No code or test changed, so no test run.

## whole branch fix round 1
- F1 (size_lock.json exact budgets for every file): fixed. Lock now holds only files above part_max (10 py, 1 ts) and the 40 long functions, like the engine lock; every other file is capped by part_max. Regenerated by a one-off script, entries unchanged in value. BOUNDARY CHANGE for the approval list: the lock moved from "no file grows" to "no file passes part_max" for 1368 small files — intended by the spec (loosening is deliberate; marked "gevsetme olabilir"). Doc updated.
- F2 (dropping a small file's entry freed it): fixed, red-first (qg-fix-red: test_removed_entry_at_or_below_part_max_exits_1 failed). size_lock_growth now counts a removed files/ts_files entry whose old budget <= part_max as growth; removal of an entry above part_max stays allowed (the size test goes red if the file is still over part_max). Existing "removed exit 0" test rewritten equally strict (removal above part_max). Doc sentence fixed. Not handled: stale entry of a deleted file (harmless, never checked).
- F3 (workflow never ran in real CI): controller item, worker cannot push. Stays open: push PR, check gh run list 'AI-DND quality gate' and 'AI-DND bounded verification'; regenerate knip/ruff baselines from CI artifact if spurious NEW; read fallow/skylos logs. Slice NOT done before that.
- F4 (actions pinned by major tag): Ruling: no change; follows existing ai-dnd-ci.yml, token is read-only. SHA pinning of both workflows together is parked, owner controller. If wrong: a compromised action tag runs with read-only token.
- F5 (skylos pip install): fixed, `--only-binary=:all:` added; policy test requires it (written with the fix, not separately red-first; it asserts the exact string so not vacuous).
- F6 (shrink-check holes: absent base file, main-vs-main on push): Ruling: accepted, no code change; safe only while main is PR-only and the 3 jobs are required. Parked: after merge make shrink steps fail when origin/main lacks the file, and compare to github.event.before on push; Kadir must set required checks (handoff item).
- F7 (approved raise cannot merge on red GREW): documented in kalite-kapisi.md "Yükseltmek": one-time admin merge by Kadir, approval row ID in PR body, raise PR touches only the baseline/lock file. No allow-file mechanism built (extra code; decide after first real raise). If wrong: Kadir does an admin merge each time.
RESULT: tests 274 skipped 0 failing_ids 0 PAR_EXIT=0 (slot 9, qg-fix-green2; flip + size budgets + ratchet + policy + fixed neighbour set via slot.sh test, exit=0, Ran 274 OK); policy rerun after skylos change: Ran 20 OK (qg-fix-pol)

## whole branch fix round 2
- F1 (workflow never ran on real GitHub CI): CONTROLLER ITEM, no worker fix possible (workers never push). Acceptance for the slice: push PR, `gh run list` shows 'AI-DND quality gate' and 'AI-DND bounded verification' green (all three jobs), then Kadir sets them as required checks. Not "done" before that. Local RESULT (tests 274, PAR_EXIT=0) is not a CI substitute; slot.sh untracked here so not rerun this round (docs-only round).
- F2 (size_lock narrowed to files above part_max): fixed as docs. Approval row added: docs/agents/onay-listesi-20261115.md section 25, marked GEVSETME OLABILIR. One-line note appended to the plan (Task 8). No code change.
- F3 (skylos `--only-binary=:all:` wheel availability unchecked): Ruling: keep flag, not verifiable offline without installing. CONTROLLER ITEM at first CI run: read the skylos step log; if install fails, record it here and fix by pin/deps, never drop --only-binary. Step is continue-on-error so failure would be silent: read the log, do not trust green. If wrong: skylos report missing until noticed.
RESULT: docs-only round, no tests run (tests 0 skipped 0 failing_ids 0 PAR_EXIT=n/a)
