---
name: Monster owner evidence
description: Distinguish fixture-owned capability tests from native mechanic coverage in Monster Combat reports.
---

An explicit fixture executor proves a Monster AI integration contract, not that the production game implements that ability. Report native execution and fixture-only coverage separately.

**Why:** Monster Combat was scoped to decisions around existing owners, with new spell, death, movement and persistence architectures excluded. Several mechanics have no production owner; treating a fixture's resolved response as native coverage would conceal that dependency.

**How to apply:** Before claiming a special ability, spell, special movement or defensive reaction works live, verify its actual owner registration and trigger producer. Missing owners must remain unavailable, not return fabricated success.

Live integration must use an explicitly selected, source-verified MM stat block
for its canonical NPC, not infer a block from an NPC name or role. Qualitative
location/presence information cannot be promoted into tactical distance,
directional visibility or a clear movement route.

**Why:** The owner explicitly requires verified production sources and selected
MM mappings, and requires an owner-approved data contract when those sources
are absent rather than invented geometry or perception.

**How to apply:** Audit actual producers before wiring consumers. If the
required source is missing, describe the missing contract and keep the native
HTTP completion criterion unmet; fixture setup does not satisfy it.
