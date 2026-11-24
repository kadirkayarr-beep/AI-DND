"""A final turn answered without a narrator still counts the model calls the incident door spent."""

import unittest
from unittest.mock import patch

import game
from api.tests.town_seed import fixed_town


class FinalSkippedIncidentCallsTests(unittest.TestCase):
    def _telemetry(self, spent):
        with fixed_town(self, 9601):
            session = game.create_session(seed=1729)
        session.world_state["location"] = "tavern"
        with patch("incidents.hooks.before_narration", return_value={"model_calls": spent}) as door, \
                patch("game.ollama.chat", side_effect=AssertionError("no model in this test")):
            result = session.run_player_turn("Uyuyorum.", interaction_mode="do")
        self.assertTrue(door.called)
        return result["_engine_event_evidence"]["telemetry"]

    def test_incident_model_calls_reach_the_final_turn_telemetry(self):
        quiet = self._telemetry(0)
        busy = self._telemetry(2)
        self.assertEqual(busy["narration_model_calls"] - quiet["narration_model_calls"], 2, (quiet, busy))
        self.assertEqual(busy["total_model_calls"] - quiet["total_model_calls"], 2, (quiet, busy))


if __name__ == "__main__":
    unittest.main()
