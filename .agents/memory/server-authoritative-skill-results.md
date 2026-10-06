---
name: Server-authoritative skill results
description: Why skill-check cards must be projected by the API rather than reconstructed or restored from client storage.
---

The browser must render only validated skill-check results supplied by Python through the API. Never create an optimistic client-side roll or restore a result card from browser transcript storage. Narration history alone is not proof of a canonical mechanics outcome.

**Why:** A locally generated or restored result could misrepresent the engine's dice, modifiers, difficulty, or outcome.

**How to apply:** Keep result projection and validation on the server. Treat browser transcript entries as presentation-only, and add structured persistence only when the engine exposes an authoritative lifecycle record.

Extended-travel acceptance must also show the Python-owned CON saves, not only walking counters and changed Exhaustion.

**Why:** Browser verification found the saves persisted internally while the public response/UI showed only their side effects; mechanic tests alone had not caught the missing result path.

**How to apply:** Verify the saved native DC, rolls, modifiers and outcome through the public state and after browser resume. Do not recompute the result from counters or narration.