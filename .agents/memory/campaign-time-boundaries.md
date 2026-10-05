---
name: Campaign Time product boundaries
description: Owner-locked time authority, baseline, and scope for later gameplay consumers.
---

Gameplay decisions drive in-game time; scheduled events never fast-forward the
player, and overlapping windows never retroactively interrupt a long action.
World occurrence is not player knowledge.

**Why:** The owner explicitly made player freedom the product requirement:
the player chooses what to do, and the world changes as a consequence, rather
than the scheduler choosing actions or forcing encounters.

**How to apply:** Preserve Python authority and the existing campaign receipt
transaction. No browser/real clock or model-written duration. New time consumers
must define actual resolved duration, not charge every message.

The owner fixed the fallback campaign baseline at **1 Mirtul 1501 DR, 09:00,
Neverwinter local**, preserving an existing exact canonical date if available.
No legacy migration project is required before real campaigns open.

**Why:** The final implementation instructions superseded the audit's unresolved
date and legacy-migration questions and narrowed those requirements.

**How to apply:** Do not reopen the fallback date choice or broaden the work into
legacy migrations without a new request.

Stable/unconscious recovery is now explicitly approved within the bounded Death
System work. It must consume the existing Campaign Time owner, never a parallel
scheduler. New combat design and broad duration/simulation remain excluded.

**Why:** The owner originally excluded recovery from the Time lock, then explicitly
authorized its bounded Death integration while preserving the Time architecture.

**How to apply:** Allow the authorized Death consumer; require a new explicit
instruction for unrelated additional time consumers.

Pending encounters must survive their window closing, saving, and combat handoff.
Finishing combat does not automatically continue the interrupted action.

PHB2024 minute, hourly and daily pace tables are distinct rounded conventions,
not interchangeable conversion formulas. Preserve the owner's exact values
(400/300/200 ft per minute, 4/3/2 miles per hour, 30/24/18 miles per day).

**Why:** Scaling the hourly values by eight hours would change the explicitly
requested fast and slow daily values; scaling feet/minute also differs.

**How to apply:** Choose the table for the duration unit being resolved, and do
not silently "correct" another table to make the arithmetic agree.

**Why:** The owner's edge-case design lock explicitly makes these separate player
decision points, not scheduler decisions or successful completion by default.

**How to apply:** Preserve actual progress, keep occurrence separate from encounter
and knowledge, and require a new explicit player action after combat. Dependency
cycles must preserve canonical state and report a diagnostic rather than fabricate
a resolution or recurse indefinitely.