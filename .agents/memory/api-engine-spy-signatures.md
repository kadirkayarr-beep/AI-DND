---
name: API engine spy signatures
description: Avoid changing signature-driven API dispatch when capturing real engine results in offline tests.
---

Preserve the original callable signature when spying on a real engine turn. A generic variadic mock is not a transparent observer of this API boundary.

**Why:** API dispatch inspects accepted parameters to forward precomputed scene plans and request identity. Replacing the bound turn with a generic mock can omit those inputs and cause lore-evidence rejection even though the underlying real turn executes.

**How to apply:** Use a signature-preserving wrapper around the real bound callable when recording engine results. Leave gameplay and evidence validation intact; do not bypass them to make an observer work.
