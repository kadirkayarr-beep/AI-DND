---
name: Narration world authority
description: Preserve narrative safety while preventing model proposals from becoming campaign canon.
---

Qwen may interpret intent and narrate verified outcomes; its proposed NPCs, locations, shops, features and events do not establish canonical state. Positive mutation fixtures must supply Python-owned definitions or existing canonical entities.

**Why:** The owner explicitly required this boundary. Historical tests expected narrator-authored locations and NPCs, so retaining those expectations would restore the prohibited authority.

Do not replace all general narration with exact mechanical-prefix templates. Keep existing lore, named-entity, smalltalk and fallback validation; enforce the no-model-canon rule at the mutation boundary. Exact-prefix narration remains appropriate for the bounded exploration adapter.

**Why:** Applying exploration's narrow template to every general action broke established smalltalk fallbacks and specific lore-safety diagnostics without improving the canonical mutation boundary.

**How to apply:** Preserve existing general narration safety and deterministic resolved fallbacks. Test matching as well as unrelated model proposals, with no state/time/RNG changes. Retain positive travel coverage using owner-approved fixtures.

The most recent player-visible assistant narration may be passed to intent classification only as untrusted context for matching a current player description to an active Python-owned NPC candidate. The NPC ID must come from the active candidate list, and its evidence quote must still be exact text from the current player message.

**Why:** Cross-turn references such as “the person you just described” cannot be grounded from the current sentence alone, but narration must not become authority for identity or world state.

**How to apply:** Keep this context short and explicitly labeled as untrusted data; never use it to authorize a new entity, memory, fact, or action.
