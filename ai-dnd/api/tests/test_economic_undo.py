"""A3 undo (C11, D2): the card's own record is outside the undo fingerprint, and undo revives only what it undid.

Preparing and cancelling never move the checkpoint. A confirm that consumes the card is a turn; undoing it opens
that card again with the same dice. A cancelled card is never revived, a card prepared after the undone turn comes
back cancelled, and an old action replays its historical answer without paying again.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from api.tests.test_economic_action_http import ROOM, TIP, EconomicHttpFixture


class UndoAndTheCard(EconomicHttpFixture):
    def label(self, text="8 Altın"):
        self.world["inventory"] = [*self.world.get("inventory", []), text]
        self.save()

    async def assert_undone(self, target):
        undone = await self.undo(target)
        self.assertEqual(undone.status_code, 200, undone.text)
        return undone.json()

    async def test_undo_real_turn_after_card_opened(self):
        card = await self.card(**TIP)
        turn_id, _ = await self.real_turn()
        undone = await self.assert_undone(turn_id)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "prepared")
        self.assertEqual(undone["state"]["economic_offer"]["offer_id"], card["offer_id"])

    async def test_prepare_cancel_do_not_move_checkpoint(self):
        self.label()
        turn_id, _ = await self.real_turn()
        checkpoint = self.checkpoint()
        card = await self.card(**ROOM)
        self.assertEqual(self.checkpoint(), checkpoint)
        await self.cancel(card["offer_id"])
        self.assertEqual(self.checkpoint(), checkpoint)
        self.assertIn("8 Altın", self.world["inventory"])
        await self.assert_undone(turn_id)

    async def test_undo_does_not_revive_cancelled_offer(self):
        card = await self.card(**TIP)
        turn_id, _ = await self.real_turn()
        await self.cancel(card["offer_id"])
        undone = await self.assert_undone(turn_id)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertIsNone(undone["state"]["economic_offer"])

    async def test_undo_cancels_offers_prepared_after_target_turn(self):
        turn_id, _ = await self.real_turn()
        card = await self.card(**TIP)
        undone = await self.assert_undone(turn_id)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertIsNone(undone["state"]["economic_offer"])

    async def test_undo_then_new_confirm_pays_once_net(self):
        card = await self.card(**TIP)
        first, first_body = await self.confirm(card)
        self.assertEqual(self.purse(), 96)
        await self.assert_undone(first_body["action_id"])
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (100, 0))
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "prepared")
        second, _ = await self.confirm(card)
        self.assertEqual(second["economic_resolution"]["status"], "applied")
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (96, 4))
        replay = await self.post(first_body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first)
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (96, 4))

    async def test_confirm_undo_old_action_returns_history_and_current_state(self):
        card = await self.card(**TIP)
        first, body = await self.confirm(card)
        stored = self.manager.get_turn_action(self.record, body["action_id"])
        undone = await self.assert_undone(body["action_id"])
        revision = self.revision()
        replay = await self.post(body)
        self.assertEqual(replay.json(), first)
        self.assertEqual(self.manager.get_turn_action(self.record, body["action_id"]), stored)
        self.assertEqual(self.revision(), revision)
        # The present is read on its own: the purse is back and the card is open again.
        self.assertEqual(undone["state"]["wallet"], {"total_cp": 100})
        self.assertEqual(undone["state"]["economic_offer"]["offer_id"], card["offer_id"])
        self.assertEqual(self.purse(), 100)

    async def test_rejected_second_confirm_then_undo_does_not_reprepare(self):
        self.label()
        card = await self.card(**TIP)
        first, body_a = await self.confirm(card)
        self.assertEqual(first["economic_resolution"]["status"], "applied")
        self.assertEqual(self.purse(), 896)
        second, body_b = await self.confirm(card)
        self.assertEqual(second["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(self.checkpoint()[0], body_a["action_id"])
        wrong = await self.undo(body_b["action_id"])
        self.assertEqual(wrong.status_code, 409, wrong.text)
        self.assertEqual(wrong.json()["detail"]["code"], "undo_unavailable")
        await self.assert_undone(body_a["action_id"])
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "prepared")
        self.assertEqual(self.purse(), 100)
        self.assertIn("8 Altın", self.world["inventory"])
        third, _ = await self.confirm(card)
        self.assertEqual(third["economic_resolution"]["status"], "applied")
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (896, 4))

    async def test_stale_confirm_then_undo_keeps_offer_cancelled(self):
        self.label()
        card = await self.card(**ROOM)
        turn_id, _ = await self.real_turn()
        with patch("bold_acts._ROOM_PRICE", 60):
            answered, _ = await self.confirm(card)
        self.assertEqual(answered["economic_resolution"]["reason_code"], "stale")
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertEqual(self.checkpoint()[0], turn_id)
        self.assertIn("8 Altın", self.world["inventory"])
        undone = await self.assert_undone(turn_id)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertIsNone(undone["state"]["economic_offer"])

    async def test_offer_ids_are_not_reused_after_undo(self):
        turn_id, _ = await self.real_turn()
        old = await self.card(**TIP)
        await self.cancel(old["offer_id"])
        await self.assert_undone(turn_id)
        kept = dict(self.offers()[old["offer_id"]])
        self.assertEqual(kept["status"], "cancelled")
        fresh = await self.card(purpose="gift", recipient_id="farmer", amount_cp=10)
        self.assertNotEqual(fresh["offer_id"], old["offer_id"])
        self.assertEqual(self.offers()[old["offer_id"]], kept)
        answered, _ = await self.confirm(old)
        self.assertEqual(answered["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(self.purse(), 100)

    async def test_pruned_cancelled_offer_not_revived_by_undo(self):
        card = await self.card(**TIP)
        turn_id, _ = await self.real_turn()
        for amount in range(1, 22):
            await self.card(purpose="tip", recipient_id="barman", amount_cp=amount)
        self.assertNotIn(card["offer_id"], self.offers())
        await self.assert_undone(turn_id)
        # Cancelled again, and as the oldest closed card it may be pruned again; it is never open.
        self.assertEqual(self.offers().get(card["offer_id"], {"status": "cancelled"})["status"], "cancelled")
        answered, _ = await self.confirm(card)
        self.assertEqual(answered["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(self.purse(), 100)


if __name__ == "__main__":
    unittest.main()
