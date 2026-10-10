# Baldur's Gate lore review draft

Status of this document: preparation for independent review. Nothing here is approved. The Baldur's Gate profile stays `UNREVIEWED / INCOMPLETE / DISABLED`.

Prepared against branch `phase8/emergent-storytelling-expansion`, HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`.

Campaign baseline: **1501 DR, Year of the Shining Mythal**. A chapter of adventure hooks is not evidence that those events have already happened.

## What was examined

Pack path:

`ai-dnd/api/lore_authority/packs/baldurs_gate_v1.extraction.json`

| Field | Value |
|---|---|
| Schema version | 1 |
| SHA-256 | `d3aed82e3c2cfb03920e48e06d8454b43f58cca1c75e7a8bb646d0a8c37331fa` |
| `extraction_status` | `REVIEW_REQUIRED` |
| `engine_review_status` | `UNREVIEWED_EXTRACTED` |
| Pack index | `fr:pack:baldurs_gate:v1`, coverage `INCOMPLETE` |
| Review manifest | None |
| Entities | 0 |
| Edges | 0 |
| Facts | 0 |

The file's own note says: "Draft pack only. No Baldurs Gate constraints loaded. Profile stays DISABLED until owner review."

The Neverwinter pack does not contain a Baldur's Gate entity. No Baldur's Gate row was borrowed from it.

## Extracted record

### BG-SRC-001

1. Constraint ID: `BG-SRC-001`
2. Exact existing normalized constraint: source record `SOURCE_FR_HEROES_2025`, title "Forgotten Realms: Heroes of Faerun", edition family "D&D 5e", source tier `TIER_2_OFFICIAL_5E`, `authority_status` `unreviewed`, `region_scope` null. Notes: "Draft pack only. No Baldurs Gate constraints loaded. Profile stays DISABLED until owner review."
3. Sourcebook filename: the record names the book, not a file path.
4. Printed page number: SOURCE NOT VERIFIED
5. PDF page number: SOURCE NOT VERIFIED
6. Section or heading: SOURCE NOT VERIFIED
7. Source-supported explanation: this row identifies a book. It states no Baldur's Gate fact. The Adventures book, which does contain a Baldur's Gate chapter, is not listed as a source on this pack.
8. Authority classification: the Heroes file hash matches the Neverwinter source record (`569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528`). That match does not verify a Baldur's Gate sentence.
9. Applicable era: not stated on this row.
10. Existing review status: `unreviewed` on the source row; pack coverage `INCOMPLETE`.
11. Proposed independent-review decision: `INCOMPLETE`
12. Ambiguity: Heroes has no text layer in this environment, so this pass cannot check the book the stub names.

## Missing topic areas

These are not extracted constraints. Each one is absent from the pack.

| ID | Expected topic | Proposed decision | Evidence |
|---|---|---|---|
| BG-GAP-001 | Established city geography | INCOMPLETE | No entity or fact. A gazetteer heading exists in Adventures; it was not extracted. |
| BG-GAP-002 | Political structures | INCOMPLETE | No entity or fact. SOURCE NOT VERIFIED as a pack constraint. |
| BG-GAP-003 | Major organizations and factions | INCOMPLETE | No entity or fact. |
| BG-GAP-004 | Official named characters | INCOMPLETE | No entity or fact. Names visible in Adventures were not copied into the pack. |
| BG-GAP-005 | Religions and deity affiliations | INCOMPLETE | No entity or fact. |
| BG-GAP-006 | Regional setting history | INCOMPLETE | No entity or fact. |
| BG-GAP-007 | Protected setting facts | INCOMPLETE | No protected-name list for this city. |
| BG-GAP-008 | Plausible campaign-local NPC identities | INCOMPLETE | No reviewed role allowlist. |
| BG-GAP-009 | Permitted minor fictional incidents | INCOMPLETE | No reviewed category allowlist. |
| BG-GAP-010 | Forbidden political or historical inventions | INCOMPLETE | No city-specific list. The general Reality Gate does not run for this city while the profile is unloaded. |

## Source location that was not extracted

`Forgotten Realms - Adventures in Faerûn.pdf` (437 pages, text layer present, SHA-256 `65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848`) contains a Baldur's Gate chapter. These are locations of headings, not extracted constraints and not approvals.

| PDF page | Heading found in extracted text | How to treat it |
|---|---|---|
| 4 | Contents line "Chapter 6: Baldur's Gate" | Pointer only |
| 8 | Chapter blurb for Baldur's Gate | Pointer only |
| 9 | Cross-reference to *Baldur's Gate: Descent into Avernus* | That book was not supplied. Do not treat it as a source for this pack. |
| 20 | Adventure titles marked "Location (Baldur's Gate; see chapter 6)" | Possible stories, not established events |
| 270 | Running header "Baldur's Gate"; trade-nexus sentence begins the chapter body | Setting chapter starts here. Not extracted. |
| 272 | "Baldur's Gate Campaigns"; "Power in Baldur's Gate" | Separate campaign tone from locked political facts during a future extraction. |
| 275 | "People of Baldur's Gate" | Not extracted. |
| 277 | "Danger in Baldur's Gate" | Includes chase tools. Not setting canon by itself. |
| 279 | "MAP: BALDUR'S GATE" | Map exists. Not extracted. |
| 281 | "Baldur's Gate Gazetteer" | The future extraction target for geography. Not extracted. |
| 297 | "Beyond Baldur's Gate" | Surroundings. Not extracted. |
| 302 | "Baldur's Gate Stories" | Possible stories, not campaign history. |
| 303 | "Baldur's Gate Conflicts" | Possible conflicts, not established outcomes. |
| 304–307 | Renown, bastions, encounters | Adventure tools, not history. |
| 308, 309, 317, 318 | "A LOCATION (BALDUR'S GATE) ADVENTURE" | Published adventure possibilities. They have not happened in this campaign unless a later accepted campaign event says so. |

Printed page numbers were not reliably separated from PDF page numbers. Printed page: SOURCE NOT VERIFIED.

No sentence from those pages was written into `baldurs_gate_v1.extraction.json`.

## Counts

| | Count |
|---|---|
| Extracted records examined | 1 source stub |
| Setting constraints (entities, edges, facts) | 0 |
| Supported by an identifiable page citation inside the pack | 0 |
| Incomplete or unsupported | 1 source stub + 10 missing topics |
| Conflicting extracted claims | 0 |
| Readable source chapter located but not extracted | Chapter 6 of Adventures |

## Proposed decision for the pack

`INCOMPLETE`. Not `READY_FOR_REVIEW`. Not approved.
