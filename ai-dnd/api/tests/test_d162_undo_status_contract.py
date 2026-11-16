"""D-162 / DÜŞ-05: the action-status read of an Undo id keeps the published GameActionStatus contract.

`response` is "the stored turn reply of an applied action; null when the receipt belongs to another command kind".
An Undo receipt (session_id, action_id, undone_action_id, narration, state) also passed the turn-reply check, so the
status read handed the Undo body out as if it were a GameTurnResult.
"""

from __future__ import annotations

import unittest
import uuid
from pathlib import Path

import yaml

from api.tests import test_d110_undo_after_lost_ack as d110  # module import: its tests are not re-collected here
from api.tests.town_seed import fixed_town
from api.tests import test_roadmap_r04_commit_boundary as r04  # module import: its tests are not re-collected here


class UndoStatusContract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 11162):
            await r04.CommitBoundaryTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    post = r04.CommitBoundaryTests.post
    status = d110.TurnUndoAfterLostAck.status

    def undo(self, action_id, target):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                              json={"action_id": action_id, "target_action_id": target})

    async def test_undo_id_status_is_applied_without_a_turn_reply(self):
        turn_id, undo_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertEqual((await self.post(turn_id)).status_code, 200)
        undone = await self.undo(undo_id, turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        status = (await self.status(undo_id)).json()
        self.assertEqual(status["state"], "applied", status)
        self.assertIsNone(status.get("response"), "an Undo receipt is another command kind, not a GameTurnResult")
        self.assertIs(status.get("undo_available"), False, status)
        # The Undo answer itself is untouched: replaying the same id still returns the stored Undo body.
        replay = await self.undo(undo_id, turn_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["undone_action_id"], turn_id)

    async def test_turn_id_status_still_carries_its_turn_reply_in_the_contract_shape(self):
        turn_id = str(uuid.uuid4())
        self.assertEqual((await self.post(turn_id)).status_code, 200)
        reply = (await self.status(turn_id)).json().get("response")
        self.assertIsInstance(reply, dict, "a turn's own status keeps its stored reply")
        self.assertEqual(reply["action_id"], turn_id)
        spec = yaml.safe_load((Path(__file__).resolve().parents[3] / "lib" / "api-spec" / "openapi.yaml")
                              .read_text(encoding="utf-8"))
        documented = set(spec["components"]["schemas"]["GameTurnResult"]["properties"])
        self.assertEqual(set(reply) - documented, set(), "status reply fields missing from GameTurnResult")


if __name__ == "__main__":
    unittest.main()
