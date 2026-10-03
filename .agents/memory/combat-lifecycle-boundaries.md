---
name: Combat lifecycle boundaries
description: Owner-locked lifecycle scope, replay semantics and narration commit boundary.
---

Combat lifecycle hardening must not redesign action economy, initiative, weapons,
monster behavior, death, spells, persistence or UI architecture.

**Why:** The owner explicitly separated these locks and required preserving the
working resolution interfaces rather than rewriting combat.

**How to apply:** Validate identity, current actor, participants and transitions
around existing mechanics. Keep unconscious initiative boundaries and event-to-combat
decisions; combat exit never blindly resumes interrupted gameplay.

Successful receipt replay precedes stale combat-context validation.

**Why:** The owner's retry requirement includes lost responses, save/resume and
closed encounters; a valid retry carries the original, now-stale context.

**How to apply:** Replay the original request/response before checking the current
encounter. Treat client combat context as a precondition, not authority. Preserve
the original context in pending browser requests.

Do not send an uncommitted combat outcome to Qwen as if it happened.

**Why:** The owner explicitly prohibited false success when persistence fails.
Combat uses the existing deterministic mechanical narration before the atomic save,
so the intent model does not receive an outcome that might subsequently roll back.

**How to apply:** Keep combat narration on the established Python result renderer
unless a future request explicitly introduces a safely committed narration phase.