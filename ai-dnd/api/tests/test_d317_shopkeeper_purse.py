"""D-317 and D-403 (debt-zero G2.9).

D-317: only the owner of a shop opens with the 1000 copper till. A person the model names "Shopkeeper" who keeps no
shop is one of the people of the town: 5-40 copper, so searching the body can never hand the player 1000 copper.
D-403 (owner answer S23: b): coin the words hold out with no figure ("biraz para") has no amount to decide, so the
game asks how much; it never stays silent. A reading that never got a list (fallback:no_list) still decides the coin
the words name, as a failed reading does (owner rule G11). No coin moves in any of these turns.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import bold_acts
import economic_actions
import equipment_economy
import money_owner
from api.tests.test_d429_coin_without_a_reading import _played
from api.tests.test_species_traits import make_session

UNNAMED_COIN = "barmene biraz para bırakıyorum"
NAMED_COIN = "barmene 5 bakır veriyorum"
ASKS_THE_AMOUNT = economic_actions._CLARIFY["amount_required"]


class AShopkeeperOnlyBecauseOfARole(unittest.TestCase):
    def setUp(self):
        self.session = make_session("Human")
        self.world = self.session.world_state

    def modelled_shopkeeper(self):
        npc = self.session.create_npc_from_ai(
            {"name": "Orrin", "role": "Shopkeeper", "location": self.world["location"]})
        self.assertIsNotNone(npc)
        return npc

    def test_a_modelled_shopkeeper_without_a_shop_carries_a_small_purse(self):
        npc = self.modelled_shopkeeper()
        self.assertTrue(5 <= self.world["currency"][npc["id"]] <= 40, self.world["currency"][npc["id"]])
        self.assertTrue(5 <= equipment_economy.person_purse(self.world, npc) <= 40)

    def test_searching_the_body_reads_the_small_purse_too(self):
        npc = self.modelled_shopkeeper()
        self.assertTrue(5 <= bold_acts._purse_of(self.world, npc) <= 40)
        del self.world["currency"][npc["id"]]  # an unwritten wallet reads what would have been written
        self.assertTrue(5 <= bold_acts._purse_of(self.world, npc) <= 40)

    def test_the_owner_of_a_real_shop_opens_with_the_till(self):
        created = self.session.create_shop_from_proposal({
            "name": "Equipment Counter", "description": "", "location": self.world["location"],
            "shopkeeper": {"name": "Equipment Merchant", "description": ""}})
        self.assertIsNotNone(created)
        owner = created["shopkeeper"]
        self.assertEqual(self.world["currency"][owner["id"]], 1000)
        self.assertEqual(equipment_economy.person_purse(self.world, owner), 1000)
        del self.world["currency"][owner["id"]]
        self.assertEqual(bold_acts._purse_of(self.world, owner), 1000)


class CoinWithNoFigureAsksTheAmount(unittest.TestCase):
    def test_coin_with_no_figure_asks_how_much_and_moves_nothing(self):
        on = _played(self, 20261702, "1", UNNAMED_COIN)
        self.assertEqual(on["route"], "fallback:failed")
        self.assertIn(ASKS_THE_AMOUNT, on["narration"])
        self.assertEqual(on["money_after"], on["money_before"])
        self.assertEqual(on["cards"], [])

    def test_a_named_figure_does_not_ask_the_amount(self):
        on = _played(self, 20261703, "1", NAMED_COIN)
        self.assertNotIn(ASKS_THE_AMOUNT, on["narration"])

    def test_the_ask_belongs_to_its_turn_alone(self):
        asked = _played(self, 20261704, "1", UNNAMED_COIN)
        self.assertIn(ASKS_THE_AMOUNT, asked["narration"])
        plain = _played(self, 20261705, "1", "barmene selam veriyorum")
        self.assertNotIn(ASKS_THE_AMOUNT, plain["narration"])


class ACoinLineWhoseListCouldNotBeBuilt(unittest.TestCase):
    def test_the_words_figure_is_still_decided_and_noted(self):
        with patch("front_proposal.listing", side_effect=RuntimeError("no list")):
            on = _played(self, 20261706, "1", NAMED_COIN)
        self.assertEqual(on["seen"], [("unclear", "barman", 5)], on["narration"])
        self.assertIn(("barman", money_owner.unclear_note(5)), on["notes"], on["narration"])
        self.assertEqual(on["money_after"], on["money_before"])

    def test_the_figureless_coin_asks_the_amount_there_too(self):
        with patch("front_proposal.listing", side_effect=RuntimeError("no list")):
            on = _played(self, 20261707, "1", UNNAMED_COIN)
        self.assertIn(ASKS_THE_AMOUNT, on["narration"])
        self.assertEqual(on["money_after"], on["money_before"])
