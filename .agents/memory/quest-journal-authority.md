---
name: Quest ledger authority
description: Python owns quest lifecycle; production definitions stay empty until owner-approved content exists.
---

Python owns quest state and transitions. Only explicit server-validated commands accept, reject, or cancel quests; canonical location, defeat, and supported-item evidence advances objectives. Narration and browser text never create or change quest state. Keep the production quest catalog empty until owner-approved definitions are supplied.

**Why:** Narration can be descriptive or contradictory, so it cannot establish game outcomes. Quest mechanics now have structured engine authority, but no production definitions have been owner-approved; an empty catalog prevents unapproved content from appearing while preserving test-only server-owned fixtures.

**How to apply:** Keep the browser limited to rendering returned quest state and sending quest IDs for explicit commands. Validate and persist engine transitions through the API; add production quest definitions only after owner approval.