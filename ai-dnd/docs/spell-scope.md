# Spell Scope Lock — bounded V1

Python alone resolves spells. This is not a general spell/class progression
engine. Qwen and the frontend cannot grant access/resources or author effects.

## Sources and access

The supplied source-verified PHB 2024 Chapter 7 contracts govern these four
spells. Checked against the current uploaded PHB text: Cure Wounds p.259,
Fire Bolt pp.274–275, Magic Missile p.295, Sacred Flame p.313. Fire Bolt and
Sacred Flame scale at levels 5, 11 and 17. No 2014 healing/damage substitution.

Creation's validated class selections produce canonical `spellcasting_v1`
inside the existing world save. Only selected class cantrips and legitimate
prepared selections confer access; an entry in the catalog alone does not.
Unlisted feature/item/scroll access is unavailable, not inferred.

Wizard creation selects six spellbook entries, while PHB 2024 requires choosing
four prepared entries. There is no preparation-selection owner. Wizard leveled
casting is therefore unavailable; selecting Magic Missile in a spellbook is not
permission to cast it. Existing Cleric/Druid creation selects two leveled spells,
whereas the 2024 feature requires four prepared spells. Their leveled casting is
also unavailable. No automatic preparation or class progression repair is made.
Their legitimate selected cantrips remain usable.

Legacy saves without the new access/resource record cannot cast; no access or
full slot pool is fabricated on resume. New character creation records it.

## Capability matrix

| Capability | V1 | Deferred | Current owner | Notes |
|---|---|---|---|---|
| Access/prepared validation | Selected compatible class access | Wizard preparation; Cleric/Druid leveled preparation; other feature/item grants | `character_creation.configure_character`, `spell_scope` | Source conflicts are gated, not silently promoted |
| Cantrips | Selected Fire Bolt/Sacred Flame; level scaling | Other cantrips | `spell_scope`, session level/PB | Inconsistent level/PB rejects |
| Slots | Level-one capacity, one slot per turn, Long Rest refresh | Higher slots/upcasts; progression; pact/other recovery features | `spell_scope`, existing rest owner | No short-rest recovery invented |
| Spell attack | Plain visible creature Fire Bolt | Modified/point-blank/condition/rider attacks | `core_resolution.resolve_attack_roll` | No weapon proficiency/mastery/damage leakage |
| Spell save | Sacred Flame Dexterity, sourced modifier, existing auto-failure/Dodge/resistance-window hooks | Unsupported modified saves | `weapon_attack.save`, `core_resolution.resolve_saving_throw` | Half/three-quarter cover ignored |
| Damage | Defined dice, native mitigation, NPC Policy A | Unknown special defenses/riders | `roll_damage`, `weapon_attack.mitigate`, `apply_npc_damage` | No direct spell-specific HP shortcut |
| Healing | Conscious player's self Cure Wounds | NPC recipients/external casters | `heal_player` | HP cap; no unconscious self-casting/resurrection |
| Range | 120/60 feet; self Touch | Unknown geometry | `weapon_attack.pair` | Never derive distance from prose |
| Target | Explicit canonical participating NPC; self for healing | Objects, invisible targets, unsupported defenses | Existing registry/combat/geometry | No implicit target choice |
| Multi-target | All three MM darts to one creature | Split darts/multiple recipients | `spell_scope` | Simultaneous one-recipient damage handoff |
| Area | No | Yes | No V1 geometry owner | Reject before casting |
| Conditions | Consume only explicitly compatible existing state | Persistent spell conditions | Existing condition owners | No new condition system |
| Duration | Instantaneous only | Persistent durations/scheduler | Existing time owners | No new scheduler |
| Concentration | No | General concentration, including damage saves | No V1 concentration owner | Concentrating targets rejected, not silently damaged |
| Reactions | No spell reactions | Counterspell, Shield, reaction catalog | Existing reaction owner, no spell executor | Reject before spending reaction |
| Bonus Action spells | No | General catalog | Existing action owner | V1 Magic is an Action |
| Rituals | No | Ritual timing | No V1 ritual owner | Reject |
| Material-cost economy | No | Materials/cost/consumption | No V1 material owner | These candidates require V/S only |
| Summons | No | Yes | No V1 owner | No invented actors |
| Transformations | No | Yes | No V1 owner | No invented stats |
| Teleportation | No spell support | General spell framework | Existing species owner remains separate | Not generalized |
| Dispelling/countering | No | Yes | No V1 owner | No inferred cancellation |
| Environmental effects | No | Object ignition/destruction/fire | No V1 environment owner | Object Fire Bolt rejects |

