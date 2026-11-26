"""D-159 / DÜŞ-02: the action-status read and abandon routes validate the action id as the contract says.

The published path parameter is ``format: uuid`` and a bad path parameter answers 422 RequestValidationError. A
temporary (no campaign) session answered ``200 {"action_id": "not-a-uuid", "state": "unknown"}`` (and abandon even
stored a refusal under the junk id), which the GameActionStatus schema rejects; a campaign session answered 500.
Turn bodies already require a UUIDv4 (D-111), so the same rule holds here.
"""

from __future__ import annotations

import unittest
import uuid

from api.tests import test_spells_v1 as spells  # module import: its tests are not re-collected here
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.town_seed import fixed_town
from api.tests import test_roadmap_r04_commit_boundary as r04  # module import: its tests are not re-collected here

BAD_IDS = ("not-a-uuid", str(uuid.uuid1()))


class TemporarySessionActionIdContract(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = spells.SpellApiTests.asyncSetUp
    asyncTearDown = spells.SpellApiTests.asyncTearDown

    async def session_id(self):
        with fixed_town(self, 11159):
            created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["session_id"]

    async def test_status_of_a_bad_id_is_a_request_validation_error(self):
        session_id = await self.session_id()
        for bad in BAD_IDS:
            with self.subTest(bad=bad):
                response = await self.http.get(f"/api/game/sessions/{session_id}/actions/{bad}")
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIsInstance(response.json().get("detail"), list, response.text)

    async def test_abandon_of_a_bad_id_is_refused_and_stores_nothing(self):
        session_id = await self.session_id()
        record = self.manager.get(session_id, principal=TEST_PLAYER)
        for bad in BAD_IDS:
            with self.subTest(bad=bad):
                response = await self.http.post(f"/api/game/sessions/{session_id}/actions/{bad}/abandon")
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIsInstance(response.json().get("detail"), list, response.text)
        self.assertEqual(dict(record.refused_actions), {}, "a bad id must not be stored as a refusal")

    async def test_a_valid_unknown_id_still_answers_unknown(self):
        session_id = await self.session_id()
        good = str(uuid.uuid4())
        response = await self.http.get(f"/api/game/sessions/{session_id}/actions/{good}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"action_id": good, "state": "unknown"})

    async def test_an_upper_case_id_reads_the_same_action_as_a_turn_body_would(self):
        # A turn body's UUID is stored lower case (str(UUID)); the status read of the same id must find that record.
        session_id = await self.session_id()
        good = str(uuid.uuid4())
        closed = await self.http.post(f"/api/game/sessions/{session_id}/actions/{good}/abandon")
        self.assertEqual(closed.status_code, 200, closed.text)
        response = await self.http.get(f"/api/game/sessions/{session_id}/actions/{good.upper()}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["action_id"], response.json()["state"]), (good, "not_applied"))


class CampaignSessionActionIdContract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 11160):
            await r04.CommitBoundaryTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    async def test_status_and_abandon_of_a_bad_id_are_request_validation_errors(self):
        session_id = self.created["session_id"]
        for bad in BAD_IDS:
            with self.subTest(bad=bad):
                status = await self.http.get(f"/api/game/sessions/{session_id}/actions/{bad}")
                self.assertEqual(status.status_code, 422, status.text)
                abandon = await self.http.post(f"/api/game/sessions/{session_id}/actions/{bad}/abandon")
                self.assertEqual(abandon.status_code, 422, abandon.text)


if __name__ == "__main__":
    unittest.main()
