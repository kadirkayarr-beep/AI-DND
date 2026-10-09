# Waterdeep lore review draft

Status of this document: preparation for independent review. Nothing here is approved. The Waterdeep profile stays `UNREVIEWED / INCOMPLETE / DISABLED`.

Prepared against branch `phase8/emergent-storytelling-expansion`, HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`.

Campaign baseline used by the project: **1501 DR, Year of the Shining Mythal**. Older material is historical or supplemental. A published adventure is a possible story, not campaign history.

## What was examined

Pack path:

`ai-dnd/api/lore_authority/packs/waterdeep_v1.extraction.json`

| Field | Value |
|---|---|
| Schema version | 1 |
| SHA-256 | `09fb42dc45217a029f7898e5884240b6a0978cd9123ca60065f64fe24f741aa5` |
| `extraction_status` | `REVIEW_REQUIRED` |
| `engine_review_status` | `UNREVIEWED_EXTRACTED` |
| Pack index | `fr:pack:waterdeep:v1`, coverage `INCOMPLETE` |
| Review manifest | None |
| Entities | 0 |
| Edges | 0 |
| Facts | 0 |

The file's own note says: "Draft pack only. No Waterdeep constraints loaded. Profile stays DISABLED until owner review."

No Waterdeep geography, government, faction, NPC, religion, culture, language, or magic constraint is in this pack. Those topics are missing material, not silent permission to invent them.

The Neverwinter pack names Waterdeep once, as a route endpoint (`fr:city:waterdeep`, note: "Included only as a directly stated route endpoint."). That row belongs to `neverwinter_the_north_v1`. It was not moved, edited, or treated as a Waterdeep profile.

## Extracted record

### WD-SRC-001

1. Constraint ID: `WD-SRC-001`
2. Exact existing normalized constraint: source record `SOURCE_FR_HEROES_2025`, title "Forgotten Realms: Heroes of Faerun", edition family "D&D 5e", source tier `TIER_2_OFFICIAL_5E`, `authority_status` `unreviewed`, `region_scope` null. Notes: "Draft pack only. No Waterdeep constraints loaded. Profile stays DISABLED until owner review."
3. Sourcebook filename: the record names the book, not a file path.
4. Printed page number: SOURCE NOT VERIFIED
5. PDF page number: SOURCE NOT VERIFIED
6. Section or heading: SOURCE NOT VERIFIED
7. Source-supported explanation: this row identifies a book. It states no Waterdeep fact.
8. Authority classification: file identity of the Heroes PDF matches the hash already stored on the Neverwinter source record (`569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528`). That match does not verify a Waterdeep sentence.
9. Applicable era: not stated on this row.
10. Existing review status: `unreviewed` on the source row; pack coverage `INCOMPLETE`.
11. Proposed independent-review decision: `INCOMPLETE`
12. Ambiguity: the Heroes PDF in this environment has no text layer (218 image pages, 0 extracted characters). This pass did not OCR it and did not invent a page citation.

## Missing topic areas

These are not extracted constraints. Each one is absent from the pack.

| ID | Expected topic | Proposed decision | Evidence |
|---|---|---|---|
| WD-GAP-001 | Official location and geography | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-002 | Districts and settlement structure | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-003 | Political authority and governance | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-004 | Known factions and organizations | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-005 | Faction presence and permitted affiliations | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-006 | Major named NPCs and protected identities | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-007 | Religious institutions and deities | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-008 | Relevant cultural details | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-009 | Languages and local customs | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-010 | Region-specific magical traditions | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED |
| WD-GAP-011 | Plausible minor NPC roles | INCOMPLETE | No city role list. The dormant profile spec still carries the generic role tuple from `_base`, and that spec is not loaded. |
| WD-GAP-012 | Allowed campaign-local fictional additions | INCOMPLETE | No reviewed allowlist. See `Lore_Activation_Readiness.md` for the engine's current refusal. |
| WD-GAP-013 | Forbidden major setting mutations | INCOMPLETE | No city-specific prohibition list. The Reality Gate's general rejects still apply only after a profile loads. This profile does not load. |
| WD-GAP-014 | Unresolved historical or edition conflicts | INCOMPLETE | No extracted claim exists to conflict. |

## What the readable book shows, without becoming a constraint

`Forgotten Realms - Adventures in Faerûn.pdf` has a text layer. A search found no "Chapter: Waterdeep" heading. Waterdeep appears in scattered sentences, including a cross-reference on PDF page 9: "Waterdeep: Dragon Heist details the city of Waterdeep on the Sword Coast."

`Waterdeep: Dragon Heist` is not one of the two books supplied for this review. Its contents were not used.

No sentence from those hits was copied into the pack, and none is proposed as a Waterdeep fact. Printed page numbers for those hits were not separated from PDF page numbers. Printed page: SOURCE NOT VERIFIED.

## Counts

| | Count |
|---|---|
| Extracted records examined | 1 source stub |
| Setting constraints (entities, edges, facts) | 0 |
| Supported by an identifiable page citation | 0 |
| Incomplete or unsupported | 1 source stub + 14 missing topics |
| Conflicting extracted claims | 0 |

## Proposed decision for the pack

`INCOMPLETE`. Not `READY_FOR_REVIEW`. Not approved.
