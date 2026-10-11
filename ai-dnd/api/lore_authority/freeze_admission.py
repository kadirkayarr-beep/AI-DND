"""Fail-closed admission check for the unapproved 1501 DR freeze candidate.

This module does not load a pack, change retrieval, or grant player knowledge.
Production loading must call it in a later, separately approved step before
any Waterdeep or Baldur's Gate record can enter a registry.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


AI_DND = Path(__file__).resolve().parents[2]
EVIDENCE = AI_DND / "docs" / "evidence" / "phase8-expansion"

V22_JSON = EVIDENCE / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json"
ERRATA_JSON = EVIDENCE / "lore-review-v2-2-errata" / "field_errata.json"
LEDGER_JSONL = EVIDENCE / "lore-review-v2-2-current-1501" / "current_1501_ledger.jsonl"
INCLUSION_JSON = (
    EVIDENCE / "lore-review-1501-freeze-candidate" / "1501_Record_Inclusion_Manifest.json"
)
RESTRICTED_JSON = (
    EVIDENCE / "lore-review-1501-freeze-candidate" / "1501_Restricted_Lore_Manifest.json"
)
OWNER_DECISION = (
    EVIDENCE / "lore-review-1501-freeze-candidate" / "Owner_Decision_Castle_Ward_1501.md"
)

PINNED_SHA256 = {
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
CURRENT_APPLICABILITY = "current_1501_candidate"
PUBLIC_KNOWLEDGE = "public"
OWNER_DECISION_CLASS = "OWNER-APPROVED CONTINUITY DECISION"


@dataclass(frozen=True)
class FreezeEvidence:
    """In-memory freeze view. Empty maps mean the load failed closed."""

    records: Mapping[str, Mapping[str, Any]]
    public_records: Mapping[str, Mapping[str, Any]]
    restricted_ids: frozenset[str]
    ledger: Mapping[str, Mapping[str, Any]]
    owner_statement: str
    integrity_errors: tuple[str, ...]


@dataclass(frozen=True)
class AdmittedSource:
    """Source citation copied from the pinned manifest, not from the proposal."""

    source_title: str
    source_sha256: str
    pdf_pages: tuple[int, ...]


@dataclass(frozen=True)
class AdmittedRecord:
    """Immutable facts a future constructor may copy.

    Runtime proposal fields are absent: visibility, temporal_scope,
    authority tier, LoreFact review status, and provenance.
    """

    record_id: str
    claim: str
    knowledge: str
    applicability_1501: str
    inclusion_status: str
    sources: tuple[AdmittedSource, ...]
    player_knowledge: str
    source_review_status: str
    source_production_status: str
    production_authorized: bool = False

    def __post_init__(self) -> None:
        if self.production_authorized:
            raise RuntimeError("An admitted freeze record cannot authorize production.")
        if self.player_knowledge != "not_granted":
            raise RuntimeError("Admission cannot grant player knowledge.")
        if self.knowledge != PUBLIC_KNOWLEDGE:
            raise RuntimeError("Admission cannot project a non-public classification.")
        if self.applicability_1501 != CURRENT_APPLICABILITY:
            raise RuntimeError("Admission cannot project a non-current applicability.")
        if self.source_review_status != "UNREVIEWED" or self.source_production_status != "DRAFT":
            raise RuntimeError("Admission cannot project an approved review status.")
        if EXCLUDED_CASTLE_WARD_INFERENCE in self.claim:
            raise RuntimeError("Admission cannot project the excluded Castle Ward inference.")


@dataclass(frozen=True)
class AdmissionDecision:
    record_id: str
    admitted: bool
    reasons: tuple[str, ...]
    production_authorized: bool = False
    record: AdmittedRecord | None = None

    def __post_init__(self) -> None:
        if self.production_authorized:
            raise RuntimeError("Freeze admission cannot authorize production loading.")
        if self.admitted and self.reasons:
            raise RuntimeError("An admitted record cannot carry rejection reasons.")
        if not self.admitted and not self.reasons:
            raise RuntimeError("A rejection requires at least one reason.")
        if self.admitted and self.record is None:
            raise RuntimeError("Admission requires a pinned projection.")
        if not self.admitted and self.record is not None:
            raise RuntimeError("A rejection cannot carry a trusted projection.")
        if self.record is not None and self.record.record_id != self.record_id:
            raise RuntimeError("The projection id does not match the decision.")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_json_object(data: bytes, name: str) -> dict[str, Any]:
    """Parse one already-hashed byte snapshot. Duplicate keys fail closed."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in items:
            if key in seen:
                raise ValueError(f"duplicate key {key} in {name}")
            seen[key] = value
        return seen

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _sequence(value: Any) -> list[Any] | None:
    if isinstance(value, (list, tuple)):
        return list(value)
    return None


