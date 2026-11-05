"""Task 21: optional-field repair and atomic memory through the existing save/undo owners."""
import copy
import json
import os
import unittest
from uuid import uuid4
from unittest.mock import patch

import httpx
from api.main import create_app
from api.auth import FixedAuthenticator
import game
import front_proposal
import npc_told
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_npc_told import ChoosingClient, FACT
from api.tests.journeys.runner import ScriptedClient


class SaveRepair(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def ready(self):
        _, self.sid, _, self.url, self.npc = await self.campaign_with_npc()
        self.cid = self.manager.get(self.sid).campaign_id
        self.manager.save_campaign(self.cid)

    @property
    def session(self):
        return self.manager.get(self.sid).game_session

    @property
    def world(self):
        return self.session.world_state

    def fresh(self):
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        sid, record, *_ = manager.resume_campaign(self.cid, principal=TEST_PLAYER)
        return manager, sid, record

    async def say(self, text=FACT, *, client=None, body=None):
        self.session._experimental_npc_dialogue_enabled = True
        client = client or ChoosingClient(True)
        body = body or speech.ExperimentalNpcDialogueTests.request(self.npc, message=text)
        response = await api.CampaignApiTests.post_scene_turn(self, self.url, client, body)
        return response, body, client

    async def undo(self, action):
        response = await self.http.post(f"/api/game/sessions/{self.sid}/undo",
            json={"action_id": str(uuid4()), "target_action_id": action})
        return response

    async def test_old_save_and_corrupted_rows_load_and_save_again(self):
        await self.ready()
        _, _, old = self.fresh()
        self.assertNotIn("npc_told_v1", old.game_session.world_state)
        first, _, _ = await self.say("Hava serin.", client=ChoosingClient(False))
        self.assertEqual(first.status_code, 200, first.text)
        self.world["npc_told_v1"] = {self.npc["id"]: [{"turn": "x"}, {"turn": 1, "text": "ok"}]}
        flags = self.world.setdefault("flags", {})
        flags["money_declined"] = {"osman": "bad"}
        flags["counter_offer_v1"] = {"npc_id": self.npc["id"], "key": "bira", "seq": 0, "turn": 0, "tip_cp": -3}
        flags["economic_ledger"] = {"operations": {"kept": {"net_debit_cp": 0, "label": 4, "payee_id": []}}}
        self.manager.save_campaign(self.cid)
        fresh, sid, record = self.fresh()
        world = record.game_session.world_state
        self.assertEqual(world["npc_told_v1"][self.npc["id"]], [{"turn": 1, "text": "ok"}])
        self.assertEqual(world["flags"]["money_declined"], {})
        self.assertNotIn("tip_cp", world["flags"]["counter_offer_v1"])
        self.assertEqual(world["flags"]["economic_ledger"]["operations"]["kept"], {"net_debit_cp": 0})
        fresh.save_campaign(self.cid)
        _, _, again = self.fresh()
        self.assertEqual(again.game_session.world_state["npc_told_v1"], world["npc_told_v1"])

    async def test_a_failure_before_the_save_keeps_the_old_world_and_memory(self):
        await self.ready()
        before = copy.deepcopy(self.world)
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("synthetic before commit")):
            response, body, _ = await self.say()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.world, before)
        _, _, reloaded = self.fresh()
        self.assertEqual(reloaded.game_session.world_state, before)
        self.assertIsNone(self.store.get_turn_action(self.cid, body["action_id"], principal=TEST_PLAYER))

    async def test_the_same_action_twice_is_byte_identical_and_writes_one_row(self):
        await self.ready()
        first, body, client = await self.say()
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy(self.world)
        calls = client.chat_calls
        second, _, _ = await self.say(client=client, body=body)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.content, first.content)
        self.assertEqual(client.chat_calls, calls)
        self.assertEqual(self.world, before)
        self.assertEqual(len(self.world["npc_told_v1"][self.npc["id"]]), 1)

    async def test_a_lost_response_after_commit_replays_the_receipt_and_learns_once(self):
        await self.ready()
        original_post = self.http.post
        committed = []
        async def drop_after_commit(*args, **kwargs):
            response = await original_post(*args, **kwargs)
            self.assertEqual(response.status_code, 200, response.text)
            committed.append(response.content)
            raise ConnectionError("synthetic response lost after commit")
        body = speech.ExperimentalNpcDialogueTests.request(self.npc, message=FACT)
        client = ChoosingClient(True)
        with patch.object(self.http, "post", new=drop_after_commit), self.assertRaises(ConnectionError):
            await self.say(body=body, client=client)
        calls = client.chat_calls
        replay, _, _ = await self.say(body=body, client=client)
        self.assertEqual(replay.content, committed[0])
        self.assertEqual(client.chat_calls, calls)
        self.assertEqual(len(self.world["npc_told_v1"][self.npc["id"]]), 1)
        _, _, reloaded = self.fresh()
        self.assertEqual(reloaded.game_session.world_state["npc_told_v1"], self.world["npc_told_v1"])

    async def test_a_new_manager_resumes_and_the_recall_is_asked_there(self):
        await self.ready()
        response, _, _ = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        old = self.session
        fresh, sid, record = self.fresh()
        self.assertIsNot(record.game_session, old)
        self.manager = fresh
        adapter = self.app.state.ollama_adapter
        await self.http.aclose()
        self.app = create_app(session_manager=fresh, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://testserver"))
        self.sid = sid
        self.url = f"/api/game/sessions/{sid}/turn"
        client = speech.ScriptedNpcSpeechClient(narration="Baban değirmenciydi, Yeşilova'da.")
        response, _, _ = await self.say("Babamın ne iş yaptığını hatırlıyor musun?", client=client)
        self.assertEqual(response.status_code, 200, response.text)
        messages = "\n".join(m["content"] for batch in client.message_batches for m in batch)
        self.assertIn(FACT, messages)
        self.assertIn("Baban değirmenciydi", response.json()["narration"])

    async def test_after_undo_the_told_line_is_in_no_speech_input(self):
        await self.ready()
        response, body, _ = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        undone = await self.undo(body["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertNotIn(self.npc["id"], self.world.get("npc_told_v1", {}))
        response, _, client = await self.say("Yol uzun mu?", client=ChoosingClient(False))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(client.message_batches)
        for batch in client.message_batches:
            for message in batch:
                self.assertNotIn(FACT, message["content"])

    async def test_undo_restores_decline_consumption_and_memory(self):
        await self.ready()
        before_decline = copy.deepcopy(self.world.get("flags", {}).get("money_declined"))
        client = ScriptedClient({"front": {"kind": "speak_to", "person_id": self.npc["id"]},
            "spoken": "Paranı istemem.", "speech": {"coin_answer": "declines", "coin_answer_for": "unclear"}})
        with patch.dict(os.environ, {front_proposal.FLAG: "1"}):
            response, first, _ = await self.say("Bu parayı alır mısın?", client=client)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(self.npc["id"], self.world["flags"]["money_declined"])
        undone = await self.undo(first["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.world.get("flags", {}).get("money_declined"), before_decline)
        self.world["inventory"] = [{"item_id": "beer1", "name": "Bira"}]
        self.world["equipment"] = {"main_hand": None, "off_hand": None}
        self.manager.save_campaign(self.cid)
        client = ScriptedClient({"front": {"kind": "consume", "item_id": "beer1"}})
        with patch.dict(os.environ, {front_proposal.FLAG: "1"}):
            response, drink, _ = await self.say(client=client,
                body={"message": "Biramı içiyorum", "interaction_mode": "do", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world["inventory"], [])
        undone = await self.undo(drink["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.world["inventory"], [{"item_id": "beer1", "name": "Bira"}])
        before_told = copy.deepcopy(self.world.get("npc_told_v1"))
        response, told, _ = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(FACT, npc_told.context_rows(self.world, self.npc["id"]))
        undone = await self.undo(told["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.world.get("npc_told_v1"), before_told)
        snapshot = copy.deepcopy(self.world)
        for action in (told["action_id"], first["action_id"]):
            refused = await self.undo(action)
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertEqual(refused.json()["detail"]["code"], "undo_unavailable")
            self.assertEqual(self.world, snapshot)
            _, _, reloaded = self.fresh()
            self.assertEqual(reloaded.game_session.world_state, snapshot)