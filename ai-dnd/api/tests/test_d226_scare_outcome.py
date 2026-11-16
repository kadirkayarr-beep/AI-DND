"""D-226: a won scare is not told as a scare that did not work. The turn route is pinned by journey 87."""

from __future__ import annotations

import unittest

import game

SAID = "Muhafızı korkutmaya çalışıyorum: Önümden çekil, yoksa başın belaya girer!"


class AWonScareIsToldAsWon(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=2261)

    def decide(self, narration, outcome):
        return self.session._narration_safety_decision(
            narration, SAID, None,
            {"action": "skill_check", "status": "resolved", "skill": "Intimidation", "outcome": outcome})

    def test_a_won_scare_cannot_leave_the_person_unmoved(self):
        for narration in ("Kavşim kollarını kavuşturup bakıyor; geri adım atmıyor.",
                          "Sözlerin ona işlemiyor.", "Muhafız seni umursamıyor bile.",
                          "Kavşim yerinden kıpırdamıyor.", "Muhafız hiç korkmuyor.",
                          "“Senden korkmuyorum,” diyor muhafız.", "Tehdidin onu etkilemiyor."):
            with self.subTest(narration=narration):
                decision = self.decide(narration, "success")
                self.assertTrue(decision["unsafe"], decision)
                self.assertEqual(decision["reason_code"], "SKILL_RESULT_CONTRADICTION")

    def test_a_won_scare_told_as_won_passes(self):
        for narration in ("Kavşim yutkunuyor ve kenara çekiliyor.",
                          "Muhafızın yüzü soluyor; tek söz etmeden yolu açıyor."):
            with self.subTest(narration=narration):
                self.assertFalse(self.decide(narration, "success")["unsafe"])

    def test_a_lost_scare_may_leave_the_person_unmoved(self):
        self.assertFalse(self.decide("Kavşim geri adım atmıyor; sözlerin ona işlemiyor.", "failure")["unsafe"])


if __name__ == "__main__":
    unittest.main()
