"""Shared Wizard/Cleric progression 1-5 (4C.3): the steps of a class that prepares its spells in the preparation window.

Every number comes from content/rules/phb2024/classes/<class>.json (slots, cantrip and prepared counts); spells of level 2 and 3
come from content/rules/phb2024/spells.json (class lists with page-backed levels; catalog-only, no resolver). A level step never
chooses a spell: it raises the limit and opens the preparation window (`spell_preparation`), which stands until the player's
first list, as the creation window does. PHB 2024: Wizard Spellcasting PDF 164-165, Cleric Spellcasting PDF 68 ("choose
additional spells" when the Prepared Spells number grows, of a level for which you have spell slots).
Shared helpers are read through `core.` at call time (this module loads while character_progression is still loading).
"""
from __future__ import annotations

import copy
import functools
import json
from pathlib import Path
from typing import Any

import character_progression as core
from class_progression import noncaster
from class_progression.base import ClassProgression

SUBCLASS_LEVEL = 3
FIRST_ASI_LEVEL = 4
LAST_LEVEL = 5
_SPELLS = Path(__file__).resolve().parents[2] / "content" / "rules" / "phb2024" / "spells.json"


@functools.lru_cache(maxsize=1)
def _source_spells() -> dict[str, Any]:
    return json.loads(_SPELLS.read_text(encoding="utf-8"))["spells"]


def source_spell_ids(class_name: str, spell_level: int) -> list[str]:
    """The class's spells of one level from the PHB spell index (level 2+; level 1 stays the creation catalog)."""
    return sorted(name for name, spell in _source_spells().items()
                  if spell.get("level") == spell_level and class_name in spell.get("classes", []))


def catalog_ids(class_name: str, field: str) -> list[str]:
    from api.dnd_2024_rules import SPELLS_CATALOG
    return [spell["id"] for spell in SPELLS_CATALOG[class_name][field]]


def slot_levels(class_name: str, level: int) -> list[int]:
    return sorted(int(key) for key in core.table(class_name)["levels"][str(level)]["slots"])


def spell_ids_up_to(class_name: str, level: int) -> list[str]:
    """Level 1+ spells of a level the class has slots for at `level`: the creation's level-1 list, then the source lists."""
    return catalog_ids(class_name, "spells_level_1") + [identity for spell_level in slot_levels(class_name, level)
                                                        if spell_level >= 2 for identity in source_spell_ids(class_name, spell_level)]


