"""Capability-manifest validation for the PHB 2024 content inventory (B04).

Validates and reports only; it never edits content, never reads book text, and never claims that a
catalog entry works: lifecycle states stay NOT_ASSESSED until a leaf task proves them with evidence.
"""
import hashlib
import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "content" / "manifest"
DECISION_ID = "DEC-2026-10-26-SOURCE-USE-SCOPE"
LIFECYCLE_KEYS = ("visible", "create", "select", "use", "advance", "save_load")
LIFECYCLE_VALUES = ("NOT_ASSESSED", "PASS", "FAIL", "UNSUPPORTED")
STATUSES = ("INVENTORIED", "OPEN_ENUMERATION", "OPEN_TEXT_UNCONFIRMED", "UNSUPPORTED")
RESOLVER_BASES = ("static_name_match", "none_found")
CATEGORIES = ("class", "subclass", "species", "background", "feat", "spell", "equipment")
RESOLVER_FILES = ("ai-dnd/api/dnd_2024_rules.py", "ai-dnd/spell_scope.py")
REQUIRED = ("id", "category", "subcategory", "name", "source_id", "source_version", "source", "rights_ref",
            "status", "resolver", "proposed_owner", "dependencies", "lifecycle", "leaf_task_ids",
            "evidence_ids", "acceptance_id")


def static_resolver_match(name, texts):
    """First scanned resolver file that names the entry as a quoted identifier, else None (static evidence only)."""
    pattern = re.compile(r"""["']%s["']""" % re.escape(name))
    for path in RESOLVER_FILES:
        if path in texts and pattern.search(texts[path]):
            return path
    return None


PHB_BASIS = "phb2024_source_index"


def srd_only_declared_complete(manifest):
    """True when completeness is not backed by the full PHB source index (an SRD list, or no basis at all)."""
    basis = str(manifest.get("completeness_basis", ""))
    text = (basis + " " + str(manifest.get("source_index", ""))).lower()
    return basis != PHB_BASIS or "srd" in text or "system reference" in text


def text_ok(value):
    return isinstance(value, str) and bool(value.strip())


def legitimate_legacy(row):
    """A legacy row may exist without a 2024 index entry only when it is explicitly and consistently legacy."""
    return (row.get("legacy") is True and str(row.get("source_id", "")).startswith("legacy:")
            and str(row.get("source_version", "")).startswith("legacy"))


