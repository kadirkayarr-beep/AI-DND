"""C06 progression state: selected Sorcerer 1–5 and earned Barbarian 1→5 (creation at starting level 1–5 for both), with pending class effects.

Facts come from `content/rules/phb2024/classes/<class>.json` (read from the book's page scans). `progression_level` is the level
whose choices were applied; a level granted by XP above it is a PENDING level-up: the character keeps its previous resources
(`capacity` follows `progression_level`, never `level`) until `apply_level_choices` applies the choices exactly once.
Applied progression supports selected non-DEX ordinary ASI Sorcerer4 followed by selected5 / selected Berserker3→4→5 (level 5 has no choices); other paths are BLOCKED.
Subclass choice storage is not implementation of subclass features or full playability. Every delta lists effects that are not implemented under `effects_pending`.
Class-specific rules live in `class_progression/<class>.py` behind a registry; this module keeps the shared flow and re-exports
the class names other modules and tests read from here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from api.dnd_2024_rules import proficiency_bonus_for_level
from class_progression import for_class, registered
from class_progression.barbarian import (  # noqa: F401
    barbarian_level_five_applied,
    EXTRA_ATTACK_ATTACKS,
    FAST_MOVEMENT_FT,
)

_CLASS_DIR = Path(__file__).resolve().parents[1] / "content" / "rules" / "phb2024" / "classes"
_cache: dict[str, dict[str, Any] | None] = {}
MAX_SUPPORTED_LEVEL = 5  # progression state only; pending class/spell effects are not playability acceptance


def _supported_level(class_name: Any) -> int:
    return min(MAX_SUPPORTED_LEVEL, for_class(class_name).supported_level)


def _noncaster_state_valid(character: dict[str, Any], world: dict[str, Any]) -> bool:
    return ("spellcasting_v1" not in world and "sorcery_points_v1" not in world
            and ("subclass_id" not in character
                 or (type(character.get("progression_level")) is int
                     and character["progression_level"] in (3, 4, 5)
                     and type(character.get("level")) is int
                     and character["progression_level"] <= character["level"] <= 20
                     and character.get("subclass_id") == "berserker"))
            and ("metamagic" not in character
                 or (type(character["metamagic"]) is list and not character["metamagic"])))


BARBARIAN_SKILLS = ("Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival")


def _validate_primal_knowledge(character):
    """One selected feature choice; retained baseline is not inferred origin."""
    record = character.get("primal_knowledge_choice")
    selected = (character.get("class") == "Barbarian"
                and type(character.get("progression_level")) is int
                and character["progression_level"] in (3, 4, 5))
    if not selected:
        if "primal_knowledge_choice" in character:
            raise ValueError("Unearned Primal Knowledge choice.")
        return
    from api.dnd_2024_rules import SKILL_DEFINITIONS
    prior = record.get("prior_proficient_skills") if type(record) is dict else None
    skill = record.get("skill") if type(record) is dict else None
    if (type(record) is not dict or set(record) != {"class_level", "skill", "prior_proficient_skills"}
            or type(record["class_level"]) is not int or record["class_level"] != 3
            or character.get("subclass_id") != "berserker"
            or type(character.get("level")) is not int
            or not character["progression_level"] <= character["level"] <= 20
            or type(prior) is not list or any(type(x) is not str or x not in SKILL_DEFINITIONS for x in prior)
            or len(set(prior)) != len(prior) or type(skill) is not str or skill not in BARBARIAN_SKILLS
            or skill in prior or character.get("proficient_skills") != prior + [skill]):
        raise ValueError("Invalid selected Primal Knowledge provenance.")


def berserker_eligible(character):
    if (character.get("class") != "Barbarian" or type(character.get("level")) is not int
            or type(character.get("progression_level")) is not int
            or character["progression_level"] not in (3, 4, 5)
            or not character["progression_level"] <= character["level"] <= 20):
        return False
    try:
        _validate_primal_knowledge(character)
        if character["progression_level"] in (4, 5):
            _validate_asi_choice_storage(character, saved="origin_choices" in character)
    except (ValueError, KeyError, TypeError):
        return False
    return character.get("subclass_id") == "berserker"


def _barbarian_three_prerequisite(session):
    character = session.character
    if (type(character.get("progression_level")) is not int or character["progression_level"] != 2
            or type(character.get("level")) is not int or not 2 <= character["level"] <= 20):
        return "previous_level_two_choices_required"
    if getattr(session, "_persisted_engine_format", 4) not in (4, 5, 6):
        return "selected_subclass_save_format_required"
    try:
        validate_saved(character, session.world_state)
        import barbarian_rage
        barbarian_rage.validate(session.world_state, character, getattr(session, "_persisted_engine_format", 4))
        if "rage_v1" not in session.world_state:
            return "selected_subclass_rage_capability_required"
        from api.dnd_2024_rules import SKILL_DEFINITIONS
        skills = character.get("proficient_skills")
        if (type(skills) is not list or any(type(x) is not str or x not in SKILL_DEFINITIONS for x in skills)
                or len(set(skills)) != len(skills)):
            return "previous_skill_state_invalid"
    except (ValueError, TypeError):
        return "previous_barbarian_state_invalid"
    return None


def _project_selected_asi_hp(character: Any, target_level: Any, choice: Any) -> dict[str, Any]:
    """Selected ordinary ASI/paid-HP bridge; grants no level, feat, HP or permission.

    Atomic progression recomputes from pre-mutation state after validating choices. Base HP and retroactive maximum are separate
    components: the latter belongs to set_player_max_hp, never heal_player.
    Character-only input cannot authorize death/world state. The selected level4
    caller consumes this projection, not a client preview token or saved grant.
    """
    def refuse(reason: str, status: str = "rejected") -> dict[str, Any]:
        return {"status": status, "reason": reason}

    if not isinstance(character, dict) or type(target_level) is not int:
        return refuse("invalid_projection_input")
    raw, applied = character.get("level"), character.get("progression_level")
    if type(raw) is not int or type(applied) is not int:
        return refuse("invalid_projection_levels")
    if not for_class(character.get("class")).selected_asi or target_level != 4 or applied != 3 or raw not in (3, 4, 5):
        return refuse("projection_scope_not_supported", "unsupported")
    if (type(choice) is not dict or set(choice) != {"increase"}
            or not _supported_asi_increase(choice["increase"])):
        return refuse("selected_asi_not_supported", "unsupported")
    constitution, maximum = character.get("constitution"), character.get("max_hp")
    if type(constitution) is not int or not 1 <= constitution <= 30 or type(maximum) is not int or maximum < 1:
        return refuse("invalid_projection_values")
    import feat_rules
    import xp
    detached = copy.deepcopy(character)
    detached["level"] = target_level
    delta = feat_rules.apply_feat_choice(detached, "Ability Score Improvement",
                                         {**copy.deepcopy(choice), "source": "class_asi"})
    if delta["status"] != "applied":
        return refuse(delta["reason"])
    con_change = next((change for change in delta["changes"] if change["ability"] == "constitution"), None)
    modifier_gain = ((con_change["to"] - 10) // 2 - (con_change["from"] - 10) // 2) if con_change else 0
    base_gain = xp.hit_point_gain(character) if raw < target_level else 0
    retroactive_gain = modifier_gain * max(raw, target_level)
    return {"status": "projected", "reason": None, "unpaid_base_gain": base_gain,
            "retroactive_max_gain": retroactive_gain,
            "resulting_maximum": maximum + base_gain + retroactive_gain,
            "feat_delta": delta}


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
    return for_class(character.get("class")).capacity(character)


def slot_capacity(character: dict[str, Any]) -> dict[str, int] | None:
    cap = capacity(character)
    return cap["slots"] if cap else None


def _preview(status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def progression_disclosure(class_name: str, level: int, **adopted: Any) -> dict[str, list[str]]:
    """Pure supported/pending view. Capability facts never adopt resources."""
    return for_class(class_name).disclosure(level, **adopted)


def progression_effects_pending(class_name: str, level: int, **adopted: Any) -> list[str]:
    return progression_disclosure(class_name, level, **adopted)["pending"]


HIGHER_START_EQUIPMENT_PENDING = ("Higher-start equipment: normal starting gear only; optional extra wealth and magic items remain pending")


def _noncaster_start_row_ok(row: Any, features: list[str], bonus: int, rages: int, damage: int, mastery: int) -> bool:
    """Exact source row for a Barbarian start step: ints only (no bool), no caster keys; anything else hides the level."""
    return (isinstance(row, dict) and row.get("features") == features
            and type(row.get("proficiency_bonus")) is int and row["proficiency_bonus"] == bonus
            and type(row.get("rages")) is int and row["rages"] == rages
            and type(row.get("rage_damage")) is int and row["rage_damage"] == damage
            and type(row.get("weapon_mastery")) is int and row["weapon_mastery"] == mastery
            and not any(key in row for key in ("slots", "cantrips", "prepared_spells")))


def barbarian_starting_creation_options() -> dict[str, Any] | None:
    """Detached capability for the accepted noncaster start2, not full class effects."""
    source = table("Barbarian")
    if _supported_level("Barbarian") < 2 or not isinstance(source, dict):
        return None
    levels = source.get("levels")
    if not isinstance(levels, dict):
        return None
    one, two = levels.get("1"), levels.get("2")
    if (not isinstance(one, dict) or not isinstance(two, dict)
            or one.get("features") != ["Rage", "Unarmored Defense", "Weapon Mastery"]
            or two.get("features") != ["Danger Sense", "Reckless Attack"]
            or any(type(row.get("proficiency_bonus")) is not int or row["proficiency_bonus"] != 2
                   or row.get("rages") != 2 or row.get("rage_damage") != 2 or row.get("weapon_mastery") != 2
                   for row in (one, two))
            or any(key in row for row in (one, two) for key in ("slots", "cantrips", "prepared_spells"))):
        return None
    result = {"supported_starting_levels": [1, 2], "level_2": {
        "choices": {},
        "effects_supported": progression_disclosure("Barbarian", 2)["supported"],
        "effects_pending": progression_effects_pending("Barbarian", 2),
    }}
    three = levels.get("3")
    if (_supported_level("Barbarian") >= 3 and isinstance(three, dict)
            and three.get("features") == ["Barbarian Subclass", "Primal Knowledge"]
            and three.get("proficiency_bonus") == 2 and three.get("rages") == 3 and three.get("rage_damage") == 2
            and three.get("weapon_mastery") == 2
            and not any(key in three for key in ("slots", "cantrips", "prepared_spells"))):
        # Source vocabulary only (not filtered per character): a malformed row 3 just omits level 3 and keeps verified 1/2.
        result["supported_starting_levels"] = [1, 2, 3]
        result["level_3"] = {
            "subclass_options": [{"id": "berserker", "name": "Path of the Berserker"}],
            "primal_knowledge_skill_options": list(BARBARIAN_SKILLS),
            "effects_supported": progression_disclosure("Barbarian", 3)["supported"],
            "effects_pending": progression_effects_pending("Barbarian", 3),
        }
        # Start 4 and 5 extend the verified prefix one row at a time: a bad row 4 hides both, a bad row 5 hides only level 5.
        asi = supported_asi_choices()
        if (_supported_level("Barbarian") >= 4 and asi
                and _noncaster_start_row_ok(levels.get("4"), ["Ability Score Improvement"], 2, 3, 2, 3)):
            result["supported_starting_levels"] = [1, 2, 3, 4]
            result["level_4"] = {
                "supported_asi_choices": asi,
                "effects_supported": progression_disclosure("Barbarian", 4)["supported"],
                "effects_pending": progression_effects_pending("Barbarian", 4) + [HIGHER_START_EQUIPMENT_PENDING],
            }
            if (_supported_level("Barbarian") >= 5
                    and _noncaster_start_row_ok(levels.get("5"), ["Extra Attack", "Fast Movement"], 3, 3, 2, 3)):
                result["supported_starting_levels"] = [1, 2, 3, 4, 5]
                result["level_5"] = {
                    "effects_supported": progression_disclosure("Barbarian", 5)["supported"],
                    "effects_pending": progression_effects_pending("Barbarian", 5) + [HIGHER_START_EQUIPMENT_PENDING],
                }
    return result


def sorcerer_starting_creation_options() -> dict[str, Any] | None:
    """Detached metadata for the fixed HTTP level 1–5 choice bundle, not effects or grants."""
    from api.dnd_2024_rules import SPELLS_CATALOG

    if MAX_SUPPORTED_LEVEL < 5:
        return None
    source = table("Sorcerer")
    if not isinstance(source, dict):
        return None
    try:
        prepared = [source["levels"][str(level)]["prepared_spells"] for level in (1, 2, 3, 4, 5)]
        cantrip_counts = [source["levels"][str(level)]["cantrips"] for level in (1, 2, 3, 4, 5)]
        cantrip_ids = [spell["id"] for spell in SPELLS_CATALOG["Sorcerer"]["cantrips"]]
        metamagic_count = source["metamagic_choice_counts"]["2"]
        metamagic = source["metamagic_options"]
        subclasses = source["subclass_options"]
        spell_ids = [spell["id"] for spell in SPELLS_CATALOG["Sorcerer"]["spells_level_1"]]
        # This projection advertises the fixed accepted HTTP adapter, whose
        # requests take two initial spells, two additions per step and two
        # level-two Metamagic choices. A changed source needs a new adapter.
        if (any(type(count) is not int for count in prepared) or prepared != [2, 4, 6, 7, 9]
                or type(metamagic_count) is not int or metamagic_count != 2
                or any(source["metamagic_choice_counts"].get(str(level), 0) != 0 for level in (3, 4, 5))
                or cantrip_counts != [4, 4, 4, 5, 5]
                or len(set(cantrip_ids)) < 5 or any(type(identity) is not str or not identity for identity in cantrip_ids)
                or not isinstance(metamagic, list) or len(metamagic) < metamagic_count
                or any(not isinstance(option, str) or not option for option in metamagic)
                or not isinstance(subclasses, dict) or not subclasses
                or not spell_ids or any(not isinstance(identity, str) or not identity for identity in spell_ids)):
            return None
        if len(set(spell_ids)) < 9 or len(set(metamagic)) < 2:
            return None
        subclass_options = [{"id": identity, "name": option["name"]} for identity, option in subclasses.items()]
        if any(not isinstance(option[key], str) or not option[key]
               for option in subclass_options for key in ("id", "name")):
            return None
    except (KeyError, TypeError):
        return None
    return copy.deepcopy({
        "supported_starting_levels": [1, 2, 3, 4, 5],
        "level_2": {
            "prepared_spell_count": prepared[1] - prepared[0],
            "prepared_spell_ids": list(spell_ids),
            "metamagic_count": metamagic_count,
            "metamagic_options": metamagic,
        },
        "level_3": {
            "prepared_spell_count": prepared[2] - prepared[1],
            "prepared_spell_ids": list(spell_ids),
            "subclass_options": subclass_options,
        },
        "level_4": {
            "prepared_spell_count": 1, "prepared_spell_ids": list(spell_ids),
            "cantrip_count": 1, "cantrip_ids": list(cantrip_ids),
            "supported_asi_choices": supported_asi_choices(),
        },
        "level_5": {"prepared_spell_count": 2, "prepared_spell_ids": list(spell_ids)},
        "effects_pending_by_level": {
            str(level): progression_effects_pending("Sorcerer", level) +
                ([HIGHER_START_EQUIPMENT_PENDING] if level >= 4 else [])
            for level in (1, 2, 3, 4, 5)
        },
    })


def preview_level_up(session: Any, target_level: Any) -> dict[str, Any]:
    """What reaching `target_level` needs and gives. Pure: nothing is changed."""
    character = session.character
    if type(target_level) is not int or not 1 <= target_level <= 20:
        return _preview("blocked", "invalid_target_level")
    if not has_table(character):
        return _preview("blocked", "class_table_not_available")
    current = applied_level(character)
    if type(character.get("level")) is not int or not 1 <= character["level"] <= 20:
        return _preview("blocked", "invalid_character_level")
    if target_level <= current:
        return _preview("blocked", "target_not_above_applied_level", from_level=current, to_level=target_level)
    if target_level > _supported_level(character["class"]):
        return _preview("blocked", "progression_level_not_supported", from_level=current, to_level=target_level)
    if character["class"] == "Barbarian" and target_level == 3:
        problem = _barbarian_three_prerequisite(session)
        if problem:
            return _preview("blocked", problem, from_level=current, to_level=target_level)
    if target_level == 4:
        problem = _level_four_prerequisite(session)
        if problem:
            return _preview("blocked", problem, from_level=current, to_level=target_level)
    if target_level == 5:
        if (type(character.get("progression_level")) is not int or character["progression_level"] != 4
                or character["level"] != 5):
            return _preview("blocked", "previous_level_four_choices_and_numeric_five_required")
        try:
            validate_saved(character, session.world_state)
            _validate_con_caches(character)
        except (ValueError, KeyError, TypeError):
            return _preview("blocked", "previous_level_four_state_invalid")
        if character["class"] == "Barbarian":
            problem = _barbarian_five_prerequisite(session)
            if problem:
                return _preview("blocked", problem, from_level=current, to_level=target_level)
    rows = [row(character, level) for level in range(current + 1, target_level + 1)]
    features = [feature for data in rows for feature in data["features"]]
    prior, goal = row(character, current), rows[-1]
    metamagic = sum(table(character["class"]).get("metamagic_choice_counts", {}).get(str(level), 0)
                    for level in range(current + 1, target_level + 1))
    import xp
    noncaster = character["class"] == "Barbarian"
    required = {} if noncaster else {"prepared_spells": goal["prepared_spells"] - prior["prepared_spells"]}
    if target_level == 4:
        if noncaster:
            required["asi"] = 1
        else:
            required.update(cantrips=1, asi=1)
    if metamagic:
        required["metamagic"] = metamagic
    if current < 3 <= target_level:
        required["subclass_id"] = 1
    if noncaster and target_level == 3:
        required["primal_knowledge_skill"] = 1
    disclosure = progression_disclosure(character["class"], target_level, **for_class(character["class"]).adoption(session.world_state))
    pending = disclosure["pending"]
    return _preview(
        "ready", None, class_name=character["class"], from_level=current, to_level=target_level, features=features,
        choices_required=required,
        capacity=None if noncaster else {"cantrips": goal["cantrips"], "prepared_spells": goal["prepared_spells"], "slots": copy.deepcopy(goal["slots"]),
                  "sorcery_points": goal["sorcery_points"]},
        hit_points={"gain": xp.hit_point_gain(character) * max(0, target_level - character["level"]), "already_applied": character["level"] >= target_level},
        effects_pending=pending, effects_supported=disclosure["supported"],
        **({"primal_knowledge_skill_options": [skill for skill in BARBARIAN_SKILLS if skill not in character["proficient_skills"]],
             "subclass_options": [{"id": "berserker", "name": "Path of the Berserker"}]}
           if noncaster and target_level == 3 else {}),
        **({"supported_asi_choices": _barbarian_asi_options(session) if noncaster else supported_asi_choices(character)}
           if target_level == 4 else {}),
    )


_NONDEX_ASI_ABILITIES = ("strength", "constitution", "intelligence", "wisdom", "charisma")


def _supported_asi_increase(increase: Any) -> bool:
    return (type(increase) is dict and not set(increase) - set(_NONDEX_ASI_ABILITIES)
            and all(type(amount) is int for amount in increase.values())
            and sorted(increase.values()) in ([2], [1, 1]))


def supported_asi_choices(character: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Static engine family, or cap-eligible choices for the current character.

    C03 remains the score/eligibility owner; DEX requires worn-armor provenance.
    """
    import feat_rules
    increases = [{a: 2} for a in _NONDEX_ASI_ABILITIES]
    increases += [{a: 1, b: 1} for i, a in enumerate(_NONDEX_ASI_ABILITIES)
                  for b in _NONDEX_ASI_ABILITIES[i + 1:]]
    options = [{"feat": "Ability Score Improvement", "increase": inc} for inc in increases]
    if character is None:
        return options
    detached = {**copy.deepcopy(character), "level": 4}
    return [option for option in options if feat_rules.apply_feat_choice(
        detached, option["feat"], {"source": "class_asi", "increase": option["increase"]})["status"] == "applied"]


