"""PHB 2024 feat eligibility and ability-score increases (C03).

Facts come from `content/rules/phb2024/feats.json` (category, level, ability minimum, armor training, feature prerequisite,
repeatability, ability increase). This module decides who may take a feat and what ability increase it gives; it is PURE: every
function returns data and never mutates the character. What a feat lets a character DO (its other benefits) is not
implemented here: each delta names those benefits under `effects_pending`, so nothing looks finished that is not.

Character shape read (all optional except class/level/scores): `class`, `level`, the six ability scores as top-level ints,
`feats` and `origin_feats` (names held), `armor_training`, `features`, `saving_throw_proficiencies`, `spellcasting`.
Class armor training, saving throws and the Spellcasting / Fighting Style features come from the existing class resolver;
a feature the resolver does not list is NOT assumed (an explicit `features` entry is needed), so eligibility fails closed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_ORACLE_PATH = Path(__file__).resolve().parents[1] / "content" / "rules" / "phb2024" / "feats.json"
ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
_SOURCE_CATEGORIES = {
    # PHB 2024 p.198 (PDF): a feat choice with no category specified may come from any category, and a class ASI level offers
    # "another feat for which you qualify"; level and feature prerequisites (not a category filter) keep epic boons and Fighting
    # Style feats out of reach. `class_asi` is therefore absent here and means "any category".
    "background": {"origin"}, "species": {"origin"}, "fighting_style": {"fighting_style"},
}
_GRANTED_TRAINING = {"Lightly Armored": {"Light", "Shield"}, "Moderately Armored": {"Medium"}, "Heavily Armored": {"Heavy"}}
_ANY_CATEGORY_SOURCES = {"class_asi", "any"}
_cache: dict[str, Any] = {}


def catalog() -> dict[str, dict[str, Any]]:
    """The oracle's feats, as a copy: callers cannot corrupt later eligibility answers."""
    if "feats" not in _cache:
        _cache["feats"] = json.loads(_ORACLE_PATH.read_text(encoding="utf-8"))["feats"]
    return copy.deepcopy(_cache["feats"])


def _class_definition(character: dict[str, Any]) -> dict[str, Any]:
    from api.dnd_2024_rules import CLASS_DEFINITIONS
    return CLASS_DEFINITIONS.get(character.get("class"), {})


def held_feats(character: dict[str, Any]) -> list[str]:
    held: list[str] = []
    for key in ("feats", "origin_feats"):
        value = character.get(key)
        if isinstance(value, (list, tuple, set)):
            held.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, str):
            held.append(value)  # a bare string is one feat, never a list of characters
    if isinstance(character.get("origin_feat"), str):
        held.append(character["origin_feat"])
    return held


def armor_training(character: dict[str, Any]) -> set[str]:
    training = {"Shield" if item.startswith("Shield") else item for item in _class_definition(character).get("armor_proficiencies", [])}
    training |= {"Shield" if item.startswith("Shield") else item for item in character.get("armor_training", [])}
    for feat in held_feats(character):
        training |= _GRANTED_TRAINING.get(feat, set())
    return training


def has_feature(character: dict[str, Any], feature: str) -> bool:
    if feature in character.get("features", []):
        return True
    definition = _class_definition(character)
    if feature == "Spellcasting or Pact Magic":
        return bool(character.get("spellcasting")) or bool(definition.get("is_spellcaster"))
    if feature == "Spellcasting":  # Pact Magic is a different feature: a Warlock needs an explicit entry
        return character.get("class") != "Warlock" and (bool(character.get("spellcasting")) or bool(definition.get("is_spellcaster")))
    if feature == "Fighting Style":
        return bool(definition.get("fighting_styles"))
    return False


def save_proficiencies(character: dict[str, Any]) -> set[str]:
    return set(_class_definition(character).get("saving_throws", [])) | set(character.get("saving_throw_proficiencies", []))


