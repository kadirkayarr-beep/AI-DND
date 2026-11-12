"""Dilim 4C.5 fix round 1 (review): the narrator may not claim coin, items or healing on a narrative cast; item-taking
lines are no narrative cast; wish/question forms are no cast; a Concentration drop is read only from a short first-person
drop line; a narrative cantrip leaves a Long Rest window open; tighter saved-fact bounds and copy-validate-write.
Fixtures: test_spell_preparation_4c2.prepper/rested (real initializer, no campaign town)."""
from __future__ import annotations

import copy
import unittest

import spell_effects
import spell_preparation
import spell_scope
from api.tests.test_dilim4c_5_narrative_spells import wizard
from api.tests.test_spell_preparation_4c2 import rested

KEY = spell_effects.KEY


class NarratorClaimGuard(unittest.TestCase):
    LIES = ("Hayalet el mandalı kaldırır; kapının ardında bir kese altın bulup cebine koyarsın, yaraların da kapanır.",
            "Yüzük avucuna düşer, artık senindir.", "Kese elinde kalır.", "Altın çantana süzülür.",
            "Eşya cebine girer.", "Yaraların kapanır.", "İyileşirsin.", "Canın dolar.", "Sana on altın kazandırır.",
            "The ring drops into your palm; it is yours now.", "You pocket the gold.", "Your wounds close.",
            "Muhafız 5 hasar alır.")
    TRUE_LINES = ("Hayalet el süzülür ve mandalı yukarı iter.", "Odada bir kedi sesi yankılanır.",
                  "Asanın ucu yumuşak bir ışıkla parlar.", "Mumun fitili bir şıklatmayla tutuşur.")

    def test_a_claimed_state_change_is_caught(self):
        for line in self.LIES:
            with self.subTest(line):
                self.assertTrue(spell_effects.claims_state_change(line))

    def test_plain_effect_lines_and_the_python_lines_pass(self):
        s = wizard()
        python_line = spell_effects.resolve(s, ("narrative", "Mage Hand"))["narration"]
        for line in (*self.TRUE_LINES, python_line):
            with self.subTest(line):
                self.assertFalse(spell_effects.claims_state_change(line))


class ItemTakingIsNoNarrativeCast(unittest.TestCase):
    def test_taking_lines(self):
        for line in ("Mage Hand ile keseyi kendime çekiyorum", "Mage Hand ile yüzüğü kapıyorum",
                     "Mage Hand ile anahtarı elime koyuyorum", "Mage Hand ile şişeyi çantama atıyorum",
                     "Mage Hand ile bozukluğu cebime indiriyorum", "Mage Hand ile sandıktan mücevheri çıkarıyorum",
                     "I use Mage Hand to bring the pouch to me", "Mage Hand: I take the key",
                     "I grab the dagger with Mage Hand", "Mage Hand picks up the ring", "I pocket it with Mage Hand"):
            with self.subTest(line):
                self.assertIsNone(spell_effects.named(line))

    def test_pure_effect_lines_still_cast(self):
        for line in ("Mage Hand ile kapının mandalını kaldırıyorum", "Minor Illusion ile bir kedi sesi yaratıyorum"):
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line)[0], "narrative")


class WishAndQuestionAreNoCast(unittest.TestCase):
    def test_forms(self):
        for line in ("Mage Hand yapmak istemiyorum", "Mage Hand yapsam mı", "Acaba Mage Hand kullansam",
                     "Keşke Mage Hand bilseydim", "Should I cast Mage Hand", "Mage Hand kullanmalı mıyım"):
            with self.subTest(line):
                self.assertIsNone(spell_effects.named(line))


class ConcentrationDropIsAPositiveMatch(unittest.TestCase):
    KEEPS = ("Konsantrasyonu bırakmamak için geri çekiliyorum", "Konsantrasyonu bırakmaktansa ölürüm",
             "Konsantrasyonu bırakmayı düşünmüyorum", "Konsantrasyonu bırakmasam mı", "Konsantrasyonu bırakmalı mıyım",
             "Konsantrasyonu bırakırsam ne olur", "Keşke konsantrasyonu bıraksaydım",
             "Muhafıza konsantrasyonunu bırakmasını söylüyorum", "if I drop concentration what happens",
             "drop concentration, no wait")

    def test_these_keep(self):
        for line in self.KEEPS:
            with self.subTest(line):
                self.assertIsNone(spell_scope.natural_command(line, None))
                self.assertFalse(spell_scope.explicit_request(line))


class CantripLeavesTheLongRestWindow(unittest.TestCase):
    def test_a_narrative_cantrip_does_not_close_it(self):
        s = rested("Wizard")
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        window = copy.deepcopy(s.world_state["spellcasting_v1"]["prepare_window"])
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(s.world_state["spellcasting_v1"]["prepare_window"], window)
        self.assertTrue(spell_preparation.window_open(s))


class SavedFactBounds(unittest.TestCase):
    def fact(self, **change):
        return {"id": "mage_hand-0", "spell_id": "Mage Hand", "kind": "narrative", "location_id": "tavern",
                "cast_second": 0, "until_second": 60, **change}

    def test_forged_bounds_are_refused(self):
        for value in ([self.fact(id="light-0")], [self.fact(id="mage_hand-5")], [self.fact(location_id="x" * 201)],
                      [self.fact(until_second=61)], [self.fact(cast_second=10 ** 12, until_second=10 ** 12 + 60,
                                                           id=f"mage_hand-{10 ** 12}")]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                spell_effects.validate_saved({KEY: value})

    def test_a_real_fact_still_loads(self):
        s = wizard()
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        spell_effects.validate_saved(s.world_state)

    def test_an_unreadable_saved_list_is_not_overwritten(self):
        s = wizard()
        s.world_state[KEY] = [self.fact(kind="bless")]
        before = copy.deepcopy(s.world_state)
        with self.assertRaises(ValueError):
            spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(s.world_state, before)

    def test_unknown_hands_are_told_in_turkish(self):
        s = wizard()
        s.world_state.pop("equipment")
        before = copy.deepcopy(s.world_state)
        cast = spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(cast["action_result"]["reason"], "equipment_unknown")
        self.assertEqual(cast["narration"], "Ellerinin durumu bilinmiyor; Büyücü Eli (Mage Hand) yapılmadı.")
        self.assertEqual(s.world_state, before)


if __name__ == "__main__":
    unittest.main()
