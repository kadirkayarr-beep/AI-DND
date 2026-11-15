"""D-158 / DÜŞ-01: the level-up routes publish the error answers the server gives.
The four level-up operations (GET and POST, canonical and legacy alias) documented only 200, while the server answers
401 (no identity), 404 (unknown session), 409 (campaign_persistence_required, stale preview, refusals, quarantine),
422 (bad body), 500 (level_up_failed) and 503 (campaign storage unavailable) in the ApiError envelope.
"""
from __future__ import annotations
import unittest
import uuid
from api.tests import test_contract_parity as parity  # module import: its tests are not re-collected here
from api.tests import test_spells_v1 as spells  # module import: its tests are not re-collected here
from api.tests.town_seed import fixed_town

LEVEL_UP_PATHS = ("/game/sessions/{session_id}/level-up", "/sessions/{session_id}/level-up")
EXPECTED = {
    "get": {"200", "401", "404", "409", "500", "503"},
    "post": {"200", "401", "404", "409", "422", "500", "503"},
}
REFS = {
    "401": "#/components/responses/AuthenticationRequired",
    "404": "#/components/responses/ApiError",
    "409": "#/components/responses/ApiError",
    "422": "#/components/responses/RequestValidationError",
    "500": "#/components/responses/ApiError",
    "503": "#/components/responses/ApiError",
}


class LevelUpErrorContract(unittest.TestCase):
    def test_every_level_up_operation_documents_its_error_answers(self):
        for path in LEVEL_UP_PATHS:
            for method, expected in EXPECTED.items():
                with self.subTest(path=path, method=method):
                    responses = parity._operation(path, method)["responses"]
                    self.assertEqual({str(status) for status in responses}, expected)
                    for status in expected - {"200"}:
                        self.assertEqual(responses[status], {"$ref": REFS[status]}, status)


class LevelUpErrorAnswersAreDocumented(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = spells.SpellApiTests.asyncSetUp
    asyncTearDown = spells.SpellApiTests.asyncTearDown

    async def test_real_error_answers_are_published_statuses(self):
        with fixed_town(self, 11158):
            created = await self.http.post("/api/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        body = {"action_id": str(uuid.uuid4()), "campaign_id": str(uuid.uuid4()), "expected_revision": 0,
                "target_level": 2, "choices": {}}
        answers = (
            ("get", "/api/game/sessions/{}/level-up".format(uuid.uuid4()), None, 404),
            ("post", f"/api/game/sessions/{session_id}/level-up", body, 409),  # campaign_persistence_required
            ("post", f"/api/game/sessions/{session_id}/level-up", {"action_id": "x"}, 422),
        )
        for method, url, payload, status in answers:
            with self.subTest(method=method, status=status):
                response = await self.http.request(method.upper(), url, json=payload)
                self.assertEqual(response.status_code, status, response.text)
                published = parity._operation("/game/sessions/{session_id}/level-up", method)["responses"]
                self.assertIn(str(status), published)


if __name__ == "__main__":
    unittest.main()
