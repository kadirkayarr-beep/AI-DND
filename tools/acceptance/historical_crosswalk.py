"""Historical crosswalk (B05): maps LR/G records and research opportunities to the new roadmap tasks.

Never lets a historical pass close the full release and never invents a source title: a record without
a source stays UNKNOWN.
"""
import copy
import re


KINDS = ("lr", "g", "opportunity")
TASK_REF = re.compile(r"([A-Z])(\d{2})(?:\s*[–-]\s*([A-Z])?(\d{2}))?")


def expand_task_refs(spec):
    """'B01–B03,D03' -> ['B01', 'B02', 'B03', 'D03']; an unreadable or reversed range is an error."""
    refs = []
    for part in re.split(r"\s*,\s*", str(spec).strip()):
        match = TASK_REF.fullmatch(part)
        if not match:
            raise ValueError(f"Unreadable task reference: {part!r}")
        prefix, start, prefix_end, end = match.groups()
        if end is None:
            refs.append(f"{prefix}{start}")
            continue
        if prefix_end and prefix_end != prefix:
            raise ValueError(f"A range must stay inside one task family: {part!r}")
        if int(end) < int(start):
            raise ValueError(f"Reversed range: {part!r}")
        refs.extend(f"{prefix}{number:02d}" for number in range(int(start), int(end) + 1))
    return refs


def crosswalk_history(entries, task_index):
    """One row per historical entry; every row says it is not the full release."""
    known = {task["id"] for task in task_index}
    rows = []
    for entry in entries:
        historical_id = entry.get("historical_id")
        if entry.get("closes_full_release") is True:
            raise ValueError(f"{historical_id}: a historical record cannot close the full release")
        if entry.get("kind") not in KINDS:
            raise ValueError(f"{historical_id}: kind must be one of {KINDS}")
        if entry.get("is_scope_decision") is True:
            raise ValueError(f"{historical_id}: a research opportunity is not a scope decision")
        targets = expand_task_refs(entry["target_spec"])
        missing = [task for task in targets if task not in known]
        source_ref = entry.get("source_ref")
        if source_ref is None:
            status, title, verification = "UNKNOWN", None, "NO_SOURCE"
        else:
            title = entry.get("source_title")
            verification = entry.get("source_verification", "PLAN_PACKAGE_RECORD_ONLY")
            status = "MAPPED" if verification == "REPO_HEADING_VERIFIED" else "MAPPED_UNVERIFIED_SOURCE"
        if missing:
            status = "UNKNOWN_TARGET"
        row = {
            "historical_id": historical_id, "kind": entry["kind"], "source_ref": copy.deepcopy(source_ref),
            "source_title": title, "package_title": entry.get("package_title"),
            "target_spec": entry["target_spec"], "target_tasks": targets, "missing_targets": missing,
            "status": status, "not_full_release": True, "source_verification": verification,
            "note": entry.get("note"), "historical_claims": copy.deepcopy(entry.get("historical_claims", {})),
        }
        if entry["kind"] == "opportunity":
            row.update({"disposition": entry.get("disposition"), "reason": entry.get("reason"), "is_scope_decision": False})
        rows.append(row)
    return rows


def historical_pass_closes_full_release(doc):
    """True when the document lets a historical record stand in for the full release (it must never)."""
    gates = doc.get("historical_gates")
    if not isinstance(gates, dict) or gates.get("closes_full_release") is not False:
        return True
    return any(row.get("not_full_release") is not True or row.get("status") == "PASS" for row in doc.get("rows", []))
