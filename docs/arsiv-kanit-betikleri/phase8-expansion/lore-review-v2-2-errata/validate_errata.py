# -*- coding: utf-8 -*-
"""Validate the V2.2 errata in memory. Does not modify inputs, call Git, or write a report unless --output is inside this directory."""
import argparse
import copy
import hashlib
import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
DEFAULT_BOOKS = Path(r"C:\Users\Kadir\Desktop\DND ALL BOOKS")
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
REQUIRED_SUPPORT = {
    "WD22-X-004": ["WD22-F-007"],
    "WD22-X-005": ["WD22-F-018"],
    "WD22-X-008": ["WD22-F-048"],
    "WD22-X-009": ["WD22-F-054", "WD22-F-005"],
}
CONFLICTS = {
    "C-V2-MOON", "C-V2-LUCK", "C-V2-TRADE", "C-V2-PORTYR", "C-V2-COUNCIL",
    "C-V2-GATES", "C-V2-ELMINSTER", "C-V2-UNDER", "C-V2-EPOCH", "C-V2-SKULLPORT-STATE",
}
VERDICTS = {
    "supported_at_stated_scope", "corrected_by_erratum", "valid_historical_or_adventure",
    "unresolved_owner_decision", "unverified",
}
NARRATION = "Qwen may narrate only a result already resolved and authorized by Python."
SECRET = re.compile(
    r"dragonstaff|aurinax|sylgar|mind flayer|mind-flayer|possessed|beholder|"
    r"banking|kolat|sahuagin|extradimensional|hidden vault|warden of waterdeep|\bstaff\b",
    re.I,
)

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

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)

def ids_of(doc):
    return {r["id"] for r in doc["records"]}

def apply_patches(records, patches):
    by = {r["id"]: copy.deepcopy(r) for r in records}
    errors = []
    if len(by) != len(records):
        errors.append("duplicate record id in base")
    for patch in patches:
        row = by.get(patch["record_id"])
        if row is None:
            errors.append("patch record missing " + patch["record_id"])
            continue
        if row.get(patch["field"]) != patch["old"]:
            errors.append(f"old value mismatch {patch['record_id']} {patch['field']}")
            continue
        row[patch["field"]] = copy.deepcopy(patch["new"])
    return list(by.values()), errors

def nonpublic_supports(by, rid, seen=None):
    seen = set() if seen is None else seen
    if rid in seen:
        return []
    seen.add(rid)
    row = by[rid]
    bad = []
    if row["knowledge"] != "public":
        bad.append(rid)
    for ref in row["supported_by"]:
        bad.extend(nonpublic_supports(by, ref, seen))
    return bad

