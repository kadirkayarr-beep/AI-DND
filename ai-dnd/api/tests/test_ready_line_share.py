"""BM Task 11: the route log records who wrote the narration, and the ready-line share is computed from it."""

from __future__ import annotations

import unittest

import front_proposal
from api.tests import test_front_proposal as front_tests


class ReadyLineShare(unittest.TestCase):
    def test_share_counts_python_sources(self):
        rows = [
            {"narration_source": "qwen", "owner": "dialogue"},
            {"narration_source": "qwen", "owner": "explore"},
            {"narration_source": "deterministic_fallback", "owner": "dialogue"},
            {"narration_source": "python_memory_response", "owner": "narrative"},
            {"narration_source": "deterministic_system", "owner": "shop_economy"},
        ]
        # spec 5.9: the denominator is every player row; engine-owned rows are never ready lines
        self.assertEqual(front_proposal.ready_line_share(rows),
                         {"moves": 5, "ready": 2, "share": 0.4, "unknown": 0})

    def test_rows_without_a_source_stay_in_the_count_as_unknown_and_an_empty_log_is_zero(self):
        self.assertEqual(front_proposal.ready_line_share([{"owner": "dialogue"}, {"narration_source": None}]),
                         {"moves": 2, "ready": 0, "share": 0.0, "unknown": 2})
        self.assertEqual(front_proposal.ready_line_share([]), {"moves": 0, "ready": 0, "share": 0.0, "unknown": 0})

    def test_a_turn_without_engine_telemetry_logs_a_python_source(self):
        """I2: an early-return owner (everyday action, gate reply) has no telemetry but a ready line; it must count."""
        class Session:
            world_state = {"flags": {"turn_index": 3}}
        direct = {"narration": "Kapıyı ittin.", "model_calls": 0, "action_result": {"action": "everyday_action"}}
        with self.assertLogs(front_proposal._logger, "INFO") as logs:
            front_proposal.log_turn(Session(), direct)
            front_proposal.log_turn(Session(), {"action_result": {"action": "x"}})
        self.assertIn('"narration_source": "python_direct"', logs.output[0])
        self.assertIn('"narration_source": null', logs.output[1])
        rows = [{"narration_source": "python_direct", "owner": "everyday_action"}, {"narration_source": "qwen", "owner": "dialogue"}]
        self.assertEqual(front_proposal.ready_line_share(rows)["ready"], 1)

    def test_the_shop_presence_line_is_a_ready_line(self):
        self.assertNotIn("shop_inquiry", front_proposal.ENGINE_OWNERS)
        rows = [{"narration_source": "python_direct", "owner": "shop_inquiry"}]
        self.assertEqual(front_proposal.ready_line_share(rows)["ready"], 1)

    def test_a_ready_line_from_a_non_engine_owner_counts(self):
        rows = [{"narration_source": "deterministic_system", "owner": "dialogue"}]
        self.assertEqual(front_proposal.ready_line_share(rows), {"moves": 1, "ready": 1, "share": 1.0, "unknown": 0})

    def test_money_dice_and_rule_owners_are_engine_owned(self):
        for owner in ("shop_economy", "death_save", "skill_check", "attack", "equipment_transaction"):
            self.assertIn(owner, front_proposal.ENGINE_OWNERS)
        self.assertNotIn("dialogue", front_proposal.ENGINE_OWNERS)


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