class PreparedCaster(ClassProgression):
    """Wizard and Cleric. A subclass supplies `name`, `subclass` (short id, source key) and its disclosure lines."""
    supported_level = LAST_LEVEL
    selected_asi = True
    subclass: tuple[str, str] = ("", "")
    keeps_spellbook = False

    # --- views -------------------------------------------------------------------------------------------------------
    def capacity(self, character):
        level = core.applied_level(character)
        if level > core.MAX_SUPPORTED_LEVEL:
            return None
        data = core.row(character, level)
        return {"cantrips": data["cantrips"], "prepared_spells": data["prepared_spells"], "slots": copy.deepcopy(data["slots"])}

    def extra_spell_ids(self, character, field):
        if field != "prepared":
            return set()
        level = min(core.applied_level(character), core.MAX_SUPPORTED_LEVEL)
        return {identity for spell_level in slot_levels(self.name, level) if spell_level >= 2
                for identity in source_spell_ids(self.name, spell_level)}

    def subclass_options(self) -> list[dict[str, str]]:
        short, key = self.subclass
        entry = core.table(self.name).get("subclass_options", {}).get(key)
        name = entry.get("name") if isinstance(entry, dict) else None
        return [{"id": short, "name": name}] if isinstance(name, str) and name else []

    def book_size(self, level: int) -> int:
        """A spellbook's size after the applied level (Wizard only)."""
        raise NotImplementedError

    # --- saved state -------------------------------------------------------------------------------------------------
    def validate_state(self, player, world):
        progression = player.get("progression_level")
        if (any(key in world for key in ("sorcery_points_v1", "rage_v1")) or player.get("metamagic")
                or ("subclass_id" in player and (type(progression) is not int or progression < SUBCLASS_LEVEL
                                                 or player["subclass_id"] != self.subclass[0]))):
            raise ValueError(f"Kayıt {self.name} için kazanılmamış Rage, Sorcery veya alt sınıf durumu içeriyor.")

    def validate_applied(self, player, world, applied):
        import spell_scope
        if (applied >= SUBCLASS_LEVEL) != ("subclass_id" in player):
            raise ValueError(f"Kayıt {self.name} alt sınıfı uygulanmış seviyeyle uyuşmuyor.")
        if applied < 2:
            return  # level 1 is the creation's own state (old saves included); spell_scope.validate owns it
        state = world.get("spellcasting_v1")
        limits = self.capacity(player)
        if (not isinstance(state, dict) or state.get("version") != 2 or len(state.get("cantrips", [])) != limits["cantrips"]
                or (self.keeps_spellbook and len(state.get("spellbook") or []) != self.book_size(applied))):
            raise ValueError(f"Kayıt uygulanmamış {self.name} seviye seçimleri iddia ediyor.")
        spell_scope.validate(state, player)

    # --- level steps -------------------------------------------------------------------------------------------------
    def _asi_options(self, session) -> list[dict[str, Any]]:
        character = session.character
        return [option for option in core.supported_asi_choices(character, session.world_state)
                if core._project_selected_asi_hp(character, FIRST_ASI_LEVEL, {"increase": option["increase"]})["status"] == "projected"]

    def level_prerequisite(self, session, target_level):
        import spell_scope
        character = session.character
        if "progression_level" in character and type(character["progression_level"]) is not int:
            return f"previous_{self.name.lower()}_state_invalid"
        current = character.get("progression_level", 1)
        if current != target_level - 1:
            return "previous_level_choices_required"
        state = session.world_state.get("spellcasting_v1")
        if self.keeps_spellbook and isinstance(state, dict) and state.get("version") == 1:
            return "wizard_spellbook_missing"  # an old save with no creation spells (D-039): the engine never writes a book
        if not isinstance(state, dict) or state.get("version") != 2:
            return f"previous_{self.name.lower()}_state_invalid"
        try:
            core.validate_saved(character, session.world_state)
            spell_scope.validate(state, character)
            if (len(state["cantrips"]) != core.row(character, current)["cantrips"]
                    or (self.keeps_spellbook and len(state["spellbook"]) != self.book_size(current))):
                return f"previous_{self.name.lower()}_state_invalid"
            if target_level == FIRST_ASI_LEVEL:
                core._validate_con_caches(character)
                return noncaster.asi_consistency_problem(character, self._asi_options(session))
        except (ValueError, KeyError, TypeError):
            return f"previous_{self.name.lower()}_state_invalid"
        return None

    def step_choices(self, target_level: int) -> dict[str, int]:
        """Choices of this class's own besides subclass/ASI/cantrips (the Wizard's spellbook)."""
        return {}

    def choices_required(self, character, current, target_level, prior, goal):
        required = self.step_choices(target_level)
        if target_level == SUBCLASS_LEVEL:
            required["subclass_id"] = 1
        if target_level == FIRST_ASI_LEVEL:
            required["asi"] = 1
        if goal["cantrips"] > prior["cantrips"]:
            required["cantrips"] = goal["cantrips"] - prior["cantrips"]
        return required

    def preview_capacity(self, goal):
        return {"cantrips": goal["cantrips"], "prepared_spells": goal["prepared_spells"], "slots": copy.deepcopy(goal["slots"])}

    def step_options(self, session, target_level) -> dict[str, Any]:
        return {}

    def preview_options(self, session, target_level):
        options = self.step_options(session, target_level)
        if target_level == SUBCLASS_LEVEL:
            options["subclass_options"] = self.subclass_options()
        if target_level == FIRST_ASI_LEVEL:
            options["supported_asi_choices"] = self._asi_options(session)
        known = session.world_state.get("spellcasting_v1", {}).get("cantrips", [])
        if core.row(session.character, target_level)["cantrips"] > core.row(session.character, target_level - 1)["cantrips"]:
            options["cantrip_ids"] = [identity for identity in catalog_ids(self.name, "cantrips") if identity not in known]
        return options

    def check_step(self, session, preview, choices) -> str | None:
        return None

    def check_choices(self, session, preview, choices):
        required = preview["choices_required"]
        problem = self.check_step(session, preview, choices)
        if problem:
            return problem
        if "subclass_id" in required and not any(option["id"] == choices.get("subclass_id") for option in preview["subclass_options"]):
            return "subclass_invalid"
        if "cantrips" in required:
            picked = choices.get("cantrips")
            if (type(picked) is not list or len(picked) != required["cantrips"] or any(type(identity) is not str for identity in picked)
                    or len(set(picked)) != len(picked) or not set(picked) <= set(preview["cantrip_ids"])):
                return "cantrips_invalid"
        if "asi" in required:
            asi = choices.get("asi")
            if (type(asi) is not dict or set(asi) != {"feat", "increase"} or asi["feat"] != "Ability Score Improvement"
                    or not core._supported_asi_increase(asi["increase"])):
                return "selected_asi_not_supported"
            if asi not in preview["supported_asi_choices"]:
                return "asi_choice_not_eligible"
        return None

    def apply_step(self, state, choices) -> list[dict[str, Any]]:
        """This class's own part of a step on the copied spell state (the Wizard's spellbook)."""
        return []

    def apply_level(self, session, preview, choices):
        """One atomic level: built on copies, written, then validated as a whole; a refusal restores the snapshot."""
        import spell_preparation
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
            old_slots = core.capacity(character)["slots"]
            new_slots = preview["capacity"]["slots"]
            state["slots"] = {key: state["slots"].get(key, 0) + maximum - old_slots.get(key, 0) for key, maximum in new_slots.items()}
            changes = [{"kind": "spell_slots", "maximum": copy.deepcopy(new_slots)},
                       {"kind": "prepared_spells_limit", "maximum": preview["capacity"]["prepared_spells"]}]
            changes.extend(self.apply_step(state, choices))
            if choices.get("cantrips"):
                state["cantrips"].extend(choices["cantrips"])
                changes.append({"kind": "cantrips", "added": list(choices["cantrips"])})
            window = state["prepare_window"]
            if window is None or window["reason"] not in spell_preparation.STANDING:
                # The grown list is chosen by the player in a window that waits for the first list (PHB: choose additional spells).
                state["prepare_window"] = {"opened_second": spell_scope.clock_second(session.world_state), "reason": "level_up"}
            character["cantrips"] = list(state["cantrips"])
            character["spell_slots_remaining"] = copy.deepcopy(state["slots"])
            gain = (projection["unpaid_base_gain"] if projection
                    else 0 if preview["hit_points"]["already_applied"] else preview["hit_points"]["gain"])
            character["max_hp"] += gain
            if character["current_hp"] > 0:
                character["current_hp"] += gain
            character.update(level=max(target, character["level"]), progression_level=target)
            character["proficiency_bonus"] = core.proficiency_bonus_for_level(character["level"])
            changes.append({"kind": "hit_points", "gain": gain})
            if target == SUBCLASS_LEVEL:
                character["subclass_id"] = choices["subclass_id"]
                changes.append({"kind": "subclass", "id": choices["subclass_id"], "effects_applied": False})
            if projection:
                character["asi_choices"] = core._selected_asi_record(choices["asi"]["increase"])
                core._apply_asi_score_delta(character, projection["feat_delta"], session.world_state)
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

    def start_shapes(self) -> dict[str, set[str]]:
        raise NotImplementedError

    def validate_start_choices(self, level, level_choices):
        if level > LAST_LEVEL:
            raise ValueError("progression_level_not_supported")
        wanted = {str(n) for n in range(2, level + 1)}
        required = f"{self.name.lower()}_level_{level}_choices_required"
        if type(level_choices) is not dict or set(level_choices) != wanted or any(type(v) is not dict for v in level_choices.values()):
            raise ValueError(required)
        shapes = self.start_shapes()
        for key, value in level_choices.items():
            if set(value) != shapes[key]:
                raise ValueError(required)
