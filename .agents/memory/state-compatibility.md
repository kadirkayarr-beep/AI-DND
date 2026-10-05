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

Do not treat character reinitialization as a fresh campaign fixture.

**Why:** Runtime fixture audits found that shared-session character resets retained
earlier journeys, scenes and campaign time, making otherwise isolated narration
assertions depend on test order.

**How to apply:** Prefer a fresh explicit session for each regression case. Test
shared-session restoration deliberately when that is the contract, rather than
relying on it for unrelated scenario setup.

For persistence round-trip regressions, compare complete canonical serialized
state across reopening, not raw checkpoint dictionaries against loaded objects.
Check checkpoint restoration using the fields originally captured.

**Why:** Loading can legitimately supply compatibility defaults missing from a
raw combat checkpoint. Exact raw-object equality can fail despite an unchanged
canonical save and correctly restored gameplay.

**How to apply:** Keep full serialized-state and RNG equality assertions before
and after replay; use captured-field comparisons only for raw checkpoint data.