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
from api.tests import test_d107_open_action_gate as gate  # module import: its tests are not re-collected here
from api.tests.town_seed import fixed_town

LEVEL_UP_PATHS = ("/game/sessions/{session_id}/level-up", "/sessions/{session_id}/level-up")
EXPECTED = {
    "get": {"200", "401", "404", "409", "500", "503"},
    "post": {"200", "401", "404", "409", "422", "500", "503"},
}
REFS = {
    "401": "#/components/responses/AuthenticationRequired",
    "404": "#/components/responses/ApiError",
    "409": "#/components/responses/LevelUpError",
    "422": "#/components/responses/RequestValidationError",
    "500": "#/components/responses/LevelUpError",
    "503": "#/components/responses/ApiError",
}


def _resolve(node):
    while isinstance(node, dict) and "$ref" in node:
        target = parity.SPEC
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def body_problems(schema, value, where="body"):
    """Minimal OpenAPI check (jsonschema is not installed): type, required, additionalProperties, enum, anyOf."""
    schema = _resolve(schema)
    if "anyOf" in schema:
        found = [body_problems(option, value, where) for option in schema["anyOf"]]
        return [] if any(not item for item in found) else sum(found, [])
    problems = []
    kind = schema.get("type")
    checks = {"object": dict, "string": str, "boolean": bool, "integer": int, "array": list}
    if kind in checks and not isinstance(value, checks[kind]):
        return [f"{where}: expected {kind}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{where}: {value!r} not in enum")
    if kind == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{where}: missing required {key}")
        for key, item in value.items():
            if key in properties:
                problems += body_problems(properties[key], item, f"{where}.{key}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{where}: unexpected property {key}")
    return problems


def published_body_problems(path, method, status, body):
    response = _resolve(parity._operation(path, method)["responses"][status])
    return body_problems(response["content"]["application/json"]["schema"], body)


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
                if status != 422:
                    self.assertEqual(published_body_problems("/game/sessions/{session_id}/level-up", method, str(status),
                                                             response.json()), [], response.text)

    def test_server_literal_500_body_fits(self):
        body = {"detail": {"code": "level_up_failed", "message": "Seviye seçimi güvenle kaydedilemedi."}}
        for path in LEVEL_UP_PATHS:
            self.assertEqual(published_body_problems(path, "post", "500", body), [])


class LevelUpCampaignErrorBodies(unittest.IsolatedAsyncioTestCase):
    """Campaign-backed answers: stale preview and an open earlier action fit the published schema."""
    asyncSetUp = gate.OpenActionGateTests.asyncSetUp
    asyncTearDown = gate.OpenActionGateTests.asyncTearDown
    boot = gate.OpenActionGateTests.boot
    counted_turn = gate.OpenActionGateTests.counted_turn
    body = gate.OpenActionGateTests.body
    turn = gate.OpenActionGateTests.turn
    leave_open_by_outage = gate.OpenActionGateTests.leave_open_by_outage

    def level_up_body(self, revision):
        return {"action_id": str(uuid.uuid4()), "campaign_id": self.campaign_id, "expected_revision": revision,
                "target_level": 2, "choices": {}}

    async def test_stale_preview_body_fits(self):
        url = f"/api/game/sessions/{self.session_id}/level-up"
        revision = (await self.http.get(url)).json()["revision"]
        response = await self.http.post(url, json=self.level_up_body(revision + 1000))
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual((detail["code"], detail.get("not_applied")), ("level_up_preview_stale", True))
        self.assertEqual(published_body_problems("/game/sessions/{session_id}/level-up", "post", "409",
                                                 response.json()), [], response.text)

    async def test_unresolved_action_body_fits(self):
        await self.leave_open_by_outage(self.body())
        url = f"/api/game/sessions/{self.session_id}/level-up"
        response = await self.http.post(url, json=self.level_up_body(0))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "unresolved_action")
        self.assertEqual(published_body_problems("/game/sessions/{session_id}/level-up", "post", "409",
                                                 response.json()), [], response.text)


if __name__ == "__main__":
    unittest.main()
