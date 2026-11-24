"""Direct unit tests for game_parts.coin (reached through game, the only importer of game_parts): shop text rules and shop proposal validation."""

import unittest

import game


class ShopkeeperRoleTests(unittest.TestCase):
    def test_trade_roles_are_shopkeepers(self):
        for role in ("Shopkeeper", "shop owner", "Merchant", "tüccar", "Dükkan Sahibi"):
            with self.subTest(role=role):
                self.assertTrue(game._is_shopkeeper_role(role))

    def test_other_roles_and_non_text_are_not(self):
        for role in ("Guard", "innkeeper", "", None, 5):
            with self.subTest(role=role):
                self.assertFalse(game._is_shopkeeper_role(role))


class RequestTextTests(unittest.TestCase):
    def test_explicit_request_to_create_a_shop(self):
        for text in ("open a shop here", "Bir dükkan kur", "I want to build a stall"):
            with self.subTest(text=text):
                self.assertTrue(game._explicit_campaign_shop_request(text))

    def test_negated_or_unrelated_text_is_not_a_request(self):
        for text in ("don't open a shop", "dükkan açma", "I look at the merchant", "", None):
            with self.subTest(text=text):
                self.assertFalse(game._explicit_campaign_shop_request(text))

    def test_negative_request_needs_a_shop_and_a_negation(self):
        self.assertTrue(game._explicit_campaign_shop_negative_request("never create a shop"))
        self.assertTrue(game._explicit_campaign_shop_negative_request("dükkan kurma"))
        self.assertFalse(game._explicit_campaign_shop_negative_request("never create a monster"))
        self.assertFalse(game._explicit_campaign_shop_negative_request("open a shop"))
        self.assertFalse(game._explicit_campaign_shop_negative_request(7))

    def test_economy_request_looks_for_price_and_trade_words(self):
        self.assertTrue(game._shop_economy_request("What is the price?"))
        self.assertTrue(game._shop_economy_request("satın al"))
        self.assertFalse(game._shop_economy_request("hello there"))
        self.assertFalse(game._shop_economy_request(None))

    def test_presence_question_needs_a_shop_word_and_a_question_mark(self):
        self.assertTrue(game._shop_presence_question("Is there a shop?"))
        self.assertFalse(game._shop_presence_question("There is a shop."))
        self.assertFalse(game._shop_presence_question("Is there a river?"))

    def test_someone_elses_purse_pattern_ignores_the_players_own(self):
        pattern = game._SOMEONE_ELSES_PURSE
        self.assertTrue(pattern.search("adamin kesesi"))
        self.assertTrue(pattern.search("cebinde ne var"))
        self.assertFalse(pattern.search("kesem"))
        self.assertFalse(pattern.search("cebimde"))

    def test_left_behind_marker_is_the_money_owners(self):
        import money_owner

        self.assertIs(game.COIN_LEFT_BEHIND, money_owner.COIN_LEFT_BEHIND)


class _SessionTestCase(unittest.TestCase):
    """The shop helpers read the active session, so each test runs inside a small real one."""

    def setUp(self):
        self.session = game.create_session(seed=11)
        self.world = self.session.world_state
        self.world["location"] = "market"
        self.world["locations"] = {"market": {}}
        self.world["npcs"] = []
        self.world["shops"] = []
        token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)


class GenerateShopIdTests(_SessionTestCase):
    def test_first_id_is_001_and_counter_advances(self):
        self.world.pop("next_shop_number", None)
        self.assertEqual(game.generate_shop_id(), "shop_001")
        self.assertEqual(game.generate_shop_id(), "shop_002")
        self.assertEqual(self.world["next_shop_number"], 3)

    def test_existing_ids_are_skipped(self):
        self.world["shops"] = [{"id": "shop_001"}, {"id": "shop_002"}, "junk"]
        self.world["next_shop_number"] = 1
        self.assertEqual(game.generate_shop_id(), "shop_003")


class ValidateShopProposalTests(_SessionTestCase):
    def _proposal(self, **over):
        proposal = {
            "name": "Lantern Row",
            "description": "A narrow stall of lamps.",
            "shopkeeper": {"name": "Mirel", "personality": "Dry wit.", "appearance": "Ink-stained fingers."},
        }
        proposal.update(over)
        return proposal

    def test_good_proposal_is_normalised_to_the_current_place(self):
        result = game.validate_shop_proposal(self._proposal())
        self.assertEqual(result["location"], "market")
        self.assertEqual(result["shopkeeper"]["name"], "Mirel")
        self.assertEqual(result["name"], "Lantern Row")

    def test_non_dict_and_missing_parts_are_refused(self):
        self.assertIsNone(game.validate_shop_proposal("shop"))
        self.assertIsNone(game.validate_shop_proposal(self._proposal(name="")))
        self.assertIsNone(game.validate_shop_proposal(self._proposal(shopkeeper="Mirel")))

    def test_money_talk_in_text_is_refused(self):
        self.assertIsNone(game.validate_shop_proposal(self._proposal(description="Everything costs 5 gold.")))
        keeper = {"name": "Mirel", "personality": "Sells cheap.", "appearance": "Tall."}
        self.assertIsNone(game.validate_shop_proposal(self._proposal(shopkeeper=keeper)))

    def test_keeper_name_must_be_new_and_clean(self):
        for name in (self.session.character["name"], "Bad_Name", "Mirel!"):
            with self.subTest(name=name):
                self.assertIsNone(game.validate_shop_proposal(self._proposal(shopkeeper={"name": name})))
        self.world["npcs"] = [{"name": "MIREL"}]
        self.assertIsNone(game.validate_shop_proposal(self._proposal()))

    def test_unknown_location_and_shop_caps_are_refused(self):
        self.world["shops"] = [{"location": "market"}] * 3
        self.assertIsNone(game.validate_shop_proposal(self._proposal()))
        self.world["shops"] = []
        self.world["location"] = "void"
        self.assertIsNone(game.validate_shop_proposal(self._proposal()))


if __name__ == "__main__":
    unittest.main()
