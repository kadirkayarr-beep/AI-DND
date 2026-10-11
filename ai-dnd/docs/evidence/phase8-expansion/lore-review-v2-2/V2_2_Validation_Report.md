# V2.2 validation report

Command: `python ai-dnd/docs/evidence/phase8-expansion/lore-review-v2-2/validate_v22.py`

Branch `phase8/emergent-storytelling-expansion`. HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`.

Failed checks: 0.

Semantic checks re-read Adventures PDF 109, 273, and 274; Dragon Heist PDF 7, 167, and 169; and Descent into Avernus PDF 163. They compared those pages with the saved claims. The other citation paraphrases were checked for structure, labels, page bounds, and source hashes. They were not each re-read against the page in this run.

No split PDF was used. Page numbers are one-based pages of the full files.

## Results

- PASS json parses without duplicate keys
- PASS 202 unique ids — 202
- PASS top-level not approved and not loadable
- PASS required fields present
- PASS all draft unreviewed not loadable
- PASS narration constraint on every row
- PASS no approved disposition
- PASS 202 V2.1 parents once
- PASS 180 V2 parents — 180
- PASS 115 V1 ids — 115
- PASS forward and reverse mapping
- PASS references resolve and public links stay public
- PASS edges are complete and reclassified rows are facts — 17
- PASS citation pages are integers and evidence is labeled
- PASS citation hashes are known sources
- PASS no invented Heroes or Adventures folio
- PASS source hashes match the cited files
- PASS cited pages are inside the full PDFs — {'569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528': 218, '65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848': 437, '8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455': 228, '3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614': 260, 'c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51': 162, '23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec': 322}
- PASS no split-pdf offset was required — full files were opened; page counts are the full-file counts
- PASS Ravengard claim omits physical presence
- PASS Ravengard offices match pages 273 and 274
- PASS Elminster claim keeps source scope
- PASS governance row is historical
- PASS dragon-type scope
- PASS tavern wording is nonabsolute
- PASS Portyr cites both spellings
- PASS Seatower evidence matches its support
- PASS public text does not embed restricted secrets
- PASS discovery route stays gated
- PASS rejected claims are not current facts
- PASS every conflict id is still open in the conflict note
- PASS epoch still linked from remaining supplemental rows
- PASS markdown ids and claims match json — mismatch 0
- PASS shared record is named in both city files
- PASS V1 V2 and V2.1 hashes unchanged
- PASS production and profile diff is empty
- PASS branch and HEAD match the reported baseline — phase8/emergent-storytelling-expansion f63d952506064cd59e960f1e3efa6627d4e52053

## Git status

```
?? ai-dnd/docs/evidence/phase8-expansion/lore-review-v2-1/
?? ai-dnd/docs/evidence/phase8-expansion/lore-review-v2-2/
?? ai-dnd/docs/evidence/phase8-expansion/lore-review-v2/
?? ai-dnd/docs/evidence/phase8-expansion/lore-review/
```

`git diff` for profiles, packs, and `game.py` was empty.

## Preservation

V1, V2, and V2.1 hashes matched the hashes recorded before this correction. Source PDF hashes matched the citation hashes. Full-file page counts: {'569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528': 218, '65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848': 437, '8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455': 228, '3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614': 260, 'c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51': 162, '23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec': 322}.

## V2.2 readiness hash

- `V2_2_Independent_Review_Readiness.md` SHA-256 `f48458ab1234d9d8604a313d2e803595342428f78b3d6656af436f1e5f330c87`

This report is not included in that hash.
