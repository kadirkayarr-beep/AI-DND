---
name: Predicate-aware lore retrieval
description: Preserve evidence coverage for narrow lore questions without weakening unknown-claim rejection.
---

For narrow questions that require related canon facts from multiple subjects, derive query intents from the wording and prioritize the exact predicate or relationship facts before applying per-subject and total context bounds. Broad overview wording can appear inside a more specific question; it must not crowd out facts required for that question.

**Why:** A Neverwinter live smoke retrieved the Lords' Alliance purpose fact but omitted the membership relation, so a safe responder could not answer both parts of the question from evidence. Broad retrieval alone did not ensure the required facts were present.

**How to apply:** When deterministic response logic supports a lore predicate or relationship, update retrieval intent coverage and assert that each necessary fact ID is selected for the corresponding query. Keep unsupported entities and claims fail-closed.