"""What the world says it does, it does: the things a long play found saying one thing and doing another.

Every line is the kind of thing the owner types. No real model is called.
"""
import json
import os
import unittest
from unittest.mock import patch

import bold_acts
import campaign_time
import interaction_adventure
import world_happenings
import world_reactions
import world_threads
from api.tests.test_front_proposal import FrontTable
from api.tests.test_lasting_consequences import OneTownScene
from api.tests.test_three_plays import PlayClient
from api.tests.test_world_reactions import GuardsActOnWhatTheyKnow


class Stealing(OneTownScene):
    async def room(self):
        await self.town()
        self.world["location"] = "shop"
        self.world["flags"].pop("active_npc_id", None)

    async def steal(self, line, roll):
        with patch.object(self.session.rng, "randint", return_value=roll):
            return await self.say(line, PlayClient())

    async def test_an_empty_room_can_be_robbed_and_the_roll_is_shown(self):
        await self.room()
        before = self.world.get("currency", {}).get("player", 0)
        out = await self.steal("kimse yok. tezgahin arkasina gecip cekmeceden parayi yurutuyorum", 15)
        self.assertEqual(out["turn_outcome"]["status"], "stolen", out["narration"])
        self.assertGreater(self.world["currency"]["player"], before)
        self.assertEqual(out["skill_check_result"]["skill"], "Sleight of Hand")
        self.assertEqual(out["skill_check_result"]["dc"], 10)
        self.assertEqual(out["skill_check_result"]["d20"], 15)

    async def test_a_miss_in_an_empty_room_is_a_result_and_never_the_character_stopping(self):
        await self.room()
        before = self.world.get("currency", {}).get("player", 0)
        out = await self.steal("kimse yok, cekmeceyi yurutuyorum", 1)
        self.assertEqual(out["turn_outcome"]["status"], "failed", out["narration"])
        self.assertEqual(self.world.get("currency", {}).get("player", 0), before)
        self.assertNotIn("duraks", out["narration"])
        self.assertNotIn("fırsat", out["narration"])
        self.assertEqual(out["skill_check_result"]["outcome"], "failure")

    async def test_a_turned_back_is_the_easy_roll_and_a_face_watching_is_not(self):
        for line, dc in (("rahip mumlara donunce bagis kutusunu yurutuyorum", 10),
                         ("adam bakarken kesesini yurutuyorum", 10),
                         ("adamin kesesini yurutuyorum", 15)):
            with self.subTest(line=line):
                await self.room()
                self.add_person("Tariq", "Rahip", location="shop")
                out = await self.steal(line, 15)
                self.assertEqual(out["skill_check_result"]["dc"], dc, out["narration"])

    async def test_two_people_in_the_room_and_a_miss_is_a_caught_hand(self):
        await self.room()
        first = self.add_person("Tariq", "Rahip", location="shop")
        self.add_person("Bren", "Çırak", location="shop")
        out = await self.steal("kutuyu yurutuyorum", 1)
        self.assertEqual(out["turn_outcome"]["status"], "caught", out["narration"])
        self.assertEqual(self.world["flags"]["deeds"][-1]["victim_id"], first["id"])


class AnInnHasRooms(OneTownScene):
    async def inn(self):
        await self.town()
        self.world["location"] = "shop"
        self.world.setdefault("currency", {})["player"] = 1000
        return self.add_person("Veyra", "Barmen", location="shop")

    async def test_asking_the_price_of_a_room_gets_the_price_and_costs_nothing(self):
        for line in ("bi gecelik oda ne kadar?", "oda var mi", "barmene: oda kaç para?"):
            with self.subTest(line=line):
                await self.inn()
                out = await self.say(line, PlayClient(spoken="Oda kiralamıyorum."))
                self.assertIn("5 gümüş", out["narration"])
                self.assertEqual(self.world["currency"]["player"], 1000)
                self.assertIsNone(self.world["flags"].get("inn_room"))

    async def test_a_question_and_going_to_bed_in_one_line_takes_the_room_and_sleeps(self):
        await self.inn()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        out = await self.say("barmene: bi gecelik oda ne kadar? yatıcam, sabaha kadar kimse uyandırmasın", PlayClient())
        self.assertIn("50 bakır", out["narration"])
        self.assertTrue(self.world["flags"].get("inn_room"))
        self.assertGreater(self.world["campaign_time"]["elapsed_seconds"], clock)

    async def test_whoever_serves_knows_the_house_has_rooms(self):
        barman = await self.inn()
        self.assertIn("5 gümüş", self.note(barman))