def _selected_asi_record(increase: dict[str, int] | None = None) -> list[dict[str, Any]]:
    return [{"class_level": 4, "feat": "Ability Score Improvement",
             "increase": copy.deepcopy(increase if increase is not None else {"constitution": 2})}]


def _score_context(player: dict[str, Any], *, saved: bool) -> dict[str, Any]:
    import feat_rules
    origin = player.get("origin_choices", {}) if saved else player
    if type(origin) is not dict:
        raise ValueError("Invalid ASI origin provenance.")
    return dict(scores={a: player.get(a) for a in feat_rules.ABILITIES},
                base_scores=origin.get("base_ability_scores"),
                background_bonuses=origin.get("background_ability_bonuses"),
                ability_score_method=origin.get("ability_score_method"), background=origin.get("background"),
                class_name=player.get("class"), level=player.get("level"),
                applied_level=player.get("progression_level"), asi_choices=player.get("asi_choices"))


def _validate_con_caches(player: dict[str, Any], *, saved: bool = False) -> None:
    import feat_rules
    scores = {a: player.get(a) for a in feat_rules.ABILITIES}
    if any(type(v) is not int for v in scores.values()):
        raise ValueError("Invalid ASI ability scores.")
    modifiers = {a: (v - 10) // 2 for a, v in scores.items()}
    if type(player.get("proficiency_bonus")) is not int or player["proficiency_bonus"] != proficiency_bonus_for_level(player["level"]):
        raise ValueError("Invalid selected ASI proficiency bonus.")
    saves = player.get("saving_throw_mods")
    if (type(saves) is not dict or set(saves) != set(scores)
            or any(type(v) is not int for v in saves.values())):
        # These are authoritative totals, not a reconstructed proficiency cache.
        # The generalized ASI family preserves legitimate nonability offsets.
        raise ValueError("Invalid ASI saving throw totals.")
    if not saved:
        if (type(player.get("modifiers")) is not dict or player["modifiers"] != modifiers
                or any(type(v) is not int for v in player["modifiers"].values())
                or any(type(player.get(a + "_mod")) is not int or player[a + "_mod"] != m
                       for a, m in modifiers.items())
                or ("final_ability_scores" in player and (type(player["final_ability_scores"]) is not dict
                    or player["final_ability_scores"] != scores
                    or any(type(v) is not int for v in player["final_ability_scores"].values())))):
            raise ValueError("Inconsistent ASI ability caches.")


def _validate_asi_choice_storage(player: dict[str, Any], *, saved: bool = False) -> None:
    """Admit one selected non-DEX ordinary ASI with source-reconstructable scores."""
    choices = player.get("asi_choices", [])
    applied = player.get("progression_level")
    if type(choices) is not list:
        raise ValueError("Invalid ASI choices.")
    if not choices and applied not in (4, 5):
        return
    if (len(choices) != 1 or type(choices[0]) is not dict
            or set(choices[0]) != {"class_level", "feat", "increase"}
            or type(choices[0]["class_level"]) is not int or choices[0]["class_level"] != 4
            or choices[0]["feat"] != "Ability Score Improvement"
            or not _supported_asi_increase(choices[0]["increase"])):
        raise ValueError("Selected earned ASI record required.")
    result = _check_detached_asi_consistency(**_score_context(player, saved=saved))
    if not result["consistent"]:
        raise ValueError("Invalid earned ASI provenance: " + result["reason"])
    _validate_con_caches(player, saved=saved)
    if player.get("class") == "Barbarian":
        context = _score_context(player, saved=saved)
        prior_con = context["base_scores"]["constitution"] + context["background_bonuses"].get("constitution", 0)
        modifier_changed = (player["constitution"] - 10) // 2 != (prior_con - 10) // 2
        ac = player.get("armor_class")
        if (type(ac) is not int or ac < 0
                or (modifier_changed and ac != _barbarian_canonical_ac(player))):
            raise ValueError("Invalid selected Barbarian ASI armor class.")


def _validate_selected_spell_mirrors(player: dict[str, Any], state: dict[str, Any]) -> None:
    if player.get("spells") != state["prepared"] or player.get("cantrips") != state["cantrips"]:
        raise ValueError("Selected ASI spell access mirrors are inconsistent.")
    # Cast/rest own world counters; the legacy character counter may lag.
    # Validate it independently, never refill authoritative world from it.
    slots, limits = player.get("spell_slots_remaining"), slot_capacity(player)
    if (type(slots) is not dict or set(slots) != set(limits)
            or any(type(n) is not int or not 0 <= n <= limits[k] for k, n in slots.items())):
        raise ValueError("Selected ASI slot mirror is outside applied capacity.")


def _barbarian_canonical_ac(character):
    return 10 + (character["dexterity"] - 10) // 2 + (character["constitution"] - 10) // 2


def _barbarian_asi_options(session) -> list[dict[str, Any]]:
    """Existing cap-eligible choices, conditionally bounded by the known AC total.

    Inventory is never formula provenance. A parity-neutral CON increase keeps
    every existing AC extra; a modifier change needs the canonical old total.
    Prerequisite/save admission independently requires retained Rage and proof.
    """
    character = session.character
    ac = character.get("armor_class")
    if type(ac) is not int or ac < 0:
        return []
    options = supported_asi_choices(character)
    accepted = []
    for option in options:
        projection = _project_selected_asi_hp(character, 4, {"increase": option["increase"]})
        if projection["status"] == "projected" and (projection["retroactive_max_gain"] == 0
                or ac == _barbarian_canonical_ac(character)):
            accepted.append(option)
    return accepted


def _barbarian_four_prerequisite(session) -> str | None:
    import barbarian_rage
    import game
    character = session.character
    if (type(character.get("progression_level")) is not int or character["progression_level"] != 3
            or type(character.get("level")) is not int or character["level"] not in (3, 4, 5)):
        return "previous_level_three_choices_required"
    version = getattr(session, "_persisted_engine_format", game.SAVE_FORMAT_VERSION)
    if type(version) is not int or version not in (4, 5, 6):
        return "asi_save_version_not_supported"
    try:
        validate_saved(character, session.world_state)
        barbarian_rage.validate(session.world_state, character, version, strict_active=True)
        if "rage_v1" not in session.world_state:
            return "selected_asi_rage_capability_required"
        _validate_con_caches(character)
        if type(character.get("armor_class")) is not int or character["armor_class"] < 0:
            return "previous_barbarian_armor_class_invalid"
        options = _barbarian_asi_options(session)
        if not options:
            return "no_supported_asi_choices"
        increase = options[0]["increase"]
        projected = _project_selected_asi_hp(character, 4, {"increase": increase})
        context = _score_context(character, saved=False)
        for change in projected["feat_delta"]["changes"]:
            context["scores"][change["ability"]] = change["to"]
        context.update(level=max(character["level"], 4), applied_level=4, asi_choices=_selected_asi_record(increase))
        check = _check_detached_asi_consistency(**context)
        if not check["consistent"]:
            return check["reason"]
    except (ValueError, KeyError, TypeError):
        return "previous_level_three_state_invalid"
    return None


def attacks_per_attack_action(character: Any) -> int:
    """Attacks one Attack action allows from class features (the existing attacks-per-Action allowance owner reads this)."""
    return _handler_of(character).attacks_per_attack_action(character)


def fast_movement_bonus_ft(character: Any, world: Any) -> int:
    """Speed bonus from class features (the existing Speed owner reads this)."""
    return _handler_of(character).speed_bonus_ft(character, world)


def _handler_of(character: Any) -> Any:
    return for_class(character.get("class") if isinstance(character, dict) else None)


def _barbarian_five_prerequisite(session) -> str | None:
    """Level 5 needs the same retained, verified Berserker/Rage/ASI facts as level 4; it adds no choice and no resource."""
    import barbarian_rage
    character = session.character
    version = getattr(session, "_persisted_engine_format", 4)
    if type(version) is not int or version not in (4, 5, 6):
        return "asi_save_version_not_supported"
    try:
        if "rage_v1" not in session.world_state:
            return "selected_level_five_rage_capability_required"
        barbarian_rage.validate(session.world_state, character, version, strict_active=True)
        if not berserker_eligible(character):
            return "previous_barbarian_state_invalid"
    except (ValueError, KeyError, TypeError):
        return "previous_level_four_state_invalid"
    return None


def _level_four_prerequisite(session: Any) -> str | None:
    if session.character.get("class") == "Barbarian":
        return _barbarian_four_prerequisite(session)
    import spell_scope
    import game
    character = session.character
    if (type(character.get("progression_level")) is not int or character["progression_level"] != 3
            or type(character.get("level")) is not int or character["level"] not in (3, 4, 5)):
        return "previous_level_three_choices_required"
    if getattr(session, "_persisted_engine_format", game.SAVE_FORMAT_VERSION) not in (4, 5, 6):
        return "asi_save_version_not_supported"
    try:
        validate_saved(character, session.world_state)
        state = session.world_state.get("spellcasting_v1")
        spell_scope.validate(state, character)
        _validate_selected_spell_mirrors(character, state)
        _validate_con_caches(character)
        # Replay from retained original provenance, never from current scores.
        options = supported_asi_choices(character)
        if not options:
            return "no_supported_asi_choices"
        increase = options[0]["increase"]
        projected = _project_selected_asi_hp(character, 4, {"increase": increase})
        if projected["status"] != "projected":
            return projected["reason"]
        context = _score_context(character, saved=False)
        for change in projected["feat_delta"]["changes"]:
            context["scores"][change["ability"]] = change["to"]
        context.update(level=4, applied_level=4, asi_choices=_selected_asi_record(increase))
        check = _check_detached_asi_consistency(**context)
        if not check["consistent"]:
            return check["reason"]
    except (ValueError, KeyError, TypeError):
        return "previous_level_three_state_invalid"
    return None


def _check_detached_asi_consistency(*, scores: Any, base_scores: Any,
                                    background_bonuses: Any, ability_score_method: Any,
                                    background: Any, class_name: Any, level: Any,
                                    applied_level: Any, asi_choices: Any) -> dict[str, Any]:
    """Private hypothetical selected ordinary ASI consistency check, NOT admission.

    Inputs are explicit normalized values, not live/saved character dictionaries.
    No mutation, ready token, HP calculation or entitlement follows from success.
    A consistent unsigned claim is not proof against rewriting its entire baseline.
    Rolled provenance is unsupported: stored scores are not a verified dice pool.
    """
    import feat_rules
    from api.dnd_2024_rules import validate_ability_scores, validate_background_bonuses

    def reject(reason):
        return {"consistent": False, "reason": reason}

    if (not for_class(class_name).selected_asi or type(level) is not int or level not in (4, 5)
            or type(applied_level) is not int or applied_level not in (4, 5) or applied_level > level):
        return reject("unsupported_hypothetical_context")
    abilities = set(feat_rules.ABILITIES)
    for values in (scores, base_scores):
        if (type(values) is not dict or set(values) != abilities
                or any(type(v) is not int for v in values.values())):
            return reject("invalid_scores")
    if (type(background_bonuses) is not dict or set(background_bonuses) - abilities
            or any(type(v) is not int or not 0 <= v <= 2 for v in background_bonuses.values())
            or type(background) is not str or type(ability_score_method) is not str
            or ability_score_method not in ("standard_array", "point_buy", "manual")):
        return reject("invalid_origin_provenance")
    try:
        validate_ability_scores(ability_score_method, base_scores)
        validate_background_bonuses(background, background_bonuses, base_scores)
    except ValueError:
        return reject("invalid_origin_provenance")
    if type(asi_choices) is not list or len(asi_choices) != 1:
        return reject("invalid_asi_record")
    record = asi_choices[0]
    if (type(record) is not dict or set(record) != {"class_level", "feat", "increase"}
            or type(record["class_level"]) is not int or record["class_level"] != 4
            or record["feat"] != "Ability Score Improvement"
            or type(record["increase"]) is not dict):
        return reject("invalid_asi_record")
    replay = {ability: base_scores[ability] + background_bonuses.get(ability, 0)
              for ability in feat_rules.ABILITIES}
    detached = {**replay, "class": class_name, "level": level}
    delta = feat_rules.apply_feat_choice(detached, record["feat"],
                                         {"source": "class_asi", "increase": record["increase"]})
    if delta["status"] != "applied":
        return reject(delta["reason"])
    for change in delta["changes"]:
        replay[change["ability"]] = change["to"]
    if replay != scores:
        return reject("score_delta_mismatch")
    return {"consistent": True, "reason": None}


def validate_saved(player: dict[str, Any], world: dict[str, Any], *, saved: bool = False) -> None:
    """Validate applied choices, not completion of the selected feature effects."""
    _validate_asi_choice_storage(player, saved=saved)
    _validate_primal_knowledge(player)
    if player.get("class") == "Barbarian" and not _noncaster_state_valid(player, world):
        raise ValueError("Kayıt Barbarian için kazanılmamış büyü veya alt sınıf durumu içeriyor.")
    if not any(field in player for field in ("progression_level", "metamagic", "subclass_id")):
        return
    applied = player.get("progression_level", 1)
    level = player.get("level", 1)
    if type(applied) is not int or type(level) is not int or not 1 <= applied <= level <= 20:
        raise ValueError("Kayıt uygulanmış ilerleme seviyesi geçersiz.")
    if not has_table(player):
        if applied != 1 or player.get("metamagic") or "subclass_id" in player:
            raise ValueError("Kayıt ilerleme tablosu olmayan sınıf için ilerleme iddia ediyor.")
        return
    if applied > _supported_level(player["class"]):
        raise ValueError("Kayıt desteklenmeyen ilerleme seviyesi iddia ediyor.")
    if player["class"] == "Barbarian":
        if applied in (4, 5):
            import barbarian_rage
            if "rage_v1" not in world:
                raise ValueError("Selected Barbarian ASI requires retained Rage capability.")
            barbarian_rage.validate(world, player, 4, strict_active=True)
        return
    options = table(player["class"]).get("subclass_options", {})
    subclass = player.get("subclass_id")
    if applied >= 3:
        if not isinstance(subclass, str) or subclass not in options:
            raise ValueError("Kayıt geçerli alt sınıf seçimi içermiyor.")
    elif "subclass_id" in player:
        raise ValueError("Kayıt kazanılmamış alt sınıf seçimi iddia ediyor.")
    known = player.get("metamagic", [])
    owed = sum(table(player["class"]).get("metamagic_choice_counts", {}).get(str(n), 0)
               for n in range(2, applied + 1))
    if (not isinstance(known, list) or any(not isinstance(x, str) for x in known)
            or len(known) != owed or len(set(known)) != len(known)
            or not set(known) <= set(table(player["class"])["metamagic_options"])):
        raise ValueError("Kayıt Metamagic seçimleri geçersiz.")
    if applied >= 2:
        state = world.get("spellcasting_v1")
        data = row(player, applied)
        if (not isinstance(state, dict) or len(state.get("prepared", [])) != data["prepared_spells"]
                or len(state.get("cantrips", [])) != data["cantrips"]):
            raise ValueError("Kayıt uygulanmamış seviye seçimleri iddia ediyor.")
        if applied in (4, 5):
            import spell_scope
            spell_scope.validate(state, player)
            _validate_selected_spell_mirrors(player, state)


def _reject(reason: str) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason, "changes": [], "effects_pending": []}


