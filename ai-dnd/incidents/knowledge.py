"""Incident knowledge writes through the Phase 7 facade store.

Hidden facts stay generator-only until a Python check reveals them.
Rumors are player_knowledge strings, not campaign history.
"""

from __future__ import annotations

from incidents import awareness


def rumor(world, record, text):
    """Record a heard rumor. It is evidence, not a quest and not canon history."""
    if not isinstance(text, str) or not text.strip() or len(text) > 400:
        return False
    fact_id = "rumor"
    record["details"]["facts"].setdefault(fact_id, text.strip())
    return awareness.reveal(
        world, record, fact_id,
        evidence={"kind": "introduction", "npc_id": "scene"},
    )