def view_errors(rows, exceptions, counts, ancestors, allowed):
    errors = []
    by = {}
    for row in rows:
        if row["id"] in by:
            errors.append("duplicate id " + row["id"])
        by[row["id"]] = row
    if ancestors["base_ids"] != set(by):
        missing = sorted(ancestors["base_ids"] - set(by))
        extra = sorted(set(by) - ancestors["base_ids"])
        errors.append(f"id set changed missing={missing[:5]} extra={extra[:5]}")
    exception_ids = {item["record_id"] for item in exceptions}
    for row in rows:
        for field in ("id", "city", "kind", "claim", "citations", "knowledge", "applicability_1501", "fact_class", "player_knowledge", "review_status", "production_status", "do_not_load_as_pack", "allowed_generative_use", "forbidden_mutation", "supported_by"):
            if field not in row:
                errors.append(f"missing {field} on {row['id']}")
        if row["kind"] not in allowed["kind"]:
            errors.append(f"bad kind {row['id']}")
        if row["knowledge"] not in allowed["knowledge"]:
            errors.append(f"bad knowledge {row['id']}")
        if row["applicability_1501"] not in allowed["applicability_1501"]:
            errors.append(f"bad applicability {row['id']}")
        if row["review_status"] != "UNREVIEWED" or row["production_status"] != "DRAFT" or row["do_not_load_as_pack"] is not True or row["player_knowledge"] != "not_granted":
            errors.append(f"status or knowledge changed {row['id']}")
        if not str(row["allowed_generative_use"]).startswith(NARRATION):
            errors.append(f"narration constraint missing {row['id']}")
        if not row["citations"] or not isinstance(row["citations"], list):
            errors.append(f"empty citations {row['id']}")
        for cite in row["citations"]:
            pages = cite.get("pdf_pages")
            if not isinstance(pages, list) or not pages or not all(isinstance(p, int) and p >= 1 for p in pages):
                errors.append(f"bad pages {row['id']}")
                continue
            digest = cite.get("source_sha256")
            if digest not in counts:
                errors.append(f"unknown source {row['id']}")
            elif any(p > counts[digest] for p in pages):
                errors.append(f"page out of range {row['id']}")
            if cite.get("source_title") is None or not str(cite.get("evidence", "")).startswith("Paraphrase:"):
                errors.append(f"citation evidence {row['id']}")
            if digest in (HEROES, ADVENTURES) and cite.get("printed_page") is not None:
                errors.append(f"invented folio {row['id']}")
        for ref in row["supported_by"]:
            if ref not in by:
                errors.append(f"missing support {row['id']} -> {ref}")
        if row["v21_id"] not in ancestors["v21"]:
            errors.append(f"missing v21 ancestor {row['id']} {row['v21_id']}")
        if row["v2_id"] not in ancestors["v2"]:
            errors.append(f"missing v2 ancestor {row['id']} {row['v2_id']}")
        for vid in row["v1_ids"]:
            if vid not in ancestors["v1"]:
                errors.append(f"missing v1 ancestor {row['id']} {vid}")
        if row["kind"] == "edge":
            for end in (row["source_entity_id"], row["target_entity_id"]):
                if end not in by or by[end]["kind"] != "entity":
                    errors.append(f"broken endpoint {row['id']} {end}")
            if not row["relationship_type"]:
                errors.append(f"missing relationship {row['id']}")
            if row["id"] in REQUIRED_SUPPORT and row["supported_by"] != REQUIRED_SUPPORT[row["id"]]:
                errors.append(f"required support {row['id']}")
            elif row["id"] in exception_ids:
                if row["supported_by"]:
                    errors.append(f"exception should stay direct {row['id']}")
                item = next(x for x in exceptions if x["record_id"] == row["id"])
                if not item.get("source_evidence") or not item.get("reason"):
                    errors.append(f"exception missing evidence {row['id']}")
            elif not row["supported_by"]:
                errors.append(f"missing required support {row['id']}")
        else:
            if row["source_entity_id"] is not None or row["target_entity_id"] is not None:
                errors.append(f"non-edge has endpoints {row['id']}")
        if row["knowledge"] == "public":
            for ref in row["supported_by"]:
                if ref in by and nonpublic_supports(by, ref):
                    errors.append(f"public depends on nonpublic {row['id']} -> {ref}")
            if row["kind"] == "edge":
                for end in (row["source_entity_id"], row["target_entity_id"]):
                    if end in by and by[end]["knowledge"] != "public":
                        errors.append(f"public edge to restricted entity {row['id']} -> {end}")
                    elif end in by:
                        for ref in by[end]["supported_by"]:
                            if nonpublic_supports(by, ref):
                                errors.append(f"transitive restricted dependency {row['id']} -> {end} -> {ref}")
        if row["knowledge"] == "public":
            blob = "\n".join([row["claim"], row["forbidden_mutation"], *(c["evidence"] for c in row["citations"])])
            if SECRET.search(blob):
                errors.append(f"public keyword screen {row['id']}")
        for conf in row["conflicts"]:
            if conf not in CONFLICTS:
                errors.append(f"unknown conflict {row['id']} {conf}")
    for rid in ("BG22-X-006", "BG22-X-009", "BG22-X-010"):
        if rid in by and by[rid]["kind"] != "fact":
            errors.append(f"reclassified row is not a fact {rid}")
    if "WD22-X-001" in by and by["WD22-X-001"]["knowledge"] != "discovery_required":
        errors.append("discovery route was opened")
    return errors

