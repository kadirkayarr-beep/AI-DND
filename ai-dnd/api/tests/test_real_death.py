"""Death is real: one save a turn, a story when you fall, an end you can read.

The lines are the owner's own kind of Turkish. Each test posts through the HTTP
API, because the check play lost its death there, with no text at all.
"""

import unittest
from unittest.mock import patch

import local_places
from api.tests.test_three_plays import BARBARIAN, FIGHTER, PlayClient, ThreePlaysTests


class TheDeadStayDeadTests(ThreePlaysTests):
    async def workshop_with_a_dead_master(self):
        await self.begin(FIGHTER)
        city = self.world["location"]
        place = local_places.create_local_place(self.world, city, "workshop", name="Quenna Atölyesi")
        await self.say("Quenna Atölyesine gidiyorum", PlayClient())
        self.assertEqual(self.world["location"], place["id"])
        master = local_places.resident_of(self.world, place["id"])
        master.update(current_hp=0, combat_status="dead", name="Kalila", name_known_to_player=True)
        await self.say("dışarı çıkıyorum", PlayClient())
        return place, master

    async def test_a_dead_master_is_not_at_the_bench_when_you_come_back(self):
        await self.workshop_with_a_dead_master()
        out = await self.say("quenna atölyesine gidiyorum, gece yanmış mı görcem", PlayClient())
        self.assertNotIn("Kalila burada", out["narration"])
        self.assertIn("kıpırtısız", out["narration"])

    async def corpse_here(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.world.setdefault("currency", {})["player"] = 0
        return self.add_person("Kalila", "Usta", current_hp=0, combat_status="dead",
                               name_known_to_player=True)

    async def test_an_unnamed_corpse_beside_you_is_found_and_searched(self):
        body = await self.corpse_here()
        client = PlayClient(narration="Odada ne bir ceset ne de başka biri bulunuyor.")
        out = await self.say("cesedini arıyorum, üstünde ne varsa alıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertTrue(body["searched"])
        self.assertIn("Kalila", out["narration"])
        self.assertNotIn("ne bir ceset", out["narration"])

    async def test_a_corpse_is_searched_by_name_and_in_plain_words(self):
        for line in ("kalilanın üzerini arıyorum", "kalilanın cesedine bakıyorum", "cesedi soyuyorum",
                     "ölünün ceplerini yokluyorum", "cesede bakıyorum"):
            with self.subTest(line=line):
                body = await self.corpse_here()
                client = PlayClient(narration="Odada ceset yok.")
                await self.say(line, client)
                self.assertEqual(client.calls, 0)
                self.assertTrue(body["searched"])

    async def test_an_emptied_corpse_says_so_and_is_still_there(self):
        await self.corpse_here()
        await self.say("cesedi arıyorum", PlayClient())
        before = self.world["currency"]["player"]
        client = PlayClient(narration="Odada ceset yok.")
        out = await self.say("cesedi bir daha arıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertIn("Kalila", out["narration"])
        self.assertEqual(self.world["currency"]["player"], before)

    async def test_a_corpse_named_elsewhere_is_placed_not_denied(self):
        body = await self.corpse_here()
        city = self.world["location"]
        place = local_places.create_local_place(self.world, city, "workshop", name="Quenna Atölyesi")
        body["location"] = place["id"]
        client = PlayClient(narration="Böyle bir ceset yok.")
        out = await self.say("kalilanın cesedini arıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertIn("Quenna Atölyesi", out["narration"])
        self.assertFalse(body.get("searched"))

    async def test_a_table_top_is_not_a_corpse_search(self):
        body = await self.corpse_here()
        await self.say("masanın üstüne bakıyorum", PlayClient())
        self.assertFalse(body.get("searched"))

    async def test_the_narrator_is_told_who_lies_here(self):
        await self.corpse_here()
        context = self.session.build_world_context()
        self.assertEqual(context["bodies_here"], ["Kalila"])


if __name__ == "__main__":
    unittest.main()
