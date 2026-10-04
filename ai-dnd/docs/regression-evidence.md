# Durable regression evidence

The historical **563/563** statement in `bounded-monster-integration.md` is
unverified: the approved artifacts do not retain that suite's selected IDs,
execution outcomes or source fingerprint. No new run can certify that missing
historical run. Commit provenance remains unresolved; this runner does not
authorize or perform commits, pushes, publication or provenance changes.

## Run a NEW suite

From the repository root:

```sh
# Bounded encounter unittest cases plus the plain functions in test_regression.py
python ai-dnd/scripts/run_regression_evidence.py

# Explicit modules, classes, methods or plain functions; repeated IDs run once
python ai-dnd/scripts/run_regression_evidence.py \
  api.tests.test_bounded_encounter test_regression

# Explicit discovery; review the pattern before selecting live/model suites
python ai-dnd/scripts/run_regression_evidence.py \
  --discover ai-dnd/api/tests --pattern 'test_bounded*.py'
```

This is an opt-in evidence runner, not a change to the existing gate selection
in `run_tests.py`. It supports unittest cases and module-owned `test_*` plain
functions (including `test_regression.py`). It does not invent individual test
results for arbitrary script-style gates. Default selection is bounded encounter
plus regression, **not** a reconstruction of the historical 563-test selection.

Legacy script entry points can be selected explicitly as functions, for example
`test_door_enter.run_tests`. Selecting a script module with only `run_tests`
does not select that entry point automatically. Imports no longer execute the
door checks or install a model mock. Each of the eight legacy scripts owns a
fresh model mock only for its `run_tests` invocation, restoring both the engine
and module bindings on success, failure or interruption.

`api.tests.test_legacy_script_isolation` checks cold imports in both orders,
all eight `__main__` entry points in fresh processes, mixed forward/reverse
entry points under an active API adapter, injected failures in each script,
fresh mocks on repeated calls, and nested interruption with an absent module
binding. Real model callbacks are forbidden in the cold-import/direct-entry
checks. These are **offline isolation contracts**, not live HTTP acceptance.

At the time of the earlier legacy-isolation runs below, the old
`test_combat.run_tests` fixture lacked authoritative distance and raised
`CombatRequestError` with `distance_unknown` at its first attack, including in
the unchanged pre-isolation script. Those isolation checks explicitly expected
that refusal; they did **not** prove a passing combat gameplay entry point.

The repaired offline combat fixture now supplies explicit five-foot geometry,
owned/held longsword equipment and deterministic character proficiency, and
starts combat through the real scheduler with player-first initiative. Every
case resets session-owned state and RNG without replacing caller-held world
references. Only dice and the offline model are controlled; attack preparation,
participation validation, resolution, damage and HP transitions run normally.
Assertions use the current server-owned attack bonus, critical dice and
nonlocal-target request refusal. Missing geometry and nonparticipant targets
still fail without state/RNG mutation. Production validation is unchanged.

The isolation suite now requires genuine success from the combat `run_tests`
and direct `__main__` entry points, while retaining injected-failure cleanup,
fresh-mock checks and active-adapter restoration in both orders. These new
results do not alter or recertify the older failed or cleanup-only records.

### Retained legacy-isolation runs

All paths below are new offline records, each with `run.json` and `output.log`.
Earlier evidence is unchanged.

| Selection | Result | Archive |
| --- | --- | --- |
| Initial isolation contracts, before accounting for the pre-existing combat fixture refusal | Failed: 5 parent tests, 1 failure and 2 subtest errors | [Initial attempt](evidence/suite-runs/20261004T100001Z-38309e2b7df64d8bbabcb11579c85ed6/run.json) |
| Seven supported legacy entry points, legacy isolation, model isolation, bounded encounter, regression, campaign time, combat lifecycle | **103/103 passed** | [Legacy-first](evidence/suite-runs/20261004T100118Z-c367985b09aa40aa841cdf9cb3209c14/run.json) |
| The same selectors in reverse order | **103/103 passed** | [API-first](evidence/suite-runs/20261004T100138Z-fd91cc67de2343a7bf0aac26d5c7204c/run.json) |

Both passing runs selected and executed 103 unique IDs with no skips or
unexecuted IDs and no source change during execution. Their five isolation
parent tests include all eight scripts; combat contributes explicit
failure-cleanup evidence, not a passing combat gameplay result.
Exact invocations and source fingerprints are in the linked records.

### Retained repaired-combat runs

These **NEW RUN** records add `test_combat.run_tests` to all selectors from
the earlier mixed legacy/API selections:

| Selection | Result | Archive |
| --- | --- | --- |
| All eight legacy entry points, legacy isolation, model isolation, bounded encounter, regression, campaign time, combat lifecycle | **104/104 passed** | [Repaired combat, legacy-first](evidence/suite-runs/20261004T100739Z-cd3df944e6804b6d8708e2f0f111f67e/run.json) |
| The same selectors in reverse order | **104/104 passed** | [Repaired combat, API-first](evidence/suite-runs/20261004T100814Z-1ee0789a67a44ab09b06c10f44228dc0/run.json) |

Both selected and executed 104 unique IDs, with zero failures, errors, skips or
unexecuted IDs, and no source changes during execution. Each archive retains
its combined `output.log` alongside `run.json`. The direct combat `__main__`
success is checked in fresh processes with live model calls forbidden; its
explicit selector also passes in both mixed orders. These are offline
regression results, not live HTTP acceptance or certification of prior runs.

Every invocation creates a unique, durable directory under
`ai-dnd/docs/evidence/suite-runs/`, with `run.json` and `output.log`. Use
`--archive-root` only for another durable location, not `/tmp`. Keep both files
together. Report the exact archive path with any result; do not replace it with
only a count or a temporary console log. New archives never overwrite old ones.
Evidence can contain test output and exception messages: inspect it before
sharing, and do not run secret-printing tests with a shareable archive.

