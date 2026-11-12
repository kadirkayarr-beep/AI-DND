"""4C.4b: the player's Concentration (PHB 2024 glossary, PDF 362) and the one Concentration spell of the first cut, Bless
(PDF 246).

State: `world_state["spell_concentration_v1"]` = None or {"spell_id", "combat_id", "started_round", "slot_level",
"targets"}. It is a world-state key of its own, not part of `spellcasting_v1`: a Paladin keeps a version-1
spell state byte for byte and has Bless too. First-cut spells are cast only in an active fight, so Concentration belongs
to that fight and ends with it.

Ends (source): another Concentration spell is cast; the caster is Incapacitated (the engine's own reading,
`combat_lifecycle.INCAPACITATED`: Unconscious at 0 HP and every condition that includes Incapacitated) or dies; a failed
Constitution save after taking damage, DC max(10, half the damage, rounded down), at most 30; the caster drops it at will
(no action). Engine readings (ledger Rulings, UNVERIFIED by a page): 1 minute = 10 of the fight's rounds (the engine's
round is 6 campaign seconds); one save per damage instance; the fight's end ends it.

Bless: each target adds 1d4 (engine-rolled) to its attack rolls and saving throws, never to ability checks.
"""
from __future__ import annotations

import copy
from typing import Any

KEY = "spell_concentration_v1"
DURATION_ROUNDS = {"Bless": 10}  # "Concentration, up to 1 minute": 10 rounds of 6 s (UNVERIFIED in rounds, ledger Ruling)
CONCENTRATION_SPELLS = frozenset(DURATION_ROUNDS)
_FIELDS = {"spell_id", "combat_id", "started_round", "slot_level", "targets"}


def save_dc(damage: int) -> int:
    """DC 10 or half the damage taken (round down), whichever is higher, to a maximum of 30."""
    return min(30, max(10, damage // 2))


def bless_max_targets(slot_level: int) -> int:
    """Up to three creatures, one more for each slot level above 1."""
    return 3 + (slot_level - 1)


def current(world: dict[str, Any]) -> dict[str, Any] | None:
    held = world.get(KEY)
    return held if isinstance(held, dict) else None


def validate_saved(world: dict[str, Any], character: dict[str, Any]) -> None:
    if KEY not in world or world[KEY] is None:
        return
    held = world[KEY]
    if (not isinstance(held, dict) or set(held) != _FIELDS or held["spell_id"] not in CONCENTRATION_SPELLS
            or not isinstance(held["combat_id"], str) or not held["combat_id"]
            or type(held["started_round"]) is not int or held["started_round"] < 1
            or type(held["slot_level"]) is not int or not 1 <= held["slot_level"] <= 9
            or not isinstance(held["targets"], list) or held["targets"] != ["player"]):
        raise ValueError("Invalid saved spell concentration.")
    # A record whose fight is over is stale, not invalid: it never holds (`holds` reads the fight) and the next cast
    # replaces it. Refusing such a save would lock the campaign (the D-001 class), so it loads.


def _incapacitated(session: Any) -> bool:
    import combat_lifecycle
    return combat_lifecycle.player_incapacitated(session.character, session.world_state)


def _expired(session: Any, held: dict[str, Any]) -> str | None:
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or combat.get("combat_id") != held["combat_id"]:
        return "combat_ended"
    if _incapacitated(session):
        return "incapacitated"
    if combat.get("round", 1) >= held["started_round"] + DURATION_ROUNDS[held["spell_id"]]:
        return "duration_ended"
    return None


def holds(session: Any) -> dict[str, Any] | None:
    """Read only: the held Concentration if it still holds right now."""
    held = current(session.world_state)
    return held if held is not None and _expired(session, held) is None else None


def end(session: Any, reason: str) -> dict[str, Any] | None:
    """End the held Concentration (if any). Returns {"spell_id", "reason"}."""
    held = current(session.world_state)
    if held is None:
        return None
    session.world_state[KEY] = None
    return {"spell_id": held["spell_id"], "reason": reason}


def settle(session: Any) -> dict[str, Any] | None:
    """End a Concentration that no longer holds (turn starts, fight end). Returns what ended, or None."""
    held = current(session.world_state)
    if held is None:
        return None
    reason = _expired(session, held)
    return end(session, reason) if reason else None


def start(session: Any, spell_id: str, slot_level: int, targets: list[str]) -> dict[str, Any] | None:
    """Begin Concentration on a cast spell; the one held before ends. Returns what ended, or None."""
    ended = end(session, "new_concentration_spell")
    combat = session.world_state["combat"]
    session.world_state[KEY] = {"spell_id": spell_id, "combat_id": combat["combat_id"], "started_round": combat["round"],
                                "slot_level": slot_level, "targets": list(targets)}
    return ended


def after_damage(session: Any, damage: int) -> dict[str, Any] | None:
    """The player took this much damage (one instance): end at 0 HP or death, else a Constitution save.

    Returns {"spell_id", "dc", "roll", "total", "kept"} for a save, {"spell_id", "kept": False, "reason"} when the damage
    ended it outright, or None when nothing was held or no damage was taken."""
    held = current(session.world_state)
    if held is None or type(damage) is not int or damage <= 0:
        return None
    reason = _expired(session, held)
    if reason:
        end(session, reason)
        return {"spell_id": held["spell_id"], "kept": False, "reason": reason}
    import weapon_attack
    dc = save_dc(damage)
    result = weapon_attack.save(session, "player", ["constitution"], dc)
    kept = result["outcome"] == "SUCCESS"
    if not kept:
        end(session, "failed_save")
    check = {"spell_id": held["spell_id"], "dc": dc, "roll": result.get("selected_roll"), "total": result.get("total"),
             "kept": kept}
    if result.get("bless_roll") is not None:
        check["bless_roll"] = result["bless_roll"]
    return check


def blessed(session: Any, actor: str) -> bool:
    held = holds(session)
    return held is not None and held["spell_id"] == "Bless" and actor in held["targets"]


def bless_roll(session: Any, actor: str) -> int | None:
    """The Bless d4 for one attack roll or saving throw of a blessed creature (engine-rolled), or None."""
    if not blessed(session, actor):
        return None
    return session.rng.randint(1, 4)


def projection(world: dict[str, Any]) -> dict[str, Any] | None:
    held = current(world)
    return copy.deepcopy(held) if held is not None else None
