import json
import unittest
from unittest.mock import patch

import game
from api.serializers import serialize_session_state


def shop_response(
    narration="Mira welcomes the player at Green Lantern.",
    create_shops=None,
):
    return {
        "narration": narration,
        "world_updates": {
            "create_locations": [],
            "create_npcs": [],
            "update_npcs": [],
            "create_features": [],
            "create_shops": create_shops or [],
            "events": [],
        },
        "lore_claims": [],
        "valid_response": True,
    }


def valid_shop_proposal():
    return {
        "name": "Green Lantern",
        "description": "A small timber storefront with a painted green sign.",
        "shopkeeper": {
            "name": "Mira",
            "personality": "Patient and observant.",
            "appearance": "A short-haired human in a plain apron.",
        },
    }


class CampaignShopTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session()
        self.session.world_state["location"] = "tavern"

    def test_explicit_request_creates_one_server_tagged_shop_and_owner(self):
        self.session.lore_authority_context = game._empty_lore_authority_context()
        with patch(
            "game.ask_dungeon_master",
            return_value=shop_response(create_shops=[valid_shop_proposal()]),
        ) as ask:
            result = self.session.run_player_turn("Find a local merchant.")

        shop = self.session.world_state["shops"][0]
        owner = next(
            npc for npc in self.session.world_state["npcs"]
            if npc["id"] == shop["shopkeeper_id"]
        )
        self.assertEqual(result["action_result"]["action"], "shop_setup")
        self.assertEqual(shop["id"], "shop_001")
        self.assertEqual(shop["location"], "tavern")
        self.assertEqual(shop["tags"], ["campaign_local", "shop"])
        self.assertEqual(shop["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(owner["id"], "npc_001")
        self.assertEqual(owner["role"], "Shopkeeper")
        self.assertEqual(owner["shop_id"], shop["id"])
        self.assertEqual(
            owner["tags"],
            ["campaign_local", "shopkeeper", "shop:shop_001"],
        )
        self.assertIn("world.shops", result["action_result"]["state_changes"])
        self.assertEqual(
            result["_engine_event_evidence"]["procedural_entity_ids"],
            ["npc_001", "shop_001"],
        )
        self.assertTrue(ask.call_args.kwargs["allow_new_shops"])
        self.assertFalse(ask.call_args.kwargs["allow_new_npcs"])

        projected = serialize_session_state(self.session)
        self.assertEqual(projected["shops"][0]["id"], shop["id"])
        self.assertEqual(projected["shops"][0]["tags"], shop["tags"])
        projected_owner = next(
            npc for npc in projected["npcs"] if npc["id"] == owner["id"]
        )
        self.assertEqual(projected_owner["shop_id"], shop["id"])
        self.assertEqual(projected_owner["tags"], owner["tags"])

    def test_live_shop_turn_uses_a_narrow_structured_response_schema(self):
        self.session.lore_authority_context = game._empty_lore_authority_context()
        model_response = {
            "world_updates": {
                "create_locations": [],
                "create_npcs": [],
                "update_npcs": [],
                "create_features": [],
                "create_shops": [valid_shop_proposal()],
                "events": [],
            },
            "narration": "Lord Vharion sells swords for gold from his shop.",
            "lore_claims": [],
        }
        with patch(
            "game.ollama.chat",
            return_value={
                "message": {
                    "content": json.dumps(model_response, ensure_ascii=False)
                }
            },
        ) as chat:
            result = self.session.run_player_turn("Find a local merchant.")

        schema = chat.call_args.kwargs["format"]
        world_updates = schema["properties"]["world_updates"]
        properties = world_updates["properties"]
        self.assertIn("create_shops", world_updates["required"])
        self.assertEqual(properties["create_shops"]["minItems"], 1)
        self.assertEqual(properties["create_shops"]["maxItems"], 1)
        for field in (
            "create_locations",
            "create_npcs",
            "update_npcs",
            "create_features",
            "events",
        ):
            self.assertEqual(properties[field]["maxItems"], 0)
        self.assertEqual(schema["properties"]["lore_claims"]["maxItems"], 0)
        self.assertEqual(len(self.session.world_state["shops"]), 1)
        self.assertEqual(len(self.session.world_state["npcs"]), 1)
        self.assertEqual(result["action_result"]["action"], "shop_setup")
        self.assertEqual(result["action_result"]["status"], "created")
        self.assertIn("yerel dükkân", result["narration"])
        self.assertNotIn("Vharion", result["narration"])
        self.assertNotIn("gold", result["narration"])

    def test_player_name_memory_is_bound_to_the_selected_npc_id(self):
        self.session.lore_authority_context = game._empty_lore_authority_context()
        self.session.create_shop_from_proposal(valid_shop_proposal())
        keeper = self.session.world_state["npcs"][0]
        other_npc = {
            "id": "npc_other",
            "name": "Rana",
            "role": "Guide",
            "location": "tavern",
            "memory": [],
        }
        self.session.world_state["npcs"].append(other_npc)
        response = shop_response(narration="Mira listens carefully.")

        with (
            patch("game.parse_player_intent", return_value={}),
            patch("game.normalize_intent", return_value={}),
            patch(
                "game.validate_intent",
                return_value={"intent_type": "narrative"},
            ),
            patch("game.ask_dungeon_master", return_value=response),
        ):
            self.session.run_player_turn(
                "Benim adım Arven. Kendimi sana tanıtıyorum; lütfen bunu hatırla.",
                target_id=keeper["id"],
            )
            recall = self.session.run_player_turn(
                "Ben sana daha önce adımı söylemiştim. Adım neydi, hatırlıyor musun?",
                target_id=keeper["id"],
            )
            recall_safety = dict(self.session.narration_safety_history[-1])
            other_recall = self.session.run_player_turn(
                "Ben sana daha önce adımı söylemiştim. Adım neydi, hatırlıyor musun?",
                target_id=other_npc["id"],
            )
            other_recall_safety = dict(self.session.narration_safety_history[-1])
            invalid_recall = self.session.run_player_turn(
                "Ben sana daha önce adımı söylemiştim. Adım neydi, hatırlıyor musun?",
                target_id="npc_missing",
            )

        self.assertTrue(
            any(
                isinstance(entry, dict)
                and entry.get("speaker") == "player"
                and game._explicit_player_name_disclosure(entry.get("text"))
                == "Arven"
                for entry in keeper.get("memory", [])
            )
        )
        self.assertIn("Arven", recall["narration"])
        self.assertNotIn("Arven", other_recall["narration"])
        self.assertNotIn("Arven", invalid_recall["narration"])
        self.assertEqual(
            recall_safety["reason_code"],
            "NPC_MEMORY_SUPPORTED_PLAYER_NAME",
        )
        self.assertEqual(
            other_recall_safety["reason_code"],
            "NPC_MEMORY_UNSUPPORTED_CLAIM",
        )
        self.assertEqual(recall_safety["handling"], "python_memory_response")
        self.assertEqual(other_recall_safety["handling"], "python_memory_response")

    def test_narration_alone_cannot_register_a_shop_or_shopkeeper(self):
        response = shop_response(
            narration="Mira opens a shop on the street.",
            create_shops=[],
        )
        with (
            patch("game.parse_player_intent", return_value={}),
            patch("game.normalize_intent", return_value={}),
            patch(
                "game.validate_intent",
                return_value={"intent_type": "narrative"},
            ),
            patch(
                "game.execute_intent",
                return_value={
                    "action": "narrative",
                    "success": True,
                    "state_changes": [],
                },
            ),
            patch("game.ask_dungeon_master", return_value=response) as ask,
        ):
            result = self.session.run_player_turn("The wind is blowing.")

        self.assertEqual(self.session.world_state["shops"], [])
        self.assertEqual(self.session.world_state["npcs"], [])
        self.assertFalse(ask.call_args.kwargs["allow_new_shops"])
        self.assertEqual(result["action_result"]["state_changes"], [])

    def test_explicit_request_without_validated_proposal_does_not_commit(self):
        response = shop_response(
            narration="A new shop appears, run by Mira.",
            create_shops=[],
        )
        with patch("game.ask_dungeon_master", return_value=response):
            result = self.session.run_player_turn("Find a local merchant.")

        self.assertEqual(self.session.world_state["shops"], [])
        self.assertEqual(self.session.world_state["npcs"], [])
        self.assertEqual(result["action_result"]["status"], "proposal_rejected")
        self.assertIn("hiçbir dükkân eklenmedi", result["narration"])

    def test_only_one_shop_and_shopkeeper_can_be_created(self):
        created = self.session.create_shop_from_proposal(valid_shop_proposal())
        self.assertIsNotNone(created)

        with patch("game.ask_dungeon_master") as ask:
            result = self.session.run_player_turn("Create another shop.")

        self.assertEqual(len(self.session.world_state["shops"]), 1)
        self.assertEqual(len(self.session.world_state["npcs"]), 1)
        self.assertEqual(result["action_result"]["status"], "limit_reached")
        ask.assert_not_called()

    def test_shop_economy_requests_do_not_change_items_or_currency(self):
        self.session.create_shop_from_proposal(valid_shop_proposal())
        inventory_before = list(self.session.world_state["inventory"])
        shops_before = list(self.session.world_state["shops"])
        npcs_before = list(self.session.world_state["npcs"])

        with patch("game.ask_dungeon_master") as ask:
            result = self.session.run_player_turn(
                "What are your prices, and can I buy a sword?"
            )

        self.assertEqual(result["action_result"]["action"], "shop_economy")
        self.assertEqual(self.session.world_state["inventory"], inventory_before)
        self.assertEqual(self.session.world_state["shops"], shops_before)
        self.assertEqual(self.session.world_state["npcs"], npcs_before)
        ask.assert_not_called()

    def test_shopkeeper_cannot_be_created_through_generic_npc_updates(self):
        updates = {
            "create_npcs": [{
                "name": "Mira",
                "role": "Merchant",
                "location": "tavern",
            }],
            "create_shops": [valid_shop_proposal()],
        }
        validated = self.session.validate_world_updates(
            updates,
            allow_new_npcs=True,
            allow_new_shops=False,
        )

        self.assertEqual(validated["create_npcs"], [])
        self.assertEqual(validated["create_shops"], [])
        self.assertEqual(self.session.world_state["npcs"], [])
        self.assertEqual(self.session.world_state["shops"], [])

    def test_shop_proposals_with_economy_details_are_rejected(self):
        proposal = valid_shop_proposal()
        proposal["description"] = "A shop with a list of prices and stocked potions."
        validated = self.session.validate_world_updates(
            {"create_shops": [proposal]},
            allow_new_shops=True,
        )

        self.assertEqual(validated["create_shops"], [])
        self.assertEqual(self.session.world_state["shops"], [])


if __name__ == "__main__":
    unittest.main()