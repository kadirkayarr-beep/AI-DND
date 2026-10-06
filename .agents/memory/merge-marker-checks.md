---
name: Merge marker checks
description: Merge completion can flag decorative equals separators as conflict markers.
---

The merge-completion marker check can reject literal runs of seven or more
equals signs even in ordinary Python comments or printed separators.

**Why:** A correctly resolved Python file was rejected solely for pre-existing
decorative separators, with no actual conflict markers remaining.

**How to apply:** If completion reports markers after conflict resolution,
inspect all literal marker substrings, not only line-start conflict syntax.
Use hyphens for decorative comments and expressions such as `"=" * 35` to
preserve printed output. Confirm semantic equivalence before continuing.
