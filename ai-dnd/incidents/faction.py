"""Faction standing through the existing lore-authority owner.

Rank above the envelope ceiling never writes. Unbound campaigns fail closed.
"""

from __future__ import annotations

from incidents.gate import FACTION_RANKS

ALLOWED_DELTAS = {"associate": 1, "member": 1, "agent": 1}


def apply(lore_state, *, faction_id, rank, source_action_id, turn_index, evidence):
    """Return an updated lore_state or the original state when the write is refused."""
    if lore_state is None:
        return None
    if rank not in ALLOWED_DELTAS:
        return lore_state
    from api.lore_authority.campaign_state import apply_faction_standing
    from api.lore_authority.models import BindingStatus

    if getattr(lore_state, "binding_status", None) is not BindingStatus.BOUND:
        return lore_state
    standing = ALLOWED_DELTAS[rank]
    try:
        return apply_faction_standing(
            lore_state,
            faction_id=faction_id,
            standing=standing,
            known_to_player=True,
            local_presence=True,
            evidence=evidence,
            source_action_id=source_action_id,
            turn_index=turn_index,
        )
    except ValueError:
        return lore_state


def rank_allowed(rank, ceiling):
    if rank not in FACTION_RANKS or ceiling not in FACTION_RANKS:
        return False
    return FACTION_RANKS.index(rank) <= FACTION_RANKS.index(ceiling)
