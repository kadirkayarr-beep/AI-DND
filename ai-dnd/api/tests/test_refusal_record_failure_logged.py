"""Every route that fails to store a refusal record logs it the same way (desloppify: refusal_record_failure).

The turn route logged a failed record_refused_action at error level; the level-up route swallowed it silently. All
sites now go through one helper: log at error level with the traceback, make no never-applied claim.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch
from api.tests import test_d158_level_up_error_contract as contract  # module import: its tests are not re-collected


class LevelUpRefusalRecordFailureIsLogged(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.LevelUpCampaignErrorBodies.asyncSetUp
    asyncTearDown = contract.LevelUpCampaignErrorBodies.asyncTearDown
    boot = contract.LevelUpCampaignErrorBodies.boot
    counted_turn = contract.LevelUpCampaignErrorBodies.counted_turn
    level_up_body = contract.LevelUpCampaignErrorBodies.level_up_body

    async def test_a_level_up_refusal_that_cannot_be_stored_is_logged_and_makes_no_claim(self):
        url = f"/api/game/sessions/{self.session_id}/level-up"
        revision = (await self.http.get(url)).json()["revision"]
        with patch.object(self.manager, "record_refused_action", side_effect=RuntimeError("disk full")):
            with self.assertLogs("ai_dnd.api", "ERROR") as logged:
                response = await self.http.post(url, json=self.level_up_body(revision + 1000))
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "level_up_preview_stale")
        self.assertNotIn("not_applied", detail, "no durable record, no never-applied claim")
        self.assertTrue(any("Refusal record could not be saved" in line for line in logged.output), logged.output)


if __name__ == "__main__":
    unittest.main()
