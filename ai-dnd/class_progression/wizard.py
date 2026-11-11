"""Wizard progression 1-5 (4C.3). Facts: content/rules/phb2024/classes/wizard.json (Wizard Features table, PDF 165).

Spellbook (PDF 164): it starts with six level-1 Wizard spells (the creation selections) and, whenever you gain a Wizard level after
1, you add two Wizard spells of your choice of a level for which you have spell slots. Prepared spells are chosen from the book in
the preparation window (`spell_preparation`). Level 3: Evoker is the one subclass offered (approved decision 5); its features are pending.
"""
from __future__ import annotations

from typing import Any

from class_progression import prepared_caster as caster

BOOK_AT_CREATION = 6  # PDF 164: the book starts with six level 1 Wizard spells (the creation's spells_count)
BOOK_PER_LEVEL = 2  # PDF 164: two Wizard spells added at each Wizard level after 1


class Wizard(caster.PreparedCaster):
    name = "Wizard"
    subclass = ("evoker", "phb2024:subclass:wizard:evoker")
    keeps_spellbook = True

    def book_size(self, level):
        return BOOK_AT_CREATION + BOOK_PER_LEVEL * (level - 1)

    def step_choices(self, target_level):
        return {"spellbook_spells": BOOK_PER_LEVEL}

    def step_options(self, session, target_level):
        book = session.world_state.get("spellcasting_v1", {}).get("spellbook") or []
        return {"spellbook_spell_ids": [identity for identity in caster.spell_ids_up_to(self.name, target_level) if identity not in book]}

    def check_step(self, session, preview, choices):
        picked = choices.get("spellbook_spells")
        if (type(picked) is not list or len(picked) != preview["choices_required"]["spellbook_spells"]
                or any(type(identity) is not str for identity in picked) or len(set(picked)) != len(picked)
                or not set(picked) <= set(preview["spellbook_spell_ids"])):
            return "spellbook_spells_invalid"
        return None

    def apply_step(self, state, choices) -> list[dict[str, Any]]:
        state["spellbook"] = [*state["spellbook"], *choices["spellbook_spells"]]
        return [{"kind": "spellbook", "added": list(choices["spellbook_spells"])}]

    def start_shapes(self):
        return {"2": {"spellbook_spells"}, "3": {"spellbook_spells", "subclass_id"},
                "4": {"spellbook_spells", "cantrips", "asi"}, "5": {"spellbook_spells"}}

    def disclosure(self, level, **_):
        supported = [
            "Spellcasting: cantrips, prepared spells and spell slots follow the Wizard Features table; a Long Rest restores slots; Intelligence is the ability",
            "Spellbook: the six creation spells, plus two Wizard spells chosen at each Wizard level after 1, of a level you have slots for",
            "Prepared spells: chosen from the spellbook in the preparation window (creation, a finished Long Rest, a Wizard level); the engine never picks",
        ]
        pending = [
            "Ritual Adept: casting a Ritual spell from the spellbook without preparing it is not implemented",
            "Arcane Recovery: recovering spell slots after a Short Rest is not implemented",
            "Spells of level 2 and 3 may be written in the book and prepared, but only resolver spells can be cast; the rest are catalog-only",
            "Cantrips: replacing a cantrip on a Long Rest remains pending",
            "Spellbook: copying a found spell and replacing a lost book remain pending",
        ]
        if level >= 2:
            pending.append("Scholar: the Expertise choice is not implemented")
        if level >= 3:
            supported.append("Wizard Subclass: Evoker is stored as the choice; it is the only subclass offered")
            pending.append("Evoker features (Evocation Savant, Potent Cantrip) are not implemented; the other subclasses are not offered")
        if level >= 4:
            supported.append("Selected level4 ordinary Ability Score Improvement and one more Wizard cantrip")
            pending.append("Other feats remain unsupported")
        if level >= 5:
            pending.append("Memorize Spell: swapping a prepared spell after a Short Rest is not implemented")
        return {"supported": supported, "pending": pending}


HANDLER = Wizard()