def _apply_patches(
    records: list[dict[str, Any]],
    patches: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_id = {row["id"]: copy.deepcopy(row) for row in records}
    errors: list[str] = []
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
    return by_id, errors


def _owner_statement(text: str) -> str | None:
    marker = "## Approved statement"
    if marker not in text or OWNER_DECISION_CLASS not in text:
        return None
    body = text.split(marker, 1)[1].lstrip("\n")
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("#"):
            break
        lines.append(line)
    paragraphs = [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]
    if not paragraphs:
        return None
    return paragraphs[0]


def _failed_evidence(errors: list[str]) -> FreezeEvidence:
    return FreezeEvidence(
        records={},
        public_records={},
        restricted_ids=frozenset(),
        ledger={},
        owner_statement="",
        integrity_errors=tuple(errors),
    )


def load_freeze_evidence(
    *,
    expected_sha256: Mapping[Path, str] | None = None,
) -> FreezeEvidence:
    """Load the pinned freeze. A hash or shape failure admits nothing."""
    pins = expected_sha256 if expected_sha256 is not None else PINNED_SHA256
    errors: list[str] = []
    blobs: dict[Path, bytes] = {}
    for path, expected in pins.items():
        if not path.is_file():
            errors.append(f"missing {path.name}")
            continue
        data = path.read_bytes()
        if _sha256_bytes(data) != expected:
            errors.append(f"sha256 mismatch {path.name}")
            continue
        blobs[path] = data
    if errors:
        return _failed_evidence(errors)
    if set(blobs) != set(PINNED_SHA256):
        return _failed_evidence(["pin set does not cover the freeze evidence"])

    try:
        base = parse_json_object(blobs[V22_JSON], V22_JSON.name)
        errata = parse_json_object(blobs[ERRATA_JSON], ERRATA_JSON.name)
        inclusion = parse_json_object(blobs[INCLUSION_JSON], INCLUSION_JSON.name)
        restricted = parse_json_object(blobs[RESTRICTED_JSON], RESTRICTED_JSON.name)
        owner_text = blobs[OWNER_DECISION].decode("utf-8")
        records, patch_errors = _apply_patches(base["records"], errata["patches"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return _failed_evidence([f"unreadable freeze evidence: {error}"])
    errors.extend(patch_errors)
    statement = _owner_statement(owner_text)
    if statement is None:
        errors.append("owner decision statement missing")
    if inclusion.get("status") != "FREEZE_CANDIDATE_NOT_APPROVED":
        errors.append("public manifest is not an unapproved freeze candidate")
    if inclusion.get("do_not_load_as_pack") is not True:
        errors.append("public manifest is marked loadable")
    public_rows = inclusion.get("records")
    if (
        not isinstance(public_rows, list)
        or inclusion.get("included_total") != len(public_rows)
        or len({row.get("id") for row in public_rows}) != len(public_rows)
    ):
        errors.append("public manifest records are incomplete")
        public_rows = []
    restricted_rows = restricted.get("records")
    if (
        not isinstance(restricted_rows, list)
        or restricted.get("count") != len(restricted_rows)
        or len({row.get("id") for row in restricted_rows}) != len(restricted_rows)
    ):
        errors.append("restricted manifest records are incomplete")
        restricted_rows = []
    ledger: dict[str, dict[str, Any]] = {}
    try:
        for line in blobs[LEDGER_JSONL].decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in ledger:
                errors.append("duplicate ledger id " + row["id"])
            ledger[row["id"]] = row
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"unreadable ledger: {error}")
    if errors:
        return _failed_evidence(errors)
    return FreezeEvidence(
        records=records,
        public_records={row["id"]: row for row in public_rows},
        restricted_ids=frozenset(row["id"] for row in restricted_rows),
        ledger=ledger,
        owner_statement=statement or "",
        integrity_errors=(),
    )


def _reject(record_id: str, reasons: list[str] | tuple[str, ...]) -> AdmissionDecision:
    unique = tuple(dict.fromkeys(reason for reason in reasons if reason))
    if not unique:
        unique = ("rejected",)
    return AdmissionDecision(record_id, False, unique, False)


def _sources_match(
    proposal_sources: Any,
    manifest_sources: Any,
    citations: Any,
) -> str | None:
    manifest_list = _sequence(manifest_sources)
    citation_list = _sequence(citations)
    proposal_list = _sequence(proposal_sources)
    if not manifest_list:
        return "missing_source_evidence"
    if not citation_list:
        return "missing_source_evidence"
    if not proposal_list:
        return "missing_sources"
    if _plain(proposal_list) != _plain(manifest_list):
        return "source_hash_mismatch"
    cited = set()
    for citation in citation_list:
        if not isinstance(citation, Mapping):
            return "missing_source_evidence"
        pages = _sequence(citation.get("pdf_pages"))
        if not pages:
            return "missing_source_evidence"
        digest = citation.get("source_sha256")
        title = citation.get("source_title")
        if not isinstance(digest, str) or len(digest) != 64:
            return "missing_source_evidence"
        if not isinstance(title, str) or not title.strip():
            return "missing_source_evidence"
        cited.add((digest, tuple(pages), title))
    for source in manifest_list:
        if not isinstance(source, Mapping):
            return "missing_source_evidence"
        key = (source.get("source_sha256"), tuple(source.get("pdf_pages") or ()), source.get("source_title"))
        if key not in cited:
            return "source_not_in_record_citations"
    return None


def _permitted_claim(
    record: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    owner_statement: str,
) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    status = manifest_row.get("inclusion_status")
    if status == "included_partial":
        scope = manifest_row.get("included_scope")
        excluded = manifest_row.get("excluded_scope")
        if not isinstance(scope, str) or not scope.strip() or not isinstance(excluded, str) or not excluded.strip():
            return None, ["missing_partial_scope"]
        if "Castle Ward" in scope or EXCLUDED_CASTLE_WARD_INFERENCE in scope or owner_statement in scope:
            return None, ["partial_scope_evidence_invalid"]
        return scope, reasons
    if status != "included_full":
        return None, ["missing_inclusion_status"]
    claim = record.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return None, ["missing_source_claim"]
    return claim, reasons


def _pinned_sources(manifest_sources: Any) -> tuple[AdmittedSource, ...] | None:
    manifest_list = _sequence(manifest_sources)
    if not manifest_list:
        return None
    pinned: list[AdmittedSource] = []
    for source in manifest_list:
        if not isinstance(source, Mapping):
            return None
        pages = _sequence(source.get("pdf_pages"))
        title = source.get("source_title")
        digest = source.get("source_sha256")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(digest, str)
            or len(digest) != 64
            or not pages
            or not all(type(page) is int for page in pages)
        ):
            return None
        pinned.append(AdmittedSource(title, digest, tuple(pages)))
    return tuple(pinned)


def _closed_review(record: Mapping[str, Any], manifest_row: Mapping[str, Any]) -> bool:
    return (
        record.get("review_status") == "UNREVIEWED"
        and manifest_row.get("review_status") == "UNREVIEWED"
        and record.get("production_status") == "DRAFT"
        and manifest_row.get("production_status") == "DRAFT"
    )


def admit_record(
    proposal: Mapping[str, Any] | None,
    evidence: FreezeEvidence | None = None,
) -> AdmissionDecision:
    """Admit one proposal only when the frozen source evidence allows it.

    Success returns an ``AdmittedRecord`` built from the pinned source and
    the approved inclusion scope. Proposal visibility, temporal scope, source
    tier, review status, and provenance are not copied.
    """
    if not isinstance(proposal, Mapping):
        return _reject("", ["proposal_not_an_object"])
    record_id = proposal.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        return _reject("", ["missing_record_id"])
    loaded = evidence if evidence is not None else load_freeze_evidence()
    if loaded.integrity_errors:
        return _reject(record_id, ["freeze_integrity", *loaded.integrity_errors])

    reasons: list[str] = []
    claim = proposal.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        reasons.append("missing_claim")
    if loaded.owner_statement and isinstance(claim, str) and loaded.owner_statement in claim:
        reasons.append("owner_continuity_not_source_fact")
    if proposal.get("provenance") == OWNER_DECISION_CLASS or proposal.get("decision_class") == OWNER_DECISION_CLASS:
        reasons.append("owner_continuity_not_source_fact")
    if isinstance(claim, str) and EXCLUDED_CASTLE_WARD_INFERENCE in claim:
        reasons.append("excluded_castle_ward_inference")

    record = loaded.records.get(record_id)
    manifest_row = loaded.public_records.get(record_id)
    if record is None or manifest_row is None:
        reasons.append("not_in_public_freeze_manifest")
        if record_id in loaded.restricted_ids or (record is not None and record.get("knowledge") != PUBLIC_KNOWLEDGE):
            reasons.append("source_classification_not_public")
        if record is not None and record.get("applicability_1501") != CURRENT_APPLICABILITY:
            reasons.append("applicability_not_verified_current")
        return _reject(record_id, reasons)

    if record.get("knowledge") != PUBLIC_KNOWLEDGE or manifest_row.get("knowledge") != PUBLIC_KNOWLEDGE:
        reasons.append("source_classification_not_public")
    if record_id in loaded.restricted_ids:
        reasons.append("source_classification_not_public")
    applicability = record.get("applicability_1501")
    if applicability != CURRENT_APPLICABILITY:
        reasons.append(
            "missing_current_applicability"
            if applicability in {None, ""}
            else "applicability_not_verified_current"
        )
    ledger_row = loaded.ledger.get(record_id)
    if ledger_row is None:
        reasons.append("missing_ledger_evidence")
    else:
        expected_verdict = (
            "verified_clause_excluded"
            if manifest_row.get("inclusion_status") == "included_partial"
            else "verified_public"
        )
        if ledger_row.get("verdict") != expected_verdict or manifest_row.get("ledger_verdict") != expected_verdict:
            reasons.append("ledger_verdict_not_verified")
    if manifest_row.get("player_knowledge") != "not_granted" or record.get("player_knowledge") != "not_granted":
        reasons.append("player_knowledge_already_granted")
    if not _closed_review(record, manifest_row):
        reasons.append("source_review_not_closed")
    source_error = _sources_match(
        proposal.get("sources"),
        manifest_row.get("sources"),
        record.get("citations"),
    )
    if source_error:
        reasons.append(source_error)
    permitted, scope_errors = _permitted_claim(record, manifest_row, loaded.owner_statement)
    reasons.extend(scope_errors)
    if permitted is None:
        pass
    elif not isinstance(claim, str) or claim != permitted:
        if "missing_claim" not in reasons:
            reasons.append("claim_mismatch")
    if permitted is not None and loaded.owner_statement and loaded.owner_statement in permitted:
        reasons.append("owner_continuity_not_source_fact")
    pinned_sources = _pinned_sources(manifest_row.get("sources"))
    if pinned_sources is None:
        reasons.append("missing_source_evidence")
    if reasons or permitted is None or pinned_sources is None:
        return _reject(record_id, reasons)
    projected = AdmittedRecord(
        record_id=record_id,
        claim=permitted,
        knowledge=PUBLIC_KNOWLEDGE,
        applicability_1501=CURRENT_APPLICABILITY,
        inclusion_status=str(manifest_row.get("inclusion_status")),
        sources=pinned_sources,
        player_knowledge="not_granted",
        source_review_status="UNREVIEWED",
        source_production_status="DRAFT",
        production_authorized=False,
    )
    return AdmissionDecision(record_id, True, (), False, projected)


def canonical_proposal(evidence: FreezeEvidence, record_id: str) -> dict[str, Any]:
    """The only proposal shape built from frozen evidence for one public ID."""
    manifest_row = evidence.public_records[record_id]
    record = evidence.records[record_id]
    permitted, errors = _permitted_claim(record, manifest_row, evidence.owner_statement)
    if permitted is None or errors:
        raise ValueError("no permitted claim for " + record_id)
    return {
        "id": record_id,
        "claim": permitted,
        "sources": _plain(manifest_row["sources"]),
    }


def bundle_digest() -> str:
    lines = [
        f"{path.name}:{PINNED_SHA256[path]}"
        for path in sorted(PINNED_SHA256, key=lambda item: item.name)
    ]
    return _sha256_bytes("\n".join(lines).encode("utf-8"))


def _batch_token(digest: str) -> str:
    return _sha256_bytes(b"phase8-trusted-batch:" + digest.encode("utf-8"))


def _text_tuple(value: Any) -> tuple[str, ...]:
    items = _sequence(value) or []
    return tuple(item for item in items if isinstance(item, str))


@dataclass(frozen=True)
class ProjectionStructure:
    """Structure taken from the pinned record, not from caller metadata."""

    kind: str
    extraction_id: str
    support_ids: tuple[str, ...]
    source_entity_id: str | None
    target_entity_id: str | None
    relationship_type: str | None
    reviewed_mapping_id: str | None = None


@dataclass(frozen=True)
class TrustedProjection:
    record: AdmittedRecord
    structure: ProjectionStructure
    evidence_bundle_digest: str
    batch_token: str


@dataclass(frozen=True)
class PinnedSnapshot:
    evidence: FreezeEvidence
    digest: str
    permitted_claims: Mapping[str, str]


_SNAPSHOT: PinnedSnapshot | None = None


def load_pinned_snapshot() -> PinnedSnapshot:
    """Production-safe snapshot. Custom pins cannot be injected here."""
    global _SNAPSHOT
    if _SNAPSHOT is not None:
        return _SNAPSHOT
    evidence = load_freeze_evidence()
    frozen = FreezeEvidence(
        records=_freeze(_plain(evidence.records)),
        public_records=_freeze(_plain(evidence.public_records)),
        restricted_ids=frozenset(evidence.restricted_ids),
        ledger=_freeze(_plain(evidence.ledger)),
        owner_statement=evidence.owner_statement,
        integrity_errors=evidence.integrity_errors,
    )
    permitted: dict[str, str] = {}
    if not frozen.integrity_errors:
        for record_id in frozen.public_records:
            claim, errors = _permitted_claim(
                frozen.records[record_id],
                frozen.public_records[record_id],
                frozen.owner_statement,
            )
            if claim is not None and not errors:
                permitted[record_id] = claim
    _SNAPSHOT = PinnedSnapshot(frozen, bundle_digest(), MappingProxyType(permitted))
    return _SNAPSHOT


def _structure_for(evidence: FreezeEvidence, record_id: str) -> ProjectionStructure:
    row = evidence.records[record_id]
    kind = row.get("kind")
    source_entity = row.get("source_entity_id")
    target_entity = row.get("target_entity_id")
    relationship = row.get("relationship_type")
    return ProjectionStructure(
        kind=kind if isinstance(kind, str) else "",
        extraction_id=record_id,
        support_ids=_text_tuple(row.get("supported_by")),
        source_entity_id=source_entity if isinstance(source_entity, str) else None,
        target_entity_id=target_entity if isinstance(target_entity, str) else None,
        relationship_type=relationship if isinstance(relationship, str) else None,
        reviewed_mapping_id=None,
    )


@dataclass(frozen=True)
class TrustedBatch:
    digest: str
    token: str
    projections: tuple[TrustedProjection, ...]
    rejections: tuple[str, ...]
    integrity_errors: tuple[str, ...]
    production_authorized: bool = False

    def __post_init__(self) -> None:
        if self.production_authorized:
            raise RuntimeError("A freeze batch cannot authorize production.")
        if self.integrity_errors or self.rejections:
            if self.projections:
                raise RuntimeError("A rejected batch cannot carry projections.")
            return
        if self.token != _batch_token(self.digest):
            raise RuntimeError("Batch token is not bound to the evidence digest.")
        snapshot = load_pinned_snapshot()
        if snapshot.evidence.integrity_errors or snapshot.digest != self.digest:
            raise RuntimeError("Batch is not bound to the pinned snapshot.")
        by_id = {item.record.record_id: item for item in self.projections}
        if set(by_id) != set(snapshot.permitted_claims):
            raise RuntimeError("Batch does not match the public freeze.")
        for item in self.projections:
            expected = snapshot.permitted_claims[item.record.record_id]
            if item.record.claim != expected or item.batch_token != self.token:
                raise RuntimeError("Projection is not bound to the pinned claim.")
            if item.evidence_bundle_digest != self.digest:
                raise RuntimeError("Projection digest does not match the batch.")


def admit_public_batch() -> TrustedBatch:
    """Admit every public record, or return a batch with no projections."""
    snapshot = load_pinned_snapshot()
    if snapshot.evidence.integrity_errors or len(snapshot.permitted_claims) != len(snapshot.evidence.public_records):
        return TrustedBatch(
            snapshot.digest,
            "",
            (),
            (),
            snapshot.evidence.integrity_errors or ("incomplete_permitted_claims",),
            False,
        )
    projections: list[TrustedProjection] = []
    rejections: list[str] = []
    token = _batch_token(snapshot.digest)
    for record_id in sorted(snapshot.permitted_claims):
        decision = admit_record(
            canonical_proposal(snapshot.evidence, record_id),
            snapshot.evidence,
        )
        if not decision.admitted or decision.record is None:
            rejections.append(record_id)
            continue
        projections.append(TrustedProjection(
            record=decision.record,
            structure=_structure_for(snapshot.evidence, record_id),
            evidence_bundle_digest=snapshot.digest,
            batch_token=token,
        ))
    if rejections or len(projections) != len(snapshot.permitted_claims):
        return TrustedBatch(snapshot.digest, "", (), tuple(rejections or ("incomplete_batch",)), (), False)
    return TrustedBatch(snapshot.digest, token, tuple(projections), (), (), False)


def projection_is_transform_ready(value: Any, batch: TrustedBatch) -> bool:
    """Type identity alone is not a trusted origin."""
    if not isinstance(value, TrustedProjection) or batch.integrity_errors or batch.rejections:
        return False
    return any(
        item.batch_token == value.batch_token
        and item.record.record_id == value.record.record_id
        and item.record.claim == value.record.claim
        and item.evidence_bundle_digest == batch.digest
        for item in batch.projections
    )
