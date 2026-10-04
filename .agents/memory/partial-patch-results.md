---
name: Partial patch results
description: A failed multi-file patch may already have applied earlier file changes.
---

Inspect the working tree after a multi-file patch failure before retrying.

**Why:** The patch tool applied earlier files even when a later file failed; repeating the whole patch would reapply already completed changes.

**How to apply:** Retry only the unapplied changes and keep hunks in source order.