def _check_choices(session: Any, preview: dict[str, Any], choices: Any) -> str | None:
    from api.dnd_2024_rules import SPELLS_CATALOG
    if not isinstance(choices, dict):
        return "choices_required"
    required = preview["choices_required"]
    if set(choices) - set(required):
        return "unsupported_choice"
    if "asi" in required and session.character["class"] == "Barbarian":
        asi = choices.get("asi")
        if (type(asi) is not dict or set(asi) != {"feat", "increase"}
                or asi["feat"] != "Ability Score Improvement"
                or not _supported_asi_increase(asi["increase"])):
            return "selected_asi_not_supported"
        if asi not in _barbarian_asi_options(session):
            return "asi_choice_not_eligible"
    if session.character["class"] == "Barbarian":
        if not _noncaster_state_valid(session.character, session.world_state):
            return "noncaster_state_invalid"
        if preview["to_level"] == 3:
            if set(choices) != {"subclass_id", "primal_knowledge_skill"} or choices.get("subclass_id") != "berserker":
                return "selected_barbarian_subclass_required"
            skill = choices.get("primal_knowledge_skill")
            if type(skill) is not str or skill not in BARBARIAN_SKILLS or skill in session.character["proficient_skills"]:
                return "primal_knowledge_skill_invalid"
        return None
    state = session.world_state["spellcasting_v1"]
    picked = choices.get("prepared_spells", [])
    allowed = {s["id"] for s in SPELLS_CATALOG.get(session.character["class"], {}).get("spells_level_1", [])}
    if not isinstance(picked, list) or len(picked) != required["prepared_spells"]:
        return "prepared_spells_count"
    if (any(not isinstance(s, str) for s in picked) or len(set(picked)) != len(picked) or not set(picked) <= allowed
            or set(picked) & set(state["prepared"])):
        return "prepared_spells_invalid"
    if "asi" in required:
        asi = choices.get("asi")
        if (type(asi) is not dict or set(asi) != {"feat", "increase"}
                or asi["feat"] != "Ability Score Improvement"
                or not _supported_asi_increase(asi["increase"])):
            return "selected_asi_not_supported"
        if asi not in supported_asi_choices(session.character):
            return "asi_choice_not_eligible"
        cantrips = choices.get("cantrips")
        allowed_cantrips = {s["id"] for s in SPELLS_CATALOG["Sorcerer"]["cantrips"]}
        if (type(cantrips) is not list or len(cantrips) != 1 or type(cantrips[0]) is not str
                or cantrips[0] not in allowed_cantrips or cantrips[0] in state["cantrips"]):
            return "cantrips_invalid"
    if "subclass_id" in required:
        chosen = choices.get("subclass_id")
        if not isinstance(chosen, str) or chosen not in table(session.character["class"]).get("subclass_options", {}):
            return "subclass_invalid"
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
    if character["class"] == "Barbarian" and preview["to_level"] == 3:
        return _apply_barbarian_three(session, preview, choices)
    if character["class"] == "Barbarian" and preview["to_level"] == 5:
        return _apply_barbarian_five(session, preview)
    if preview["to_level"] == 4:
        if character["class"] == "Barbarian":
            return _apply_barbarian_four(session, preview, choices)
        return _apply_selected_level_four(session, preview, choices)
    import spell_scope
    new_character = copy.deepcopy(character)
    if character["class"] == "Barbarian":
        to_level = preview["to_level"]
        changes = []
        if not preview["hit_points"]["already_applied"]:
            gain = preview["hit_points"]["gain"]
            new_character["max_hp"] += gain
            if new_character["current_hp"] > 0:
                new_character["current_hp"] += gain
            changes.append({"kind": "hit_points", "gain": gain})
        new_character["level"] = max(new_character["level"], to_level)
        new_character["progression_level"] = to_level
        new_character["proficiency_bonus"] = proficiency_bonus_for_level(new_character["level"])
        try:
            spell_scope.validate(session.world_state.get("spellcasting_v1"), new_character)
            validate_saved(new_character, session.world_state)
        except ValueError:
            return _reject("resulting_state_invalid")
        character.clear()
        character.update(new_character)
        changes.append({"kind": "level", "from": preview["from_level"], "to": to_level})
        return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}
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
        if new_character["current_hp"] > 0:
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
    if "subclass_id" in choices:
        new_character["subclass_id"] = choices["subclass_id"]
        changes.append({"kind": "subclass_choice", "subclass_id": choices["subclass_id"], "effects_applied": False})
    try:
        import sorcery_points
        points = sorcery_points.advanced(session, new_character)
        spell_scope.validate(state, new_character)
        validate_saved(new_character, {"spellcasting_v1": state})
    except ValueError:
        return _reject("resulting_state_invalid")
    character.clear()
    character.update(new_character)
    session.world_state["spellcasting_v1"] = state
    if points is not None:
        session.world_state[sorcery_points.KEY] = points
    changes.append({"kind": "level", "from": preview["from_level"], "to": to_level})
    return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}


