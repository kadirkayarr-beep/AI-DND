---
name: Turkish intent grounding
description: Compatibility and trust boundary for Turkish natural-language intent changes.
---

Normalize Turkish accents, apostrophes, and spacing only for deterministic matching; retain the player's original words for the model and do not use substring-based target matching as authority. Do not put a question-form-only early return ahead of explicit imperative intent patterns such as route-distance requests. Name-disclosure patterns must not accept interrogative fillers such as “ne” or “nedir” as captured names, and self-identity questions must not be routed through NPC-memory disclosure.

**Why:** A prior typo replacement approach silently rewrote whole input fragments and accepted targets merely because their stem occurred inside another word. A separate regression showed that matching after whitespace normalization must not assume the original leading spaces survive. A live continuity smoke also showed that exact phrase normalization alone can miss inflected Turkish paraphrases after the recent-turn window. A route-distance matcher can be correct yet ineffective if an earlier question-form gate drops imperative Turkish requests before that matcher runs. A name-disclosure pattern also captured “ne” from “benim adım ne?” as the player's name, diverting a self-query into NPC disclosure. Live Ollama classification also omitted query_type and selected a location target for “Benim adım ne?” until the prompt added an explicit self-query rule and valid JSON example.

**How to apply:** Match complete entity words with supported suffixes, ground travel in the player's actual text, and keep model responses advisory. Test question, imperative, and declarative forms so early intent gates cannot hide a narrower safety matcher; pair “benim adım ne?” with a real name disclosure such as “Benim adım Arven.” For long-term dialogue threads, use bounded token overlap for retrieval and test Turkish paraphrases after the recent window and after API resume; never treat approximate text matching as a canonical action. Test query, travel, and exploration separately while protecting explicit session ownership and persisted state. Do not transfer checkpoint validation totals to the merged engine without rerunning its tests.

For explicitly routed interaction inputs, require the structured envelope and original-input quote in the response schema. Preserve the Python-selected coarse intent category while leaving argument interpretation to the model.

**Why:** Real Qwen ignored an optional interaction property despite prompt instructions; even after requiring it, it reclassified a stated personal goal as information and a promise as side switching. Mocks returned compliant packets and did not expose this failure.

**How to apply:** Use schema constraints, not retries or silent acceptance of another operation. Keep generic free-form interpretation for inputs without an explicit coarse hint, and verify both paths with the real model separately from fixture tests.

Canonical character-sheet questions must not depend on resolving an NPC, including when conversation selection is absent or expired.

**Why:** Scene planning can emit an NPC clarification before the later canonical-query handler runs. Fixing only the later handler leaves that earlier diversion intact.

**How to apply:** Preserve query priority across both planning and execution, while keeping death, combat, explicit-target validation and genuine NPC-memory questions on their existing owner paths.