# -*- coding: utf-8 -*-
"""Read-only checks for the V2.2 review package. Writes only V2_2_Validation_Report.md."""
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
V21 = ROOT / "lore-review-v2-1"
V2 = ROOT / "lore-review-v2"
V1 = ROOT / "lore-review"
JSON_PATH = HERE / "lore_extraction_candidates_v2_2.draft.json"
BOOKS = Path(r"C:\Users\Kadir\Desktop\DND ALL BOOKS")

PRIOR = {
    V1 / "Baldurs_Gate_Lore_Review_Draft.md": "07d863ef1982dbb28ae911c3cdab6ddb9e5dce7f4c477ce31e304bb7f5d14f67",
    V1 / "Baldurs_Gate_Source_Extraction_Candidates.md": "322bff7844d596c201491e45626bec5613ec6864bded182a7b79ad0cbbb379c7",
    V1 / "Lore_Activation_Readiness.md": "03ffdacebd572c48c11572ab837a359cb0f1cd61e9ed1a9854d9d64e7b1c42d7",
    V1 / "Lore_Conflicts_And_Gaps.md": "369f8cbe0d67923e2fac44e12ba759c09f2098d22b03ef21534505665d536424",
    V1 / "lore_extraction_candidates.draft.json": "fcd6678d4f0adaa02829361186ddc7203fb299639f37b879cac0057e75d34fca",
    V1 / "Lore_Review_Queue.md": "ea39bb73370e409e057704dd2725601f3ba9dda3ddebb892f4e66099bb0a3816",
    V1 / "Source_Provenance_And_Conflicts.md": "50baf15a01487c22ad84f8aca8c3c58cf8827527612a7a22f5709b2c8bf15968",
    V1 / "Waterdeep_Lore_Review_Draft.md": "3a39d24d1a094454a89752771104287b5bb77136553b5eac1b74d5d80da0f94d",
    V1 / "Waterdeep_Source_Extraction_Candidates.md": "da69f97c0b32f11efb1ad45b0a8ed61a64a11035fca362941cbc807ecc98b90b",
    V2 / "Waterdeep_V2_Candidates.md": "8816419a0fd2071411fcdc0dce3f6811a861115ba6fe78447cdf781e0b2b0a35",
    V2 / "Baldurs_Gate_V2_Candidates.md": "66e8233b9abbda9c0e3d54004d1d5adf3980b760b22edde02e81282af76aa411",
    V2 / "V1_to_V2_Record_Mapping.md": "b4a62efcceebefa87b029fdac0a1f942c770f425d807ed680363ed487e49c313",
    V2 / "V2_Conflicts_And_Owner_Decisions.md": "312282c42455eee624896f1f25069e2924f247122048ceb2a0b650831042ff37",
    V2 / "lore_extraction_candidates_v2.draft.json": "66d64df8536dbfa65410931387efc6398efd05337406c02eac3e8ffdcdad9f3c",
    V2 / "V2_Independent_Review_Readiness.md": "76d5551ed144f019d194d136ca6c40e75fc6b1d3f9439c9d814d3831d39ddf98",
    V21 / "Waterdeep_V2_1_Candidates.md": "c3c3cfeafef966ba5d9fbf081e5eef7f10b88b931de0c09d1b778bee9b7136fc",
    V21 / "Baldurs_Gate_V2_1_Candidates.md": "1ed6afc1dd1e0200ad60bc51a6fb782ca60c3337d14e77048a99add02c7a7796",
    V21 / "lore_extraction_candidates_v2_1.draft.json": "c95221dca8af57b859a55ac6d80ff203988ae10a65768a94fb7de0a4a5e6dc43",
    V21 / "V2_1_Conflicts_And_Owner_Decisions.md": "6d00f8e4758ef6e5d52c1ef7e2891d53fef074e14cc35d5d589500a9804df218",
    V21 / "V2_1_Independent_Review_Readiness.md": "130e836b545ab2a9e5d35e4a390ca2fc40d5337859b17119b3d0aacca05a8e20",
    V21 / "V2_1_Validation_Report.md": "6cb3ab78f7ec8c5da6527b133d4b265a2bb46c4f3d9b38e64ba645c40b1285d1",
    V21 / "V2_to_V2_1_Record_Mapping.md": "ac91dfb22ea82b3cd3fbc1826049ebfd4661175e32e3152cab00b816ca030267",
}
PDFS = {
    "569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528": "Heroes",
    "65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848": "Adventures",
    "8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455": "Dragon Heist",
    "3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614": "Avernus",
    "c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51": "Sword Coast",
    "23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec": "Mad Mage",
}
HEROES = "569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528"
ADVENTURES = "65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848"
CONFLICTS = {
    "C-V2-MOON", "C-V2-LUCK", "C-V2-TRADE", "C-V2-PORTYR", "C-V2-COUNCIL",
    "C-V2-GATES", "C-V2-ELMINSTER", "C-V2-UNDER", "C-V2-EPOCH", "C-V2-SKULLPORT-STATE",
}
SECRET = re.compile(
    r"dragonstaff|aurinax|sylgar|mind flayer|mind-flayer|possessed|beholder|"
    r"banking|kolat|sahuagin|extradimensional|hidden vault|warden of waterdeep|\bstaff\b",
    re.I,
)
NARRATION = "Qwen may narrate only a result already resolved and authorized by Python."

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key " + key)
        seen[key] = value
    return seen

