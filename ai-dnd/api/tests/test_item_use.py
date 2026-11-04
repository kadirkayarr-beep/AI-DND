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
        self.assertEqual([r.status for r in results[:2]], ["pass", "pass"], results)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[2].status, "unreached")
        from api.tests.journeys.runner import REAL_CHAIN_ONLY
        self.assertEqual(results[2].failures, (REAL_CHAIN_ONLY,))
        session = self.manager.get(self.last_session_id).game_session
        self.assertIn((None, "Bira içildi"), session._turn_notes)
        self.assertIn("bu tur: Bira içildi", truth_card.narrator_view(session.world_state, this_turn=session._turn_notes))
        npc = {"id": "other", "role": "Yolcu"}
        self.assertNotIn("Bira içildi", truth_card.npc_view(session.world_state, npc=npc, this_turn=session._turn_notes))

    async def test_a_consume_reading_cannot_eat_a_sword(self):
        results = await self.run_scenario(load_scenario(SCENARIO_DIR / "28_consume_wrong_item.json"))
        self.assertEqual([r.status for r in results], ["pass"], results)

class AmmunitionTests(unittest.TestCase):
    def bow(self, legacy=False):
        from api.tests.test_weapon_attack import armed
        session, npc = armed("Longbow", distance=30)
        session.world_state.pop("ammunition")
        session.world_state["inventory"] = (["Uzun Yay & 20 Ok"] if legacy else
            [{"item_id": "bow1", "name": "Uzun Yay & 20 Ok", "weapon_id": "longbow"}])
        return session, npc

    def test_a_bow_shot_seeds_twenty_and_spends_one(self):
        from api.tests.test_weapon_attack import resolve
        session, npc = self.bow()
        resolve(session, npc, "Longbow")
        self.assertEqual(session.world_state["ammunition"], {"arrow": 19})
        self.assertIs(session.world_state["inventory"][0]["ammo_seeded_v1"], True)

    def test_save_reload_and_a_second_shot_leave_eighteen(self):
        import tempfile
        from pathlib import Path
        from api.tests.test_weapon_attack import resolve
        session, npc = self.bow()
        resolve(session, npc, "Longbow")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            session.save_game(path)
            restored, _ = self.bow()
            restored.load_game(path)
        target = next(n for n in restored.world_state["npcs"] if n["id"] == npc["id"])
        resolve(restored, target, "Longbow")
        self.assertEqual(restored.world_state["ammunition"], {"arrow": 18})

    def test_an_old_text_inventory_still_seeds_once(self):
        from api.tests.test_weapon_attack import resolve
        session, npc = self.bow(legacy=True)
        resolve(session, npc, "Longbow")
        self.assertEqual(item_use.ensure_ammunition(session.world_state), {"arrow": 19})
        self.assertEqual(item_use.ensure_ammunition(session.world_state), {"arrow": 19})

    def test_prepare_reads_without_writing(self):
        import weapon_attack
        session, npc = self.bow(legacy=True)
        before = copy.deepcopy(session.world_state)
        self.assertEqual(item_use.ammo_available(session.world_state, "arrow"), 20)
        weapon_attack.prepare(session, "player", npc["id"], "Longbow")
        self.assertEqual(session.world_state, before)
        self.assertNotIn("ammunition", session.world_state)

    def test_an_unlisted_label_is_skipped_silently(self):
        world = {"inventory": ["Garip Yay & 5 Ok"]}
        self.assertEqual(item_use.ammo_available(world, "arrow"), 0)
        self.assertEqual(item_use.ensure_ammunition(world), {})
        self.assertNotIn("ammo_seeded_v1", world["inventory"][0])

    def test_ammo_note_and_card_show_remaining_counter_without_mutating(self):
        world = {"inventory": [], "ammunition": {"arrow": 19, "bolt": 20}}
        before = copy.deepcopy(world)
        self.assertEqual(item_use.ammo_note(world), "(ok: 19) (cıvata: 20)")
        self.assertIn("(ok: 19)", truth_card.narrator_view(world))
        self.assertEqual(world, before)
        self.assertEqual(item_use.ammo_note({"ammunition": {"arrow": 0}}), "")

    def test_invalid_existing_counter_cannot_be_hidden_by_a_pack(self):
        import weapon_attack
        from combat_lifecycle import CombatRequestError
        for invalid in (True, -1):
            with self.subTest(invalid=invalid):
                session, npc = self.bow()
                session.world_state["ammunition"] = {"arrow": invalid}
                before = copy.deepcopy(session.world_state)
                with self.assertRaises(CombatRequestError):
                    weapon_attack.prepare(session, "player", npc["id"], "Longbow")
                self.assertEqual(session.world_state, before)

    def test_two_distinct_packs_seed_once_each_and_existing_counter_survives(self):
        world = {"inventory": ["Kısa Yay & 20 Ok", "Uzun Yay & 20 Ok"], "ammunition": {"arrow": 3}}
        self.assertEqual(item_use.ammo_available(world, "arrow"), 43)
        self.assertEqual(item_use.ensure_ammunition(world), {"arrow": 43})
        self.assertEqual(item_use.ensure_ammunition(world), {"arrow": 43})

class AmmunitionJourney(JourneyCase):
    async def test_original_consume_scenario_bow_step_passes_without_broken_marker(self):
        scenario = load_scenario(SCENARIO_DIR / "04_consume.json")
        self.assertEqual(scenario.steps[2].known_broken, ())
        results = await self.run_scenario(scenario)
        self.assertEqual(results[2].status, "pass", results[2])