def negative_tests(rows, patches, exceptions, counts, ancestors, allowed):
    results = []
    def expect(name, mutated_rows=None, mutated_patches=None, mutated_exceptions=None):
        use_rows = mutated_rows if mutated_rows is not None else rows
        use_patches = mutated_patches if mutated_patches is not None else patches
        use_ex = mutated_exceptions if mutated_exceptions is not None else exceptions
        view, apply_errs = apply_patches(use_rows, use_patches)
        found = apply_errs + ([] if apply_errs else view_errors(view, use_ex, counts, ancestors, allowed))
        results.append((name, bool(found), found[:2]))

    dup = copy.deepcopy(rows)
    dup.append(copy.deepcopy(dup[0]))
    expect("duplicate id", mutated_rows=dup)

    missing = copy.deepcopy(rows)
    missing[0]["v21_id"] = "NO-SUCH-ANCESTOR"
    expect("missing ancestor", mutated_rows=missing)

    bad_patch = copy.deepcopy(patches)
    bad_patch[0]["old"] = "this is not the stored value"
    expect("wrong patch old value", mutated_patches=bad_patch)

    empty_c = copy.deepcopy(rows)
    empty_c[0]["citations"] = []
    expect("empty citation", mutated_rows=empty_c)

    empty_p = copy.deepcopy(rows)
    empty_p[0]["citations"][0]["pdf_pages"] = []
    expect("empty pages", mutated_rows=empty_p)

    broken = copy.deepcopy(rows)
    edge = next(r for r in broken if r["kind"] == "edge")
    edge["target_entity_id"] = "NO-SUCH-ENTITY"
    expect("broken endpoint", mutated_rows=broken)

    nosupport = copy.deepcopy(rows)
    held = next(r for r in nosupport if r["id"] == "WD22-X-004")
    held["supported_by"] = []
    # The real patch would refill it. Remove that patch so the hole remains.
    kept = [p for p in patches if not (p["record_id"] == "WD22-X-004" and p["field"] == "supported_by")]
    expect("missing required support", mutated_rows=nosupport, mutated_patches=kept)

    public_edge = copy.deepcopy(rows)
    edge = next(r for r in public_edge if r["id"] == "WD22-X-004")
    target = next(r for r in public_edge if r["id"] == edge["target_entity_id"])
    target["knowledge"] = "restricted"
    expect("public edge to restricted entity", mutated_rows=public_edge)

    transitive = copy.deepcopy(rows)
    public_fact = next(r for r in transitive if r["knowledge"] == "public" and r["kind"] == "fact" and not r["supported_by"])
    restricted = next(r for r in transitive if r["knowledge"] == "restricted")
    public_fact["supported_by"] = [restricted["id"]]
    expect("transitive restricted dependency", mutated_rows=transitive)

    oor = copy.deepcopy(rows)
    oor[0]["citations"][0]["pdf_pages"] = [99999]
    expect("page out of range", mutated_rows=oor)

    deleted = copy.deepcopy(rows)
    deleted.pop()
    expect("unexpected record deletion", mutated_rows=deleted)

    status = copy.deepcopy(rows)
    status[0]["review_status"] = "APPROVED"
    expect("invalid status", mutated_rows=status)

    granted = copy.deepcopy(rows)
    granted[0]["player_knowledge"] = "granted"
    expect("granted player knowledge", mutated_rows=granted)
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v22-json", type=Path)
    parser.add_argument("--books", type=Path, default=DEFAULT_BOOKS)
    parser.add_argument("--errata-dir", type=Path, default=HERE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    errata_dir = args.errata_dir.resolve()
    v22_json = (args.v22_json or (errata_dir.parent / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json")).resolve()
    if args.output:
        out = args.output.resolve()
        if errata_dir not in out.parents and out.parent != errata_dir:
            print("output must stay inside the errata directory")
            return 2
    errata = load(errata_dir / "field_errata.json")
    manifest = load(errata_dir / "input_manifest.json")
    base = load(v22_json)
    errors = []
    if sha256(v22_json) != errata["base_sha256"]:
        errors.append("base hash mismatch")
    for patch in errata["patches"]:
        if patch.get("base_sha256") != errata["base_sha256"] or "old" not in patch or "new" not in patch or not patch.get("source_evidence"):
            errors.append(f"patch missing exact old, new, evidence, or base hash {patch.get('record_id')}")
    root = HERE.parents[4]
    for item in manifest["files"]:
        path = root / item["path"]
        if not path.exists() or sha256(path) != item["sha256"]:
            errors.append("preservation mismatch " + item["path"])
    view, apply_errors = apply_patches(base["records"], errata["patches"])
    errors.extend(apply_errors)
    counts = {}
    for digest, part in PDFS.items():
        path = next(p for p in args.books.iterdir() if part.casefold() in p.name.casefold() and p.suffix.lower() == ".pdf")
        actual = sha256(path)
        if actual != digest:
            errors.append("source hash mismatch " + path.name)
        counts[digest] = len(PdfReader(str(path)).pages)
    expansion = v22_json.parents[1]
    ancestors = {
        "base_ids": ids_of(base),
        "v21": ids_of(load(expansion / "lore-review-v2-1" / "lore_extraction_candidates_v2_1.draft.json")),
        "v2": ids_of(load(expansion / "lore-review-v2" / "lore_extraction_candidates_v2.draft.json")),
        "v1": ids_of(load(expansion / "lore-review" / "lore_extraction_candidates.draft.json")),
    }
    allowed = {
        "kind": {r["kind"] for r in base["records"]},
        "knowledge": {r["knowledge"] for r in base["records"]},
        "applicability_1501": {r["applicability_1501"] for r in base["records"]},
    }
    if not apply_errors:
        errors.extend(view_errors(view, errata["direct_source_exceptions"], counts, ancestors, allowed))
    v22 = v22_json.parent
    mapping = (v22 / "V2_1_to_V2_2_Record_Mapping.md").read_text(encoding="utf-8")
    forward = {}
    for line in mapping.splitlines():
        match = re.match(r"- `([^`]+)` (\w+) -> `([^`]+)`", line)
        if match:
            forward[match.group(1)] = (match.group(2), match.group(3))
    by_orig = {r["id"]: r for r in base["records"]}
    for row in base["records"]:
        label, child = forward.get(row["v21_id"], ("", ""))
        if label != row["v22_disposition"] or child != row["id"]:
            errors.append("lineage mismatch " + row["id"])
    if set(forward) != {r["v21_id"] for r in base["records"]}:
        errors.append("mapping coverage mismatch")
    claim_mismatch = 0
    md_ids = set()
    for name in ("Waterdeep_V2_2_Candidates.md", "Baldurs_Gate_V2_2_Candidates.md"):
        body = (v22 / name).read_text(encoding="utf-8")
        md_ids.update(re.findall(r"^### (\S+)", body, re.M))
        for block in re.split(r"^### ", body, flags=re.M)[1:]:
            rid = block.splitlines()[0].strip()
            match = re.search(r"- Claim: (.+)", block)
            if rid not in by_orig or not match or match.group(1) != by_orig[rid]["claim"]:
                claim_mismatch += 1
    if md_ids != set(by_orig) or claim_mismatch:
        errors.append(f"markdown claim mismatch {claim_mismatch}")
    ledger_ids = []
    unverified = []
    for line in (errata_dir / "semantic_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        ledger_ids.append(item["id"])
        if item["verdict"] not in VERDICTS:
            errors.append("bad verdict " + item["id"])
        if item["verdict"] == "unverified":
            unverified.append(item["id"])
    if ledger_ids != [r["id"] for r in base["records"]]:
        errors.append(f"ledger coverage {len(ledger_ids)}")
    if unverified:
        errors.append("unverified ledger rows " + ",".join(unverified))
    tests = negative_tests(base["records"], errata["patches"], errata["direct_source_exceptions"], counts, ancestors, allowed)
    missed = [name for name, found, _ in tests if not found]
    if missed:
        errors.append("negative tests missed " + ",".join(missed))
    lines = [f"base {errata['base_sha256']}", f"records {len(view)}", f"patches {len(errata['patches'])}", f"page_counts {counts}"]
    lines.append("keyword screen is not a proof of secret absence or of natural-language correctness")
    for name, found, sample in tests:
        lines.append(("PASS " if found else "FAIL ") + "negative " + name + " " + str(sample))
    lines.append("FAILS " + str(len(errors)))
    for err in errors:
        lines.append("FAIL " + err)
    if not errors:
        lines.append("PASS in-memory corrected view")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
