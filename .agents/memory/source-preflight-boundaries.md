---
name: Source preflight boundaries
description: Keep accidental definition-loss checks separate from intentional runtime patch fixtures.
---

Keep regression definition protection source-only and narrowly resolvable; do
not treat every runtime change to a callable as accidental test loss.

**Why:** Regression fixtures intentionally patch callables. The owner requested
protection against explicit post-class replacement without rejecting those
fixtures or weakening existing lexical checks.

**How to apply:** Any future extension to aliases, dynamic attribute operations,
or inheritance needs its own resolution policy and offline acceptance fixtures
for intentional patches and unrelated objects. Preserve the distinction between
source inspection and execution evidence.