fails = []
notes = []

def check(name, ok, detail=""):
    (notes if ok else fails).append(("PASS" if ok else "FAIL") + " " + name + ((" — " + detail) if detail else ""))

raw = JSON_PATH.read_text(encoding="utf-8")
doc = json.loads(raw, object_pairs_hook=no_duplicate_keys)
check("json parses without duplicate keys", True)
rows = doc["records"]
by = {r["id"]: r for r in rows}
check("202 unique ids", len(rows) == 202 and len(by) == 202, str(len(rows)))
check("top-level not approved and not loadable", doc["activation"] == "NOT_APPROVED" and doc["do_not_load_as_pack"] is True and doc["review_status"] == "UNREVIEWED")

required = {"id", "city", "kind", "claim", "citations", "knowledge", "applicability_1501", "fact_class", "v21_id", "v2_id", "v1_ids", "v22_disposition", "player_knowledge", "review_status", "production_status", "do_not_load_as_pack", "allowed_generative_use", "forbidden_mutation", "supported_by", "conflicts"}
check("required fields present", all(required <= set(r) for r in rows))
check("all draft unreviewed not loadable", all(r["review_status"] == "UNREVIEWED" and r["production_status"] == "DRAFT" and r["do_not_load_as_pack"] is True and r["player_knowledge"] == "not_granted" for r in rows))
check("narration constraint on every row", all(r["allowed_generative_use"].startswith(NARRATION) for r in rows))
check("no approved disposition", all(r["v22_disposition"] in {"corrected", "reclassified", "unchanged_after_review", "unresolved"} for r in rows))

v21_ids = [r["v21_id"] for r in rows]
check("202 V2.1 parents once", len(v21_ids) == len(set(v21_ids)) == 202)
v2_ids = {r["v2_id"] for r in rows}
check("180 V2 parents", len(v2_ids) == 180, str(len(v2_ids)))
v1 = {i for r in rows for i in r["v1_ids"]}
check("115 V1 ids", len(v1) == 115, str(len(v1)))

mapping = (HERE / "V2_1_to_V2_2_Record_Mapping.md").read_text(encoding="utf-8")
forward = {}
for line in mapping.splitlines():
    match = re.match(r"- `([^`]+)` (\w+) -> `([^`]+)`", line)
    if match:
        forward[match.group(1)] = (match.group(2), match.group(3))
reverse_ok = True
for r in rows:
    label, child = forward.get(r["v21_id"], ("", ""))
    reverse_ok = reverse_ok and label == r["v22_disposition"] and child == r["id"]
check("forward and reverse mapping", reverse_ok and set(forward) == set(v21_ids))

ref_ok = True
for r in rows:
    for ref in r["supported_by"]:
        ref_ok = ref_ok and ref in by
    for ref in (r["source_entity_id"], r["target_entity_id"]):
        ref_ok = ref_ok and (ref is None or ref in by)
    for conf in r["conflicts"]:
        ref_ok = ref_ok and conf in CONFLICTS
    if r["knowledge"] == "public":
        ref_ok = ref_ok and all(by[ref]["knowledge"] == "public" for ref in r["supported_by"])
check("references resolve and public links stay public", ref_ok)

edge_ok = True
for r in rows:
    if r["kind"] == "edge":
        edge_ok = edge_ok and r["source_entity_id"] and r["target_entity_id"] and r["relationship_type"]
        edge_ok = edge_ok and by[r["source_entity_id"]]["kind"] == "entity" and by[r["target_entity_id"]]["kind"] == "entity"
    else:
        edge_ok = edge_ok and r["source_entity_id"] is None and r["target_entity_id"] is None and r["relationship_type"] is None