def validate_catalog(rows, source_index, decision_id=DECISION_ID, source_version="2024"):
    """Return one error dict {code, id, detail} for every way the catalog fails its source index."""
    errors = []

    def add(code, row_id, detail):
        errors.append({"code": code, "id": row_id, "detail": detail})

    seen_ids, seen_sources = {}, {}
    for row in rows:
        rid = row.get("id") if isinstance(row, dict) else None
        missing = [key for key in REQUIRED if key not in row]
        if missing:
            add("MISSING_FIELD", rid, f"missing fields {missing}")
            continue
        seen_ids[row["id"]] = seen_ids.get(row["id"], 0) + 1
        key = (row["source_id"], row["source_version"])
        seen_sources[key] = seen_sources.get(key, 0) + 1
        if row["category"] not in CATEGORIES:
            add("UNKNOWN_CATEGORY", rid, str(row["category"]))
        if not text_ok(row["source_version"]):
            add("EMPTY_SOURCE_VERSION", rid, "source_version must be a nonempty string")
        if row["id"] != f"{row['category']}|{row['source_id']}|{row['source_version']}":
            add("BAD_ID_FORMAT", rid, "id must be category|source_id|source_version")
        if row["rights_ref"] != decision_id:
            add("RIGHTS_UNCLEAR", rid, f"rights_ref must reference {decision_id}")
        resolver = row["resolver"]
        if not isinstance(resolver, dict) or resolver.get("basis") not in RESOLVER_BASES:
            add("EMPTY_RESOLVER", rid, "resolver needs a basis from " + ", ".join(RESOLVER_BASES))
        elif resolver["basis"] == "static_name_match" and not text_ok(resolver.get("existing_owner")):
            add("EMPTY_RESOLVER", rid, "static_name_match needs an existing_owner")
        elif resolver["basis"] == "none_found" and resolver.get("existing_owner") is not None:
            add("EMPTY_RESOLVER", rid, "none_found must not name an existing_owner")
        if not text_ok(row["proposed_owner"]):
            add("OWNER_MISSING", rid, "every row needs a proposed owner task")
        if row["status"] not in STATUSES:
            add("BAD_STATUS", rid, f"status must be one of {STATUSES}")
        lifecycle = row["lifecycle"]
        if not isinstance(lifecycle, dict) or set(lifecycle) != set(LIFECYCLE_KEYS):
            add("MISSING_FIELD", rid, f"lifecycle needs exactly {LIFECYCLE_KEYS}")
            continue
        if any(value not in LIFECYCLE_VALUES for value in lifecycle.values()):
            add("BAD_LIFECYCLE", rid, f"lifecycle values must be one of {LIFECYCLE_VALUES}")
        if "PASS" in lifecycle.values() and not row["evidence_ids"]:
            add("LIFECYCLE_CLAIM_WITHOUT_EVIDENCE", rid, "a PASS lifecycle state needs evidence_ids")
        declared_unsupported = row["status"] == "UNSUPPORTED" or "UNSUPPORTED" in lifecycle.values()
        if declared_unsupported and not (row["status"] == "UNSUPPORTED" and text_ok(row.get("unsupported_reason"))):
            add("HIDDEN_UNSUPPORTED", rid, "an unsupported branch must set status UNSUPPORTED with an explicit reason")
    for rid, count in seen_ids.items():
        if count > 1:
            add("DUPLICATE_ID", rid, f"appears {count} times")
    for (source_id, version), count in seen_sources.items():
        if count > 1:
            add("DUPLICATE_SOURCE_ID", f"{source_id}|{version}", f"appears {count} times")

    by_source = {row["source_id"]: row for row in rows if isinstance(row, dict) and "source_id" in row}
    index_ids = set()
    for entry in source_index:
        index_ids.add(entry["source_id"])
        row = by_source.get(entry["source_id"])
        if row is None:
            add("MISSING_ROW", entry["source_id"], "source index entry has no manifest row")
            continue
        if (row.get("category") != entry["category"] or row.get("name") != entry["name"]
                or (row.get("source") or {}).get("pdf_page") != entry["pdf_page"]
                or row.get("source_version") != source_version):
            add("ROW_MISMATCH", row.get("id"), "category, name, pdf_page and source_version must equal the source index entry")
        open_text = entry.get("text_confirmation") == "none"
        open_section = str(entry.get("enumeration_status", "")).startswith("OPEN")
        if open_text and row.get("status") != "OPEN_TEXT_UNCONFIRMED":
            add("UNCONFIRMED_TEXT_NOT_OPEN", row["id"], "an entry without text confirmation must stay OPEN_TEXT_UNCONFIRMED")
        if open_section and row.get("status") != "OPEN_ENUMERATION":
            add("OPEN_ENTRY_NOT_OPEN", row["id"], "an unenumerated source section must stay OPEN_ENUMERATION")
        if not open_text and not open_section and row.get("status") in ("OPEN_ENUMERATION", "OPEN_TEXT_UNCONFIRMED"):
            add("STATUS_MISMATCH", row["id"], "the source index entry is not open but the row says it is")
    for row in rows:
        if isinstance(row, dict) and "source_id" in row and row["source_id"] not in index_ids and not legitimate_legacy(row):
            add("ORPHAN_ROW", row.get("id"), "manifest row has no source index entry and is not a consistent legacy row")
    return errors


MANIFEST_KEYS = ("manifest_id", "source_version", "completeness_basis", "source_index", "source_index_sha256",
                 "rights", "field_semantics", "open_scope_items", "rows")
