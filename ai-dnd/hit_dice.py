"""K07: Hit Point Dice (PHB 2024 glossary PDF 367, Short Rest PDF 372, Long Rest PDF 369; values only, no book text).

One die per APPLIED class level (`character_progression.applied_level`): a level that XP granted but whose class choices were not
applied gives no die. The die size is the class Hit Die. Single class per character (multiclass is C07).
`character["hit_dice"] = {"spent": n, "window_second": s | None}` is additive: a save without it means no die is spent.
Short Rest opens a spending window at the campaign second it finished; each `spend` is a separate request, so the player decides
after every roll. The window closes when the clock moves, combat is active, or Hit Points differ from what the rest / last spend left. Long Rest regains ALL spent dice.
"""
from __future__ import annotations

from typing import Any

import character_progression
from api.dnd_2024_rules import CLASS_DEFINITIONS

_KEYS = {"spent", "window_second", "hp"}


def die_size(character: dict[str, Any]) -> int | None:
    return CLASS_DEFINITIONS.get(character.get("class"), {}).get("hit_die")


def total(character: dict[str, Any]) -> int:
    return character_progression.applied_level(character) if die_size(character) else 0


def _state(character: dict[str, Any]) -> dict[str, Any]:
    return character.get("hit_dice") or {"spent": 0, "window_second": None, "hp": None}


def spent(character: dict[str, Any]) -> int:
    return _state(character)["spent"]


def remaining(character: dict[str, Any]) -> int:
    return max(0, total(character) - spent(character))


def _now(session: Any) -> int:
    return session.world_state["campaign_time"]["elapsed_seconds"]


def window_open(session: Any) -> bool:
    state = _state(session.character)
    # Open only at the second the rest finished, out of combat, and while Hit Points are exactly what the rest / last spend left:
    # any damage or other healing since then ends the window, even when the clock did not move.
    return (state["window_second"] is not None and state["window_second"] == _now(session)
            and state["hp"] == session.character["current_hp"] and not session.world_state.get("combat", {}).get("active"))


def summary(session: Any) -> dict[str, Any]:
    character = session.character
    return {"die": die_size(character), "remaining": remaining(character), "total": total(character),
            "can_spend": window_open(session) and remaining(character) > 0}


def open_window(session: Any) -> dict[str, Any]:
    """Called when a Short Rest has finished (never for an interrupted one)."""
    session.character["hit_dice"] = {"spent": spent(session.character), "window_second": _now(session),
                                     "hp": session.character["current_hp"]}
    return summary(session)


def restore_all(character: dict[str, Any]) -> None:
    character["hit_dice"] = {"spent": 0, "window_second": None, "hp": None}


def spend(session: Any, heal: Any) -> dict[str, Any]:
    """Spend one die after a finished Short Rest: roll + Constitution modifier (minimum 1), capped by the Hit Point maximum."""
    character = session.character
    if not window_open(session):
        raise ValueError("Zar harcamak için kısa dinlenmeyi yeni bitirmiş olmalısın.")
    if remaining(character) <= 0:
        raise ValueError("Harcanabilecek Hit Point Dice kalmadı.")
    if character["current_hp"] >= character["max_hp"]:
        raise ValueError("Can puanın zaten en yüksek düzeyde.")
    roll = session.rng.randint(1, die_size(character))
    modifier = character.get("modifiers", {}).get("constitution", character.get("constitution_mod", 0))
    healing = min(max(1, roll + modifier), character["max_hp"] - character["current_hp"])
    heal(healing)
    character["hit_dice"] = {"spent": spent(character) + 1, "window_second": _state(character)["window_second"],
                             "hp": character["current_hp"]}
    return {"dice": [roll], "healing": healing, "current_hp": character["current_hp"],
            "remaining": remaining(character), "hit_dice": summary(session)}


def validate_saved(player: dict[str, Any]) -> None:
    if "hit_dice" not in player:
        return
    state = player["hit_dice"]
    if not isinstance(state, dict) or set(state) != _KEYS:
        raise ValueError("Kayıt Hit Point Dice alanı geçersiz.")
    count, window, hp = state["spent"], state["window_second"], state["hp"]
    if type(count) is not int or not 0 <= count <= total(player):
        raise ValueError("Kayıt harcanmış Hit Point Dice sayısı geçersiz.")
    if window is not None and (type(window) is not int or window < 0):
        raise ValueError("Kayıt Hit Point Dice penceresi geçersiz.")
    if (window is None) != (hp is None) or (hp is not None and (type(hp) is not int or hp < 0)):
        raise ValueError("Kayıt Hit Point Dice penceresi geçersiz.")
