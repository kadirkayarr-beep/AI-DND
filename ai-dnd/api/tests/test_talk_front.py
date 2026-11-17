"""BM Task 1: a line said in conversation is read once by the model (the front reading); the old word routes are the
fallback. The reading is the turn's classifier call, so a plain talk turn is two calls: the reading and the speech.

Real app, real adapter, real engine; only the Ollama client is scripted. New campaigns pin the town (fixed_town)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import front_proposal
import game
import talk_front
from api import model_chain
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_front_proposal import FrontClient
from api.tests.town_seed import fixed_town

TOWN_SEED = 4171
SPOKEN = "Çarnuva'dan duyduğum pek bir şey yok."
LINE = "Bu aralar kasabada ne var ne yok?"


class TalkFrontTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def start(self, *, front_on=True, front=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.route_file = Path(directory.name) / "routes.jsonl"
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("AI_DND_NPC_SPEECH", None)
        os.environ.pop("AI_DND_FRONT_PROPOSAL", None)
        if front_on:
            os.environ["AI_DND_FRONT_PROPOSAL"] = "1"
            os.environ["AI_DND_ROUTE_LOG"] = str(self.route_file)
        with fixed_town(self, TOWN_SEED):
            city_id, self.session_id, self.session, self.turn_url, marek = await self.campaign_with_npc(
                experimental=False)
        self.world = self.session.world_state
        self.marek = next(n for n in self.world["npcs"] if n["id"] == marek["id"])
        self.sera = next(n for n in self.world["npcs"] if n["id"] == "npc_private_sera")
        self.client = FrontClient(SPOKEN)
        self.client.front = front or {"kind": "speak_to", "person_id": self.marek["id"], "asks": "rumour",
                                      "about_person_id": "none"}
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    async def say(self, message, *, mode="say", target=True):
        body = {"message": message, "action_id": str(uuid.uuid4()), "interaction_mode": mode}
        if target:
            body["target_id"] = self.marek["id"]
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def routes(self):
        return [json.loads(line) for line in self.route_file.read_text(encoding="utf-8").splitlines()]

    def front_calls(self):
        return [s for s in self.client.schemas if "front" in (s.get("properties") or {})]

    def classifier_calls(self):
        return [s for s in self.client.schemas if "intent" in (s.get("properties") or {})
                and "front" not in (s.get("properties") or {})]


class SayLineIsRead(TalkFrontTable):
    async def test_say_line_is_read_once(self):
        await self.start()
        body = await self.say(LINE)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertEqual(len(self.classifier_calls()), 0)
        self.assertEqual(self.client.chat_calls, 2)  # the reading and the speech
        self.assertIn(SPOKEN, body["narration"])
        self.assertNotEqual(self.routes()[-1]["route"], "skipped:typed")
        self.assertIs(self.routes()[-1]["reached_model"], True)

    async def test_failed_reading_skips_old_classifier(self):
        await self.start()
        self.client.fails = RuntimeError("provider gone")
        body = await self.say(LINE)
        self.assertLessEqual(self.client.chat_calls, 2)
        self.assertEqual(len(self.classifier_calls()), 0)
        self.assertTrue(body["narration"].strip())

    async def test_flag_off_keeps_old_chain(self):
        await self.start(front_on=False)
        body = await self.say(LINE)
        self.assertEqual(len(self.front_calls()), 0)  # no reading at all
        self.assertIn(SPOKEN, body["narration"])

    async def test_ask_dm_line_without_a_person_is_read_too(self):
        await self.start()
        await self.say(LINE, mode="ask_dm", target=False)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_slash_line_is_not_read(self):
        await self.start()
        await self.say("/inventory", target=False)
        self.assertEqual(len(self.front_calls()), 0)

    async def test_coin_line_still_goes_to_money_owner(self):
        await self.start(front={"kind": "speak_to", "person_id": "npc_experimental_marek", "coin_cp": 500,
                                "deal": "tip", "deal_goods": "none", "keep_change": False})
        self.marek["role"] = "barmen"
        kept = []
        clear = game._clear_turn_transients

        def keep_then_clear(session):
            if not kept:
                kept.append(getattr(session, "_front_coin", 0))
            clear(session)

        with patch.object(game, "_clear_turn_transients", keep_then_clear):
            await self.say("Beş altın veriyorum, Çarnuva nerede?")
        self.assertEqual(kept, [500])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_bad_about_person_is_none(self):
        await self.start()
        for about, want in ((self.marek["id"], "none"), ("npc_missing", "none"),
                            (self.sera["id"], self.sera["id"])):
            self.client.front = {"kind": "speak_to", "person_id": self.marek["id"], "asks": "person",
                                 "about_person_id": about}
            await self.say(LINE)
            self.assertEqual(self.session._front_talk["about_person_id"], want, about)
            self.assertEqual(self.session._front_talk["asks"], "person")

    async def test_unknown_asks_is_none(self):
        await self.start()
        self.client.front = {"kind": "speak_to", "person_id": self.marek["id"], "asks": "weather"}
        await self.say(LINE)
        self.assertEqual(self.session._front_talk["asks"], "none")
        self.assertEqual(self.session._front_talk["about_person_id"], "none")


class TheSchemaAndTheGate(unittest.TestCase):
    LISTED = {"people": [{"id": "npc_a", "name": "A"}], "places": [], "things": [], "offers": [], "bag": [],
              "parcels": [], "jobs": [], "wants": [], "goods": [], "speaking_with": "npc_a"}

    def test_schema_has_asks_and_about_early(self):
        schema = front_proposal.schema(self.LISTED)
        self.assertEqual(front_proposal.ASKS, ("place", "rumour", "work", "person", "shop", "name", "small_talk",
                                               "other", "none"))
        self.assertEqual(schema["properties"]["asks"]["enum"], list(front_proposal.ASKS))
        self.assertEqual(schema["properties"]["about_person_id"]["enum"], ["npc_a", "none"])
        first = schema["required"][:10]
        self.assertIn("asks", first)
        self.assertIn("about_person_id", first)
        model_chain._haiku_schema(schema)  # must not raise

    def test_guidance_describes_both_fields(self):
        text = front_proposal.guidance(self.LISTED)
        self.assertIn("asks:", text)
        self.assertIn("about_person_id:", text)

    def test_is_plain_talk(self):
        plain = {"kind": "speak_to", "person_id": "npc_a", "answer": "none"}
        self.assertTrue(talk_front.is_plain_talk(plain))
        self.assertFalse(talk_front.is_plain_talk(None))
        self.assertFalse(talk_front.is_plain_talk({**plain, "kind": "go_to"}))
        self.assertFalse(talk_front.is_plain_talk({**plain, "job_id": "thread_001"}))
        self.assertFalse(talk_front.is_plain_talk({**plain, "coin_cp": 5}))
        self.assertFalse(talk_front.is_plain_talk({**plain, "answer": "accept"}))
        self.assertTrue(talk_front.is_plain_talk({**plain, "job_id": "none", "coin_cp": 0}))

    def test_old_owner_allowed(self):
        plain = {"kind": "speak_to", "person_id": "npc_a", "answer": "none", "asks": "rumour"}
        self.assertEqual(len(talk_front.OWNERS), 11)
        self.assertTrue(talk_front.old_owner_allowed(None, "small_talk"))
        self.assertFalse(talk_front.old_owner_allowed(plain, "small_talk"))
        self.assertFalse(talk_front.old_owner_allowed(plain, "shop_presence"))
        self.assertTrue(talk_front.old_owner_allowed({**plain, "asks": "shop"}, "shop_presence"))
        self.assertFalse(talk_front.old_owner_allowed({**plain, "asks": "shop"}, "small_talk"))
        self.assertTrue(talk_front.old_owner_allowed({**plain, "kind": "go_to"}, "small_talk"))


if __name__ == "__main__":
    unittest.main()