def _apply_barbarian_three(session, preview, choices):
    snapshot = session._capture_runtime_snapshot()
    try:
        character = copy.deepcopy(session.character)
        prior = list(character["proficient_skills"])
        skill = choices["primal_knowledge_skill"]
        character["primal_knowledge_choice"] = {"class_level": 3, "skill": skill, "prior_proficient_skills": prior}
        character["proficient_skills"] = prior + [skill]
        if skill == "Perception":
            character.pop("passive_perception", None)
        gain = preview["hit_points"]["gain"]
        character["max_hp"] += gain
        if character["current_hp"] > 0:
            character["current_hp"] += gain
        character.update(level=max(3, character["level"]), progression_level=3, subclass_id="berserker")
        state = copy.deepcopy(session.world_state["rage_v1"])
        state["remaining"] += 1  # capacity delta only; no refill or activation
        session.character.clear()
        session.character.update(character)
        session.world_state["rage_v1"] = state
        import barbarian_rage
        barbarian_rage.validate(session.world_state, character, getattr(session, "_persisted_engine_format", 4))
        validate_saved(character, session.world_state)
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        session._player_state_for_save()
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        return _reject("resulting_state_invalid")
    return {"status": "applied", "reason": None, "changes": [
        {"kind": "level", "from": 2, "to": 3}, {"kind": "hit_points", "gain": gain},
        {"kind": "skill_proficiency", "added": skill}, {"kind": "rage_capacity", "from": 2, "to": 3}],
        "effects_pending": list(preview["effects_pending"])}


