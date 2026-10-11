# -*- coding: utf-8 -*-
"""Write the V2.2 errata. Reads the frozen V2.2 JSON. Does not modify it."""
import copy
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
V22 = HERE.parent / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json"
BASE = "2255bc3b1a3b2a907e8b639528c1adb78e1b37e9a41b04934469fd6c33b46ee4"

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

actual = sha256(V22)
if actual != BASE:
    raise SystemExit("V2.2 JSON hash changed: " + actual)

doc = json.loads(V22.read_text(encoding="utf-8"))
by = {r["id"]: r for r in doc["records"]}
patches = []

def add(record_id, field, new, reason, evidence):
    old = copy.deepcopy(by[record_id][field])
    if old == new:
        raise SystemExit(f"no change for {record_id} {field}")
    patches.append({
        "record_id": record_id,
        "field": field,
        "old": old,
        "new": new,
        "reason": reason,
        "source_evidence": evidence,
        "base_sha256": BASE,
    })

def cites(record_id):
    return copy.deepcopy(by[record_id]["citations"])

def hero_cite(pages, evidence):
    sample = by["WD22-F-003"]["citations"][0]
    return {
        "source_title": sample["source_title"],
        "edition": sample["edition"],
        "source_sha256": sample["source_sha256"],
        "pdf_pages": pages,
        "printed_page": None,
        "printed_page_status": "not_verified",
        "evidence": evidence,
    }

def adv_cite(pages, evidence):
    sample = by["BG22-F-002"]["citations"][1]
    return {
        "source_title": sample["source_title"],
        "edition": sample["edition"],
        "source_sha256": sample["source_sha256"],
        "pdf_pages": pages,
        "printed_page": None,
        "printed_page_status": "not_verified",
        "evidence": evidence,
    }

# Workstream 1 — support links that match existing facts.
add("WD22-X-004", "supported_by", ["WD22-F-007"],
    "The edge restates the Watch/Guard beat split already in WD22-F-007.",
    "Dragon Heist PDF 169: the City Guard patrols roads, walls, and civic structures and protects magisters; the City Watch polices the streets.")
add("WD22-X-005", "supported_by", ["WD22-F-018"],
    "The edge restates the palace-seat and castle-redoubt split already in WD22-F-018.",
    "Dragon Heist PDF 177: the castle is the last defense, and for well over a century the ruler has occupied the Palace of Waterdeep.")
add("WD22-X-008", "supported_by", ["WD22-F-048"],
    "The patrol sentence is the patrol clause of WD22-F-048.",
    "Heroes of Faerûn PDF 98 OCR: the Field Ward is not patrolled by the city guards.")
add("WD22-X-009", "supported_by", ["WD22-F-054", "WD22-F-005"],
    "Vajra's Blackstaff office is WD22-F-054. The distinct Open Lordship is WD22-F-005. Both are on Heroes PDF 98.",
    "Heroes PDF 98 OCR: Laeral Silverhand is Open Lord; Vajra Safahr currently holds the Blackstaff. The page does not merge the offices.")

# Workstream 1 exceptions stay without a new fact. X-003-2 still gains the missing Heroes citation below.

# Workstream 2 — comparative citations.
c = cites("BG22-F-014")
c[0]["evidence"] = "Paraphrase: the 1492 portrait says the Guild oversees almost every organized criminal act."
c.append(adv_cite([277], "Paraphrase: several syndicates are named, and the Guild is called the most significant local one, led by Nine-Fingers Keene."))
add("BG22-F-014", "citations", c,
    "The 1492 sentence and the current-chapter comparison were both hanging on Avernus PDF 159.",
    "Avernus PDF 159 supports the older Guild sentence. Adventures PDF 277 supports the current syndicate comparison.")

add("BG22-F-017", "claim",
    "The 2015 guide says the dwarven Shattershields are a patriar family. A text search of Adventures PDF 260-329 did not find that name.",
    "The absence is limited to the searched Baldur's Gate span, not the whole book.",
    "Sword Coast Adventurer's Guide PDF 47 names the Shattershields. Adventures PDF 260-329 text has no Shattershield.")
