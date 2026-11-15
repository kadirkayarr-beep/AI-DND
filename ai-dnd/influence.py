"""Influence (guide 4.5, ZAR_KURALLARI_DND2024): will this person do what is asked, and how hard is it to talk them round.

D-169, kept to the one ask D-166 needs (Kadir kararı 2026-11-15): the player asking a person for coin. The guide first
sorts the target: willing helps without a roll, unwilling refuses whatever the roll, hesitant can be swayed by a check
against max(15, the target's Intelligence SCORE). Attitude is apart from willingness: friendly rolls with advantage,
hostile with disadvantage. A failed try by the same means waits 24 hours (the GM's time; here every try waits).

For coin the engine also sets the sum: a share of the person's purse by attitude, under a ceiling. Nobody hands a
stranger coin unasked-for without a roll, so a coin ask is never "willing" here.
"""

from __future__ import annotations

from typing import Any

import relationships
from incidents import state as clock_state

DAY_SECONDS = 86400
COIN_ASKS = "coin_asks"
# Percent of the purse and the most a person hands over, in copper, by attitude.
_COIN_SHARE = {"friendly": (20, 50), "indifferent": (10, 10), "hostile": (0, 0)}


def attitude(world: dict[str, Any], npc_id: Any) -> str:
    """'friendly', 'indifferent' or 'hostile', read from the relationship score."""
    score = relationships.score(world, npc_id)
    return "friendly" if score >= 1 else "hostile" if score <= -1 else "indifferent"


def dc(npc: Any) -> int:
    """max(15, Intelligence score); a person with no score written has the common 10."""
    score = npc.get("intelligence") if isinstance(npc, dict) else None
    return max(15, score if type(score) is int else 10)


def gift_cap_cp(held: Any, mood: str) -> int:
    """The most this purse hands the player, by attitude: a share, never above the ceiling."""
    percent, ceiling = _COIN_SHARE[mood]
    return min(held * percent // 100, ceiling) if type(held) is int and held > 0 else 0


def coin_willingness(world: dict[str, Any], npc_id: Any, cap: int) -> str:
    """'hesitant' (a roll decides) or 'unwilling' (nothing to spare, or asked within the day)."""
    asked = ((world.get("flags") or {}).get(COIN_ASKS) or {}).get(str(npc_id))
    if cap <= 0 or (type(asked) is int and clock_state.clock(world) - asked < DAY_SECONDS):
        return "unwilling"
    return "hesitant"


def note_coin_ask(world: dict[str, Any], npc_id: Any) -> None:
    """A roll was made: the next try at this person waits a day."""
    world.setdefault("flags", {}).setdefault(COIN_ASKS, {})[str(npc_id)] = clock_state.clock(world)
