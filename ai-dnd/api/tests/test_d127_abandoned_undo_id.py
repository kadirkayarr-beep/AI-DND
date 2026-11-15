"""D-127 / ORTA-20: an undo action id the player closed for good (abandon) can never be applied later.

A campaign already refuses it inside the commit transaction. A transient session kept no such check: the undo route
looked only for a success receipt, so the closed id later undid the turn and gathered a refusal and a receipt at once.
"""

from __future__ import annotations

import unittest
import uuid

from api.tests import test_persistence_idempotency as idempotency
from api.tests import test_roadmap_r04_commit_boundary as r04  # module import: its tests are not re-collected here
from api.tests.town_seed import fixed_town


class AbandonedUndoIdStaysClosed(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 12701):
            await r04.CommitBoundaryTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    prepare_spell = idempotency.PersistenceIdempotencyTests.prepare_spell

    async def check(self, session_id):
        # A deterministic engine turn (one spell in combat): it needs no model and sets the one-step undo point.
        record, command = self.prepare_spell({"session_id": session_id})
        turn_id, undo_id = command["action_id"], str(uuid.uuid4())
        turn = await self.http.post(f"/api/game/sessions/{session_id}/turn", json=command)
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual((record.undo_checkpoint or {}).get("action_id"), turn_id)
        closed = await self.http.post(f"/api/game/sessions/{session_id}/actions/{undo_id}/abandon")
        self.assertEqual(closed.status_code, 200, closed.text)
        before = record.game_session.serialize_game_state()

        late = await self.http.post(f"/api/game/sessions/{session_id}/undo",
                                    json={"action_id": undo_id, "target_action_id": turn_id})
        self.assertEqual(late.status_code, 409, late.text)
        self.assertEqual(late.json()["detail"]["code"], "action_abandoned", late.text)
        self.assertEqual(record.game_session.serialize_game_state(), before, "the closed id must not undo the turn")
        self.assertIsNone(self.manager.get_turn_action(record, undo_id), "no success receipt for a closed id")
        status = await self.http.get(f"/api/game/sessions/{session_id}/actions/{undo_id}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["state"], "not_applied", status.text)
        self.assertEqual((record.undo_checkpoint or {}).get("action_id"), turn_id, "a fresh id may still undo")

    async def test_transient_session_refuses_an_abandoned_undo_id(self):
        transient = await self.http.post("/api/game/sessions")
        self.assertEqual(transient.status_code, 200, transient.text)
        self.assertIsNone(self.manager.get(transient.json()["session_id"]).campaign_id)
        await self.check(transient.json()["session_id"])

    async def test_campaign_refuses_an_abandoned_undo_id(self):
        await self.check(self.created["session_id"])

    def test_transient_commit_never_gives_a_refused_id_a_receipt(self):
        """Backstop at the same depth as the campaign store: whichever route got this far, the receipt is refused."""
        from api.persistence.campaign_models import CampaignStaleError

        record = self.manager.create(r04.TEST_PLAYER)[1]
        action_id = str(uuid.uuid4())
        self.manager.abandon_action(record, action_id)
        with record.turn_lock, self.assertRaises(CampaignStaleError):
            self.manager.autosave_turn(record, "x", "y", turn_action_receipt={
                "action_id": action_id, "request_hash": "a" * 64, "response": {}})
        self.assertIsNone(self.manager.get_turn_action(record, action_id))
        self.assertEqual(self.manager.action_state(record, action_id), "not_applied")


if __name__ == "__main__":
    unittest.main()