c = cites("BG22-F-017")
c[0]["evidence"] = "Paraphrase: the dwarven Shattershields are named as a patriar family."
c.append(adv_cite(list(range(260, 330)), "Paraphrase: a text search of these PDF pages found no Shattershield. The search is this span only."))
add("BG22-F-017", "citations", c,
    "The positive statement keeps its 2015 citation. The absence citation is the span that was actually searched.",
    "SCAG PDF 47. Adventures PDF 260-329 text search.")

c = cites("WD22-X-003-2")
c[0]["evidence"] = "Paraphrase: the Open Lord is selected and supported by masked lords."
c.append(hero_cite([98], "Paraphrase: Heroes PDF 98 says the Masked Lords rule anonymously beside the Open Lord. That page does not state the selection procedure."))
add("WD22-X-003-2", "citations", c,
    "The selection sentence is SCAG PDF 56. The absence is only Heroes PDF 98, which was read.",
    "SCAG PDF 56: the Open Lord is selected and supported by several masked lords. Heroes PDF 98 OCR contains no 'select' in that government paragraph.")

c = cites("WD22-F-011")
first, second = c[0], copy.deepcopy(c[0])
first["pdf_pages"] = [165]
first["evidence"] = "Paraphrase: arrivals are likely spotted by the Griffon Cavalry."
second["pdf_pages"] = [198]
second["evidence"] = "Paraphrase: the Griffon Cavalry is a special branch of the City Guard."
add("WD22-F-011", "citations", [first, second, hero_cite([98], "Paraphrase: the Defenses paragraph names the griffon cavalry. It does not call it a Guard branch or say arrivals are spotted by it.")],
    "Each positive sentence has its own Dragon Heist page. The absence is scoped to the Heroes PDF 98 Defenses paragraph.",
    "Dragon Heist PDF 165 and 198. Heroes PDF 98 OCR Defenses paragraph.")

c = cites("WD22-F-042")
c[0]["evidence"] = "Paraphrase: Durnan is the Yawning Portal's proprietor; the same paragraph says he built the tavern over the Well and charges coin to descend."
c.append(hero_cite([98], "Paraphrase: Heroes PDF 98 says adventurers descend from a well in the Yawning Portal. That page does not name Durnan or a fee."))
add("WD22-F-042", "citations", c,
    "The fee and the builder stay on Dragon Heist PDF 178. The absence is Heroes PDF 98 only. The text layer renders the second name in that paragraph imperfectly; the proprietor sentence names Durnan.",
    "Dragon Heist PDF 178. Heroes PDF 98 OCR Yawning Portal sentence.")

c = cites("BG22-F-028")
trade, disdain = c[0], copy.deepcopy(c[0])
trade["pdf_pages"] = [161]
trade["evidence"] = "Paraphrase: Baldur's Gate trades with Waterdeep and Neverwinter and contends with Amn."
disdain["pdf_pages"] = [162]
disdain["evidence"] = "Paraphrase: Elturgard and Cormyr view Baldur's Gate as a lawless cesspool that might have to be dealt with."
add("BG22-F-028", "claim",
    "The 1492 gazetteer says Baldur's Gate trades with Waterdeep and Neverwinter, contends with Amn, and is viewed by Elturgard and Cormyr as a lawless cesspool. Heroes PDF 97 states alliance trade ties and names Neverwinter as a member. It does not restate the Amn contention or the Elturgard and Cormyr portrait.",
    "The absence is narrowed to the Heroes PDF 97 alliance paragraph that was read. Neverwinter membership is not treated as a denial of the 1492 trade sentence.",
    "Avernus PDF 161 and 162. Heroes PDF 97 OCR Lords' Alliance paragraph.")
