---
name: Concurrent test-file integration
description: Validation boundary when parallel tasks edit the same Python test suite.
---

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

Restore unterminated multiline fixture delimiters before deciding which
surrounding test definitions are duplicates.

**Why:** A broken string can hide intact methods from Python's parser, while
duplicated tails can look like a valid continuation of another test.

**How to apply:** Compare complete test bodies in the source before removing
fragments, then check syntax and definition uniqueness together.
