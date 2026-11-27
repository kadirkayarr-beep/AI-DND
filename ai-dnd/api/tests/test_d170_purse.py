"""D-170: a theft's coin comes out of the victim's purse; none is made (ZAR_KURALLARI 4.6: the old owner and the new are
clear). The turn route, undo and reload are pinned by journeys 50c, 51b, 52, 52b and 52c."""

from __future__ import annotations

import unittest

import bold_acts


def world(wallets):
    return {"currency": dict(wallets), "scene_state": {"campaign_seed": "d170"}}


class APersonsPurse(unittest.TestCase):
    def test_a_counted_purse_is_the_wallet(self):
        self.assertEqual(bold_acts._purse_of(world({"kavsim": 7}), {"id": "kavsim"}), 7)
        self.assertEqual(bold_acts._purse_of(world({"kavsim": 0}), {"id": "kavsim"}), 0)
        self.assertEqual(bold_acts._purse_of(world({"kavsim": -4}), {"id": "kavsim"}), 0)

    def test_an_uncounted_purse_is_fixed_by_who_they_are(self):
        # D-207: the same identity-bound purse the town writes, fixed by the campaign seed too
        purses = {bold_acts._purse_of(world({}), {"id": name}) for name in ("kavsim", "sera", "marek", "npc-17", "x")}
        self.assertTrue(all(5 <= purse <= 40 for purse in purses))
        self.assertEqual(bold_acts._purse_of(world({}), {"id": "kavsim"}), bold_acts._purse_of(world({}), {"id": "kavsim"}))
        self.assertEqual(bold_acts._purse_of(world({}), {"id": "kavsim"}), 32)

    def test_an_uncounted_shopkeeper_has_the_shops_cash(self):
        owned = world({})
        owned["shops"] = [{"id": "shop_marek", "shopkeeper_id": "marek"}]  # D-317: the till belongs to the shop's owner
        self.assertEqual(bold_acts._purse_of(owned, {"id": "marek", "role": "Shopkeeper"}), 1000)
        owned["currency"]["marek"] = 12
        self.assertEqual(bold_acts._purse_of(owned, {"id": "marek", "role": "Shopkeeper"}), 12)
        self.assertTrue(5 <= bold_acts._purse_of(world({}), {"id": "marek", "role": "Shopkeeper"}) <= 40)

    def test_counting_does_not_write_the_wallet(self):
        counted = world({"player": 40})
        bold_acts._purse_of(counted, {"id": "kavsim"})
        self.assertEqual(counted["currency"], {"player": 40})

    def test_every_empty_purse_line_says_the_purse_is_empty(self):
        # D-230: a lifted purse with no coin says so; journey 52b pins the turn route with one seeded line
        for line in bold_acts._PURSE_EMPTY:
            self.assertIn("kesesi boş", line.format(n="Kavşim"))
            self.assertIn("Kavşim", line.format(n="Kavşim"))


if __name__ == "__main__":
    unittest.main()