class FrontLines(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = FrontTable.asyncSetUp, FrontTable.asyncTearDown
    campaign_with_npc, open_job, line = FrontTable.campaign_with_npc, FrontTable.open_job, FrontTable.line
    begin, routes, front_calls = FrontTable.begin, FrontTable.routes, FrontTable.front_calls

    def purse(self):
        return self.world.setdefault("currency", {}).get("player", 0)

    async def test_hanging_about_moves_the_clock(self):
        await self.begin()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        out = await self.line("köşedeki masaya geçip akşama kadar takılıyorum, millet dolsun bakalım")
        self.assertGreater(self.world["campaign_time"]["elapsed_seconds"], clock + 1800, out["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.routes()[-1]["owner"], "wait")

    async def test_hanging_about_with_no_length_is_a_while(self):
        await self.begin()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        await self.line("biraz oyalaniyorum burda")
        passed = self.world["campaign_time"]["elapsed_seconds"] - clock
        self.assertTrue(600 <= passed <= 3600, passed)

    async def test_a_coin_given_leaves_the_purse_and_the_person_has_it(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 100
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
        out = await self.line("yasliya yarim gumus veriyorum sus diye")
        self.assertEqual(self.purse(), 95)
        self.assertEqual(self.world["currency"][self.npc["id"]], 5)
        self.assertIn("5 bakır", out["narration"])

    async def test_words_about_coin_move_no_coin(self):
        for line in ("sana yarim gumus veririm ha", "yarim gumus eder mi?", "yarin bir gumus getiririm"):
            with self.subTest(line=line):
                await self.begin()
                self.world.setdefault("currency", {})["player"] = 100
                self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
                await self.line(line)
                self.assertEqual(self.purse(), 100, line)

    async def test_a_figure_with_no_coin_in_the_line_moves_nothing(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 100
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
        await self.line("sus artik bak")
        self.assertEqual(self.purse(), 100)

    async def test_more_than_the_purse_holds_stays_in_the_purse(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 3
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50}
        await self.line("al sana bes gumus veriyorum")
        self.assertEqual(self.purse(), 3)


class Messengers(FrontLines):
    def links(self):
        return world_happenings.links(world_threads.view(self.world))

    async def sent(self, tone="warned", assault=False):
        """Someone the player wronged has sent a person; the clock has just reached them."""
        await self.begin()
        self.world["flags"].pop("active_npc_id", None)
        if assault:
            bold_acts.remember(self.session, "assault", "biri üzerine yürüdü", victim_id=self.npc["id"])
        link = world_happenings.tie(self.world, world_happenings.CALLER, tone, self.npc, self.world["location"])
        campaign_time.advance(self.world, link["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        self.client.front = {"kind": "look"}
        return link

    def caller(self, link):
        return next((npc for npc in self.world["npcs"] if npc.get("caller_of") == link["thread_id"]), None)

    async def test_a_messenger_says_who_sent_them_why_and_what_is_wanted(self):
        link = await self.sent(assault=True)
        out = await self.line("etrafa bi bakiyim")
        self.assertIn(world_threads.spoken_owner(self.world, {"owner_npc_id": self.npc["id"]}), out["narration"])
        self.assertIn("Üzerine yürüdüğünü", out["narration"])
        self.assertNotIn("Söylenen söz", out["narration"])
        self.assertIn(self.caller(link)["message"], out["narration"])

    async def test_asked_what_the_news_is_they_say_it_again_from_python_too(self):
        link = await self.sent(assault=True)
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        said = interaction_adventure.immersive_unknown(visitor, "haber ne, lafi dolandirma?")
        self.assertIn(visitor["message"], said)

    async def test_they_say_it_and_go_and_are_not_in_the_room_hours_later(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        here = self.world["location"]
        self.assertEqual(visitor["location"], here)
        self.client.front = {"kind": "speak_to", "person_id": visitor["id"]}
        await self.line("ne istiyosun")
        self.assertEqual(visitor["location"], here)
        out = await self.line("sen kimsin ya")
        self.assertEqual(visitor["location"], link["place_id"] if link["place_id"] != here else here, out["narration"])
        self.assertIsNot(self.world["flags"].get("active_npc_id"), visitor["id"])

    async def test_walked_away_from_they_are_gone_when_the_player_comes_back(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        visitor["came_from"] = "elsewhere"
        self.world["location"], here = "other", self.world["location"]
        campaign_time.advance(self.world, 3600, "rest", "test")
        await self.line("etrafa bi bakiyim")
        self.assertEqual(visitor["location"], "elsewhere")

    async def test_the_same_visitor_line_does_not_come_twice_running(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        first = self.caller(link)["message"], self.world["flags"].get("turn_index")
        words = world_threads.job_lines("link", "caller")
        self.assertGreaterEqual(len(words["warned"]), 3)
        self.assertGreaterEqual(len(words["messages"]["warned"]), 3)
        lines = {world_happenings._caller_line(self.world, {"thread_id": f"link_{n:03d}", "tone": "warned"}, words)
                 for n in range(1, 4)}
        self.assertEqual(len(lines), 3)
        self.assertTrue(first)

    async def test_a_second_caller_waits_until_the_first_has_gone(self):
        link = await self.sent()
        other = world_happenings.tie(self.world, world_happenings.CALLER, "opened", {"id": "npc_other"},
                                     self.world["location"])
        campaign_time.advance(self.world, other["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        await self.line("etrafa bi bakiyim")
        callers = [npc for npc in self.world["npcs"] if npc.get("caller_of")]
        self.assertEqual(len(callers), 1, callers)
        self.assertTrue(link)


class ReadingClient(PlayClient):
    """A reading on top of the scripted person."""

    def __init__(self, front, **kwargs):
        super().__init__(**kwargs)
        self.front = front

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties", {})
        if "front" not in properties:
            return super().chat(*args, **kwargs)
        filled = {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none", "answer": "none",
                  "inside": False, **self.front}
        return {"message": {"content": json.dumps({"intent": "narrative", "action": "narrative", "target": {
            "type": "none", "reference": "", "npc_id": "", "evidence_quote": ""}, "completion": "unclear",
            "confidence": 1.0, "front": filled}, ensure_ascii=False)}}


class TheLawFindsTheKiller(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = OneTownScene.asyncSetUp, OneTownScene.asyncTearDown
    post_scene_turn, begin, say = OneTownScene.post_scene_turn, OneTownScene.begin, OneTownScene.say
    add_person, town, killed_earlier, wait = (OneTownScene.add_person, OneTownScene.town,
                                              OneTownScene.killed_earlier, OneTownScene.wait)
    guard_told_by_witness = GuardsActOnWhatTheyKnow.guard_told_by_witness
    deed = GuardsActOnWhatTheyKnow.deed

    async def stopped(self):
        """A witness told a guard, the guard has walked up and asked: the player has the next word."""
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=20):
            out = await self.wait("iki saat bekliyorum")
        self.assertIn("Dur bakalım", out["narration"])
        return guard

    async def held(self):
        guard = await self.stopped()
        out = await self.say("ben dun tapinakta calistim, rahibe sor", PlayClient(spoken="Dinliyorum."))
        self.assertIn("karakola", out["narration"].casefold())
        self.assertFalse(self.world["combat"]["active"])
        return guard

    async def test_the_question_is_followed_by_an_arrest_not_a_shrug(self):
        guard = await self.held()
        self.assertIn("tutukluyorsun", bold_acts.speech_note(self.world, guard))

    async def test_talking_on_ends_in_a_fight(self):
        guard = await self.held()
        await self.say("yanlis adam bu", PlayClient(spoken="Yürü."))
        out = await self.say("dur bir konusalim", PlayClient(spoken="Yeter."))
        self.assertTrue(self.world["combat"]["active"], out["narration"])
        self.assertTrue(guard["hostile"])

    async def test_a_blow_is_a_fight_through_the_normal_door(self):
        guard = await self.held()
        guard.update(current_hp=80, max_hp=80)
        out = await self.say(f"{guard['name'].lower()}a saldiriyorum", PlayClient())
        self.assertTrue(self.world["combat"]["active"], out["narration"])

    async def test_walking_off_is_flight_and_a_good_roll_gets_away(self):
        guard = await self.held()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            out = await self.say("tuz hanindan cikiyorum, sokaga", PlayClient())
        self.assertNotEqual(self.world["location"], "inn", out["narration"])
        self.assertFalse(self.world["combat"]["active"], out["narration"])
        self.assertNotIn("hold", self.deed())
        self.assertIn("izini", out["narration"])
        self.assertTrue(world_reactions._lost_sight(self.world, guard))

    async def test_a_bad_roll_and_the_guard_has_caught_up(self):
        guard = await self.held()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):
            out = await self.say("tuz hanindan cikiyorum, sokaga", PlayClient())
        self.assertEqual(guard["location"], self.world["location"], out["narration"])
        self.assertTrue(self.world["combat"]["active"], out["narration"])

    async def test_a_bribe_that_lands_costs_the_coin_and_ends_the_arrest(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        client = ReadingClient({"kind": "speak_to", "person_id": guard["id"], "coin_cp": 500}, spoken="Hm.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}), patch.object(
                bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            out = await self.say("avucuna bes altin birakiyorum, beni gormedin", client)
        self.assertEqual(self.world["currency"][guard["id"]], 500, out["narration"])
        self.assertIn("500 bakır", out["narration"])
        self.assertNotIn("hold", self.deed())
        self.assertFalse(self.world["combat"]["active"])

    async def test_a_bribe_that_fails_stays_in_the_purse_and_the_arrest_stands(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        client = ReadingClient({"kind": "speak_to", "person_id": guard["id"], "coin_cp": 10}, spoken="Hm.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}), patch.object(
                bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):
            out = await self.say("al sana bir gumus, unut gitsin", client)
        self.assertNotIn(guard["id"], self.world["currency"], out["narration"])
        self.assertIn("hold", self.deed())

    async def test_giving_up_is_a_night_held_and_a_fine_and_it_is_over(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        clock = self.world["campaign_time"]["elapsed_seconds"]
        client = ReadingClient({"kind": "attempt", "deed": "yield"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say("tamam tamam kilici birakiyorum, teslim oluyorum", client)
        self.assertIn("500 bakır", out["narration"])
        self.assertGreaterEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 8 * 3600)
        self.assertEqual(self.world["location"], "post", out["narration"])
        self.assertTrue(self.deed().get("settled"))
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(guard["location"], "post")

    async def test_a_killing_of_someone_who_came_at_the_player_brings_no_arrest(self):
        await self.town()
        self.add_person("Kalila", "Haydut", location="shop", combat_status="dead", current_hp=0, hostile=True)
        self.world["flags"]["deeds"] = [{"kind": "killing", "text": "Kalila öldürüldü", "location": "shop",
                                         "victim_id": "npc_kalila", "witnesses": [], "turn": 3, "at": 0,
                                         "heard": [], "told": []}]
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("hold", self.deed())
