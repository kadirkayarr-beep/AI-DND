---
name: Live Vite gate verification
description: Verify temporary development-only UI gates in the running Vite output, not only in loaded config.
---

For isolated Vite-only features, a passing config-loader test is not proof that the running server applied the gate. Verify the live HTML marker and transformed module, then verify the feature is absent from a production build.

**Why:** In the F03-P03 ownership panel work, config tests passed while the live transformed app still contained an unresolved global flag, leaving the panel hidden.

**How to apply:** When adding or changing a Vite command/port/environment gate, test each config combination and query the exact running dev server's HTML/module output before calling the feature ready.
