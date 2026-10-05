import unittest
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import game
import local_dialogue
import living_world
import interaction_adventure
import campaign_time


class TestNarrativeRebalance(unittest.TestCase):
    def setUp(self):
        # Individual model fixtures override this guard; all other paths stay
        # offline even if a deterministic route accidentally reaches Ollama.
        model_guard = patch("game.ollama.chat", side_effect=AssertionError(
            "Unexpected model call in an offline narrative release gate"
        ))
        guarded_chat = model_guard.start()
        self.addCleanup(model_guard.stop)
        self.addCleanup(guarded_chat.assert_not_called)
        # Character initialization is not a world reset. Each case owns a
        # fresh session so earlier journeys/scenes cannot change its evidence.
        self.session = game.create_session(seed=42)
        self.session.character["current_hp"] = 10
        self.session.character["max_hp"] = 10
        self.session.character["name"] = "Tester"
        self.session.lore_authority_context = game._empty_lore_authority_context()
        self.session.recent_dm_narrations = []
        self.patcher = patch("builtins.print")
        self.patcher.start()
        self.session.world_state["location"] = "l_tavern"
        self.session.world_state["locations"] = {
            "l_tavern": {"id": "l_tavern", "name": "Eski Han", "type": "tavern"}
        }
        self.session.world_state["npcs"] = [{
            "id": "npc_barkeep",
            "name": "Hancı",
            "role": "Barkeep",
            "location": "l_tavern",
            "relationship": "neutral",
            "memory": [],
            "knowledge": [],
        }]
        self.session.world_state["flags"] = {"active_npc_id": "npc_barkeep"}

    def tearDown(self):
        self.patcher.stop()

    def mock_ollama_response(self, content):
        mock = MagicMock()
        mock.message.content = content
        return mock

    # 1. known deterministic gameplay intent reaches Qwen narration when eligible
    @patch("game.ollama.chat")
    def test_01_known_deterministic_gameplay_reaches_narration_model(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hancı tezgaha yaslanıp kısık sesle konuşur.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 0)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["intent_source"], "deterministic_dialogue")
        self.assertEqual(telemetry["narration_source"], "qwen")
        mock_chat.assert_called_once()

    # 2. ambiguous input may use: intent model -> Python resolution -> narration model
    @patch("game.ollama.chat")
    def test_02_ambiguous_intent_uses_intent_and_narration_models(self, mock_chat):
        mock_chat.side_effect = [
            self.mock_ollama_response('{"action": "dialogue", "target": "npc_barkeep"}'),
            self.mock_ollama_response('{"valid_response": true, "narration": "Hancı dönüp sana bakar.", "lore_claims": [], "world_updates": {}}')
        ]
        result = self.session.run_player_turn("Masanın altındaki gölgeye doğru hafifçe fısıldıyorum.")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 1)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["intent_source"], "model")
        self.assertEqual(telemetry["narration_source"], "qwen")

    # 3. no turn exceeds 2 model calls
    @patch("game.ollama.chat")
    def test_03_no_turn_exceeds_2_model_calls(self, mock_chat):
        mock_chat.side_effect = [
            self.mock_ollama_response('{"action": "dialogue", "target": "npc_barkeep"}'),
            self.mock_ollama_response('{"valid_response": true, "narration": "Selam yabancı.", "lore_claims": [], "world_updates": {}}')
        ]
        result = self.session.run_player_turn("Kim var orada?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(telemetry["total_model_calls"], 2)
        self.assertLessEqual(telemetry["intent_model_calls"] + telemetry["narration_model_calls"], 2)

    # 4. narration failure/validation rejection does NOT retry model
    @patch("game.ollama.chat")
    def test_04_narration_validation_failure_does_not_retry_model(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Kılıcını savurursun.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        self.assertNotIn("savurursun", result["narration"])

    # 5. narration cannot create canonical state
    @patch("game.ollama.chat")
    def test_05_narration_cannot_create_canonical_state(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hazine buldun.", "world_updates": {"create_quests": [{"quest_id": "q_hallucinated"}], "create_locations": [{"id": "loc_secret"}]}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        self.assertNotIn("q_hallucinated", [q.get("quest_id") for q in self.session.world_state.get("quests", [])])
        self.assertNotIn("loc_secret", self.session.world_state.get("locations", {}))
        self.assertEqual(self.session.character["current_hp"], 10)

    # 6. generated narration cannot invent player action
    @patch("game.ollama.chat")
    def test_06_generated_narration_cannot_invent_player_action(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Kılıcını savurursun ve ileri atılırsın.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        self.assertNotIn("savurursun", result["narration"])

    # 7. generated narration cannot invent player dialogue
    @patch("game.ollama.chat")
    def test_07_generated_narration_cannot_invent_player_dialogue(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Sen, \\"Bana bedava içki ver yoksa yakarım\\" diyorsun.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        self.assertNotIn("Bana bedava içki ver", result["narration"])

    # 8. generated narration cannot invent player emotion
    @patch("game.ollama.chat")
    def test_08_generated_narration_cannot_invent_player_emotion(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Korkarsın ve geri çekilirsin.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        self.assertNotIn("Korkarsın", result["narration"])

    # 9. unsupported official lore cannot become factual narration
    @patch("game.ollama.chat")
    def test_09_unsupported_official_lore_cannot_become_factual_narration(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Neverwinter is ruled by King Vharion.", "world_updates": {}, "lore_claims": [{"subject": "Neverwinter", "predicate": "ruled_by", "object_id_or_value": "King Vharion"}]}'
        )
        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        # Conversation-only packets are stripped of unsupported updates/claims
        # by the interaction owner before the general narration validator.
        self.assertEqual(result["narration"], interaction_adventure.immersive_unknown(
            self.session.world_state["npcs"][0]))
        self.assertNotIn("King Vharion", result["narration"])
        self.assertEqual(telemetry["intent_source"], "deterministic_dialogue")
        self.assertEqual(telemetry["narration_source"], "qwen")
        self.assertEqual(telemetry["narration_validation_result"], "accepted")
        self.assertIsNone(telemetry["fallback_reason"])
        self.assertEqual(telemetry["total_model_calls"], 1)
        mock_chat.assert_called_once()

    # 10. NPC-scoped player-name memory works ONLY when evidence exists
    @patch("game.ollama.chat")
    def test_10_npc_scoped_player_name_memory_works_only_when_evidence_exists(self, mock_chat):
        # Part A: Memory evidence exists -> Name is recognized
        self.session.world_state["npcs"][0]["memory"] = [{"speaker": "player", "text": "Benim adım Tester."}]
        res_with_memory = self.session.run_player_turn("Adımı hatırlıyor musun?")
        self.assertIn("Tester", res_with_memory["narration"])
        self.assertEqual(
            res_with_memory["_engine_event_evidence"]["telemetry"]["narration_source"],
            "python_memory_response"
        )

        # Part B: No memory evidence exists -> Name is NOT known / denied
        self.session.world_state["npcs"][0]["memory"] = []
        res_no_memory = self.session.run_player_turn("Adımı hatırlıyor musun?")
        self.assertNotIn("Tester", res_no_memory["narration"])
        self.assertTrue(
            "bilmiyorum" in res_no_memory["narration"].lower()
            or "hatırlamıyorum" in res_no_memory["narration"].lower()
            or "söylemedin" in res_no_memory["narration"].lower()
            or "kayıt yok" in res_no_memory["narration"].lower()
        )
        self.assertEqual(
            res_no_memory["_engine_event_evidence"]["telemetry"]["narration_source"],
            "python_memory_response"
        )

    # 11. unsupported NPC historical/memory claim fails closed naturally
    @patch("game.ollama.chat")
    def test_11_unsupported_npc_historical_claim_fails_closed_naturally(self, mock_chat):
        # Canonical memory is empty (no debt recorded)
        self.session.world_state["npcs"][0]["memory"] = []
        # Qwen attempts to hallucinate agreement with the debt claim
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hancı başını sallar, evet hatırladım, sana borcum vardı.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Hancı, bana borcun vardı, hatırladın mı?")
        narration_lower = result["narration"].lower()
        self.assertNotIn("sana borcum vardı", narration_lower)
        self.assertTrue(
            "hatırlamıyorum" in narration_lower
            or "kayıt yok" in narration_lower
            or "doğrulanmış bir bilgi yok" in narration_lower
        )

    # 12. active addressee remains stable
    @patch("game.ollama.chat")
    def test_12_active_addressee_remains_stable(self, mock_chat):
        mock_chat.side_effect = [
            self.mock_ollama_response('{"valid_response": true, "narration": "Hancı dinliyor.", "lore_claims": [], "world_updates": {}}'),
            self.mock_ollama_response('{"valid_response": true, "narration": "Hancı başını sallar.", "lore_claims": [], "world_updates": {}}')
        ]
        self.session.run_player_turn("Hey hancı!")
        self.assertEqual(self.session.world_state["flags"]["active_npc_id"], "npc_barkeep")
        self.session.run_player_turn("Bana bir içki ver.")
        self.assertEqual(self.session.world_state["flags"]["active_npc_id"], "npc_barkeep")

    # 13. world subject vs active addressee remains correct
    def test_13_world_subject_vs_active_addressee_remains_correct(self):
        question = "Bu şehrin hükümdarı kim?"
        self.assertTrue(local_dialogue.is_world_subject_question(question))
        with patch("game.ask_dungeon_master") as mock_ask:
            result = self.session.run_player_turn(question, target_id="npc_barkeep")
        mock_ask.assert_not_called()
        self.assertEqual(result["action_result"]["status"], "unverified")
        self.assertNotIn("Hancı", result["narration"])

    # 14. route/distance question cannot materialize unrelated procedural location
    def test_14_route_distance_question_does_not_materialize_location(self):
        loc_count_before = len(self.session.world_state.get("locations", {}))
        result = self.session.run_player_turn("Neverwinter ne kadar uzakta?")
        loc_count_after = len(self.session.world_state.get("locations", {}))
        self.assertEqual(loc_count_after, loc_count_before)
        self.assertNotIn("Neverwinter", self.session.world_state.get("locations", {}))

    # 15. rejected/unverified turn does not poison the next normal action
    @patch("game.ollama.chat")
    def test_15_rejected_turn_does_not_poison_next_normal_action(self, mock_chat):
        # Turn 1: Unverified lore question
        r1 = self.session.run_player_turn("Does King Vharion rule Neverwinter?")
        self.assertEqual(r1["action_result"]["status"], "unverified")

        # Turn 2: Normal look around
        mock_chat.side_effect = [
            self.mock_ollama_response('{"action": "search"}'),
            self.mock_ollama_response('{"valid_response": true, "narration": "Etrafına dikkatle bakıyorsun, ahşap masalar sakin görünüyor.", "lore_claims": [], "world_updates": {}}')
        ]
        r2 = self.session.run_player_turn("Etrafa bak")
        self.assertEqual(r2["action_result"]["status"], "resolved")
        self.assertIn("bakıyorsun", r2["narration"])

    # 16. restart/resume canonical state remains equivalent
    @patch("game.ollama.chat")
    def test_16_restart_resume_canonical_state_remains_equivalent(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hancı selamını alır.", "lore_claims": [], "world_updates": {}}'
        )
        self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        state1 = self.session.serialize_game_state()
        new_session = game.create_session()
        new_session.character = copy.deepcopy(self.session.character)
        new_session.world_state = copy.deepcopy(self.session.world_state)
        state2 = new_session.serialize_game_state()
        self.assertEqual(state1["player"]["current_hp"], state2["player"]["current_hp"])
        self.assertEqual(state1["player"]["name"], state2["player"]["name"])
        self.assertEqual(state1["world_state"]["location"], state2["world_state"]["location"])

    # 17. model-generated prose alone cannot create canonical memory or mutate relationships
    @patch("game.ollama.chat")
    def test_17_model_generated_prose_alone_cannot_create_canonical_memory(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor.", "lore_claims": [], "world_updates": {"update_npcs": [{"id": "npc_barkeep", "relationship": "allied"}]}}'
        )
        self.session.world_state["npcs"][0]["relationship"] = "neutral"
        gold_before = self.session.character.get("gold", 0)
        items_before = copy.deepcopy(self.session.character.get("inventory", []))

        result = self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        npc = self.session.world_state["npcs"][0]

        # 1. canonical relationship is unchanged
        self.assertEqual(npc.get("relationship"), "neutral")
        self.assertEqual(len(npc.get("knowledge", [])), 0)

        # 2. no reward/quest/inventory mutation occurs
        self.assertEqual(len(self.session.world_state.get("quests", [])), 0)
        self.assertEqual(self.session.character.get("gold", 0), gold_before)
        self.assertEqual(self.session.character.get("inventory", []), items_before)

        # 3. narration does not present the unsupported canonical claim as fact
        narration_lower = result["narration"].lower()
        self.assertNotIn("tamamen güveniyor", narration_lower)
        self.assertNotIn("en iyi dostu", narration_lower)

        # 4. unsupported claim is NOT written into trusted NPC memory
        memory_texts = [
            m.get("text", "") if isinstance(m, dict) else str(m)
            for m in npc.get("memory", [])
        ]
        for text in memory_texts:
            self.assertNotIn("tamamen güveniyor", text.lower())
            self.assertNotIn("en iyi dostu", text.lower())

        # 5. there is no extra model retry
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(telemetry["total_model_calls"], 2)

        # 6. The interaction owner substitutes safe prose before validation;
        # telemetry describes that accepted text, not the discarded model text.
        self.assertEqual(result["narration"], interaction_adventure.immersive_unknown(npc))
        self.assertEqual(telemetry["narration_validation_result"], "accepted")
        self.assertIsNone(telemetry["fallback_reason"])
        self.assertEqual(telemetry["intent_source"], "deterministic_dialogue")
        self.assertEqual(telemetry["narration_source"], "qwen")
        self.assertEqual(telemetry["total_model_calls"], 1)
        mock_chat.assert_called_once()

    @patch("game.ollama.chat")
    def test_general_narrator_still_rejects_lore_and_relationship_invention(self, chat):
        # Greetings take the ordinary resolved-smalltalk narration route, not
        # the conversation packet sanitizer tested above. Keep both guards.
        for narration, claims, reason in (
            ("Neverwinter is ruled by King Vharion.",
             [{"subject": "Neverwinter", "predicate": "ruled_by",
               "object_id_or_value": "King Vharion"}], "UNVERIFIED_LORE_CLAIM"),
            ("Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor.",
             [], "CANONICAL_RELATIONSHIP_CONTRADICTION"),
        ):
            with self.subTest(reason=reason):
                self.session.recent_dm_narrations.clear()
                chat.reset_mock()
                chat.return_value = self.mock_ollama_response(json.dumps({
                    "valid_response": True, "narration": narration,
                    "lore_claims": claims, "world_updates": {},
                }))
                result = self.session.run_player_turn("Hancı'ya selam veriyorum")
                telemetry = result["_engine_event_evidence"]["telemetry"]
                self.assertEqual(result["action_result"]["status"], "answered_smalltalk")
                self.assertEqual(telemetry["fallback_reason"], reason)
                self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
                self.assertEqual(telemetry["narration_validation_result"], "python_fallback")
                self.assertEqual(telemetry["total_model_calls"], 1)
                self.assertNotEqual(result["narration"], narration)
                self.assertEqual(self.session.world_state["npcs"][0]["relationship"], "neutral")
                chat.assert_called_once()

    @patch("game.ollama.chat")
    def test_registered_proposal_without_an_authored_route_does_not_move_player(self, chat):
        initial_location = self.session.world_state["location"]
        chat.side_effect = [
            self.mock_ollama_response(json.dumps({
                "intent": "travel", "action": "travel",
                "target": {"type": "location", "reference": "Eski Kütüphane"},
                "completion": "completed", "confidence": 0.9,
            })),
            self.mock_ollama_response(json.dumps({
                "valid_response": True,
                "narration": "Eski Kütüphane kapısına vardın.",
                "lore_claims": [], "world_updates": {"create_locations": [{
                    "name": "Eski Kütüphane", "type": "library",
                    "description": "Terk edilmiş eski kütüphane.",
                }]},
            })),
        ]
        with patch.object(self.session.rng, "randint") as dice:
            result = self.session.run_player_turn("Eski kütüphaneye gidiyorum")
        self.assertEqual(result["action_result"]["status"], "unverified")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.session.world_state["location"], initial_location)
        self.assertEqual(len(self.session.world_state["locations"]), 2)
        self.assertNotIn("journey", self.session.world_state)
        self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"], 0)
        dice.assert_not_called()
        self.assertEqual(chat.call_count, 2)

    # 18. legitimate unknown procedural travel destination creates matching location
    @patch("game.ollama.chat")
    def test_18_legitimate_unknown_procedural_travel_destination_creates_matching_location(self, mock_chat):
        # Both ends are authored local procedural fiction: the Time owner
        # permits its explicit five-minute pedestrian convention.
        self.session.world_state["locations"]["l_tavern"]["reality_layer"] = "PROCEDURAL_LOCAL_FICTION"
        intent_payload = '{"intent": "travel", "action": "travel", "target": {"type": "location", "reference": "Kuzeydeki Terkedilmiş Maden"}, "completion": "completed", "confidence": 0.9}'
        narration_payload = '{"valid_response": true, "narration": "Kuzeydeki Terkedilmiş Maden girişine ulaştın.", "lore_claims": [], "world_updates": {"create_locations": [{"name": "Kuzeydeki Terkedilmiş Maden", "type": "dungeon", "description": "Terk edilmiş bir maden."}]}}'
        mock_chat.side_effect = [
            self.mock_ollama_response(intent_payload),
            self.mock_ollama_response(narration_payload)
        ]
        locs_before = len(self.session.world_state.get("locations", {}))
        with patch.object(self.session.rng, "randint", return_value=6) as dice:
            result = self.session.run_player_turn("Kuzeydeki terkedilmiş madene gidiyorum")
        locs_after = len(self.session.world_state.get("locations", {}))
        self.assertEqual(locs_after, locs_before + 1)
        self.assertEqual(result["action_result"]["status"], "completed")
        dice.assert_called_once_with(1, 6)
        self.assertEqual(result["action_result"]["time_result"]["elapsed_seconds"], 300)
        location = self.session.world_state["locations"][self.session.world_state["location"]]
        self.assertEqual(location["name"], "Kuzeydeki Terkedilmiş Maden")
        self.assertEqual(self.session.world_state["journey"]["status"], "ARRIVED")

    # 19. unrelated model-proposed location is rejected
    @patch("game.ollama.chat")
    def test_19_unrelated_model_proposed_location_is_rejected(self, mock_chat):
        intent_payload = '{"intent": "travel", "action": "travel", "target": {"type": "location", "reference": "Kuzeydeki Terkedilmiş Maden"}, "completion": "completed", "confidence": 0.9}'
        narration_payload = '{"valid_response": true, "narration": "Uzak Çöl kumlarına ulaştın.", "lore_claims": [], "world_updates": {"create_locations": [{"name": "Uzak Çöl", "type": "wilderness", "description": "Uzak bir çöl."}]}}'
        mock_chat.side_effect = [
            self.mock_ollama_response(intent_payload),
            self.mock_ollama_response(narration_payload)
        ]
        locs_before = len(self.session.world_state.get("locations", {}))
        result = self.session.run_player_turn("Kuzeydeki terkedilmiş madene gidiyorum")
        locs_after = len(self.session.world_state.get("locations", {}))
        self.assertEqual(locs_after, locs_before)
        self.assertEqual(result["action_result"]["status"], "failed")
        self.assertNotIn("Uzak Çöl", result["narration"])

    # 20. route/distance question cannot create location
    def test_20_route_distance_question_cannot_create_location(self):
        loc_count_before = len(self.session.world_state.get("locations", {}))
        result = self.session.run_player_turn("Neverwinter ne kadar uzakta?")
        loc_count_after = len(self.session.world_state.get("locations", {}))
        self.assertEqual(loc_count_after, loc_count_before)
        self.assertNotIn("Neverwinter", self.session.world_state.get("locations", {}))

    # 21. location proposal and narration stays within max 2 model calls
    @patch("game.ollama.chat")
    def test_21_location_proposal_and_narration_stays_within_max_2_model_calls(self, mock_chat):
        intent_payload = '{"intent": "travel", "action": "travel", "target": {"type": "location", "reference": "Kuzeydeki Terkedilmiş Maden"}, "completion": "completed", "confidence": 0.9}'
        narration_payload = '{"valid_response": true, "narration": "Kuzeydeki Terkedilmiş Maden girişine ulaştın.", "lore_claims": [], "world_updates": {"create_locations": [{"name": "Kuzeydeki Terkedilmiş Maden", "type": "dungeon", "description": "Terk edilmiş bir maden."}]}}'
        mock_chat.side_effect = [
            self.mock_ollama_response(intent_payload),
            self.mock_ollama_response(narration_payload)
        ]
        result = self.session.run_player_turn("Kuzeydeki terkedilmiş madene gidiyorum")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(telemetry["total_model_calls"], 2)

    # 22. failed location proposal leaves current location unchanged
    @patch("game.ollama.chat")
    def test_22_failed_location_proposal_leaves_current_location_unchanged(self, mock_chat):
        initial_loc = self.session.world_state.get("location")
        intent_payload = '{"intent": "travel", "action": "travel", "target": {"type": "location", "reference": "Kuzey Kalesi"}, "completion": "completed", "confidence": 0.9}'
        narration_payload = '{"valid_response": true, "narration": "Büyülü Orman derinliklerine vardın.", "lore_claims": [], "world_updates": {"create_locations": [{"name": "Büyülü Orman", "type": "forest", "description": "Orman."}]}}'
        mock_chat.side_effect = [
            self.mock_ollama_response(intent_payload),
            self.mock_ollama_response(narration_payload)
        ]
        result = self.session.run_player_turn("Kuzey kalesine gidiyorum")
        self.assertEqual(self.session.world_state.get("location"), initial_loc)
        self.assertEqual(result["action_result"]["status"], "failed")

    # 23. successful committed travel produces correct canonical location
    @patch("game.ollama.chat")
    def test_23_successful_committed_travel_produces_correct_canonical_location(self, mock_chat):
        self.session.world_state["locations"]["l_tavern"]["reality_layer"] = "PROCEDURAL_LOCAL_FICTION"
        initial_loc = self.session.world_state.get("location")
        intent_payload = '{"intent": "travel", "action": "travel", "target": {"type": "location", "reference": "Eski Kütüphane"}, "completion": "completed", "confidence": 0.9}'
        narration_payload = '{"valid_response": true, "narration": "Eski Kütüphane kapısına vardın.", "lore_claims": [], "world_updates": {"create_locations": [{"name": "Eski Kütüphane", "type": "library", "description": "Terk edilmiş eski kütüphane."}]}}'
        mock_chat.side_effect = [
            self.mock_ollama_response(intent_payload),
            self.mock_ollama_response(narration_payload)
        ]
        with patch.object(self.session.rng, "randint", return_value=6) as dice:
            result = self.session.run_player_turn("Eski kütüphaneye gidiyorum")
        new_loc = self.session.world_state.get("location")
        self.assertNotEqual(new_loc, initial_loc)
        self.assertIn(new_loc, self.session.world_state.get("locations", {}))
        self.assertEqual(result["action_result"]["status"], "completed")
        dice.assert_called_once_with(1, 6)
        self.assertEqual(result["action_result"]["new_location"], new_loc)
        self.assertEqual(self.session.world_state["locations"][new_loc]["name"], "Eski Kütüphane")
        self.assertEqual(result["action_result"]["time_result"]["elapsed_seconds"], 300)

    # 24 (A). multiple NPCs present + active NPC exists: "Etrafımda neler var?" resolves as explore, not dialogue clarification
    @patch("game.ollama.chat")
    def test_24_multiple_npcs_and_active_npc_explore_not_dialogue_clarification(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Taverna çevresine bakıyorsun, masalar dolu.", "lore_claims": [], "world_updates": {}}'
        )
        self.session.world_state["npcs"] = [
            {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "l_tavern", "relationship": "neutral", "memory": [], "knowledge": []},
            {"id": "npc_002", "name": "Elaris", "role": "Müşteri", "location": "l_tavern", "relationship": "neutral", "memory": [], "knowledge": []},
        ]
        self.session.world_state["flags"]["active_npc_id"] = "npc_001"
        result = self.session.run_player_turn("Etrafımda neler var?")
        action = result["action_result"]
        self.assertEqual(action.get("action"), "explore")
        self.assertNotEqual(action.get("action"), "dialogue")
        self.assertNotEqual(action.get("status"), "clarification")
        self.assertNotIn("Bu tanıma uyan birden fazla kişi var", result["narration"])

    # 25 (B). deterministically resolved ordinary NPC greeting: exactly one narration model call when narration-eligible
    @patch("game.ollama.chat")
    def test_25_deterministic_npc_greeting_makes_single_narration_call(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Gromm sana başıyla selam verir.", "lore_claims": [], "world_updates": {}}'
        )
        self.session.world_state["npcs"] = [
            {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "l_tavern", "relationship": "neutral", "memory": [], "knowledge": []},
        ]
        result = self.session.run_player_turn("Gromm'a selam veriyorum")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 0)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["status"], "answered_smalltalk")

    # 26 (C). deterministically resolved exploration: exactly one narration model call when narration-eligible
    @patch("game.ollama.chat")
    def test_26_deterministic_exploration_makes_single_narration_call(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Etrafına baktığında tahta masalar ve ocak başı dikkat çeker.", "lore_claims": [], "world_updates": {}}'
        )
        result = self.session.run_player_turn("Etrafıma bakıyorum")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 0)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        self.assertEqual(result["action_result"]["action"], "explore")
        self.assertEqual(result["action_result"]["status"], "observed")

    # 27 (D). direct factual queries return from Python without forcing a Qwen call
    @patch("game.ollama.chat")
    def test_27_direct_factual_queries_use_zero_model_calls(self, mock_chat):
        # Keep the location-query regression alongside presence and identity.
        # The scoped mock prevents a routing regression from calling a live model.
        mock_chat.return_value = self.mock_ollama_response(
            '{"narration": "Hancı başını sallar.", "world_updates": {}, "lore_claims": []}'
        )
        for text, expected in (
            ("Neredeyim?", "Eski Han"),
            ("Tavernada kimler var?", "Hancı"),
            ("Hancı, senin adın ne?", "Hancı"),
        ):
            mock_chat.reset_mock()
            result = self.session.run_player_turn(text)
            with self.subTest(query=text, contract="python_only"):
                self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
                mock_chat.assert_not_called()
            with self.subTest(query=text, contract="canonical_answer"):
                self.assertEqual(result["action_result"]["action"], "query")
                self.assertIn(expected, result["narration"])

    @patch("game.ollama.chat")
    def test_location_queries_bypass_conversation_proposals(self, mock_chat):
        for text, target_id in (
            ("Neredeyim?", None),
            ("Şu an neredeyim?", None),
            ("Konumum neresi?", None),
            ("Hancı, hangi yerdeyim?", "npc_barkeep"),
            ("Buranın adı ne?", None),
        ):
            with self.subTest(query=text, target_id=target_id):
                npc_memory = copy.deepcopy(self.session.world_state["npcs"][0]["memory"])
                with patch("game.parse_player_intent") as parse_intent:
                    result = self.session.run_player_turn(text, target_id=target_id)
                parse_intent.assert_not_called()
                mock_chat.assert_not_called()
                self.assertEqual(result["action_result"]["query_type"], "location")
                self.assertEqual(
                    result["action_result"]["direct_response"],
                    "Bulunduğun yer: Eski Han.",
                )
                self.assertIn("Bulunduğun yer: Eski Han.", result["narration"])
                telemetry = result["_engine_event_evidence"]["telemetry"]
                self.assertEqual(telemetry["intent_model_calls"], 0)
                self.assertEqual(telemetry["narration_model_calls"], 0)
                self.assertEqual(self.session.world_state["location"], "l_tavern")
                self.assertEqual(self.session.world_state["npcs"][0]["memory"], npc_memory)

    @patch("game.ollama.chat")
    def test_character_queries_bypass_active_npc_conversation_proposals(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"narration": "Hancı başını sallar.", "world_updates": {}, "lore_claims": []}'
        )
        self.session.character.update(
            name="Tester", race="Elf", **{"class": "Wizard"}, level=7,
        )
        npc = self.session.world_state["npcs"][0]
        self.session.world_state["npcs"].append({
            "id": "npc_patron", "name": "Yolcu", "role": "Patron",
            "location": "l_tavern", "relationship": "neutral",
            "memory": [], "knowledge": [],
        })
        # An NPC may remember an alias; it is not character-sheet authority.
        npc["memory"] = [{"speaker": "player", "text": "Benim adım Arven."}]
        for text, expected in (
            ("Benim adım ne?", "Adın Tester."),
            ("Benim ismim ne?", "Adın Tester."),
            ("Karakterimin adı ne?", "Adın Tester."),
            ("Karakterimin ismi ne?", "Adın Tester."),
            ("Ben kimim?", "Adın Tester."),
            ("Karakterim kim?", "Adın Tester."),
            ("Kim oynuyorum?", "Adın Tester."),
            ("Hangi sınıfım?", "sınıfın Wizard."),
            ("Sınıfım ne?", "sınıfın Wizard."),
            ("Hangi class?", "sınıfın Wizard."),
            ("Hangi ırktayım?", "ırkın Elf."),
            ("Irkım ne?", "ırkın Elf."),
            ("Hangi ırkım?", "ırkın Elf."),
            ("Seviyem kaç?", "seviyen 7."),
            ("Levelim kaç?", "seviyen 7."),
            ("Kaçıncı seviyedeyim?", "seviyen 7."),
            ("Hancı, benim adım ne?", "Adın Tester."),
            ("Benim adım ne, sınıfım ne, ırkım ne, seviyem kaç?",
             "Adın Tester; ırkın Elf; sınıfın Wizard; seviyen 7."),
        ):
            for target_id in (None, "npc_barkeep"):
                with self.subTest(query=text, target_id=target_id):
                    character_before = copy.deepcopy(self.session.character)
                    memory_before = copy.deepcopy(npc["memory"])
                    with patch("game.parse_player_intent") as parse_intent:
                        result = self.session.run_player_turn(text, target_id=target_id)
                    parse_intent.assert_not_called()
                    mock_chat.assert_not_called()
                    self.assertEqual(result["action_result"]["action"], "character_query")
                    self.assertEqual(result["action_result"]["direct_response"], expected)
                    self.assertEqual(result["narration"], expected)
                    telemetry = result["_engine_event_evidence"]["telemetry"]
                    self.assertEqual(telemetry["intent_model_calls"], 0)
                    self.assertEqual(telemetry["narration_model_calls"], 0)
                    self.assertEqual(telemetry["total_model_calls"], 0)
                    self.assertEqual(npc["memory"], memory_before)
                    self.assertEqual(self.session.character, character_before)
                    self.assertEqual(self.session.world_state["flags"]["active_npc_id"], "npc_barkeep")

    @patch("game.ollama.chat")
    def test_name_disclosure_and_npc_recall_remain_separate_from_character_facts(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"narration": "Hancı başını sallar.", "world_updates": {}, "lore_claims": []}'
        )
        npc = self.session.world_state["npcs"][0]
        disclosure = "Benim adım Arven."
        result = self.session.run_player_turn(disclosure)
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["status"], "player_name_disclosed")
        mock_chat.assert_not_called()
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
        self.assertTrue(any(
            entry.get("speaker") == "player" and entry.get("text") == disclosure
            for entry in npc["memory"]
        ))
        self.assertEqual(self.session.character["name"], "Tester")

        mock_chat.reset_mock()
        recall = self.session.run_player_turn("Adımı hatırlıyor musun?")
        self.assertIn("Arven", recall["narration"])
        self.assertEqual(
            recall["_engine_event_evidence"]["telemetry"]["narration_source"],
            "python_memory_response",
        )
        mock_chat.assert_not_called()

        self_query = self.session.run_player_turn("Benim adım ne?")
        self.assertEqual(self_query["narration"], "Adın Tester.")
        mock_chat.assert_not_called()

    # 28 (E). all tested turns remain <= 2 total model calls
    @patch("game.ollama.chat")
    def test_28_all_tested_turns_remain_under_max_2_calls(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Taverna hareketli ve gürültülü.", "lore_claims": [], "world_updates": {}}'
        )
        turns = [
            "Etrafımda neler var?",
            "Gromm'a selam veriyorum",
            "Etrafıma bakıyorum",
            "Neredeyim?",
            "Tavernada kimler var?",
        ]
        for t in turns:
            res = self.session.run_player_turn(t)
            telemetry = res["_engine_event_evidence"]["telemetry"]
            self.assertLessEqual(telemetry["total_model_calls"], 2, f"Turn '{t}' exceeded 2 model calls: {telemetry}")


    # 29. unverified historical/memory claim for remote NPC fails closed without model calls
    def test_29_unverified_historical_claim_remote_npc_fails_closed(self):
        self.session.world_state["location"] = "forest"
        self.session.world_state["npcs"] = [
            {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "relationship": "neutral", "memory": [], "knowledge": []},
        ]
        result = self.session.run_player_turn("Gromm bana ejderha hazinesinden bahsetmişti.")
        action = result["action_result"]
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(action.get("status"), "unverified")
        self.assertFalse(action.get("success"))
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(self.session.world_state["location"], "forest")
        narration = result["narration"]
        self.assertTrue(
            "kayıt yok" in narration or "bulunmuyor" in narration or "hatırlam" in narration,
            f"Expected denial/unverified indication, got: {narration}"
        )
        self.assertNotIn("çınlıyor", narration)
        self.assertNotIn("sırlarını açan", narration)

    # 30. unverified historical/memory claim for local NPC fails closed with direct denial
    def test_30_unverified_historical_claim_local_npc_fails_closed(self):
        self.session.world_state["location"] = "tavern"
        self.session.world_state["npcs"] = [
            {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "relationship": "neutral", "memory": [], "knowledge": []},
        ]
        result = self.session.run_player_turn("Gromm bana ejderha hazinesinden bahsetmişti.")
        action = result["action_result"]
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(action.get("status"), "unverified")
        self.assertFalse(action.get("success"))
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertIn("hatırlamıyorum", result["narration"])

    # 31. narration safety validator rejects model narration affirming unverified historical premise
    def test_31_narration_safety_rejects_unverified_claim_affirmation(self):
        self.session.world_state["location"] = "forest"
        self.session.world_state["npcs"] = [
            {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "relationship": "neutral", "memory": [], "knowledge": []},
        ]
        unverified_input = "Gromm bana ejderha hazinesinden bahsetmişti."
        model_affirmation = "Gromm’un sözleri hâlâ kulaklarında çınlıyor; ejderha hazinesinin sırlarını açan bir yolun olması gerektiğini belirtti."
        # API narration observers may wrap this module callable without exposing
        # GameSession's dynamic-helper marker. Bind the owning session explicitly.
        output = game.finalize_narration(
            model_affirmation,
            unverified_input,
            npc_target=None,
            action_result={"action": "dialogue", "status": "unverified", "success": False},
            session=self.session,
        )
        self.assertTrue(
            self.session.last_narration_safety["reason_code"] in ("UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM", "NPC_MEMORY_UNSUPPORTED_CLAIM"),
            f"Expected safety reason code, got: {self.session.last_narration_safety}"
        )
        self.assertNotIn("çınlıyor", output)
        self.assertTrue(
            "kayıt yok" in output or "bulunmuyor" in output or "hatırlam" in output or "kesin yanıt belirsiz" in output,
            f"Expected fallback denial, got: {output}"
        )

    # 32. canonical city ID resolves deterministically with 0 model calls
    def test_32_canonical_city_id_look_is_deterministic_zero_model_calls(self):
        self.session.world_state["location"] = "fr:city:waterdeep"
        self.session.world_state["locations"] = {
            "fr:city:waterdeep": {"id": "fr:city:waterdeep", "name": "Waterdeep"}
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafımda neler var?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "deterministic_system")
        self.assertIn("Waterdeep", result["narration"])

    # 33. city display-name/alias resolves deterministically with 0 model calls
    def test_33_city_display_alias_look_is_deterministic_zero_model_calls(self):
        self.session.world_state["location"] = "Waterdeep"
        self.session.world_state["locations"] = {
            "fr:city:waterdeep": {
                "id": "fr:city:waterdeep",
                "name": "Waterdeep",
                "aliases": ["waterdeep"],
            }
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafıma bakıyorum.")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "deterministic_system")
        self.assertIn("Waterdeep", result["narration"])

    # 34. sub-location with city parent resolves deterministically with 0 model calls
    def test_34_sublocation_with_city_parent_look_is_deterministic_zero_model_calls(self):
        self.session.world_state["location"] = "loc_market_square"
        self.session.world_state["locations"] = {
            "fr:city:neverwinter": {"id": "fr:city:neverwinter", "name": "Neverwinter"},
            "loc_market_square": {
                "id": "loc_market_square",
                "name": "Pazar Meydanı",
                "parent_location_id": "fr:city:neverwinter",
            },
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafımda neler var?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "deterministic_system")

    # 35. district location resolves deterministically with 0 model calls
    def test_35_district_look_is_deterministic_zero_model_calls(self):
        self.session.world_state["location"] = "loc_sea_ward"
        self.session.world_state["locations"] = {
            "fr:city:waterdeep": {"id": "fr:city:waterdeep", "name": "Waterdeep"},
            "loc_sea_ward": {
                "id": "loc_sea_ward",
                "name": "Sea Ward",
                "type": "district",
                "parent_location_id": "fr:city:waterdeep",
            },
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafıma bakıyorum.")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "deterministic_system")

    # 36. street location resolves deterministically with 0 model calls
    def test_36_street_look_is_deterministic_zero_model_calls(self):
        self.session.world_state["location"] = "loc_high_road"
        self.session.world_state["locations"] = {
            "fr:city:neverwinter": {"id": "fr:city:neverwinter", "name": "Neverwinter"},
            "loc_high_road": {
                "id": "loc_high_road",
                "name": "High Road",
                "type": "street",
                "parent_location_id": "fr:city:neverwinter",
            },
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafımda neler var?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["total_model_calls"], 0)
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "deterministic_system")

    # 37. tavern exploration preserves 1 Qwen model call
    @patch("game.ollama.chat")
    def test_37_tavern_exploration_preserves_one_model_call(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Tavernanın loş ışıkları masalara vuruyor.", "lore_claims": [], "world_updates": {}}'
        )
        self.session.world_state["location"] = "l_tavern"
        self.session.world_state["locations"] = {
            "l_tavern": {"id": "l_tavern", "name": "Eski Han", "type": "tavern", "scene_kind": "tavern"}
        }
        self.session.world_metadata = {"environment": "city"}
        result = self.session.run_player_turn("Etrafımda neler var?")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 0)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        self.assertEqual(telemetry["narration_source"], "qwen")

    # 38. forest exploration preserves 1 Qwen model call
    @patch("game.ollama.chat")
    def test_38_forest_exploration_preserves_one_model_call(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Ağaçların arasından rüzgarın uğultusu duyuluyor.", "lore_claims": [], "world_updates": {}}'
        )
        self.session.world_state["location"] = "forest"
        self.session.world_state["locations"] = {
            "forest": {"id": "forest", "name": "Karanlık Orman", "type": "forest", "scene_kind": "wilderness"}
        }
        self.session.world_metadata = {"environment": "wilderness"}
        result = self.session.run_player_turn("Etrafıma bakıyorum.")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 0)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        self.assertEqual(telemetry["narration_source"], "qwen")


