"""What the last long play tripped over, replayed with the player's own lines.

Each test goes through the HTTP turn with a mocked model, so it proves what
Python does on its own: no raw error, no second reading of the player's words.
"""

import local_places
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests

HOUR = 3600


class SecondRestTests(ThreePlaysTests):
    def elapsed(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def rested(self):
        await self.begin(FIGHTER)
        await self.say("sabaha kadar uyuyorum")
        self.assertIn("last_long_rest_completed_at", self.world)
        self.session.character["current_hp"] = 12

    async def test_a_second_sleep_too_soon_is_a_story_and_gives_nothing(self):
        await self.rested()
        before = self.elapsed()
        out = await self.say("8 saat uyuyorum")
        self.assertEqual(self.session.character["current_hp"], 12, out["narration"])
        self.assertEqual(self.elapsed() - before, 8 * HOUR, out["narration"])
        self.assertTrue(out["narration"].strip())
        self.assertNotIn("16", out["narration"])

    async def test_a_rest_long_enough_to_cover_the_gap_is_a_real_rest(self):
        await self.rested()
        self.world["campaign_time"]["start_second"] = 7 * HOUR  # morning, as in the play
        before = self.elapsed()
        out = await self.say("bi gün ortadan kayboluyum en iyisi, 24 saat dinleniyorum")
        self.assertEqual(self.elapsed() - before, 24 * HOUR, out["narration"])
        self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"], out["narration"])
        self.assertEqual(self.world["last_long_rest_completed_at"], self.elapsed())

    async def test_the_line_from_the_play_gets_a_reply(self):
        await self.rested()
        out = await self.say("bi gün ortadan kayboluyum en iyisi, ertesi sabaha kadar dinleniyorum")
        self.assertTrue(out["narration"].strip())


class KnockOutTests(ThreePlaysTests):
    """PHB 2024: a melee blow that would drop someone to 0 can leave them at 1 HP, Unconscious."""

    async def nearly_down(self, hp=1):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.session.character.update(current_hp=300, max_hp=300)
        self.foe = self.add_person("Dorn", "Nöbetçi çavuş", current_hp=500, max_hp=500, armor_class=1,
                                   inventory=[], coins_cp=8)
        await self.say("çavuşa yumrukla saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])
        self.foe["current_hp"] = hp
        for record in self.world["combat"]["participant_records"]:
            if record["id"] == self.foe["id"]:
                record["current_hp"] = hp

    async def strike_until_down(self, line):
        for _ in range(12):
            out = await self.say(line, PlayClient(intent="attack"))
            if self.foe["combat_status"] != "active":
                return out
        self.fail("the blow never landed")

    async def test_the_line_from_the_play_leaves_him_alive_and_out(self):
        for line in ("öldürmicem. kılıcın kabzasıyla şakağına vurup bayıltıyorum",
                     "yumrukla bayıltıyorum", "öldürmeden indiriyorum, kılıcın yan yüzüyle vuruyorum"):
            with self.subTest(line=line):
                await self.nearly_down()
                out = await self.strike_until_down(line)
                self.assertEqual(self.foe["combat_status"], "unconscious", out["narration"])
                self.assertEqual(self.foe["current_hp"], 1)
                self.assertNotIn("ölür", out["narration"])
                self.assertIn("bilincini kaybeder", out["narration"])
                self.assertFalse(self.world["combat"]["active"])

    async def test_no_killing_said_once_holds_for_the_fight(self):
        await self.nearly_down(500)
        await self.say("bi daha vuruyorum, öldürmek yok, yumruk", PlayClient(intent="attack"))
        self.foe["current_hp"] = 1
        for record in self.world["combat"]["participant_records"]:
            if record["id"] == self.foe["id"]:
                record["current_hp"] = 1
        out = await self.strike_until_down("vur vur")
        self.assertEqual(self.foe["combat_status"], "unconscious", out["narration"])

    async def test_a_plain_blow_still_kills(self):
        await self.nearly_down()
        out = await self.strike_until_down("çavuşa vuruyorum")
        self.assertEqual(self.foe["combat_status"], "dead", out["narration"])
        self.assertIn("ölür", out["narration"])

    async def test_changing_your_mind_kills(self):
        await self.nearly_down(500)
        await self.say("çavuşu bayıltıyorum", PlayClient(intent="attack"))
        self.foe["current_hp"] = 1
        for record in self.world["combat"]["participant_records"]:
            if record["id"] == self.foe["id"]:
                record["current_hp"] = 1
        out = await self.strike_until_down("yeter, öldürüyorum bu adamı")
        self.assertEqual(self.foe["combat_status"], "dead", out["narration"])

    async def test_the_one_out_cold_is_searched_and_described_not_called_dead(self):
        await self.nearly_down()
        await self.strike_until_down("yumrukla bayıltıyorum")
        out = await self.say("etrafa bakıyorum", PlayClient())
        self.assertIn("baygın", out["narration"])
        out = await self.say("üstünü arıyorum para var mı", PlayClient())
        self.assertEqual(out["turn_outcome"]["action"], "loot", out["narration"])

    async def test_he_wakes_after_about_an_hour(self):
        await self.nearly_down()
        await self.strike_until_down("yumrukla bayıltıyorum")
        await self.say("iki saat bekliyorum", PlayClient())
        await self.say("etrafa bakıyorum", PlayClient())
        self.assertEqual(self.foe["combat_status"], "active")
        self.assertEqual(self.foe["current_hp"], 1)
        self.assertNotIn("unconscious", self.foe.get("conditions", []))


class EnteringWhereYouStandTests(ThreePlaysTests):
    async def town(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        city = self.world["location"]
        self.temple = local_places.create_local_place(self.world, city, "temple", name="Çilovesa Tapınağı")
        post = local_places.create_local_place(self.world, city, "archive", name="Rovelan Karakolu")
        self.inn = local_places.create_local_place(self.world, city, "smithy", name="Göl Sofrası Hanı")
        self.world.setdefault("doors", []).append({
            "id": f"venue-door:{self.inn['id']}", "name": "Göl Sofrası Hanı Kapısı",
            "description": "Göl Sofrası Hanı Kapısı", "location": city, "place_id": self.inn["id"],
            "destination_location_id": self.inn["id"], "open": True, "locked": False, "broken": False,
        })
        self.world["location"] = post["id"]
        return city

    async def test_in_goes_where_the_walk_ended_not_to_the_only_door_in_town(self):
        city = await self.town()
        out = await self.say("hızlıca dışarı çıkıyorum, kılıcı silip tapınağa gidiyorum sanki bişey olmamış gibi")
        self.assertIn("Çilovesa", out["narration"])
        self.assertEqual(self.world["location"], city)
        out = await self.say("içeri giriyorum")
        self.assertEqual(self.world["location"], self.temple["id"], out["narration"])

    async def test_a_plain_door_still_opens_when_you_stand_at_nothing_else(self):
        await self.town()
        self.world["location"] = self.world["locations"][self.inn["id"]]["parent_location_id"]
        out = await self.say("içeri giriyorum")
        self.assertEqual(self.world["location"], self.inn["id"], out["narration"])
