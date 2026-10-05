---
name: Concurrent test-file integration
description: Validation boundary when parallel tasks edit the same Python test suite.
---

When multiple tasks edit the same test module, validate the integrated file after their commits are combined, not only the local pre-integration version. An integrated version can contain duplicated fixture fragments or appended test bodies even if each task's local suite passed.

**Why:** Parallel changes to overlapping sections produced a syntactically invalid integrated test module despite earlier successful local execution.

**How to apply:** Before completion, check the current repository state and rerun the relevant test module after integration, especially when another task changes the same test file. Include transitively imported fixture modules in source-definition preflight: a focused suite can depend on campaign API tests through shared spell fixtures even when its own files remain valid. Completion may include newly integrated changes outside the task's diff.

Treat shared fixture modules as part of this validation boundary, even when the
assigned regression lives in a different file. A successful local run can be
invalidated by another task's later merge into an imported fixture module.

**Why:** Completion failed after a previously passing regression because an
integrated fixture dependency contained an orphaned duplicate test fragment.

**How to apply:** When collection fails after integration, inspect the reported
fixture dependency and preserve the original test before removing duplicate
fragments. Rerun the affected regression and the dependency's suite together.

Completion can combine concurrent changes after a successful local test run. If
its checks report new syntax errors or shadowed fixtures, inspect the current
integrated file rather than relying on the earlier passing run.

**Why:** Integration at the completion boundary can invalidate local evidence
without any new edits by the task's agent.

**How to apply:** Repair duplicated fragments without dropping intact tests,
then run source-definition preflight and the affected suites on that version.