def _apply_barbarian_five(session, preview):
    """Atomic noncaster level 5: XP already paid Hit Points and Proficiency Bonus; no choice, Rage refill or new resource."""
    snapshot = session._capture_runtime_snapshot()
    had_format = "_persisted_engine_format" in session.__dict__
    previous_format = copy.deepcopy(session.__dict__.get("_persisted_engine_format"))
    try:
        character = copy.deepcopy(session.character)
        character["progression_level"] = 5
        session.character.clear()
        session.character.update(character)
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        validate_saved(session.character, session.world_state)
        session._validate_save_payload(session.serialize_game_state())
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        if had_format:
            session._persisted_engine_format = previous_format
        else:
            session.__dict__.pop("_persisted_engine_format", None)
        return _reject("resulting_state_invalid")
    return {"status": "applied", "reason": None, "changes": [{"kind": "level", "from": 4, "to": 5}],
            "effects_pending": list(preview["effects_pending"])}


def _apply_asi_score_delta(character, feat_delta):
    """Apply the recomputed C03 delta, preserving authoritative save offsets."""
    import feat_rules
    for change in feat_delta["changes"]:
        ability = change["ability"]
        old_modifier = (change["from"] - 10) // 2
        new_modifier = (change["to"] - 10) // 2
        character[ability] = change["to"]
        character[ability + "_mod"] = new_modifier
        character["modifiers"][ability] = new_modifier
        character["saving_throw_mods"][ability] += new_modifier - old_modifier
    # Creation-only hints are not live authorities; actual consumers derive
    # their values. Do not change DEX/AC/initiative or NPC caches.
    for key in ("spell_save_dc", "spell_attack_bonus", "passive_perception"):
        character.pop(key, None)
    character["final_ability_scores"] = {a: character[a] for a in feat_rules.ABILITIES}