## Exact supported catalog modes

- **Fire Bolt:** selected Wizard/Sorcerer class cantrip, active player combat
  turn, one explicitly visible participating NPC, 120 feet, clear path, no
  unsupported actor/target conditions or tracked attack/species modifiers and
  no conscious participant within five feet. Shared attack roll: ability + PB,
  natural 1 miss, natural 20 critical, critical doubles spell dice. Fire damage
  is 1/2/3/4d10 at levels 1/5/11/17. Existing half/three-quarter AC cover applies.
  Object ignition, blind/point-blank attacks and unsupported modifiers reject.
- **Magic Missile:** selected/prepared Sorcerer spell, character level one,
  one visible participating creature within 120 feet, one level-one slot.
  Three 1d4+1 Force darts; no attack/save roll. All darts are rolled before one
  simultaneous HP handoff; native resistance/immunity applies to each dart.
  Split targets, upcasts, free feature casting and unsupported defenses reject.
- **Cure Wounds:** selected/prepared Bard/Paladin/Ranger spell, character level
  one, existing combat turn, conscious living player targeting themselves.
  One level-one slot; 2d8 + class casting modifier through `heal_player`, capped
  at maximum HP. Bard catalog now includes this source-verified candidate.
  NPC recipients lack an existing healing owner and reject; the player cannot
  self-cast at 0 HP or while dead. No external caster/control route is fabricated
  to prove a currently unreachable zero-HP recipient mode.
- **Sacred Flame:** selected Cleric cantrip, one visible participating creature,
  60 feet. Shared Dexterity save vs 8 + Wisdom modifier + PB. No damage on
  success; 1/2/3/4d8 Radiant on failure at levels 1/5/11/17. Half/three-quarter
  cover gives no save bonus; total cover still blocks the path. Unknown save
  modifiers, restrained saves, unsupported defenses and concentration reject.

## Transactions, API and narration

Use the **existing** turn contract: `combat_action.steps` with
`kind: "magic"`, `ability: "<exact spell name>"`, `target_id: "<NPC ID or player>"`.
No new request schema or frontend spell UI. Explicit English names/Turkish
aliases also propose the same command through `message` plus `target_id`.
Questions/negations are not casts. Ambiguous targets and compound/split/ritual/
upcast/free-cast modes fail closed; they are not PHB invalid-target casts.

Validate actor, access, mode, target, range, components (existing free-hand
equipment plus speech-blocking conditions), action and slots before resolution.
Unsupported engine modes consume no slot/action/RNG/HP/time. There is no support
for secretly invalid/illusory-target resolution and its PHB slot-consumption
rule; such uncertainty must not be promoted into a supported V1 cast.

Magic consumes the existing Action and leaves the turn open for explicit
completion. Campaign Time advances through existing turn/rest owners, not once
again for each spell. Slots and the turn-use marker live in the existing save;
shared action transaction, session RNG and campaign receipts remain authoritative.
Saved spell access, counts and markers are validated before loading.

Explicit V1 casts use **zero model calls** and deterministic narration of the
resolved result. No model retry, proposal-granted resources or narrated HP
mutation. Existing nonspell turns retain their maximum-two-call/fallback policy.
NPC spell capability executors remain unavailable; no allied-NPC control or
autonomous spellcasting is introduced.

## Verification

Focused engine and real HTTP tests cover attack hit/miss/critical/scaling,
save success/failure/DC/cover, slots/action/component/range/access rejections,
simultaneous MM damage and mitigation, HP/death/healing owners, zero-HP NPC
damage and rejection of unconscious self-healing, receipt replay before stale
context, fresh-manager resume/replay, persisted RNG/resources, isolation and
zero-model operation. Durable suite evidence is append-only; failed runs and
prior Death certification remain retained.