"""What the world says it does, it does: the things a long play found saying one thing and doing another.

Every line is the kind of thing the owner types. No real model is called.
"""
import unittest
from unittest.mock import patch

import bold_acts
from api.tests.test_front_proposal import FrontTable
from api.tests.test_lasting_consequences import OneTownScene
from api.tests.test_three_plays import PlayClient


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
