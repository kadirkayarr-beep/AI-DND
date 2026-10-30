"""Sorcerer progression: selected levels 1-5 (spell resources, Metamagic, subclass choice storage, ordinary ASI).

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
from class_progression.base import ClassProgression


def sorcerer_starting_creation_options() -> dict[str, Any] | None:
    """Detached metadata for the fixed HTTP level 1–5 choice bundle, not effects or grants."""
    from api.dnd_2024_rules import SPELLS_CATALOG

    if core.MAX_SUPPORTED_LEVEL < 5:
        return None
    source = core.table("Sorcerer")
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
            "supported_asi_choices": core.supported_asi_choices(),
        },
        "level_5": {"prepared_spell_count": 2, "prepared_spell_ids": list(spell_ids)},
        "effects_pending_by_level": {
            str(level): core.progression_effects_pending("Sorcerer", level) +
                ([core.HIGHER_START_EQUIPMENT_PENDING] if level >= 4 else [])
            for level in (1, 2, 3, 4, 5)
        },
    })


def _validate_selected_spell_mirrors(player: dict[str, Any], state: dict[str, Any]) -> None:
    if player.get("spells") != state["prepared"] or player.get("cantrips") != state["cantrips"]:
        raise ValueError("Selected ASI spell access mirrors are inconsistent.")
    # Cast/rest own world counters; the legacy character counter may lag.
    # Validate it independently, never refill authoritative world from it.
    slots, limits = player.get("spell_slots_remaining"), core.slot_capacity(player)
    if (type(slots) is not dict or set(slots) != set(limits)
            or any(type(n) is not int or not 0 <= n <= limits[k] for k, n in slots.items())):
        raise ValueError("Selected ASI slot mirror is outside applied capacity.")


def _level_four_prerequisite(session: Any) -> str | None:
    import spell_scope
    import game
    character = session.character
    if (type(character.get("progression_level")) is not int or character["progression_level"] != 3
            or type(character.get("level")) is not int or character["level"] not in (3, 4, 5)):
        return "previous_level_three_choices_required"
    if getattr(session, "_persisted_engine_format", game.SAVE_FORMAT_VERSION) not in (4, 5, 6):
        return "asi_save_version_not_supported"
    try:
        core.validate_saved(character, session.world_state)
        state = session.world_state.get("spellcasting_v1")
        spell_scope.validate(state, character)
        _validate_selected_spell_mirrors(character, state)
        core._validate_con_caches(character)
        # Replay from retained original provenance, never from current scores.
        options = core.supported_asi_choices(character)
        if not options:
            return "no_supported_asi_choices"
        increase = options[0]["increase"]
        projected = core._project_selected_asi_hp(character, 4, {"increase": increase})
        if projected["status"] != "projected":
            return projected["reason"]
        context = core._score_context(character, saved=False)
        for change in projected["feat_delta"]["changes"]:
            context["scores"][change["ability"]] = change["to"]
        context.update(level=4, applied_level=4, asi_choices=core._selected_asi_record(increase))
        check = core._check_detached_asi_consistency(**context)
        if not check["consistent"]:
            return check["reason"]
    except (ValueError, KeyError, TypeError):
        return "previous_level_three_state_invalid"
    return None


def _check_level_choices(session, preview, choices):
    from api.dnd_2024_rules import SPELLS_CATALOG
    required = preview["choices_required"]
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
                or not core._supported_asi_increase(asi["increase"])):
            return "selected_asi_not_supported"
        if asi not in core.supported_asi_choices(session.character):
            return "asi_choice_not_eligible"
        cantrips = choices.get("cantrips")
        allowed_cantrips = {s["id"] for s in SPELLS_CATALOG["Sorcerer"]["cantrips"]}
        if (type(cantrips) is not list or len(cantrips) != 1 or type(cantrips[0]) is not str
                or cantrips[0] not in allowed_cantrips or cantrips[0] in state["cantrips"]):
            return "cantrips_invalid"
    if "subclass_id" in required:
        chosen = choices.get("subclass_id")
        if not isinstance(chosen, str) or chosen not in core.table(session.character["class"]).get("subclass_options", {}):
            return "subclass_invalid"
    if "metamagic" in required:
        options = core.table(session.character["class"])["metamagic_options"]
        known = session.character.get("metamagic", [])
        picks = choices.get("metamagic", [])
        if not isinstance(picks, list) or len(picks) != required["metamagic"]:
            return "metamagic_count"
        if any(not isinstance(m, str) for m in picks) or len(set(picks)) != len(picks) or not set(picks) <= set(options) \
                or set(picks) & set(known):
            return "metamagic_invalid"
    return None


def _apply_sorcerer_level(session, preview, choices):
    import spell_scope
    character = session.character
    new_character = copy.deepcopy(character)
    state = copy.deepcopy(session.world_state["spellcasting_v1"])  # only the spell state is replaced, not the whole world
    old_cap, new_cap = core.capacity(character), preview["capacity"]
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
    new_character["proficiency_bonus"] = core.proficiency_bonus_for_level(new_character["level"])
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
        core.validate_saved(new_character, {"spellcasting_v1": state})
    except ValueError:
        return core._reject("resulting_state_invalid")
    character.clear()
    character.update(new_character)
    session.world_state["spellcasting_v1"] = state
    if points is not None:
        session.world_state[sorcery_points.KEY] = points
    changes.append({"kind": "level", "from": preview["from_level"], "to": to_level})
    return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}


def _apply_selected_level_four(session: Any, preview: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
    """Atomic selected path. Base HP is paid once; retroactive maximum never heals."""
    import spell_scope
    projection = core._project_selected_asi_hp(session.character, 4, {"increase": choices["asi"]["increase"]})
    if projection["status"] != "projected":
        return core._reject(projection["reason"])
    snapshot = session._capture_runtime_snapshot()
    had_format = "_persisted_engine_format" in session.__dict__
    previous_format = copy.deepcopy(session.__dict__.get("_persisted_engine_format"))
    try:
        character = copy.deepcopy(session.character)
        armor_class = character["armor_class"]
        state = copy.deepcopy(session.world_state["spellcasting_v1"])
        old_slots = core.capacity(character)["slots"]
        state["slots"] = {k: state["slots"].get(k, 0) + maximum - old_slots.get(k, 0)
                          for k, maximum in preview["capacity"]["slots"].items()}
        state["prepared"].extend(choices["prepared_spells"])
        state["cantrips"].extend(choices["cantrips"])
        base = projection["unpaid_base_gain"]
        character["max_hp"] += base
        if character["current_hp"] > 0:
            character["current_hp"] += base
        character.update(level=max(4, character["level"]), progression_level=4,
                         asi_choices=core._selected_asi_record(choices["asi"]["increase"]))
        core._apply_asi_score_delta(character, projection["feat_delta"])
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
        combat = session.world_state.get("combat", {})
        if combat.get("active") and session.character["armor_class"] != armor_class:
            session._sync_combat_participant_records(combat)
        spell_scope.validate(state, session.character)
        core.validate_saved(session.character, session.world_state)
        # Game owner also enforces the retained save version and serialized shape.
        session._player_state_for_save()
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        if had_format:
            session._persisted_engine_format = previous_format
        else:
            session.__dict__.pop("_persisted_engine_format", None)
        return core._reject("resulting_state_invalid")
    return {"status": "applied", "reason": None,
            "changes": [{"kind": "level", "from": 3, "to": 4},
                        {"kind": "hit_points", "gain": base},
                        {"kind": "maximum_hit_points", "gain": projection["retroactive_max_gain"]},
                        {"kind": "asi", "feat_delta": projection["feat_delta"]},
                        {"kind": "cantrips", "added": list(choices["cantrips"])},
                        {"kind": "prepared_spells", "added": list(choices["prepared_spells"])},
                        {"kind": "spell_slots", "maximum": copy.deepcopy(preview["capacity"]["slots"])}],
            "effects_pending": list(preview["effects_pending"])}


class Sorcerer(ClassProgression):
    name = "Sorcerer"
    supported_level = 5
    selected_asi = True

    def validate_applied(self, player, world, applied):
        options = core.table(player["class"]).get("subclass_options", {})
        subclass = player.get("subclass_id")
        if applied >= 3:
            if not isinstance(subclass, str) or subclass not in options:
                raise ValueError("Kayıt geçerli alt sınıf seçimi içermiyor.")
        elif "subclass_id" in player:
            raise ValueError("Kayıt kazanılmamış alt sınıf seçimi iddia ediyor.")
        known = player.get("metamagic", [])
        owed = sum(core.table(player["class"]).get("metamagic_choice_counts", {}).get(str(n), 0)
                   for n in range(2, applied + 1))
        if (not isinstance(known, list) or any(not isinstance(x, str) for x in known)
                or len(known) != owed or len(set(known)) != len(known)
                or not set(known) <= set(core.table(player["class"])["metamagic_options"])):
            raise ValueError("Kayıt Metamagic seçimleri geçersiz.")
        if applied >= 2:
            state = world.get("spellcasting_v1")
            data = core.row(player, applied)
            if (not isinstance(state, dict) or len(state.get("prepared", [])) != data["prepared_spells"]
                    or len(state.get("cantrips", [])) != data["cantrips"]):
                raise ValueError("Kayıt uygulanmamış seviye seçimleri iddia ediyor.")
            if applied in (4, 5):
                import spell_scope
                spell_scope.validate(state, player)
                _validate_selected_spell_mirrors(player, state)

    def disclosure(self, level, *, points_adopted=None, **_):
        supported, pending = [], []
        pending.append("Innate Sorcery: activation and effects are not implemented")
        if level >= 2:
            if points_adopted is False:
                pending.append("Font of Magic: Sorcery Points are not adopted in this legacy state; no load-time grant")
            else:
                supported.extend(["Font of Magic: Sorcery Points tracked; slot-to-point conversion supported; adopted state required",
                                  "Metamagic: selected Quickened Magic Missile supported; selected choice and adopted points required"])
            pending.extend(["Font of Magic: creating spell slots remains unsupported",
                            "Other Metamagic effects remain unsupported"])
        if level >= 3:
            pending.append("Sorcerer subclass features and always-prepared grants are not implemented (C19)")
        if level >= 5:
            pending.append("Sorcerous Restoration: rest recovery remains pending (C19)")
        pending.append("Optional spell, cantrip and Metamagic replacement choices remain unsupported")
        return {"supported": supported, "pending": pending}

    def adoption(self, world):
        return {"points_adopted": "sorcery_points_v1" in world}

    def capacity(self, character):
        level = core.applied_level(character)
        if level > core.MAX_SUPPORTED_LEVEL:
            return None
        data = core.row(character, level)
        return {"cantrips": data["cantrips"], "prepared_spells": data["prepared_spells"], "slots": copy.deepcopy(data["slots"]),
                "sorcery_points": data["sorcery_points"]}

    def level_prerequisite(self, session, target_level):
        return _level_four_prerequisite(session) if target_level == 4 else None

    def choices_required(self, character, current, target_level, prior, goal):
        metamagic = sum(core.table(character["class"]).get("metamagic_choice_counts", {}).get(str(level), 0)
                        for level in range(current + 1, target_level + 1))
        required = {"prepared_spells": goal["prepared_spells"] - prior["prepared_spells"]}
        if target_level == 4:
            required.update(cantrips=1, asi=1)
        if metamagic:
            required["metamagic"] = metamagic
        if current < 3 <= target_level:
            required["subclass_id"] = 1
        return required

    def preview_capacity(self, goal):
        return {"cantrips": goal["cantrips"], "prepared_spells": goal["prepared_spells"], "slots": copy.deepcopy(goal["slots"]),
                "sorcery_points": goal["sorcery_points"]}

    def preview_options(self, session, target_level):
        return {"supported_asi_choices": core.supported_asi_choices(session.character)} if target_level == 4 else {}

    def check_choices(self, session, preview, choices):
        return _check_level_choices(session, preview, choices)

    def apply_level(self, session, preview, choices):
        if preview["to_level"] == 4:
            return _apply_selected_level_four(session, preview, choices)
        return _apply_sorcerer_level(session, preview, choices)

    def validate_start_choices(self, level, level_choices):
        """The real step owners check the bundle."""


HANDLER = Sorcerer()