class ResolvedNarrationFallbackTests(unittest.TestCase):
    """Resolved Python outcomes survive narration rejection without model retries."""

    def setUp(self):
        model_guard = patch("game.ollama.chat", side_effect=AssertionError(
            "Unexpected model call in an offline narrative release gate"
        ))
        guarded_chat = model_guard.start()
        self.addCleanup(model_guard.stop)
        self.addCleanup(guarded_chat.assert_not_called)
        self.session = game.create_session(seed=42)
        self.session.character["name"] = "Tester"
        self.world = self.session.world_state
        self.world["location"] = "tavern"
        self.world["npcs"] = []
        self.world["next_npc_number"] = 5
        self.npc = self.session.create_npc_from_ai({
            "name": "Darian", "role": "Yolcu", "location": "tavern",
            "personality": "Kibar.", "appearance": "Sade bir pelerin giymiş.",
            "relationship": "neutral",
        })
        self.world["flags"]["active_npc_id"] = self.npc["id"]
        living_world.ensure_scene_record(self.world, "tavern", 0)["materialized"] = True
        self.session.lore_authority_context = game._empty_lore_authority_context()
        self.player_input = "Onunla kısa bir selamlaşıyorum."
        self.action = {
            "action": "dialogue", "status": "answered_smalltalk",
            "success": True, "npc_id": self.npc["id"], "state_changes": [],
        }
        self.resolved_response = self.session._direct_npc_smalltalk_response(
            self.player_input, self.npc
        )
        self.unsafe_response = "Halric başını sallar."

    def finalize(self, narration, candidate):
        return game.finalize_narration(
            narration, self.player_input, npc_target=self.npc,
            action_result=self.action, resolved_fallback_response=candidate,
            session=self.session,
        )

    @patch("game.ollama.chat")
    def test_rejected_smalltalk_preserves_resolved_outcome_and_accounting(self, chat):
        from api.tests.live_playable_living_world_v1_smoke import _is_fallback_candidate

        chat.return_value = {"message": {"content": json.dumps({
            "narration": self.unsafe_response, "world_updates": {}, "lore_claims": [],
        })}}
        for player_input in (self.player_input, "Onunla selamlaşıyoruz."):
            with self.subTest(player_input=player_input):
                self.session.recent_dm_narrations.clear()
                expected = self.session._direct_npc_smalltalk_response(player_input, self.npc)
                self.assertTrue(expected)
                chat.reset_mock()
                result = self.session.run_player_turn(player_input, target_id=self.npc["id"])
                self.assertEqual(result["action_result"]["status"], "answered_smalltalk")
                self.assertEqual(result["action_result"]["npc_id"], "npc_005")
                self.assertTrue(result["action_result"]["success"])
                self.assertEqual(result["narration"], expected)
                diagnostic = self.session.last_narration_safety
                self.assertEqual(diagnostic["reason_code"], "UNREGISTERED_NAMED_ENTITY")
                self.assertEqual(diagnostic["trigger_span"], "Halric")
                self.assertEqual(diagnostic["handling"], "python_fallback")
                self.assertEqual(diagnostic["tier"], "tier_3_fallback")
                self.assertTrue(_is_fallback_candidate(diagnostic))
                telemetry = result["_engine_event_evidence"]["telemetry"]
                self.assertEqual(telemetry["intent_model_calls"], 0)
                self.assertEqual(telemetry["narration_model_calls"], 1)
                self.assertEqual(telemetry["total_model_calls"], 1)
                self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
                chat.assert_called_once()
                self.assertEqual([npc["name"] for npc in self.world["npcs"]], ["Darian"])

    def test_resolved_fallback_is_checked_by_existing_safety(self):
        original = game._narration_safety_decision
        with patch("game._narration_safety_decision", wraps=original) as decide:
            result = self.finalize(self.unsafe_response, self.resolved_response)
        self.assertEqual(result, self.resolved_response)
        self.assertIn(self.resolved_response, [call.args[0] for call in decide.call_args_list])
        self.assertEqual(len(self.session.narration_safety_history), 1)
        self.assertEqual(self.session.last_narration_safety["reason_code"], "UNREGISTERED_NAMED_ENTITY")

    def test_invalid_or_unsafe_resolved_fallback_keeps_legacy_behavior(self):
        legacy = self.session._fallback_for_action_result(
            self.player_input, self.action, npc_target=self.npc
        )
        for candidate in (None, "", " \n ", 17, "<think>discard</think>", self.unsafe_response):
            with self.subTest(candidate=candidate):
                self.session.recent_dm_narrations.clear()
                self.assertEqual(self.finalize(self.unsafe_response, candidate), legacy)
                self.assertEqual(self.session.last_narration_safety["reason_code"], "UNREGISTERED_NAMED_ENTITY")
        self.assertEqual([npc["name"] for npc in self.world["npcs"]], ["Darian"])

    def test_unregistered_name_classifier_remains_strict(self):
        decision = self.session._narration_safety_decision(
            self.unsafe_response, self.player_input, self.npc, self.action
        )
        self.assertTrue(decision["unsafe"])
        self.assertEqual(decision["reason_code"], "UNREGISTERED_NAMED_ENTITY")
        self.assertEqual(decision["trigger_span"], "Halric")
        self.assertFalse(self.session._narration_safety_decision(
            self.resolved_response, self.player_input, self.npc, self.action
        )["unsafe"])

    def test_repetition_keeps_resolved_outcome_and_existing_classification(self):
        self.session.recent_dm_narrations.append(self.resolved_response.casefold())
        result = self.finalize(self.unsafe_response, self.resolved_response)
        self.assertEqual(result, self.resolved_response)
        self.assertEqual(self.session.last_narration_safety["reason_code"], "REPEATED_NARRATION")
        self.assertEqual(self.session.last_narration_safety["handling"], "python_fallback")
        self.assertEqual(len(self.session.narration_safety_history), 1)

    def test_accepted_narration_and_existing_repair_still_take_precedence(self):
        accepted = "Darian başını sallar."
        self.assertEqual(self.finalize(accepted, self.resolved_response), accepted)
        self.assertEqual(self.session.last_narration_safety["handling"], "accepted")
        self.session.recent_dm_narrations.clear()
        self.assertEqual(self.finalize(accepted + " Kılıcını savurursun.", self.resolved_response), accepted)
        self.assertEqual(self.session.last_narration_safety["handling"], "repaired")
        self.assertEqual(self.session.last_narration_safety["reason_code"], "INVENTED_PLAYER_ACTION")

    def test_empty_model_narration_uses_resolved_fallback(self):
        self.assertEqual(self.finalize("", self.resolved_response), self.resolved_response)
        self.assertEqual(self.session.last_narration_safety["reason_code"], "EMPTY_NARRATION")

    @patch("game.ollama.chat")
    def test_invalid_model_packet_uses_resolved_fallback_without_retry(self, chat):
        legacy = self.session._fallback_for_action_result(self.player_input, self.action)
        result = game.finalize_narration(
            legacy, self.player_input, npc_target=self.npc, action_result=self.action,
            fallback_reason_code="INVALID_MODEL_RESPONSE",
            resolved_fallback_response=self.resolved_response, session=self.session,
        )
        self.assertEqual(result, self.resolved_response)
        self.assertEqual(self.session.last_narration_safety["reason_code"], "INVALID_MODEL_RESPONSE")
        self.assertEqual(self.session.last_narration_safety["handling"], "python_fallback")
        chat.assert_not_called()

    def test_dedicated_lore_fallback_remains_authoritative(self):
        expected = self.session._unverified_lore_response(self.player_input, self.npc)
        result = game.finalize_narration(
            self.unsafe_response, self.player_input, npc_target=self.npc,
            action_result=self.action, fallback_reason_code="UNVERIFIED_LORE_CLAIM",
            resolved_fallback_response=self.resolved_response, session=self.session,
        )
        self.assertEqual(result, expected)
        self.assertEqual(self.session.last_narration_safety["reason_code"], "UNVERIFIED_LORE_CLAIM")

    def test_other_resolved_action_uses_its_deterministic_fallback(self):
        self.action.update(action="approach", status="completed")
        expected = "Darian seni fark edip sana dönüyor."
        self.assertEqual(self.finalize(self.unsafe_response, expected), expected)

    @patch("game.ollama.chat")
    def test_proposal_turn_preserves_final_action_fallback(self, chat):
        self.world["locations"]["tavern"] = {
            "id": "tavern", "name": "Taverna",
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }
        campaign_time.initialize(self.world)
        chat.return_value = {"message": {"content": json.dumps({
            "narration": self.unsafe_response,
            "world_updates": {"create_locations": [{
                "key": "l1", "name": "Sessiz Avlu", "type": "building",
                "description": "Sade bir avlu.", "aliases": ["Sessiz Avlu"],
            }]}, "lore_claims": [],
        })}}
        action = {
            "action": "travel", "status": "awaiting_proposal",
            "success": False, "completion": "completed",
            "target_reference": "Sessiz Avlu", "state_changes": [],
        }
        resolved = game.ResolvedTurn(
            action_result=action, fallback_response="Seyahat hedefi henüz doğrulanmadı.",
            raw_result={"action_result": action, "_engine_event_evidence": {}},
            allow_new_locations=True, lore_context=self.session.lore_authority_context,
        )
        with patch.object(self.session.rng, "randint", return_value=6) as dice:
            result = self.session._narrate_resolved_turn(
                resolved, "Sessiz Avlu'ya gidiyorum.", None, None
            )
        self.assertEqual(action["status"], "completed")
        dice.assert_called_once_with(1, 6)
        self.assertEqual(action["time_result"]["elapsed_seconds"], 300)
        self.assertEqual(action["new_location"], self.world["location"])
        self.assertEqual(result["narration"], self.session._fallback_for_action_result(
            "Sessiz Avlu'ya gidiyorum.", action
        ))
        self.assertEqual(self.session.last_narration_safety["reason_code"], "UNREGISTERED_NAMED_ENTITY")
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 1)
        chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
