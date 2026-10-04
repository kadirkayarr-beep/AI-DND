# Bounded development verification

From the repository root (also runnable from `ai-dnd/` as `python scripts/...`):

```sh
python ai-dnd/scripts/project_health_check.py
python ai-dnd/scripts/final_gate.py
# Inspect only: required execution checks are NOT RUN and Final Gate is NO-GO.
python ai-dnd/scripts/final_gate.py --static-only
# Include committed differences from an explicitly reviewed base in the
# infrastructure-only production-scope check:
python ai-dnd/scripts/final_gate.py --baseline <reviewed-revision>
```

Health Check defaults to **bounded structural inspection**, not an automatic
Python suite or frontend build. It records exact HEAD, branch/detachment,
staged/unstaged/untracked entries, required files, existing verification
commands, and structural authority guard presence. HEALTHY means its required
structural checks passed, **not** that tests ran. Execution rows remain NOT RUN.

Final Gate invokes the existing regression evidence runner using the explicit
bounded selectors in `scripts/development_checks.json`. It reuses the documented
bounded encounter + regression + campaign time + combat lifecycle selection,
adds existing offline model-isolation/ceiling guards and evidence/tooling
contracts, then runs the primary experience frontend's existing library
typecheck, typecheck, test and build commands. It does not run discovery, the
full repository suite or reconstruct the historical 643-test review.

Each command has a 300-second timeout. Vite's required offline build environment
is set to `NODE_ENV=production`, `PORT=5099`, `BASE_PATH=/`; no server is started.
Configuration uses strict JSON, argv arrays and no shell evaluation. Required
failures remain visible and the gate continues collecting other check results.
Commands are trusted developer configuration, not an untrusted command API.

## Status and scope

- **PASS**: the named check actually passed within its stated scope.
- **FAIL**: the named condition/command failed; required failures block the gate.
- **NOT RUN**: not executed, never synonymous with PASS.
- **UNVERIFIED**: insufficient evidence or a started but incomplete command.

GO requires every required check to PASS, including a clean checkout,
stable local verifier fingerprint, all required commands, and complete retained
regression evidence (no failed, skipped, unexecuted or expected-failure tests).
Local detached HEAD blocks the gate. An exact-SHA detached GitHub Actions checkout
is explicitly permitted only when the recorded event SHA equals local HEAD and
a run ID is present; its detachment is still recorded. Any event SHA mismatch fails.
Working changes, including an uploaded untracked instruction file, deliberately
produce nonzero exit status: do not hide them or commit merely to make a gate GO.
Checkout state is observed before creating this command's own record. Previously
generated untracked records still count as Git-dirty; generated files are excluded
from source-content fingerprints, not secretly removed from Git status.
Exit codes: 0 passed required checks; 1 blocked/failed required checks;
2 configuration/tooling failure; 130 interruption.

The infrastructure scope guard detects changed gameplay Python files and either
frontend's player-facing source; it compares working changes to HEAD by default.
`--baseline` adds committed differences from that revision. It is a conservative
**infrastructure-only** review guard, not a general authorization policy for
future gameplay packages. Architecture presence is structural, not proof of
gameplay correctness. No existing gameplay rules, model-call ceiling, persistence,
receipts, RNG or API contracts are changed by this tooling.

Live HTTP, live Qwen, remote server identity and an actual remote Actions run
are not established by local execution. Live checks remain explicitly NOT RUN;
server source identity remains UNVERIFIED. A local GO is not deployment approval,
remote Git identity, historical certification or live narration acceptance.

## Evidence and CI

Records extend the existing [regression provenance conventions](regression-evidence.md):
timestamp/UUID exclusive directories, `run.json`, combined `output.log`, command
argv/cwd, UTC start/end, process exit status, NEW RUN/non-certification markers,
and the **same** `source_snapshot` implementation. Command checks live under
`docs/evidence/development-runs/`; the child regression retains its original
`suite_run` schema in a separate unique directory in that same approved root,
linked from the parent check. No parallel test or hashing implementation exists.

The generated archive root and existing suite archives are excluded by the
existing fingerprint API. Source start/end still identify exact HEAD and working
content; these are **verifier identities only**. Interrupted/crashed runs with
unfinished checks are incomplete, never PASS. Old records and failure records
are not overwritten. An alternate `--archive-root` must be durable; temporary
test fixtures are not release evidence. Archives containing verifier sources or
inside historical suite archives are rejected. Inspect logs before sharing.
The repository's existing `output.log` ignore exception is extended to this
archive folder, retaining logs even on machines with a global `*.log` ignore.
Within the checkout only `docs/evidence/development-runs` (or its descendants)
is permitted, preventing arbitrary archive exclusions from hiding source files.

`.github/workflows/ai-dnd-ci.yml` checks out the exact event SHA (PRs use GitHub's
event merge SHA, not necessarily the contributor branch SHA), installs Python
3.13/Node 24/pnpm 10.26.1/uv 0.9.24 using existing frozen lockfiles, and executes
these same commands. It requires no project secrets, model host, campaign server
or external live acceptance. Checkout credentials are not persisted. Evidence
records include event SHA, workflow, job, run ID and attempt when in Actions.
CI stages new records outside the checkout in `$RUNNER_TEMP/ai-dnd-evidence`
so sequential Health Check/Final Gate records do not dirty the source checkout.
The upload step is their retained CI artifact; child suite links include an
archive-relative path that remains usable after download.
Failure evidence is uploaded with `always()` and retained for **30 days**; this
artifact retention is finite, not a permanent replacement for the project's
durable evidence archives. No workflow has run merely because its YAML validates.