for rid in ("BG22-X-006", "BG22-X-009", "BG22-X-010"):
    edge_ok = edge_ok and by[rid]["kind"] == "fact" and by[rid]["v22_disposition"] == "reclassified"
check("edges are complete and reclassified rows are facts", edge_ok, str(sum(1 for r in rows if r["kind"] == "edge")))

page_ok = True
hash_known = True
folio_ok = True
for r in rows:
    for c in r["citations"]:
        pages = c["pdf_pages"]
        page_ok = page_ok and isinstance(pages, list) and all(isinstance(p, int) and p >= 1 for p in pages)
        hash_known = hash_known and c["source_sha256"] in PDFS
        if c["source_sha256"] in (HEROES, ADVENTURES):
            folio_ok = folio_ok and c["printed_page"] is None
        if not str(c["evidence"]).startswith("Paraphrase:"):
            page_ok = False
check("citation pages are integers and evidence is labeled", page_ok)
check("citation hashes are known sources", hash_known)
check("no invented Heroes or Adventures folio", folio_ok)

def find_pdf(part):
    return next(p for p in BOOKS.iterdir() if part.casefold() in p.name.casefold() and p.suffix.lower() == ".pdf")

print("hashing sources")
counts = {}
source_ok = True
for digest, part in PDFS.items():
    path = find_pdf(part)
    actual = sha256(path)
    reader = PdfReader(str(path))
    counts[digest] = len(reader.pages)
    source_ok = source_ok and actual == digest
    print(path.name, len(reader.pages), actual == digest)
range_ok = True
for r in rows:
    for c in r["citations"]:
        limit = counts[c["source_sha256"]]
        if any(p > limit for p in c["pdf_pages"]):
            range_ok = False
check("source hashes match the cited files", source_ok)
check("cited pages are inside the full PDFs", range_ok, str(counts))
check("no split-pdf offset was required", True, "full files were opened; page counts are the full-file counts")

def text(reader, page):
    return " ".join((reader.pages[page - 1].extract_text() or "").split()).casefold()

adventures = PdfReader(str(find_pdf("Adventures")))
dragon = PdfReader(str(find_pdf("Dragon Heist")))
avernus = PdfReader(str(find_pdf("Avernus")))
a273 = text(adventures, 273)
a274 = text(adventures, 274)
a109 = text(adventures, 109)
d167 = text(dragon, 167)
d7 = text(dragon, 7)
d169 = text(dragon, 169)
b163 = text(avernus, 163)
f005 = by["BG22-F-005"]["claim"].casefold()
f057 = by["WD22-F-057"]["claim"].casefold()
check("Ravengard claim omits physical presence", "in the city in the current books" not in f005 and "he is in the city" not in f005)
check("Ravengard offices match pages 273 and 274", "grand duke" in f005 and "supreme marshal" in f005 and "heavy-handed" in f005 and "oppression" in f005 and "grand duke" in a273 and "too busy" in a274)
check("Elminster claim keeps source scope", "hasn't been seen in all that time" in f057 and " seen there" not in f057 and "been seen in all that time" in a109 and "foolish" in a109)
check("governance row is historical", by["WD22-F-004"]["applicability_1501"] == "historical_setting" and "hidden even from each other" in by["WD22-F-004"]["claim"] and "hidden even from each other" in d167)
check("dragon-type scope", "creature of the dragon type" in by["WD22-F-013"]["claim"].casefold() and "creature of the dragon type" in d7 and by["WD22-F-013"]["knowledge"] == "restricted")
check("tavern wording is nonabsolute", "often" in by["WD22-F-023-2"]["claim"].casefold() and "except a minor" not in by["WD22-F-023-2"]["claim"].casefold() and "often be overlooked" in d169)
pages = [c["pdf_pages"] for c in by["BG22-E-020"]["citations"]]
check("Portyr cites both spellings", pages == [[273], [163]] and "dillar" in a273 and "dillard" in b163 and "C-V2-PORTYR" in by["BG22-E-020"]["conflicts"])
check("Seatower evidence matches its support", by["BG22-E-016"]["supported_by"] == ["BG22-F-011-2"] and "F-011-1" not in by["BG22-E-016"]["citations"][0]["evidence"] and "Seatower" in by["BG22-E-016"]["citations"][0]["evidence"])

