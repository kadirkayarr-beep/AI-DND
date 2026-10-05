---
name: Concurrent test-file integration
description: Validation boundary when parallel tasks edit the same Python test suite.
---

When multiple tasks edit the same test module, validate the integrated file after their commits are combined, not only the local pre-integration version. An integrated version can contain duplicated fixture fragments or appended test bodies even if each task's local suite passed.

**Why:** Parallel changes to overlapping sections produced a syntactically invalid integrated test module despite earlier successful local execution.

**How to apply:** Before completion, check the current repository state and rerun the relevant test module after integration, especially when another task changes the same test file.
