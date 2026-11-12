"""Cleric progression 1-5 (4C.3). Facts: content/rules/phb2024/classes/cleric.json (Cleric Features table, PDF 69).

Prepared spells (PDF 68) are chosen from the Cleric list in the preparation window (`spell_preparation`): the creation's level-1
list plus the PHB Cleric spells of each level the Cleric has slots for. Level 3: Life Domain is the one subclass offered (approved
decision 5); its features are pending.
"""
from __future__ import annotations

from class_progression import prepared_caster as caster


class Cleric(caster.PreparedCaster):
    name = "Cleric"
    subclass = ("life_domain", "phb2024:subclass:cleric:life-domain")

    def start_shapes(self):
        return {"2": set(), "3": {"subclass_id"}, "4": {"cantrips", "asi"}, "5": set()}

    def disclosure(self, level, **_):
        supported = [
            "Spellcasting: cantrips, prepared spells and spell slots follow the Cleric Features table; a Long Rest restores slots; Wisdom is the ability",
            "Prepared spells: chosen from the Cleric list in the preparation window (creation, a finished Long Rest, a Cleric level); the engine never picks",
        ]
        pending = [
            "Divine Order: the Protector or Thaumaturge choice is not implemented",
            "Spells of level 2 and 3 may be prepared, but only resolver spells can be cast; the rest are catalog-only",
            "Cantrips: replacing a cantrip on gaining a Cleric level remains pending",
        ]
        if level >= 2:
            pending.append("Channel Divinity: its uses, Divine Spark and Turn Undead are not implemented")
        if level >= 3:
            supported.append("Cleric Subclass: Life Domain is stored as the choice; it is the only subclass offered")
            pending.append("Life Domain features (Disciple of Life, Preserve Life, always-prepared domain spells) are not implemented; "
                           "the other domains are not offered")
        if level >= 4:
            supported.append("Selected level4 ordinary Ability Score Improvement and one more Cleric cantrip")
            pending.append("Other feats remain unsupported")
        if level >= 5:
            pending.append("Sear Undead is not implemented")
        return {"supported": supported, "pending": pending}


HANDLER = Cleric()
