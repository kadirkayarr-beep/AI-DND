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
        self.assertEqual(front_proposal.ready_line_share(rows), {"moves": 4, "ready": 2, "share": 0.5})

    def test_rows_without_a_source_are_not_moves_and_an_empty_log_is_zero(self):
        self.assertEqual(front_proposal.ready_line_share([{"owner": "dialogue"}, {"narration_source": None}]),
                         {"moves": 0, "ready": 0, "share": 0.0})
        self.assertEqual(front_proposal.ready_line_share([]), {"moves": 0, "ready": 0, "share": 0.0})

    def test_a_ready_line_from_a_non_engine_owner_counts(self):
        rows = [{"narration_source": "deterministic_system", "owner": "dialogue"}]
        self.assertEqual(front_proposal.ready_line_share(rows), {"moves": 1, "ready": 1, "share": 1.0})

    def test_money_dice_and_rule_owners_are_engine_owned(self):
        for owner in ("shop_economy", "death_save", "skill_check", "attack", "equipment_transaction"):
            self.assertIn(owner, front_proposal.ENGINE_OWNERS)
        self.assertNotIn("dialogue", front_proposal.ENGINE_OWNERS)


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
