"""Paladin progression: earned and starting levels 1-5 with the selected Oath of Devotion. Effects live in paladin_features.

Facts are read from content/rules/phb2024/classes/paladin.json. Shared helpers are read through `core.` at call time, because this
module loads while character_progression is still loading and tests patch names there (`table`, `validate_saved`, ...).
Spell state stays spell_scope's `spellcasting_v1`; the slot and prepared steps follow the Sorcerer path. One function applies every
level because each one is the same atomic transaction with different choices.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
import paladin_features as features
from class_progression import noncaster
from class_progression.base import ClassProgression

DEVOTION_SOURCE_KEY = "phb2024:subclass:paladin:oath-of-devotion"
SUBCLASS_LEVEL = 3
FIRST_ASI_LEVEL = 4
LAST_LEVEL = 5
MASTERY_PENDING = "Weapon Mastery: selections and effects remain pending (C10/C04)"
FIGHTING_STYLES = ("Archery", "Defense", "Dueling", "Great Weapon Fighting", "Two-Weapon Fighting")
# Exact source rows through level 5 (Paladin Features table, PDF 109): features, Proficiency Bonus, Channel Divinity, Prepared Spells, slots.
SOURCE_ROWS = {1: (["Lay On Hands", "Spellcasting", "Weapon Mastery"], 2, None, 2, {"1": 2}),
               2: (["Fighting Style", "Paladin's Smite"], 2, None, 3, {"1": 2}),
               3: (["Channel Divinity", "Paladin Subclass"], 2, 2, 4, {"1": 3}),
               4: (["Ability Score Improvement"], 2, 2, 5, {"1": 3}),
               5: (["Extra Attack", "Faithful Steed"], 3, 2, 6, {"1": 4, "2": 2})}


def _row_ok(row: Any, level: int) -> bool:
    """Exact source row: ints only (no bool), no column of another class; anything else hides the level."""
    features_row, bonus, channel, prepared, slots = SOURCE_ROWS[level]
    return (isinstance(row, dict) and row.get("features") == features_row
            and type(row.get("proficiency_bonus")) is int and row["proficiency_bonus"] == bonus
            and "channel_divinity" in row and row["channel_divinity"] == channel and type(row["channel_divinity"]) is type(channel)
            and type(row.get("prepared_spells")) is int and row["prepared_spells"] == prepared
            and row.get("slots") == slots and all(type(value) is int for value in slots.values())
            and all(type(value) is int for value in row["slots"].values())
            and not any(key in row for key in ("cantrips", "second_wind", "weapon_mastery")))


def _spell_ids(level: int) -> list[str]:
    from api.dnd_2024_rules import SPELLS_CATALOG
    return [spell["id"] for spell in SPELLS_CATALOG["Paladin"]["spells_level_2" if level >= 5 else "spells_level_1"]]


def _allowed_ids(level: int) -> list[str]:
    """Paladin spells of a level the character has slots for at this class level (PDF 108): level 2 spells open with the level 2 slots."""
    return _spell_ids(1) + (_spell_ids(5) if level >= 5 else [])


def _cantrip_ids() -> list[str]:
    from api.dnd_2024_rules import SPELLS_CATALOG
    return [spell["id"] for spell in SPELLS_CATALOG["Cleric"]["cantrips"]]


def _subclass_options() -> list[dict[str, str]] | None:
    source = core.table("Paladin")
    entry = source.get("subclass_options", {}).get(DEVOTION_SOURCE_KEY) if isinstance(source, dict) else None
    name = entry.get("name") if isinstance(entry, dict) else None
    return [{"id": features.SUBCLASS, "name": name}] if type(name) is str and name else None


def _offered(level: int, oath: bool) -> list[str]:
    always = features.always_prepared(level, oath)
    return [identity for identity in _allowed_ids(level) if identity not in always]


def _scope(level: int) -> dict[str, list[str]]:
    pending = core.progression_effects_pending("Paladin", level)
    return {"effects_supported": core.progression_disclosure("Paladin", level)["supported"],
            "effects_pending": pending + ([core.HIGHER_START_EQUIPMENT_PENDING] if level >= FIRST_ASI_LEVEL else [])}


def paladin_starting_creation_options() -> dict[str, Any] | None:
    """Detached capability offered one verified row at a time: a bad row hides that level and everything above it."""
    source = core.table("Paladin")
    levels = source.get("levels") if isinstance(source, dict) else None
    if (core._supported_level("Paladin") < 2 or not isinstance(levels, dict)
            or not _row_ok(levels.get("1"), 1) or not _row_ok(levels.get("2"), 2)):
        return None
    cantrips = _cantrip_ids()
    if len(set(cantrips)) < features.BLESSED_WARRIOR_CANTRIPS or len(set(_offered(5, True))) < 4:
        return None
    result: dict[str, Any] = {"supported_starting_levels": [1, 2], "level_2": {
        "prepared_spell_count": 1, "prepared_spell_ids": _offered(2, False), "fighting_style_options": [*FIGHTING_STYLES, features.BLESSED_WARRIOR],
        "blessed_warrior_cantrip_count": features.BLESSED_WARRIOR_CANTRIPS, "blessed_warrior_cantrip_ids": cantrips, **_scope(2)}}
    subclasses = _subclass_options()
    if not subclasses or not _row_ok(levels.get("3"), 3):
        return result
    result["supported_starting_levels"].append(3)
    result["level_3"] = {"prepared_spell_count": 1, "prepared_spell_ids": _offered(3, True), "subclass_options": subclasses, **_scope(3)}
    asi = core.supported_asi_choices()
    if not asi or not _row_ok(levels.get("4"), 4):
        return result
    result["supported_starting_levels"].append(4)
    result["level_4"] = {"prepared_spell_count": 1, "prepared_spell_ids": _offered(4, True), "supported_asi_choices": asi, **_scope(4)}
    if _row_ok(levels.get("5"), 5):
        result["supported_starting_levels"].append(5)
        result["level_5"] = {"prepared_spell_count": 1, "prepared_spell_ids": _offered(5, True), **_scope(5)}
    return copy.deepcopy(result)


def _asi_options(session) -> list[dict[str, Any]]:
    character = session.character
    return [option for option in core.supported_asi_choices(character)
            if core._project_selected_asi_hp(character, FIRST_ASI_LEVEL, {"increase": option["increase"]})["status"] == "projected"]


def _prerequisite(session, target_level: int) -> str | None:
    import spell_scope
    character = session.character
    if "progression_level" in character and type(character["progression_level"]) is not int:
        return "previous_paladin_state_invalid"
    if character.get("progression_level", 1) != target_level - 1:
        return "previous_level_choices_required"
    state = session.world_state.get("spellcasting_v1")
    if not isinstance(state, dict):
        return "paladin_spell_state_required"  # only creation grants spell access; nothing is manufactured here
    try:
        core.validate_saved(character, session.world_state)
        spell_scope.validate(state, character)
        if len(state["prepared"]) != core.row(character, target_level - 1)["prepared_spells"]:
            return "previous_paladin_state_invalid"
        if target_level == FIRST_ASI_LEVEL:
            core._validate_con_caches(character)
            return noncaster.asi_consistency_problem(character, _asi_options(session))
    except (ValueError, KeyError, TypeError):
        return "previous_paladin_state_invalid"
    return None


def _check_prepared(session, preview, choices) -> str | None:
    picked = choices.get("prepared_spells", [])
    if type(picked) is not list or len(picked) != preview["choices_required"]["prepared_spells"]:
        return "prepared_spells_count"
    state = session.world_state["spellcasting_v1"]
    if (any(type(identity) is not str for identity in picked) or len(set(picked)) != len(picked)
            or not set(picked) <= set(preview["prepared_spell_ids"]) or set(picked) & set(state["prepared"])):
        return "prepared_spells_invalid"
    return None


def _check_style(choices) -> str | None:
    style = choices.get("fighting_style")
    if type(style) is not str or style not in (*FIGHTING_STYLES, features.BLESSED_WARRIOR):
        return "fighting_style_invalid"
    picked = choices.get("cantrips")
    if style != features.BLESSED_WARRIOR:
        return "blessed_warrior_cantrips_invalid" if picked is not None else None
    if (type(picked) is not list or len(picked) != features.BLESSED_WARRIOR_CANTRIPS or any(type(identity) is not str for identity in picked)
            or len(set(picked)) != len(picked) or not set(picked) <= set(_cantrip_ids())):
        return "blessed_warrior_cantrips_invalid"
    return None


def _armor_worn(character: dict[str, Any]) -> bool:
    """The creation calculator's reading of carried equipment, the same one the Fighter's Defense total used."""
    from api.dnd_2024_rules import get_equipment_armor_and_shield
    armor, _ = get_equipment_armor_and_shield(character.get("equipment_choices"))
    return armor is not None


def _step_changes(character, state, preview, choices) -> list[dict[str, Any]]:
    """The caster half of a level: prepared list, slots (the table adds, nothing refills) and the mirrors."""
    old_slots = core.capacity(character)["slots"]
    state["prepared"].extend(choices["prepared_spells"])
    new_slots = preview["capacity"]["slots"]
    state["slots"] = {key: state["slots"].get(key, 0) + maximum - old_slots.get(key, 0) for key, maximum in new_slots.items()}
    if choices.get("cantrips"):
        state["cantrips"].extend(choices["cantrips"])
    character["spells"] = list(state["prepared"])
    character["cantrips"] = list(state["cantrips"])
    character["spell_slots_remaining"] = copy.deepcopy(state["slots"])
    changes = [{"kind": "prepared_spells", "added": list(choices["prepared_spells"])},
               {"kind": "spell_slots", "maximum": copy.deepcopy(new_slots)}]
    if choices.get("cantrips"):
        changes.append({"kind": "cantrips", "added": list(choices["cantrips"])})
    return changes


def _apply(session, preview, choices):
    """One atomic level: everything is built on copies, written, then validated as a whole; a refusal restores the snapshot."""
    import spell_scope
    target = preview["to_level"]
    projection = None
    if target == FIRST_ASI_LEVEL:
        projection = core._project_selected_asi_hp(session.character, FIRST_ASI_LEVEL, {"increase": choices["asi"]["increase"]})
        if projection["status"] != "projected":
            return core._reject(projection["reason"])
    snapshot = session._capture_runtime_snapshot()
    captured = noncaster._capture_format(session)
    try:
        character = copy.deepcopy(session.character)
        state = copy.deepcopy(session.world_state["spellcasting_v1"])
        changes = _step_changes(character, state, preview, choices)
        gain = projection["unpaid_base_gain"] if projection else 0 if preview["hit_points"]["already_applied"] else preview["hit_points"]["gain"]
        character["max_hp"] += gain
        if character["current_hp"] > 0:
            character["current_hp"] += gain
        character.update(level=max(target, character["level"]), progression_level=target)
        character["proficiency_bonus"] = core.proficiency_bonus_for_level(character["level"])
        changes.append({"kind": "hit_points", "gain": gain})
        if "fighting_style" in choices:
            character["fighting_style"] = choices["fighting_style"]
            changes.append({"kind": "fighting_style", "id": choices["fighting_style"]})
            if choices["fighting_style"] == "Defense" and _armor_worn(character):
                character["armor_class"] += 1  # the same creation-total reading the Fighter's Defense has
        if target == SUBCLASS_LEVEL:
            character["subclass_id"] = features.SUBCLASS
            changes.append({"kind": "subclass", "id": features.SUBCLASS})
        if projection:
            character["asi_choices"] = core._selected_asi_record(choices["asi"]["increase"])
            core._apply_asi_score_delta(character, projection["feat_delta"])
            changes.extend([{"kind": "maximum_hit_points", "gain": projection["retroactive_max_gain"]},
                            {"kind": "asi", "feat_delta": projection["feat_delta"]}])
        session.character.clear()
        session.character.update(character)
        session.world_state["spellcasting_v1"] = state
        if projection:
            session.set_player_max_hp(projection["resulting_maximum"])
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        spell_scope.validate(state, session.character)
        core.validate_saved(session.character, session.world_state)
        session._validate_save_payload(session.serialize_game_state())
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        noncaster._restore_format(session, captured)
        return core._reject("resulting_state_invalid")
    changes.append({"kind": "level", "from": preview["from_level"], "to": target})
    return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}


def _catalog_only_note(level: int) -> str:
    return ("Paladin spells may be prepared at the table's counts, but only Cure Wounds has a resolver: every other prepared spell is "
            "catalog-only and has no effect in play yet")


class Paladin(ClassProgression):
    name = "Paladin"
    supported_level = LAST_LEVEL
    selected_asi = True
    extra_attack_level = 5
    class_weapon_proficiencies = ("simple", "martial")

    def progression_path_verified(self, character):
        return character.get("subclass_id") == features.SUBCLASS

    def validate_class_fields(self, player):
        features.validate_saved(player)

    def validate_state(self, player, world):
        progression = player.get("progression_level")
        if (any(key in world for key in ("sorcery_points_v1", "rage_v1")) or player.get("metamagic")
                or ("subclass_id" in player and (type(progression) is not int or progression < SUBCLASS_LEVEL
                                                 or player["subclass_id"] != features.SUBCLASS))):
            raise ValueError("Kayıt Paladin için kazanılmamış Rage, Sorcery veya alt sınıf durumu içeriyor.")
        features.validate_clock_bounds(player, world)

    def validate_applied(self, player, world, applied):
        import spell_scope
        if (applied >= SUBCLASS_LEVEL) != ("subclass_id" in player):
            raise ValueError("Kayıt Paladin alt sınıfı uygulanmış seviyeyle uyuşmuyor.")
        style = player.get("fighting_style")
        if (applied >= features.STYLE_LEVEL) != (style is not None) or (style is not None and style not in (*FIGHTING_STYLES, features.BLESSED_WARRIOR)):
            raise ValueError("Kayıt Paladin dövüş tarzı uygulanmış seviyeyle uyuşmuyor.")
        if applied >= features.STYLE_LEVEL:
            state = world.get("spellcasting_v1")
            limits = self.capacity(player)
            if (not isinstance(state, dict) or len(state.get("prepared", [])) != limits["prepared_spells"]
                    or len(state.get("cantrips", [])) != limits["cantrips"]):
                raise ValueError("Kayıt uygulanmamış Paladin seviye seçimleri iddia ediyor.")
            spell_scope.validate(state, player)

    def disclosure(self, level, **_):
        supported = [
            f"Lay On Hands: a pool of {features.pool_maximum(level)} Hit Points, Bonus Action on your own combat turn or outside combat, "
            "5 points remove your Poisoned condition, the pool refills on a Long Rest",
            "Spellcasting: spell slots and prepared spells follow the Paladin Features table; a Long Rest restores slots; Charisma is the ability",
        ]
        pending = [
            MASTERY_PENDING,
            _catalog_only_note(level),
            "Lay On Hands: only yourself; touching another creature has no healing owner yet",
            "Prepared spells: replacing a spell on a Long Rest remains pending",
            "Spellcasting: the existing spell path needs a free hand; a Holy Symbol on a Shield as a focus is not modelled",
            "Paladin equipment packages are the existing catalog lists, not yet the PHB packages",
            "Weapon proficiency: a Paladin with no stored list has Simple and Martial, worked out at each attack and never written back",
        ]
        if level >= 2:
            supported.extend([
                "Fighting Style: Archery, Defense, Dueling, Great Weapon Fighting and Two-Weapon Fighting apply; Defense raises the Armor Class total once when the step is taken in armor",
                "Blessed Warrior: two Cleric cantrips with Charisma; Sacred Flame has a resolver, others are catalog-only",
                "Paladin's Smite: Divine Smite always prepared, a Bonus Action right after a Melee weapon or Unarmed Strike hit, 2d8 Radiant, +1d8 per slot level above 1, "
                "+1d8 against a Fiend or Undead with a sourced type; one cast without a slot per Long Rest",
            ])
            pending.extend([
                "Fighting Style: replacing the feat on a Paladin level, Protection and the feats not offered remain pending",
                "Blessed Warrior: replacing a cantrip on a Paladin level remains pending",
                "Divine Smite: the dice are not doubled by a Critical Hit (the attack's own dice are); a thrown Melee weapon counts as a reading of the spell, not a stated rule",
                "Divine Smite: only on your own turn after a hit by the engine's attack owner; other Smite spells are catalog-only",
            ])
        if level >= 3:
            supported.extend([
                "Channel Divinity: two uses, one back on a Short Rest, all on a Long Rest",
                "Divine Sense: Bonus Action, 10 minutes, ends at Incapacitated; lists Celestials, Fiends and Undead with a sourced type within 60 feet among combat participants",
                "Selected Oath of Devotion Sacred Weapon: on the Attack action, a held Melee weapon adds your Charisma modifier (minimum +1) to attacks for 10 minutes and may deal Radiant damage",
                "Oath of Devotion spells are listed as always prepared: Protection from Evil and Good, Shield of Faith",
            ])
            pending.extend([
                "Divine Sense: detection outside combat and consecrated or desecrated places remain unsupported; a Stun that ends between your commands is not seen",
                "Sacred Weapon: its light and ending it early remain pending; two identical unnamed weapons share one identity",
                "Oath of Devotion spells have no resolver; the Oath's later features and the other Oaths remain unsupported",
            ])
        if level >= 4:
            supported.append("Selected level4 ordinary non-DEX Ability Score Improvement supported")
            pending.append("DEX Ability Score Improvement and other feats remain unsupported")
        if level >= 5:
            supported.append("Extra Attack: an applied level-5 Paladin makes two attacks instead of one when taking the Attack action on their own turn")
            pending.append("Faithful Steed: Find Steed is listed as always prepared; casting it, the free cast and the steed itself remain pending (no summon owner, no resolver)")
            pending.append("Oath of Devotion Aid and Zone of Truth are listed as always prepared and have no resolver")
        return {"supported": supported, "pending": pending}

    def capacity(self, character):
        level = core.applied_level(character)
        if level > core.MAX_SUPPORTED_LEVEL:
            return None
        data = core.row(character, level)
        return {"cantrips": features.BLESSED_WARRIOR_CANTRIPS if character.get("fighting_style") == features.BLESSED_WARRIOR else 0,
                "prepared_spells": data["prepared_spells"], "slots": copy.deepcopy(data["slots"])}

    def extra_spell_ids(self, character, field):
        if field == "cantrips":
            return set(_cantrip_ids()) if character.get("fighting_style") == features.BLESSED_WARRIOR else set()
        return set(_spell_ids(5)) if core.applied_level(character) >= 5 else set()

    def level_prerequisite(self, session, target_level):
        return _prerequisite(session, target_level)

    def choices_required(self, character, current, target_level, prior, goal):
        required = {"prepared_spells": goal["prepared_spells"] - prior["prepared_spells"]}
        if target_level == features.STYLE_LEVEL:
            required.update(fighting_style=1, cantrips=features.BLESSED_WARRIOR_CANTRIPS)  # cantrips only with Blessed Warrior
        if target_level == SUBCLASS_LEVEL:
            required["subclass_id"] = 1
        if target_level == FIRST_ASI_LEVEL:
            required["asi"] = 1
        return required

    def preview_capacity(self, goal):
        return {"prepared_spells": goal["prepared_spells"], "slots": copy.deepcopy(goal["slots"])}

    def preview_options(self, session, target_level):
        oath = target_level >= SUBCLASS_LEVEL
        options: dict[str, Any] = {"prepared_spell_ids": [identity for identity in _offered(target_level, oath)
                                                          if identity not in session.world_state.get("spellcasting_v1", {}).get("prepared", [])]}
        if target_level == features.STYLE_LEVEL:
            options.update(fighting_style_options=[*FIGHTING_STYLES, features.BLESSED_WARRIOR], blessed_warrior_cantrip_ids=_cantrip_ids())
        if target_level == SUBCLASS_LEVEL:
            options["subclass_options"] = _subclass_options() or []
        if target_level == FIRST_ASI_LEVEL:
            options["supported_asi_choices"] = _asi_options(session)
        return options

    def check_choices(self, session, preview, choices):
        required = preview["choices_required"]
        problem = _check_prepared(session, preview, choices)
        if problem:
            return problem
        if "fighting_style" in required:
            problem = _check_style(choices)
            if problem:
                return problem
        if "subclass_id" in required and not any(option["id"] == choices.get("subclass_id") for option in preview["subclass_options"]):
            return "selected_paladin_subclass_required"
        if "asi" in required:
            asi = choices.get("asi")
            if (type(asi) is not dict or set(asi) != {"feat", "increase"} or asi["feat"] != "Ability Score Improvement"
                    or not core._supported_asi_increase(asi["increase"])):
                return "selected_asi_not_supported"
            if asi not in _asi_options(session):
                return "asi_choice_not_eligible"
        return None

    def apply_level(self, session, preview, choices):
        return _apply(session, preview, choices)

    def prepare_rest(self, session):
        features.validate_saved(session.character)

    def rest_recovery(self, session, kind):
        features.rest_recovery(session, kind)

    def validate_start_choices(self, level, level_choices):
        if level > LAST_LEVEL:
            raise ValueError("progression_level_not_supported")
        wanted = {str(n) for n in range(2, level + 1)}
        required = f"paladin_level_{level}_choices_required"
        if type(level_choices) is not dict or set(level_choices) != wanted or any(type(v) is not dict for v in level_choices.values()):
            raise ValueError(required)
        shapes = {"2": {"prepared_spells", "fighting_style"}, "3": {"prepared_spells", "subclass_id"},
                  "4": {"prepared_spells", "asi"}, "5": {"prepared_spells"}}
        for key, value in level_choices.items():
            if set(value) - {"cantrips"} != shapes[key] or (key != "2" and "cantrips" in value):
                raise ValueError(required)


HANDLER = Paladin()
