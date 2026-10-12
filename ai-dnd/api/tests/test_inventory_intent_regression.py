"""Regression: concrete item movement must outrank abstract abandonment.

Fresh isolated sessions; no persisted campaign or real model.
"""
import unittest
from unittest.mock import patch

from api.tests.test_stage10a_gameplay_repairs import city_session


class InventoryIntentRegression(unittest.TestCase):
    def test_sword_drop_paraphrases_move_the_same_canonical_item(self):
        for seed, message in enumerate((
            "Kılıcımı bırakıyorum.",
            "Kılıcımı yere bırakıyorum.",
            "Kılıcımı yere koyuyorum.",
            "Kılıcımı yere atıyorum.",
        ), start=870):
            with self.subTest(message=message):
                session = city_session(seed=seed)
                self.assertIn("Kılıç", session.world_state["inventory"])
                with patch("game.ollama.chat", side_effect=AssertionError("No model needed")):
                    result = session.run_player_turn(message, interaction_mode="do")
                self.assertEqual(result["action_result"]["action"], "inventory")
                self.assertNotIn("Kılıç", session.world_state["inventory"])
                location = session.world_state["location"]
                self.assertIn("Kılıç", session.world_state["ground_items_by_location"][location])
                self.assertNotIn("geri döner", result["narration"].casefold())
                self.assertLessEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 2)

    def test_sword_pickup_cannot_narrate_uncommitted_movement(self):
        session = city_session(seed=880)
        location = session.world_state["location"]
        session.world_state["inventory"].remove("Kılıç")
        session.world_state.setdefault("ground_items_by_location", {}).setdefault(location, []).append("Kılıç")
        with patch("game.ollama.chat", side_effect=AssertionError("No model needed")):
            result = session.run_player_turn("Kılıcı yerden alıyorum.", interaction_mode="do")
        self.assertEqual(result["action_result"]["action"], "inventory")
        self.assertIn("Kılıç", session.world_state["inventory"])
        self.assertNotIn("Kılıç", session.world_state["ground_items_by_location"][location])


if __name__ == "__main__":
    unittest.main()
