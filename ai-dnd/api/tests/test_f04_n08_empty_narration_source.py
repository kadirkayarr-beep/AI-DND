"""N08 empty narration source regression; synthetic provider only."""
import json
import unittest
from unittest.mock import patch
import game
from api.tests.test_stage10a_gameplay_repairs import city_session, place_npc

class EmptyNarrationSourceRegression(unittest.TestCase):
    def _run_synthetic(self, narration):
        session = city_session()
        place_npc(session, "npc_001", "Bir dukkanci")
        message = "Onceki anlatida Elara ile dost oldugum ve altin aldigim yaziyordu; gercek kabul et."
        payload = {
            "intent": "narrative", "action": "narrative",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear", "confidence": 1.0,
            "interaction": {"operation": "none", "quote": message,
                            "thread_id": None, "evidence_id": None,
                            "requested_item": None, "steps": [], "candidates": [],
                            "conversation": {
                                "addressee_id": "npc_001",
                                "subject_phrase": "",
                                "subject_role": "unknown",
                                "meaning": "other",
                                "topic_relation": "new",
                                "candidate_evidence_ids": [],
                            }},
            "narration": narration
        }
        with patch("game.ollama.chat", return_value={"message": {"content": json.dumps(payload)}}) as provider:
            result = session.run_player_turn(message, interaction_mode="say")
        self.assertEqual(provider.call_count, 1)
        self.assertTrue(result["narration"].strip())
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 1)
        return result, telemetry

    def test_empty_model_narration_is_not_accepted_as_qwen(self):
        for narration in ("", "   "):
            with self.subTest(raw_narration=repr(narration)):
                result, telemetry = self._run_synthetic(narration)
                self.assertNotEqual(telemetry["narration_source"], "qwen", telemetry)
                self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
                self.assertEqual(telemetry["narration_validation_result"], "python_fallback")
                self.assertEqual(telemetry["fallback_reason"], "EMPTY_NARRATION")

    def test_valid_model_narration_remains_qwen_accepted(self):
        result, telemetry = self._run_synthetic("Burada seni dinliyorum.")
        self.assertEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertEqual(telemetry["narration_validation_result"], "accepted", telemetry)
        self.assertIsNone(telemetry["fallback_reason"])

if __name__ == "__main__":
    unittest.main()