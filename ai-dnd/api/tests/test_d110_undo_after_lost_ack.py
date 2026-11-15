"""D-110 / YÜK-05: a move the database committed keeps its one-step undo, whatever happened to its answer.

Two ways the answer goes missing. (1) The store raises after the commit (committed_unconfirmed): the live runtime adopts
the committed revision, and must adopt the move's undo point with it. (2) Only the HTTP reply is lost: the server holds
the undo point, and the action-status read must say so, so the screen can keep the undo button instead of dropping it.
"""

from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import yaml

from api.persistence.campaign_models import CampaignStorageError
from api.tests.test_economic_action_http import TIP, EconomicHttpFixture
from api.tests import test_roadmap_r04_commit_boundary as r04  # module import: its tests are not re-collected here
from api.tests.town_seed import fixed_town


class EconomicConfirmUndoAfterLostAck(EconomicHttpFixture):
    async def asyncSetUp(self):
        with fixed_town(self, 11101):
            await super().asyncSetUp()

    def status(self, action_id):
        return self.http.get(f'/api/game/sessions/{self.campaign["session_id"]}/actions/{action_id}')

    async def test_committed_unconfirmed_payment_can_still_be_undone(self):
        card = await self.card(**TIP)
        real_save = self.manager.autosave_turn

        def saved_then_lost(*args, **kwargs):
            real_save(*args, **kwargs)
            raise RuntimeError("fixture: the commit landed but its answer was lost")

        body = {"message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
                "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                    "confirmation_digest": card["confirmation_digest"]}}
        with patch.object(self.manager, "autosave_turn", side_effect=saved_then_lost):
            lost = await self.post(body)
        self.assertEqual(lost.json()["detail"].get("commit_status"), "committed_unconfirmed", lost.text)
        self.assertEqual(self.purse(), 96)
        self.assertEqual((self.record.undo_checkpoint or {}).get("action_id"), body["action_id"],
                         "the committed payment is the live undo target")
        status = await self.status(body["action_id"])
        self.assertEqual(status.json().get("undo_available"), True, status.text)
        replay = await self.post(body)
        self.assertEqual(replay.status_code, 200, replay.text)
        undone = await self.undo(body["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (100, 0))
        stored = self.store.get_campaign(self.record.campaign_id).payload
        self.assertEqual(stored["engine_save"]["world_state"]["currency"]["player"], 100)
        after = await self.status(body["action_id"])
        self.assertEqual(after.json().get("undo_available"), False, "an undone payment is no longer an undo target")

    async def test_unbuildable_undo_point_keeps_the_commit_answer_and_drops_the_older_point(self):
        earlier, _ = await self.confirm(await self.card(**TIP))
        self.assertEqual((self.record.undo_checkpoint or {}).get("action_id"), earlier["action_id"])
        card = await self.card(**TIP)
        real_save = self.manager.autosave_turn

        def saved_then_lost(*args, **kwargs):
            real_save(*args, **kwargs)
            raise RuntimeError("fixture: the commit landed but its answer was lost")

        body = {"message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
                "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                    "confirmation_digest": card["confirmation_digest"]}}
        with patch.object(self.manager, "autosave_turn", side_effect=saved_then_lost), \
             patch("api.main._state_fingerprint", side_effect=RuntimeError("fixture: fingerprint failed")):
            lost = await self.post(body)
        self.assertEqual(lost.json()["detail"].get("commit_status"), "committed_unconfirmed", lost.text)
        self.assertEqual(self.purse(), 92, "both payments stay committed")
        self.assertIsNone(self.record.undo_checkpoint, "no undo point, and never the older payment's stale one")


class TurnUndoAfterLostAck(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 11102):
            await r04.CommitBoundaryTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    post = r04.CommitBoundaryTests.post
    live_facts = r04.CommitBoundaryTests.live_facts

    def status(self, action_id):
        return self.http.get(f"/api/game/sessions/{self.created['session_id']}/actions/{action_id}")

    def undo(self, target):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                              json={"action_id": str(uuid.uuid4()), "target_action_id": target})

    async def test_committed_unconfirmed_turn_can_still_be_undone(self):
        before = self.live_facts()
        action_id = str(uuid.uuid4())
        real_save = self.store.save_campaign

        def commit_then_lose_ack(*args, **kwargs):
            real_save(*args, **kwargs)
            raise CampaignStorageError("commit acknowledgement lost")

        with patch.object(self.store, "save_campaign", side_effect=commit_then_lose_ack):
            lost = await self.post(action_id)
        self.assertEqual(lost.json()["detail"]["commit_status"], "committed_unconfirmed", lost.text)
        self.assertEqual((self.record.undo_checkpoint or {}).get("action_id"), action_id)
        self.assertEqual((await self.post(action_id)).status_code, 200)
        undone = await self.undo(action_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.live_facts()["hp"], before["hp"])
        self.assertEqual(self.live_facts()["money"], before["money"])

    async def test_status_names_only_the_live_undo_target(self):
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertEqual((await self.post(first)).status_code, 200)
        self.assertEqual((await self.post(second, "Kapıyı yeniden dinliyorum.")).status_code, 200)
        # The reply of `second` was lost on the way: the screen asks the server what it recorded.
        self.assertEqual((await self.status(second)).json().get("undo_available"), True)
        self.assertEqual((await self.status(first)).json().get("undo_available"), False,
                         "an older turn is applied but is not the undo target")
        self.assertEqual((await self.undo(second)).status_code, 200)
        self.assertEqual((await self.status(second)).json().get("undo_available"), False)

    async def test_published_status_contract_names_every_status_field(self):
        # The generated client type comes from the OpenAPI schema; a field the server sends but the schema omits
        # dies silently the day the client starts parsing responses strictly.
        action_id = str(uuid.uuid4())
        self.assertEqual((await self.post(action_id)).status_code, 200)
        sent = set((await self.status(action_id)).json())
        self.assertIn("undo_available", sent)
        spec = yaml.safe_load((Path(__file__).resolve().parents[3] / "lib" / "api-spec" / "openapi.yaml")
                              .read_text(encoding="utf-8"))
        documented = spec["components"]["schemas"]["GameActionStatus"]
        self.assertEqual(sent - set(documented["properties"]), set(), "server fields missing from GameActionStatus")
        self.assertEqual(documented["properties"]["undo_available"].get("type"), "boolean")


if __name__ == "__main__":
    unittest.main()
