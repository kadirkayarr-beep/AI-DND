"""What a town's work comes to when the player talks the way people talk.

Every line here is the kind of thing typed in play. No real model is called.
"""
import unittest
from unittest.mock import patch

import campaign_time
import living_world
import local_dialogue
import pocket
import town_knowledge
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


class OnATrouble(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = links.InPlay.asyncSetUp
    asyncTearDown = links.InPlay.asyncTearDown
    campaign_with_npc = links.InPlay.campaign_with_npc
    open_job = links.InPlay.open_job
    line = links.InPlay.line
    status = links.InPlay.status
    trouble = links.InPlay.trouble


class TakingATroubleOn(OnATrouble):
    """A line has to be an offer of help, about something the player knows of."""

    async def test_nothing_is_taken_on_by_a_question_a_maybe_or_a_price(self):
        for line in ("yükünü taşımana yardım edeyim mi?", "yardım edeyim mi", "yardımcı olabilirim ama ne kadar verirsin?",
                     "ben bakayım bir düşüneyim", "belki yardım ederim", "hallederim ama para isterim",
                     "yardım ederim de ne kadar kazanırım"):
            await self.trouble()
            await self.line(line, "Hmm.", mode="say", target=True)
            self.assertNotEqual(self.status(), "accepted", line)
            self.assertIn("fires_at", self.thread, line)

    async def test_a_trouble_nobody_mentioned_cannot_be_stepped_into(self):
        await self.trouble()
        self.thread.update(status="open", heard_turn=None)
        await self.line("derdini ben hallederim", "Ne derdi?", mode="say", target=True)
        self.assertIn(self.status(), world_threads.PUBLIC)
        self.assertIn("fires_at", self.thread)

    async def test_the_one_who_just_told_it_can_be_answered(self):
        await self.trouble()
        self.thread.update(status="open", heard_turn=None)
        await self.line("derdin ne senin", "Hesap tutmuyor işte, bakan biri lazım.", mode="say", target=True)
        await self.line("tamam ben hallederim", "Sağ ol.", mode="say", target=True)
        self.assertEqual(self.status(), "accepted")


class ABareYesToAModelsId(OnATrouble):
    async def proposal(self, last_line, said):
        await self.trouble()
        self.world["npc_speech_log"] = {self.npc["id"]: [{"player": "selam", "npc": last_line}]}
        taken = []
        town_knowledge.settle_reply(self.world, self.npc, said, {"kind": "job_accepted", "thread_id": self.thread["thread_id"]},
                                    "Oldu.", accept_job=taken.append)
        return taken

    async def test_it_does_not_bind_a_trouble_when_the_question_was_something_else(self):
        self.assertEqual(await self.proposal("Yorgun görünüyorsun, bir oturur musun?", "evet"), [])

    async def test_it_binds_when_the_trouble_was_just_put_to_the_player(self):
        self.assertTrue(await self.proposal("Hesap tutmuyor, bakan biri lazım. Bakar mısın?", "evet"))

    async def test_real_words_are_enough_whatever_came_before(self):
        self.assertTrue(await self.proposal("Yorgun görünüyorsun.", "tamam derdini ben hallederim"))


class ALaterPromiseIsNotAShift(OnATrouble):
    async def taken_on(self):
        await self.trouble()
        await self.line("yardım edeyim", "Sağ ol.", mode="say", target=True)
        self.assertEqual(self.status(), "accepted")

    async def test_promising_it_for_later_runs_no_clock(self):
        for line in ("merak etme derdini hallederim", "derdini yarın hallederim", "derdini sonra hallederim",
                     "işi yarın yaparım", "yarın işe başlayalım", "işe başlayalım, yarın sabah", "bu işi haftaya yapıyorum"):
            await self.taken_on()
            before = world_threads._now(self.world)
            out = await self.line(line, "İyi.", mode="say", target=True)
            self.assertNotEqual(out["turn_outcome"]["action"], "work", line)
            self.assertEqual(world_threads._now(self.world), before, line)
            self.assertEqual(self.status(), "accepted", line)

    async def test_doing_it_now_still_does_it(self):
        for line in ("dediğin işi yapıyorum", "derdini halledeyim o zaman, işi yapayım"):
            await self.taken_on()
            out = await self.line(line, "Hmm.")
            self.assertEqual(out["turn_outcome"]["action"], "work", line)


class WhatFollowsBenIsNotAlwaysAName(unittest.TestCase):
    def test_a_lowercase_word_after_ben_that_says_something_is_no_name(self):
        for line in ("ben bulurum", "ben görürüm", "ben yürürüm", "ben alırım", "ben varım", "ben yaptım", "ben geldim",
                     "ben olurum", "ben götürürüm", "ben korurum", "ben halledicem", "ben karışmam", "ben yorgunum",
                     "ben hazırım", "ben burdayım", "ben burda", "tamam ben kadir", "peki ben gelirim"):
            self.assertIsNone(local_dialogue.explicit_player_name_disclosure(line), line)

    def test_a_name_on_its_own_still_is_one(self):
        for line, name in (("ben ahmet", "ahmet"), ("selam ben ahmet", "ahmet"), ("ben Kerim", "Kerim"), ("Ben Alırım", "Alırım")):
            self.assertEqual(local_dialogue.explicit_player_name_disclosure(line), name)


class ATroubleIsItsOwnersOwn(unittest.TestCase):
    def owner(self):
        world, state = links.town_with_trouble()
        thread = links.thread_at(state)
        return world, thread, links.resident(world, thread["place_id"])

    def test_what_is_coming_is_said_in_the_first_person(self):
        world, thread, npc = self.owner()
        thread.update(public_line="Burası bir dertteymiş, Usta ondan yakınıyor.",
                      owner_line="Yardımcım iki gündür gelmedi. İstersen Dalia ile konuş.")
        waiting = town_knowledge.speech_note(world, npc).split("Seni bekleyen:")[1]
        self.assertIn("Yardımcım iki gündür gelmedi;", waiting)
        self.assertNotIn("yakınıyor", waiting)
        self.assertNotIn("İstersen", waiting)

    def test_afterwards_it_happened_to_them_it_is_not_something_they_heard(self):
        world, thread, npc = self.owner()
        state, closed = links.fire(world, thread)
        row = state["happenings"][-1]
        self.assertEqual(world_threads.recent_closed(world, npc), [closed])
        note = town_knowledge.speech_note(world, npc)
        self.assertIn("başına geldi", note)
        self.assertNotIn(row["line"], note)

    def test_someone_next_door_still_only_heard_it(self):
        world, thread, npc = self.owner()
        state, closed = links.fire(world, thread)
        other = links.resident(world, thread["place_id"], "komsu")
        other.pop("place_role_of")
        self.assertIn(state["happenings"][-1]["line"], town_knowledge.speech_note(world, other))


if __name__ == "__main__":
    unittest.main()
