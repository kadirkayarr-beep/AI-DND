"""Expand the PHB 2024 manifest into the atomic leaf ledger (C01).

usage: python tools/content/expand_tasks.py --write   # (re)generate docs/acceptance/content-task-index.json
       python tools/content/expand_tasks.py --check   # exit 1 when the ledger is stale or a source entry has no leaf

The ledger is derived data: the manifest stays the single source of truth, and a stale ledger fails --check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-dnd"))

import capabilities  # noqa: E402

LEDGER = ROOT / "docs" / "acceptance" / "content-task-index.json"


def build() -> dict:
    rows = capabilities.manifest_rows()
    open_scope = capabilities.manifest_open_scope()
    leaves = capabilities.expand_manifest_tasks(rows) + capabilities.expand_open_scope(open_scope)
    return {
        "schema_version": 1, "task": "C01", "manifest": "content/manifest/phb2024.json",
        "entries": len(rows), "open_scope_items": len(open_scope), "leaves": len(leaves),
        "blocking_entries": len(capabilities.release_blockers(rows, open_scope)),
        "leaves_with_missing_test_owner": sum(1 for leaf in leaves if not leaf["test_owner_exists"]),
        "tasks": leaves,
    }


def main(argv: list[str]) -> int:
    ledger = build()
    text = json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if "--write" in argv:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(text, encoding="utf-8")
        print(f"wrote {LEDGER.relative_to(ROOT)}: {ledger['entries']} entries, {ledger['leaves']} leaves")
        return 0
    current = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    covered = {leaf["source_id"] for leaf in ledger["tasks"]}
    uncovered = [row["source_id"] for row in capabilities.manifest_rows() if row["source_id"] not in covered]
    if current != text or uncovered:
        print(f"stale ledger or entries without a leaf ({len(uncovered)})")
        return 1
    print("ledger is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
