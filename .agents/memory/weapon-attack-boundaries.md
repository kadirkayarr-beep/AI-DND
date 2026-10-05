---
name: Weapon attack boundaries
description: Scope decisions behind the shared weapon attack mechanics and their minimal geometry interface.
---

Do not manufacture attack distance, cover, clear push corridors, equipment ownership, proficiency or mastery eligibility from narration, client numbers, or a test's desired outcome.

**Why:** The owner requires PHB 2024 mechanics with Python authority, while the earlier combat system has no authoritative battle-map positioning service. Guessing contact distance would conceal that missing prerequisite.

**How to apply:** Connect a real authoritative producer or use explicit fixture facts. A missing prerequisite is a rejected request or an explicitly unresolved displacement, not permission to assume five feet.

Keep class-specific feature implementation separate from the shared attack extension points. Weapon mastery support is not a grant of mastery to every character.

**Why:** The owner explicitly excluded class-feature bundles, Monster Combat, Spell Scope and UI redesign from this weapon-mechanics phase.

**How to apply:** Let existing feature owners provide trusted grants and overrides; do not infer eligibility from class names or add adjacent systems merely to demonstrate a weapon property.

Finite authored geometry must lose its authority after any successful
displacement whose endpoint is unknown, including reactions and species
teleports. Spending movement or an ability use does not establish a position.

**Why:** Passing ordinary-movement and native encounter tests did not cover
cross-owner movement; stale anchors could still recreate known distance and
visibility after supported displacement.

**How to apply:** Invalidate at the actual successful movement owner, covering
direct and structured calls. Reuse the existing bounded invalidation; never
invent an endpoint. Failed actions and transaction rollback must preserve the
previous geometry, resources and RNG.

Treat a repaired legacy isolation fixture as unproven until its scripted attack
and damage dice are consumed and its post-attack isolation assertions pass.

**Why:** The first missing prerequisite can hide later fixture gaps, including
damage provenance and perception. A valid miss can also produce an owned result
record without damaging the target; that is not cross-campaign leakage.

**How to apply:** Supply explicit test-owned facts through existing owners and
include legitimate result records in expected snapshots. Do not bypass attack
validation or discard unrelated state comparisons to make old tests pass.

Full-state attack regressions must distinguish lazy owner initialization from
attack effects; keep the snapshot comparison complete rather than excluding
observer or character state to hide fixture differences.

**Why:** Minimal armed fixtures can leave encounter mirrors, observer memory,
and neutral species defaults uninitialized. Successful hits reach owners that
misses do not, so otherwise identical fixtures can produce misleading diffs.

**How to apply:** Establish neutral owner state before taking the baseline,
then explicitly expect the legitimate attack sequence, observation, result
record, and HP changes. Keep unrelated state and session-owned RNG assertions.