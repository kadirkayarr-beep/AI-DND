# Lore conflicts and gaps

This list is for independent review. It does not approve either city. No pack file was edited.

## Packs

| City | Extracted setting constraints | Review manifest | Index coverage | Profile |
|---|---|---|---|---|
| Neverwinter | 14 entities, 7 edges, 20 facts in `neverwinter_the_north_v1` | `neverwinter_the_north_v1.review.json` exists | `VERIFIED_PARTIAL` | Loads for Neverwinter. Not modified. |
| Waterdeep | 0 | Missing | `INCOMPLETE` | `UNREVIEWED / DISABLED` |
| Baldur's Gate | 0 | Missing | `INCOMPLETE` | `UNREVIEWED / DISABLED` |

## Unsupported or incomplete

| ID | Item | Why it is not ready |
|---|---|---|
| GAP-WD-EMPTY | Waterdeep pack | Source stub only. No geography, government, factions, NPCs, religions, culture, languages, or magic rows. |
| GAP-BG-EMPTY | Baldur's Gate pack | Source stub only. Same absence. |
| GAP-NO-REVIEW | Both city packs | No `*.review.json`. `pack_loader` will not treat them as verified. |
| GAP-HEROES-TEXT | Heroes of Faerun | The file is present and its SHA-256 matches the Neverwinter source note, but all 218 pages returned 0 characters. No new page citation from this book was made. SOURCE NOT VERIFIED for any new Heroes sentence. |
| GAP-WD-CHAPTER | Waterdeep chapter | No Waterdeep chapter heading was found in the extractable Adventures text. Adventures PDF page 9 points at *Waterdeep: Dragon Heist*, which was not supplied. |
| GAP-BG-NOT-IN-STUB | Baldur's Gate source choice | Adventures Chapter 6 is readable. The Baldur's Gate stub lists only Heroes, which could not be text-searched. The readable chapter was not extracted. |
| GAP-PRINT-PAGES | Printed page numbers | PDF page numbers above come from the extractor. Printed folio numbers were not established. |
| GAP-SPLITS | Adventures split PDFs | `Forgotten Realms - Adventures in Faerûn-1-200.pdf` (200 pages) and `...-201-437.pdf` (237 pages) were located. They were not reassembled and compared byte-for-byte with the 437-page file. The full file hash matches the Neverwinter Adventures hash. |

## Conflicts

No conflict exists inside the Waterdeep or Baldur's Gate packs, because those packs contain no setting claims.

These are boundaries, not contradictions of an extracted row:

| ID | Boundary |
|---|---|
| BOUND-ADVENTURE | Adventures Chapter 6 mixes a gazetteer with campaigns, stories, conflicts, and "location adventures." Extracting the gazetteer later must not mark those adventures as events that have already happened. |
| BOUND-OTHER-BOOKS | PDF page 9 of Adventures names *Baldur's Gate: Descent into Avernus*, *Waterdeep: Dragon Heist*, and a Baldur's Gate 3 character book. Those books were not the review sources. Their plots are not campaign history. |
| BOUND-NEVERWINTER-ENDPOINT | The Neverwinter pack's `fr:city:waterdeep` row is a route endpoint cited there as Heroes PDF p.89. This pass could not re-read that image page. It is not reopened as a defect, and it is not a Waterdeep city profile. |
| BOUND-ERA | Current campaign epoch remains 1501 DR, Year of the Shining Mythal, as already reviewed for Neverwinter. City packs do not restate it. Older editions were not used to fill the empty packs. |

## Historical lore treated as current

None inside the empty city packs.

## Adventure possibilities treated as established events

None inside the empty city packs. The risk is in Adventures Chapter 6 if a later extraction copies story headings into facts. Those headings are listed in `Baldurs_Gate_Lore_Review_Draft.md` and stay unextracted.

## Items that need a human decision

1. Whether to extract Waterdeep at all before *Dragon Heist* or a readable Heroes page is checked by eye.
2. Which Adventures Chapter 6 sentences are locked setting facts, and which are adventure possibilities.
3. The exact reviewed content hash at approval time. The hashes in `Lore_Activation_Readiness.md` describe the empty stubs only. They must not be reused after the files change.
