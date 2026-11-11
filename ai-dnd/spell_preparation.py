"""4C.2: the spell preparation window (Wizard from the spellbook, Cleric from the class list).

The window lives in `spellcasting_v1["prepare_window"]` (state version 2): opened at creation, at the end of a finished
Long Rest, by the version-1 migration, or by a Wizard/Cleric level step (4C.3). Like the Hit Dice window it is open only at the second it opened and out of
combat; a combat start or the player's "done" closes it for good. The engine never chooses a spell: invalid names are
dropped with a reason, and a list over the limit saves nothing and asks which to leave out.
"""
from __future__ import annotations

import copy
from typing import Any

import spell_scope
from api.dnd_2024_rules import SPELLS_CATALOG


class PrepareRefused(ValueError):
    """A refusal with its own public code (the route answers 409 with it); nothing was changed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _state(session: Any, *, write: bool = True) -> dict[str, Any] | None:
    """The version-2 state. A version-1 state still in memory (an old death checkpoint) is upgraded first; a read
    (`write=False`) upgrades a copy and leaves the session untouched."""
    world = session.world_state if write else {**session.world_state,
                                                "spellcasting_v1": copy.deepcopy(session.world_state.get("spellcasting_v1"))}
    spell_scope.upgrade(world, session.character)
    state = world.get("spellcasting_v1")
    spell_scope.validate(state, session.character)
    return state


# A creation, migration or level-up window waits for the player's first list (fix round 1; 4C.3 level steps): it ignores
# the clock and a fight, and ends with the first saved list, `close: true` or a finished Long Rest. A Long Rest window keeps
# the approved rule.
STANDING = frozenset({"creation", "migration", "level_up"})


def _blocked(state: Any) -> str | None:
    """Why this caster cannot use the window: not a preparing class, or a Wizard whose save carries no spellbook."""
    if not isinstance(state, dict) or state["class"] not in spell_scope.PREPARING:
        return "not_preparing_class"
    if state["version"] == 1:  # only a Wizard with no saved creation spells stays version 1 (spell_scope.upgrade)
        return "spellbook_missing"
    return None


def _supported(state: Any) -> bool:
    return _blocked(state) is None


def _open(world: dict[str, Any], state: Any) -> bool:
    window = state.get("prepare_window") if isinstance(state, dict) else None
    if window is None or world.get("combat", {}).get("active"):
        return False
    return window["reason"] in STANDING or window["opened_second"] == spell_scope.clock_second(world)


def window_open(session: Any) -> bool:
    return _open(session.world_state, session.world_state.get("spellcasting_v1"))


def open_window(session: Any, reason: str) -> None:
    """A finished Long Rest (never an interrupted one) opens the window for a preparing class."""
    state = _state(session)
    if _supported(state):
        state["prepare_window"] = {"opened_second": spell_scope.clock_second(session.world_state), "reason": reason}


def close_window(session: Any) -> None:
    """Combat start: a Long Rest window ends for good; a creation/migration window waits for the first list."""
    state = session.world_state.get("spellcasting_v1")
    window = state.get("prepare_window") if isinstance(state, dict) else None
    if window is not None and window["reason"] not in STANDING:
        state["prepare_window"] = None


def _candidates(state: dict[str, Any], character: dict[str, Any]) -> list[str]:
    if state["class"] == "Wizard":
        return list(state["spellbook"])
    import character_progression
    listed = [s["id"] for s in SPELLS_CATALOG[state["class"]]["spells_level_1"]]
    return listed + sorted(character_progression.extra_spell_ids(character, "prepared") - set(listed))


def view(session: Any) -> dict[str, Any]:
    state = _state(session, write=False)
    blocked = _blocked(state)
    if blocked:
        return {"supported": False, "blocked_reason": blocked, "class_name": session.character.get("class"),
                "open": False, "reason": None, "limit": 0, "candidates": [], "prepared": [], "spellbook": None}
    window = state["prepare_window"]
    return {"supported": True, "blocked_reason": None, "class_name": state["class"], "open": _open(session.world_state, state),
            "reason": window["reason"] if window else None, "limit": spell_scope.prepare_limit(session.character),
            "candidates": _candidates(state, session.character), "prepared": list(state["prepared"]),
            "spellbook": copy.deepcopy(state["spellbook"])}


def prepare(session: Any, requested: list[str] | None, close: bool = False) -> dict[str, Any]:
    """`requested=None` keeps today's list (a plain "done"); an explicit [] is an explicit empty list."""
    state = _state(session)
    blocked = _blocked(state)
    if blocked == "spellbook_missing":
        raise ValueError("Büyü kitabın kayıtta yok; bu eski kayıt büyü seçimlerini taşımıyor.")
    if blocked:
        raise ValueError("Bu sınıf büyü hazırlamaz.")
    if not window_open(session):
        raise ValueError("Büyü hazırlamak için uzun dinlenmeyi yeni bitirmiş ya da yeni bir seviyeye geçmiş olmalısın.")
    character = session.character
    candidates = _candidates(state, character)
    cantrips = {s["id"] for s in SPELLS_CATALOG[state["class"]]["cantrips"]}
    kept: list[str] = []
    dropped: list[dict[str, str]] = []
    for spell in (list(state["prepared"]) if requested is None else requested):
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
    if requested is not None and state["prepare_window"]["reason"] == "level_up":
        # A level step only grows the list (PHB: "choose additional spells"); replacing spells needs a finished Long Rest.
        removed = [spell for spell in state["prepared"] if spell not in kept]
        if removed:
            raise PrepareRefused("prepare_level_up_additive_only",
                                 "Yeni seviyede yalnız büyü ekleyebilirsin; hazırladığın büyüleri değiştirmek için uzun dinlenme "
                                 f"gerekir. Listede kalması gereken: {', '.join(removed)}.")
    limit = spell_scope.prepare_limit(character)
    if len(kept) > limit:
        excess = len(kept) - limit
        return {"status": "too_many", "prepared": kept, "dropped": dropped, "limit": limit, "excess": excess,
                "open": True, "message": f"En çok {limit} büyü hazırlayabilirsin; {excess} fazlası var. Hangisini bırakıyorsun?"}
    candidate = {**copy.deepcopy(state), "prepared": kept}
    if close or state["prepare_window"]["reason"] in STANDING:
        candidate["prepare_window"] = None  # the first saved list ends a creation/migration window
    spell_scope.validate(candidate, character)  # check the whole new state before it is written
    session.world_state["spellcasting_v1"] = candidate
    empty = limit - len(kept)
    message = f"Hazırlanan büyüler: {', '.join(kept) if kept else 'yok'}."
    if empty:
        message += f" {empty} boş yerin kaldı."
    return {"status": "prepared", "prepared": list(kept), "dropped": dropped, "limit": limit, "excess": 0,
            "open": window_open(session), "message": message}
