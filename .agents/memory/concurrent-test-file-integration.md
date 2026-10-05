---
name: Concurrent test-file integration
description: Validation boundary when parallel tasks edit the same Python test suite.
---

Validate the final integrated test sources and their shared fixture dependencies, not only the task's locally edited module.

**Why:** Concurrent merges at the completion boundary can introduce duplicated or orphaned fragments into transitively imported fixtures after a local suite passes, invalidating that earlier evidence.

**How to apply:** When integration changes a test or imported fixture, run source-definition and syntax preflight over the dependency set, then run the affected suites together. Inspect current sources if completion reports collection failures; do not treat a prior local pass as proof of the integrated version or drop intact tests.
