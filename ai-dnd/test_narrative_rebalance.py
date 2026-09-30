import unittest
import copy
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import game
import local_dialogue


class TestNarrativeRebalance(unittest.TestCase):
    def setUp(self):
        game.initialize_game(creation_choice="1", print_fn=lambda x: None, input_fn=lambda x: "1")
        self.session = game._DEFAULT_SESSION
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
        self.assertEqual(telemetry["intent_source"], "deterministic")
        self.assertEqual(telemetry["narration_source"], "qwen")

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
        self.assertEqual(telemetry["fallback_reason"], "UNVERIFIED_LORE_CLAIM")
        self.assertEqual(telemetry["narration_source"], "deterministic_fallback")

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

    # 17. model-generated prose alone cannot create canonical memory
    @patch("game.ollama.chat")
    def test_17_model_generated_prose_alone_cannot_create_canonical_memory(self, mock_chat):
        mock_chat.return_value = self.mock_ollama_response(
            '{"valid_response": true, "narration": "Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor.", "world_updates": {"update_npcs": [{"id": "npc_barkeep", "relationship": "allied"}]}}'
        )
        self.session.world_state["npcs"][0]["relationship"] = "neutral"
        self.session.run_player_turn("Hancı, buralarda neler dönüyor?")
        npc = self.session.world_state["npcs"][0]
        self.assertEqual(npc.get("relationship"), "neutral")
        self.assertEqual(len(npc.get("knowledge", [])), 0)


if __name__ == "__main__":
    unittest.main()