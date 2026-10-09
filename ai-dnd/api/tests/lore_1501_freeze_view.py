"""In-memory view of the unapproved 1501 freeze candidate.

Reads the frozen V2.2 JSON, applies the 47 errata patches in memory, and
loads the freeze manifests. Does not write files or build a production pack.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


AI_DND = Path(__file__).resolve().parents[2]
EVIDENCE = AI_DND / "docs" / "evidence" / "phase8-expansion"

V22_JSON = (
    EVIDENCE / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json"
)
ERRATA_JSON = EVIDENCE / "lore-review-v2-2-errata" / "field_errata.json"
LEDGER_JSONL = (
    EVIDENCE / "lore-review-v2-2-current-1501" / "current_1501_ledger.jsonl"
)
INCLUSION_JSON = (
    EVIDENCE
    / "lore-review-1501-freeze-candidate"
    / "1501_Record_Inclusion_Manifest.json"
)
RESTRICTED_JSON = (
    EVIDENCE
    / "lore-review-1501-freeze-candidate"
    / "1501_Restricted_Lore_Manifest.json"
)
OWNER_DECISION = (
    EVIDENCE
    / "lore-review-1501-freeze-candidate"
    / "Owner_Decision_Castle_Ward_1501.md"
)

EXPECTED_SHA256 = {
    V22_JSON: "2255bc3b1a3b2a907e8b639528c1adb78e1b37e9a41b04934469fd6c33b46ee4",
    ERRATA_JSON: "14ef3cdedb439d9f65a52f3d01a3ad6fe4ca75021ccdc5aedd0b93b635fa2859",
    LEDGER_JSONL: "8e1a846004dfb3d03f3cfbc51dc198c4260f37331b1a1fd85d4b6f780e1d0889",
    INCLUSION_JSON: "27156e0f0b123b7d700285feb2af8da6d8e1e41108099cdcef38a1135107464a",
    RESTRICTED_JSON: "48612fc93a18f18b0858016a6aaefa9aea88f124775c0d99f128baf7a40661a9",
    OWNER_DECISION: "be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a",
}

EXCLUDED_CASTLE_WARD_INFERENCE = (
    "Castle Ward's absence from that sentence does not abolish it."
)
PERMITTED_WARD_NAMES = (
    "Sea Ward",
    "North Ward",
    "Trade Ward",
    "Southern Ward",
    "Dock Ward",
    "City of the Dead",
    "Field Ward",
)
OWNER_EXISTENCE_SENTENCE = (
    "Castle Ward continues to exist as a ward of Waterdeep in 1501 DR, "
    "the Year of the Shining Mythal."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict:
    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                raise ValueError(f"duplicate key {key} in {path.name}")
            seen[key] = value
        return seen

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def _apply_patches(records: list[dict], patches: list[dict]) -> tuple[list[dict], list[str]]:
    """Same old-to-new field replace as validate_errata.apply_patches."""
    by_id = {row["id"]: copy.deepcopy(row) for row in records}
    errors = []
    if len(by_id) != len(records):
        errors.append("duplicate record id in base")
    for patch in patches:
        row = by_id.get(patch["record_id"])
        if row is None:
            errors.append("patch record missing " + patch["record_id"])
            continue
        if row.get(patch["field"]) != patch["old"]:
            errors.append(f"old value mismatch {patch['record_id']} {patch['field']}")
            continue
        row[patch["field"]] = copy.deepcopy(patch["new"])
    return list(by_id.values()), errors


@dataclass(frozen=True)
class FreezeView:
    records: dict[str, dict]
    public_ids: tuple[str, ...]
    restricted_ids: tuple[str, ...]
    supplemental_ids: tuple[str, ...]
    historical_ids: tuple[str, ...]
    inclusion: dict
    restricted_manifest: dict
    ledger: dict[str, dict]
    owner_decision_text: str
    patch_count: int
    patched_record_count: int
    patch_errors: tuple[str, ...]

    def record(self, record_id: str) -> dict:
        return self.records[record_id]

    def ids_for(self, *, city: str, kind: str | None = None, knowledge: str | None = None) -> frozenset[str]:
        found = set()
        allowed = set(self.public_ids)
        for record_id in self.public_ids:
            row = self.records[record_id]
            if row["city"] != city:
                continue
            if kind is not None and row["kind"] != kind:
                continue
            if knowledge is not None and row["knowledge"] != knowledge:
                continue
            found.add(record_id)
        if not found <= allowed:
            raise RuntimeError("public id filter escaped the manifest")
        return frozenset(found)


def load_freeze_view() -> FreezeView:
    missing = [path for path in EXPECTED_SHA256 if not path.is_file()]
    if missing:
        names = ", ".join(path.name for path in missing)
        raise FileNotFoundError("freeze inputs missing: " + names)
    for path, expected in EXPECTED_SHA256.items():
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"freeze input changed: {path.name} sha256 {actual}")

    base = _load_object(V22_JSON)
    errata = _load_object(ERRATA_JSON)
    inclusion = _load_object(INCLUSION_JSON)
    restricted = _load_object(RESTRICTED_JSON)
    patched, errors = _apply_patches(base["records"], errata["patches"])
    records = {row["id"]: row for row in patched}
    ledger = {}
    for line in LEDGER_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ledger[row["id"]] = row
    supplemental = tuple(
        sorted(
            record_id
            for record_id, row in records.items()
            if row["applicability_1501"] == "supplemental_unconfirmed_1501"
        )
    )
    historical = tuple(
        sorted(
            record_id
            for record_id, row in records.items()
            if row["applicability_1501"] == "historical_setting"
        )
    )
    return FreezeView(
        records=records,
        public_ids=tuple(row["id"] for row in inclusion["records"]),
        restricted_ids=tuple(row["id"] for row in restricted["records"]),
        supplemental_ids=supplemental,
        historical_ids=historical,
        inclusion=inclusion,
        restricted_manifest=restricted,
        ledger=ledger,
        owner_decision_text=OWNER_DECISION.read_text(encoding="utf-8"),
        patch_count=len(errata["patches"]),
        patched_record_count=len({patch["record_id"] for patch in errata["patches"]}),
        patch_errors=tuple(errors),
    )
