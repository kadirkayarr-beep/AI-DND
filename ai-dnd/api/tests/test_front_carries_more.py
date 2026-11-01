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
