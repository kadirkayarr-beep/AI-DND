"""Offline regression gates for the bounded playable living-world layer."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import interaction_adventure
import living_world
import local_dialogue


class PlayableLivingWorldTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=1729)
        self.world = self.session.world_state
        self.world["location"] = "forest"
        self.root_location = self.world["location"]

    def _set_npc_conversation_deadline(self, turn_index, *, active=True):
        npcs = [
            {
                "id": "npc_deadline_aylin", "name": "Aylin",
                "role": "Tüccar", "location": self.root_location,
                "tags": [],
            },
            {
                "id": "npc_deadline_tuna", "name": "Tuna",
                "role": "Muhafız", "location": self.root_location,
                "tags": [],
            },
        ]
        self.world["npcs"] = npcs
        self.world["flags"].update({
            "active_npc_id": npcs[0]["id"] if active else None,
            "last_npc_id": npcs[0]["id"],
            "active_npc_until_turn": 12,
            "turn_index": turn_index,
        })
        return npcs

    def test_npc_conversation_deadline_is_inclusive(self):
        for active in (True, False):
            with self.subTest(active_npc_present=active):
                npcs = self._set_npc_conversation_deadline(12, active=active)

                result = self.session.resolve_npc_reference("Ona adını soruyorum.")

                self.assertEqual(result["status"], "found")
                self.assertEqual(result["npc"]["id"], npcs[0]["id"])
                flags = self.world["flags"]
                self.assertEqual(flags["active_npc_id"], npcs[0]["id"])
                self.assertEqual(flags["last_npc_id"], npcs[0]["id"])
                self.assertEqual(flags["active_npc_until_turn"], 18)

    def test_npc_conversation_first_turn_after_deadline_needs_clarification(self):
        for active in (True, False):
            with self.subTest(active_npc_present=active):
                npcs = self._set_npc_conversation_deadline(13, active=active)
                before = copy.deepcopy(self.world)

                result = self.session.resolve_npc_reference("Ona adını soruyorum.")

                self.assertEqual(result["status"], "ambiguous")
                self.assertEqual(
                    {npc["id"] for npc in result["npcs"]},
                    {npc["id"] for npc in npcs},
                )
                self.assertNotIn("npc", result)
                self.assertEqual(self.world, before)

    def test_pronoun_greetings_select_conversation_at_deadline(self):
        for active in (True, False):
            for player_input in ("Ona selam veriyorum.", "Kendisine selam veriyorum."):
                with self.subTest(active_npc_present=active, player_input=player_input):
                    npcs = self._set_npc_conversation_deadline(12, active=active)

                    result = self.session.resolve_npc_reference(player_input)

                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["npc"]["id"], npcs[0]["id"])
                    self.assertEqual(self.world["flags"]["active_npc_id"], npcs[0]["id"])
                    self.assertEqual(self.world["flags"]["last_npc_id"], npcs[0]["id"])
                    self.assertEqual(self.world["flags"]["active_npc_until_turn"], 18)

    def test_pronoun_greetings_are_ambiguous_after_conversation_expiry(self):
        for active in (True, False):
            for player_input in ("Ona selam veriyorum.", "Kendisine selam veriyorum."):
                with self.subTest(active_npc_present=active, player_input=player_input):
                    npcs = self._set_npc_conversation_deadline(13, active=active)
                    before = copy.deepcopy(self.world)

                    result = self.session.resolve_npc_reference(player_input)

                    self.assertEqual(result["status"], "ambiguous")
                    self.assertEqual(
                        {npc["id"] for npc in result["npcs"]},
                        {npc["id"] for npc in npcs},
                    )
                    self.assertNotIn("npc", result)
                    self.assertEqual(self.world, before)

    def test_pronoun_dialogue_selects_conversation_at_deadline(self):
        for active in (True, False):
            for selected_index in (0, 1):
                for player_input in (
                    "Onunla konuşuyorum.",
                    "Ondan sohbet etmesini istiyorum.",
                ):
                    with self.subTest(
                        active_npc_present=active, selected_index=selected_index,
                        player_input=player_input,
                    ):
                        npcs = self._set_npc_conversation_deadline(12, active=active)
                        selected_id = npcs[selected_index]["id"]
                        flags = self.world["flags"]
                        flags["active_npc_id"] = selected_id if active else None
                        flags["last_npc_id"] = selected_id

                        result = self.session.resolve_npc_reference(player_input)

                        self.assertEqual(result["status"], "found")
                        self.assertEqual(result["npc"]["id"], selected_id)
                        self.assertEqual(flags["active_npc_id"], selected_id)
                        self.assertEqual(flags["last_npc_id"], selected_id)
                        self.assertEqual(flags["active_npc_until_turn"], 18)

    def test_pronoun_dialogue_is_ambiguous_after_conversation_expiry(self):
        for active in (True, False):
            for player_input in (
                "Onunla konuşuyorum.",
                "Ondan sohbet etmesini istiyorum.",
            ):
                with self.subTest(active_npc_present=active, player_input=player_input):
                    npcs = self._set_npc_conversation_deadline(13, active=active)
                    before = copy.deepcopy(self.world)

                    result = self.session.resolve_npc_reference(player_input)

                    self.assertEqual(result["status"], "ambiguous")
                    self.assertEqual(
                        {npc["id"] for npc in result["npcs"]},
                        {npc["id"] for npc in npcs},
                    )
                    self.assertNotIn("npc", result)
                    self.assertEqual(self.world, before)

    def test_unknown_named_dialogue_with_pronouns_rejects_conversation_fallback(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for player_input in (
                    "Onunla konuşuyorum, Bora'yla konuşuyorum.",
                    "Bora'yla konuşuyorum, Onunla konuşuyorum.",
                    "Ondan sohbet etmesini istiyorum, Bora'yla konuşuyorum.",
                    "Bora'yla konuşuyorum, Ondan sohbet etmesini istiyorum.",
                ):
                    with self.subTest(
                        turn_index=turn_index, active_npc_present=active,
                        player_input=player_input,
                    ):
                        self._set_npc_conversation_deadline(turn_index, active=active)
                        before = copy.deepcopy(self.world)

                        result = self.session.resolve_npc_reference(player_input)

                        self.assertEqual(result["status"], "none")
                        self.assertIsNone(result["npc"])
                        self.assertEqual(self.world, before)

    def test_unknown_named_ablative_dialogue_rejects_conversation_fallback(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for target in ("Bora'dan", "Ece'den", "Murat'tan", "Mert'ten", "Bora’dan"):
                    named_clause = f"{target} sohbet etmesini istiyorum"
                    for player_input in (
                        f"{named_clause}.",
                        f"Ondan sohbet etmesini istiyorum, {named_clause}.",
                        f"{named_clause}, Ondan sohbet etmesini istiyorum.",
                    ):
                        with self.subTest(
                            turn_index=turn_index, active_npc_present=active,
                            player_input=player_input,
                        ):
                            self._set_npc_conversation_deadline(turn_index, active=active)
                            before = copy.deepcopy(self.world)

                            result = self.session.resolve_npc_reference(player_input)

                            self.assertEqual(result["status"], "none")
                            self.assertIsNone(result["npc"])
                            self.assertEqual(self.world, before)

    def test_unknown_named_greetings_do_not_fall_back_to_conversation(self):
        for turn_index in (12, 13):
            for player_input in (
                "Bora'ya selam veriyorum.",
                "Bora'yla konuşuyorum.",
                "Ona selam veriyorum, Bora'ya selam veriyorum.",
            ):
                with self.subTest(turn_index=turn_index, player_input=player_input):
                    self._set_npc_conversation_deadline(turn_index)
                    before = copy.deepcopy(self.world)

                    result = self.session.resolve_npc_reference(player_input)

                    self.assertEqual(result["status"], "none")
                    self.assertIsNone(result["npc"])
                    self.assertEqual(self.world, before)

    def test_expired_npc_conversation_still_allows_explicit_name_or_role(self):
        for active in (True, False):
            for player_input in (
                "Tuna ile konuşuyorum.",
                "Muhafız ile konuşuyorum.",
                "Tuna'dan sohbet etmesini istiyorum.",
                "Muhafız'dan sohbet etmesini istiyorum.",
            ):
                with self.subTest(
                    active_npc_present=active, player_input=player_input,
                ):
                    npcs = self._set_npc_conversation_deadline(13, active=active)

                    result = self.session.resolve_npc_reference(player_input)

                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["npc"]["id"], npcs[1]["id"])
                    flags = self.world["flags"]
                    self.assertEqual(flags["active_npc_id"], npcs[1]["id"])
                    self.assertEqual(flags["last_npc_id"], npcs[1]["id"])
                    self.assertEqual(flags["active_npc_until_turn"], 19)

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
        self.assertEqual(
            shop["name"],
            f"{game._turkish_genitive_form(merchant['name'])} Tezgâhı",
        )
        self.assertEqual(game._turkish_genitive_form("Veyra"), "Veyra'nın")
        self.assertEqual(game._turkish_genitive_form("Marek"), "Marek'in")

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
            "“Pencere yanı meşe masa” yakınında uygun bir yere oturup yerleşiyorsun.",
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
        turn_index = self.world["flags"].get("turn_index", 0)
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

    def _narration_projection_referent(self, session=None, *, promoted=True):
        session = session or self.session
        world = session.world_state
        world["location"] = self.root_location
        turn_index = world["flags"]["turn_index"]
        living_world.ensure_scene_record(world, self.root_location, turn_index)
        ref = living_world.create_scene_referent(
            world,
            self.root_location,
            turn_index,
            description="Girişteki ziyaretçi çantasının kayışını düzeltiyor.",
            aliases=["ziyaretçi", "çantalı yolcu"],
        )
        npc = (
            session._promote_scene_referent(ref, self.root_location)
            if promoted
            else session.create_npc_from_ai({
                "name": "Melis",
                "role": "Kent sakini",
                "location": self.root_location,
            })
        )
        self.assertIsNotNone(npc)
        return ref, npc

    def test_narration_projection_promoted_prompt_uses_persistent_npc(self):
        ref, npc = self._narration_projection_referent()

        context = json.loads(self.session._living_world_prompt_context())

        self.assertEqual(
            [item["id"] for item in context["visible_npcs"]],
            [npc["id"]],
        )
        self.assertEqual(context["visible_npcs"][0]["name"], npc["name"])
        self.assertNotIn(
            ref["id"],
            {item["id"] for item in context["background_referents"]},
        )
        self.assertEqual(context["background_referents"], [])

    def test_narration_projection_promoted_presence_omits_anonymous_description(self):
        ref, npc = self._narration_projection_referent()

        presence = self.session._scene_presence_text(self.root_location)

        self.assertIn(npc["name"], presence)
        self.assertNotIn(ref["description"], presence)

    def test_narration_projection_presented_referent_remains_visible(self):
        ref, npc = self._narration_projection_referent(promoted=False)

        context = json.loads(self.session._living_world_prompt_context())
        presence = self.session._scene_presence_text(self.root_location)
        look = self.session._scene_look_text(self.root_location)

        self.assertEqual(context["background_referents"], [{
            "id": ref["id"],
            "lifecycle": "presented",
            "description": ref["description"],
        }])
        self.assertIn(npc["name"], presence)
        self.assertIn(ref["description"], presence)
        self.assertIn(ref["description"], look)
        self.assertEqual(ref["lifecycle"], "presented")
        self.assertIsNone(ref["promoted_npc_id"])

    def test_narration_projection_preserves_promoted_binding_and_public_metadata(self):
        ref, npc = self._narration_projection_referent()
        before = copy.deepcopy(self.world)
        public_before = living_world.public_scene_projection(
            self.world, self.world["flags"]["turn_index"]
        )

        self.session._living_world_prompt_context()
        self.session._scene_presence_text(self.root_location)
        self.session._scene_look_text(self.root_location)

        self.assertEqual(self.world, before)
        self.assertEqual(ref["lifecycle"], "promoted")
        self.assertEqual(ref["promoted_npc_id"], npc["id"])
        public_after = living_world.public_scene_projection(
            self.world, self.world["flags"]["turn_index"]
        )
        self.assertEqual(public_after, public_before)
        public_ref = next(
            item for item in public_after["referents"] if item["id"] == ref["id"]
        )
        self.assertEqual(public_ref["lifecycle"], "promoted")
        self.assertEqual(public_ref["promoted_npc_id"], npc["id"])
        self.assertEqual(public_ref["addressable_alias"], ref["aliases"][0])
        for alias in ref["aliases"]:
            resolved = living_world.resolve_scene_referent(
                self.world, alias, self.world["flags"]["turn_index"]
            )
            self.assertEqual(resolved["status"], "promoted")
            self.assertIs(resolved["referent"], ref)
            self.assertIs(
                self.session._promote_scene_referent(ref, self.root_location),
                npc,
            )
        self.assertEqual(self.world, before)

    def test_narration_projection_save_load_preserves_binding_and_deduplication(self):
        ref, npc = self._narration_projection_referent()
        expected_ref = copy.deepcopy(ref)
        public_before = living_world.public_scene_projection(
            self.world, self.world["flags"]["turn_index"]
        )
        restored_session = game.create_session(seed=2718)
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "promoted-referent-save.json"
            self.session.save_game(save_path)
            restored_session.load_game(save_path)

        restored_world = restored_session.world_state
        restored_ref = next(
            item for item in restored_world["scene_state"]["scenes"]
            [self.root_location]["referents"]
            if item["id"] == expected_ref["id"]
        )
        self.assertEqual(restored_ref, expected_ref)
        self.assertEqual(
            living_world.public_scene_projection(
                restored_world, restored_world["flags"]["turn_index"]
            ),
            public_before,
        )
        resolved = living_world.resolve_scene_referent(
            restored_world,
            expected_ref["aliases"][0],
            restored_world["flags"]["turn_index"],
        )
        self.assertEqual(resolved["status"], "promoted")
        self.assertEqual(resolved["referent"]["promoted_npc_id"], npc["id"])
        context = json.loads(restored_session._living_world_prompt_context())
        self.assertEqual(
            [item["id"] for item in context["visible_npcs"]],
            [npc["id"]],
        )
        self.assertEqual(context["background_referents"], [])
        self.assertNotIn(
            expected_ref["description"],
            restored_session._scene_presence_text(self.root_location),
        )

    def test_narration_projection_isolates_sessions_and_save_load(self):
        ref, npc = self._narration_projection_referent()
        other_session = game.create_session(seed=3141)
        other_ref, other_npc = self._narration_projection_referent(other_session)
        self.assertEqual(other_ref["id"], ref["id"])
        self.assertEqual(other_npc["id"], npc["id"])
        other_before = other_session.serialize_game_state()
        default_before = game.serialize_game_state()
        own_before = self.session.serialize_game_state()
        restored_session = game.create_session(seed=1618)

        self.session._living_world_prompt_context()
        self.session._scene_presence_text(self.root_location)
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "isolated-promotion-save.json"
            self.session.save_game(save_path)
            restored_session.load_game(save_path)
            restored_session._living_world_prompt_context()
            restored_session._scene_presence_text(self.root_location)

        self.assertEqual(self.session.serialize_game_state(), own_before)
        self.assertEqual(other_session.serialize_game_state(), other_before)
        self.assertEqual(game.serialize_game_state(), default_before)
        self.assertIsNot(ref, other_ref)
        self.assertIsNot(npc, other_npc)

    def test_observing_referent_does_not_promote_it_to_an_npc(self):
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
            "Ziyaretçi ne yapıyor?"
        )
        result = plan["direct_result"]

        self.assertEqual(result["action"], "explore")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["target_id"], ref["id"])
        self.assertEqual(result["direct_response"], description)
        self.assertEqual(ref["lifecycle"], "presented")
        self.assertIsNone(ref.get("promoted_npc_id"))
        self.assertEqual(self.world["npcs"], [])

    def test_unrelated_unsupported_query_does_not_expire_scene_referent(self):
        self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        turn_index = self.world["flags"].get("turn_index", 0)
        ref = living_world.create_scene_referent(
            self.world,
            self.root_location,
            turn_index,
            description="Girişteki ziyaretçi çantasının kayışını düzeltiyor.",
            aliases=["ziyaretçi"],
        )
        ref["expires_after_turn"] = turn_index

        with patch("game.ask_dungeon_master") as ask:
            result = self.session.run_player_turn("Bu iki yer arası kaç mil?")

        ask.assert_not_called()
        self.assertEqual(result["action_result"]["status"], "unverified")
        self.assertEqual(ref["lifecycle"], "presented")

    def test_expired_scene_referent_expires_when_addressed(self):
        turn_index = self.world["flags"].get("turn_index", 0)
        ref = living_world.create_scene_referent(
            self.world,
            self.root_location,
            turn_index,
            description="Girişteki ziyaretçi çantasının kayışını düzeltiyor.",
            aliases=["ziyaretçi"],
        )
        ref["expires_after_turn"] = turn_index

        plan = self.session.plan_living_world_turn("Ziyaretçi ne yapıyor?")

        self.assertEqual(plan["direct_result"]["status"], "expired")
        self.assertEqual(ref["lifecycle"], "expired")

    def test_unverified_distance_response_does_not_attribute_player_action(self):
        response = game._unverified_lore_response(
            "Bu iki yer arası kaç mil?"
        )
        self.assertIn("ölçüm kaydı yok", response)
        self.assertNotIn("vermiyorsun", response)
        self.assertNotIn("ölçün yok", response)

    def test_distance_question_mentioning_tavern_does_not_create_local_venue(self):
        self.world["location"] = "tavern"
        self.session.plan_living_world_turn("Etrafıma bakıyorum.")
        question = "Taverna ile Kale arasındaki yol mesafesi kaç kilometre?"

        self.assertFalse(living_world.is_tavern_search(question))
        self.assertTrue(
            living_world.is_tavern_search("Yakınlarda bir taverna arıyorum.")
        )
        before = {
            key: copy.deepcopy(self.world.get(key))
            for key in (
                "location",
                "locations",
                "npcs",
                "shops",
                "features",
                "doors",
                "containers",
                "scene_state",
                "quests",
                "quest_offers",
                "inventory",
            )
        }

        with patch("game.ask_dungeon_master") as ask:
            result = self.session.run_player_turn(question)

        ask.assert_not_called()
        self.assertEqual(result["action_result"]["status"], "unverified")
        self.assertIn("ölçüm kaydı yok", result["narration"])
        for key, value in before.items():
            self.assertEqual(self.world.get(key), value, key)

    def test_unverified_ruler_response_handles_turkish_inflections(self):
        for question in (
            "Bu şehrin hükümdarı kim?",
            "Bu şehrin hükümdarı kimdir?",
            "Bu şehrin yöneticisi kim?",
            "Bu ülkenin kraliçesi kim?",
        ):
            with self.subTest(question=question):
                response = game._unverified_lore_response(question)
                self.assertIn("yöneticisinin kim olduğu", response)
                self.assertNotIn("kesin yanıt belirsiz", response)

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

    @patch("game.ollama.chat", side_effect=AssertionError("City observation is deterministic"))
    def test_v11_semantic_city_observation_and_local_discovery(self, model_chat):
        city_id = "city_observation_fixture"
        self.world["locations"][city_id] = {
            "id": city_id,
            "name": "Gözlem Test Kenti",
            "type": "city",
            "connections": [],
        }
        self.world["location"] = city_id
        # See docs/interaction-quest-adventure-v1.md, "Compound-plan correction":
        # two complete comma-separated clauses are a plan, not instant actions.
        # A single observation clause exercises the deterministic explore owner.
        observation = self.session.plan_living_world_turn(
            "Şehirde dolanırken etrafımda neler var gözlemliyorum."
        )
        self.assertIsNotNone(observation["direct_result"], observation)
        self.assertEqual(observation["direct_result"]["action"], "explore")
        self.assertEqual(observation["direct_result"]["status"], "observed")
        self.assertTrue(observation["direct_result"]["success"])
        self.assertIn(
            "Gözlem Test Kenti",
            observation["direct_result"]["direct_response"],
        )
        scene = self.world["scene_state"]["scenes"][city_id]
        self.assertEqual(scene["kind"], "city")
        self.assertTrue(scene["materialized"])
        scene_before_discovery = copy.deepcopy(scene)

        venue = self.session.plan_living_world_turn(
            "Yakınlarda oturup bir şeyler içebileceğim bir yer var mı?"
        )
        self.assertIsNotNone(venue["direct_result"], venue)
        self.assertEqual(venue["direct_result"]["action"], "local_search")
        self.assertEqual(venue["direct_result"]["status"], "found")
        self.assertTrue(venue["direct_result"]["success"])
        self.assertTrue(venue["direct_result"]["direct_response"].strip())
        tavern = self.world["locations"][venue["direct_result"]["target_id"]]
        self.assertEqual(tavern["scene_kind"], "tavern")
        self.assertEqual(tavern["parent_location_id"], city_id)
        self.assertEqual(tavern["exit_location_id"], city_id)

        merchant = self.session.plan_living_world_turn(
            "Buralarda bir tücaar var mı?"
        )
        self.assertIsNotNone(merchant["direct_result"], merchant)
        self.assertEqual(merchant["direct_result"]["action"], "local_search")
        self.assertEqual(merchant["direct_result"]["status"], "found")
        self.assertTrue(merchant["direct_result"]["success"])
        self.assertTrue(merchant["direct_result"]["direct_response"].strip())
        self.assertEqual(len(self.world["shops"]), 1)
        shop = self.world["shops"][0]
        self.assertEqual(shop["id"], merchant["direct_result"]["shop_id"])
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(shop["shopkeeper_id"], merchant["direct_result"]["target_id"])
        shopkeeper = next(
            npc for npc in self.world["npcs"] if npc["id"] == shop["shopkeeper_id"]
        )
        self.assertEqual(shopkeeper["location"], city_id)
        self.assertEqual(self.world["location"], city_id)
        self.assertEqual(scene, scene_before_discovery)
        model_chat.assert_not_called()

    def test_compound_city_observation_defers_scene_execution_to_plan_owner(self):
        text = "Şehirde dolanıyorum, etrafımda neler var gözlemliyorum."
        self.assertEqual(living_world.classify_scene_action(text), "look")
        self.assertEqual(interaction_adventure.hint(text), "plan")
        proposal = interaction_adventure.compound_plan(text)
        self.assertEqual(
            [step["quote"] for step in proposal["steps"]],
            ["Şehirde dolanıyorum", "etrafımda neler var gözlemliyorum."],
        )
        before = self.session.serialize_game_state()
        rng_before = self.session.rng.getstate()
        with patch("game.ollama.chat", side_effect=AssertionError("No model needed")):
            observation = self.session.plan_living_world_turn(text)
        self.assertIsNone(observation["direct_result"])
        self.assertEqual(observation["state_changes"], [])
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_v11_personal_profile_answers_remain_procedural_and_stable(self):
        npc = {
            "id": "npc_v11_profile",
            "name": "Derya",
            "role": "Yolcu",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }
        self.world["npcs"].append(npc)
        questions = (
            "Mesleğin nedir?",
            "Şu an ne yapıyorsun?",
            "Bugün ne yaptın?",
            "Keyfin nasıl?",
            "Nereden geliyorsun?",
            "Peki sen, kendinden biraz bahset.",
        )
        for question in questions:
            answer = local_dialogue.personal_answer(npc, question)
            self.assertIsNotNone(answer, question)
            text, category = answer
            self.assertIn("Derya", text)
            self.assertEqual(category, local_dialogue.PROCEDURAL_PERSONAL_FACT)
        activity_answer, _ = local_dialogue.personal_answer(npc, questions[1])
        self.assertTrue(activity_answer.split("“", 1)[1][0].isupper())
        self.assertEqual(
            local_dialogue.personal_answer(npc, questions[0]),
            local_dialogue.personal_answer(npc, questions[0]),
        )
        self.assertEqual(
            npc["reality_layer"], "PROCEDURAL_LOCAL_FICTION"
        )

    def test_v11_name_disclosure_is_bound_to_the_npc_who_heard_it(self):
        npc = {
            "id": "npc_v11_memory",
            "name": "Melis",
            "role": "Kent sakini",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "memory": [],
        }
        other_npc = {
            "id": "npc_v11_other",
            "name": "Duru",
            "role": "Muhafız",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "memory": [],
        }
        self.world["npcs"].extend([npc, other_npc])
        self.assertEqual(
            local_dialogue.explicit_player_name_disclosure(
                "Benim adım Arven; kendimi tanıtıyorum."
            ),
            "Arven",
        )
        game.record_npc_interaction(
            npc,
            "Melis, “Tanıştığımıza memnun oldum, Arven,” der.",
            "Benim adım Arven; kendimi tanıtıyorum.",
            npc,
        )
        self.assertEqual(
            game._historical_player_name_from_npc_memory(
                npc, "Adımı hatırlıyor musun?"
            ),
            "Arven",
        )
        self.assertIsNone(
            game._historical_player_name_from_npc_memory(
                other_npc, "Adımı hatırlıyor musun?"
            )
        )

    def test_v11_work_questions_do_not_create_or_imply_a_job_offer(self):
        npc = {
            "id": "npc_v11_work",
            "name": "Tuna",
            "role": "Tüccar",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }
        self.world["npcs"].append(npc)
        inquiry = local_dialogue.personal_answer(npc, "Bu civarda iş var mı?")
        acceptance = local_dialogue.personal_answer(
            npc, "İşe başlamaya hazırım."
        )
        self.assertIsNotNone(inquiry)
        self.assertIsNotNone(acceptance)
        self.assertIn("belirli bir iş yok", inquiry[0].casefold())
        self.assertNotIn("ara sıra gündelik işler", inquiry[0].casefold())
        self.assertIn("henüz sana belirli bir iş önermedim", acceptance[0].casefold())
        self.assertEqual(self.world["quests"], [])

    def test_v11_world_subject_question_is_not_routed_to_active_npc_identity(self):
        npc = {
            "id": "npc_v11_world_subject",
            "name": "Melis",
            "role": "Kent sakini",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }
        other_npc = {
            "id": "npc_v11_world_subject_other",
            "name": "Darian",
            "role": "Yolcu",
            "location": self.root_location,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }
        self.world["npcs"].extend([npc, other_npc])
        question = "Bu şehrin hükümdarı kim?"
        self.assertTrue(local_dialogue.is_world_subject_question(question))
        self.assertIsNone(
            local_dialogue.personal_question_kind(question)
        )
        self.assertIsNone(game._detect_query_type(question, npc))
        self.session.lore_authority_context = game._empty_lore_authority_context()
        with patch("game.ask_dungeon_master") as ask:
            targeted = self.session.run_player_turn(question, target_id=npc["id"])
            untargeted = self.session.run_player_turn(question)
        ask.assert_not_called()
        for result in (targeted, untargeted):
            self.assertEqual(result["action_result"]["status"], "unverified")
            self.assertNotIn("npc_id", result["action_result"])
            self.assertNotIn("Melis", result["narration"])
            self.assertNotIn("Darian", result["narration"])

    def test_v11_npc_identity_answer_uses_natural_name_only(self):
        response = game._handle_query(
            "Adın ne?",
            "npc_identity",
            {"name": "Orin", "role": "Barmen"},
        )
        self.assertEqual(
            response,
            "Orin, “Ben Orin. Barmen olarak buradayım.” diye yanıt verir.",
        )

    def test_v11_reentering_the_current_tavern_is_idempotent(self):
        search = self.session.plan_living_world_turn(
            "Yakınlarda bir taverna arıyorum."
        )
        tavern_id = search["direct_result"]["target_id"]
        self.world["flags"]["turn_index"] += 1
        enter = self.session.plan_living_world_turn(
            "Taverna içine giriyorum."
        )
        self.assertEqual(enter["direct_result"]["target_id"], tavern_id)
        self.assertIn(
            "Kapıdan içeri giriyorsun.",
            enter["direct_result"]["direct_response"],
        )
        self.assertEqual(self.world["location"], tavern_id)
        self.world["flags"]["turn_index"] += 1

        repeated = self.session.plan_living_world_turn("İçeri giriyorum.")
        self.assertEqual(repeated["direct_result"]["status"], "already_inside")
        self.assertIn(
            "Zaten içeridesin.",
            repeated["direct_result"]["direct_response"],
        )
        self.assertEqual(repeated["direct_result"]["target_id"], tavern_id)
        self.assertEqual(self.world["location"], tavern_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
