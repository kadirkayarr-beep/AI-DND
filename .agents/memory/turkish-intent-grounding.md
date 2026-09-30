---
name: Turkish intent grounding
description: Compatibility and trust boundary for Turkish natural-language intent changes.
---

Normalize Turkish accents, apostrophes, and spacing only for deterministic matching; retain the player's original words for the model and do not use substring-based target matching as authority. Do not put a question-form-only early return ahead of explicit imperative intent patterns such as route-distance requests.

**Why:** A prior typo replacement approach silently rewrote whole input fragments and accepted targets merely because their stem occurred inside another word. A separate regression showed that matching after whitespace normalization must not assume the original leading spaces survive. A live continuity smoke also showed that exact phrase normalization alone can miss inflected Turkish paraphrases after the recent-turn window. A route-distance matcher can be correct yet ineffective if an earlier question-form gate drops imperative Turkish requests before that matcher runs.

**How to apply:** Match complete entity words with supported suffixes, ground travel in the player's actual text, and keep model responses advisory. Test question, imperative, and declarative forms so early intent gates cannot hide a narrower safety matcher. For long-term dialogue threads, use bounded token overlap for retrieval and test Turkish paraphrases after the recent window and after API resume; never treat approximate text matching as a canonical action. Test query, travel, and exploration separately while protecting explicit session ownership and persisted state. Do not transfer checkpoint validation totals to the merged engine without rerunning its tests.