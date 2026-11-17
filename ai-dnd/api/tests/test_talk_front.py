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
import local_dialogue
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

    async def say_keeping_the_reading(self, message):
        """The reading as the turn held it: front_proposal.end clears it once the turn is over (BM Task 2)."""
        kept = []
        run = game._run_player_turn

        def run_and_keep(*args, **kwargs):
            try:
                return run(*args, **kwargs)
            finally:
                kept.append(getattr(self.session, "_front_talk", None))

        with patch.object(game, "_run_player_turn", run_and_keep):
            await self.say(message)
        return kept[0]

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
            held = await self.say_keeping_the_reading(LINE)
            self.assertEqual(held["about_person_id"], want, about)
            self.assertEqual(held["asks"], "person")

    async def test_unknown_asks_is_none(self):
        await self.start()
        self.client.front = {"kind": "speak_to", "person_id": self.marek["id"], "asks": "weather"}
        held = await self.say_keeping_the_reading(LINE)
        self.assertEqual(held["asks"], "none")
        self.assertEqual(held["about_person_id"], "none")


class SayOwnersAreFallback(TalkFrontTable):
    """BM Task 2: shop presence, unknown name, place name and name disclosure answer by speech when the reading is
    plain talk. With no reading (the reading failed) the old line stands."""

    def talk(self, **extra):
        return {"kind": "speak_to", "person_id": self.marek["id"], "about_person_id": "none", "asks": "none", **extra}

    async def vendor(self, front):
        await self.start(front=front)
        self.marek["role"] = "Tüccar"

    def action(self, body):
        return (body.get("turn_outcome") or {}).get("action")

    async def test_shop_word_question_to_vendor_is_spoken(self):
        await self.vendor(None)
        self.client.front = self.talk(asks="rumour")
        body = await self.say("Satıcı esnafı arasında ne dönüyor?")
        self.assertIn(SPOKEN, body["narration"])
        self.assertNotEqual(self.action(body), "shop_inquiry")
        self.assertEqual(self.client.chat_calls, 2)

    async def test_shop_list_when_reading_asks_shop(self):
        await self.vendor(None)
        self.client.front = self.talk(asks="shop")
        body = await self.say("Satıcı esnafı arasında ne dönüyor?")
        self.assertEqual(self.action(body), "shop_inquiry", str({k: body[k] for k in body if k != "state"})[:900])

    async def test_shop_line_when_the_reading_failed(self):
        await self.vendor(None)
        self.client.fails = RuntimeError("provider gone")
        body = await self.say("Satıcı esnafı arasında ne dönüyor?")
        self.assertEqual(self.action(body), "shop_inquiry", str({k: body[k] for k in body if k != "state"})[:900])

    async def test_unknown_name_uses_reading(self):
        await self.start()
        self.client.front = self.talk(person_id="none", person_word="Zoltan")
        body = await self.say("Zoltan, merhaba", target=False)
        self.assertIn("Burada Zoltan adıyla tanıdığın biri görünmüyor.", body["narration"])
        self.client.front = self.talk()
        body = await self.say("Çavuş, merhaba", target=False)
        self.assertNotIn("adıyla tanıdığın biri görünmüyor", body["narration"])
        self.assertIn(SPOKEN, body["narration"])

    async def test_unknown_name_line_when_the_reading_failed(self):
        await self.start()
        self.client.fails = RuntimeError("provider gone")
        body = await self.say("Zoltan, merhaba", target=False)
        self.assertIn("Burada Zoltan adıyla tanıdığın biri görünmüyor.", body["narration"])

    async def test_name_disclosure_is_spoken_and_stored(self):
        await self.start(front=None)
        self.client.front = self.talk(asks="name")
        body = await self.say("Adım Dorin.")
        self.assertEqual(game._known_player_name(self.marek), "Dorin")
        self.assertIn(SPOKEN, body["narration"])
        for reply in local_dialogue.INTRODUCTION_REPLIES:
            self.assertNotIn(reply.format(name="Dorin"), body["narration"])
        self.assertEqual(self.client.chat_calls, 2)

    async def test_name_disclosure_pool_when_the_reading_failed(self):
        await self.start()
        self.client.fails = RuntimeError("provider gone")
        body = await self.say("Adım Dorin.")
        self.assertEqual(game._known_player_name(self.marek), "Dorin")
        self.assertTrue(any(reply.format(name="Dorin") in body["narration"]
                            for reply in local_dialogue.INTRODUCTION_REPLIES), body["narration"])

    async def test_name_disclosure_pool_when_the_speech_failed(self):
        """Task 2 carry: the reading is fine, the speech call gives no usable line; the old intro line is the
        fallback (spec 5.3)."""
        await self.start(front=None)
        self.client.front = self.talk(asks="name")
        self.client.narration = ""
        body = await self.say("Adım Dorin.")
        self.assertEqual(game._known_player_name(self.marek), "Dorin")
        self.assertTrue(any(reply.format(name="Dorin") in body["narration"]
                            for reply in local_dialogue.INTRODUCTION_REPLIES), body["narration"])

    async def test_place_name_question_is_spoken(self):
        await self.start()
        self.client.front = self.talk(asks="place")
        with patch.object(game, "_topic_place_name", return_value="Kızıl Geçit"):
            body = await self.say("Peki oranın adı ne?")
        self.assertIn(SPOKEN, body["narration"])
        self.assertNotIn("Kızıl Geçit", body["narration"])

    async def test_place_name_line_when_the_reading_failed(self):
        await self.start()
        self.client.fails = RuntimeError("provider gone")
        with patch.object(game, "_topic_place_name", return_value="Kızıl Geçit"):
            body = await self.say("Peki oranın adı ne?")
        self.assertIn("Kızıl Geçit", body["narration"])

    async def test_each_owner_also_runs_with_the_flag_off(self):
        await self.start(front_on=False)
        with patch.object(game, "_topic_place_name", return_value="Kızıl Geçit"):
            body = await self.say("Peki oranın adı ne?")
        self.assertIn("Kızıl Geçit", body["narration"])
        self.marek["role"] = "Tüccar"
        body = await self.say("Satıcı esnafı arasında ne dönüyor?")
        self.assertEqual(self.action(body), "shop_inquiry", str({k: body[k] for k in body if k != "state"})[:900])

    async def test_the_reading_is_this_turns_only(self):
        await self.start()
        await self.say(LINE)
        self.assertIsNone(self.session._front_talk)  # front_proposal.end clears it

    async def test_a_check_turn_does_not_keep_an_earlier_reading(self):
        await self.start()
        self.session._front_talk = {"kind": "speak_to", "person_id": self.marek["id"], "asks": "rumour"}
        seen = []

        def stop(*args, **kwargs):
            seen.append(getattr(self.session, "_front_talk", "missing"))
            raise RuntimeError("stop here")

        feature = sorted(game.CHECK_FEATURES)[0]
        token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        with patch.object(game, "primal_knowledge_check_admission"), patch.object(game, "_run_player_turn", stop):
            with self.assertRaises(RuntimeError):
                game._run_player_turn_owned("x", [], None, None, "a", self.session_id, None, "do", feature, [])
        self.assertEqual(seen, [None])