`run.json` contains:

- `NEW RUN`, `suite_run`, and an explicit false historical-certification flag.
- Exact command argv and shell rendering, working directory, Python version,
  UTC start/end timestamps, process exit status and runner completion status.
- HEAD revision at start/end, dirty-tree status, hashes of git status and staged
  binary diff, and a working-tree SHA-256 over file paths, modes and content
  hashes. Tracked files (including missing/deleted files) and nonignored untracked
  files are included. Ignored files, environment values and generated suite
  archive directories are excluded. This fingerprint identifies source content;
  it is not a source backup or proof of commit authorship.
- Fully qualified unique selected and actually started test IDs, unexecuted IDs,
  occurrence counts, duplicate IDs with counts, and duplicates removed.
- Per-test timestamps/outcomes and detailed failure/error/skip events; suite
  setup/teardown events are separate and never pretend a method ran.
- Aggregate unittest failures/errors/skips, expected failures, unexpected
  successes and per-test outcome counts. Multiple failing subtests can count as
  multiple failures within one executed parent test.
- Hash of the retained combined stdout/stderr log and source-change detection.

Exit codes: `0` successful suite, `1` suite failure, `2` runner/selection/evidence
error, `130` keyboard interruption. JSON is written before selection, after each
test event, and on finalization. A forcibly killed process can leave `running`
status with no end time/exit status; treat that as incomplete, never PASS.
A source-change flag also means the run cannot certify one stable source tree.

## Travel and invalid-target regression contracts

The original failed run at
`evidence/suite-runs/20261004T091911Z-7fd21e30fb6140f4a5e448cf3f367cac/run.json`
is retained unchanged. Its two regression failures exposed old test assumptions,
not permission to relax gameplay validation:

- `test_regression.test_named_location_return`: `game.execute_intent` delegates
  registered-origin travel to `timed_gameplay.start_travel`. Registered names
  without a verified duration produce `unverified`, not a location change.
  The updated check first asserts this refusal and unchanged time, then supplies
  an explicit server-owned 300-second forest-to-tavern route and checks arrival,
  journey completion and elapsed time. Only encounter dice are controlled;
  intent grounding and the travel engine execute normally.
- `test_regression.test_unsupported_attack`: the legacy test ID is retained for
  comparison, but attacks are no longer universally unsupported.
  `combat_lifecycle.validate_request` rejects nonexistent or nonlocal targets
  with `CombatRequestError`, code `invalid_combat_target`, HTTP status `400`,
  before intent parsing. Both cases must leave the full world, character,
  RNG and recent narration unchanged and must not call the model.

Regression functions now reset to fresh seeded sessions so routes, clock,
journey, combat and character state cannot leak between checks. Gameplay code
and invalid-target validation are unchanged. To archive these checks together
with the adjacent authoritative contracts:

```sh
python ai-dnd/scripts/run_regression_evidence.py \
  api.tests.test_bounded_encounter test_regression \
  api.tests.test_campaign_time api.tests.test_combat_lifecycle
```

## HTTP acceptance is different evidence

`evidence/bounded-encounter-http.json` is the previously retained real-network
acceptance artifact from `scripts/verify_bounded_encounter_http.py`. It is not a
suite execution record, has no deduplicated suite IDs, and does not substantiate
563/563. Preserve it unchanged. Running the evidence runner does not trigger
HTTP acceptance. Neither these instructions nor the verifier changes authorize
a live rerun, push, publication or commit-provenance change.

Only after separate approval, a future **NEW RUN** uses:

```sh
python ai-dnd/scripts/verify_bounded_encounter_http.py \
  --base '<approved-running-server>' \
  --resume-base '<approved-second-running-server>'
```

Every attempt creates an exclusive timestamp/UUID directory under
`evidence/http-runs/`, separate from `evidence/suite-runs/`. `run.json` is written
**before any HTTP request**, checkpointed as requests/turns complete, and finalized
on success, exceptions, Ctrl-C or SIGTERM. It includes `NEW RUN`,
`http_acceptance`, a false historical-certification flag, exact interpreter argv
and shell rendering, working directory, UTC start/end timestamps, exit status,
server addresses, request progress, partial turns, campaign/session identifiers
when available, and failure details. Completed acceptance keeps the existing
scenario/movement/attack/save/resume/replay fields. Report the exact archive path;
never use HTTP records to backfill historical suite results.

`--archive-root` selects another durable HTTP location. The suite archive
directory (including symlink aliases) and historical HTTP filename are forbidden.
The optional legacy `--output <new-filename>` creates an exclusive export:
existing files are refused before HTTP begins, and that refusal itself leaves a
failed record in the unique archive. A new export is reserved before requests
and finalized from the same record; the archive remains authoritative. Nothing
silently replaces earlier evidence. Keep failed and interrupted archives too.

Exit statuses are `0` PASS, `1` acceptance assertion failure, `2` HTTP/setup/error,
`130` Ctrl-C and `143` SIGTERM. SIGKILL or a process/machine crash cannot be
finalized by Python: the last checkpoint remains `RUNNING`, with null end time
and exit status. That is an identifiable **incomplete attempt**, never PASS;
do not invent an observed end time or exit status. Errors preventing archive
creation/writing fail explicitly; no runner can promise retention on an
unwritable or unavailable filesystem. Records can contain raw game responses,
server addresses and exception details; inspect them before sharing.

Offline archive-contract checks (no live acceptance, game server or model):

```sh
cd ai-dnd
python -m unittest api.tests.test_http_acceptance_evidence
```