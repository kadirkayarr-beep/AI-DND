"""Content-bound review of a staged freeze pack.

This does not call the production pack loader and does not enable a city.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .freeze_transform import StagedPack


@dataclass(frozen=True)
class ReviewedStage:
    pack: StagedPack
    accepted_ids: tuple[str, ...]
    production_authorized: bool = False

    def __post_init__(self) -> None:
        if self.production_authorized:
            raise RuntimeError("Staged review cannot authorize production.")


def review_staged_pack(
    pack: StagedPack,
    decisions: Mapping[str, Mapping[str, str]],
) -> ReviewedStage:
    if pack.production_authorized:
        raise ValueError("Staged pack is not isolated.")
    if len(decisions) != len(pack.facts):
        raise ValueError("Review does not cover every staged fact.")
    accepted: list[str] = []
    for staged in pack.facts:
        decision = decisions.get(staged.extraction_id)
        if not isinstance(decision, Mapping):
            raise ValueError("Review is missing a staged fact.")
        if decision.get("item_payload_digest") != staged.payload_digest:
            raise ValueError("Review digest does not match the staged payload.")
        if decision.get("evidence_bundle_digest") != pack.evidence_bundle_digest:
            raise ValueError("Review is bound to different evidence.")
        if decision.get("mapping_spec_digest") != pack.mapping_digest:
            raise ValueError("Review is bound to a different mapping.")
        if decision.get("decision") != "accept":
            raise ValueError("Staged fact was not accepted.")
        if not str(decision.get("reviewer_id") or "").strip():
            raise ValueError("Reviewer id is required.")
        if not str(decision.get("review_note") or "").strip():
            raise ValueError("Review note is required.")
        accepted.append(staged.extraction_id)
    return ReviewedStage(pack, tuple(accepted), False)