def _apply_barbarian_four(session, preview, choices):
    """Atomic noncaster ASI; no Rage/Hit Dice refill and no caster fabrication."""
    projection = _project_selected_asi_hp(session.character, 4, {"increase": choices["asi"]["increase"]})
    if projection["status"] != "projected":
        return _reject(projection["reason"])
    snapshot = session._capture_runtime_snapshot()
    had_format = "_persisted_engine_format" in session.__dict__
    previous_format = copy.deepcopy(session.__dict__.get("_persisted_engine_format"))
    try:
        character = copy.deepcopy(session.character)
        old_con_modifier = (character["constitution"] - 10) // 2
        base = projection["unpaid_base_gain"]
        character["max_hp"] += base
        if character["current_hp"] > 0:
            character["current_hp"] += base
        character.update(level=max(4, character["level"]), progression_level=4,
                         asi_choices=_selected_asi_record(choices["asi"]["increase"]))
        _apply_asi_score_delta(character, projection["feat_delta"])
        con_delta = character["constitution_mod"] - old_con_modifier
        if con_delta:
            # Choice admission checked the old canonical total, never guesses
            # whether inventory armor/shields are worn or contributing extras.
            character["armor_class"] += con_delta
        session.character.clear()
        session.character.update(character)
        session.set_player_max_hp(projection["resulting_maximum"])
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        validate_saved(session.character, session.world_state)
        # Full canonical serialized admission follows combat synchronization.
        session._validate_save_payload(session.serialize_game_state())
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        if had_format:
            session._persisted_engine_format = previous_format
        else:
            session.__dict__.pop("_persisted_engine_format", None)
        return _reject("resulting_state_invalid")
    return {"status": "applied", "reason": None,
            "changes": [{"kind": "level", "from": 3, "to": 4},
                        {"kind": "hit_points", "gain": base},
                        {"kind": "maximum_hit_points", "gain": projection["retroactive_max_gain"]},
                        {"kind": "asi", "feat_delta": projection["feat_delta"]}],
            "effects_pending": list(preview["effects_pending"])}


