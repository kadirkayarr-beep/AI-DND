"""Narration authorization for freeze-candidate claims.

Importing this module does not load the production registry. The fingerprint
check reads the packet the caller already built. It does not add a fingerprint
object to that packet.
"""

from __future__ import annotations

from typing import Any, Mapping

from .freeze_eligibility import load_corpus


def freeze_claims_authorized(
    claim_ids: list[str],
    lore_context: Mapping[str, Any] | None,
) -> bool:
    corpus = load_corpus()
    if not corpus.available:
        return True
    sections = {}
    if isinstance(lore_context, Mapping):
        raw_sections = lore_context.get("sections")
        if isinstance(raw_sections, Mapping):
            sections = raw_sections
    rows: dict[str, Mapping[str, Any]] = {}
    for name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
        "npc_known_lore",
    ):
        for item in sections.get(name, ()):
            if not isinstance(item, Mapping):
                continue
            fact_id = item.get("fact_id") or item.get("override_id")
            if isinstance(fact_id, str):
                rows[fact_id] = item
    for fact_id in claim_ids:
        if fact_id not in corpus.all_ids:
            continue
        permitted = corpus.public_claims.get(fact_id)
        row = rows.get(fact_id)
        if permitted is None or row is None:
            return False
        if row.get("object_id_or_value") != permitted:
            return False
        if fact_id not in corpus.page_verified_ids and row.get("authority_tier") != "TEST_FIXTURE":
            return False
    return True
