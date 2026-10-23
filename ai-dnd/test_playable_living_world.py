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
import exploration
import scheduled_events
import grounded_action
from api.serializers import serialize_session_state, serialize_combat_result
from api.campaign_journal import empty_campaign_journal, update_campaign_journal


class PlayableLivingWorldTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=1729)
        self.world = self.session.world_state
        self.world["location"] = "forest"
        self.root_location = self.world["location"]

    def _seed_local_shop(self):
        created = self.session.create_shop_from_proposal({
            "name": f"{game._turkish_genitive_form('Test Merchant')} Tezgâhı",
            "description": "Küçük ve sade bir yerel tezgâh.",
            "shopkeeper": {
                "name": "Test Merchant",
                "personality": "Sakin ve dikkatli.",
                "appearance": "Sade giysili bir dükkâncı.",
            },
        })
        self.assertIsNotNone(created)
        return created["shop"], created["shopkeeper"]

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

    def test_unknown_named_ablative_dialogue_rejects_single_npc_fallback(self):
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
                            npcs = self._set_npc_conversation_deadline(
                                turn_index, active=active,
                            )
                            self.world["npcs"] = npcs[:1]
                            self.assertEqual(self.session.active_npcs(), npcs[:1])
                            before = copy.deepcopy(self.world)

                            result = self.session.resolve_npc_reference(player_input)

                            self.assertEqual(result["status"], "none")
                            self.assertIsNone(result["npc"])
                            self.assertEqual(self.world, before)

    def test_elsewhere_named_ablative_dialogue_rejects_single_local_npc_fallback(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for name, target in (
                    ("Bora", "Bora'dan"),
                    ("Ece", "Ece'den"),
                    ("Murat", "Murat'tan"),
                    ("Mert", "Mert'ten"),
                    ("Bora", "Bora’dan"),
                ):
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
                            npcs = self._set_npc_conversation_deadline(
                                turn_index, active=active,
                            )
                            npcs[1].update({"name": name, "location": "village"})
                            self.assertNotEqual(
                                npcs[1]["location"], self.world["location"],
                            )
                            self.assertIn(npcs[1], self.world["npcs"])
                            self.assertEqual(self.session.active_npcs(), npcs[:1])
                            before = copy.deepcopy(self.world)

                            result = self.session.resolve_npc_reference(player_input)

                            self.assertEqual(result["status"], "none")
                            self.assertIsNone(result["npc"])
                            self.assertEqual(self.world, before)

    def test_explicit_local_name_resolves_with_another_npc_elsewhere(self):
        for turn_index in (12, 13):
            for active in (True, False):
                with self.subTest(
                    turn_index=turn_index, active_npc_present=active,
                ):
                    npcs = self._set_npc_conversation_deadline(
                        turn_index, active=active,
                    )
                    npcs[1]["location"] = "village"
                    self.assertNotEqual(npcs[1]["location"], self.world["location"])
                    self.assertIn(npcs[1], self.world["npcs"])
                    self.assertEqual(self.session.active_npcs(), npcs[:1])
                    expected = copy.deepcopy(self.world)
                    expected["flags"].update({
                        "active_npc_id": npcs[0]["id"],
                        "last_npc_id": npcs[0]["id"],
                        "active_npc_until_turn": turn_index + 6,
                    })

                    result = self.session.resolve_npc_reference(
                        "Aylin'den sohbet etmesini istiyorum.",
                    )

                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["npc"], npcs[0])
                    self.assertEqual(self.world, expected)

    def _set_hidden_scheduled_npc_conversation(
        self, turn_index, *, active, name, aftermath_visible=False,
    ):
        npcs = self._set_npc_conversation_deadline(turn_index, active=active)
        npcs[1].update({"name": name, "location": "village"})
        self.world["scheduled_events"] = []
        event = scheduled_events.register_event(
            self.world,
            event_id="hidden_npc_arrival",
            window_start=0,
            window_end=1,
            location_id=self.root_location,
            visibility="hidden",
            aftermath_visible=aftermath_visible,
            aftermath=f"{name} burada duruyor." if aftermath_visible else "",
            effects=[{
                "kind": "npc_location",
                "npc_id": npcs[1]["id"],
                "location_id": self.root_location,
            }],
        )
        scheduled_events.process_events(self.world, 0, 1)
        self.assertEqual(event["status"], "OCCURRED")
        self.assertFalse(event["player_observed"])
        self.assertEqual(event["visibility"], "hidden")
        self.assertEqual(event["canonical_result"]["effects_applied"], 1)
        self.assertEqual(self.world["npcs"], npcs)
        for npc in npcs:
            self.assertEqual(npc["location"], self.world["location"])
        self.assertEqual(scheduled_events.visible_npcs(self.world), npcs[:1])
        self.assertEqual(self.session.active_npcs(), npcs[:1])
        return npcs

    def test_hidden_scheduled_named_ablative_dialogue_rejects_single_local_npc_fallback(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for name, target in (
                    ("Bora", "Bora'dan"),
                    ("Ece", "Ece'den"),
                    ("Murat", "Murat'tan"),
                    ("Mert", "Mert'ten"),
                    ("Bora", "Bora’dan"),
                ):
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
                            npcs = self._set_hidden_scheduled_npc_conversation(
                                turn_index, active=active, name=name,
                            )
                            saved_state = self.session.serialize_game_state()
                            restored_session = game.create_session(seed=2718)
                            with tempfile.TemporaryDirectory() as directory:
                                save_path = Path(directory) / "unobserved-hidden-npc.json"
                                self.session.save_game(save_path)
                                restored_session.load_game(save_path)

                            self.assertEqual(
                                restored_session.serialize_game_state(), saved_state,
                            )
                            self.assertIsNot(restored_session.world_state, self.world)
                            self.assertEqual(restored_session.world_state, self.world)

                            for session in (self.session, restored_session):
                                with self.subTest(reopened=session is restored_session):
                                    before = copy.deepcopy(session.world_state)
                                    event = session.world_state["scheduled_events"][0]
                                    self.assertEqual(event["status"], "OCCURRED")
                                    self.assertEqual(event["visibility"], "hidden")
                                    self.assertFalse(event["player_observed"])
                                    self.assertEqual(event["player_known_summary"], "")
                                    self.assertEqual(session.active_npcs(), npcs[:1])
                                    self.assertNotIn(npcs[1], session.active_npcs())

                                    result = session.resolve_npc_reference(player_input)

                                    self.assertEqual(result["status"], "none")
                                    self.assertIsNone(result["npc"])
                                    self.assertEqual(session.world_state, before)

    def test_explicit_visible_local_name_resolves_with_hidden_scheduled_npc(self):
        for turn_index in (12, 13):
            for active in (True, False):
                with self.subTest(
                    turn_index=turn_index, active_npc_present=active,
                ):
                    npcs = self._set_hidden_scheduled_npc_conversation(
                        turn_index, active=active, name="Bora",
                    )
                    expected = copy.deepcopy(self.world)
                    expected["flags"].update({
                        "active_npc_id": npcs[0]["id"],
                        "last_npc_id": npcs[0]["id"],
                        "active_npc_until_turn": turn_index + 6,
                    })

                    result = self.session.resolve_npc_reference(
                        "Aylin'den sohbet etmesini istiyorum.",
                    )

                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["npc"], npcs[0])
                    self.assertEqual(self.world, expected)

    def test_explicit_newly_observed_hidden_npc_name_resolves_after_reopening_at_and_after_deadline(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for player_input in (
                    "Bora'yla konuşuyorum.",
                    "Bora'ya selam veriyorum.",
                    "Bora'dan sohbet etmesini istiyorum.",
                ):
                    with self.subTest(
                        turn_index=turn_index, active_npc_present=active,
                        player_input=player_input,
                    ):
                        npcs = self._set_hidden_scheduled_npc_conversation(
                            turn_index, active=active, name="Bora",
                            aftermath_visible=True,
                        )
                        event = self.world["scheduled_events"][0]
                        canonical_result = copy.deepcopy(event["canonical_result"])

                        observed = scheduled_events.process_events(
                            self.world, 1, 2,
                            observation={
                                "kind": "look",
                                "location_id": self.root_location,
                            },
                        )

                        self.assertTrue(event["player_observed"])
                        self.assertEqual(len(observed), 1)
                        self.assertEqual(observed[0]["summary"], event["aftermath"])
                        self.assertEqual(event["player_known_summary"], event["aftermath"])
                        self.assertEqual(event["visibility"], "hidden")
                        self.assertEqual(event["status"], "OCCURRED")
                        self.assertEqual(event["canonical_result"], canonical_result)
                        self.assertEqual(self.session.active_npcs(), npcs)
                        self.assertIn(npcs[1], self.session.active_npcs())

                        saved_state = self.session.serialize_game_state()
                        restored_session = game.create_session(seed=2718)
                        with tempfile.TemporaryDirectory() as directory:
                            save_path = Path(directory) / "observed-hidden-npc.json"
                            self.session.save_game(save_path)
                            restored_session.load_game(save_path)

                        self.assertEqual(
                            restored_session.serialize_game_state(), saved_state,
                        )
                        restored_world = restored_session.world_state
                        self.assertIsNot(restored_world, self.world)
                        self.assertEqual(restored_world, self.world)
                        restored_event = restored_world["scheduled_events"][0]
                        self.assertTrue(restored_event["player_observed"])
                        self.assertEqual(restored_event, event)
                        self.assertEqual(restored_session.active_npcs(), npcs)
                        self.assertIn(npcs[1], restored_session.active_npcs())
                        expected = copy.deepcopy(self.world)
                        expected["flags"].update({
                            "active_npc_id": npcs[1]["id"],
                            "last_npc_id": npcs[1]["id"],
                            "active_npc_until_turn": turn_index + 6,
                        })

                        for session in (self.session, restored_session):
                            with self.subTest(reopened=session is restored_session):
                                result = session.resolve_npc_reference(player_input)

                                self.assertEqual(result["status"], "found")
                                self.assertEqual(result["npc"], npcs[1])
                                self.assertEqual(session.world_state, expected)

    def test_pronoun_only_dialogue_preserves_single_npc_fallback(self):
        for turn_index in (12, 13):
            for active in (True, False):
                for player_input in (
                    "Onunla konuşuyorum.",
                    "Ondan sohbet etmesini istiyorum.",
                ):
                    with self.subTest(
                        turn_index=turn_index, active_npc_present=active,
                        player_input=player_input,
                    ):
                        npcs = self._set_npc_conversation_deadline(
                            turn_index, active=active,
                        )
                        self.world["npcs"] = npcs[:1]
                        self.assertEqual(self.session.active_npcs(), npcs[:1])
                        expected = copy.deepcopy(self.world)
                        expected["flags"].update({
                            "active_npc_id": npcs[0]["id"],
                            "last_npc_id": npcs[0]["id"],
                            "active_npc_until_turn": turn_index + 6,
                        })

                        result = self.session.resolve_npc_reference(player_input)

                        self.assertEqual(result["status"], "found")
                        self.assertEqual(result["npc"]["id"], npcs[0]["id"])
                        self.assertEqual(self.world, expected)

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
            "Duru, “Yolların ne durumda olduğunu bilemem; kesin bir şey "
            "söylersem seni yanıltırım,” diye yanıt verir.",
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

    def test_merchant_search_finds_existing_local_person_and_shop_without_trade(self):
        shop, merchant = self._seed_local_shop()
        inventory_before = copy.deepcopy(self.world["inventory"])
        shops_before = copy.deepcopy(self.world["shops"])
        merchant_before = copy.deepcopy(merchant)
        plan = self.session.plan_living_world_turn(
            "Bir tüccar arıyorum."
        )
        self.assertEqual(plan["direct_result"]["action"], "local_search")
        self.assertEqual(plan["direct_result"]["status"], "found")
        self.assertEqual(plan["direct_result"]["shop_id"], shop["id"])
        self.assertEqual(plan["direct_result"]["target_id"], merchant["id"])
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
        self.assertEqual(self.world["inventory"], inventory_before)
        self.assertEqual(self.world["shops"], shops_before)
        self.assertEqual(merchant, merchant_before)

        negative = self.session.plan_living_world_turn(
            "Bir tüccar aramıyorum."
        )
        self.assertIsNone(negative["direct_result"])
        self.assertEqual(self.world["shops"], shops_before)

    def test_addressed_npc_tavern_question_does_not_create_a_world_search_result(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Muhafız",
            "location": self.root_location,
        })
        before_locations = copy.deepcopy(self.world["locations"])

        plan = self.session.plan_living_world_turn(
            "buralarda bir taverna varmı diye muhafıza soruyorum"
        )

        self.assertIsNone(plan["direct_result"])
        self.assertEqual(plan["npc_target_id"], npc["id"])
        self.assertEqual(self.world["locations"], before_locations)

    def test_addressed_npc_tavern_question_is_bounded_dialogue_without_model_or_discovery(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Muhafız",
            "location": self.root_location,
        })
        before_locations = copy.deepcopy(self.world["locations"])

        with patch("game.ollama.chat", side_effect=AssertionError("Local NPC venue answer must be deterministic")):
            result = self.session.run_player_turn(
                "buralarda bir taverna varmı diye muhafıza soruyorum"
            )

        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0
        )
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["npc_id"], npc["id"])
        self.assertNotIn("Cael", result["narration"])
        self.assertIn("muhafız", result["narration"].casefold())
        self.assertNotIn("buluyorsun", result["narration"])
        self.assertEqual(self.world["locations"], before_locations)

    def test_new_npc_name_is_hidden_until_identity_is_learned(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Muhafız",
            "location": self.root_location,
            "appearance": "Kapı yakınında nöbet tutan, düzenli giyimli.",
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True

        projected = living_world.public_scene_projection(self.world, 0)
        self.assertFalse(npc.get("name_known_to_player", True))
        self.assertNotEqual(projected["npcs"][0]["name"], "Cael")
        self.assertNotIn("Cael", json.dumps(projected, ensure_ascii=False))

        with patch("game.ollama.chat", side_effect=AssertionError("Identity lookup must be deterministic")):
            result = self.session.run_player_turn("Muhafıza adını soruyorum.")

        self.assertTrue(npc["name_known_to_player"])
        self.assertIn("Cael", result["narration"])
        projected_after = living_world.public_scene_projection(self.world, 1)
        self.assertEqual(projected_after["npcs"][0]["name"], "Cael")

    def test_legacy_npcs_without_epistemic_fields_remain_known(self):
        legacy = {"id": "legacy", "name": "OldName", "role": "Traveler"}
        self.assertTrue(living_world.npc_name_known_to_player(legacy))
        self.assertTrue(living_world.npc_role_known_to_player(legacy))
        self.assertEqual(living_world.public_npc_name(legacy), "OldName")
        self.assertEqual(living_world.public_npc_role(legacy), "yolcu")
        self.assertEqual(legacy["role"], "Traveler")

    def test_obvious_role_can_be_visible_without_revealing_name(self):
        guard = self.session.create_npc_from_ai({
            "name": "Cael", "role": "Muhafız", "location": self.root_location,
        })
        traveler = self.session.create_npc_from_ai({
            "name": "Liora", "role": "Yolcu", "location": self.root_location,
        })
        self.assertFalse(guard["name_known_to_player"])
        self.assertTrue(guard["role_known_to_player"])
        self.assertEqual(living_world.public_npc_name(guard), "Bir muhafız")
        self.assertFalse(traveler["name_known_to_player"])
        self.assertFalse(traveler["role_known_to_player"])
        self.assertNotIn("Liora", living_world.public_npc_name(traveler))
        self.assertIsNone(living_world.public_npc_role(traveler))

    def test_npc_identity_knowledge_is_session_isolated(self):
        peer = game.create_session(seed=1731)
        peer.world_state["location"] = self.root_location
        first = self.session.create_npc_from_ai({
            "name": "Cael", "role": "Muhafız", "location": self.root_location,
        })
        second = peer.create_npc_from_ai({
            "name": "Cael", "role": "Muhafız", "location": self.root_location,
        })
        first["name_known_to_player"] = True
        self.assertTrue(first["name_known_to_player"])
        self.assertFalse(second["name_known_to_player"])
        self.assertEqual(living_world.public_npc_name(first), "Cael")
        self.assertNotEqual(living_world.public_npc_name(second), "Cael")

    def test_hidden_identity_is_absent_from_public_state_and_model_context(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora",
            "role": "Yolcu",
            "location": self.root_location,
            "appearance": "Mavi pelerinli, kapı yanında bekleyen.",
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True

        public_state = serialize_session_state(self.session)
        world_context = game.build_world_context(npc, session=self.session)
        prompt_context = json.loads(
            self.session._living_world_prompt_context(npc_target=npc)
        )
        interaction_context = interaction_adventure.context(self.world, npc)
        for projection in (public_state, world_context, prompt_context, interaction_context):
            encoded = json.dumps(projection, ensure_ascii=False)
            self.assertNotIn("Liora", encoded)
            self.assertNotIn("Yolcu", encoded)

        self.assertEqual(public_state["npcs"][0]["role"], "")
        self.assertNotEqual(public_state["npcs"][0]["name"], "Liora")

    def test_hidden_identity_stays_out_of_full_model_prompts_and_fallbacks(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora", "role": "Yolcu", "location": self.root_location,
        })
        with patch("game.ollama.chat", return_value={"message": {"content": "{}"}}) as model:
            self.session.parse_player_intent("Dikkatle bakıyorum.")
            game.ask_dungeon_master([], "Bugün nasıl gidiyor?", npc_target=npc,
                                    return_details=True, session=self.session)
        self.assertEqual(model.call_count, 2)
        for call in model.call_args_list:
            prompt = json.dumps(call.kwargs["messages"], ensure_ascii=False)
            self.assertNotIn("Liora", prompt)
            self.assertNotIn("Yolcu", prompt)
        for text in ("Merhaba", "Adımı biliyor musun?", "Burası nasıl bir yer?"):
            with self.subTest(text=text):
                fallback = self.session._fallback_narration(text, npc_target=npc)
                self.assertNotIn("Liora", fallback)
                self.assertNotIn("Yolcu", fallback)
        direct = self.session._direct_npc_smalltalk_response("Burası nasıl bir yer?", npc)
        self.assertNotIn("Yolcu", direct)
        self.assertFalse(npc["name_known_to_player"])

    def test_rejected_hidden_identity_narration_does_not_retry_or_reveal(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora", "role": "Yolcu", "location": self.root_location,
        })
        with patch("game.ollama.chat", side_effect=AssertionError("No retry")):
            decision = self.session._narration_safety_decision(
                "Liora sana selam verir.", "Merhaba", npc_target=npc)
            self.assertTrue(decision["unsafe"])
            self.assertEqual(decision["reason_code"], "HIDDEN_NPC_IDENTITY_DISCLOSURE")
            narration = game.finalize_narration(
                "Liora sana selam verir.", "Merhaba", npc_target=npc, session=self.session)
        self.assertNotIn("Liora", narration)
        self.assertFalse(npc["name_known_to_player"])

    def test_nested_combat_receipt_hides_actor_id_identity_without_mutation(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora", "role": "Yolcu", "location": self.root_location,
        })
        from api.serializers import _sanitize_combat_names
        receipt = {"economy_steps": [{"enemy_actions": [
            {"actor_id": npc["id"], "actor_name": "Liora", "target_id": "player"}
        ]}]}
        projected = _sanitize_combat_names(copy.deepcopy(receipt), self.world)
        self.assertNotIn("Liora", json.dumps(projected))
        self.assertIn("Liora", json.dumps(receipt))
        self.assertEqual(npc["name"], "Liora")

    def test_personal_question_does_not_reveal_unlearned_npc_name(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora", "role": "Yolcu", "location": self.root_location,
        })
        with patch("game.ollama.chat", side_effect=AssertionError("Personal answer is deterministic")):
            result = self.session.run_player_turn("Bugün nasılsın?", target_id=npc["id"])
        self.assertNotIn("Liora", result["narration"])
        self.assertFalse(npc["name_known_to_player"])
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)

    def test_hidden_canonical_name_cannot_target_npc_until_learned(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Muhafız",
            "location": self.root_location,
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True

        self.assertEqual(
            self.session.resolve_npc_reference("Cael ile konuşuyorum")["status"],
            "none",
        )
        by_role = self.session.resolve_npc_reference("Muhafız ile konuşuyorum")
        self.assertEqual(by_role["status"], "found")
        self.assertEqual(by_role["npc"]["id"], npc["id"])

        with patch("game.ollama.chat", side_effect=AssertionError("Identity lookup must be deterministic")):
            result = self.session.run_player_turn("Muhafıza adını soruyorum.")
        self.assertIn("Cael", result["narration"])
        self.assertEqual(
            self.session.resolve_npc_reference("Cael ile konuşuyorum")["status"],
            "found",
        )

    def test_learned_npc_identity_survives_save_load(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Muhafız",
            "location": self.root_location,
        })
        living_world.ensure_scene_record(self.world, self.root_location, 0)["materialized"] = True
        with patch("game.ollama.chat", side_effect=AssertionError("Identity lookup must be deterministic")):
            self.session.run_player_turn("Muhafıza adını soruyorum.")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            self.session.save_game(path)
            reopened = game.create_session(seed=1730)
            reopened.load_game(path)

        restored = next(
            item for item in reopened.world_state["npcs"]
            if item.get("id") == npc["id"]
        )
        self.assertTrue(restored["name_known_to_player"])
        self.assertTrue(restored["role_known_to_player"])
        public_state = serialize_session_state(reopened)
        self.assertIn("Cael", json.dumps(public_state, ensure_ascii=False))

    def test_campaign_journal_does_not_promote_unknown_identity(self):
        before = self.session.serialize_game_state()
        npc = self.session.create_npc_from_ai({
            "name": "Liora",
            "role": "Yolcu",
            "location": self.root_location,
        })
        unknown = self.session.serialize_game_state()
        journal = update_campaign_journal(
            empty_campaign_journal(),
            before,
            unknown,
            {"action": "query", "query_type": "presence", "success": True},
            None,
            presence_location_id=self.root_location,
        )
        self.assertEqual(len(journal["known_npcs"]), 1)
        self.assertNotEqual(journal["known_npcs"][0]["name"], "Liora")
        self.assertNotEqual(journal["known_npcs"][0].get("role"), "Yolcu")

        before_learning = self.session.serialize_game_state()
        npc["name_known_to_player"] = True
        npc["role_known_to_player"] = True
        after_learning = self.session.serialize_game_state()
        journal = update_campaign_journal(
            journal,
            before_learning,
            after_learning,
            {
                "action": "query",
                "query_type": "npc_identity",
                "npc_id": npc["id"],
                "success": True,
            },
            None,
        )
        self.assertEqual(len(journal["known_npcs"]), 1)
        self.assertEqual(journal["known_npcs"][0]["name"], "Liora")
        self.assertEqual(journal["known_npcs"][0]["role"], "Yolcu")

    def test_hidden_identity_is_sanitized_in_combat_api_projection(self):
        npc = self.session.create_npc_from_ai({
            "name": "Liora",
            "role": "Yolcu",
            "location": self.root_location,
        })
        npc["distance_ft"] = 5
        with (
            patch("game.roll_initiative_player", return_value=20),
            patch("game.roll_initiative_npc", return_value=1),
            patch("game.roll_attack", return_value=10),
            patch("game.roll_damage", return_value=2),
        ):
            result = self.session.execute_intent(
                {"intent": "attack"},
                "ona sald\u0131r\u0131yorum",
                npc_target=npc,
                target_id=npc["id"],
            )

        public_result = serialize_combat_result(result, self.session)
        public_state = serialize_session_state(self.session)
        narration = self.session._combat_narration(result)
        self.assertNotIn("Liora", narration)
        self.assertNotIn("Liora", json.dumps(public_result, ensure_ascii=False))
        self.assertNotIn("Liora", json.dumps(public_state["combat"], ensure_ascii=False))
        self.assertNotEqual(public_result.get("target_name"), "Liora")
        npc_record = next(
            record for record in public_state["combat"]["participant_records"]
            if record["id"] == npc["id"]
        )
        self.assertNotEqual(npc_record["name"], "Liora")

    def test_guessed_hidden_name_cannot_select_attack_target(self):
        npc = self.session.create_npc_from_ai({
            "name": "Cael",
            "role": "Yolcu",
            "location": self.root_location,
        })
        npc["distance_ft"] = 5
        living_world.ensure_scene_record(self.world, self.root_location, 0)["materialized"] = True
        before_hp = npc["current_hp"]

        with patch("game.ollama.chat", side_effect=AssertionError("Explicit attack must not need a model")):
            result = self.session.run_player_turn("Cael'e sald\u0131r\u0131yorum")

        action = result["action_result"]
        self.assertEqual(action["action"], "attack")
        self.assertFalse(action["success"])
        self.assertEqual(action["status"], "clarification")
        self.assertEqual(action["outcome"], "missing_target")
        self.assertEqual(npc["current_hp"], before_hp)
        self.assertFalse(self.world["combat"]["active"])
        self.assertNotIn("Cael", result["narration"])
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0
        )

    def test_explicit_conversation_start_is_stable_and_model_free(self):
        npc = self.session.create_npc_from_ai({
            "name": "Marek",
            "role": "Kent sakini",
            "location": self.root_location,
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True
        npc["name_known_to_player"] = True

        with patch("game.ollama.chat", side_effect=AssertionError("Conversation start must not need a model")):
            first = self.session.run_player_turn("Marek ile konuşmak istiyorum.")
            second = self.session.run_player_turn("Marek ile konuşmak istiyorum.")

        for result in (first, second):
            self.assertEqual(result["action_result"]["action"], "dialogue")
            self.assertEqual(result["action_result"]["status"], "conversation_started")
            self.assertEqual(result["action_result"]["npc_id"], npc["id"])
            self.assertEqual(
                result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0
            )
        # The first opening is the plain line; a repeat varies instead of echoing it.
        self.assertIn("Seni dinliyorum", first["narration"])
        self.assertIn(
            second["narration"],
            [line.format(name="Marek") for line in game._CONVERSATION_OPENINGS],
        )
        self.assertNotEqual(first["narration"], second["narration"])
        self.assertEqual(self.world["flags"]["active_npc_id"], npc["id"])

    def test_local_place_question_to_orin_uses_current_scene_not_verification_fallback(self):
        self.world["location"] = "tavern"
        npc = self.session.create_npc_from_ai({
            "name": "Orin",
            "role": "Barmen",
            "location": "tavern",
        })
        scene = living_world.ensure_scene_record(self.world, "tavern", 0)
        scene["materialized"] = True

        with patch("game.ollama.chat", side_effect=AssertionError("Bounded local scene answer must not need a model")):
            result = self.session.run_player_turn(
                "buralarde yeniyim nasıl bir yer burası diye barmene soruyorum"
            )

        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["npc_id"], npc["id"])
        self.assertIn("Burası Taverna", result["narration"])
        self.assertNotIn("kendi gözlerimle görmedim", result["narration"])
        self.assertNotIn("doğrulanmış", result["narration"])
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0
        )

    def test_approach_bartender_phrase_routes_to_existing_scene_action(self):
        npc = self.session.create_npc_from_ai({
            "name": "Orin",
            "role": "Barmen",
            "location": self.root_location,
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True

        plan = self.session.plan_living_world_turn(
            "Barmen ile konuşmaya için yakınına gidiyorum"
        )

        self.assertEqual(plan["direct_result"]["action"], "approach")
        self.assertEqual(plan["direct_result"]["status"], "completed")
        self.assertEqual(plan["direct_result"]["target_id"], npc["id"])
        self.assertEqual(plan["npc_target_id"], npc["id"])
        self.assertEqual(npc["distance_ft"], 5)

    def test_explicit_attack_after_approach_uses_existing_combat_owner(self):
        npc = self.session.create_npc_from_ai({
            "name": "Orin",
            "role": "Barmen",
            "location": self.root_location,
        })
        scene = living_world.ensure_scene_record(self.world, self.root_location, 0)
        scene["materialized"] = True
        self.session.plan_living_world_turn(
            "Barmen ile konu\u015fmaya i\u00e7in yak\u0131n\u0131na gidiyorum"
        )

        with (
            patch("game.ollama.chat", side_effect=AssertionError("Explicit attack must not need a model")),
            patch("game.roll_initiative_player", return_value=20),
            patch("game.roll_initiative_npc", return_value=1),
            patch("game.roll_attack", return_value=10),
            patch("game.roll_damage", return_value=2),
        ):
            result = self.session.run_player_turn("barmene sald\u0131r\u0131yorum")

        self.assertEqual(result["action_result"]["action"], "attack")
        self.assertEqual(result["action_result"]["target_id"], npc["id"])
        self.assertTrue(result["action_result"]["combat_started"])
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0
        )
        self.assertNotIn("do\u011frulanm\u0131\u015f", result["narration"])
        self.assertNotIn("kabul etmedi", result["narration"])

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
        self.assertIn("kapalı ve kilitli", search["direct_result"]["direct_response"])
        self.world["flags"]["turn_index"] += 1

        blocked = self.session.plan_living_world_turn("Enter the tavern.")
        self.assertEqual(blocked["direct_result"]["status"], "blocked")
        self.assertEqual(self.world["location"], self.root_location)
        door = next(
            item for item in self.world["doors"]
            if item.get("id") == f"venue-door:{tavern_id}"
        )
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        door["locked"] = False
        door["open"] = True
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

    def test_discovered_venue_entry_is_not_generic_travel(self):
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            search = self.session.run_player_turn(
                "Yakınlarda oturup bir şeyler içebileceğim bir yer var mı?"
            )
        search_action = search["action_result"]
        self.assertEqual(search_action["action"], "local_search")
        self.assertEqual(search_action["status"], "found")
        tavern_id = search_action["target_id"]
        tavern = self.world["locations"][tavern_id]
        self.assertEqual(tavern["parent_location_id"], self.root_location)
        self.assertEqual(self.world["location"], self.root_location)
        phrase = f"{tavern['name']} içine giriyorum."
        door = next(
            item for item in self.world["doors"]
            if item.get("id") == f"venue-door:{tavern_id}"
        )
        door["locked"] = False
        door["open"] = True

        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            entered = self.session.run_player_turn(phrase)

        action = entered["action_result"]
        self.assertEqual(action["action"], "enter")
        self.assertNotEqual(action["action"], "travel")
        self.assertEqual(action["status"], "completed")
        self.assertEqual(action["target_id"], tavern_id)
        self.assertEqual(self.world["location"], tavern_id)
        self.assertEqual(
            entered["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )

    def test_exact_venue_door_break_is_not_a_tavern_search(self):
        phrase = "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum."
        self.assertFalse(living_world.is_tavern_search(phrase))
        self.assertFalse(living_world.is_local_venue_search(phrase))
        self.assertTrue(
            living_world.is_tavern_search("Yakınlarda bir taverna arıyorum.")
        )
        self.assertTrue(
            living_world.is_tavern_search("Yakınlarda oturup dinlenecek bir han arıyorum.")
        )
        self.assertFalse(living_world.is_tavern_search("Kael Hanı kapısı kırıldı."))
        self.assertFalse(living_world.is_tavern_search("Han kapısını kırmalı mıyım?"))
        self.assertFalse(living_world.is_tavern_search("Kael Hanı kapısını gözlemliyorum."))
        self.assertEqual(living_world.classify_scene_action("Etrafıma bakıyorum."), "look")
        self.assertNotEqual(
            living_world.classify_scene_action(
                "Şehirde oturup sıcak yemek yiyebileceğim bir han var mı?"
            ),
            "sit",
        )
        self.assertEqual(
            living_world.classify_scene_action(
                "Sandalyeye oturup muhafızı dinliyorum."
            ),
            "sit",
        )

    def test_building_inspection_of_known_tavern_does_not_start_a_new_search(self):
        sentence = "hanın olduğu binayı araştırıyorum açık pencere varmı bakıyorum"
        self.assertFalse(living_world.is_tavern_search(sentence))
        self.assertTrue(living_world.is_anchored_structure_inquiry(sentence))
        self.assertTrue(living_world.is_tavern_search("Yakınlarda bir taverna arıyorum."))
        self.assertTrue(
            living_world.is_tavern_search("Yakınlarda oturup dinlenecek bir han arıyorum.")
        )
        self.assertTrue(living_world.is_tavern_search("Yakınlarda han binası var mı?"))
        self.assertFalse(living_world.is_tavern_search("Han binasını araştırmıyorum."))
        self.assertFalse(
            living_world.is_tavern_search(
                "Muhafıza, 'hanın olduğu binayı araştırıyorum' diyorum."
            )
        )
        self.assertFalse(living_world.is_tavern_search("Şu sandığı araştırıyorum."))
        self.assertFalse(living_world.is_tavern_search("Yakınlarda bir kütüphane arıyorum."))
        self.assertTrue(
            living_world.is_anchored_structure_inquiry(
                "Hanın bulunduğu binayı gözden geçiriyorum."
            )
        )
        self.assertTrue(
            living_world.is_anchored_structure_inquiry(
                "I look at the building the inn is in."
            )
        )
        self.assertTrue(
            living_world.is_anchored_structure_inquiry("Han binasında açık bir yer var mı?")
        )
        self.assertFalse(
            living_world.is_anchored_structure_inquiry(
                "Muhafıza, 'hanın olduğu binayı araştırıyorum' diyorum."
            )
        )

        before_ids = set(self.world["locations"])
        before_inventory = copy.deepcopy(self.world["inventory"])
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            missing = self.session.run_player_turn(sentence)
        self.assertEqual(set(self.world["locations"]), before_ids)
        self.assertEqual(self.world["location"], self.root_location)
        self.assertEqual(self.world["inventory"], before_inventory)
        self.assertNotEqual(missing["action_result"]["action"], "local_search")
        self.assertNotIn("pencere yok", missing["narration"].casefold())
        self.assertNotIn("açık pencere", missing["narration"].casefold())

        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            search = self.session.run_player_turn("Yakınlarda bir taverna arıyorum.")
        self.assertEqual(search["action_result"]["action"], "local_search")
        tavern_id = search["action_result"]["target_id"]
        door = next(
            item for item in self.world["doors"]
            if item.get("id") == f"venue-door:{tavern_id}"
        )
        before_door = {
            key: door.get(key) for key in ("open", "locked", "broken")
        }
        location_ids = set(self.world["locations"])
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            looked = self.session.run_player_turn(sentence)
        action = looked["action_result"]
        self.assertEqual(action["action"], "inspect")
        self.assertEqual(action["status"], "not_detailed")
        self.assertEqual(action["target_id"], tavern_id)
        self.assertEqual(
            looked["narration"],
            f"{self.world['locations'][tavern_id]['name']} binasına bakıyorsun. "
            "Sokağa açılan kapısı kapalı ve kilitli. "
            "Bu bakışın seçtiği diğer parça henüz ayrıntılandırılmamış.",
        )
        self.assertEqual(set(self.world["locations"]), location_ids)
        self.assertEqual(self.world["location"], self.root_location)
        self.assertEqual(
            {key: door.get(key) for key in ("open", "locked", "broken")},
            before_door,
        )
        self.assertEqual(self.world["inventory"], before_inventory)
        self.assertEqual(
            looked["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )

        self.world["features"].append({
            "id": "feature_sign",
            "location": self.root_location,
            "name": "Tabela",
            "description": "Soluk bir tabela.",
            "aliases": ["tabela"],
            "hidden": False,
        })
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            sign = self.session.run_player_turn(
                "hanın olduğu binadaki tabelayı inceliyorum."
            )
        self.assertEqual(sign["action_result"]["target_id"], "feature_sign")
        self.assertEqual(sign["narration"], "Tabela: Soluk bir tabela.")
        self.assertEqual(set(self.world["locations"]), location_ids)
        self.assertEqual(
            {key: door.get(key) for key in ("open", "locked", "broken")},
            before_door,
        )

        self.world["features"].append({
            "id": "feature_hidden_latch",
            "location": self.root_location,
            "name": "Gizli sürgü",
            "description": "Gizli sürgü içeri açılıyor.",
            "aliases": ["sürgü", "surgu"],
            "hidden": True,
        })
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            hidden = self.session.run_player_turn(
                "hanın olduğu binadaki sürgüye bakıyorum."
            )
        self.assertEqual(hidden["action_result"]["status"], "not_visible")
        self.assertNotIn("içeri açılıyor", hidden["narration"].casefold())
        self.assertNotIn("gizli sürgü", hidden["narration"].casefold())
        self.assertEqual(self.world["location"], self.root_location)
        self.assertEqual(
            {key: door.get(key) for key in ("open", "locked", "broken")},
            before_door,
        )

    def test_dynamic_venue_door_action_requires_current_affirmative_named_intent(self):
        self.world["location"] = "fr:city:neverwinter"
        door = {
            "id": "venue-door:location_001",
            "name": "Kael Hanı Kapısı",
            "location": "fr:city:neverwinter",
            "open": False,
            "locked": True,
            "broken": False,
        }
        self.world["doors"] = [door]
        exact = "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum."
        self.assertTrue(exploration.native_request(exact, self.session))
        self.assertEqual(
            exploration._natural_venue_door_action(self.session, exact),
            ("venue-door:location_001", "break"),
        )
        for non_action in (
            "Kael Hanı kapısını kırmalı mıyım?",
            "Kael Hanı kapısını kırmak istemiyorum.",
            "Dün Kael Hanı kapısını kırmaya çalıştım.",
            "Kael Hanı kapısını gözlemliyorum.",
        ):
            with self.subTest(message=non_action):
                self.assertIsNone(
                    exploration._natural_venue_door_action(self.session, non_action)
                )

    def test_compound_move_and_knock_follow_the_actual_building_result(self):
        self.world["location"] = "neverwinter"
        self.world["locations"]["neverwinter"] = {
            "id": "neverwinter", "name": "Neverwinter", "type": "city",
        }
        for identity, name in (("inn_ash", "Kuzgun Hanı"), ("inn_blue", "Mavi Fener")):
            self.world["locations"][identity] = {
                "id": identity, "name": name,
                "parent_location_id": "neverwinter",
                "scene_kind": "tavern", "type": "inn",
            }
        self.world["doors"] = [
            {
                "id": f"venue-door:{identity}",
                "name": f"{name} Kapısı",
                "location": "neverwinter",
                "open": False, "locked": False, "broken": False,
            }
            for identity, name in (("inn_ash", "Kuzgun Hanı"), ("inn_blue", "Mavi Fener"))
        ]
        grounded_action.note_near(self.world, "venue-door:inn_ash")

        result = grounded_action.resolve_turn(
            self.session,
            "Mavi Fener'e gidiyorum ve kapısını çalıyorum.",
            allow_model=False,
        )

        self.assertEqual(result["action_result"]["status"], "completed")
        steps = result["action_result"]["steps"]
        self.assertEqual(steps[0]["target_id"], "inn_blue")
        self.assertEqual(steps[1]["target_id"], "venue-door:inn_blue")
        self.assertEqual(steps[1]["target_name"], "Mavi Fener Kapısı")

    def test_compound_move_preserves_explicit_smithy_door_target(self):
        self.world["location"] = "neverwinter"
        self.world["locations"]["neverwinter"] = {
            "id": "neverwinter", "name": "Neverwinter", "type": "city",
        }
        for identity, name, scene_kind, kind in (
            ("inn_ash", "Kuzgun Hanı", "tavern", "inn"),
            ("inn_blue", "Mavi Fener", "tavern", "inn"),
            ("smithy", "Ali'nin Demirhanesi", "smithy", "smithy"),
        ):
            self.world["locations"][identity] = {
                "id": identity, "name": name,
                "parent_location_id": "neverwinter",
                "scene_kind": scene_kind, "type": kind,
            }
        self.world["doors"] = [
            {
                "id": f"venue-door:{identity}",
                "name": "Atölye Kapısı" if identity == "smithy" else f"{name} Kapısı",
                "location": "neverwinter",
                "open": False, "locked": False, "broken": False,
            }
            for identity, name in (
                ("inn_ash", "Kuzgun Hanı"),
                ("inn_blue", "Mavi Fener"),
                ("smithy", "Atölye"),
            )
        ]
        grounded_action.note_near(self.world, "venue-door:inn_ash")

        result = grounded_action.resolve_turn(
            self.session,
            "Mavi Fener'e gidip demirhanenin kapısını açıyorum.",
            allow_model=False,
        )

        self.assertEqual(result["action_result"]["status"], "completed")
        steps = result["action_result"]["steps"]
        self.assertEqual(steps[0]["target_id"], "inn_blue")
        self.assertEqual(steps[1]["target_id"], "venue-door:smithy")
        self.assertNotIn("venue-door:inn_ash|0:0", self.world[grounded_action.KEY]["answers"])

    def test_named_smithy_door_wins_over_separate_workshop_kind(self):
        self.world["location"] = "neverwinter"
        self.world["locations"]["neverwinter"] = {
            "id": "neverwinter", "name": "Neverwinter", "type": "city",
        }
        for identity, name, scene_kind, kind in (
            ("inn_blue", "Mavi Fener", "tavern", "inn"),
            ("smithy", "Arin'in Demirhanesi", "smithy", "smithy"),
            ("workshop", "Lina'nın Atölyesi", "workshop", "workshop"),
        ):
            self.world["locations"][identity] = {
                "id": identity, "name": name,
                "parent_location_id": "neverwinter",
                "scene_kind": scene_kind, "type": kind,
            }
        self.world["doors"] = [
            {
                "id": f"venue-door:{identity}",
                "name": name,
                "location": "neverwinter",
                "open": False, "locked": False, "broken": False,
            }
            for identity, name in (
                ("inn_blue", "Mavi Fener Kapısı"),
                ("smithy", "Atölye Kapısı"),
                ("workshop", "Lina'nın Atölyesi Kapısı"),
            )
        ]

        result = grounded_action.resolve_turn(
            self.session,
            "Mavi Fener’e gidip Atölye Kapısını açıyorum.",
            allow_model=False,
        )

        self.assertEqual(result["action_result"]["status"], "completed")
        steps = result["action_result"]["steps"]
        self.assertEqual(steps[0]["target_id"], "inn_blue")
        self.assertEqual(steps[1]["target_id"], "venue-door:smithy")

    def test_guard_smalltalk_does_not_recommend_locked_known_tavern_as_unblocked(self):
        self.world["location"] = "fr:city:neverwinter"
        self.world["locations"]["location_001"] = {
            "id": "location_001",
            "name": "Kael Hanı",
            "parent_location_id": "fr:city:neverwinter",
            "scene_kind": "tavern",
            "type": "inn",
        }
        self.world["doors"] = [{
            "id": "venue-door:location_001",
            "name": "Kael Hanı Kapısı",
            "description": "Kael Hanı sokağa açılan kapısı",
            "location": "fr:city:neverwinter",
            "locked": True,
            "open": False,
            "broken": False,
        }]
        npc = {"id": "npc_guard", "name": "Muhafız", "role": "Muhafız"}
        phrase = (
            "Muhafız, bu hanın kapısı kilitli. "
            "Dinlenmek için nereye gidebilirim?"
        )
        with patch.object(game, "_session", return_value=self.session):
            answer = game._direct_npc_smalltalk_response(phrase, npc)
            self.assertIsNotNone(answer)
            self.assertIn("kilitli", answer.casefold())
            self.assertNotIn("Yakınlarda Kael Hanı var", answer)
            self.world["doors"][0]["locked"] = False
            unlocked_answer = game._direct_npc_smalltalk_response(phrase, npc)
            greeting = game._direct_npc_smalltalk_response("Muhafız, merhaba.", npc)
        self.assertIn("Yakınlarda Kael Hanı var", unlocked_answer)
        self.assertIn("Merhaba", greeting)

    def test_named_destination_still_routes_through_travel(self):
        destination = "castle"
        self.assertIn(destination, self.world["locations"])
        self.assertNotEqual(self.world["location"], destination)

        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            result = self.session.run_player_turn("Kaleye gidiyorum.")

        action = result["action_result"]
        self.assertEqual(action["action"], "travel")
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
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
        self.assertNotEqual(context["visible_npcs"][0]["name"], npc["name"])
        self.assertNotIn(npc["name"], json.dumps(context, ensure_ascii=False))
        self.assertNotIn(
            ref["id"],
            {item["id"] for item in context["background_referents"]},
        )
        self.assertEqual(context["background_referents"], [])

    def test_narration_projection_promoted_presence_omits_anonymous_description(self):
        ref, npc = self._narration_projection_referent()

        presence = self.session._scene_presence_text(self.root_location)

        self.assertNotIn(npc["name"], presence)
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
        self.assertNotIn(npc["name"], presence)
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
        with patch("game.ollama.chat") as chat:
            played = self.session.run_player_turn("Ziyaretçi ne yapıyor?")
        chat.assert_not_called()
        self.assertEqual(played["narration"], description)
        self.assertEqual(
            played["_engine_event_evidence"]["telemetry"]["narration_model_calls"],
            0,
        )
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
        self.assertIn("Kesin bir ölçü henüz elinde değil", response)
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
        self.assertIn("Kesin bir ölçü henüz elinde değil", result["narration"])
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
    def test_v11_semantic_city_observation_and_existing_shop_discovery(self, model_chat):
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

        seeded_shop, seeded_shopkeeper = self._seed_local_shop()
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
        self.assertEqual(shop["id"], seeded_shop["id"])
        self.assertEqual(shop["id"], merchant["direct_result"]["shop_id"])
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(shop["shopkeeper_id"], merchant["direct_result"]["target_id"])
        shopkeeper = next(
            npc for npc in self.world["npcs"] if npc["id"] == shop["shopkeeper_id"]
        )
        self.assertEqual(shopkeeper["id"], seeded_shopkeeper["id"])
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
        door = next(
            item for item in self.world["doors"]
            if item.get("id") == f"venue-door:{tavern_id}"
        )
        door["locked"] = False
        door["open"] = True
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

    def _force_athletics(self, roll):
        self.session.character["modifiers"]["strength"] = 0
        self.session.character["proficient_skills"] = []
        self.session.character["proficiency_bonus"] = 2
        self.session.rng.randint = lambda _a, _b: roll

    def test_new_tavern_door_opens_or_stays_locked_and_reloads(self):
        search = self.session.plan_living_world_turn("Yakınlarda bir taverna arıyorum.")
        tavern_id = search["direct_result"]["target_id"]
        again = self.session.plan_living_world_turn("Yakınlarda bir taverna arıyorum.")
        self.assertEqual(again["direct_result"]["target_id"], tavern_id)
        doors = [
            door for door in self.world["doors"]
            if door.get("id") == game._venue_door_id(tavern_id)
        ]
        self.assertEqual(len(doors), 1)
        self.assertTrue(doors[0]["locked"])
        self.assertFalse(doors[0]["open"])
        self.assertEqual(doors[0]["location"], self.root_location)

        self._force_athletics(1)
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            failed = self.session.run_player_turn("Kapıyı açmaya çalışıyorum.")
        self.assertEqual(failed["action_result"]["outcome"], "failure")
        self.assertFalse(doors[0]["open"])
        self.assertEqual(self.world["location"], self.root_location)
        self.assertIn("kilitli kalır", failed["narration"])
        failed_telemetry = failed["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(failed_telemetry["total_model_calls"], 2)
        self.assertEqual(failed_telemetry["narration_model_calls"], 1)
        self.assertEqual(failed_telemetry["narration_source"], "deterministic_fallback")

        self._force_athletics(19)
        rejected = "Kapı kilitli kalır."
        calls = {"count": 0}

        def contradict(_model=None, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise AssertionError("intent")
            return {"message": {"content": json.dumps({
                "valid_response": True,
                "narration": rejected,
                "lore_claims": [],
                "world_updates": {},
            })}}

        with patch("game.ollama.chat", side_effect=contradict):
            opened = self.session.run_player_turn("Kapıyı açmaya çalışıyorum.")
        self.assertEqual(opened["action_result"]["outcome"], "success")
        self.assertTrue(doors[0]["open"])
        self.assertFalse(doors[0]["locked"])
        self.assertEqual(self.world["location"], self.root_location)
        self.assertIn("açılır", opened["narration"])
        self.assertNotIn(rejected, opened["narration"])
        self.assertNotIn(rejected, self.session.recent_dm_narrations)
        self.assertEqual(len(doors), 1)
        opened_telemetry = opened["_engine_event_evidence"]["telemetry"]
        self.assertEqual(opened_telemetry["narration_source"], "deterministic_fallback")
        self.assertLessEqual(opened_telemetry["total_model_calls"], 2)
        self.assertEqual(opened_telemetry["narration_model_calls"], 1)

        entered = self.session.plan_living_world_turn("Enter the tavern.")
        self.assertEqual(entered["direct_result"]["status"], "completed")
        self.assertEqual(self.world["location"], tavern_id)

        import tempfile
        from pathlib import Path
        path = Path(tempfile.mkdtemp()) / "venue-door.json"
        self.session.save_game(path)
        loaded = game.create_session(seed=99)
        loaded.load_game(path)
        loaded_door = next(
            door for door in loaded.world_state["doors"]
            if door.get("id") == game._venue_door_id(tavern_id)
        )
        self.assertTrue(loaded_door["open"])
        self.assertFalse(loaded_door["locked"])
        self.assertEqual(loaded.world_state["location"], tavern_id)
        other = game.create_session(seed=3)
        self.assertFalse(any(
            isinstance(door, dict) and door.get("id") == loaded_door["id"]
            for door in other.world_state.get("doors", [])
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
