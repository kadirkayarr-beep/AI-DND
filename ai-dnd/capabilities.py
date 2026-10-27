"""Capability status and leaf-task expansion for the PHB 2024 manifest (C01).

A manifest entry is COMPLETE only when all six lifecycle axes (visible, create, select, use, advance, save_load) are
SUPPORTED. Any other combination is INCOMPLETE (or NOT_ASSESSED when nothing was proven); a source entry whose enumeration is
still open is OPEN and can never be COMPLETE. `expand_manifest_tasks` gives every source entry atomic leaves so that no class,
spell or feat is closed by a bulk "done" label; `release_blockers` lists what still stops a full release.

Interfaces follow the plan; `RuleContext`/`RuleDelta`/`CapabilityRow` do not exist as types in this codebase, so plain dicts are the
equivalent (a delta always carries `status` and `changes`). Resolvers stay with their existing owners: `resolve_capability` only dispatches to a resolver a family has registered for an
entry that is COMPLETE, and otherwise refuses without changing anything.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = _ROOT / "ai-dnd" / "api" / "tests"
EVIDENCE_ROOT = _ROOT / "docs" / "acceptance" / "evidence"  # tests may point this at a temporary directory
AXES = ("visible", "create", "select", "use", "advance", "save_load")
AXIS_STATES = frozenset({"SUPPORTED", "UNSUPPORTED", "NOT_ASSESSED"})
_MANIFEST = Path(__file__).resolve().parents[1] / "content" / "manifest" / "phb2024.json"
_RESOLVERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {}
_cache: dict[str, Any] = {}


def _manifest() -> dict[str, Any]:
    if "manifest" not in _cache:
        _cache["manifest"] = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return _cache["manifest"]


def manifest_rows() -> list[dict[str, Any]]:
    """The B04 manifest entries (one per source entry)."""
    return _manifest()["rows"]


def manifest_open_scope() -> list[dict[str, Any]]:
    """Source sections B04 declared but did not enumerate (rule lists, appendices); open work, never counted as done."""
    return _manifest().get("open_scope_items", [])


def _confined(path: str, base: Path) -> Path | None:
    """Resolve `path` under `base`; anything that escapes it (`..`, absolute paths, symlinks out) is refused."""
    try:
        resolved = (base / str(path)).resolve()
        return resolved if resolved.is_relative_to(base.resolve()) else None
    except (OSError, ValueError):
        return None


def evidence_valid(evidence: Any, entry_id: str, axis: str) -> bool:
    """A real acceptance record bound to exactly this (entry, axis): a PASS row (integer exit code 0, not a mock) for this
    evidence id that names this entry, this axis and this very test file, inside the evidence root; and a real `test_*.py`
    inside the tests directory. A bare id, flag or status, an unrelated existing file, or a record reused for another entry or
    axis proves nothing."""
    if not isinstance(evidence, dict) or not isinstance(evidence.get("evidence_id"), str) or not evidence["evidence_id"]:
        return False
    test = _confined(evidence.get("test_owner", ""), _ROOT)
    tests_dir = TESTS_ROOT.resolve()
    if test is None or not test.is_file() or not test.is_relative_to(tests_dir) or not test.name.startswith("test_")             or test.suffix != ".py":
        return False
    record_path = _confined(evidence.get("record", ""), EVIDENCE_ROOT)
    if record_path is None or not record_path.is_file():
        return False
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(record, dict) and record.get("testID") == evidence["evidence_id"] and record.get("status") == "PASS"
            and type(record.get("exitCode")) is int and record["exitCode"] == 0 and record.get("mock") is False
            and record.get("entry") == entry_id and record.get("axis") == axis
            and record.get("test") == evidence.get("test_owner"))


def _proven_axes(row: dict[str, Any]) -> set[str]:
    """Axes with valid evidence bound to this entry and axis (a record cannot serve two entries or two axes)."""
    return {axis for axis in AXES
            if evidence_valid((row.get("axis_evidence") or {}).get(axis), str(row.get("source_id")), axis)}


def status_of_row(row: dict[str, Any], character: dict[str, Any]) -> dict[str, Any]:
    """Per-axis state plus an overall status; `character` is reserved for per-character selection checks.

    A claimed SUPPORTED without evidence is reported as UNPROVEN and does not count; a test file merely existing proves nothing
    without an evidence id, and an evidence id without an existing test file proves nothing either.
    """
    raw = {axis: (row.get("lifecycle") or {}).get(axis, "NOT_ASSESSED") for axis in AXES}
    proven = _proven_axes(row)
    axes = {axis: ("UNPROVEN" if state == "SUPPORTED" and axis not in proven else state) for axis, state in raw.items()}
    missing = [axis for axis in AXES if axes[axis] != "SUPPORTED"]
    if any(state not in AXIS_STATES for state in raw.values()):
        overall = "INVALID_ROW"  # an unknown axis value (a typo) is never read as progress
    elif row.get("status") != "INVENTORIED":
        overall = "OPEN"
    elif not missing:
        overall = "COMPLETE"
    elif all(state == "NOT_ASSESSED" for state in axes.values()):
        overall = "NOT_ASSESSED"
    else:
        overall = "INCOMPLETE"
    return {"entry_id": row.get("id"), "source_id": row.get("source_id"), "axes": axes, "missing_axes": missing, "status": overall}


def capability_status(entry_id: str, character: dict[str, Any]) -> dict[str, Any]:
    row = next((r for r in manifest_rows() if entry_id in (r["id"], r["source_id"])), None)
    if row is None:
        return {"entry_id": entry_id, "status": "UNKNOWN_ENTRY", "axes": {}, "missing_axes": list(AXES)}
    return status_of_row(row, character)


def register_resolver(entry_id: str, resolver: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]) -> None:
    _RESOLVERS[entry_id] = resolver


def resolve_capability(entry_id: str, context: dict[str, Any], choice: dict[str, Any]) -> dict[str, Any]:
    status = capability_status(entry_id, context)
    resolver = _RESOLVERS.get(entry_id)
    if status["status"] != "COMPLETE" or resolver is None:
        return {"entry_id": entry_id, "status": "unsupported", "changes": [],
                "reason": f"capability is {status['status']}; no change applied"}
    return resolver(context, choice)


def _behaviors(row: dict[str, Any]) -> list[str]:
    if row.get("status") != "INVENTORIED":
        return ["enumerate"]
    behaviors = []
    for axis in AXES:
        if axis == "advance" and row.get("category") == "spell":
            # the level of a spell is not in the index: cantrip scaling and slot upcasting are separate behaviours
            behaviors += ["advance.cantrip_scaling", "advance.slot_upcast"]
        else:
            behaviors.append(axis)
    return behaviors


def _leaf_ids(row: dict[str, Any]) -> list[str]:
    owner = row.get("proposed_owner") or "UNOWNED"
    return [f"{owner}.{row['source_id']}.{behavior}" for behavior in _behaviors(row)]


def _test_owner(owner: str) -> tuple[str, str, bool]:
    module = f"api.tests.test_roadmap_{str(owner).lower()}"
    path = f"ai-dnd/{module.replace('.', '/')}.py"
    return module, path, (_ROOT / path).exists()


def expand_manifest_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One atomic leaf per behaviour per source entry: oracle, command, dependency, rollback, test owner.

    A manifest dependency (a source id) is mapped to the LAST leaf of that entry (its chain makes the earlier ones implied);
    a dependency outside the given rows is kept as an explicit `unresolved:<source_id>` marker, never dropped.
    """
    source_ids = [row["source_id"] for row in rows]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Duplicate source_id in the manifest rows.")
    last_leaf = {row["source_id"]: _leaf_ids(row)[-1] for row in rows}
    leaves: list[dict[str, Any]] = []
    for row in rows:
        owner = row.get("proposed_owner") or "UNOWNED"
        source = row.get("source") or {}
        module, test_path, test_exists = _test_owner(owner)
        previous = None
        for behavior, leaf_id in zip(_behaviors(row), _leaf_ids(row)):
            deps = [last_leaf.get(dep, f"unresolved:{dep}") for dep in (row.get("dependencies") or [])]
            leaves.append({
                "leaf_id": leaf_id, "source_id": row["source_id"], "entry_id": row["id"], "category": row.get("category"),
                "behavior": behavior, "owner": owner, "status": "OPEN" if row.get("status") != "INVENTORIED" else "NOT_STARTED",
                "existing_owner": (row.get("resolver") or {}).get("existing_owner"),
                "test_owner": test_path, "test_owner_exists": test_exists,
                "oracle": {"book": source.get("book"), "edition": source.get("edition"), "pdf_page": source.get("pdf_page"),
                           "printed_page": source.get("printed_page"), "section": source.get("section"),
                           "source_id": row["source_id"]},
                "command": f"cd ai-dnd && python -m unittest {module} -v",
                "dependencies": [*deps, *([previous] if previous else [])],
                "rollback": "RB-1",
            })
            previous = leaf_id
    return leaves


