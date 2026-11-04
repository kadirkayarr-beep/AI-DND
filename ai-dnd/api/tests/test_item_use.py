"""Task 14: the model selects a bag id; the engine alone decides consumption."""
import copy
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import equipment_economy as ee
import front_proposal
import game
import item_use
import truth_card
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class ItemUse(unittest.TestCase):
    def setUp(self):
        self.world = {"inventory": [{"item_id": "beer1", "name": "Bira"},
                                    {"item_id": "beer2", "name": "Bira"},
                                    {"item_id": "food", "name": "Tabak yemek"},
                                    {"item_id": "sword", "name": "Greatsword"}],
                      "equipment": {"main_hand": None, "off_hand": None},
                      "currency": {"player": 100}, "npcs": [], "flags": {}}

    def test_kinds_come_from_the_table_by_full_name(self):
        for name, kind in (("Bira", "drink"), ("Şarap", "drink"), ("Tabak yemek", "food")):
            self.assertEqual(item_use.kind_of(name), kind)
            self.assertEqual(item_use.kind_of({"name": name}), kind)
        for name in ("Greatsword", "bira", "Bira kılıcı", " Tabak yemek", "Bira "):
            self.assertIsNone(item_use.kind_of(name))
        self.assertIsNone(item_use.kind_of({"name": "Greatsword", "kind": "food"}))

    def test_consume_drops_one_record_and_keeps_the_rest(self):
        before = copy.deepcopy(self.world)
        result = item_use.consume(self.world, "beer1")
        self.assertEqual((result.status, result.name, result.note), ("consumed", "Bira", "Bira içildi"))
        self.assertEqual(self.world, {**before, "inventory": before["inventory"][1:]})
        with self.assertRaises(FrozenInstanceError):
            result.status = "changed"

    def test_food_has_its_own_note(self):
        self.assertEqual(item_use.consume(self.world, "food").note, "Tabak yemek yendi")

    def test_a_sword_is_not_consumed(self):
        before = copy.deepcopy(self.world)
        result = item_use.consume(self.world, "sword")
        self.assertEqual((result.status, result.note), ("not_consumable", None))
        self.assertEqual(self.world, before)

    def test_a_worn_item_is_rejected_without_changing_world(self):
        self.world["equipment"]["main_hand"] = "beer1"
        before = copy.deepcopy(self.world)
        with self.assertRaises(ee.EquipmentError):
            item_use.consume(self.world, "beer1")
        self.assertEqual(self.world, before)

    def test_no_eating_in_a_fight(self):
        self.world["combat"] = {"active": True}
        before = copy.deepcopy(self.world)
        self.assertEqual(item_use.consume(self.world, "beer1").status, "in_combat")
        self.assertEqual(self.world, before)

    def test_an_absent_or_someone_elses_item_is_not_in_bag(self):
        self.world["npcs"] = [{"id": "guest", "inventory": [{"item_id": "their_beer", "name": "Bira"}]}]
        before = copy.deepcopy(self.world)
        for identity in ("missing", "their_beer"):
            self.assertEqual(item_use.consume(self.world, identity).status, "not_in_bag")
        self.assertEqual(self.world, before)

    def test_remover_returns_the_exact_record(self):
        expected = copy.deepcopy(self.world["inventory"][0])
        self.assertEqual(ee.remove_item(self.world, "beer1"), expected)
        self.assertEqual([i["item_id"] for i in self.world["inventory"]], ["beer2", "food", "sword"])

    def test_remover_validates_before_committing_any_change(self):
        self.world["inventory"][1]["quantity"] = 2
        before = copy.deepcopy(self.world)
        with self.assertRaises(ee.EquipmentError):
            ee.remove_item(self.world, "beer1")
        self.assertEqual(self.world, before)

    def test_remover_respects_legacy_weapon_alias_in_hand(self):
        self.world["equipment"]["main_hand"] = "greatsword"
        before = copy.deepcopy(self.world)
        with self.assertRaises(ee.EquipmentError):
            ee.remove_item(self.world, "sword")
        self.assertEqual(self.world, before)

    def test_remover_preserves_creation_owned_armor(self):
        self.world["inventory"].append({"item_id": "armor", "name": "Deri Zırh"})
        before = copy.deepcopy(self.world)
        with self.assertRaises(ee.EquipmentError):
            ee.remove_item(self.world, "armor")
        self.assertEqual(self.world, before)

    def test_the_same_identity_cannot_be_consumed_twice(self):
        item_use.consume(self.world, "beer1")
        before = copy.deepcopy(self.world)
        self.assertEqual(item_use.consume(self.world, "beer1").status, "not_in_bag")
        self.assertEqual(self.world, before)

    def test_front_does_not_consume_while_player_cannot_act(self):
        session = game.create_session(seed=7)
        session.world_state["inventory"] = copy.deepcopy(self.world["inventory"])
        session.character["current_hp"] = 0
        before = copy.deepcopy(session.world_state["inventory"])
        token = game._ACTIVE_SESSION.set(session)
        try:
            with self.assertRaises(game.PlayerCannotAct):
                game._front_consume({"kind": "consume", "item": "beer1"}, "Biramı içiyorum")
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(session.world_state["inventory"], before)

    def test_consumption_has_no_healing_coin_or_extra_time_effect(self):
        session = game.create_session(seed=7)
        session.world_state["inventory"] = copy.deepcopy(self.world["inventory"])
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        session.character["current_hp"] = 3
        session.require_player_can_act()
        before = copy.deepcopy((session.character, session.world_state.get("currency"),
                                session.world_state.get("campaign_time")))
        token = game._ACTIVE_SESSION.set(session)
        try:
            with patch("game.ollama.chat", side_effect=AssertionError("No extra model call")):
                reply = game._front_consume({"kind": "consume", "item": "beer1"}, "Biramı içiyorum")["reply"]
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(reply["action_result"]["action"], "consume")
        self.assertEqual(reply["action_result"]["state_changes"], ["inventory"])
        self.assertEqual((session.character, session.world_state.get("currency"),
                          session.world_state.get("campaign_time")), before)
        self.assertIn((None, "Bira içildi"), session._turn_notes)

    def test_front_requires_a_listed_bag_id(self):
        listed = {"people": [], "offers": [], "bag": front_proposal._bag(self.world)}
        self.assertEqual(front_proposal.validate({"front": {"kind": "consume", "item_id": "beer1"}}, listed),
                         {"kind": "consume", "item": "beer1"})
        for identity in ("missing", "none", None):
            self.assertIsNone(front_proposal.validate({"front": {"kind": "consume", "item_id": identity}}, listed))
        self.assertIn("consume", game._PLANNER_STAYS_OUT)


class ConsumeJourneys(JourneyCase):
    async def test_a_consume_reading_drops_the_food_and_beer_and_the_card_says_so(self):
        results = await self.run_scenario(load_scenario(SCENARIO_DIR / "04b_consume_front.json"))
        self.assertEqual([r.status for r in results], ["pass", "pass"], results)
        session = self.manager.get(self.last_session_id).game_session
        self.assertIn((None, "Bira içildi"), session._turn_notes)
        self.assertIn("bu tur: Bira içildi", truth_card.narrator_view(session.world_state, this_turn=session._turn_notes))
        npc = {"id": "other", "role": "Yolcu"}
        self.assertNotIn("Bira içildi", truth_card.npc_view(session.world_state, npc=npc, this_turn=session._turn_notes))

    async def test_a_consume_reading_cannot_eat_a_sword(self):
        results = await self.run_scenario(load_scenario(SCENARIO_DIR / "28_consume_wrong_item.json"))
        self.assertEqual([r.status for r in results], ["pass"], results)