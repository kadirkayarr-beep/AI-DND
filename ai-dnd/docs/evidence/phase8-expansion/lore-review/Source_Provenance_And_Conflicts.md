# Source provenance and conflicts

Status: UNREVIEWED. This file is review evidence. It does not approve Waterdeep or Baldur's Gate, does not change a production pack, and does not change activation.

Campaign epoch used by the project: 1501 DR, Year of the Shining Mythal. This pass did not re-read that sentence from Heroes of Faerûn. That PDF has no text layer. A claim below is current for 1501 only when a current-authority book states it. Supplemental books describe their own publication era.

## Books inspected

| Book | Path | Year as printed | Pages | Readability | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Sword Coast Adventurer's Guide | `C:\Users\Kadir\Desktop\DND ALL BOOKS\Sword Coast Adventurer's Guide.pdf` | 2015, as cited in the Descent into Avernus credits bibliography | 162 | Text layer present. Waterdeep section on PDF 56 was readable. | `c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51` |
| Volo's Guide to Waterdeep | `C:\Users\Kadir\Desktop\DND ALL BOOKS\Volo's Guide to Waterdeep.pdf` | 1992, as cited in the Sword Coast Adventurer's Guide bibliography | 243 | Text extraction is garbled. CFF fonts warned that fontTools is required. No city fact was taken from it. | `f31b3ce89ae8aec35bc91680dc4539ad0ef9298206343541e33ec9adf350844a` |
| City of Splendors: Waterdeep | `C:\Users\Kadir\Desktop\DND ALL BOOKS\City of Splendors_ Waterdeep.pdf` | 2005, as cited in the Sword Coast Adventurer's Guide bibliography | 159 | Text extraction is garbled. No city fact was taken from it. | `3609eaf001a166ece823067f2cd83678dcb47bd55237e662733c9319620c1b25` |
| Baldur's Gate: Descent into Avernus | `C:\Users\Kadir\Desktop\DND ALL BOOKS\D&D 5e - Baldurs Gate - Descent into Avernus.pdf` | First printing September 2019 | 260 | Text layer present. Gazetteer and chapter 1 overview were readable. | `3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614` |
| Waterdeep: Dragon Heist | `C:\Users\Kadir\Desktop\DND ALL BOOKS\D&D 5e - Waterdeep - Dragon Heist.pdf` | First printing September 2018. ISBN 978-0-7869-6625-7 | 228 | Text layer present. Chapter 9 and the introduction were readable. | `8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455` |
| Waterdeep: Dungeon of the Mad Mage | `C:\Users\Kadir\Desktop\DND ALL BOOKS\D&D 5e - Waterdeep - Dungeon of the Mad Mage.pdf` | First printing November 2018. ISBN 978-0-7869-6626-4 | 322 | Text layer on 321 of 322 pages. Overview and Skullport pages were read. | `23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec` |

Previously located current-authority files, not re-hashed in this pass:

- Heroes of Faerûn: `C:\Users\Kadir\Desktop\Belgeler\PDF\Forgotten Realms - Heroes of Faerun.pdf`. 218 pages, no text layer. Prior SHA-256 `569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528`. No new citation was taken from it.
- Adventures in Faerûn: `C:\Users\Kadir\Desktop\Belgeler\PDF\Forgotten Realms - Adventures in Faerûn.pdf`. Text layer present. Prior SHA-256 `65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848`. Chapter 6 pages were re-read for this pass.

PDFs were read from the external directories above. None were copied into git.

## Page-number method

Printed folios were recorded only when a number was visible in the extract or when the book's own contents listing named the section and that heading was found on the next PDF page.

- Dragon Heist contents list "Entering Waterdeep" at printed 164. That heading is on PDF 165. "The Wards of Waterdeep" is listed at printed 174 and the heading is on PDF 175. Appendix B on PDF 198 ends with the visible folio 197.
- Descent into Avernus PDF 161 begins with the visible folio 160. The gazetteer says the city is described as of 1492 DR.
- Adventures in Faerûn chapter 6 extracts did not show a separate printed folio. Those printed pages are SOURCE NOT VERIFIED.
- Sword Coast Adventurer's Guide PDF 56 contains the Waterdeep section. Its printed folio was not visible in the extract, so the printed page is SOURCE NOT VERIFIED.

