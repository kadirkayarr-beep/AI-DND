"""Attack-verb precision, written red-first from a real play log.

In play, "Boddynock Hanı'nın kapısına yaklaşıp üç kez nazikçe vuruyorum" (knocking)
ended with "Bu hedef artık geçerli değil. Görünen rakiplerden birini seç." because
`vur-` counts as an attack verb. Measuring the detector showed the prefix match is
much wider: "keşfediyorum", "kesinlikle", "kesin" start with `kes-` and were read as
attacks too, so ordinary exploration turns could be answered with a combat error.

Real attacks must stay attacks; the checks use the real detector with no model.
"""

from __future__ import annotations

import unittest

import combat_lifecycle
import game

NOT_ATTACKS = (
    # knocking
    "Kapıya vuruyorum.",
    "Boddynock Hanı’nın kapısına yaklaşıp üç kez nazikçe vuruyorum. İçeriden ayak sesi ya da konuşma geliyor mu diye dinliyorum.",
    "Kapıyı çalıyorum.",
    "Pencereye hafifçe vuruyorum.",
    # words that merely start with kes-/döv-/vur-
    "Çevreyi keşfediyorum.",
    "Keşif yapmak için sokağa çıkıyorum.",
    "Kesinlikle bir han arıyorum.",
    "Kesin bir yere gidiyorum.",
    "Sokakta dövme yapan birini arıyorum.",
    "Bu noktaya özellikle vurgu yapıyorum.",
    "Kesim işi yapan bir esnaf arıyorum.",
    # already negated or hypothetical
    "Saldırmak istemiyorum.",
    "Dövüşmek istemiyorum.",
)

ATTACKS = (
    "Gromm'a saldırıyorum.",
    "Muhafıza vuruyorum.",
    "Kapıdaki muhafıza vuruyorum.",
    "Haydutu yumruklayıp kaçıyorum.",
    "Kılıcımla vuruyorum.",
    "Haydutu bıçaklıyorum.",
    "Yaratığa kılıcımı saplıyorum.",
    "Goblinle dövüşüyorum.",
    "Kılıçla yaratığı kesiyorum.",
)


class AttackVerbPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=3)

    def decision(self, message):
        return combat_lifecycle.is_attack_decision(self.session, message)

    def test_ordinary_turns_are_not_attack_decisions(self):
        for message in NOT_ATTACKS:
            with self.subTest(message=message[:50]):
                self.assertFalse(self.decision(message), message)

    def test_real_attacks_stay_attack_decisions(self):
        for message in ATTACKS:
            with self.subTest(message=message[:50]):
                self.assertTrue(self.decision(message), message)

    def test_a_question_or_negated_attack_is_still_not_a_decision(self):
        for message in ("Gromm'a saldırsam ne olur?", "Muhafıza saldırmıyorum.", "Saldırmayacağım."):
            with self.subTest(message=message):
                self.assertFalse(self.decision(message), message)


if __name__ == "__main__":
    unittest.main()
