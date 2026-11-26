"""D-159 review: every body that stores an action receipt takes a UUIDv4 action id, like the status route reads.
The status and abandon routes read only UUIDv4 ids (D-159), turns and species actions take only UUIDv4 (D-111) and
spell preparation too (D-193). The Undo body (`TurnUndoRequest.action_id`) still took any UUID: a uuid1 Undo was
applied and its receipt stored, but the status of that same id answered 422. `target_action_id` names an action
already stored, so it is not narrowed. The level-up body already refused a non-UUIDv4 id (and campaign id), but the
published `LevelUpApplyRequest` did not say so (D-158: the identity requirement missing from the contract).
"""
from __future__ import annotations
import re
import unittest
import uuid
from pydantic import ValidationError
from api.schemas import LevelUpApplyRequest, TurnUndoRequest
from api.tests import test_contract_parity as parity  # module import: its tests are not re-collected here
from api.tests import test_spells_v1 as spells  # module import: its tests are not re-collected here
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.town_seed import fixed_town

UUID4_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
ACCEPTED = [f"12345678-9abc-4def-{variant}123-456789abcdef" for variant in "89ab"]
REJECTED = [f"12345678-9abc-{version}def-8123-456789abcdef" for version in "01235678"]
REJECTED += [f"12345678-9abc-4def-{variant}123-456789abcdef" for variant in "07cf"]
REJECTED.append(str(uuid.uuid1()))


def level_up_body(action_id: str) -> dict:
    return {"action_id": action_id, "campaign_id": str(uuid.uuid4()), "expected_revision": 0, "target_level": 2,
            "choices": {}}


class ActionIdModels(unittest.TestCase):
    def test_published_patterns_are_the_uuid4_pattern(self):
        self.assertEqual(parity._schema("GameTurnUndoInput")["properties"]["action_id"].get("pattern"), UUID4_PATTERN)
        for field in ("action_id", "campaign_id"):
            with self.subTest(field=field):
                self.assertEqual(parity._schema("LevelUpApplyRequest")["properties"][field].get("pattern"), UUID4_PATTERN)

    def test_undo_action_id_takes_only_uuid4_and_the_target_any_uuid(self):
        old_target = str(uuid.uuid1())
        for action_id in ACCEPTED:
            with self.subTest(accepted=action_id):
                parsed = TurnUndoRequest(action_id=action_id, target_action_id=old_target)
                self.assertEqual((str(parsed.action_id), str(parsed.target_action_id)), (action_id, old_target))
                self.assertIsNotNone(re.fullmatch(UUID4_PATTERN, action_id))
        for action_id in REJECTED:
            with self.subTest(rejected=action_id):
                with self.assertRaisesRegex(ValidationError, "Action ID must be a UUIDv4"):
                    TurnUndoRequest(action_id=action_id, target_action_id=str(uuid.uuid4()))
                self.assertIsNone(re.fullmatch(UUID4_PATTERN, action_id))

    def test_level_up_action_id_takes_only_uuid4(self):
        for action_id in ACCEPTED:
            with self.subTest(accepted=action_id):
                self.assertEqual(str(LevelUpApplyRequest.model_validate(level_up_body(action_id)).action_id), action_id)
        for action_id in REJECTED:
            with self.subTest(rejected=action_id):
                with self.assertRaisesRegex(ValidationError, "A UUID4 identity is required"):
                    LevelUpApplyRequest.model_validate(level_up_body(action_id))
                self.assertIsNone(re.fullmatch(UUID4_PATTERN, action_id))


class ActionIdHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = spells.SpellApiTests.asyncSetUp
    asyncTearDown = spells.SpellApiTests.asyncTearDown

    async def session_id(self, seed: int) -> str:
        with fixed_town(self, seed):
            created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["session_id"]

    async def test_uuid1_undo_and_level_up_are_refused_and_store_nothing(self):
        session_id = await self.session_id(11161)
        record = self.manager.get(session_id, principal=TEST_PLAYER)
        bad = str(uuid.uuid1())
        calls = (
            ("undo", f"/api/game/sessions/{session_id}/undo",
             {"action_id": bad, "target_action_id": str(uuid.uuid4())}),
            ("level-up", f"/api/game/sessions/{session_id}/level-up", level_up_body(bad)),
        )
        for name, url, body in calls:
            with self.subTest(route=name):
                response = await self.http.post(url, json=body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIsInstance(response.json().get("detail"), list, response.text)
        self.assertEqual(dict(record.refused_actions), {}, "a uuid1 id must not be stored as a refusal")
        self.assertIsNone(self.manager.get_turn_action(record, bad))
        status = await self.http.get(f"/api/game/sessions/{session_id}/actions/{bad}")
        self.assertEqual(status.status_code, 422, status.text)  # the status route reads the same rule


if __name__ == "__main__":
    unittest.main()
