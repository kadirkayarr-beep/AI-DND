"""D-139 (ORTA-01): a dice card binds to the story row its receipt was written with, not to the engine turn number.

A card prepare row, an undo marker or an undo itself moves the story sequence and the engine turn number apart; the
skill result must still sit on its own row (and on no other row), live and after the receipt archive.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_campaign_api as fixtures
from api.tests.test_economic_action_http import TIP, EconomicHttpFixture
from api.tests.town_seed import fixed_town

STEALTH = "Köşede gizlenmeye çalışıyorum."


class SkillCardRowIdentity(EconomicHttpFixture):
    async def asyncSetUp(self):
        with fixed_town(self, 13901):
            await super().asyncSetUp()

    async def stealth_turn(self):
        narrator = fixtures.ControlledVenueOllamaClient("narrative")  # the same scripted model as real_turn
        with patch("api.tests.test_campaign_api.FakeOllamaClient.chat", side_effect=narrator.chat):
            response = await self.post({"message": STEALTH, "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsInstance(body.get("skill_check_result"), dict, body)
        return body

    async def history(self):
        detail = await self.http.get(f'/api/game/campaigns/{self.campaign["campaign_id"]}')
        self.assertEqual(detail.status_code, 200, detail.text)
        return detail.json()["history"]

    def assert_card_only_on_last_row(self, history, body):
        self.assertEqual(history[-1]["player_message"], STEALTH)
        self.assertEqual(history[-1].get("skill_check_result"), body["skill_check_result"], history[-1])
        carded = [i for i, h in enumerate(history) if "skill_check_result" in h]
        self.assertEqual(carded, [len(history) - 1], history)

    async def test_a_card_prepare_row_does_not_drop_the_next_dice_card(self):
        await self.card(**TIP)
        body = await self.stealth_turn()
        self.assert_card_only_on_last_row(await self.history(), body)

    async def test_an_undo_does_not_drop_the_next_dice_card(self):
        turn_id, _ = await self.real_turn()
        self.assertEqual((await self.undo(turn_id)).status_code, 200)
        body = await self.stealth_turn()
        self.assert_card_only_on_last_row(await self.history(), body)

    async def test_the_card_stays_on_its_row_after_the_receipt_archive(self):
        await self.card(**TIP)
        body = await self.stealth_turn()
        campaign_id = self.campaign["campaign_id"]
        revision = self.store.get_campaign(campaign_id).metadata["revision"]
        self.store.compact_receipts(campaign_id, before_revision=revision + 1, keep_latest=0)
        self.assert_card_only_on_last_row(await self.history(), body)


class RowOfReceipt(unittest.TestCase):
    def test_only_one_row_with_the_same_time_and_text_is_proof(self):
        from api.persistence.campaign_store import _row_of_receipt

        at, later = "2026-11-15T10:00:01+00:00", "2026-11-15T10:00:02+00:00"
        rows = [
            {"sequence": 1, "narration": "A", "created_at": at},
            {"sequence": 2, "narration": "B", "created_at": at},
            {"sequence": 3, "narration": "B", "created_at": later},
            {"sequence": 4, "narration": "B", "created_at": later},
        ]
        self.assertEqual(_row_of_receipt(rows, at, "A"), 1)
        self.assertEqual(_row_of_receipt(rows, at, "B"), 2)
        self.assertIsNone(_row_of_receipt(rows, later, "B"))     # two rows in one second: nothing is guessed
        self.assertIsNone(_row_of_receipt(rows, later, "A"))     # same text, other moment
        self.assertIsNone(_row_of_receipt(rows, at, None))       # a receipt without narration names no row
        self.assertIsNone(_row_of_receipt(rows, None, "A"))


if __name__ == "__main__":
    unittest.main()
