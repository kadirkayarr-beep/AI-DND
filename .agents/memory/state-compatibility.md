---
name: State migration compatibility
description: Compatibility constraint for incremental session-state refactoring.
---

Preserve the identity of the shared world dictionary during restoration until callers have been migrated to explicit sessions.

**Why:** Existing consumers retain references to this dictionary; replacing the module variable would silently leave them operating on an abandoned world. The save/load work deliberately keeps this compatibility rather than combining persistence with a broad rewrite.

**How to apply:** Restore contents in place and test reference identity. A future session refactor should migrate callers together rather than assuming module-variable reassignment updates their references.

Keep imported-module character aliases, but do not reintroduce character-state synchronization from plain exec dictionaries.

**Why:** Plain dictionary assignment cannot be intercepted by module properties. Supporting both made test setup a second implicit input into the default adventure; those consumers were migrated to explicit sessions deliberately.

**How to apply:** Use explicit session ownership for test setup and new callers. Preserve terminal default-session behavior and imported-module aliases, and exercise overlapping adventures when changing session dispatch.