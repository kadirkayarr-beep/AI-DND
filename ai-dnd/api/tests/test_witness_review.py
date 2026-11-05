"""R2 review regressions: a witness selection cannot bypass a veto or change the question."""
import copy
import json
import unittest
import uuid

import economic_actions as ea
import witness_recall
from api.tests import test_campaign_api as fixtures
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.test_lasting_consequences import WitnessRecallClient

RECALL = "ben dün burada ne yaptım hatırlıyor musun"
FAMILY = "Babamın ne iş yaptığını hatırlıyor musun?"
DEED = "Quenna Atölyesi içinde ateş yaktı"


class ReviewClient(WitnessRecallClient):
    def __init__(self, question, *, answer="none", part="unclear"):
        super().__init__(question)
        self.answer, self.part = answer, part
        self.spoken = "Paranı istemem." if answer == "declines" else "Baban değirmenciydi."

    def chat(self, *args, **kwargs):
        result = super().chat(*args, **kwargs)
        if "spoken_text" in (kwargs.get("format") or {}).get("properties", {}):
            packet = json.loads(result["message"]["content"])
            packet.update(coin_answer=self.answer, coin_answer_for=self.part)
            if getattr(self, "omit_source_quote", False):
                packet["witness_recall"].pop("source_quote", None)
            result["message"]["content"] = json.dumps(packet, ensure_ascii=False)
        return result


class WitnessReviewSetup(EconomicHttpFixture):
    async def ready_witness(self, *, kind="arson", text=DEED):
        self.record.game_session._experimental_npc_dialogue_enabled = True
        self.world["flags"]["deeds"] = [{"kind": kind, "text": text, "location": self.here,
            "victim_id": None, "witnesses": ["barman"], "turn": 0, "at": 0, "heard": [], "told": []}]
        self.world["flags"].update(active_npc_id="barman", last_npc_id="barman", active_npc_until_turn=99)
        self.save()

    def financial_state(self):
        flags = self.world.get("flags", {})
        return copy.deepcopy({"currency": self.world["currency"], "inventory": self.world.get("inventory"),
                              "ledger": flags.get("economic_ledger"), "room": flags.get("inn_room")})

    async def recall(self, question, *, answer="none", part="unclear", action=None):
        client = ReviewClient(question, answer=answer, part=part)
        body = {"message": question, "action_id": action or str(uuid.uuid4()),
                "interaction_mode": "say", "target_id": "barman"}
        response = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(client.offered), 1, "the malicious/valid selector really received a live source")
        self.assertEqual(client.calls, 1, "one speech request per turn")
        return response.json(), body

    async def decline_then_confirm(self, proposal, part, *, question=RECALL, expected_status=None):
        # Assault is a witnessed engine deed without the separate grave-deed vendor refusal.
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        card = await self.card(**proposal)
        before = self.financial_state()
        reply, _ = await self.recall(question, answer="declines", part=part)
        if expected_status is not None:
            self.assertEqual(reply["turn_outcome"]["status"], expected_status)
        after_reply = self.financial_state()
        declined = ea.declined(self.world, "barman", part, day=ea.game_day(self.world))
        card_status = self.offers()[card["offer_id"]]["status"]
        confirmed, _ = await self.confirm(card)
        # Check the real monetary effect first, not merely whether a flag was set.
        self.assertEqual(self.financial_state(), before,
            {"card_before_confirm": card_status, "declined": declined, "after_reply": after_reply,
             "confirmation": confirmed["narration"]})
        self.assertTrue(declined)
        self.assertEqual(card_status, "cancelled")
        self.assertIn("geri çevirdi", reply["narration"])



