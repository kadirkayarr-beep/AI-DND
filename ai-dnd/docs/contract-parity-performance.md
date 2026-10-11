# Contract parity performance

## Measurements

Measured in the Replit workspace with Python 3.13 and PyYAML 6.0.3,
with LibYAML available. Times are wall-clock seconds, excluding module imports.
Timing instrumentation accumulated `perf_counter()` around each dump and load,
not a heavyweight profiler.

| Check | Before: Python safe YAML | After: accelerated safe YAML |
| --- | ---: | ---: |
| Complete parity and reader suite | 455.28 (95 tests) | 102.57 (97 tests, all passing) |
| Time inside YAML dumping | 145.29 (1,838 calls) | 36.58 (1,844 calls) |
| Time inside contract loading | 286.42 (1,850 calls) | 43.23 (1,874 calls) |
| Isolated quest-parent mutation test | 54.39 (passing) | 10.26 (passing) |

The full suite finished about **4.4 times faster**, reducing elapsed time by
**77.5%** and bringing it below the five-minute foreground limit. YAML work
accounted for about 95% of the baseline runtime. The two additional tests exercise
backend safety, scalar typing, complete-contract round trips, and independent data.

After merging concurrent parity coverage and fixing the loader-helper definition
order, the integrated suite contained **107 tests** and passed in **117.06 seconds**
with the accelerated backend. The complete 107-test suite also passed with
`CSafeLoader` and `CSafeDumper` unavailable, confirming the pure-Python fallback;
that run's wall time was not captured.

These are observed timings, not hard performance thresholds: the full runs
overlapped on a shared runner, and the isolated measurements also ran while the
baseline was active. Different test inventories or runner load affect comparisons.

### Baseline diagnostic caveat

The before-change process imported the original test module before editing began.
It completed all 95 tests but reported eight subtest failures in the
unexpected-campaign-start-property reader test. The assertions examine traceback
source text, and Python read the edited source at the original line numbers.
This was a source/traceback mismatch, not changed contract acceptance or parsing.

Both the missing-property and unexpected-property tests passed when rerun from
an immutable snapshot of the original source (2 tests, 8.05 seconds). All 97 tests
passed against the final source. Future baselines should finish before editing or
use an immutable source snapshot with matching traceback source lines.

## Coverage and implementation

- Prefer `CSafeLoader` and `CSafeDumper` when PyYAML provides them; otherwise use
  `SafeLoader` and `SafeDumper`. No package or runtime dependency was added.
- Retain duplicate-key detection on both loader implementations. Neither parser
  accepts Python-object tags, and neither dumper serializes arbitrary objects.
- Every existing mutation still starts from its own deep copy and serializes and
  reloads the full contract in both block and compact YAML. No fixture cache,
  shared mutated documents, skipped mutations, or reduced format coverage.
- An AST comparison confirmed all 95 original test bodies are unchanged except
  for replacing `yaml.safe_dump` with the safe accelerated dump helper.
- Existing drift diagnostics, restoration assertions, unchanged-contract
  acceptance, and full parity checks remain intact.
- With the C backend attributes deliberately absent, fallback selection, both
  safety tests, and complete-contract acceptance in both formats passed
  (3 tests, 1.44 seconds).
- The complete 107-test integrated suite also passed when both C backend
  attributes were removed to exercise the pure-Python fallback.
- `api/schemas.py` and `lib/api-spec/openapi.yaml` were not modified.

## Reproduce the functional check

From the workspace root:

```sh
cd ai-dnd
python -m unittest api.tests.test_contract_parity
```

For isolated before/after measurements on the same test source, run the
quest-parent reader test once with the default backend and once while patching
`_SAFE_DUMPER` to `yaml.SafeDumper` and `_ContractLoader` to a class inheriting
`_DuplicateKeyLoaderMixin` and `yaml.SafeLoader`. Time the runner with
`time.perf_counter()`. Do not edit the source while either measurement runs.
