"""What the world says it does, it does: the things a long play found saying one thing and doing another.

Every line is the kind of thing the owner types. No real model is called.
"""
from unittest.mock import patch

import bold_acts
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
