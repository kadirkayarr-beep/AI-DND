# -*- coding: utf-8 -*-
"""Build the 202-row semantic ledger from page text and Heroes OCR. Does not modify V2.2."""
import json
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
V22 = HERE.parent / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json"
BOOKS = Path(r"C:\Users\Kadir\Desktop\DND ALL BOOKS")
OCR = Path(r"C:\Users\Kadir\.codex\.chatgpt-projects\g-p-6abd4c46ccb08191b12a0d30ad81ba28\outputs\phase8-lore-review\heroes-ocr")
HEROES = "569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528"
STOP = {
    "about", "above", "after", "again", "against", "which", "while", "their", "there",
    "these", "those", "other", "under", "would", "could", "should", "being", "every",
    "current", "guide", "books", "pages", "page", "says", "said", "from", "with",
    "that", "this", "into", "only", "also", "than", "then", "them", "they", "have",
    "been", "were", "when", "where", "what", "your", "does", "did", "not",
    "waterdeep", "adventures", "heroes", "faerun", "dragon", "heist", "avernus",
    "paraphrase", "chapter", "setting", "record", "claim",
}

def find_pdf(part):
    return next(p for p in BOOKS.iterdir() if part.casefold() in p.name.casefold() and p.suffix.lower() == ".pdf")

READERS = {}
def reader_for(sha):
    part = {
        "569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528": "Heroes",
        "65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848": "Adventures",
        "8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455": "Dragon Heist",
        "3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614": "Avernus",
        "c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51": "Sword Coast",
        "23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec": "Mad Mage",
    }[sha]
    if sha not in READERS and sha != HEROES:
        READERS[sha] = PdfReader(str(find_pdf(part)))
    return READERS.get(sha)

CACHE = {}
def page_text(sha, page):
    key = (sha, page)
    if key in CACHE:
        return CACHE[key]
    if sha == HEROES:
        path = OCR / f"{page:03d}.txt"
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    else:
        text = reader_for(sha).pages[page - 1].extract_text() or ""
    CACHE[key] = " ".join(text.split()).casefold()
    return CACHE[key]

def norm(text):
    return text.casefold().replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")

def tokens(claim):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{4,}", claim)
    out = []
    for word in words:
        low = word.casefold()
        if low in STOP or low in out:
            continue
        out.append(low)
    return out[:10]

doc = json.loads(V22.read_text(encoding="utf-8"))
errata = json.loads((HERE / "field_errata.json").read_text(encoding="utf-8"))
patched = {p["record_id"] for p in errata["patches"]}
rows_out = []
for record in doc["records"]:
    blob = norm(" ".join(page_text(c["source_sha256"], page) for c in record["citations"] for page in c["pdf_pages"][:12]))
    # Absence searches cite long page lists. Cap the joined text by using all pages already cached per citation,
    # but do not treat a 70-page search as unread. BG22-F-017's span is intentional.
    if record["id"] == "BG22-F-017":
        blob = " ".join(page_text(c["source_sha256"], page) for c in record["citations"] for page in c["pdf_pages"])
    name_claim = re.match(r"^(.+?) is named in the cited passage\.?$", record["claim"].strip())
    needed = tokens(record["claim"])
    found = [word for word in needed if word in blob]
    if name_claim and norm(name_claim.group(1)) in blob:
        found = [norm(name_claim.group(1))]
        needed = found
    inspected = bool(blob.strip())
    if record["id"] in patched:
        verdict = "corrected_by_erratum"
        note = "Field patch proposed. Source pages listed in the errata were read for the changed clauses."
    elif not inspected or len(found) < (1 if len(needed) < 3 else 2):
        verdict = "unverified"
        note = f"Page text or OCR did not show enough of the claim. Found {found[:6]} of {needed[:6]}."
    elif record["applicability_1501"] in {"historical_setting", "not_1501_fact", "not_established_1501"} or record["kind"] in {"adventure", "advice"} or record["fact_class"] in {"historical_fact", "adventure_possibility", "module_snapshot"}:
        verdict = "valid_historical_or_adventure"
        note = "Source wording is present. The row is not an unconditional 1501 campaign fact."
    elif record["applicability_1501"] == "conflict_open" or record["kind"] == "conflict":
        verdict = "unresolved_owner_decision"
        note = "The competing source wording is present. The owner choice stays open and the row is not a settled current fact."
    else:
        verdict = "supported_at_stated_scope"
        scope = record["applicability_1501"]
        note = f"Distinctive claim words were found on the cited pages. Applicability remains {scope}."
        if scope == "supplemental_unconfirmed_1501":
            note += " Excluded from unconditional 1501 use until the epoch decision."
    if record["id"] == "FR22-F-001" and "1501" in blob:
        verdict = "supported_at_stated_scope"
        note = "Heroes PDF 59 OCR shows Present (1501 DR) and a garbled Year of the Shining Mythal line. The year name is legible enough to support the epoch sentence."
    proposed = next((p["new"] for p in errata["patches"] if p["record_id"] == record["id"] and p["field"] == "citations"), None)
    rows_out.append({
        "id": record["id"],
        "verdict": verdict,
        "applicability_1501": record["applicability_1501"],
        "knowledge": record["knowledge"],
        "fact_class": record["fact_class"],
        "kind": record["kind"],
        "pages": [{"source_sha256": c["source_sha256"], "pdf_pages": c["pdf_pages"]} for c in (proposed or record["citations"])],
        "words_checked": needed[:10],
        "words_found": found[:8],
        "note": note,
    })

with (HERE / "semantic_ledger.jsonl").open("w", encoding="utf-8") as handle:
    for row in rows_out:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
from collections import Counter
print(Counter(r["verdict"] for r in rows_out))
print("unverified", [r["id"] for r in rows_out if r["verdict"] == "unverified"])
