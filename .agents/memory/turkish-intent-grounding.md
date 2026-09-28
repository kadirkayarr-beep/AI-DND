---
name: Turkish intent grounding
description: Compatibility and trust boundary for Turkish natural-language intent changes.
---

Normalize Turkish accents, apostrophes, and spacing only for deterministic matching; retain the player's original words for the model and do not use substring-based target matching as authority.

**Why:** A prior typo replacement approach silently rewrote whole input fragments and accepted targets merely because their stem occurred inside another word. A separate regression showed that matching after whitespace normalization must not assume the original leading spaces survive. A live continuity smoke also showed that exact phrase normalization alone can miss inflected Turkish paraphrases after the recent-turn window.

**How to apply:** Match complete entity words with supported suffixes, ground travel in the player's actual text, and keep model responses advisory. For long-term dialogue threads, use bounded token overlap for retrieval and test Turkish paraphrases after the recent window and after API resume; never treat approximate text matching as a canonical action. Test query, travel, and exploration separately while protecting explicit session ownership and persisted state. Do not transfer checkpoint validation totals to the merged engine without rerunning its tests.