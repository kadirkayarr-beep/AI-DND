"""Dilim 4C.5 fix round 2 (re-review): "cantrip" is no bag; the narrator guard reads "elinde ... kalır" with words between
and every spelling of a bag; a verb-first Turkish drop and "I stop concentrating" drop; pulling a door is a pure effect.
Pure readers only (no session, no town)."""
from __future__ import annotations

import unittest

import spell_effects
import spell_scope


class CantripIsNoBag(unittest.TestCase):
    def test_cantrip_lines_cast(self):
        for line, spell in (("I cast the Mage Hand cantrip to open the door", "Mage Hand"),
                            ("Mage Hand cantripini kullanıyorum", "Mage Hand"),
                            ("Light cantrip on my staff", "Light")):
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), ("narrative", spell))

    def test_bag_lines_still_do_not(self):
        for line in ("Mage Hand ile şişeyi çantama atıyorum", "Mage Hand ile şişeyi cantama atiyorum",
                     "Mage Hand ile keseyi kendime çekiyorum"):
            with self.subTest(line):
                self.assertIsNone(spell_effects.named(line))

    def test_pulling_a_door_is_a_pure_effect(self):
        self.assertEqual(spell_effects.named("Mage Hand ile kapıyı çekiyorum"), ("narrative", "Mage Hand"))


class NarratorGuardSpellings(unittest.TestCase):
    def test_claims(self):
        for line in ("Elinde bir yüzük kalır.", "Elinde parlak, küçük bir yüzük kalır.", "Cantına koyarsın.",
                     "Çantana süzülür.", "Çantanın dibine düşer.", "Cantana girer."):
            with self.subTest(line):
                self.assertTrue(spell_effects.claims_state_change(line))

    def test_harmless_lines(self):
        for line in ("Hayalet el kapıyı çeker ve kapı gıcırdar.", "Asanın ucu yumuşak bir ışıkla parlar.",
                     "Bir cantrip kadar küçük bir kıvılcım belirir.", "Elinde asan, bekliyorsun."):
            with self.subTest(line):
                self.assertFalse(spell_effects.claims_state_change(line))


class DropWordOrders(unittest.TestCase):
    def test_these_drop(self):
        for line in ("bırakıyorum konsantrasyonu", "Bitiriyorum konsantrasyonumu", "I stop concentrating"):
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), {"steps": [{"kind": "end_concentration"}]})
                self.assertTrue(spell_scope.explicit_request(line))

    def test_parked_comma_line_keeps(self):
        self.assertIsNone(spell_scope.natural_command("Konsantrasyonu bırakıyorum, saldırıyorum", None))


if __name__ == "__main__":
    unittest.main()
