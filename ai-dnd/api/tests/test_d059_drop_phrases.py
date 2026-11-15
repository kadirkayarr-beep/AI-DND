"""D-059: the Concentration drop line reads the future tense, "I'll", a comma before a later clause and the held spell's
own name ("Bless'i bırakıyorum", "I drop Bless"). A line that names a Concentration spell beside a drop verb is never a
cast of that spell (before: "Bless'i bırakıyorum" and "Bless'i bırakmıyorum" cast Bless again and spent a slot).
A named drop ends only that spell: another spell's name is refused and nothing changes.
Fixture: test_spell_scope.caster (fixed session seed 17; no campaign, no town)."""
from __future__ import annotations

import copy
import unittest

import spell_concentration
import spell_scope
from combat_lifecycle import CombatRequestError
from api.tests.test_dilim4c_4b_fix1 import blessed
from api.tests.test_dilim4c_spell_resolvers import held, refused, typed

DROP = {"steps": [{"kind": "end_concentration"}]}
DROP_BLESS = {"steps": [{"kind": "end_concentration", "spell_id": "Bless"}]}
PLAIN_DROPS = ("konsantrasyonumu bırakacağım", "Konsantrasyonu bitireceğim", "konsantrasyonu keseceğim",
               "I'll drop my concentration", "I'll end concentration",
               "Konsantrasyonu bırakıyorum, sonra kaçıyorum", "I drop concentration, then attack")
NAMED_DROPS = ("Bless'i bırakıyorum", "Bless'i bırakacağım", "kutsamayı bırakıyorum", "Kutsama büyüsünü bitireceğim",
               "Bless'in konsantrasyonunu bırakıyorum", "bırakıyorum Bless'i", "I drop Bless", "I'll end Bless",
               "drop concentration on Bless", "stop concentrating on Bless")
NAMED_KEPT = ("Bless'i bırakmıyorum", "Bless'i bırakmak istemiyorum", "Bless'i bırakırsam ne olur",
              "kutsamayı bırakmadan saldırıyorum", "I won't drop Bless", "if I drop Bless", "drop Bless, no wait",
              "Bless'i asla bırakmıyorum", "Kutsama büyüsünü bırakmıyorum", "Bless'in konsantrasyonunu kesmiyorum",
              "I never end Bless", "I'm not dropping Bless", "I stopped concentrating on Bless?",
              # The closed Turkish suffix list and the English possessive/determiner gap still keep these.
              "Bless'i bırakmayacağım", "Bless'i bitirmedim", "Bless'i kesmem", "Bless'i bırakmalı mıyım",
              "I won't drop my Bless", "I'm not ending the Bless spell", "I won't drop my concentration on Bless")
STILL_KEPT = ("drop concentration, no wait", "Konsantrasyonu bırakıyorum, yok vazgeçtim")
# A drop verb's look-alike (kesin/kesinlikle, kesmek = to cut a foe, drop prone, endless) or a drop verb that governs
# something else (no object case on the spell, or a converb / "and" / "cast" between) is no drop: these still cast Bless.
CAST_BLESS = {"steps": [{"kind": "magic", "ability": "Bless", "target_id": None}]}
CASTS_BESIDE_A_DROP_LOOKALIKE = ("Bless'i kesinlikle atıyorum", "Bless atıp goblini kesiyorum", "Bless atıp kesiyorum",
                                 "Kutsama büyüsünü kesin olarak yapıyorum", "Bless'i atıp goblini kesiyorum",
                                 "Endless war: I cast Bless", "I break formation to cast Bless",
                                 # A drop root inside another word (keskin, kestirme, bitirici) is no drop verb; an
                                 # English drop verb whose object is something else (them, the fight) does not govern
                                 # the spell. HEAD 6d790201 cast all six.
                                 "Bless'i keskin bir sesle atıyorum", "Bless'i kestirmeden atıyorum",
                                 "Bless'i bitirici darbeden önce atıyorum", "I stop them with Bless",
                                 "I end the fight with Bless", "I break their morale with Bless")
# Two-clause casts reach the cast path, which refuses a second clause as outside V1 (as "I cast Bless and attack" is).
TWO_CLAUSE_CASTS = ("Bless atıyorum ve bitiriyorum bu işi", "I drop prone and cast Bless")


class D059DropLines(unittest.TestCase):
    def test_future_tense_ill_and_a_comma_before_a_later_clause_drop(self):
        for line in PLAIN_DROPS:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), DROP)
                self.assertTrue(spell_scope.explicit_request(line))

    def test_the_held_spells_name_drops_that_spell(self):
        for line in NAMED_DROPS:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), DROP_BLESS)

    def test_a_named_line_that_is_no_drop_never_casts_the_spell(self):
        for line in NAMED_KEPT + STILL_KEPT:
            with self.subTest(line):
                self.assertIsNone(spell_scope.natural_command(line, None))

    def test_a_cast_beside_a_drop_lookalike_still_casts(self):
        for line in CASTS_BESIDE_A_DROP_LOOKALIKE:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), CAST_BLESS)
                self.assertTrue(spell_scope.explicit_request(line))
        for line in TWO_CLAUSE_CASTS:
            with self.subTest(line), self.assertRaises(CombatRequestError) as raised:
                spell_scope.natural_command(line, None)
            self.assertEqual(raised.exception.code, "unsupported_spell_mode")

    def test_a_named_drop_turn_ends_bless_and_spends_no_slot(self):
        for line in ("Bless'i bırakıyorum", "I drop Bless"):
            with self.subTest(line):
                s, _ = blessed()
                slots = copy.deepcopy(s.world_state["spellcasting_v1"]["slots"])
                typed(s, line)
                self.assertIsNone(spell_concentration.current(s.world_state))
                self.assertEqual(s.world_state["spellcasting_v1"]["slots"], slots)

    def test_a_kept_named_turn_keeps_bless_and_its_slots(self):
        for line in NAMED_KEPT:
            with self.subTest(line):
                s, _ = blessed()
                before = held(s)
                try:
                    typed(s, line)
                except CombatRequestError:  # a refused turn is fine; a crash (KeyError, TypeError) is not
                    pass
                self.assertEqual(spell_concentration.current(s.world_state),
                                 spell_concentration.current(before[0]))
                self.assertEqual(s.world_state["spellcasting_v1"]["slots"], before[0]["spellcasting_v1"]["slots"])

    def test_a_named_drop_of_another_spell_is_refused_and_changes_nothing(self):
        for spell in ("Fire Bolt", "Healing Word", 7):
            with self.subTest(spell):
                s, _ = blessed()
                refused(self, s, {"steps": [{"kind": "end_concentration", "spell_id": spell}]},
                        "concentration_not_held")

    def test_any_other_field_is_still_refused(self):
        s, _ = blessed()
        refused(self, s, {"steps": [{"kind": "end_concentration", "target_id": "player"}]}, "unsupported_action")


if __name__ == "__main__":
    unittest.main()
