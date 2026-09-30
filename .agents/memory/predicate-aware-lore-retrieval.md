---
name: Lore query evidence and side-effect boundaries
description: Preserve exact structured-lore coverage, fail closed on unsupported claims, and prevent unrelated world-state changes during query handling.
---

For narrow questions that require related canon facts from multiple subjects, derive query intents from the wording and prioritize the exact predicate or relationship facts before applying per-subject and total context bounds. Broad overview wording can appear inside a more specific question; it must not crowd out facts required for that question.

**Why:** A Neverwinter live smoke retrieved the Lords' Alliance purpose fact but omitted the membership relation, so a safe responder could not answer both parts of the question from evidence. Broad retrieval alone did not ensure the required facts were present.

**How to apply:** When deterministic response logic supports a lore predicate or relationship, update retrieval intent coverage and assert that each necessary fact ID is selected for the corresponding query. Keep unsupported entities and claims fail-closed.

World-subject questions must bypass NPC identity and target resolution. If loaded structured evidence cannot support an answer, return an unverified response without changing unrelated scene entities during query handling or serialization. Expire referents on observation or explicit reference, not as a side effect of unrelated reads.

**Why:** A live unsupported route query crossed a scene-referent expiry boundary; serializing the query expired an unrelated visitor and failed the no-side-effects gate.

**How to apply:** Test world-subject questions both with and without an explicit NPC target. Assert an evidence-backed answer or an unverified response with no unrelated state diff, while confirming that observing or addressing a stale referent still expires it as intended.