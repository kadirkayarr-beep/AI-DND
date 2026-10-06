---
name: Concurrent test-file integration
description: Validation boundary when parallel tasks edit the same Python test suite.
---

Treat pre-existing working-tree edits as a separate change set before completing
a narrowly scoped task.

**Why:** Completion can commit all outstanding edits, including unrelated changes
that were present before the task began, and review the combined diff. Review
can also include changes committed by concurrent tasks, even when the initial
working tree was clean.

**How to apply:** Record the initial dirty paths. If unrelated edits are captured,
preserve them separately and obtain permission before moving them out of the
active task branch; never discard them or silently fix unrelated gameplay.
Compare commit ownership when a review reports changes absent from the scoped
task diff rather than assuming all reviewed changes belong to the current task.

The merge continuation check can mistake decorative runs of equals signs in
comments or printed separators for unresolved conflict markers.

**Why:** A fully parsed conflict-free file was rejected solely for decorative
separators containing seven or more equals signs.

**How to apply:** If continuation still reports markers after structural
resolution, search for all marker substrings, not only line-start markers.
Use hyphens for decorative separators without changing gameplay logic.

Validate the final integrated test sources and their shared fixture dependencies, not only the task's locally edited module.

**Why:** Concurrent merges at the completion boundary can introduce duplicated or orphaned fragments into transitively imported fixtures after a local suite passes, invalidating that earlier evidence.

**How to apply:** When integration changes a test or imported fixture, run source-definition and syntax preflight over the dependency set, then run the affected suites together. Check for duplicate class methods as well: valid Python can silently shadow an earlier fixture or test definition. Inspect current sources if completion reports collection failures; do not treat a prior local pass as proof of the integrated version or drop intact tests.

Before removing an orphaned fragment, verify its assertions already exist in a complete independent test. A syntax-only fix can leave the fragment executing under another test's setup.

**Why:** A duplicated test tail can be appended inside an unrelated method; removing only the unmatched delimiter leaves undefined variables and misleading coverage.

**How to apply:** Preserve the complete test and remove only the proven duplicate tail, then check parsing and run the integrated suite.
Check duplicate fixture and helper definitions, including setup/teardown,
as well as syntax: Python silently replaces earlier methods with later definitions.

**Why:** Integration can duplicate setup and helper methods while appending an orphaned test fragment elsewhere. A syntax repair alone leaves shadowed definitions that Python accepts silently.

**How to apply:** Remove only proven duplicate fragments, preserve the fully initialized tests, and check class-level definition uniqueness before rerunning the integrated suite.

An isolated run loading intact shared fixture definitions can verify scoped
regressions while an unrelated fixture body is broken, but it is not proof that
ordinary module collection or the configured release suite passes.

**Why:** A syntax error anywhere in an imported fixture prevents all dependent
tests from collecting, even when the setup helpers themselves remain valid.

**How to apply:** Report isolated results and the normal collection blocker
separately. Keep the broken integrated source visible; do not quietly substitute
an isolated loader into the project's normal test command.

Check embedded multiline fixtures as well as Python syntax after integration.

**Why:** Combining concurrent edits can move test definitions into a fixture
string or remove fixture contents; syntax and method uniqueness alone cannot
prove all intended tests remain discoverable.

**How to apply:** Run ordinary module collection and fixture-equivalence checks,
and confirm independently added test methods are still discovered.

When repairing a structurally corrupted integration, compare against the last
parseable integrated parent and preserve its full test-method inventory.

**Why:** A merge can lose entire parity methods while duplicating mutation
tails; fixing only the first syntax error does not restore coverage.

**How to apply:** Retain independent merged checks, reapply only intact scoped
additions, and verify method preservation and uniqueness before running the suite.

Successful working-tree cleanup does not guarantee the completion merge retains
those deletions. If review reports duplicates that local checks did not see,
inspect the integrated committed tree before retrying completion.

**Why:** Concurrent integration has reintroduced already removed duplicate
fixture definitions and orphaned test tails after a clean local suite run.

**How to apply:** Apply cleanup against the integrated version, preserve all
distinct complete tests, and check the committed source as well as the working
tree before resubmitting.

Restore unterminated multiline fixture delimiters before deciding which
surrounding test definitions are duplicates.

**Why:** A broken string can hide intact methods from Python's parser, while
duplicated tails can look like a valid continuation of another test.

**How to apply:** Compare complete test bodies in the source before removing
fragments, then check syntax and definition uniqueness together. An AST comparison
against the last parseable integrated version can confirm every pre-existing
method body is preserved while identifying only the intended new methods.

Locate orphaned duplicate tails by their surrounding method before removing
them; matching text alone can identify the intact original first.

**Why:** An integration tail can be byte-identical to part of a complete earlier
test. First-occurrence replacement would damage the valid test instead of
removing the orphan.

**How to apply:** Confirm the original body remains intact, remove the fragment
with unique surrounding context, and compare method inventories and fixture
contents against a parseable version before running the combined suites.

Reference-mutation tests that require exactly one failure should run their
owning parity check directly rather than assume the whole suite has only one
check capable of detecting the drift.

**Why:** Adding independent collection-reference coverage can legitimately
produce a second failure for an existing mutation without weakening either
check.

**How to apply:** Keep the full suite as the baseline acceptance check, but
isolate the target parity method when asserting an exact mutation failure count.

Freeze the source used by performance baselines when tests assert traceback
source text; do not edit that source while its baseline is running.

**Why:** Python can execute an already imported test body while traceback
formatting reads newer lines from disk. This creates diagnostic-assertion
failures unrelated to the mutation or parser being measured.

**How to apply:** Finish a baseline before editing, or compile an immutable
source snapshot with matching traceback source lines. Keep source-sensitive
assertions intact rather than loosening them to accommodate benchmark races.
