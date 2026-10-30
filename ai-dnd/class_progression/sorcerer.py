"""Sorcerer progression: selected levels 1-5 (spell resources, Metamagic, subclass choice storage, ordinary ASI).

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
from class_progression.base import ClassProgression


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


HANDLER = Sorcerer()
