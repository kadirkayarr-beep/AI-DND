"""Frozen meaning-only comparisons; factual labels retain their own contract."""
import copy
import json
import unittest
import os
from unittest.mock import patch

import game
import interaction_adventure as ia
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech


class MeaningBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    question = "Marek, mürekkebin kokusu hoşuna gider mi?"
    reply = "Mürekkebin kokusunu severim."

    async def test_default_speech_schema_attribution_pair_and_replay_without_optin(self):
        for flag in (None, "0", "1"):
            with self.subTest(flag=flag), patch.dict(os.environ):
                if flag is None:
                    os.environ.pop("AI_DND_NPC_SPEECH", None)
                else:
                    os.environ["AI_DND_NPC_SPEECH"] = flag
                _, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                client = speech.ScriptedNpcSpeechClient(self.reply)
                body = speech.ExperimentalNpcDialogueTests.request(npc, message=self.question)
                response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.schemas[0]["required"], ["spoken_text", "stage_direction"])
                self.assertNotIn("narration", client.schemas[0]["properties"])
                self.assertIn(self.reply, response.json()["narration"])
                self.assertTrue(response.json()["narration"].startswith(npc["name"]))
                pairs = copy.deepcopy(session.world_state["npc_speech_log"][npc["id"]])
                self.assertEqual(len(pairs), 1)
                self.assertEqual(pairs[0]["npc"], self.reply)
                replay = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
                self.assertEqual(replay.json(), response.json())
                self.assertEqual(client.chat_calls, 1)
                self.assertEqual(session.world_state["npc_speech_log"][npc["id"]], pairs)

    def envelope(self, npc, meaning):
        return {"operation": "none", "quote": self.question, "conversation": {
            "addressee_id": npc["id"], "subject_phrase": "Marek",
            "subject_role": "addressee", "meaning": meaning,
            "topic_relation": "new", "candidate_evidence_ids": []}}

    async def test_owner_meaning_matrix_and_invalid_authority(self):
        _, _, session, _, npc = await self.campaign_with_npc()
        before = copy.deepcopy(session.world_state)
        for meaning in ("other", "unknown", "unclear", "cause", "lore", "identity", "personal_purpose"):
            raw = self.envelope(npc, meaning)
            result = ia.resolve_conversation(session.world_state, self.question, raw, npc)
            with self.subTest(meaning=meaning):
                if meaning == "personal_purpose":
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result["meaning"], meaning)
                    self.assertEqual(result["answer_field"], "npc_identity" if meaning == "identity" else None)
            print("OWNER_MATRIX", json.dumps({"meaning": meaning, "resolution": result}, ensure_ascii=False))
        for change in ("quote", "wrong_npc", "wrong_evidence"):
            raw = self.envelope(npc, "other")
            if change == "quote": raw["quote"] = "Different input"
            if change == "wrong_npc": raw["conversation"]["addressee_id"] = "npc_private_sera"
            if change == "wrong_evidence": raw["conversation"]["candidate_evidence_ids"] = ["npc-profile:npc_private_sera:v1:occupation"]
            with self.subTest(invalid=change):
                self.assertIsNone(ia.resolve_conversation(session.world_state, self.question, raw, npc))
        self.assertEqual(session.world_state, before)

    async def test_harmless_reply_meaning_only_legacy_and_experimental(self):
        for experimental in (False, True):
            _, _, session, url, npc = await self.campaign_with_npc(experimental=experimental)
            # Restore the complete trusted runtime fixture, including narration
            # caches. Keep API campaign ownership/revision in its own record.
            snapshot = session._capture_runtime_snapshot()
            world = copy.deepcopy(session.world_state)
            character = copy.deepcopy(session.character)
            rng = session.rng.getstate()
            for meaning in ("other", "unknown", "unclear", "personal_purpose", "identity"):
                session._restore_runtime_snapshot(snapshot)
                npc = next(n for n in session.world_state["npcs"] if n["id"] == npc["id"])
                client = speech.ScriptedNpcSpeechClient(self.reply, conversation=self.envelope(npc, meaning)["conversation"])
                body = speech.ExperimentalNpcDialogueTests.request(npc, message=self.question)
                response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
                self.assertEqual(response.status_code, 200, response.text)
                final = response.json()["narration"]
                replay = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
                self.assertEqual(replay.json(), response.json())
                self.assertEqual(client.chat_calls, 1)
                self.assertEqual(session.character, character)
                self.assertEqual(session.rng.getstate(), rng)
                self.assertEqual(session.world_state["inventory"], world["inventory"])
                print("API_MATRIX", json.dumps({"experimental": experimental, "meaning": meaning,
                    "input": self.question, "raw_reply": self.reply, "final": final,
                    "safety": session.last_narration_safety}, ensure_ascii=False, default=str))
                if meaning in ("other", "unknown", "unclear"):
                    with self.subTest(experimental=experimental, meaning=meaning):
                        self.assertIn(self.reply, final)

    def test_salvage_does_not_authorize_factual_or_mechanical_proposals(self):
        for meaning in ("personal_purpose", "identity", "cause", "lore"):
            raw = {"narration": self.reply, "interaction": self.envelope({"id": "npc"}, meaning)}
            self.assertFalse(game._salvage_plain_speech(raw))
        for operation in ("generate", "request", "promise"):
            raw = {"narration": self.reply, "interaction": {"operation": operation, "conversation": {"meaning": "other"}}}
            self.assertFalse(game._salvage_plain_speech(raw))


class DefaultSpeechBoundaryNegatives(unittest.IsolatedAsyncioTestCase):
    """Run unchanged boundary assertions with no experimental session opt-in."""
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    request = staticmethod(speech.ExperimentalNpcDialogueTests.request)
    sensitive_state = staticmethod(speech.ExperimentalNpcDialogueTests.sensitive_state)

    async def campaign_with_npc(self, *, experimental=False):
        return await speech.ExperimentalNpcDialogueTests.campaign_with_npc(self, experimental=False)

    test_default_wrong_identity_and_hidden_fact = speech.ExperimentalNpcDialogueTests.test_opt_in_wrong_speaker_identity_and_hidden_fact_are_rejected
    test_default_invalid_proposal_no_repair_or_mutation = speech.ExperimentalNpcDialogueTests.test_opt_in_invalid_proposal_does_not_trigger_repair_or_mutation
    test_default_operation_not_accepted = speech.ExperimentalNpcDialogueTests.test_opt_in_model_operation_is_not_accepted
    test_default_player_action_rejected = speech.ExperimentalNpcDialogueTests.test_opt_in_speech_rejects_physical_action_assigned_to_player
    test_default_narration_only_rejected = speech.ExperimentalNpcDialogueTests.test_opt_in_legacy_narration_field_fails_closed
    test_default_save_rollback_and_replay = speech.ExperimentalNpcDialogueTests.test_opt_in_save_failure_rolls_back_and_retry_receipt_replays
