"""Barbarian progression: earned and starting levels 1-5 with the selected Berserker path.

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
from class_progression import noncaster
from class_progression.base import ClassProgression, EXTRA_ATTACK_ATTACKS  # noqa: F401


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
    source = core.table("Barbarian")
    if core._supported_level("Barbarian") < 2 or not isinstance(source, dict):
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
        "effects_supported": core.progression_disclosure("Barbarian", 2)["supported"],
        "effects_pending": core.progression_effects_pending("Barbarian", 2),
    }}
    three = levels.get("3")
    if (core._supported_level("Barbarian") >= 3 and isinstance(three, dict)
            and three.get("features") == ["Barbarian Subclass", "Primal Knowledge"]
            and three.get("proficiency_bonus") == 2 and three.get("rages") == 3 and three.get("rage_damage") == 2
            and three.get("weapon_mastery") == 2
            and not any(key in three for key in ("slots", "cantrips", "prepared_spells"))):
        # Source vocabulary only (not filtered per character): a malformed row 3 just omits level 3 and keeps verified 1/2.
        result["supported_starting_levels"] = [1, 2, 3]
        result["level_3"] = {
            "subclass_options": [{"id": "berserker", "name": "Path of the Berserker"}],
            "primal_knowledge_skill_options": list(BARBARIAN_SKILLS),
            "effects_supported": core.progression_disclosure("Barbarian", 3)["supported"],
            "effects_pending": core.progression_effects_pending("Barbarian", 3),
        }
        # Start 4 and 5 extend the verified prefix one row at a time: a bad row 4 hides both, a bad row 5 hides only level 5.
        asi = core.supported_asi_choices()
        if (core._supported_level("Barbarian") >= 4 and asi
                and _noncaster_start_row_ok(levels.get("4"), ["Ability Score Improvement"], 2, 3, 2, 3)):
            result["supported_starting_levels"] = [1, 2, 3, 4]
            result["level_4"] = {
                "supported_asi_choices": asi,
                "effects_supported": core.progression_disclosure("Barbarian", 4)["supported"],
                "effects_pending": core.progression_effects_pending("Barbarian", 4) + [core.HIGHER_START_EQUIPMENT_PENDING],
            }
            if (core._supported_level("Barbarian") >= 5
                    and _noncaster_start_row_ok(levels.get("5"), ["Extra Attack", "Fast Movement"], 3, 3, 2, 3)):
                result["supported_starting_levels"] = [1, 2, 3, 4, 5]
                result["level_5"] = {
                    "effects_supported": core.progression_disclosure("Barbarian", 5)["supported"],
                    "effects_pending": core.progression_effects_pending("Barbarian", 5) + [core.HIGHER_START_EQUIPMENT_PENDING],
                }
    return result


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
        return noncaster.asi_consistency_problem(character, core._barbarian_asi_options(session))
    except (ValueError, KeyError, TypeError):
        return "previous_level_three_state_invalid"
    return None


FAST_MOVEMENT_FT = 10  # Barbarian Fast Movement, features table level 5 (+10 ft Speed)


def barbarian_level_five_applied(character: Any) -> bool:
    """The only source of level-5 Barbarian features: applied level 5 of the selected Berserker (the shared entitlement)."""
    return HANDLER.extra_attack_applied(character)


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


def _check_level_choices(session, preview, choices):
    required = preview["choices_required"]
    if "asi" in required:
        asi = choices.get("asi")
        if (type(asi) is not dict or set(asi) != {"feat", "increase"}
                or asi["feat"] != "Ability Score Improvement"
                or not core._supported_asi_increase(asi["increase"])):
            return "selected_asi_not_supported"
        if asi not in core._barbarian_asi_options(session):
            return "asi_choice_not_eligible"
    if not _noncaster_state_valid(session.character, session.world_state):
        return "noncaster_state_invalid"
    if preview["to_level"] == 3:
        if set(choices) != {"subclass_id", "primal_knowledge_skill"} or choices.get("subclass_id") != "berserker":
            return "selected_barbarian_subclass_required"
        skill = choices.get("primal_knowledge_skill")
        if type(skill) is not str or skill not in BARBARIAN_SKILLS or skill in session.character["proficient_skills"]:
            return "primal_knowledge_skill_invalid"
    return None


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
        core.validate_saved(character, session.world_state)
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        session._player_state_for_save()
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        return core._reject("resulting_state_invalid")
    return {"status": "applied", "reason": None, "changes": [
        {"kind": "level", "from": 2, "to": 3}, {"kind": "hit_points", "gain": gain},
        {"kind": "skill_proficiency", "added": skill}, {"kind": "rage_capacity", "from": 2, "to": 3}],
        "effects_pending": list(preview["effects_pending"])}


class Barbarian(ClassProgression):
    name = "Barbarian"
    supported_level = 5
    selected_asi = True
    extra_attack_level = 5

    def progression_path_verified(self, character):
        return character.get("subclass_id") == "berserker"

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

    def choices_required(self, character, current, target_level, prior, goal):
        required = {}
        if target_level == 4:
            required["asi"] = 1
        if current < 3 <= target_level:
            required["subclass_id"] = 1
        if target_level == 3:
            required["primal_knowledge_skill"] = 1
        return required

    def preview_options(self, session, target_level):
        character = session.character
        if target_level == 3:
            return {"primal_knowledge_skill_options": [skill for skill in BARBARIAN_SKILLS if skill not in character["proficient_skills"]],
                    "subclass_options": [{"id": "berserker", "name": "Path of the Berserker"}]}
        if target_level == 4:
            return {"supported_asi_choices": core._barbarian_asi_options(session)}
        return {}

    def check_choices(self, session, preview, choices):
        return _check_level_choices(session, preview, choices)

    def apply_level(self, session, preview, choices):
        if preview["to_level"] == 3:
            return _apply_barbarian_three(session, preview, choices)
        if preview["to_level"] == 5:
            return noncaster.apply_earned_final_step(session, preview)
        if preview["to_level"] == 4:
            return noncaster.apply_asi_step(session, preview, choices, armor_class_ability="constitution")
        return noncaster.apply_plain_step(session, preview)

    def validate_start_choices(self, level, level_choices):
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


HANDLER = Barbarian()
