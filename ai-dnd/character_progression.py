"""C06 (first slice): table-driven class progression, Sorcerer level 1 -> 2, through preview / apply / create / save-load.

Facts come from `content/rules/phb2024/classes/<class>.json` (read from the book's page scans). `progression_level` is the level
whose choices were applied; a level granted by XP above it is a PENDING level-up: the character keeps its previous resources
(`capacity` follows `progression_level`, never `level`) until `apply_level_choices` applies the choices exactly once.
Only levels whose slots are all level 1 are supported (the spell/save validators accept slot level 1 only); anything above is a
BLOCKED preview with a reason, never a faked level. Every delta lists effects that are not implemented under `effects_pending`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from api.dnd_2024_rules import proficiency_bonus_for_level

_CLASS_DIR = Path(__file__).resolve().parents[1] / "content" / "rules" / "phb2024" / "classes"
_cache: dict[str, dict[str, Any] | None] = {}
MAX_SUPPORTED_LEVEL = 2  # highest level whose slots are all level 1 (Sorcerer table)


def table(class_name: Any) -> dict[str, Any] | None:
    if not isinstance(class_name, str) or not class_name.isalpha():
        return None
    if class_name not in _cache:
        path = _CLASS_DIR / f"{class_name.lower()}.json"
        _cache[class_name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return _cache[class_name]


def applied_level(character: dict[str, Any]) -> int:
    value = character.get("progression_level", 1)
    level = character.get("level", 1)
    if type(value) is not int or value < 1:
        value = 1
    return min(value, level) if type(level) is int and level >= 1 else value


def has_table(character: dict[str, Any]) -> bool:
    return table(character.get("class")) is not None


def row(character: dict[str, Any], level: int) -> dict[str, Any]:
    return table(character["class"])["levels"][str(level)]


def capacity(character: dict[str, Any]) -> dict[str, Any] | None:
    """Spell resources at the APPLIED level for a class with a table; None when the class has no table (old level-1 rule)."""
    if not has_table(character):
        return None
    level = applied_level(character)
    if level > MAX_SUPPORTED_LEVEL:
        return None
    data = row(character, level)
    return {"cantrips": data["cantrips"], "prepared_spells": data["prepared_spells"], "slots": copy.deepcopy(data["slots"]),
            "sorcery_points": data["sorcery_points"]}


def slot_capacity(character: dict[str, Any]) -> dict[str, int] | None:
    cap = capacity(character)
    return cap["slots"] if cap else None


def _preview(status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def preview_level_up(session: Any, target_level: Any) -> dict[str, Any]:
    """What reaching `target_level` needs and gives. Pure: nothing is changed."""
    character = session.character
    if type(target_level) is not int or not 1 <= target_level <= 20:
        return _preview("blocked", "invalid_target_level")
    if not has_table(character):
        return _preview("blocked", "class_table_not_available")
    current = applied_level(character)
    if target_level <= current:
        return _preview("blocked", "target_not_above_applied_level", from_level=current, to_level=target_level)
    if target_level > MAX_SUPPORTED_LEVEL:
        return _preview("blocked", "slot_levels_above_1_not_supported", from_level=current, to_level=target_level)
    rows = [row(character, level) for level in range(current + 1, target_level + 1)]
    features = [feature for data in rows for feature in data["features"]]
    prior, goal = row(character, current), rows[-1]
    metamagic = sum(table(character["class"]).get("metamagic_choice_counts", {}).get(str(level), 0)
                    for level in range(current + 1, target_level + 1))
    import xp
    required = {"prepared_spells": goal["prepared_spells"] - prior["prepared_spells"]}
    if metamagic:
        required["metamagic"] = metamagic
    pending = []
    if "Font of Magic" in features:
        pending.append("Font of Magic: Sorcery Points are not tracked yet")
    if "Metamagic" in features:
        pending.append("Metamagic: the chosen options are stored, their effects are not implemented")
    return _preview(
        "ready", None, class_name=character["class"], from_level=current, to_level=target_level, features=features,
        choices_required=required,
        capacity={"cantrips": goal["cantrips"], "prepared_spells": goal["prepared_spells"], "slots": copy.deepcopy(goal["slots"]),
                  "sorcery_points": goal["sorcery_points"]},
        hit_points={"gain": xp.hit_point_gain(character) * (target_level - current), "already_applied": character["level"] >= target_level},
        effects_pending=pending,
    )


def validate_saved(player: dict[str, Any], world: dict[str, Any]) -> None:
    """Refuse a save that claims an applied level whose choices are missing or whose slice is unsupported."""
    if "progression_level" not in player and "metamagic" not in player:
        return
    if not has_table(player):
        if player.get("progression_level", 1) != 1 or player.get("metamagic"):
            raise ValueError("Kayıt ilerleme tablosu olmayan sınıf için ilerleme iddia ediyor.")
        return
    applied = applied_level(player)
    if player.get("progression_level", 1) > MAX_SUPPORTED_LEVEL:
        raise ValueError("Kayıt desteklenmeyen ilerleme seviyesi iddia ediyor.")
    if applied >= 2:
        state = world.get("spellcasting_v1")
        data = row(player, applied)
        owed = sum(table(player["class"]).get("metamagic_choice_counts", {}).get(str(n), 0) for n in range(2, applied + 1))
        if (not isinstance(state, dict) or len(state.get("prepared", [])) != data["prepared_spells"]
                or len(player.get("metamagic", [])) != owed):
            raise ValueError("Kayıt uygulanmamış seviye seçimleri iddia ediyor.")


def _reject(reason: str) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason, "changes": [], "effects_pending": []}


def _check_choices(session: Any, preview: dict[str, Any], choices: Any) -> str | None:
    from api.dnd_2024_rules import SPELLS_CATALOG
    if not isinstance(choices, dict):
        return "choices_required"
    required = preview["choices_required"]
    if set(choices) - set(required):
        return "unsupported_choice"
    state = session.world_state["spellcasting_v1"]
    picked = choices.get("prepared_spells", [])
    allowed = {s["id"] for s in SPELLS_CATALOG.get(session.character["class"], {}).get("spells_level_1", [])}
    if not isinstance(picked, list) or len(picked) != required["prepared_spells"]:
        return "prepared_spells_count"
    if (any(not isinstance(s, str) for s in picked) or len(set(picked)) != len(picked) or not set(picked) <= allowed
            or set(picked) & set(state["prepared"])):
        return "prepared_spells_invalid"
    if "metamagic" in required:
        options = table(session.character["class"])["metamagic_options"]
        known = session.character.get("metamagic", [])
        picks = choices.get("metamagic", [])
        if not isinstance(picks, list) or len(picks) != required["metamagic"]:
            return "metamagic_count"
        if any(not isinstance(m, str) for m in picks) or len(set(picks)) != len(picks) or not set(picks) <= set(options) \
                or set(picks) & set(known):
            return "metamagic_invalid"
    return None


def apply_level_choices(session: Any, preview: Any, choices: Any) -> dict[str, Any]:
    """Apply one previewed level-up atomically. A rejection changes nothing; applying the same preview twice is refused."""
    if not isinstance(preview, dict) or preview.get("status") != "ready":
        return _reject("preview_not_ready")
    character = session.character
    if type(preview.get("to_level")) is int and preview["to_level"] <= applied_level(character):
        return _reject("already_applied")
    current = preview_level_up(session, preview.get("to_level"))
    if current != preview:
        return _reject("preview_not_current")
    problem = _check_choices(session, preview, choices)
    if problem:
        return _reject(problem)
    import spell_scope
    new_character = copy.deepcopy(character)
    state = copy.deepcopy(session.world_state["spellcasting_v1"])  # only the spell state is replaced, not the whole world
    old_cap, new_cap = capacity(character), preview["capacity"]
    to_level = preview["to_level"]
    state["prepared"] = [*state["prepared"], *choices["prepared_spells"]]
    state["slots"] = {k: state["slots"].get(k, 0) + n - old_cap["slots"].get(k, 0) for k, n in new_cap["slots"].items()}
    changes = [{"kind": "prepared_spells", "added": list(choices["prepared_spells"])},
               {"kind": "spell_slots", "maximum": copy.deepcopy(new_cap["slots"])}]
    if not preview["hit_points"]["already_applied"]:
        gain = preview["hit_points"]["gain"]
        new_character["max_hp"] += gain
        new_character["current_hp"] += gain
        changes.append({"kind": "hit_points", "gain": gain})
    new_character["level"] = max(new_character["level"], to_level)
    new_character["progression_level"] = to_level
    new_character["proficiency_bonus"] = proficiency_bonus_for_level(new_character["level"])
    new_character["spells"] = list(state["prepared"])
    new_character["spell_slots_remaining"] = copy.deepcopy(state["slots"])
    if "metamagic" in choices:
        new_character["metamagic"] = [*new_character.get("metamagic", []), *choices["metamagic"]]
        changes.append({"kind": "metamagic", "added": list(choices["metamagic"])})
    try:
        spell_scope.validate(state, new_character)
    except ValueError:
        return _reject("resulting_state_invalid")
    character.clear()
    character.update(new_character)
    session.world_state["spellcasting_v1"] = state
    changes.append({"kind": "level", "from": preview["from_level"], "to": to_level})
    return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}


def create_at_level(session: Any, spec: dict[str, Any], level: int = 1, level_choices: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a level-1 character with the real creation path, then reach `level` through the same preview/apply steps.

    Everything is checked before the character is created, so an unsupported level or missing choices leaves no half-made level.
    """
    from api.character_creation import configure_character
    if type(level) is not int or not 1 <= level <= 20:
        raise ValueError("invalid_target_level")
    if level > 1:
        if table(spec.get("character_class")) is None:
            raise ValueError("class_table_not_available")
        if level > MAX_SUPPORTED_LEVEL:
            raise ValueError("slot_levels_above_1_not_supported")
        missing = [str(n) for n in range(2, level + 1) if not isinstance((level_choices or {}).get(str(n)), dict)]
        if missing:
            raise ValueError(f"choices_required_for_levels_{','.join(missing)}")
    configure_character(session, mode="custom", **spec)
    for step in range(2, level + 1):
        delta = apply_level_choices(session, preview_level_up(session, step), level_choices[str(step)])
        if delta["status"] != "applied":
            raise ValueError(delta["reason"])
    session.character.setdefault("progression_level", 1)
    return session.character