## Authority used

Current setting authority for Baldur's Gate in this pass is Adventures in Faerûn chapter 6, because that book was readable. Heroes of Faerûn was not cited.

Supplemental setting authority is Dragon Heist chapter 9 (Volo's Waterdeep Enchiridion), the Sword Coast Adventurer's Guide Waterdeep and Baldur's Gate sections, the Descent into Avernus gazetteer where it describes the city rather than the adventure, and Dungeon of the Mad Mage where it describes Undermountain and the routes into Skullport.

Historical references are the 1992 Volo's Guide and the 2005 City of Splendors. Their prose was not extracted. The 2018 enchiridion itself says the older Volo guide is long out of print.

Adventure modules contribute possibilities. A death, disappearance, victory, destruction, or change of ruler inside those adventures is not campaign history.

## Conflicts left unresolved

1. **C-001 Ravengard.** Adventures in Faerûn PDF 273–274 presents Ulder Ravengard as the current grand duke, still holding the Flaming Fist, and includes an illustration caption of him addressing the people. Descent into Avernus chapter 1 presents him as missing after a mission to Elturel, with Elturel already drawn into Avernus. The gazetteer dates that portrait to 1492 DR. These are competing claims. The adventure starting condition is not adopted as 1501 history.
2. **C-002 Council membership.** Adventures names Duke Dillar Portyr, Duke Brevek Faenor, and Duke Belynne Stelmane beside Ravengard. Descent into Avernus names Duke Dillard Portyr and Duke Thalamra Vanthampur, and places Ravengard offstage. The given-name spelling differs. Vanthampur's 1501 status is unknown. Faenor's status before the Adventures text is unknown.
3. **C-003 Stelmane.** Both Adventures and Descent into Avernus say a mind flayer possesses Duke Belynne Stelmane. Descent into Avernus says her aides do not know. This is restricted knowledge. It is not a public rumor for narration to announce.
4. **C-004 Under-city access.** The Sword Coast Adventurer's Guide says living or digging below Waterdeep has been deemed illegal except by people the lords authorize. The enchiridion says Durnan charges coin to descend the Yawning Portal well into Undermountain. The two statements were not merged into one rule.
5. **C-005 Dragonward and the staff.** Dragon Heist describes Ahghairon's dragonward as a permanent city effect that does not cover the harbor or Undermountain. The same introduction says the dragonstaff is currently held by the gold dragon Aurinax, who guards a hidden vault. The ward is a setting description. Aurinax's custody is adventure state.
6. **C-006 Skullport's present ruler.** Dungeon of the Mad Mage describes Skullport as a settlement reached by the River Sargauth, and also says Xanathar has made it a haven and that most local businesses are shut. The connection is geographic. The shutdown and the beholder's control are module present-tense, not a 1501 fact.
7. **C-007 Waterdeep in 1501.** Adventures in Faerûn has a Baldur's Gate chapter and no matching Waterdeep chapter in the pages previously scanned. Heroes of Faerûn could not be quoted. Waterdeep candidates from 2015 and 2018 books stay supplemental until a reviewer sees the current Forgotten Realms page.
8. **C-008 Older Waterdeep books.** The 1992 and 2005 PDFs did not yield trustworthy text. No tavern, shop, or NPC from those books was marked present in 1501.
9. **C-009 The nine-year gap.** Descent into Avernus dates its Baldur's Gate description to 1492 DR. Dragon Heist does not print a year on the pages read. The campaign epoch is 1501 DR. Nothing in this pass invents the events of the years between.

## What was deliberately left out

- Penalty amounts in the Dragon Heist Code Legal handout. The extracted letters were corrupted (`Flo88in8` and similar). The existence of the code is recorded. The numbers need a visual re-read.
- The Southern Ward's character. The heading appears at the end of Dragon Heist PDF 179. The descriptive paragraph was not captured cleanly.
- Undercliff beyond one sentence: two noble families have estates there.
- Every guild, alley, and walking statue in the enchiridion.
- Level-by-level Undermountain encounters and their aftermaths.
- Descent into Avernus chapter outcomes.
- Any prose from the unreadable historical PDFs.
