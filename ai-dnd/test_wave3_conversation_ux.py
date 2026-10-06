import copy
import json
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

import game
from api.serializers import serialize_session_state


class Wave3ConversationUxTests(unittest.TestCase):
    def fresh(self):
        session = game.create_session(seed=1729)
        world = session.world_state
        world["location"] = "forest"
        world["npcs"] = [
            {
                "id": "npc_aylin", "name": "Aylin", "role": "Tüccar",
                "location": "forest", "tags": [], "name_known_to_player": True,
                "role_known_to_player": True, "armor_class": 10,
                "current_hp": 40, "max_hp": 40,
            },
            {
                "id": "npc_tuna", "name": "Tuna", "role": "Muhafız",
                "location": "forest", "tags": [], "name_known_to_player": True,
                "role_known_to_player": True, "armor_class": 10,
                "current_hp": 40, "max_hp": 40,
            },
        ]
        world["flags"].update({
            "turn_index": 3,
            "active_npc_id": "npc_aylin",
            "last_npc_id": "npc_aylin",
            "active_npc_until_turn": 9,
        })
        return session

    @staticmethod
    def dialogue_packet(text='Aylin, "Seni dinliyorum," der.'):
        return {
            "message": {
                "content": (
                    '{"intent":"dialogue","interaction":{"operation":"none"},'
                    '"world_updates":{},"lore_claims":[],"narration":'
                    + __import__("json").dumps(text, ensure_ascii=False) + '}'
                )
            }
        }

    def test_say_followup_uses_valid_active_interlocutor(self):
        session = self.fresh()
        with patch("game.ollama.chat", return_value=self.dialogue_packet()) as model:
            result = session.run_player_turn("Buralarda yeniyim.", interaction_mode="say")
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["npc_id"], "npc_aylin")
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_aylin")
        self.assertLessEqual(model.call_count, 2)

    def test_say_does_not_turn_hostile_words_into_attack(self):
        session = self.fresh()
        with patch("game.ollama.chat", return_value=self.dialogue_packet('Aylin seni dikkatle dinler.')):
            result = session.run_player_turn("Sana saldıracağımı söyledim.", interaction_mode="say")
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertFalse(session.world_state["combat"]["active"])

    def test_do_explicit_attack_reaches_existing_combat_owner(self):
        session = self.fresh()
        target = session.world_state["npcs"][0]
        target["distance_ft"] = 5
        with patch("game.ollama.chat", side_effect=AssertionError("model used")), \
             patch("game.roll_initiative_player", return_value=20), \
             patch("game.roll_initiative_npc", return_value=1):
            result = session.run_player_turn("Ona sald\u0131r\u0131yorum.", interaction_mode="do")
        self.assertEqual(result["action_result"]["action"], "attack")
        self.assertEqual(result["action_result"]["target_id"], target["id"])
        self.assertTrue(result["action_result"]["combat_started"])
        self.assertTrue(session.world_state["combat"]["active"])
        self.assertIsNone(session.world_state["flags"]["active_npc_id"])

    def test_ask_dm_inventory_never_uses_npc_resolver(self):
        session = self.fresh()
        with patch.object(session, "resolve_npc_reference", side_effect=AssertionError("NPC resolver used")), \
             patch("game.ollama.chat", side_effect=AssertionError("model used")):
            result = session.run_player_turn("Envanterimde neler var?", interaction_mode="ask_dm")
        self.assertEqual(result["action_result"]["action"], "inventory")
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_aylin")

    def test_ask_dm_presence_does_not_become_npc_speech(self):
        session = self.fresh()
        with patch("game.ollama.chat", side_effect=AssertionError("model used")):
            result = session.run_player_turn("Burada kimler var?", interaction_mode="ask_dm")
        self.assertEqual(result["action_result"]["action"], "query")
        self.assertEqual(result["action_result"]["query_type"], "presence")
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_aylin")

    def test_expired_say_target_with_multiple_npcs_requires_clarification(self):
        session = self.fresh()
        session.world_state["flags"]["turn_index"] = 10
        with patch("game.ollama.chat", side_effect=AssertionError("model used")):
            result = session.run_player_turn("Merhaba.", interaction_mode="say")
        self.assertEqual(result["action_result"]["status"], "clarification")
        self.assertFalse(result["action_result"]["success"])

    def test_end_conversation_is_deterministic_and_clears_active_target(self):
        session = self.fresh()
        with patch("game.ollama.chat", side_effect=AssertionError("model used")):
            result = session.run_player_turn("Konuşmayı bitiriyorum.", interaction_mode="do")
        self.assertEqual(result["action_result"]["status"], "conversation_ended")
        self.assertEqual(result["model_calls"], 0)
        self.assertIsNone(session.world_state["flags"]["active_npc_id"])
        self.assertEqual(session.world_state["flags"]["active_npc_until_turn"], -1)

    def test_combat_start_invalidates_active_conversation(self):
        session = self.fresh()
        target = session.world_state["npcs"][0]
        target["distance_ft"] = 5
        with patch("game.roll_initiative_player", return_value=20), \
             patch("game.roll_initiative_npc", return_value=1):
            session.start_combat(target)
        self.assertTrue(session.world_state["combat"]["active"])
        self.assertIsNone(session.world_state["flags"]["active_npc_id"])
        self.assertEqual(session.world_state["flags"]["active_npc_until_turn"], -1)

    def test_say_name_question_learns_identity_through_python_state(self):
        session = self.fresh()
        npc = session.world_state["npcs"][0]
        npc["name"] = "Liora"
        npc["role"] = "Yolcu"
        npc["name_known_to_player"] = False
        npc["role_known_to_player"] = True
        with patch("game.ollama.chat", side_effect=AssertionError("model used")):
            result = session.run_player_turn("Adın ne?", interaction_mode="say")
        self.assertEqual(result["action_result"]["action"], "query")
        self.assertEqual(result["action_result"]["query_type"], "npc_identity")
        self.assertTrue(npc["name_known_to_player"])
        self.assertIn("Liora", result["narration"])
        self.assertEqual(session.world_state["flags"]["active_npc_id"], npc["id"])

    def test_explicit_say_target_switches_active_interlocutor(self):
        session = self.fresh()
        with patch("game.ollama.chat", return_value=self.dialogue_packet('Tuna, "Seni dinliyorum," der.')):
            result = session.run_player_turn(
                "Merhaba.", interaction_mode="say", target_id="npc_tuna"
            )
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["npc_id"], "npc_tuna")
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_tuna")
        self.assertEqual(session.world_state["flags"]["last_npc_id"], "npc_tuna")

    def test_ask_dm_historical_question_does_not_become_npc_memory(self):
        session = self.fresh()
        before_npcs = copy.deepcopy(session.world_state["npcs"])
        before_target = session.world_state["flags"]["active_npc_id"]
        with patch("game.ollama.chat", side_effect=AssertionError("history question used model")):
            result = session.run_player_turn("Aylin daha önce bana ejderhadan bahsetmişti.", interaction_mode="ask_dm")
        self.assertEqual(session.world_state["npcs"], before_npcs)
        self.assertEqual(session.world_state["flags"]["active_npc_id"], before_target)
        self.assertEqual(result["action_result"]["status"], "unverified")
        with patch("game.ollama.chat", side_effect=AssertionError("NPC memory used model")):
            spoken = session.run_player_turn("Aylin daha \u00f6nce bana ejderhadan bahsetmi\u015fti.", interaction_mode="say")
        self.assertEqual(spoken["action_result"]["npc_id"], "npc_aylin")
        self.assertEqual(len(session.world_state["npcs"][0]["memory"]), 2)

    def test_say_explicit_name_or_role_wins_over_previous_interlocutor(self):
        for text in ("Tuna, buralarda yeniyim.", "Muhaf\u0131z, buralarda yeniyim."):
            with self.subTest(text=text):
                session = self.fresh()
                with patch("game.ollama.chat", return_value=self.dialogue_packet('Tuna seni dinliyor.')):
                    result = session.run_player_turn(text, interaction_mode="say")
                self.assertEqual(result["action_result"]["npc_id"], "npc_tuna")
                self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_tuna")

    def test_say_cannot_select_hidden_or_remote_npc(self):
        for change in ({"hidden": True}, {"location": "tavern"}):
            with self.subTest(change=change):
                session = self.fresh()
                session.world_state["npcs"][0].update(change)
                with patch("game.ollama.chat", side_effect=AssertionError("invalid addressee used model")):
                    result = session.run_player_turn("Merhaba.", interaction_mode="say", target_id="npc_aylin")
                self.assertEqual(result["action_result"]["status"], "clarification")
                self.assertFalse(result["action_result"]["success"])
                self.assertFalse(serialize_session_state(session)["conversation"]["active"])

    def test_say_attack_words_and_model_intent_remain_speech(self):
        for text in ("Ona sald\u0131r\u0131yorum.", "Muhaf\u0131za sald\u0131r\u0131yorum."):
            with self.subTest(text=text):
                session = self.fresh()
                before_hp = [npc["current_hp"] for npc in session.world_state["npcs"]]
                packet = self.dialogue_packet()
                raw = json.loads(packet["message"]["content"])
                raw["intent"] = "attack"
                packet["message"]["content"] = json.dumps(raw)
                with patch("game.ollama.chat", return_value=packet) as model:
                    result = session.run_player_turn(text, interaction_mode="say")
                self.assertEqual(result["action_result"]["action"], "dialogue")
                self.assertFalse(session.world_state["combat"]["active"])
                self.assertEqual([npc["current_hp"] for npc in session.world_state["npcs"]], before_hp)
                self.assertLessEqual(model.call_count, 2)

    def test_say_wait_is_speech_without_advancing_time(self):
        session = self.fresh()
        session.ensure_campaign_clock()
        before = session.world_state["campaign_time"]["elapsed_seconds"]
        with patch("game.ollama.chat", return_value=self.dialogue_packet()):
            result = session.run_player_turn("Bir dakika bekliyorum.", interaction_mode="say")
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before)

    def test_ask_dm_does_not_execute_wait_or_record_compound_plan(self):
        for text in ("Bir dakika bekliyorum.", "Biraz bekleyeyim; kap\u0131y\u0131 a\u00e7ay\u0131m."):
            with self.subTest(text=text):
                session = self.fresh()
                session.ensure_campaign_clock()
                before_clock = copy.deepcopy(session.world_state["campaign_time"])
                before_plan = copy.deepcopy(session.world_state.get("interaction_adventure_v1", {}).get("plan"))
                with patch("game.ollama.chat", side_effect=AssertionError("question used model")):
                    result = session.run_player_turn(text, interaction_mode="ask_dm")
                self.assertEqual(result["action_result"]["status"], "unverified")
                self.assertEqual(session.world_state["campaign_time"], before_clock)
                self.assertEqual(session.world_state.get("interaction_adventure_v1", {}).get("plan"), before_plan)

    def test_say_without_local_target_clarifies_without_model(self):
        for target_id in (None, "npc_missing"):
            with self.subTest(target_id=target_id):
                session = self.fresh()
                session.world_state["npcs"] = []
                with patch("game.ollama.chat", side_effect=AssertionError("no addressee")):
                    result = session.run_player_turn("Buralarda yeniyim.", interaction_mode="say", target_id=target_id)
                self.assertEqual(result["action_result"]["action"], "dialogue")
                self.assertFalse(result["action_result"]["success"])
                self.assertIn(result["action_result"]["status"], ("clarification", "invalid_target"))

    def test_ask_dm_ignores_target_and_cannot_end_conversation(self):
        session = self.fresh()
        with patch("game.ollama.chat", side_effect=AssertionError("question used model")):
            result = session.run_player_turn("Konusmayi bitiriyorum.", interaction_mode="ask_dm", target_id="npc_missing")
        self.assertNotEqual(result["action_result"]["status"], "conversation_ended")
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_aylin")

    def test_speech_modes_do_not_bypass_active_combat_owner(self):
        session = self.fresh()
        target = session.world_state["npcs"][0]
        target["distance_ft"] = 5
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative_npc", return_value=1):
            session.start_combat(target)
        before = copy.deepcopy(session.world_state)
        before_rng = session.rng.getstate()
        for mode in ("say", "ask_dm"):
            with self.subTest(mode=mode), patch("game.ollama.chat", side_effect=AssertionError("combat used model")):
                with self.assertRaises(game.combat_lifecycle.CombatRequestError):
                    session.run_player_turn("Envanterimde neler var?", interaction_mode=mode)
                self.assertEqual(session.world_state, before)
                self.assertEqual(session.rng.getstate(), before_rng)

    def test_unconscious_player_cannot_use_conversation_shortcuts(self):
        for text, mode in (("Konusmayi bitiriyorum.", "do"), ("Envanterimde neler var?", "ask_dm")):
            with self.subTest(text=text, mode=mode):
                session = self.fresh()
                session.character["current_hp"] = 0
                session.world_state["player_combat_status"] = "unconscious"
                with patch("game.ollama.chat", side_effect=AssertionError("unconscious speech")):
                    with self.assertRaises(ValueError):
                        session.run_player_turn(text, interaction_mode=mode)
                self.assertEqual(session.world_state["flags"]["active_npc_id"], "npc_aylin")

    def test_do_compound_sequence_reuses_existing_bounded_plan_owner(self):
        session = self.fresh()
        before_location = session.world_state["location"]
        before_doors = list(session.world_state["doors"])
        text = "Biraz bekleyeyim; kap\u0131y\u0131 a\u00e7ay\u0131m."
        with patch("game.ollama.chat", return_value={"message": {"content": "{}"}}):
            result = session.run_player_turn(text, interaction_mode="do")
        self.assertEqual(result["action_result"]["action"], "interaction")
        self.assertEqual(result["action_result"]["operation"], "plan")
        self.assertEqual(result["action_result"]["status"], "recorded")
        plan = session.world_state["interaction_adventure_v1"]["plan"]
        self.assertEqual(plan["status"], "awaiting_confirmation")
        self.assertEqual(plan["cursor"], 0)
        self.assertEqual(session.world_state["location"], before_location)
        self.assertEqual(session.world_state["doors"], before_doors)

    def test_active_conversation_survives_save_reload_with_existing_world_state_owner(self):
        session = self.fresh()
        expected = serialize_session_state(session)["conversation"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wave3-conversation.json"
            session.save_game(path)
            reopened = game.create_session(seed=99)
            reopened.load_game(path)
        self.assertEqual(serialize_session_state(reopened)["conversation"], expected)
        self.assertEqual(reopened.world_state["flags"]["active_npc_id"], "npc_aylin")

    def test_active_conversation_is_session_isolated(self):
        first = self.fresh()
        second = game.create_session(seed=99)
        self.assertTrue(serialize_session_state(first)["conversation"]["active"])
        self.assertFalse(serialize_session_state(second)["conversation"]["active"])
        self.assertIsNone(second.world_state["flags"].get("active_npc_id"))

    def test_public_conversation_projection_hides_unknown_canonical_name(self):
        session = self.fresh()
        npc = session.world_state["npcs"][0]
        npc["name"] = "Liora"
        npc["name_known_to_player"] = False
        npc["role_known_to_player"] = True
        state = serialize_session_state(session)
        conversation = state["conversation"]
        self.assertTrue(conversation["active"])
        self.assertEqual(conversation["interlocutor"]["id"], "npc_aylin")
        self.assertNotEqual(conversation["interlocutor"]["name"], "Liora")
        self.assertNotIn("Liora", str(conversation))


if __name__ == "__main__":
    unittest.main()
