"""D-170: a theft's coin comes out of the victim's purse; none is made (ZAR_KURALLARI 4.6: the old owner and the new are
clear). The turn route, undo and reload are pinned by journeys 50c, 51b, 52, 52b and 52c."""

from __future__ import annotations

import unittest

import bold_acts


class APersonsPurse(unittest.TestCase):
    def test_a_counted_purse_is_the_wallet(self):
        self.assertEqual(bold_acts._purse_of({"kavsim": 7}, {"id": "kavsim"}), 7)
        self.assertEqual(bold_acts._purse_of({"kavsim": 0}, {"id": "kavsim"}), 0)
        self.assertEqual(bold_acts._purse_of({"kavsim": -4}, {"id": "kavsim"}), 0)

    def test_an_uncounted_purse_is_fixed_by_who_they_are(self):
        purses = {bold_acts._purse_of({}, {"id": name}) for name in ("kavsim", "sera", "marek", "npc-17", "x")}
        self.assertTrue(all(5 <= purse <= 40 for purse in purses))
        self.assertEqual(bold_acts._purse_of({}, {"id": "kavsim"}), bold_acts._purse_of({}, {"id": "kavsim"}))
        self.assertEqual(bold_acts._purse_of({}, {"id": "kavsim"}), 26)

    def test_an_uncounted_shopkeeper_has_the_shops_cash(self):
        self.assertEqual(bold_acts._purse_of({}, {"id": "marek", "role": "Shopkeeper"}), 1000)
        self.assertEqual(bold_acts._purse_of({"marek": 12}, {"id": "marek", "role": "Shopkeeper"}), 12)

    def test_counting_does_not_write_the_wallet(self):
        wallets = {"player": 40}
        bold_acts._purse_of(wallets, {"id": "kavsim"})
        self.assertEqual(wallets, {"player": 40})


if __name__ == "__main__":
    unittest.main()
