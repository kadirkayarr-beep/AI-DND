"""NPC can acknowledge a player introduction and answer a same-turn question."""
import unittest
from unittest.mock import patch

from api.tests.test_stage10a_gameplay_repairs import city_session, place_npc


class CompoundNpcDialogueRegression(unittest.TestCase):
    def test_player_introduction_and_npc_identity_question_both_answered(self):
        session = city_session(seed=990)
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        message = "Ben Astrid. Senin adın ne, ne iş yaparsın?"
        with patch("game.ollama.chat", side_effect=AssertionError("Deterministic")):
            turn = session.run_player_turn(message, target_id="npc_001", interaction_mode="say")
        self.assertIn("Astrid", turn["narration"])
        self.assertIn("Mira", turn["narration"])
        self.assertIn("shopkeeper", turn["narration"])
        self.assertEqual(turn["action_result"]["npc_id"], "npc_001")
        self.assertEqual(turn["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
        first, second = session.world_state["npcs"][-2:]
        self.assertTrue(first.get("name_known_to_player"))
        self.assertFalse(second.get("name_known_to_player", False))
        self.assertEqual(second["memory"], [])


if __name__ == "__main__":
    unittest.main()
