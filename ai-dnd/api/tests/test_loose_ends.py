"""What a town's work comes to when the player talks the way people talk.

Every line here is the kind of thing typed in play. No real model is called.
"""
import unittest
from unittest.mock import patch

import campaign_time
import living_world
import pocket
import world_threads
from adventure import dialogue_jobs

from api.tests import test_play_consequences as consequences
from api.tests import test_story_links as links
from api.tests import test_thread_gate as gate_tests
from api.tests.test_world_threads import DAY


class ATroubleFromAnOldSave(unittest.TestCase):
    def test_taken_on_and_left_it_still_comes_to_an_end(self):
        world, state = links.town_with_trouble()
        thread = links.thread_at(state)
        thread.pop("fires_at", None)
        thread["terms"]["work_days"] = None
        links.resident(world, thread["place_id"])
        self.assertTrue(world_threads.transition(thread, "offered"))
        self.assertTrue(world_threads.accept_hired(world, thread, 0))
        self.assertEqual(thread["terms"]["work_days"], 1)
        campaign_time.advance(world, 3 * DAY, "wait", "test")
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "failed")


class ReadingIsSomethingYouDo(consequences.OnTheJob):
    carrying = consequences.Sealed.carrying

    async def test_a_line_that_is_not_reading_leaves_the_seal_alone(self):
        for line in ("mektubu okumadım, mühür duruyor", "Ne yazık ki mektup elimde değil", "mektubu okumak istemiyorum",
                     "mektubu okudum sanma", "mektubu okuyamam", "mektubu okumayacağım", "mektubu yazanı tanıyor musun",
                     "mektupta ne yazıyor", "mektupta ne yazıyor?", "mektubu okuyayım mı"):
            await self.carrying()
            out = await self.line(line, "Hmm.")
            self.assertIsNone(self.thread.get("seal_broken"), line)
            self.assertNotIn("Kâğıtta", out["narration"], line)

    async def test_reading_it_for_real_still_reads_it(self):
        for line in ("mektubu okuyom", "mührü kırıp mektubu okudum", "mektubu okuyayım", "mektubu açıp okuyorum"):
            await self.carrying()
            out = await self.line(line, "Hmm.")
            self.assertIs(self.thread.get("seal_broken"), True, line)
            self.assertIn("Kâğıtta", out["narration"], line)

    async def test_a_question_with_someone_in_front_of_you_is_theirs_even_for_an_open_note(self):
        await self.carrying(template="meeting_note", noun="not")
        out = await self.line("notta ne yazıyor?", "Bilmem, kapalıydı.")
        self.assertNotIn("Kâğıtta", out["narration"])

    async def test_alone_with_an_open_note_the_question_is_answered_by_the_note(self):
        await self.carrying(template="meeting_note", noun="not")
        self.world["flags"].pop("active_npc_id", None)
        self.assertIn("Kâğıtta", dialogue_jobs.read_parcel(self.session, "notta ne yazıyor?")["narration"])


class Bag:
    """Only what pocket reads of a session."""

    def __init__(self):
        self.character = {"current_hp": 9}
        self.messages = []
        self.world_state = {
            "inventory": [{"item_id": "parcel:job:abc", "name": "Mektup", "quantity": 1},
                          {"item_id": "item_torch", "name": "Meşale", "quantity": 1}],
            "equipment": {}, "flags": {}, "combat": {}, "npcs": [], "location": "kapi",
            world_threads.KEY: {"version": world_threads.SCHEMA_VERSION, "threads": [{"quest_id": "job:abc", "status": "accepted"}]},
        }

    def names(self):
        return [item["name"] for item in self.world_state["inventory"]]

    def thread(self):
        return self.world_state[world_threads.KEY]["threads"][0]


class ThrowingNeedsAThingThrown(unittest.TestCase):
    def test_a_turn_of_phrase_with_at_in_it_throws_nothing(self):
        for line in ("mektuba göz atıyorum", "meşaleyle bir adım atıp kapıya bakıyorum", "mektubu alıp bir göz atıyorum",
                     "mektuba imza atıyorum", "mektubu okuyup kahkaha atıyorum", "mesela meşaleyi verdim atıyorum",
                     "meşaleyi yakıyorum", "meşaleyi yakıp ilerliyorum", "mektubu fırlatmıyorum"):
            bag = Bag()
            self.assertIsNone(pocket.resolve(bag, line), line)
            self.assertEqual(bag.names(), ["Mektup", "Meşale"], line)
            self.assertNotIn("parcel_gone", bag.thread(), line)

    def test_a_real_throw_is_told_on_the_screen(self):
        for line, gone in (("mektubu denize atıyorum", "Mektup"), ("meşaleyi yere fırlatıyorum", "Meşale"),
                           ("mektubu yırtıyorum", "Mektup"), ("mektubu yakıyorum", "Mektup"),
                           ("meşaleyi alıp kuyuya atıyorum", "Meşale")):
            bag = Bag()
            out = pocket.resolve(bag, line)
            self.assertNotIn(gone, bag.names(), line)
            self.assertIn(gone, out["narration"], line)
            self.assertEqual(out["model_calls"], 0, line)
        self.assertNotIn("parcel_gone", bag.thread())

    def test_a_parcel_goes_only_when_it_is_thrown_somewhere(self):
        bag = Bag()
        self.assertIsNone(pocket.resolve(bag, "mektubu atıyorum"))
        self.assertIn("Mektup", bag.names())
        pocket.resolve(bag, "meşaleyi atıyorum")
        self.assertNotIn("Meşale", bag.names())


class SettingAParcelDown(consequences.OnTheJob):
    carrying = consequences.Sealed.carrying

    async def at_the_door(self):
        await self.carrying()
        self.world["location"] = "place_x"
        self.world["flags"].pop("active_npc_id", None)
        self.world["flags"].pop("last_npc_id", None)

    async def test_put_down_for_the_one_it_is_for_it_is_delivered(self):
        await self.at_the_door()
        await self.line("mektubu masaya atıyorum", "Hmm.")
        self.assertEqual(self.status(), "done")
        self.assertNotIn("parcel_gone", self.thread)

    async def test_in_the_owners_face_it_is_still_in_hand(self):
        await self.carrying()
        await self.line("mektubu önüne atıyorum", "Hmm.")
        self.assertTrue(dialogue_jobs.holds_parcel(self.world, self.thread))
        self.assertNotIn("parcel_gone", self.thread)


if __name__ == "__main__":
    unittest.main()
