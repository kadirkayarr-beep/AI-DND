"""Sorcerer progression: selected levels 1-5 (spell resources, Metamagic, subclass choice storage, ordinary ASI).

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
from class_progression.base import ClassProgression


class Sorcerer(ClassProgression):
    name = "Sorcerer"
    supported_level = 5
    selected_asi = True

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


HANDLER = Sorcerer()
