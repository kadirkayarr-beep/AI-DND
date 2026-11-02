"""A paper the player really holds or stands by has words on it, the same words each time.

Real app, real engine; lines are typed the way the owner types them.
"""

from __future__ import annotations

import copy
import json

import bound_text
import town_knowledge
import world_threads
from api.tests.test_front_proposal import FrontTable


class Papers(FrontTable):
    def rows(self):
        return bound_text.items("written_texts")

    def paper(self, name="Eski parşömen", item_id="paper_1"):
        self.world.setdefault("inventory", []).append({"item_id": item_id, "name": name, "quantity": 1})

    def texts(self, *kinds):
        return {row["text"] for row in self.rows() if row["kind"] in kinds}

    async def quiet_town(self):
        await self.begin()
        world_threads.view(self.world)["threads"].clear()

    async def test_a_parchment_in_the_bag_has_real_words_and_keeps_them(self):
        await self.quiet_town()
        self.paper()
        first = await self.line("parsomeni acip okuyom")
        self.assertIn("Kâğıtta şunlar yazıyor", first["narration"])
        self.assertTrue(any(row in first["narration"] for row in self.texts("not", "tehdit", "defter")), first["narration"])
        again = await self.line("parsomeni bi daha okuyom")
        self.assertEqual(again["narration"], first["narration"])

    async def test_what_it_says_is_asked_too(self):
        await self.quiet_town()
        self.paper("Buruşuk makbuz")
        reply = await self.line("makbuzda ne yaziyo")
        self.assertTrue(any(row in reply["narration"] for row in self.texts("makbuz")), reply["narration"])

    async def test_a_look_the_reading_put_on_the_paper_is_a_reading(self):
        await self.quiet_town()
        self.paper()
        self.client.front = {"kind": "look", "thing_word": "parşömen"}
        reply = await self.line("parsomene soyle bi goz gezdiriyim")
        self.assertIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_burning_it_is_not_reading_it(self):
        await self.quiet_town()
        self.paper()
        self.client.front = {"kind": "attempt", "thing_word": "parşömen"}
        reply = await self.line("parsomeni mum alevine tutuyom")
        self.assertNotIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_a_paper_nobody_has_gives_nothing_to_read(self):
        await self.quiet_town()
        reply = await self.line("parsomeni okuyom")
        self.assertNotIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_a_paper_lying_here_is_read_where_it_lies(self):
        await self.quiet_town()
        self.session.create_local_feature({"location": self.world["location"], "name": "Buruşuk not",
                                           "description": "Yerde duran buruşuk bir not.", "aliases": ["not"]})
        reply = await self.line("yerdeki notu okuyom")
        self.assertIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_a_slip_the_screen_just_told_of_has_words_and_stays_out_of_the_bag(self):
        await self.quiet_town()
        self.session.messages.append({"role": "assistant", "content": "Yığının çoğu sararmış teslim fişleri."})
        self.client.front = {"kind": "look", "thing_word": "fiş"}
        first = await self.line("teslim fislerinden birini okuyom")
        self.assertTrue(any(row in first["narration"] for row in self.texts("makbuz")), first["narration"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        self.assertEqual((await self.line("fisi bi daha okuyom"))["narration"], first["narration"])
        self.assertFalse(any("fiş" in str(item.get("name", "")).casefold() for item in self.world["inventory"]
                             if isinstance(item, dict)))

    async def test_a_paper_the_narrator_told_of_a_turn_ago_is_read(self):
        await self.quiet_town()
        self.world["flags"].update(active_npc_id=None, last_npc_id=None, active_npc_until_turn=-1)
        self.npc["location"] = "elsewhere"
        self.session.recent_dm_narrations.append("sokağın kenarında sararmış bir yığın eski kâğıt görünüyor.")
        self.client.front = {"kind": "look", "thing_word": "kağıt"}
        reply = await self.line("yerdeki eski bir kagidi okuyom")
        self.assertIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_a_paper_with_its_own_saved_words_keeps_them(self):
        await self.quiet_town()
        self.session.create_local_feature({"location": self.world["location"], "name": "Yıpranmış Defter",
                                           "description": "Açık bir defter.", "text": "Kapı kilitsiz.", "aliases": ["defter"]})
        self.session.recent_dm_narrations.append("köşede yıpranmış bir defter duruyor.")
        reply = await self.line("yipranmis defteri okuyorum")
        self.assertIsNone(self.world.get(bound_text.KEY))
        self.assertIn("Kapı kilitsiz.", reply["narration"])

    async def test_a_whisper_is_no_paper(self):
        await self.quiet_town()
        self.session.messages.append({"role": "assistant", "content": "Köşeden bir fısıltı geliyor."})
        self.client.front = {"kind": "look"}
        reply = await self.line("fisiltiyi okuyom")
        self.assertNotIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_the_board_stays_the_board_when_the_screen_spoke_of_it(self):
        await self.begin()
        self.thread["place_id"] = self.a_place()
        self.session.messages.append({"role": "assistant", "content": "Köşedeki ilan panosuna yeni kâğıtlar çivilenmiş."})
        reply = await self.line("ilan panosunda ne yaziyo bi bakiyim")
        self.assertIn("Panoya çivili", reply["narration"])

    async def test_asking_someone_what_a_paper_says_is_for_them_to_answer(self):
        await self.quiet_town()
        self.paper()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("usta bu parsomende ne yaziyo?")
        self.assertNotIn("Kâğıtta şunlar yazıyor", reply["narration"])

    async def test_reading_moves_no_coin_no_clock_no_bag_and_no_quest(self):
        await self.quiet_town()
        self.paper("Buruşuk makbuz")
        before = copy.deepcopy((self.world["inventory"], self.world.get("time_state"), self.world.get("quests")))
        await self.line("makbuzu okuyom")
        self.assertEqual((self.world["inventory"], self.world.get("time_state"), self.world.get("quests")), before)

    async def test_the_question_it_leaves_never_reaches_the_screen_or_the_narrator(self):
        await self.quiet_town()
        self.paper()
        reply = await self.line("parsomeni okuyom")
        self.client.front = {"kind": "attempt"}
        await self.line("masaya yaslanip etrafi dinliyom")
        said = json.dumps(self.client.message_batches, ensure_ascii=False) + reply["narration"]
        for row in self.rows():
            self.assertNotIn(row["leaves_question"], said)

    async def test_no_row_with_a_person_in_it_is_filled_without_a_bond(self):
        await self.begin()
        for number in range(40):
            choice = bound_text.choose_paper(self.world, f"p{number}", ["not", "tehdit", "defter", "makbuz", "ilan"])
            self.assertTrue(choice is None or "{" not in choice["text"])

    async def test_a_row_with_work_in_it_names_a_real_job_and_the_job_is_heard(self):
        await self.begin()
        self.thread["place_id"] = "location_bound"
        self.world["locations"]["location_bound"] = {
            "id": "location_bound", "name": "Ay Sofrası Atölyesi", "place_kind": "workshop", "scene_kind": "building",
            "parent_location_id": self.world["location"]}
        self.paper("Eski defter")
        reply = await self.line("defteri okuyom")
        self.assertIn("Ay Sofrası Atölyesi", reply["narration"])
        self.assertEqual(self.thread["status"], "heard")

    async def test_choosing_a_paper_writes_nothing(self):
        await self.begin()
        before = copy.deepcopy(self.world)
        bound_text.choose_paper(self.world, "item:x", ["not"])
        self.assertEqual(self.world, before)

    async def test_a_board_shows_a_public_notice_beside_the_work_and_the_same_one_again(self):
        await self.begin()
        self.thread["place_id"] = self.a_place()
        first = town_knowledge.read_board(self.world)
        notices = {row["text"] for row in self.rows() if row["public"]}
        self.assertIn(self.thread["public_line"], first)
        self.assertEqual(town_knowledge.read_board(self.world), first)
        self.assertFalse(any(row["text"] in first for row in self.rows() if not row["public"]))
        self.assertTrue(notices)

    async def test_taking_a_paper_and_reading_it_in_one_line_does_both(self):
        await self.quiet_town()
        self.session.messages.append({"role": "assistant", "content": "Çekmecede katlanmış eski bir parşömen duruyor."})
        self.client.front = {"kind": "take", "thing_word": "parşömen"}
        reply = await self.line("parsomeni alip okuyom")
        self.assertTrue(any("parşömen" in str(item.get("name", "")).casefold() for item in self.world["inventory"]
                            if isinstance(item, dict)), self.world["inventory"])
        self.assertIn("Kâğıtta şunlar yazıyor", reply["narration"])