def feat_status(character: dict[str, Any], feat: str, source: str) -> dict[str, Any]:
    """{"eligible": bool, "reasons": [...]}: every reason a refusal has, never an empty refusal."""
    info = catalog().get(feat)
    if info is None:
        return {"eligible": False, "reasons": ["unknown_feat"]}
    reasons: list[str] = []
    if source not in _ANY_CATEGORY_SOURCES | set(_SOURCE_CATEGORIES):
        return {"eligible": False, "reasons": ["unknown_source"]}
    if source not in _ANY_CATEGORY_SOURCES and info["category"] not in _SOURCE_CATEGORIES[source]:
        reasons.append(f"category_{info['category']}_not_available_from_{source}")
    if info["level"] and int(character.get("level", 0)) < info["level"]:
        reasons.append(f"level_{info['level']}_required")
    minimum = info["ability_min"]
    if minimum and not any(int(character.get(ability, 0)) >= minimum["min"] for ability in minimum["any_of"]):
        reasons.append("ability_" + "_or_".join(minimum["any_of"]) + f"_{minimum['min']}_required")
    needed = info["training"].split(" ")[0] if info["training"] else None  # "Light Armor" -> "Light"; "Shield" stays
    if needed and needed not in armor_training(character):
        reasons.append("shield_training_required" if needed == "Shield" else f"{needed.lower()}_armor_training_required")
    if info["feature"] and not has_feature(character, info["feature"]):
        reasons.append("feature_" + info["feature"].lower().replace(" ", "_") + "_required")
    if feat in held_feats(character) and not info["repeatable"]:
        reasons.append("already_taken")
    return {"eligible": not reasons, "reasons": reasons}


def eligible_feats(character: dict[str, Any], source: str) -> list[str]:
    """Feats the character may take from `source` (background, species, class_asi, fighting_style, any), in catalog order."""
    return [name for name in catalog() if feat_status(character, name, source)["eligible"]]


def _default_source(category: str) -> str:
    return {"origin": "background", "fighting_style": "fighting_style"}.get(category, "class_asi")


def _reject(feat: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "rejected", "feat": feat, "reason": reason, "changes": [], "effects_pending": [], **extra}


def apply_feat_choice(character: dict[str, Any], feat_id: str, choice: dict[str, Any]) -> dict[str, Any]:
    """The delta of taking a feat: its ability increase (clamped at the cap, rejected when a rule forbids it).

    Pure: the character is not changed. `effects_pending` lists the benefits this module does not implement yet.
    """
    info = catalog().get(feat_id)
    if info is None:
        return _reject(feat_id, "unknown_feat")
    status = feat_status(character, feat_id, choice.get("source") or _default_source(info["category"]))
    if not status["eligible"]:
        return _reject(feat_id, "not_eligible", reasons=status["reasons"])
    changes: list[dict[str, Any]] = []
    asi = info["asi"]
    extra: dict[str, Any] = {}
    if feat_id == "Ability Score Improvement":
        increase = choice.get("increase")
        well_formed = isinstance(increase, dict) and all(type(v) is int for v in increase.values())
        values = sorted(increase.values()) if well_formed else []
        # an increase that would pass 20 is refused (not clamped like a feat's own fixed +1): the player chose the amounts
        if not well_formed or set(increase) - set(ABILITIES) or values not in ([2], [1, 1]):
            return _reject(feat_id, "invalid_increase")
        for ability, amount in increase.items():
            before = int(character.get(ability, 0))
            if before + amount > asi["cap"]:
                return _reject(feat_id, "exceeds_cap")
            changes.append({"ability": ability, "from": before, "to": before + amount})
    elif asi:
        allowed = asi["abilities"]
        ability = allowed[0] if len(allowed) == 1 else choice.get("ability")
        if ability not in allowed:
            return _reject(feat_id, "ability_choice_required")
        if asi["kind"] == "save_proficiency_lacking":
            if ability in save_proficiencies(character):
                return _reject(feat_id, "already_proficient_in_that_save")
            extra["grants_save_proficiency"] = [ability]
        before = int(character.get(ability, 0))
        after = min(before + asi["amount"], asi["cap"])
        if after != before:
            changes.append({"ability": ability, "from": before, "to": after})
    return {"status": "applied", "feat": feat_id, "changes": changes, "effects_pending": list(info["benefits"]), **extra}
