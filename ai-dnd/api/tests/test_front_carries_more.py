"""Roadmap step 5, second part: the front reading comes before the planner and the old word-list owners.

Real app, real adapter, real engine; only the Ollama client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

from api.tests.test_front_proposal import FrontTable


class ReadsBeforeThePlanner(FrontTable):
    async def test_a_place_named_in_a_question_to_someone_does_not_walk_the_player(self):
        await self.begin()
        where = self.world["location"]
        place = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line(f"usta yirtik sayfalari soruyorum yine. biri bi kayit ariyormus, {place} tarafinda "
                                "son gorulmus. senin defterden mi gitti o sayfalar")
        self.assertEqual(self.world["location"], where)
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_a_threat_with_otur_in_it_is_said_not_sat(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("efendinle gorusmeden bunu vermiyorum. geceleri zifiri karanlikta otur istersen")
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["owner"], "dialogue")

    async def test_a_line_that_also_wants_a_proposal_is_read_once_and_the_reply_carries_it(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        await self.line("sana söz veriyorum, paketi yarın getiririm")
        self.assertEqual(len(self.front_calls()), 1)
        self.assertIn("interaction", self.front_calls()[0]["properties"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_the_cap_counts_a_reading_taken_before_the_planner(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("usta bu kasabada kim kimle tanisir, sor bakalim sana sorayim")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.client.chat_calls, len(self.client.schemas))
        self.assertLessEqual(self.client.chat_calls, 2)


class ReadsBeforeTheOldOwners(FrontTable):
    async def test_lighting_a_lantern_is_no_arson(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        await self.line("kandil malzemesini acip sonuk fenere yag koyup yakiyorum")
        self.assertNotEqual(self.routes()[-1]["owner"], "arson")
        self.assertFalse(self.world["flags"].get("fires"))

    async def test_a_fire_the_model_read_is_still_a_fire(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "burn"}
        await self.line("su dukkani bastan asagi tutusturuyorum")
        self.assertEqual(self.routes()[-1]["owner"], "arson")

    async def test_a_glance_at_a_purse_is_no_theft(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("adamin kesesine bi goz atiyorum, dolu mu diye")
        self.assertNotEqual(self.routes()[-1]["owner"], "theft")

    async def test_a_theft_the_word_list_never_heard_is_still_a_theft(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "steal"}
        await self.line("kalabaligi firsat bilip adamin belindekini usulca kendime katiyorum")
        self.assertEqual(self.routes()[-1]["owner"], "theft")

    async def test_with_no_reading_the_old_words_still_catch_a_fire(self):
        await self.begin()
        self.client.drop_front = True
        await self.line("dukkani atese veriyorum")
        self.assertEqual(self.routes()[-1]["owner"], "arson")

    async def test_what_is_in_my_bag_goes_by_the_reading_however_it_is_said(self):
        await self.begin()
        self.client.front = {"kind": "bag"}
        reply = await self.line("çantama koydum mu duyuruyu bi bakayim")
        self.assertIn("Envanterinde", reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:bag")
        self.assertLessEqual(self.client.chat_calls, 1)

    async def test_what_is_in_the_purse_goes_the_same_way(self):
        await self.begin()
        self.client.front = {"kind": "bag"}
        self.world.setdefault("currency", {})["player"] = 2412
        reply = await self.line("kese ne alemde, kac bakirim var")
        self.assertIn("24 altın 12 bakır", reply["narration"])
