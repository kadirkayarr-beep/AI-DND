# V2.2 correction findings

Status: DRAFT. These findings are not owner approval. No record is APPROVED or REVIEWED. No city is activated.

ID convention: the version token 21 becomes 22. `BG21-F-005` becomes `BG22-F-005`. Each V2.1 record has one V2.2 child. A reclassified edge keeps its X id and changes kind to fact.

The passages below were read from the full PDFs in `C:\Users\Kadir\Desktop\DND ALL BOOKS` during this correction. Page numbers are one-based pages of those full files. No split PDF was used.

## BG21-F-005 -> BG22-F-005

- Problem: the claim said “He is in the city in the current books.”
- Source: Adventures in Faerûn PDF 273 and 274.
- What the pages support: he is the current grand duke, remains supreme marshal, works at both duties, has led the city through recent tribulations, and his inattention while occupied as grand duke is followed by the Flaming Fist sliding into oppression, brutality, heavy-handed bullying, and corruption.
- What they do not support: a current street location, scene presence, encounter availability, or campaign travel. “Prosperity in the city” and “led the city” are leadership wording, not a statement that he is physically present.
- Correction: the physical-presence sentence was removed. The offices and the stated effect on the company remain. Dependent identity row: `BG22-E-012`.
- Owner decision: none opened or closed.

## WD21-F-057 -> WD22-F-057 and C-V2-ELMINSTER

- Problem: V2.1 added “there,” which narrows “hasn’t been seen in all that time.”
- Source: Adventures in Faerûn PDF 109, in the Shadowdale discussion. The former windmill has been locked and abandoned for a decade. Elminster hasn’t been seen in all that time. The page says it would be foolish to assume he is dead.
- Correction: the claim uses that wording and attributes it to the Shadowdale discussion. It does not decide that the sentence means absence from all Faerûn, or absence only from Shadowdale. It does not infer death, resignation, a vacant wardenship, a current location, a replacement, or a return date.
- Dependent row: `WD22-E-018` states the public name and titles only. The restricted wardenship remains on its own row.
- Owner decision: whether the older Waterdeep wardenship persists. Still open.

## WD21-F-004 -> WD22-F-004

- Problem: “hidden even from each other” was carried as an unsettled current-style statement.
- Source: Dragon Heist PDF 166 opens Age Two, The Lords’ Rule Begins, including the 1032 DR dispute. PDF 167 says Ahghairon decreed the government and that the other lords’ identities would be hidden even from each other.
- Correction: fact class is historical. Applicability is historical_setting. Knowledge stays restricted. The 1501 continuation is not treated as verified and stays under `C-V2-EPOCH`.
- Owner decision: whether that historical concealment is still the practice in 1501. Still open. This row is no longer one of the supplemental candidates.

## WD21-F-013 -> WD22-F-013

- Problem: the exception was limited to “a dragon.”
- Source: Dragon Heist PDF 7. A creature of the dragon type touched by the dragonstaff can ignore the ward until touched again, or until a time specified by someone attuned to the staff.
- Correction: the claim uses creature-of-the-dragon-type scope and both conditions. It stays restricted and supplemental_unconfirmed_1501. No mechanic was implemented.
- Owner decision: whether the 2018 exception still applies in 1501. Still open under `C-V2-EPOCH`.

## WD21-F-023-2 -> WD22-F-023-2

- Problem: the tavern sentence was written as an exemption from arrest.
- Source: Dragon Heist PDF 169. Caught brawlers are arrested regardless of who started the fight. The described tavern brawls will often be overlooked when the proprietor does not seek payment for damages and nobody is significantly injured.
- Correction: the claim keeps “often” and both conditions. The forbidden field says this is not a guaranteed exemption.
- Owner decision: whether the 2018 watch practice applies in 1501. Still open under `C-V2-EPOCH`.

## BG21-E-020 -> BG22-E-020

- Problem: the claim compared two spellings while citing only Adventures PDF 273.
- Source: Adventures PDF 273 names Duke Dillar Portyr. Descent into Avernus PDF 163 names Duke Dillard Portyr.
- Correction: both citations are on the record. The spellings are not merged and no errata was declared.
- Owner decision: `C-V2-PORTYR` stays open.

## BG21-X-006, BG21-X-010, BG21-X-009

- Problem: the records were edges with missing endpoints or no relationship type.
- Correction: all three are reclassified as facts. No gate, fortress, or relationship entity was invented. `BG22-X-006` does not use the city of Waterdeep as a stand-in for Black Dragon Gate. `BG22-X-010` does not invent Wyrm’s Rock. `BG22-X-009` stays a described dusk practice and points at the existing Watch fact `BG22-F-010`.
- Related edge: `BG22-X-002` now says only that the Council directs the Flaming Fist, because that is the endpoint pair. Navy and taxes remain on `BG22-F-004`.
- Owner decision: none.

## BG21-E-016 -> BG22-E-016

- Problem: `supported_by` pointed at the Seatower fact, while the evidence text still named the other Flaming Fist child.
- Correction: the evidence paraphrases the Seatower headquarters sentence on Adventures PDF 274. The structured link is `BG22-F-011-2`.
- Owner decision: none.

## Citation evidence across the package

Evidence fields that repeated a claim without a label, named an internal record, or carried reviewer commentary now begin with “Paraphrase:” and omit those notes. Safety instructions stay in `forbidden_mutation`. This normalization is why most rows are disposition `corrected` even when the setting claim itself did not change.

These paraphrases are not presented as verbatim quotations. Apart from the passages named above, this pass did not re-read every cited page. The page numbers and source hashes remain those verified for V2.1, and the corrected claims were checked against the pages named in this file.

## Dispositions

See `V2_1_to_V2_2_Record_Mapping.md` for all 202 rows. None is approved. None is unresolved as a blocked correction. Owner conflicts stay open on the conflict records.
