---
name: Git guard errors
description: Distinguish shell-tool protection errors from actual repository corruption.
---

A shell-tool refusal naming the workspace Git index lock may occur during read-only status or diff inspection. Treat it as an execution guard, not evidence that the repository needs repair.

**Why:** Read-only inspections were rejected even with optional Git locks disabled; an explicitly permitted read-only invocation succeeded without repository repair.

**How to apply:** Keep inspection separate from mutations and honor the tool's permission requirements. Do not delete lock files, reset history, or loosen permissions merely to silence this guard.
