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

## HTTP acceptance is different evidence

`evidence/bounded-encounter-http.json` is the previously retained real-network
acceptance artifact from `scripts/verify_bounded_encounter_http.py`. It is not a
suite execution record, has no deduplicated suite IDs, and does not substantiate
563/563. Preserve it unchanged. If a separately approved HTTP acceptance is
rerun, choose a **new** HTTP output filename and label the report as a new run;
never write it inside a suite archive or use it to backfill historical suite
results. Running the evidence runner does not trigger HTTP acceptance.