class WitnessReviewHttp(WitnessReviewSetup):
    async def test_witness_room_no_cancels_the_old_card_and_prevents_actual_debit(self):
        await self.decline_then_confirm({"purpose": "room", "recipient_id": "barman"}, "room")

    async def test_witness_gift_no_cancels_the_old_card_and_prevents_actual_debit(self):
        await self.decline_then_confirm({"purpose": "gift", "recipient_id": "barman", "amount_cp": 5}, "gift")

    async def test_an_explicit_witness_source_answer_keeps_the_same_coin_decline_veto(self):
        await self.decline_then_confirm({"purpose": "gift", "recipient_id": "barman", "amount_cp": 5}, "gift",
            question="Birinin üzerine yürüdü. Bu olayı hatırlıyor musun?",
            expected_status="answered_from_witnessed_deed")
    def full_snapshot(self):
        return copy.deepcopy((self.record.game_session.serialize_game_state(),
            self.record.game_session.rng.getstate(), self.record.journal, self.record.narrative_memory,
            self.record.lore_authority.to_dict(), self.record.turn_action_receipts,
            self.store.get_campaign(self.record.campaign_id)))

    async def test_witness_veto_save_failure_rolls_back_then_retry_and_replay_commit_once(self):
        from unittest.mock import patch
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        card = await self.card(purpose="gift", recipient_id="barman", amount_cp=5)
        before = self.full_snapshot()
        body = {"message": RECALL, "action_id": str(uuid.uuid4()), "interaction_mode": "say", "target_id": "barman"}
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("witness save failure")):
            failed = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url,
                ReviewClient(RECALL, answer="declines", part="gift"), body)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(self.full_snapshot(), before)
        retry = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url,
            ReviewClient(RECALL, answer="declines", part="gift"), body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        committed = self.full_snapshot()
        client = ReviewClient(RECALL, answer="declines", part="gift")
        replay = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url, client, body)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(client.calls, 0)
        self.assertEqual(self.full_snapshot(), committed)

    async def test_witness_veto_survives_a_fresh_manager_and_still_blocks_old_card_confirmation(self):
        import httpx
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        card = await self.card(purpose="room", recipient_id="barman")
        await self.recall(RECALL, answer="declines", part="room")
        old = self.manager
        reopened = fixtures.CampaignStore(self.store.path, bound_principal=fixtures.TEST_PLAYER)
        fresh = fixtures.SessionManager(campaign_store=reopened)
        session_id, *_ = fresh.resume_campaign(self.record.campaign_id)
        adapter = self.app.state.ollama_adapter
        app = fixtures.create_app(session_manager=fresh, ollama_adapter=adapter,
                                 authenticator=fixtures.FixedAuthenticator(fixtures.TEST_PLAYER))
        headers, base_url = dict(self.http.headers), self.http.base_url
        await self.http.aclose()
        self.manager, self.store, self.app = fresh, reopened, app
        self.campaign["session_id"] = session_id
        self.turn_url = f"/api/game/sessions/{session_id}/turn"
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url, headers=headers)
        self.assertIsNot(self.manager, old)
        self.assertTrue(ea.declined(self.world, "barman", "room", day=ea.game_day(self.world)))
        before = self.financial_state()
        await self.confirm(card)
        self.assertEqual(self.financial_state(), before)

    async def test_one_undo_restores_decline_without_reviving_cancelled_card_and_second_undo_is_refused(self):
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        card = await self.card(purpose="gift", recipient_id="barman", amount_cp=5)
        before = self.financial_state()
        _, body = await self.recall(RECALL, answer="declines", part="gift")
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        restored = await self.undo(body["action_id"])
        self.assertEqual(restored.status_code, 200, restored.text)
        # Existing reconcile_offers_after_undo never revives a cancelled offer.
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertFalse(ea.declined(self.world, "barman", "gift", day=ea.game_day(self.world)))
        self.assertEqual(self.financial_state(), before)
        second = await self.undo(body["action_id"])
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(self.financial_state(), before)
        await self.confirm(card)
        self.assertEqual(self.financial_state(), before)
        fresh = await self.card(purpose="gift", recipient_id="barman", amount_cp=5)
        await self.confirm(fresh)
        self.assertEqual(self.purse(), 95)
        self.assertEqual(len(self.world["flags"]["economic_ledger"]["operations"]), 1)

    async def test_a_witness_takes_field_cannot_lift_an_existing_decline(self):
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        ea.record_decline(self.world, "barman", "gift", 5, day=ea.game_day(self.world), turn=0)
        self.save()
        await self.recall(RECALL, answer="takes", part="gift")
        self.assertTrue(ea.declined(self.world, "barman", "gift", day=ea.game_day(self.world)))
        self.assertEqual(self.purse(), 100)
