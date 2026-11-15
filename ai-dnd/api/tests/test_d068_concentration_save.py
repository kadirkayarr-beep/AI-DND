"""D-068: a saved Concentration record is checked against the character and the fight, not only for its shape.

A forged save could hold Bless for a class whose spell list has no Bless, or start it in a round the fight has not
reached yet (which stretches its minute). Both are refused. A finished fight's record still loads (the D-001 class: a
stale record never holds and must not lock the campaign). Fixture: test_spell_scope.caster (fixed session, no campaign,
no town), through test_dilim4c_spell_resolvers."""
from __future__ import annotations

import copy
import unittest

import spell_concentration
from api.tests.test_dilim4c_spell_resolvers import cleric, magic, turn, wizard
from api.tests.test_spell_scope import caster

MESSAGE = "Invalid saved spell concentration."


def bless_record(s, **extra):
    combat = s.world_state["combat"]
    return {"spell_id": "Bless", "combat_id": combat["combat_id"], "started_round": combat["round"], "slot_level": 1,
            "targets": ["player"], **extra}


class ClassMustHaveTheSpell(unittest.TestCase):
    def test_a_wizard_save_holding_bless_is_refused(self):
        s, _ = wizard()
        saved = s.serialize_game_state()
        saved["world_state"][spell_concentration.KEY] = bless_record(s)
        with self.assertRaisesRegex(ValueError, MESSAGE):
            s._validate_save_payload(saved)

    def test_a_stale_wizard_record_is_refused_too(self):
        s, _ = wizard()
        saved = s.serialize_game_state()
        saved["world_state"][spell_concentration.KEY] = bless_record(s, combat_id="an-old-fight")
        with self.assertRaisesRegex(ValueError, MESSAGE):  # no fight ever gave this class Bless
            s._validate_save_payload(saved)

    def test_a_cleric_and_a_paladin_may_hold_bless(self):
        s, _ = cleric()
        turn(s, magic("Bless", "player"))
        s._validate_save_payload(copy.deepcopy(s.serialize_game_state()))
        p, _ = caster(cls="Paladin")
        spell_concentration.validate_saved({**p.world_state, spell_concentration.KEY: bless_record(p)}, p.character)


class StartedRoundMustBeReached(unittest.TestCase):
    def blessed_save(self):
        s, _ = cleric()
        turn(s, magic("Bless", "player"))
        return s, s.serialize_game_state()

    def test_a_round_the_fight_has_not_reached_is_refused(self):
        s, saved = self.blessed_save()
        now = saved["world_state"]["combat"]["round"]
        saved["world_state"][spell_concentration.KEY]["started_round"] = now + 5
        with self.assertRaisesRegex(ValueError, MESSAGE):
            s._validate_save_payload(saved)

    def test_the_current_and_an_earlier_round_load(self):
        s, saved = self.blessed_save()
        saved["world_state"]["combat"]["round"] = 4
        for started in (1, 4):
            forged = copy.deepcopy(saved)
            forged["world_state"][spell_concentration.KEY]["started_round"] = started
            s._validate_save_payload(forged)

    def test_a_finished_fights_record_is_not_held_to_this_fights_round(self):
        s, saved = self.blessed_save()
        record = saved["world_state"][spell_concentration.KEY]
        record.update(combat_id="an-old-fight", started_round=saved["world_state"]["combat"]["round"] + 5)
        s._validate_save_payload(saved)  # stale: it never holds, so it must not lock the campaign


if __name__ == "__main__":
    unittest.main()
