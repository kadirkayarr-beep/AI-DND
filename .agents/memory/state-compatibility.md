---
name: State migration compatibility
description: Compatibility constraint for incremental session-state refactoring.
---

Preserve the identity of the shared world dictionary during restoration until callers have been migrated to explicit sessions.

**Why:** Existing consumers retain references to this dictionary; replacing the module variable would silently leave them operating on an abandoned world. The save/load work deliberately keeps this compatibility rather than combining persistence with a broad rewrite.

**How to apply:** Restore contents in place and test reference identity. A future session refactor should migrate callers together rather than assuming module-variable reassignment updates their references.

During incremental migration, retain the default-adventure adapter for callers that execute the engine in a plain dictionary as well as callers that import it.

**Why:** Existing offline consumers assign character scalars directly in an exec namespace; a module-only property adapter cannot intercept those assignments. Independent sessions must not temporarily swap module globals to accommodate them.

**How to apply:** Keep compatibility at default-session boundaries until those consumers are migrated. Prefer explicit session ownership for new callers, and exercise overlapping adventures when changing the adapter.