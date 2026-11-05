"""Independent-review regressions for daily price notes and fixed-price room proposals."""
from dataclasses import replace

import bold_acts
import economic_actions as ea
import game
import money_owner
import shop_trade
from api.tests.test_spoken_decline import Spoken


class ReviewedPrices(Spoken):
    def test_day_one_discount_is_the_price_in_the_speech_input(self):
        self.w.setdefault("campaign_time", {})["elapsed_seconds"] = 86400
        npc = self.npc("barman")
        shop_trade.apply_cut(self.w, npc, "bira", 4)
        self.assertEqual(shop_trade.quote(self.w, "barman", "bira", 1)["unit_cp"], 3)
        note = game._experimental_speech_note(self.w, npc, "reveal", "bira ne kadar?")
        self.assertIn("bira 3 bakır", note)
        self.assertNotIn("bira 4 bakır", note)

    def test_expired_discount_does_not_survive_in_the_speech_input(self):
        npc = self.npc("barman")
        shop_trade.apply_cut(self.w, npc, "bira", 4)
        self.w.setdefault("campaign_time", {})["elapsed_seconds"] = 86400
        self.assertEqual(shop_trade.quote(self.w, "barman", "bira", 1)["unit_cp"], 4)
        note = game._experimental_speech_note(self.w, npc, "reveal", "bira ne kadar?")
        self.assertIn("bira 4 bakır", note)
        self.assertNotIn("bira 3 bakır", note)

    def test_fixed_amount_room_is_repriced_without_payment_and_old_card_is_invalid(self):
        self.assertEqual(self.prepare("room", "barman", amount_cp=50, tender_cp=50).status, "prepared")
        [old] = self.prepared()
        before = self.money()
        note = money_owner.haggle(self.s, self.npc("barman"), {"skill": "Persuasion", "result": "BAŞARILI"})
        self.assertIsNotNone(note)
        self.assertEqual(self.money(), before)
        [new] = self.prepared()
        self.assertNotEqual(new["offer_id"], old["offer_id"])
        self.assertEqual(sum(line["total_cp"] for line in new["lines"]), 45)
        refused = self.confirm(old, "old-fixed-price")
        self.assertEqual((refused.status, refused.net_debit_cp), ("refused", 0))
        paid = self.confirm(new, "new-fixed-price")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 45))
        self.assertEqual(self.w["currency"]["player"], 55)
    def test_repriced_room_preserves_tip_and_requires_new_confirmation(self):
        proposal = replace(ea.turn_proposal("room", "barman", amount_cp=50, tender_cp=60), tip_cp=5)
        self.assertEqual(ea.prepare_from_turn(self.s, proposal).status, "prepared")
        before = self.money()
        self.assertIsNotNone(money_owner.haggle(self.s, self.npc("barman"),
                                              {"skill": "Persuasion", "result": "BAŞARILI"}))
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["tip_cp"], 5)
        self.assertEqual(card["proposal"]["tender_cp"], 60)
        self.assertEqual(sum(line["total_cp"] for line in card["lines"]), 50)
        self.assertEqual(self.money(), before)
        paid = self.confirm(card, "new-discount-tip")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 50))

    def test_yesterday_discount_card_cannot_pay_today(self):
        self.prepare("room", "barman")
        money_owner.haggle(self.s, self.npc("barman"), {"skill": "Persuasion", "result": "BAŞARILI"})
        [card] = self.prepared()
        self.w.setdefault("campaign_time", {})["elapsed_seconds"] = 86400
        before = self.money()
        result = self.confirm(card, "expired-discount")
        self.assertEqual((result.status, result.net_debit_cp), ("refused", 0))
        self.assertEqual(self.money(), before)
        self.assertEqual(bold_acts.room_price(self.w, self.npc("barman")), 50)


import copy
from unittest.mock import patch
from uuid import uuid4
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR, ScriptedModel
from api.tests.journeys.schema import load_scenario
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.tests.auth_fixture import TEST_PLAYER


class HagglePersistence(JourneyCase):
    async def open_room(self):
        self.scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        result = await self.run_scenario(replace(self.scenario, steps=self.scenario.steps[:1]))
        self.assertEqual([r.status for r in result], ["pass"], result)
        self.sid = self.last_session_id
        self.cid = self.manager.get(self.sid).campaign_id

    def world(self):
        return self.manager.get(self.sid).game_session.world_state

    def reopened_world(self):
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, record, *_ = manager.resume_campaign(self.cid, principal=TEST_PLAYER)
        return record.game_session.world_state

    async def test_discount_save_failure_rolls_back_and_retry_can_discount(self):
        await self.open_room()
        before = copy.deepcopy(self.world())
        body = self._body(self.sid, self.scenario.steps[1])
        with patch.object(self, "_body", return_value=body), patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("synthetic haggle save failure")):
            failures = await self._play(self.sid, self.scenario.steps[1], ScriptedModel())
        self.assertTrue(any("HTTP 503" in failure for failure in failures), failures)
        self.assertEqual(self.world(), before)
        self.assertEqual(self.reopened_world(), before)
        with patch.object(self, "_body", return_value=body):
            self.assertEqual(await self._play(self.sid, self.scenario.steps[1], ScriptedModel()), [])
        npc = next(n for n in self.world()["npcs"] if n["id"] == "barman")
        self.assertEqual(bold_acts.room_price(self.world(), npc), 45)

    async def test_saved_discount_reloads_and_undo_restores_price_without_reviving_cancelled_cards(self):
        await self.open_room()
        before = copy.deepcopy(self.world())
        self.assertEqual(await self._play(self.sid, self.scenario.steps[1], ScriptedModel()), [])
        discounted = copy.deepcopy(self.world())
        self.assertEqual(self.reopened_world(), discounted)
        response = await self.http.post(f"/api/game/sessions/{self.sid}/undo", json={
            "action_id": str(uuid4()), "target_action_id": self.last_turn_action_id})
        self.assertEqual(response.status_code, 200, response.text)
        npc = next(n for n in self.world()["npcs"] if n["id"] == "barman")
        self.assertEqual(bold_acts.room_price(self.world(), npc), 50)
        self.assertNotIn("price_cut_day_v1", npc)
        old_open = [o for o in before["flags"]["economic_offers"].values() if o["status"] == "prepared"]
        open_now = [o for o in self.world()["flags"]["economic_offers"].values() if o["status"] == "prepared"]
        self.assertEqual(open_now, [])
        self.assertTrue(old_open)
        for card in old_open:
            self.assertEqual(self.world()["flags"]["economic_offers"][card["offer_id"]]["status"], "cancelled")
        self.assertEqual(self.world()["currency"], before["currency"])
        self.assertEqual(self.reopened_world(), self.world())