"""Digest-bound disclosure for freeze-candidate IDs.

An identifier is governed only when it is an exact member of the pinned
freeze corpus. A WD22/BG22/FR22 prefix is not an accept or reject rule.
IDs outside the corpus keep the legacy retrieval policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .freeze_admission import load_pinned_snapshot


@dataclass(frozen=True)
class FreezeCorpus:
    available: bool
    all_ids: frozenset[str]
    public_claims: dict[str, str]
    page_verified_ids: frozenset[str]


_CORPUS: FreezeCorpus | None = None


def load_corpus() -> FreezeCorpus:
    global _CORPUS
    if _CORPUS is not None:
        return _CORPUS
    snapshot = load_pinned_snapshot()
    if snapshot.evidence.integrity_errors:
        _CORPUS = FreezeCorpus(False, frozenset(), {}, frozenset())
        return _CORPUS
    _CORPUS = FreezeCorpus(
        True,
        frozenset(snapshot.evidence.records),
        dict(snapshot.permitted_claims),
        frozenset(),
    )
    return _CORPUS


def discovery_allowed(fact_id: str) -> bool:
    """Unapproved freeze records cannot become persistent player knowledge."""
    corpus = load_corpus()
    if not corpus.available:
        return True
    return fact_id not in corpus.all_ids


def player_surface_block_reason(fact_id: str) -> str | None:
    """English canonical claims are not a Turkish player surface."""
    corpus = load_corpus()
    if not corpus.available or fact_id not in corpus.all_ids:
        return None
    if fact_id not in corpus.page_verified_ids:
        return "turkish_rendering_missing"
    return "reviewed_turkish_rendering_missing"