add("BG22-F-028", "citations", [trade, disdain, hero_cite([97], "Paraphrase: the alliance keeps trade ties and names Neverwinter among its members. The examined paragraph does not state the Amn contention or the Elturgard and Cormyr portrait.")],
    "Each 1492 sentence has its own page. Heroes PDF 97 is cited only for the paragraph that was read.",
    "Avernus PDF 161-162. Heroes PDF 97.")

c = cites("BG22-A-004")
avernus = c[0]
avernus["pdf_pages"] = [147]
avernus["evidence"] = "Paraphrase: chapter 5 says the climax can redeem Zariel, save Elturel, or both, and that other outcomes are possible."
add("BG22-A-004", "citations", [avernus, hero_cite([98], "Paraphrase: brave heroes eliminated the Companion and returned Elturel. The page does not choose an adventure ending or name the heroes.")],
    "The multiple-ending sentence is Avernus PDF 147. The return without a chosen ending is Heroes PDF 98. Pages 148-150 were not re-read as separate ending proofs.",
    "Avernus PDF 147. Heroes PDF 98 OCR, Fall of Elturel.")

# Multi-source evidence attribution.
c = cites("WD22-F-017-1")
c[0]["evidence"] = "Paraphrase: the High Road and the Way of the Dragon meet in the heart of the Trades Ward."
c[1]["evidence"] = "Paraphrase: the ward section is headed Trades Ward."
add("WD22-F-017-1", "citations", c,
    "PDF 171 is the landmark sentence. PDF 178 is the heading. Neither citation carries both.",
    "Dragon Heist PDF 171 and 178.")

c = cites("WD22-F-017-3")
hero, heist = c[0], c[1]
hero["evidence"] = "Paraphrase: Heroes PDF 98 calls the market district the Trade Ward."
landmark, heading = copy.deepcopy(heist), copy.deepcopy(heist)
landmark["pdf_pages"] = [171]
landmark["evidence"] = "Paraphrase: Dragon Heist PDF 171 says Trades Ward."
heading["pdf_pages"] = [178]
heading["evidence"] = "Paraphrase: Dragon Heist PDF 178 heads the section Trades Ward."
add("WD22-F-017-3", "citations", [hero, landmark, heading],
    "Each spelling has the page that prints it.",
    "Heroes PDF 98 OCR Trade Ward. Dragon Heist PDF 171 and 178.")

c = cites("WD22-C-001")
c[0]["evidence"] = "Paraphrase: the House of the Moon is a Selûne temple whose tower rises about seventy-five feet."
c[1]["evidence"] = "Paraphrase: the major-temple table names Selûne's temple the Tower of the Moon in the Sea Ward."
c[2]["evidence"] = "Paraphrase: an adventure hook uses the name House of the Moon and does not settle the gazetteer."
add("WD22-C-001", "citations", c,
    "Each citation now carries only the clause its page supports.",
    "Dragon Heist PDF 176 and 177. Adventures PDF 45.")

c = cites("BG22-F-002")
c[0]["evidence"] = "Paraphrase: patriars live in the Upper City, most other people in the Lower City, and refugees and the destitute in the Outer City."
c[1]["evidence"] = "Paraphrase: sturdy walls and gates divide the three districts."
add("BG22-F-002", "citations", c,
    "Heroes PDF 97 supports the population split. Adventures PDF 270 supports the walls and gates.",
    "Heroes PDF 97 OCR. Adventures PDF 270.")

c = cites("BG22-C-001")
c[0]["evidence"] = "Paraphrase: people without a patriar, livery, or letter must use the gate called Baldur's Gate between the Upper and Lower Cities."
c[1]["evidence"] = "Paraphrase: Gond Gate, Heap Gate, Manor Gate, and Sea Gate are vital for commerce and travel."
add("BG22-C-001", "citations", c,
    "The 2015 limit and the current vital-gates sentence are no longer copied onto each other.",
    "SCAG PDF 47. Adventures PDF 281.")

c = cites("BG22-X-007")
c[0]["evidence"] = "Paraphrase: the Chionthar gives seagoing vessels access to Gray Harbor."
c[1]["evidence"] = "Paraphrase: Gray Harbor is a deep harbor on the Chionthar."
add("BG22-X-007", "citations", c,
    "PDF 270 supports access from the river. PDF 288 supports the deep-harbor wording.",
    "Adventures PDF 270 and 288.")

