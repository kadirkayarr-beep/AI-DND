"""BM Task 11: the route log records who wrote the narration."""

from __future__ import annotations

import unittest

import front_proposal
from api.tests import test_front_proposal as front_tests


class ReadyLineShare(unittest.TestCase):
    def test_a_turn_without_engine_telemetry_logs_a_python_source(self):
        """I2: an early-return owner (everyday action, gate reply) has no telemetry but a ready line; its source must still be logged."""
        class Session:
            world_state = {"flags": {"turn_index": 3}}
        direct = {"narration": "Kapıyı ittin.", "model_calls": 0, "action_result": {"action": "everyday_action"}}
        with self.assertLogs(front_proposal._logger, "INFO") as logs:
            front_proposal.log_turn(Session(), direct)
            front_proposal.log_turn(Session(), {"action_result": {"action": "x"}})
        self.assertIn('"narration_source": "python_direct"', logs.output[0])
        self.assertIn('"narration_source": null', logs.output[1])


class GuidanceTellsJobDecisions(unittest.TestCase):
    def test_guidance_says_wage_matter_and_take_up_need_work_or_a_job_id(self):
        """I3: with a reading the job gate only runs for asks=work or a job id; the model has to be told so."""
        text = front_proposal.guidance({"offers": [], "people": [], "places": [], "things": [], "items": [], "wants": [], "jobs": [], "bag": []})
        self.assertIn("ücret, dert ve üstlenme kararı yalnız work ya da job_id ile verilir", text)


class LogTurnWritesSource(front_tests.FrontTable):
    async def test_log_turn_writes_source(self):
        await self.begin()
        await self.line("etrafa şöyle bir göz atayım")
        row = self.routes()[-1]
        self.assertIn("narration_source", row)
        self.assertIn("model_calls", row)
        self.assertIsInstance(row["model_calls"], int)
        self.assertIn(row["narration_source"], {"qwen", "python_memory_response", "deterministic_fallback",
                                                "deterministic_system", None})
        self.assertIsNotNone(row["narration_source"])  # a say turn reports its source in the engine telemetry


if __name__ == "__main__":
    unittest.main()
