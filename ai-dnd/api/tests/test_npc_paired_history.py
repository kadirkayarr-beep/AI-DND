"""Committed visible NPC exchanges across native and experimental routes."""
import copy
import unittest
from unittest.mock import patch

import game
import local_dialogue
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.auth_fixture import TEST_PLAYER
from api.persistence.campaign_models import CampaignStorageError


class PairedHistoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    request = staticmethod(speech.ExperimentalNpcDialogueTests.request)

    async def post(self, url, client, body):
        response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    @staticmethod
    def pairs(session, npc):
        return session.world_state.get("npc_speech_log", {}).get(npc["id"], [])

    async def native(self):
        _, sid, session, url, npc = await self.campaign_with_npc()
        client = speech.ScriptedNpcSpeechClient(narration="Kayıtları düzenlemeyi seviyorum.")
        body = self.request(npc, message="Adın nedir?", interaction_mode="do")
        response = await self.post(url, client, body)
        self.assertEqual(client.chat_calls, 0)
        self.assertIn(npc["name"], response.json()["narration"])
        return sid, session, url, npc, client, body, response

    async def test_native_then_experimental_followup_has_one_visible_pair(self):
        _, session, url, npc, client, body, response = await self.native()
        expected = {"player": body["message"], "npc": response.json()["narration"][:400]}
        self.assertEqual(self.pairs(session, npc), [expected])
        contexts = []
        original = game._experimental_npc_dialogue_context
        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            contexts.append(copy.deepcopy(result))
            return result
        with patch.object(game, "_experimental_npc_dialogue_context", side_effect=capture):
            await self.post(url, client, {"message": "Peki neden?", "interaction_mode": "say"})
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(contexts[-1]["last_exchange"], {"player": expected["player"], "npc_reply": expected["npc"]})
        self.assertIn(expected["player"], str(client.message_batches[-1]))
        self.assertEqual(len(self.pairs(session, npc)), 2)

    async def test_answer_field_then_followup_has_visible_pair(self):
        _, _, session, url, npc = await self.campaign_with_npc()
        proposal = {"addressee_id": npc["id"], "subject_phrase": "Marek",
                    "subject_role": "addressee", "meaning": "personal_purpose",
                    "topic_relation": "new", "candidate_evidence_ids": [
                        f"npc-profile:{npc['id']}:v1:reason_for_being_here"]}
        client = speech.MalformedNpcSpeechClient(conversation=proposal)
        body = self.request(npc, message="Marek, neden buraya geldin?")
        response = await self.post(url, client, body)
        self.assertIn(npc["personal_profile"]["reason_for_being_here"], response.json()["narration"])
        self.assertEqual(self.pairs(session, npc), [{"player": body["message"], "npc": response.json()["narration"][:400]}])
        following = speech.ScriptedNpcSpeechClient(narration="Kayıtları düzenlemeyi seviyorum.")
        contexts = []
        original = game._experimental_npc_dialogue_context
        def capture(*args, **kwargs):
            result = original(*args, **kwargs); contexts.append(copy.deepcopy(result)); return result
        with patch.object(game, "_experimental_npc_dialogue_context", side_effect=capture):
            await self.post(url, following, self.request(npc, message="Peki neden?"))
        self.assertEqual(contexts[-1]["last_exchange"]["npc_reply"], response.json()["narration"][:400])

    async def test_pair_history_resume_and_replay_do_not_duplicate(self):
        sid, session, url, npc, client, body, response = await self.native()
        pairs = copy.deepcopy(self.pairs(session, npc))
        self.assertEqual(len(pairs), 1)
        replay = await self.post(url, client, body)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(client.chat_calls, 0)
        self.assertEqual(self.pairs(session, npc), pairs)
        campaign_id = self.manager.get(sid).campaign_id
        detail = await self.http.get(f"/api/game/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        expected_history = detail.json()["history"]
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        manager = api.SessionManager(campaign_store=self.store)
        app = api.create_app(session_manager=manager, ollama_adapter=api.AuthenticatedOllamaAdapter(client),
                             authenticator=api.FixedAuthenticator(TEST_PLAYER))
        async with api.httpx.AsyncClient(transport=api.httpx.ASGITransport(app=app), base_url="http://test") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        fresh = manager.get(resumed.json()["session_id"]).game_session
        self.assertEqual(self.pairs(fresh, npc), pairs)
        history = resumed.json()["history"]
        self.assertEqual(history, expected_history)
        self.assertEqual((history[-1]["player_message"], history[-1]["narration"]),
                         (body["message"], response.json()["narration"]))
        self.assertEqual(client.chat_calls, 0)

    async def test_resumed_session_replay_preserves_pair_history_state_and_rng(self):
        sid, _, _, npc, client, body, original = await self.native()
        campaign_id = self.manager.get(sid).campaign_id
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        manager = api.SessionManager(campaign_store=self.store)
        app = api.create_app(session_manager=manager, ollama_adapter=api.AuthenticatedOllamaAdapter(client),
                             authenticator=api.FixedAuthenticator(TEST_PLAYER))
        async with api.httpx.AsyncClient(transport=api.httpx.ASGITransport(app=app), base_url="http://test") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            new_sid = resumed.json()["session_id"]
            fresh = manager.get(new_sid).game_session
            before = copy.deepcopy(fresh.serialize_game_state())
            rng = fresh.rng.getstate()
            pairs = copy.deepcopy(self.pairs(fresh, npc))
            history = resumed.json()["history"]
            calls = client.chat_calls
            with patch.object(game, "run_player_turn", side_effect=AssertionError("Replay must not execute engine")) as engine:
                replay = await http.post(f"/api/game/sessions/{new_sid}/turn", json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), {**original.json(), "session_id": new_sid})
                conflict = await http.post(f"/api/game/sessions/{new_sid}/turn", json={**body, "message": "Farklı bir soru."})
                self.assertEqual(conflict.status_code, 409, conflict.text)
                engine.assert_not_called()
            detail = await http.get(f"/api/game/campaigns/{campaign_id}")
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["history"], history)
            self.assertEqual(fresh.serialize_game_state(), before)
            self.assertEqual(fresh.rng.getstate(), rng)
            self.assertEqual(self.pairs(fresh, npc), pairs)
            self.assertEqual(client.chat_calls, calls)

    async def test_same_npc_id_keeps_campaign_pair_contexts_separate(self):
        sid_a, session_a, _, npc_a, _, _, _ = await self.native()
        pairs_a = copy.deepcopy(self.pairs(session_a, npc_a))
        _, sid_b, session_b, url_b, npc_b = await self.campaign_with_npc()
        self.assertNotEqual(self.manager.get(sid_a).campaign_id, self.manager.get(sid_b).campaign_id)
        self.assertEqual(npc_a["id"], npc_b["id"])
        self.assertEqual(self.pairs(session_b, npc_b), [])
        contexts = []
        original = game._experimental_npc_dialogue_context
        def capture(*args, **kwargs):
            result = original(*args, **kwargs); contexts.append(copy.deepcopy(result)); return result
        client = speech.ScriptedNpcSpeechClient(narration="Kayıtları düzenlemeyi seviyorum.")
        with patch.object(game, "_experimental_npc_dialogue_context", side_effect=capture):
            response = await self.post(url_b, client, self.request(npc_b, message="Selam, bugün nasılsın?"))
        self.assertEqual(contexts[-1]["conversation_so_far"], [])
        self.assertIsNone(contexts[-1]["last_exchange"])
        self.assertNotIn(pairs_a[0]["npc"], str(client.message_batches[-1]))
        self.assertEqual(self.pairs(session_a, npc_a), pairs_a)
        self.assertEqual(len(self.pairs(session_b, npc_b)), 1)
        self.assertIn(self.pairs(session_b, npc_b)[0]["npc"], response.json()["narration"])
        self.assertIsNot(session_a.world_state["npc_speech_log"], session_b.world_state["npc_speech_log"])

    async def test_native_pair_save_failure_rolls_back_before_retry(self):
        _, sid, session, url, npc = await self.campaign_with_npc()
        client = speech.ScriptedNpcSpeechClient()
        body = self.request(npc, message="Adın nedir?", interaction_mode="do")
        before = copy.deepcopy(session.serialize_game_state())
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("synthetic failure")):
            failed = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
        self.assertEqual(failed.status_code, 503, failed.text)
        fresh = self.manager.get(sid).game_session
        self.assertEqual(fresh.serialize_game_state(), before)
        self.assertEqual(self.pairs(fresh, npc), [])
        response = await self.post(url, client, body)
        self.assertEqual(len(self.pairs(fresh, npc)), 1)
        self.assertEqual(self.pairs(fresh, npc)[0]["npc"], response.json()["narration"][:400])
        self.assertEqual(client.chat_calls, 0)

    async def test_native_pair_does_not_leak_to_other_npc(self):
        _, session, url, npc, client, _, _ = await self.native()
        self.assertEqual(len(self.pairs(session, npc)), 1)
        other = next(n for n in session.world_state["npcs"] if n.get("id") == "npc_private_sera")
        contexts = []
        original = game._experimental_npc_dialogue_context
        def capture(*args, **kwargs):
            result = original(*args, **kwargs); contexts.append(copy.deepcopy(result)); return result
        with patch.object(game, "_experimental_npc_dialogue_context", side_effect=capture):
            await self.post(url, client, self.request(other, message="Selam, bugün nasılsın?"))
        self.assertEqual(contexts[-1]["npc_id"], other["id"])
        self.assertEqual(contexts[-1]["conversation_so_far"], [])
        self.assertIsNone(contexts[-1]["last_exchange"])
        self.assertNotIn("PRIVATE_PROFILE_SECRET", str(client.message_batches[-1]))
        self.assertEqual(len(self.pairs(session, npc)), 1)

    async def test_rejected_proposal_is_not_added_as_a_pair(self):
        _, session, url, npc, _, _, _ = await self.native()
        before = copy.deepcopy(session.world_state["npc_speech_log"])
        client = speech.MalformedNpcSpeechClient(conversation={
            "addressee_id": "npc_private_sera", "subject_phrase": "Marek",
            "subject_role": "addressee", "meaning": "personal_purpose",
            "topic_relation": "new", "candidate_evidence_ids": [
                f"npc-profile:{npc['id']}:v1:reason_for_being_here"],
        })
        response = await self.post(url, client, self.request(npc, message="Selam, bugün nasılsın?"))
        self.assertEqual(client.chat_calls, 1)
        # A shown, accepted Python fallback is dialogue context, not the
        # rejected model proposal. Preserve the original pair and reject raw
        # malformed prose; do not forbid the already-supported shown fallback.
        pairs = self.pairs(session, npc)
        self.assertEqual(pairs[:1], before[npc["id"]])
        self.assertNotIn("Fallback text.", str(pairs))
        self.assertNotIn("PRIVATE", str(pairs))
        self.assertEqual(pairs[-1]["npc"], response.json()["narration"][:400])

    async def test_wrong_identity_and_false_past_never_store_rejected_prose(self):
        for bad in ('Ben Taren, buranın muhafızıyım.', 'Dün sana on altın vermiştim.'):
            with self.subTest(prose=bad):
                _, _, session, url, npc = await self.campaign_with_npc()
                client = speech.ScriptedNpcSpeechClient(narration=bad)
                response = await self.post(url, client, self.request(npc))
                self.assertNotIn(bad, response.json()["narration"])
                self.assertNotIn(bad, str(self.pairs(session, npc)))
                self.assertEqual(client.chat_calls, 1)

    def test_pair_limits_do_not_promote_speech_or_increase_memory(self):
        world = {"npcs": [{"id": "a"}], "locations": {}, "lore": {}}
        before = copy.deepcopy(world)
        for i in range(6):
            local_dialogue.remember_speech_exchange(world, "a", str(i) + 'p' * 300, 'n' * 500)
        pairs = world["npc_speech_log"]["a"]
        self.assertEqual(len(pairs), 4)
        self.assertEqual([x["player"][0] for x in pairs], list('2345'))
        self.assertTrue(all(len(x["player"]) == 240 and len(x["npc"]) == 400 for x in pairs))
        self.assertEqual({k: v for k, v in world.items() if k != "npc_speech_log"}, before)
