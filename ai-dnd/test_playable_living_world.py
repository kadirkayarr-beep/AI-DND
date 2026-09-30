"""Offline regression gates for the bounded playable living-world layer."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import game
import living_world


class PlayableLivingWorldTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=1729)
        self.world = self.session.world_state
        self.world["location"] = "forest"
        self.root_location = self.world["location"]

    def test_look_materializes_once_and_presence_is_natural(self):
        first = self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        self.assertEqual(first["direct_result"]["action"], "explore")
        scene = self.world["scene_state"]["scenes"][self.root_location]
        self.assertTrue(scene["materialized"])
        scene_id = scene["id"]
        feature_ids = {
            item["id"] for item in self.world["features"]
            if item.get("location") == self.root_location
        }

        second = self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        self.assertEqual(second["direct_result"]["action"], "explore")
        self.assertEqual(
            self.world["scene_state"]["scenes"][self.root_location]["id"],
            scene_id,
        )
        self.assertEqual(
            {
                item["id"] for item in self.world["features"]
                if item.get("location") == self.root_location
            },
            feature_ids,
        )

        self.world["npcs"].extend([
            {
                "id": "npc_presence_one",
                "name": "Aylin",
                "role": "Kent sakini",
                "location": self.root_location,
                "tags": [],
            },
            {
                "id": "npc_presence_two",
                "name": "Tuna",
                "role": "Muhafız",
                "location": self.root_location,
                "tags": [],
            },
        ])
        presence = self.session.plan_living_world_turn("Burada kimler var?")
        response = presence["direct_result"]["direct_response"]
        self.assertNotIn("kayıtlı", response.casefold())
        self.assertNotIn("npc", response.casefold())
        self.assertIn("Aylin", response)
        self.assertIn("Tuna", response)
        self.assertTrue(response.strip())

    def test_selected_npc_smalltalk_uses_grounded_responses(self):
        npc = {"id": "npc_smalltalk", "name": "Melis"}

        activity = game._direct_npc_smalltalk_response(
            "Bugün burada neler oluyor?", npc
        )
        self.assertEqual(
            activity,
            "Melis, “Şimdilik göze çarpan özel bir şey yok; "
            "ben kendi işimle ilgileniyorum,” diye yanıt verir.",
        )
        day = game._direct_npc_smalltalk_response(
            "Bugün günün nasıl gidiyor?", npc
        )
        self.assertEqual(
            day,
            "Melis, “Fena değil, teşekkür ederim. "
            "Sorduğun için sağ ol,” diye karşılık verir.",
        )
        guard = game._direct_npc_smalltalk_response(
            "Bugün yol ve güvenlik nasıl?",
            {"id": "npc_guard", "name": "Duru"},
        )
        self.assertEqual(
            guard,
            "Duru, “Yol ve güvenlik hakkında doğrulanmış bilgim yok; "
            "kesin bir şey söyleyemem,” diye yanıt verir.",
        )
        greeting = game._direct_npc_smalltalk_response(
            "Onunla kısa bir selamlaşıyorum.", npc
        )
        self.assertEqual(
            greeting,
            "Melis, “Merhaba,” diye karşılık verir.",
        )
        self.assertIsNone(
            game._direct_npc_smalltalk_response("Doğu'da ne var?", npc)
        )

    def test_merchant_search_creates_local_person_and_shop_without_trade(self):
        plan = self.session.plan_living_world_turn(
            "Bir tüccar arıyorum."
        )
        self.assertEqual(plan["direct_result"]["action"], "local_search")
        self.assertEqual(plan["direct_result"]["status"], "found")
        self.assertEqual(len(self.world["shops"]), 1)
        shop = self.world["shops"][0]
        merchant = next(
            item for item in self.world["npcs"]
            if item["id"] == shop["shopkeeper_id"]
        )
        self.assertEqual(shop["location"], self.root_location)
        self.assertEqual(merchant["location"], self.root_location)
        self.assertIn("campaign_local", shop["tags"])
        self.assertIn("campaign_local", merchant["tags"])
        self.assertNotIn("stock", shop)
        self.assertNotIn("gold", shop)
        self.assertNotIn("inventory", shop)

        negative = self.session.plan_living_world_turn(
            "Bir tüccar aramıyorum."
        )
        self.assertIsNone(negative["direct_result"])
        self.assertEqual(len(self.world["shops"]), 1)

    def test_tavern_search_enter_exit_and_return_use_local_parent(self):
        search = self.session.plan_living_world_turn(
            "Yakınlarda bir taverna arıyorum."
        )
        self.assertEqual(search["direct_result"]["action"], "local_search")
        tavern_id = search["direct_result"]["target_id"]
        tavern = self.world["locations"][tavern_id]
        self.assertEqual(tavern["parent_location_id"], self.root_location)
        self.assertEqual(tavern["exit_location_id"], self.root_location)
        self.assertEqual(tavern["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.world["flags"]["turn_index"] += 1

        enter = self.session.plan_living_world_turn("Enter the tavern.")
        self.assertEqual(enter["direct_result"]["status"], "completed")
        self.assertEqual(self.world["location"], tavern_id)
        self.world["flags"]["turn_index"] += 1
        self.assertEqual(
            self.world["scene_state"]["player_position"]["location_id"],
            tavern_id,
        )
        first_visit = self.world["scene_state"]["scenes"][tavern_id]["visit_revision"]

        exit_plan = self.session.plan_living_world_turn("Tavernadan dışarı çıkıyorum.")
        self.assertEqual(exit_plan["direct_result"]["action"], "exit")
        self.assertEqual(self.world["location"], self.root_location)
        self.world["flags"]["turn_index"] += 1
        self.assertEqual(
            living_world.classify_scene_action("Emre Hanı içine giriyorum."),
            "enter",
        )
        return_plan = self.session.plan_living_world_turn(
            f"{tavern['name']} içine giriyorum."
        )
        self.assertEqual(return_plan["direct_result"]["action"], "enter")
        self.world["flags"]["turn_index"] += 1
        self.assertEqual(self.world["location"], tavern_id)
        self.assertGreater(
            self.world["scene_state"]["scenes"][tavern_id]["visit_revision"],
            first_visit,
        )

    def test_travel_uses_last_named_location_as_destination(self):
        search = self.session.plan_living_world_turn(
            "Yakınlarda bir taverna arıyorum."
        )
        tavern_id = search["direct_result"]["target_id"]
        tavern = self.world["locations"][tavern_id]
        self.world["location"] = tavern_id
        root_name = self.world["locations"][self.root_location]["name"]
        travel_text = (
            f"{tavern['name']} içinden {root_name} konumuna dönüyorum."
        )

        self.assertEqual(
            self.session._location_reference_in_text(travel_text),
            tavern_id,
        )
        intent = self.session.normalize_intent(
            {
                "intent": "travel",
                "target": {"type": "location", "reference": tavern["name"]},
            },
            travel_text,
        )
        self.assertEqual(intent["intent"], "travel")
        self.assertEqual(intent["target"]["reference"], self.root_location)

        validated = self.session.validate_intent(intent, travel_text)
        self.assertEqual(
            validated["target"]["reference"], self.root_location
        )
        result = self.session.execute_intent(validated, travel_text)
        self.assertTrue(result["success"])
        self.assertEqual(result["new_location"], self.root_location)
        self.assertEqual(self.world["location"], self.root_location)

    def test_feature_identity_and_scene_projection_survive_save_load(self):
        self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        feature = self.session.create_local_feature({
            "location": self.root_location,
            "name": "Pencere yanı meşe masa",
            "description": "Çizikleri olan sağlam bir masa.",
            "kind": "table",
            "aliases": ["masa", "meşe masa"],
        })
        self.assertIsNotNone(feature)
        self.assertTrue(feature["id"].startswith("feature_"))
        sit = self.session.plan_living_world_turn(
            f"{feature['name']} yanına oturuyorum.",
            target_id=feature["id"],
        )
        self.assertEqual(sit["direct_result"]["target_id"], feature["id"])
        self.assertEqual(
            sit["direct_result"]["direct_response"],
            "Seçtiğin özelliğin yanındaki yere oturuyorsun.",
        )
        inspect = self.session.plan_living_world_turn(
            f"{feature['name']} üzerindeki ayrıntıyı inceliyorum.",
            target_id=feature["id"],
        )
        inspect_result = inspect["direct_result"]
        self.assertEqual(inspect_result["action"], "inspect")
        self.assertEqual(inspect_result["status"], "observed")
        self.assertEqual(inspect_result["target_id"], feature["id"])
        public_scene = living_world.public_scene_projection(
            self.world, self.world["flags"]["turn_index"]
        )
        self.assertIn(feature["id"], {item["id"] for item in public_scene["features"]})

        expected_id = feature["id"]
        expected_scene_id = public_scene["id"]
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "scene-save.json"
            self.session.save_game(save_path)
            self.world["features"].clear()
            self.world["scene_state"]["scenes"].clear()
            self.session.load_game(save_path)

        restored = living_world.public_scene_projection(
            self.world, self.world["flags"]["turn_index"]
        )
        self.assertEqual(restored["id"], expected_scene_id)
        self.assertIn(expected_id, {item["id"] for item in restored["features"]})

    def test_public_scene_referent_exposes_only_one_addressable_alias(self):
        self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        turn_index = self.world["flags"]["turn_index"]
        ref = living_world.create_scene_referent(
            self.world,
            self.root_location,
            turn_index,
            description="A traveler adjusts a satchel.",
            aliases=["traveler", "person with a satchel"],
        )

        public_scene = living_world.public_scene_projection(
            self.world, turn_index
        )
        public_ref = next(
            item for item in public_scene["referents"] if item["id"] == ref["id"]
        )

        self.assertEqual(public_ref["addressable_alias"], "traveler")
        self.assertNotIn("aliases", public_ref)

    def test_observing_referent_does_not_promote_it_to_an_npc(self):
        self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        turn_index = self.world["flags"].get("turn_index", 0) + 1
        description = "Girişteki ziyaretçi çantasının kayışını düzeltiyor."
        ref = living_world.create_scene_referent(
            self.world,
            self.root_location,
            turn_index,
            description=description,
            aliases=["ziyaretçi"],
        )

        plan = self.session.plan_living_world_turn(
            "Ziyaretçi etkinliğine dikkat ediyorum."
        )
        result = plan["direct_result"]

        self.assertEqual(result["action"], "explore")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["target_id"], ref["id"])
        self.assertEqual(result["direct_response"], description)
        self.assertEqual(ref["lifecycle"], "presented")
        self.assertIsNone(ref.get("promoted_npc_id"))

    def test_legacy_save_migrates_feature_ids_idempotently(self):
        location = self.root_location
        legacy = self.session.serialize_game_state()
        legacy_world = legacy["world_state"]
        legacy_world.pop("scene_state", None)
        legacy_world["features"] = [{
            "location": location,
            "name": "Eski taş masa",
            "description": "Duvar kenarında duran bir masa.",
        }]
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "legacy-save.json"
            save_path.write_text(
                json.dumps(legacy, ensure_ascii=False),
                encoding="utf-8",
            )
            self.session.load_game(save_path)
            first_id = self.world["features"][0]["id"]
            self.session.load_game(save_path)
            second_id = self.world["features"][0]["id"]
        self.assertTrue(first_id.startswith("feature_"))
        self.assertEqual(first_id, second_id)

    def test_invalid_scene_state_load_is_atomic(self):
        before = self.session.serialize_game_state()
        corrupt = copy.deepcopy(before)
        scenes = corrupt["world_state"]["scene_state"]["scenes"]
        scenes["corrupt_scene"] = {
            "id": None,
            "location_id": "missing",
            "kind": "tavern",
            "referents": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "bad-save.json"
            save_path.write_text(
                json.dumps(corrupt, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises((ValueError, TypeError)):
                self.session.load_game(save_path)
        self.assertEqual(self.session.serialize_game_state(), before)

    def test_lore_guard_allows_local_craft_role_and_personal_arrival(self):
        npc = self.session.create_npc_from_ai({
            "name": "Tuna",
            "role": "demirci",
            "location": self.root_location,
            "appearance": "Önlüğünde demir tozu olan sakin bir usta.",
            "personality": "Dikkatli ve ölçülü.",
            "relationship": "neutral",
            "knowledge": [],
            "backstory": "",
        })
        self.assertIsNotNone(npc)
        lore_context = {"sections": {"verified_entities": []}}

        self.assertFalse(game._narration_has_unsupported_lore_claim(
            "Demirci tezgâhının üzerindeki aletleri düzenliyor.",
            [],
            lore_context,
            self.world,
        ))
        self.assertFalse(game._narration_has_unsupported_lore_claim(
            "Sana söylüyorum, iki gün önce geldim.",
            [],
            lore_context,
            self.world,
        ))
        self.assertTrue(game._narration_has_unsupported_lore_claim(
            "A town is two days away.",
            [],
            lore_context,
            self.world,
        ))
        self.assertTrue(game._narration_has_unsupported_lore_claim(
            "Gümüş işçiliği bu kasabanın bütün ekonomisini yönetiyor.",
            [],
            lore_context,
            self.world,
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)