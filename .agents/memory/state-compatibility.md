---
name: State migration compatibility
description: Compatibility constraint for incremental session-state refactoring.
---

Preserve the identity of the shared world dictionary during restoration until callers have been migrated to explicit sessions.

**Why:** Existing consumers retain references to this dictionary; replacing the module variable would silently leave them operating on an abandoned world. The save/load work deliberately keeps this compatibility rather than combining persistence with a broad rewrite.

**How to apply:** Restore contents in place and test reference identity. A future session refactor should migrate callers together rather than assuming module-variable reassignment updates their references.