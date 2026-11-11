"""4C.2: the spell preparation window (Wizard from the spellbook, Cleric from the class list).

The window lives in `spellcasting_v1["prepare_window"]` (state version 2): opened at creation, at the end of a finished
Long Rest, or by the version-1 migration. Like the Hit Dice window it is open only at the second it opened and out of
combat; a combat start or the player's "done" closes it for good. The engine never chooses a spell: invalid names are
dropped with a reason, and a list over the limit saves nothing and asks which to leave out.
"""
from __future__ import annotations

import copy
from typing import Any

import spell_scope
from api.dnd_2024_rules import SPELLS_CATALOG


def _state(session: Any, *, write: bool = True) -> dict[str, Any] | None:
    """The version-2 state. A version-1 state still in memory (an old death checkpoint) is upgraded first; a read
    (`write=False`) upgrades a copy and leaves the session untouched."""
    world = session.world_state if write else {**session.world_state,
                                                "spellcasting_v1": copy.deepcopy(session.world_state.get("spellcasting_v1"))}
    spell_scope.upgrade(world, session.character)
    state = world.get("spellcasting_v1")
    spell_scope.validate(state, session.character)
    return state


def _supported(state: Any) -> bool:
    return isinstance(state, dict) and state["class"] in spell_scope.PREPARING


def _open(world: dict[str, Any], state: Any) -> bool:
    window = state.get("prepare_window") if isinstance(state, dict) else None
    return (window is not None and window["opened_second"] == spell_scope.clock_second(world)
            and not world.get("combat", {}).get("active"))


def window_open(session: Any) -> bool:
    return _open(session.world_state, session.world_state.get("spellcasting_v1"))


def open_window(session: Any, reason: str) -> None:
    """A finished Long Rest (never an interrupted one) opens the window for a preparing class."""
    state = _state(session)
    if _supported(state):
        state["prepare_window"] = {"opened_second": spell_scope.clock_second(session.world_state), "reason": reason}


def close_window(session: Any) -> None:
    state = session.world_state.get("spellcasting_v1")
    if isinstance(state, dict) and state.get("prepare_window") is not None:
        state["prepare_window"] = None


def _candidates(state: dict[str, Any], character: dict[str, Any]) -> list[str]:
    if state["class"] == "Wizard":
        return list(state["spellbook"])
    import character_progression
    listed = [s["id"] for s in SPELLS_CATALOG[state["class"]]["spells_level_1"]]
    return listed + sorted(character_progression.extra_spell_ids(character, "prepared") - set(listed))


def view(session: Any) -> dict[str, Any]:
    state = _state(session, write=False)
    if not _supported(state):
        return {"supported": False, "class_name": session.character.get("class"), "open": False, "reason": None,
                "limit": 0, "candidates": [], "prepared": [], "spellbook": None}
    window = state["prepare_window"]
    return {"supported": True, "class_name": state["class"], "open": _open(session.world_state, state),
            "reason": window["reason"] if window else None, "limit": spell_scope.prepare_limit(session.character),
            "candidates": _candidates(state, session.character), "prepared": list(state["prepared"]),
            "spellbook": copy.deepcopy(state["spellbook"])}


def prepare(session: Any, requested: list[str], close: bool = False) -> dict[str, Any]:
    state = _state(session)
    if not _supported(state):
        raise ValueError("Bu sınıf büyü hazırlamaz.")
    if not window_open(session):
        raise ValueError("Büyü hazırlamak için uzun dinlenmeyi yeni bitirmiş olmalısın.")
    character = session.character
    candidates = _candidates(state, character)
    cantrips = {s["id"] for s in SPELLS_CATALOG[state["class"]]["cantrips"]}
    kept: list[str] = []
    dropped: list[dict[str, str]] = []
    for spell in requested:
        if spell in kept:
            reason = "duplicate"
        elif spell in cantrips:
            reason = "cantrip"
        elif spell not in candidates:
            reason = "not_in_spellbook" if state["class"] == "Wizard" else "not_on_class_list"
        else:
            kept.append(spell)
            continue
        dropped.append({"spell_id": spell, "reason": reason})
    limit = spell_scope.prepare_limit(character)
    if len(kept) > limit:
        excess = len(kept) - limit
        return {"status": "too_many", "prepared": kept, "dropped": dropped, "limit": limit, "excess": excess,
                "open": True, "message": f"En çok {limit} büyü hazırlayabilirsin; {excess} fazlası var. Hangisini bırakıyorsun?"}
    candidate = {**copy.deepcopy(state), "prepared": kept}
    if close:
        candidate["prepare_window"] = None
    spell_scope.validate(candidate, character)  # check the whole new state before it is written
    session.world_state["spellcasting_v1"] = candidate
    empty = limit - len(kept)
    message = f"Hazırlanan büyüler: {', '.join(kept) if kept else 'yok'}."
    if empty:
        message += f" {empty} boş yerin kaldı."
    return {"status": "prepared", "prepared": list(kept), "dropped": dropped, "limit": limit, "excess": 0,
            "open": window_open(session), "message": message}