def _slug(area: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(area or "").lower()).strip("-")


def expand_open_scope(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One OPEN `enumerate` leaf per declared-but-not-enumerated source area."""
    leaves = []
    slugs = [re.sub(r"[^a-z0-9]+", "-", str(item.get("area", "")).lower()).strip("-") for item in items]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate open scope area.")
    for item in items:
        slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("area", "")).lower()).strip("-")
        owner = item.get("proposed_owner") or "UNOWNED"
        module, test_path, test_exists = _test_owner(owner)
        pages = item.get("pdf_pages") or [None, None]
        leaves.append({
            "leaf_id": f"{owner}.openscope:{slug}.enumerate", "source_id": f"openscope:{slug}", "entry_id": f"openscope|{slug}",
            "category": "open_scope", "behavior": "enumerate", "owner": owner, "status": "OPEN",
            "test_owner": test_path, "test_owner_exists": test_exists,
            "oracle": {"area": item.get("area"), "pdf_page": pages[0], "pdf_page_end": pages[-1], "reason": item.get("reason")},
            "command": f"cd ai-dnd && python -m unittest {module} -v", "dependencies": [], "rollback": "RB-1",
        })
    return leaves


def can_complete_leaf(leaf_id: str, leaves: list[dict[str, Any]], completed: set[str]) -> dict[str, Any]:
    """A leaf may complete only when EVERY leaf it depends on, transitively, is already completed.

    Finding the target id is not enough: the dependency's earlier leaves must be complete too (an out-of-order completion of a
    class's last leaf does not satisfy a subclass), and an `unresolved:` dependency is never satisfied.
    """
    by_id = {leaf["leaf_id"]: leaf for leaf in leaves}
    if leaf_id not in by_id:
        return {"allowed": False, "unmet": [leaf_id], "reason": "unknown_leaf"}
    if leaf_id in completed:
        return {"allowed": False, "unmet": [], "reason": "already_completed"}
    unmet: list[str] = []
    seen: set[str] = set()
    stack = list(by_id[leaf_id]["dependencies"])
    while stack:
        dependency = stack.pop()
        if dependency in seen:
            continue
        seen.add(dependency)
        if dependency not in completed or dependency not in by_id:
            unmet.append(dependency)
        if dependency in by_id:
            stack.extend(by_id[dependency]["dependencies"])
    if leaf_id in seen:
        return {"allowed": False, "unmet": sorted(unmet), "reason": "dependency_cycle"}
    return {"allowed": not unmet, "unmet": sorted(unmet), "reason": None if not unmet else "dependencies_incomplete"}


_VIEW_LABELS = {"COMPLETE": "usable", "INCOMPLETE": "partial", "NOT_ASSESSED": "not_yet_supported",
                "OPEN": "not_yet_supported", "INVALID_ROW": "not_yet_supported", "UNKNOWN_ENTRY": "unknown"}


def capability_view(entry_id: str, character: dict[str, Any]) -> dict[str, Any]:
    """What a menu may honestly show: only a COMPLETE entry is selectable; everything else says what is missing."""
    status = capability_status(entry_id, character)
    return {"entry_id": entry_id, "label": _VIEW_LABELS.get(status["status"], "not_yet_supported"),
            "selectable": status["status"] == "COMPLETE", "missing_axes": status["missing_axes"], "status": status["status"]}


def release_blockers(rows: list[dict[str, Any]], open_scope_items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Entries and declared open scope areas that are not COMPLETE; a full release needs this list to be empty.

    `open_scope_items=None` loads the manifest's open scope: forgetting the argument can never hide it (pass `[]` explicitly
    to ignore it, e.g. in a unit test of rows only)."""
    if open_scope_items is None:
        open_scope_items = manifest_open_scope()
    statuses = [status_of_row(row, {}) for row in rows]
    blockers = [status for status in statuses if status["status"] != "COMPLETE"]
    # a declared open scope area blocks until the area itself is recorded ENUMERATED_COMPLETE with its sub-leaves; closing the
    # counting (`enumerate`) leaf never removes the blocker
    items = [item for item in open_scope_items
             if not (item.get("status") == "ENUMERATED_COMPLETE"
                     and evidence_valid(item.get("evidence"), "openscope:" + _slug(item.get("area")), "enumerate"))]
    blockers += [{"entry_id": f"openscope|{leaf['source_id'][10:]}", "source_id": leaf["source_id"], "status": "OPEN",
                  "axes": {}, "missing_axes": list(AXES)} for leaf in expand_open_scope(items)]
    return blockers