def _apply_selected_level_four(session: Any, preview: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
    """Atomic selected path. Base HP is paid once; retroactive maximum never heals."""
    import spell_scope
    projection = _project_selected_asi_hp(session.character, 4, {"increase": choices["asi"]["increase"]})
    if projection["status"] != "projected":
        return _reject(projection["reason"])
    snapshot = session._capture_runtime_snapshot()
    had_format = "_persisted_engine_format" in session.__dict__
    previous_format = copy.deepcopy(session.__dict__.get("_persisted_engine_format"))
    try:
        character = copy.deepcopy(session.character)
        state = copy.deepcopy(session.world_state["spellcasting_v1"])
        old_slots = capacity(character)["slots"]
        state["slots"] = {k: state["slots"].get(k, 0) + maximum - old_slots.get(k, 0)
                          for k, maximum in preview["capacity"]["slots"].items()}
        state["prepared"].extend(choices["prepared_spells"])
        state["cantrips"].extend(choices["cantrips"])
        base = projection["unpaid_base_gain"]
        character["max_hp"] += base
        if character["current_hp"] > 0:
            character["current_hp"] += base
        character.update(level=max(4, character["level"]), progression_level=4,
                         asi_choices=_selected_asi_record(choices["asi"]["increase"]))
        _apply_asi_score_delta(character, projection["feat_delta"])
        character["spells"] = list(state["prepared"])
        character["cantrips"] = list(state["cantrips"])
        character["spell_slots_remaining"] = copy.deepcopy(state["slots"])
        import sorcery_points
        points = sorcery_points.advanced(session, character)
        session.character.clear()
        session.character.update(character)
        session.world_state["spellcasting_v1"] = state
        if points is not None:
            session.world_state[sorcery_points.KEY] = points
        session.set_player_max_hp(projection["resulting_maximum"])
        spell_scope.validate(state, session.character)
        validate_saved(session.character, session.world_state)
        # Game owner also enforces the retained save version and serialized shape.
        session._player_state_for_save()
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        if had_format:
            session._persisted_engine_format = previous_format
        else:
            session.__dict__.pop("_persisted_engine_format", None)
        return _reject("resulting_state_invalid")
    return {"status": "applied", "reason": None,
            "changes": [{"kind": "level", "from": 3, "to": 4},
                        {"kind": "hit_points", "gain": base},
                        {"kind": "maximum_hit_points", "gain": projection["retroactive_max_gain"]},
                        {"kind": "asi", "feat_delta": projection["feat_delta"]},
                        {"kind": "cantrips", "added": list(choices["cantrips"])},
                        {"kind": "prepared_spells", "added": list(choices["prepared_spells"])},
                        {"kind": "spell_slots", "maximum": copy.deepcopy(preview["capacity"]["slots"])}],
            "effects_pending": list(preview["effects_pending"])}


def create_at_level(session: Any, spec: dict[str, Any], level: int = 1, level_choices: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a level-1 character with the real creation path, then reach `level` through the same preview/apply steps.

    Everything is checked before the character is created, so an unsupported level or missing choices leaves no half-made level.
    """
    from api.character_creation import configure_character
    if type(level) is not int or not 1 <= level <= 20:
        raise ValueError("invalid_target_level")
    if level > 1:
        class_name = spec.get("character_class")
        if class_name not in ("Sorcerer", "Barbarian"):
            raise ValueError("starting_level_class_not_supported")
        if class_name == "Barbarian":
            if level > 5:
                raise ValueError("progression_level_not_supported")
            # Start 3-5 reuse the accepted earned-3/4/5 owners; only the outer bundle shape is checked here, skill ownership,
            # ASI eligibility and the rest belong to the real step owners (the whole creation is rolled back on refusal).
            wanted = {str(n) for n in range(2, level + 1)}
            required = {2: "barbarian_level_two_choices_required", 3: "barbarian_level_three_choices_required",
                        4: "barbarian_level_four_choices_required", 5: "barbarian_level_five_choices_required"}[level]
            if (type(level_choices) is not dict or set(level_choices) != wanted
                    or type(level_choices["2"]) is not dict or level_choices["2"]):
                raise ValueError(required)
            if level >= 3:
                three = level_choices["3"]
                if (type(three) is not dict or set(three) != {"subclass_id", "primal_knowledge_skill"}
                        or three["subclass_id"] != "berserker" or type(three["primal_knowledge_skill"]) is not str):
                    raise ValueError(required)
            if level >= 4 and (type(level_choices["4"]) is not dict or set(level_choices["4"]) != {"asi"}):
                raise ValueError(required)
            if level == 5 and (type(level_choices["5"]) is not dict or level_choices["5"]):
                raise ValueError(required)
        if table(spec.get("character_class")) is None:
            raise ValueError("class_table_not_available")
        if level > 5:  # Higher creation stays bounded independently of future progression.
            raise ValueError("progression_level_not_supported")
        if level >= 4 and (type(level_choices) is not dict
                           or set(level_choices) != {str(n) for n in range(2, level + 1)}
                           or any(type(value) is not dict for value in level_choices.values())):
            raise ValueError("exact_creation_level_choices_required")
        missing = [str(n) for n in range(2, level + 1) if not isinstance((level_choices or {}).get(str(n)), dict)]
        if missing:
            raise ValueError(f"choices_required_for_levels_{','.join(missing)}")
    snapshot = session._capture_runtime_snapshot()
    try:
        for field in ("progression_level", "metamagic", "subclass_id", "hit_dice"):
            session.character.pop(field, None)
        configure_character(session, mode="custom", **spec)
        if level >= 4:
            # New-character initialization, not migration or a paid XP award.
            session._persisted_engine_format = 6 if level == 5 else 4
            session._xp_level_up = None
            session.world_state.setdefault("xp_awarded_event_ids", [])
        for step in range(2, level + 1):
            if step == 5:
                import xp
                xp._apply_numeric_level(session.character, 5)
            delta = apply_level_choices(session, preview_level_up(session, step), level_choices[str(step)])
            if delta["status"] != "applied":
                raise ValueError(delta["reason"])
        session.character.setdefault("progression_level", 1)
        # Starting XP is initialization, not an award: choices above already
        # applied the level's HP/resources. Keep this inside atomic creation.
        import xp
        session.character["xp"] = dict(xp.LEVEL_THRESHOLDS)[level]
        if level >= 4:
            # Only fresh creation ends full. Advancement's maximum-only ASI
            # setter must continue to preserve an existing character's wounds.
            session.character["current_hp"] = session.character["max_hp"]
            session._validate_save_payload(session.serialize_game_state())
        return session.character
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        raise
