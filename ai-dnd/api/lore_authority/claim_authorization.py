"""Narration authorization for freeze-candidate claims.

Importing this module does not load the production registry. The fingerprint
check reads the packet the caller already built. It does not add a fingerprint
object to that packet.
"""

from __future__ import annotations

import re
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


_EXACT_CLAIM_TYPES = frozenset({"OBJECTIVE_CANON_FACT", "HISTORICAL_FACT"})
_EXACT_VISIBILITY = frozenset({"COMMON_KNOWLEDGE", "REGIONAL_KNOWLEDGE"})
_TURKISH_FOLD = str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"})


def _fold(value: Any) -> str:
    text = str(value or "").casefold().translate(_TURKISH_FOLD)
    text = re.sub(r"['’](?:s|[a-z]{1,5})\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _sentences(value: Any) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?。！？])\s+", str(value or "").strip()) if part.strip()]


def exact_narration_evidence_ids(
    narration: Any,
    lore_context: Mapping[str, Any] | None,
) -> list[str]:
    """Fact ids for a narration made only of sentences a public official fact states.

    The narration-only prompt asks the model for no citations, so evidence is
    chosen here instead: every sentence must equal a sentence of an eligible
    row's `notes`. Anything else, including one extra sentence or a changed
    figure, selects nothing and the ordinary unsupported-claim guard applies.
    """
    sections = lore_context.get("sections") if isinstance(lore_context, Mapping) else None
    rows = sections.get("official_forgotten_realms_lore") if isinstance(sections, Mapping) else None
    if not isinstance(rows, (list, tuple)):
        return []
    by_sentence: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("hidden"):
            continue
        fact_id = row.get("fact_id") or row.get("override_id")
        if not isinstance(fact_id, str):
            continue
        claim_type = row.get("claim_type")
        visibility = row.get("visibility")
        if claim_type is not None and claim_type not in _EXACT_CLAIM_TYPES:
            continue
        if visibility is not None and visibility not in _EXACT_VISIBILITY:
            continue
        for sentence in _sentences(row.get("notes")):
            by_sentence.setdefault(_fold(sentence), fact_id)
    spoken = _sentences(narration)
    if not spoken:
        return []
    chosen: list[str] = []
    for sentence in spoken:
        fact_id = by_sentence.get(_fold(sentence))
        if fact_id is None:
            return []
        if fact_id not in chosen:
            chosen.append(fact_id)
    return chosen
