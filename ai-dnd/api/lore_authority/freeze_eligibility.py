"""Digest-bound disclosure for freeze-candidate IDs.

An identifier is governed only when it is an exact member of the pinned
freeze corpus. A WD22/BG22/FR22 prefix is not an accept or reject rule.
IDs outside the corpus keep the legacy retrieval policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .freeze_admission import TrustedBatch, admit_public_batch, load_pinned_snapshot
from .models import SourceTier


@dataclass(frozen=True)
class FreezeCorpus:
    available: bool
    all_ids: frozenset[str]
    public_claims: dict[str, str]
    page_verified_ids: frozenset[str]


_CORPUS: FreezeCorpus | None = None
_BATCH: TrustedBatch | None = None


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


def trusted_batch() -> TrustedBatch:
    global _BATCH
    if _BATCH is None:
        _BATCH = admit_public_batch()
    return _BATCH


def explicit_scope_required(fact_id: str) -> bool:
    """Candidate records may not become current by omitting temporal scope."""
    corpus = load_corpus()
    return corpus.available and fact_id in corpus.all_ids


def disclosure_allowed(fact: object) -> bool:
    """Exact payload plus classification. Test fixtures can exercise the contract.

    Staged official-tier facts stay out of narrator context until a page
    verification id is added. That set is empty in this build.
    """
    corpus = load_corpus()
    fact_id = getattr(fact, "fact_id", None)
    if not isinstance(fact_id, str) or not corpus.available or fact_id not in corpus.all_ids:
        return True
    permitted = corpus.public_claims.get(fact_id)
    if permitted is None or getattr(fact, "object_id_or_value", None) != permitted:
        return False
    tier = getattr(fact, "authority_tier", None)
    if fact_id in corpus.page_verified_ids:
        return True
    return tier is SourceTier.TEST_FIXTURE


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