add("BG22-X-008", "claim",
    "The Guild is Baldur's Gate's principal local criminal organization. Nine-Fingers Keene leads it.",
    "The editorial sentence about agent placements stays in the forbidden field, not in the claim.",
    "Adventures PDF 277 and Heroes PDF 97 both name her leadership. The banking sentence is not part of this public claim.")
c = cites("BG22-X-008")
c[0]["evidence"] = "Paraphrase: the Guild is the most significant local syndicate and is led by Nine-Fingers Keene."
c[1]["evidence"] = "Paraphrase: the Guild operates under the leadership of Nine-Fingers Keene."
add("BG22-X-008", "citations", c,
    "Each page's evidence stops at leadership.",
    "Adventures PDF 277. Heroes PDF 97 OCR leadership sentence.")

# Workstream 3 — claim-specific constraints.
add("WD22-F-023-3", "forbidden_mutation",
    "Do not drop the extra sale tax on a blade longer than one foot, and do not turn this row into a dueling rule.",
    "The inherited text forbade legalizing duels. This row is the blade tax.",
    "Dragon Heist PDF 169: a blade more than one foot long is subject to an extra tax when sold.")
add("BG22-F-011-1", "forbidden_mutation",
    "Do not decide that the Council has stopped paying the Flaming Fist or name a different payer.",
    "The inherited text was about Outer City patrol and Upper City rule.",
    "Adventures PDF 274: the Council pays the Fist to defend, patrol, and punish.")
add("BG22-F-011-2", "forbidden_mutation",
    "Do not move the Flaming Fist headquarters away from the Seatower of Balduran.",
    "The inherited text was about Outer City patrol and Upper City rule.",
    "Adventures PDF 274: headquarters at the Seatower.")
add("BG22-F-011-3", "forbidden_mutation",
    "Do not give the Flaming Fist routine rule of the Upper City. This row says the Fist defers to the Watch there.",
    "This is the Upper City clause, not the Outer City frequency clause.",
    "Adventures PDF 274.")
add("BG22-F-011-4", "forbidden_mutation",
    "Do not treat Lower City activity as exclusive authority over the Upper or Outer City.",
    "This row is only the Lower City activity statement.",
    "Adventures PDF 274.")
add("BG22-F-011-5", "claim",
    "The Flaming Fist rarely patrols the Outer City, and then in large numbers for a specific goal.",
    "The gloss 'rarely does not mean never' is a constraint, not a second source sentence.",
    "Adventures PDF 274 uses rarely for Outer City patrols.")
add("BG22-F-011-5", "forbidden_mutation",
    "Do not change rarely into never or into always. Rarely is not a guaranteed absence.",
    "The frequency limit belongs on this child only.",
    "Adventures PDF 274.")
add("BG22-F-011-6", "forbidden_mutation",
    "Do not move the Wyrm's Rock tax post or decide that the bridges are raised. Python resolves that state.",
    "The inherited text was about Outer City frequency and Upper City rule.",
    "Adventures PDF 274: the Fist staffs Wyrm's Rock for taxes and raises the bridges at night.")
add("WD22-F-009-2", "forbidden_mutation",
    "Do not treat the truncheon, dagger, and buckler as gear every Watch member must carry. Typically is not universal.",
    "The inherited text was about the uniform's 1501 status.",
    "Dragon Heist PDF 169: each typically carries those three items.")
add("WD22-F-009-3", "forbidden_mutation",
    "Do not describe this lantern as the Watch uniform. It marks a watch post.",
    "The inherited text was about the uniform.",
    "Dragon Heist PDF 169: a watch post is marked by a green-and-gold continual-flame lantern.")
