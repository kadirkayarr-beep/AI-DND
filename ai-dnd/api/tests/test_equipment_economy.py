"""Bounded contracts for the real possession/turn/save owners; no model calls."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import equipment_economy as economy
from api.serializers import serialize_session_state


class EquipmentEconomyTests(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session()
        self.w = self.s.world_state
        self.w["npcs"] = [{
            "id": "vendor", "name": "Mira", "location": self.w["location"],
            "current_hp": 10, "inventory": ["Hançer"],
        }]
        self.w["shops"] = [{"id": "shop", "location": self.w["location"],
                            "shopkeeper_id": "vendor"}]
        self.w["currency"] = {"player": 5000, "vendor": 5000}

    def run_item(self, text):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = self.s.run_player_turn(text)
        self.assertEqual(result["model_calls"], 0)
        return result["action_result"]

    def prepare(self):
        self.assertTrue(self.run_item("/item list")["success"])
        return (next(i for i in self.w["inventory"] if i["name"] == "Kılıç")["item_id"],
                self.w["npcs"][0]["inventory"][0]["item_id"])

    def test_natural_inventory_query_preempts_npc_resolution(self):
        self.w["npcs"].extend([
            {"id": "cael", "name": "Cael", "role": "Muhafız", "location": self.w["location"]},
            {"id": "liora", "name": "Liora", "role": "Yolcu", "location": self.w["location"]},
        ])
        turn_before = self.w["flags"].get("turn_index", 0)
        with (
            patch("game.resolve_npc_reference", side_effect=AssertionError("NPC resolver must not run")),
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")),
        ):
            result = self.s.run_player_turn("Envanterimde neler var?")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["action_result"]["action"], "inventory")
        self.assertTrue(result["action_result"]["success"])
        self.assertIn("Envanterinde:", result["narration"])
        self.assertIn("Kılıç", result["narration"])
        self.assertNotIn("Hangisini", result["narration"])
        self.assertEqual(self.w["flags"].get("turn_index", 0), turn_before)

    def test_inventory_quick_action_phrase_uses_same_owner(self):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = self.s.run_player_turn("Envanterimi gözden geçir")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["action_result"]["action"], "inventory")
        self.assertTrue(result["action_result"]["success"])

    def test_natural_inventory_query_never_claims_another_actor(self):
        self.assertIsNone(economy.execute(self.s, "Mira'nın envanterinde ne var?"))

    def unchanged_rejection(self, command, reason):
        before, rng = copy.deepcopy(self.w), self.s.rng.getstate()
        result = self.run_item(command)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], reason)
        self.assertEqual(self.w, before)
        self.assertEqual(self.s.rng.getstate(), rng)

    def test_legacy_migration_preserves_duplicates_as_distinct_instances(self):
        self.w["inventory"].append("Kılıç")
        self.run_item("/item list")
        swords = [i for i in self.w["inventory"] if i["name"] == "Kılıç"]
        self.assertEqual(len(swords), 2)
        self.assertNotEqual(swords[0]["item_id"], swords[1]["item_id"])
        self.assertEqual(len(set(i["item_id"] for i in self.w["inventory"])), 3)

    def test_materialize_rewrites_unique_starting_hand_alias_to_item_id(self):
        self.assertEqual(self.w["equipment"]["main_hand"], "longsword")
        economy.materialize(self.w)
        sword_id = next(i["item_id"] for i in self.w["inventory"] if i["name"] == "Kılıç")
        self.assertEqual(self.w["equipment"]["main_hand"], sword_id)

    def test_materialize_does_not_auto_equip_empty_hands_from_inventory(self):
        self.w["equipment"] = {"main_hand": None, "off_hand": None}
        economy.materialize(self.w)
        self.assertIsNone(self.w["equipment"]["main_hand"])
        self.assertIsNone(self.w["equipment"]["off_hand"])
        self.assertTrue(any(i.get("name") == "Kılıç" for i in self.w["inventory"]))

    def test_materialize_leaves_ambiguous_catalog_hand_alias_unresolved(self):
        self.w["inventory"].append("Kılıç")
        economy.materialize(self.w)
        self.assertEqual(self.w["equipment"]["main_hand"], "longsword")
        self.assertEqual(sum(1 for i in self.w["inventory"] if i.get("name") == "Kılıç"), 2)

    def test_identity_drop_take_and_equipment_cleanup(self):
        sword, _ = self.prepare()
        clock = copy.deepcopy(self.w.get("campaign_time"))
        self.assertTrue(self.run_item("/item unequip main_hand")["success"])
        self.assertTrue(self.run_item(f"/item equip {sword} main_hand")["success"])
        self.assertTrue(self.run_item(f"/item drop {sword}")["success"])
        self.assertIsNone(self.w["equipment"]["main_hand"])
        self.assertTrue(self.run_item(f"/item take {sword}")["success"])
        self.assertEqual(next(i for i in self.w["inventory"] if i["item_id"] == sword)["name"], "Kılıç")
        self.assertEqual(self.w.get("campaign_time"), clock)

    def test_missing_ownership_never_uses_equipment_default(self):
        self.w["npcs"][0]["inventory"] = []
        self.w["npcs"][0]["equipment"] = {"main_hand": "longsword", "off_hand": None}
        self.unchanged_rejection("/item receive longsword vendor", "item_not_owned")

    def test_npc_transfer_denied_without_explicit_consent(self):
        _, dagger = self.prepare()
        self.unchanged_rejection(f"/item receive {dagger} vendor", "npc_consent_required")

    def test_two_party_transfer_preserves_id_and_consumes_consent(self):
        _, dagger = self.prepare()
        npc = self.w["npcs"][0]
        npc["item_consents"] = {dagger: {"operation": "receive", "recipient": "player"}}
        npc["equipment"] = {"main_hand": dagger, "off_hand": None}
        self.assertTrue(self.run_item(f"/item receive {dagger} vendor")["success"])
        npc = self.w["npcs"][0]
        self.assertEqual(npc["inventory"], [])
        self.assertIsNone(npc["equipment"]["main_hand"])
        self.assertEqual(npc["item_consents"], {})
        self.assertTrue(any(i["item_id"] == dagger for i in self.w["inventory"]))
        self.unchanged_rejection(f"/item receive {dagger} vendor", "item_not_owned")

    def test_consent_bound_to_recipient_and_operation(self):
        _, dagger = self.prepare()
        self.w["npcs"][0]["item_consents"] = {
            dagger: {"operation": "receive", "recipient": "someone_else"}}
        self.unchanged_rejection(f"/item receive {dagger} vendor", "npc_consent_required")

    def test_player_gift_needs_acceptance(self):
        sword, _ = self.prepare()
        self.unchanged_rejection(f"/item give {sword} vendor", "npc_consent_required")
        self.w["npcs"][0]["item_consents"] = {
            sword: {"operation": "give", "recipient": "vendor"}}
        self.assertTrue(self.run_item(f"/item give {sword} vendor")["success"])
        self.assertTrue(any(i["item_id"] == sword for i in self.w["npcs"][0]["inventory"]))

    def test_remote_npc_cannot_transfer(self):
        _, dagger = self.prepare()
        self.w["npcs"][0]["location"] = "elsewhere"
        self.unchanged_rejection(f"/item receive {dagger} vendor", "npc_unavailable")

    def test_buy_sell_conserves_money_and_item_identity(self):
        _, dagger = self.prepare()
        self.w["shops"][0].update(item_offers_cp={dagger: 200}, buys_equipment=True)
        self.assertTrue(self.run_item(f"/item buy {dagger} shop")["success"])
        self.assertEqual(self.w["currency"], {"player": 4800, "vendor": 5200})
        self.assertTrue(self.run_item(f"/item sell {dagger} shop")["success"])
        self.assertEqual(self.w["currency"], {"player": 4900, "vendor": 5100})
        self.assertEqual(self.w["npcs"][0]["inventory"][0]["item_id"], dagger)
        self.unchanged_rejection(f"/item buy {dagger} shop", "stock_or_price_unavailable")

    def test_insufficient_funds_rolls_back_entire_buy(self):
        _, dagger = self.prepare()
        self.w["shops"][0]["item_offers_cp"] = {dagger: 200}
        self.w["currency"]["player"] = 199
        self.unchanged_rejection(f"/item buy {dagger} shop", "insufficient_funds")

    def test_unknown_price_is_not_invented(self):
        _, dagger = self.prepare()
        self.w["npcs"][0]["inventory"][0].pop("weapon_id")
        self.unchanged_rejection(f"/item buy {dagger} shop", "price_source_unavailable")

    def test_duplicate_ids_reject_without_partial_migration(self):
        sword, _ = self.prepare()
        self.w["npcs"][0]["inventory"][0]["item_id"] = sword
        self.unchanged_rejection("/item list", "duplicate_item_identity")

    def test_active_combat_is_not_bypassed(self):
        self.w["combat"]["active"] = True
        self.unchanged_rejection("/item list", "existing_action_owner_required")

    def test_terminal_or_unconscious_actor_is_not_bypassed(self):
        self.s.character["current_hp"] = 0
        self.unchanged_rejection("/item list", "existing_action_owner_required")

    def test_armor_changes_fail_closed(self):
        self.w["inventory"].append("Chain Mail")
        self.prepare()
        armor = next(i for i in self.w["inventory"] if i["name"] == "Chain Mail")["item_id"]
        self.unchanged_rejection(f"/item drop {armor}", "armor_owner_required")

    def test_legacy_and_record_save_roundtrip(self):
        for migrated in (False, True):
            if migrated:
                self.prepare()
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "save.json"
                self.s.save_game(path)
                restored = game.create_session()
                self.assertTrue(restored.load_game(path))
                self.assertEqual(restored.world_state["inventory"], self.w["inventory"])
                self.assertEqual(restored.world_state["currency"], self.w["currency"])

    def test_public_projection_preserves_string_contract(self):
        self.prepare()
        items = serialize_session_state(self.s)["inventory"]
        self.assertTrue(all(isinstance(i, str) for i in items))
        self.assertTrue(any("[item_" in i for i in items))

    def test_session_and_rng_isolation(self):
        other = game.create_session()
        before, rng = copy.deepcopy(other.world_state), self.s.rng.getstate()
        self.prepare()
        self.assertEqual(other.world_state, before)
        self.assertEqual(self.s.rng.getstate(), rng)

    def test_reward_requires_completed_existing_quest(self):
        self.unchanged_rejection("/item reward unknown", "quest_not_completed")

    def test_reward_atomicity_and_once_only(self):
        _, dagger = self.prepare()
        # Contract fixture, not a new production quest or reward definition.
        self.w["quests"] = [{"quest_id": "fixture", "status": "completed"}]
        self.w["item_rewards"] = {"fixture": {
            "source_npc_id": "vendor", "item_ids": [dagger], "currency_cp": 300}}
        self.assertTrue(self.run_item("/item reward fixture")["success"])
        self.assertEqual(self.w["currency"], {"player": 5300, "vendor": 4700})
        self.assertEqual(self.w["npcs"][0]["inventory"], [])
        self.unchanged_rejection("/item reward fixture", "reward_already_claimed")

    def test_reward_missing_second_item_rolls_back_all_sources(self):
        _, dagger = self.prepare()
        self.w["quests"] = [{"quest_id": "fixture", "status": "completed"}]
        self.w["item_rewards"] = {"fixture": {
            "source_npc_id": "vendor", "item_ids": [dagger, "missing"], "currency_cp": 300}}
        self.unchanged_rejection("/item reward fixture", "item_not_owned")

    def test_bad_command_cannot_commit_migration(self):
        self.unchanged_rejection("/item explode", "invalid_item_command")

    def test_bad_wallet_type_rejects(self):
        self.w["currency"]["player"] = True
        self.unchanged_rejection("/item list", "invalid_currency")

    def test_legacy_drop_still_works_after_migration(self):
        self.prepare()
        result = self.s.update_inventory_from_player("Kılıcı yere bırak")
        self.assertIn("envanterden yere taşındı", result)


if __name__ == "__main__":
    unittest.main()
