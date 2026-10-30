"""Barbarian progression: earned and starting levels 1-5 with the selected Berserker path.

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
from class_progression.base import ClassProgression


BARBARIAN_SKILLS = ("Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival")


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
            core._validate_asi_choice_storage(character, saved="origin_choices" in character)
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
        core.validate_saved(character, session.world_state)
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
    options = core.supported_asi_choices(character)
    accepted = []
    for option in options:
        projection = core._project_selected_asi_hp(character, 4, {"increase": option["increase"]})
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
        core.validate_saved(character, session.world_state)
        barbarian_rage.validate(session.world_state, character, version, strict_active=True)
        if "rage_v1" not in session.world_state:
            return "selected_asi_rage_capability_required"
        core._validate_con_caches(character)
        if type(character.get("armor_class")) is not int or character["armor_class"] < 0:
            return "previous_barbarian_armor_class_invalid"
        options = core._barbarian_asi_options(session)
        if not options:
            return "no_supported_asi_choices"
        increase = options[0]["increase"]
        projected = core._project_selected_asi_hp(character, 4, {"increase": increase})
        context = core._score_context(character, saved=False)
        for change in projected["feat_delta"]["changes"]:
            context["scores"][change["ability"]] = change["to"]
        context.update(level=max(character["level"], 4), applied_level=4, asi_choices=core._selected_asi_record(increase))
        check = core._check_detached_asi_consistency(**context)
        if not check["consistent"]:
            return check["reason"]
    except (ValueError, KeyError, TypeError):
        return "previous_level_three_state_invalid"
    return None


FAST_MOVEMENT_FT = 10  # Barbarian Fast Movement, features table level 5 (+10 ft Speed)
EXTRA_ATTACK_ATTACKS = 2  # Barbarian Extra Attack, features table level 5 (two attacks instead of one)


def barbarian_level_five_applied(character: Any) -> bool:
    """The only source of level-5 Barbarian features: applied level 5 of the selected Berserker.

    Cheap on purpose (Speed and attack allowance read it often); the retained choices behind it are admitted by `validate_saved`
    on every save, restore and level-up, so a numeric XP level 5 or a forged field never reaches here with a valid state.
    """
    return (isinstance(character, dict) and character.get("class") == "Barbarian"
            and type(character.get("level")) is int and type(character.get("progression_level")) is int
            and character["progression_level"] == 5 and character["level"] >= 5
            and character.get("subclass_id") == "berserker")


def fast_movement_bonus_ft(character: Any, world: Any) -> int:
    """Fast Movement: +10 ft Speed while not wearing Heavy armor.

    The engine has no general worn-armor owner. The only retained fact is the Barbarian `worn_armor_v1` proof: `armor_id` None is
    the verified unarmored state. A named suit is read from the existing PHB armor table (Heavy => no bonus); a missing proof or an
    unknown armor cannot be verified as non-Heavy, so no bonus is granted (honest under-grant, never an invented armor state).
    """
    if not barbarian_level_five_applied(character) or not isinstance(world, dict):
        return 0
    proof = world.get("worn_armor_v1")
    if type(proof) is not dict or "armor_id" not in proof:
        return 0
    armor = proof["armor_id"]
    if armor is None:
        return FAST_MOVEMENT_FT
    if type(armor) is not str:
        return 0
    from api.dnd_2024_rules import ARMOR_CLASS_RULES, ARMOR_NAME_ALIASES
    rule = ARMOR_CLASS_RULES.get(ARMOR_NAME_ALIASES.get(armor, armor))
    return FAST_MOVEMENT_FT if rule is not None and rule["category"] in ("light", "medium") else 0


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


class Barbarian(ClassProgression):
    name = "Barbarian"
    supported_level = 5
    selected_asi = True

    def validate_class_fields(self, player):
        _validate_primal_knowledge(player)

    def validate_state(self, player, world):
        if not _noncaster_state_valid(player, world):
            raise ValueError("Kayıt Barbarian için kazanılmamış büyü veya alt sınıf durumu içeriyor.")

    def validate_applied(self, player, world, applied):
        if applied in (4, 5):
            import barbarian_rage
            if "rage_v1" not in world:
                raise ValueError("Selected Barbarian ASI requires retained Rage capability.")
            barbarian_rage.validate(world, player, 4, strict_active=True)

    def validate_asi_storage(self, player, *, saved):
        context = core._score_context(player, saved=saved)
        prior_con = context["base_scores"]["constitution"] + context["background_bonuses"].get("constitution", 0)
        modifier_changed = (player["constitution"] - 10) // 2 != (prior_con - 10) // 2
        ac = player.get("armor_class")
        if (type(ac) is not int or ac < 0
                or (modifier_changed and ac != _barbarian_canonical_ac(player))):
            raise ValueError("Invalid selected Barbarian ASI armor class.")

    def disclosure(self, level, *, rage_adopted=None, **_):
        supported, pending = [], []
        if rage_adopted is False:
            pending.append("Rage unavailable: this saved character has no verified unarmored Rage state; legacy state is not automatically adopted")
        else:
            supported.append(f"Rage: known-unarmored Barbarian {'1–2' if level <= 2 else '1–3' if level == 3 else '1–4' if level == 4 else '1–5'} combat Bonus activation/extension, supported attack/check/save/resistance routes and rest recovery; verified adopted state required")
        pending.append("Weapon Mastery: selections and effects remain pending (C10/C04)")
        pending.append("General armor changes and broader Unarmored Defense routes remain unsupported")
        if level >= 4:
            supported.append("Selected level4 ordinary non-DEX Ability Score Improvement supported")
            pending.append("CON modifier-changing ASI requires canonical unarmored AC (10 + DEX + CON modifiers); shield or unexplained AC extras remain unsupported for those choices")
            pending.append("Level4 third Weapon Mastery selection and effects remain pending (C10/C04)")
        if level >= 2:
            supported.extend(["Reckless Attack: explicit first own-turn attack choice and canonical advantage window supported",
                              "Danger Sense: weapon/unarmed Dexterity-save route supported"])
            pending.append("Danger Sense: other save routes remain pending (C10)")
        if level >= 3:
            supported.extend(["Selected Berserker Frenzy: first eligible own-turn Strength hit after Reckless while raging; 2d6 extra damage",
                              "Primal Knowledge: one additional class skill proficiency supported",
                              "Primal Knowledge: explicit optional Strength for selected untargeted immediate Acrobatics, Intimidation, Perception, Stealth or Survival checks while Rage is active"])
            pending.append("Primal Knowledge: Strength substitution in targeted commands, timed tasks, tracking, travel, active combat and model-only check routes remains unsupported (engine scope, not a PHB restriction)")
            pending.append("Other Barbarian subclasses and higher-level features remain unsupported")
        if level >= 5:
            supported.extend(["Extra Attack: an applied level-5 Barbarian makes two attacks instead of one when taking the Attack action on their own turn (existing attacks-per-Action allowance)",
                              "Fast Movement: +10 ft Speed while the verified unarmored state is retained (the bonus never applies in Heavy armor)"])
            pending.extend(["Fast Movement: general worn-armor tracking is unavailable; without the verified unarmored state no bonus is granted",
                            "Other extra-Action attack grants keep their own attack limit; Extra Attack does not raise them"])
        return {"supported": supported, "pending": pending}

    def adoption(self, world):
        return {"rage_adopted": "rage_v1" in world}

    def attacks_per_attack_action(self, character):
        return EXTRA_ATTACK_ATTACKS if barbarian_level_five_applied(character) else 1

    def speed_bonus_ft(self, character, world):
        return fast_movement_bonus_ft(character, world)

    def level_prerequisite(self, session, target_level):
        if target_level == 3:
            return _barbarian_three_prerequisite(session)
        if target_level == 4:
            return _barbarian_four_prerequisite(session)
        if target_level == 5:
            return _barbarian_five_prerequisite(session)
        return None


HANDLER = Barbarian()