add("WD22-F-058-1", "forbidden_mutation",
    "Do not treat the twenty-three-floor count as a cleared dungeon or a finished adventure.",
    "The inherited text said 'him,' which does not refer to the dungeon.",
    "Heroes PDF 98 OCR: twenty-three-floor megadungeon.")
add("WD22-F-058-4", "forbidden_mutation",
    "Do not import a module shutdown into this existence claim, and do not treat Skullport's presence here as a completed adventure.",
    "The inherited text said 'him,' which does not refer to the other founders or to Skullport.",
    "Heroes PDF 98 OCR: other creatures founded places in Undermountain, including Skullport.")
add("WD22-X-004", "forbidden_mutation",
    "Do not merge the Watch and the Guard, and do not give either force the other's beat.",
    "The inherited text was about a secret cause or a change of office.",
    "Dragon Heist PDF 169.")
add("WD22-X-005", "forbidden_mutation",
    "Do not move the ruler into the Castle or declare the Palace vacant.",
    "The inherited text was about a change of office.",
    "Dragon Heist PDF 177.")
add("WD22-X-006", "forbidden_mutation",
    "Do not open or close the well, and do not treat a descent as already completed.",
    "The inherited text was about a change of office.",
    "Heroes PDF 98: the Yawning Portal well is an entrance.")
add("WD22-X-008", "forbidden_mutation",
    "Do not give the Field Ward a routine city-guard patrol.",
    "The inherited text was about a change of office.",
    "Heroes PDF 98: the Field Ward is not patrolled by the city guards.")
add("BG22-X-006", "forbidden_mutation",
    "Do not treat this road statement as a journey the party has taken.",
    "The inherited text was about a death or a coup. This row is a road fact.",
    "Adventures PDF 281: the road from Black Dragon Gate leads north to Waterdeep.")
c = cites("BG22-A-003-1")
c[0]["pdf_pages"] = [4]
c[0]["evidence"] = "Paraphrase: the contents list Dungeon of the Dead Three and Vanthampur Villa as chapter 1 sections."
add("BG22-A-003-1", "citations", c,
    "PDF 4 is the contents list. PDF 6 names the Dead Three cult and does not name those two locations.",
    "Avernus PDF 4 contents: Dungeon of the Dead Three and 1.5 Vanthampur Villa.")
add("BG22-A-003-2", "claim",
    "Chapter 1 presents the Dead Three killings and the characters' hunt for their lair as the adventure the players enter, not as a finished history.",
    "PDF 6 does not say that fights inside the dungeon or the villa have or have not already happened. It does present the killings and the hunt as the players' chapter.",
    "Avernus PDF 6: the characters are ordered to root out Dead Three followers who are murdering city folk, and they investigate.")
c = cites("BG22-A-003-2")
c[0]["evidence"] = "Paraphrase: the characters are ordered to root out Dead Three followers who are murdering city folk, and they investigate."
add("BG22-A-003-2", "citations", c,
    "The evidence now quotes the page's situation instead of repeating the old editorial sentence.",
    "Avernus PDF 6.")
add("WD22-E-002", "claim",
    "The Open Lord is named in the cited passage.",
    "Heroes PDF 98 names the Open Lord. It does not use the label Office of the Open Lord.",
    "Heroes PDF 98: the current Open Lord, Laeral Silverhand, keeps her identity known to the public.")
c = cites("WD22-E-002")
c[0]["evidence"] = "Paraphrase: the current Open Lord is Laeral Silverhand."
add("WD22-E-002", "citations", c,
    "The evidence now follows the sentence on the page.",
    "Heroes PDF 98.")
c = cites("WD22-E-017")
c[0]["evidence"] = "Paraphrase: the Blackstaff is currently Vajra Safahr."
add("WD22-E-017", "citations", c,
    "The page image spells Safahr. The OCR text drops the final r.",
    "Heroes PDF 98 image: currently Vajra Safahr.")
c = cites("WD22-R-001")
c[0]["evidence"] = "Paraphrase: even foreign dignitaries may retain only up to sixteen armed warriors."
add("WD22-R-001", "citations", c,
    "The page limits dignitaries to sixteen warriors. It does not exempt envoys.",
    "Dragon Heist PDF 173.")