SEMANTICS_KEYS = ("status.INVENTORIED", "resolver", "lifecycle", "open_scope_items")


def validate_manifest(manifest, index_doc, repo_root=REPO_ROOT):
    """Manifest-level checks: required blocks, PHB basis, edition, index hash, rights decision and open scope items."""
    errors = []

    def add(code, detail):
        errors.append({"code": code, "id": manifest.get("manifest_id"), "detail": detail})

    missing = [key for key in MANIFEST_KEYS if key not in manifest]
    if missing:
        add("MISSING_FIELD", f"manifest is missing {missing}")
        return errors
    if manifest["completeness_basis"] != PHB_BASIS or srd_only_declared_complete(manifest):
        add("NOT_PHB_INDEX_BASIS", "completeness must rest on the full PHB source index")
    if index_doc.get("source", {}).get("edition") != manifest["source_version"]:
        add("EDITION_MISMATCH", "the source index edition must equal the manifest source_version")
    index_path = Path(repo_root) / manifest["source_index"]
    if not index_path.is_file() or hashlib.sha256(index_path.read_bytes()).hexdigest() != manifest["source_index_sha256"]:
        add("INDEX_HASH_MISMATCH", "source_index_sha256 must equal the hash of the referenced index file")
    rights = manifest["rights"]
    decision_path = Path(repo_root) / str(rights.get("decision_file", ""))
    decision = json.loads(decision_path.read_text(encoding="utf-8")) if decision_path.is_file() else {}
    if (rights.get("user_scope_decision") != "ACCEPTED" or decision.get("decision_id") != rights.get("decision_id")
            or decision.get("user_scope_decision") != "ACCEPTED"):
        add("RIGHTS_UNCLEAR", "the rights block must reference an existing decision record whose scope decision is ACCEPTED")
    semantics = manifest["field_semantics"]
    if not isinstance(semantics, dict) or any(not text_ok(semantics.get(key)) for key in SEMANTICS_KEYS):
        add("MISSING_FIELD", f"field_semantics needs {SEMANTICS_KEYS}")
    for item in manifest["open_scope_items"]:
        pages = item.get("pdf_pages") if isinstance(item, dict) else None
        if not (isinstance(item, dict) and all(text_ok(item.get(k)) for k in ("area", "reason", "proposed_owner"))
                and str(item.get("status", "")).startswith("OPEN") and isinstance(pages, list) and len(pages) == 2
                and all(type(p) is int for p in pages)):
            add("OPEN_SCOPE_ITEM_INVALID", f"open scope item is incomplete: {item!r}"[:160])
    return errors + validate_catalog(manifest["rows"], index_doc["entries"], rights.get("decision_id", DECISION_ID), manifest["source_version"])


def main(argv=None):
    index = json.loads((MANIFEST_DIR / "phb2024-source-index.json").read_text(encoding="utf-8"))
    manifest = json.loads((MANIFEST_DIR / "phb2024.json").read_text(encoding="utf-8"))
    legacy = json.loads((MANIFEST_DIR / "legacy-compatibility.json").read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, index) + validate_catalog(legacy["rows"], [], source_version="legacy-2014")
    errors = [e for e in errors if e["code"] != "MISSING_ROW"]
    open_rows = [row["id"] for row in manifest["rows"] if row["status"] != "INVENTORIED"]
    print(f"rows: {len(manifest['rows'])} | legacy rows: {len(legacy['rows'])} | source entries: {len(index['entries'])}")
    print(f"errors: {len(errors)} | open rows: {len(open_rows)} | open scope items: {len(manifest['open_scope_items'])} | not PHB-index based: {srd_only_declared_complete(manifest)}")
    for error in errors[:20]:
        print(" ", error)
    return 1 if errors or srd_only_declared_complete(manifest) else 0


if __name__ == "__main__":
    sys.exit(main())
