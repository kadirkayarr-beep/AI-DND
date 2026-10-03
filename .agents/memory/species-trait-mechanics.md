---
name: Species trait mechanics
description: Server authority and timing edge cases for D&D species abilities.
---

Species abilities are resolved by the game engine: it owns rolls, uses, recharge, and combat effects. For timed conditions, reason from the actual turn-counter increment and expiration path, then test through a complete turn transition. Relentless Endurance must not trigger when post-mitigation damage meets the massive-damage instant-death threshold.

**Why:** Client-side mechanics drift from the engine, and off-by-one durations or survival at instant death can change canonical outcomes.

**How to apply:** Keep UI controls as requests and render the returned result and state. Cover activation, opponent response, turn advancement, recharge/save-resume, and the fatal-damage boundary in engine tests.