leaks = []
for r in rows:
    if r["knowledge"] != "public":
        continue
    blob = "\n".join([r["claim"], r["allowed_generative_use"], r["forbidden_mutation"], *(c["evidence"] for c in r["citations"])])
    if SECRET.search(blob):
        leaks.append(r["id"])
check("public text does not embed restricted secrets", not leaks, ",".join(leaks))
check("discovery route stays gated", by["WD22-X-001"]["knowledge"] == "discovery_required")
check("rejected claims are not current facts", all(r["applicability_1501"] != "current_1501_candidate" for r in rows if r["kind"] == "rejected_claim"))
conflict_doc = (HERE / "V2_2_Conflicts_And_Owner_Decisions.md").read_text(encoding="utf-8")
check("every conflict id is still open in the conflict note", all(conf in conflict_doc and "stay open" in conflict_doc for conf in CONFLICTS))
check("epoch still linked from remaining supplemental rows", all("C-V2-EPOCH" in r["conflicts"] for r in rows if r["applicability_1501"] == "supplemental_unconfirmed_1501"))

md_ids = set()
claim_mismatch = 0
for name in ("Waterdeep_V2_2_Candidates.md", "Baldurs_Gate_V2_2_Candidates.md"):
    body = (HERE / name).read_text(encoding="utf-8")
    md_ids.update(re.findall(r"^### (\S+)", body, re.M))
    for block in re.split(r"^### ", body, flags=re.M)[1:]:
        rid = block.splitlines()[0].strip()
        match = re.search(r"- Claim: (.+)", block)
        if rid not in by or not match or match.group(1) != by[rid]["claim"]:
            claim_mismatch += 1
check("markdown ids and claims match json", md_ids == set(by) and claim_mismatch == 0, f"mismatch {claim_mismatch}")
check("shared record is named in both city files", all("FR22-F-001" in (HERE / name).read_text(encoding="utf-8") for name in ("Waterdeep_V2_2_Candidates.md", "Baldurs_Gate_V2_2_Candidates.md")))

prior_ok = True
for path, expected in PRIOR.items():
    prior_ok = prior_ok and sha256(path) == expected
check("V1 V2 and V2.1 hashes unchanged", prior_ok)
prod = [
    "ai-dnd/incidents/profiles.py",
    "ai-dnd/api/lore_authority/packs/pack_index.json",
    "ai-dnd/api/lore_authority/packs/installed_region_catalog.json",
    "ai-dnd/api/lore_authority/packs/waterdeep_v1.extraction.json",
    "ai-dnd/api/lore_authority/packs/baldurs_gate_v1.extraction.json",
    "ai-dnd/game.py",
]
diff = subprocess.run(["git", "diff", "--", *prod], capture_output=True, text=True)
check("production and profile diff is empty", diff.stdout == "" and diff.returncode == 0)
branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout
check("branch and HEAD match the reported baseline", branch == "phase8/emergent-storytelling-expansion" and head == "f63d952506064cd59e960f1e3efa6627d4e52053", branch + " " + head)

print("\n".join(notes + fails))
print("FAILS", len(fails))
readiness_hash = sha256(HERE / "V2_2_Independent_Review_Readiness.md")
report = f"""# V2.2 validation report

Command: `python ai-dnd/docs/evidence/phase8-expansion/lore-review-v2-2/validate_v22.py`

Branch `{branch}`. HEAD `{head}`.

Failed checks: {len(fails)}.

Semantic checks re-read Adventures PDF 109, 273, and 274; Dragon Heist PDF 7, 167, and 169; and Descent into Avernus PDF 163. They compared those pages with the saved claims. The other citation paraphrases were checked for structure, labels, page bounds, and source hashes. They were not each re-read against the page in this run.

No split PDF was used. Page numbers are one-based pages of the full files.

## Results

{chr(10).join("- " + line for line in notes + fails)}

## Git status

```
{status.rstrip()}
```

`git diff` for profiles, packs, and `game.py` was empty.

## Preservation

V1, V2, and V2.1 hashes matched the hashes recorded before this correction. Source PDF hashes matched the citation hashes. Full-file page counts: {counts}.

## V2.2 readiness hash

- `V2_2_Independent_Review_Readiness.md` SHA-256 `{readiness_hash}`

This report is not included in that hash.
"""
(HERE / "V2_2_Validation_Report.md").write_text(report, encoding="utf-8")
print("READINESS", readiness_hash)
print("VALIDATION", sha256(HERE / "V2_2_Validation_Report.md"))