c = cites("WD22-F-044")
c[0]["evidence"] = "Paraphrase: the harbor was cleared of the broken ships that made up Mistshore, and Waterdeep again has its own navy."
add("WD22-F-044", "citations", c,
    "The page says broken ships, not the word wrecks. The claim's wrecks is that paraphrase and stays. The evidence now follows the sentence.",
    "Sword Coast Adventurer's Guide PDF 56.")
add("BG22-X-010", "forbidden_mutation",
    "Do not raise or lower the bridges or collect the tax by narration. Python resolves that state.",
    "The inherited text was about a death or a coup.",
    "Adventures PDF 274.")

exceptions = [
    {
        "record_id": "WD22-X-001",
        "reason": "No separate fact states the five passes or the River Sargauth link. The edge cites Dungeon of the Mad Mage PDF 304 directly. A duplicate fact was not added.",
        "source_evidence": "Mad Mage PDF 304: Skullport connects to Undermountain level 3 by the River Sargauth and by Beggar's Rest Pass, Shadow Pass, Steamfall Pass, Taglath's Gap, and Whisperhaunt Pass. Few souls of the surface world know the way.",
    },
    {
        "record_id": "WD22-X-003-2",
        "reason": "No separate fact states the 2015 selection procedure. After the Heroes PDF 98 citation is added, the edge still carries that procedure from SCAG PDF 56. WD22-F-003 states anonymous rule, not selection, so it is not used as support.",
        "source_evidence": "SCAG PDF 56 selection sentence. Heroes PDF 98 anonymous-rule paragraph.",
    },
]

errata = {
    "base_file": "lore-review-v2-2/lore_extraction_candidates_v2_2.draft.json",
    "base_sha256": BASE,
    "id_policy": "V2.2 IDs are unchanged. Patches replace fields on those IDs.",
    "direct_source_exceptions": exceptions,
    "patches": patches,
}
(HERE / "field_errata.json").write_text(json.dumps(errata, indent=2, ensure_ascii=False), encoding="utf-8")

changed = sorted({p["record_id"] for p in patches})
summary = ["# V2.2 errata summary", "", f"Base JSON SHA-256 `{BASE}`.", "", f"Field patches: {len(patches)}. Records with at least one patch: {len(changed)}.", "", "V2.2 IDs are not renamed. BG22-X-006, BG22-X-009, and BG22-X-010 stay facts.", "", "## Records", ""]
for rid in changed:
    reasons = [p["reason"] for p in patches if p["record_id"] == rid]
    summary.append(f"- `{rid}`: " + " ".join(reasons))
summary += ["", "## Direct-source exceptions", "", "- `WD22-X-001` keeps an empty supported_by. Mad Mage PDF 304 is the support.", "- `WD22-X-003-2` keeps an empty supported_by. SCAG PDF 56 states the selection procedure; Heroes PDF 98 is only the page-scoped absence.", "", "## Not regressed", "", "BG22-F-005, WD22-F-057, WD22-F-004, WD22-F-013, WD22-F-023-2, BG22-E-020, and BG22-E-016 have no patch.", ""]
(HERE / "correction_summary.md").write_text("\n".join(summary), encoding="utf-8")

def file_hash(path):
    return sha256(path)

v22_dir = V22.parent
manifest_files = []
for folder in (v22_dir, v22_dir.parent / "lore-review-v2-1", v22_dir.parent / "lore-review-v2", v22_dir.parent / "lore-review"):
    for path in sorted(folder.iterdir()):
        if path.is_file():
            manifest_files.append({"path": str(path.relative_to(HERE.parents[4])).replace("\\", "/"), "sha256": file_hash(path), "bytes": path.stat().st_size})
(HERE / "input_manifest.json").write_text(json.dumps({"base_sha256": BASE, "files": manifest_files}, indent=2), encoding="utf-8")
print("patches", len(patches), "records", len(changed), "manifest", len(manifest_files))
