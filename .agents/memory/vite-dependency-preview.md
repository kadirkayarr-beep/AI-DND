---
name: Vite dependency preview
description: A compiled build can pass while missing optimized dev dependencies leave the preview blank.
---

Distinguish a Vite optimized-dependency availability failure from application,
API or port failures. Healthy source routes and a successful production build
do not prove that the browser's optimized dependency URLs are usable.

**Why:** The development preview was blank with dependency requests returning
504, while its source files and Python API returned 200. The optimized dependency
directory was incomplete. The same application rendered after its managed
frontend restarted; no routing or application source change was needed.
The precise cause of that incomplete cache was not established.

**How to apply:** For this failure shape, compare actual dependency URLs with
source/API responses before proposing code or routing changes. Keep the known
root Replit dev-banner request failure separate from application readiness.
