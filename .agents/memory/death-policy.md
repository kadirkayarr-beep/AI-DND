---
name: Death and save policy
description: Owner-selected NPC mortality, historical canon, and save deletion boundaries.
---

Ordinary resolved lethal damage reducing an NPC/monster to zero HP means dead.
Player-style death saves and generic Stable recovery do not apply to monsters.
Only actually supported, verified survival mechanics may override this; narrative
importance cannot. Explicit knockout is separate, not zero-HP lethal unconsciousness.

**Why:** The user explicitly selected 2024 default monster death (Policy A).

**How to apply:** Consume existing damage-owner results through one Death handoff.
Never infer missing Monster Manual abilities or let Qwen/frontend choose survival.

Historical saved zero-HP unconscious NPCs must not be silently rewritten as dead
or assigned a fabricated death event. Loading them must not consume gameplay RNG.

**Why:** The user required preserving historical campaign canon despite the new policy.

**How to apply:** Preserve saved status; deterministic incapacity/cursor handling is
allowed, but actual new damage follows Policy A.

Character death never automatically deletes the player's campaign in any mode.
Save deletion is a separate, explicit selected-campaign operation requiring
destructive confirmation; successful deletion revokes its active session.

**Why:** The user explicitly separated mortality from Save Management and prohibited
automatic deletion in Normal, Permadeath and Ironman.

**How to apply:** Keep mode outcomes and persistence deletion independent, and preserve
unrelated campaigns/sessions.

For bounded Death completion, stabilization must use an already legitimate
production actor/action path and existing receipts. Do not add autonomous NPC
behavior or a new self-healing capability merely to expose it. If no such path is
available, stop and report an architectural conflict rather than inventing one.

**Why:** The user explicitly imposed this gate in the bounded completion follow-up.

**How to apply:** Check production reachability before connecting the helper; a
direct engine helper or test-only actor is not sufficient.