class ShopPresenceReply(unittest.TestCase):
    def test_no_shop_here(self):
        world = {"location": "here", "shops": [], "npcs": []}
        self.assertEqual(talk_front.shop_presence_reply(world, None),
                         "Bu çevrede şu an görünür bir dükkân ya da dükkâncı yok.")


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


class RemainingSayOwnersAreFallback(TalkFrontTable):
    """BM Task 3: personal, small talk, quest/work, lore gate, role + person answer by speech when the reading is
    plain talk; with no reading the old line stands. Also D-325 and the dead `_with_job_news`."""

    def talk(self, **extra):
        return {"kind": "speak_to", "person_id": self.marek["id"], "about_person_id": "none", "asks": "none", **extra}

    def action(self, body):
        return (body.get("turn_outcome") or {}).get("action")

    async def spoken(self, line, mode="say", target=True, **front):
        await self.start(front=None)
        self.marek["role"] = "Çavuş"
        self.client.front = self.talk(**front)
        body = await self.say(line, mode=mode, target=target)
        self.assertIn(SPOKEN, body["narration"], body["narration"])
        self.assertEqual(self.client.chat_calls, 2)
        return body

    async def old_line(self, line, mode="say", target=True, role=None):
        await self.start(front=None)
        if role:
            self.marek["role"] = role
        self.client.fails = RuntimeError("provider gone")
        body = await self.say(line, mode=mode, target=target)
        self.assertNotIn(SPOKEN, body["narration"])
        self.assertTrue(body["narration"].strip(), body)
        return body

    async def test_personal_question_is_spoken(self):
        await self.spoken("Nereden geldin?", asks="other")
        await self.spoken("Nereden geldin?", mode="ask_dm", target=False, asks="other")

    async def test_personal_question_old_line_when_the_reading_failed(self):
        body = await self.old_line("Nereden geldin?")
        self.assertEqual(self.action(body), "dialogue")
        self.assertEqual((body.get("turn_outcome") or {}).get("status"), "answered_personal_question")

    async def test_small_talk_is_spoken(self):
        await self.spoken("Günün nasıl geçiyor?", mode="ask_dm", target=False, asks="small_talk")

    async def test_small_talk_old_line_when_the_reading_failed(self):
        body = await self.old_line("Günün nasıl geçiyor?", mode="ask_dm", target=False)
        self.assertIn("söylentiler belirsiz", body["narration"])  # the lore gate's line

    async def test_quest_question_is_spoken(self):
        await self.spoken("Burada iş var mı?", mode="ask_dm", target=False, asks="work")
        await self.spoken("Burada iş var mı?", asks="work")

    async def test_quest_question_old_line_when_the_reading_failed(self):
        body = await self.old_line("Burada iş var mı?", mode="ask_dm", target=False)
        self.assertEqual(self.action(body), "local_inquiry")

    async def test_lore_question_is_spoken(self):
        await self.spoken("Kralın adı ne?", mode="ask_dm", target=False, asks="other")
        await self.spoken("Kralın adı ne?", asks="other")

    async def test_lore_question_old_line_when_the_reading_failed(self):
        body = await self.old_line("Kralın adı ne?", mode="ask_dm", target=False)
        self.assertEqual((body.get("turn_outcome") or {}).get("status"), "unverified")

    async def test_role_who_is_here_is_spoken(self):
        await self.spoken("Çavuş, bu gece nöbette kim var?", target=False, asks="person")
        await self.spoken("Çavuş, bu gece nöbette kim var?", mode="ask_dm", target=False, asks="person")

    async def test_role_who_is_here_old_line_when_the_reading_failed(self):
        body = await self.old_line("Çavuş, bu gece nöbette kim var?", mode="ask_dm", target=False, role="Çavuş")
        self.assertEqual((body.get("turn_outcome") or {}).get("status"), "answered_from_current_scene")
        body = await self.old_line("Çavuş, bu gece nöbette kim var?", target=False)
        self.assertEqual((body.get("turn_outcome") or {}).get("status"), "invalid_target")

    async def test_told_before_line_gets_own_rumour(self):
        await self.start(front=None)
        self.world["heard_rumours"] = [{
            "id": "rum_own", "settlement_id": self.world.get("current_settlement_id") or "x",
            "text": "Kespur Tapınağı: kilitte taze çizikler", "said_by": self.marek["id"],
            "speakers": [self.marek["id"]]}]
        self.client.fails = RuntimeError("provider gone")
        self.client.narration = ""  # and the speech call gives no usable line either
        body = await self.say("Bana Kespur Tapınağı'ndan bahsetmiştin")
        self.assertIn("kilitte taze çizikler", body["narration"])

class WithJobNewsIsGone(unittest.TestCase):
    def test_with_job_news_is_gone(self):
        self.assertFalse(hasattr(game, "_with_job_news"))
