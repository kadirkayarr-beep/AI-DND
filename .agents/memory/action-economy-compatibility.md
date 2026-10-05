---
name: Action Economy compatibility
description: Why legacy plain attacks and explicit multi-step turns intentionally differ.
---

Preserve legacy single free-text attack automatic turn completion while allowing structured and compound commands to keep the turn open for movement, Bonus Actions and explicit completion.

**Why:** The Action Economy work deliberately preserved the existing combat-lifecycle contract instead of changing the default input workflow while later combat phases remain locked.

**How to apply:** Do not casually make all attacks hold the turn, or make all attacks end it. Changing this compatibility decision needs an explicit product decision, not an incidental resource-ledger refactor.

Keep unsupported Action-specific mechanics unavailable rather than inventing successful outcomes.

**Why:** The owner explicitly separated resource accounting from later weapon, monster, spell, persistence and final UI work.

**How to apply:** A future feature may connect a real mechanic to the existing ledger; the presence of an Action-family name or grant is not evidence that its effect has been implemented.

Treat explicit actor-ID spending in legacy-shaped combat as an additive
compatibility contract, not evidence that historical V1/V2 writers emitted it.
Preserve valid markers or reject invalid ones; do not require modern resource
ledgers or infer spending from the saved cursor.

**Why:** The historical writers omitted action-use data, but discarding explicit
spending when importing an extended legacy shape would silently grant another
action. Compatibility fixtures must not be presented as historical evidence.

**How to apply:** Audit the actual historical writer when extending migration.
Keep native-format validation strict and separate from legacy normalization.