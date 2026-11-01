"""What the player can know of a job: face to face, on arrival, or from someone who heard."""

from __future__ import annotations

import copy
import unittest

import api.serializers as serializers
import interaction_adventure
import town_knowledge
import world_threads
from api.tests.test_world_threads import city, person, stage

HOUR = 3600
DAY = 86400


def closed_job(seed="seen", status="filled_by_other", **fields):
    world = city(seed)
    world_threads.ensure(world)
    world.setdefault("flags", {})["turn_index"] = 5
    thread = world[world_threads.KEY]["threads"][0]
    thread.update(status=status, type="hiring", offered_at=0, closed_at=0, owner_name="Kalila",
                  filled_by_name="Bren", filled_by_npc_id=None, **fields)
    state = world[world_threads.KEY]
    state["threads"].remove(thread)
    state["history"].append(thread)
    return world, thread


class OnArrival(unittest.TestCase):
    def test_it_comes_once_and_names_the_person(self):
        world, thread = closed_job()
        line = world_threads.arrival_line(world, thread["place_id"])
        self.assertIn("Bren", line)
        self.assertIsNone(world_threads.arrival_line(world, thread["place_id"]))
        self.assertEqual(thread["outcome_known_turn"], 5)

    def test_it_stays_at_the_place_it_belongs_to(self):
        world, _ = closed_job()
        self.assertIsNone(world_threads.arrival_line(world, "city"))

    def test_a_job_nobody_offered_you_is_no_news_to_you(self):
        world, thread = closed_job()
        thread["offered_at"] = None
        self.assertIsNone(world_threads.arrival_line(world, thread["place_id"]))

    def test_an_expired_offer_has_no_arrival_line(self):
        world, thread = closed_job(status="expired")
        self.assertIsNone(world_threads.arrival_line(world, thread["place_id"]))

    def test_a_failed_job_meets_you_at_the_door(self):
        world, thread = closed_job(status="failed")
        self.assertTrue(world_threads.arrival_line(world, thread["place_id"]))


class TheLog(unittest.TestCase):
    def known(self, world):
        return [e for e in interaction_adventure.get(world)["events"] if e["player_known"]]

    def test_the_clock_closing_a_job_tells_the_player_nothing(self):
        world = city("log")
        world_threads.ensure(world)
        thread = stage(world, "offered", expires_at=HOUR, offered_at=0)
        world_threads.tick(world, 2 * HOUR)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "expired")
        self.assertEqual(self.known(world), [])
        self.assertTrue(interaction_adventure.get(world)["events"])

    def test_hearing_it_is_what_puts_it_in_the_log(self):
        world, thread = closed_job()
        self.assertEqual(self.known(world), [])
        world_threads.learn_outcome(world, thread)
        self.assertEqual(len(self.known(world)), 1)
        self.assertEqual(self.known(world)[0]["location_id"], thread["place_id"])

    def test_an_owner_saying_it_counts_as_hearing(self):
        world, thread = closed_job()
        owner = person(world, "owner", thread["place_id"])
        world["location"] = thread["place_id"]
        world["npc_statements"] = None
        town_knowledge.note_mention(world, owner, "O işi başkası aldı.", job_talk=True)
        self.assertEqual(thread["outcome_known_turn"], 5)


class TheWitness(unittest.TestCase):
    def setUp(self):
        self.world, self.thread = closed_job("witness")
        self.world["campaign_time"]["elapsed_seconds"] = HOUR
        self.thread["closed_at"] = 0

    def teller(self):
        for number in range(40):
            npc = {"id": f"npc_{number}", "name": "Han", "role": "Barmen", "location": "city"}
            if any(i["kind"] == "news" for i in town_knowledge.public_knowledge(self.world, npc)):
                return npc
        self.fail("nobody heard")

    def test_news_says_who_and_points_at_the_real_thread(self):
        news = next(i for i in town_knowledge.public_knowledge(self.world, self.teller()) if i["kind"] == "news")
        self.assertEqual(news["thread_id"], self.thread["thread_id"])
        self.assertIn("Bren", news["text"])

    def test_done_and_failed_are_heard_about_too(self):
        for status in ("done", "failed"):
            self.thread["status"] = status
            self.assertTrue(self.teller())

    def test_hearing_it_said_marks_it_learned_by_id_not_by_guess(self):
        npc = self.teller()
        place = self.world["locations"][self.thread["place_id"]]["name"]
        town_knowledge.note_mention(self.world, npc, f"{place} işini Bren kapmış.")
        self.assertEqual(self.thread["outcome_known_turn"], 5)

    def test_naming_the_place_tells_nothing_about_how_the_job_ended(self):
        npc = self.teller()
        place = self.world["locations"][self.thread["place_id"]]["name"]
        for reply in (f"{place} tarafına git, meydanın arkasında.", f"{place} şu yanda."):
            town_knowledge.note_mention(self.world, npc, reply)
            self.assertIsNone(self.thread.get("outcome_known_turn"), reply)
        self.assertFalse([e for e in interaction_adventure.get(self.world)["events"] if "learned" in e.get("kind", "")])
        self.assertTrue(world_threads.arrival_line(self.world, self.thread["place_id"]))

    def test_saying_it_in_other_words_still_counts(self):
        npc = self.teller()
        place = self.world["locations"][self.thread["place_id"]]["name"]
        town_knowledge.note_mention(self.world, npc, f"{place} tarafındaki işi başkası almış diyorlar.")
        self.assertEqual(self.thread["outcome_known_turn"], 5)

    def test_the_news_goes_stale(self):
        self.world["campaign_time"]["elapsed_seconds"] = 2 * DAY
        for number in range(40):
            npc = {"id": f"npc_{number}", "name": "Han", "role": "Barmen", "location": "city"}
            self.assertFalse(any(i["kind"] == "news" for i in town_knowledge.public_knowledge(self.world, npc)))


class WhatNeverShows(unittest.TestCase):
    def test_a_job_in_hand_is_not_street_talk(self):
        for status in ("offered", "accepted", "declined"):
            world = city(f"street-{status}")
            world_threads.ensure(world)
            thread = stage(world, status, expires_at=DAY)
            self.assertNotIn(thread["thread_id"], [t["thread_id"] for t in world_threads.active(world)])
            for number in range(10):
                npc = {"id": f"npc_{number}", "name": "Han", "role": "Barmen", "location": "city"}
                self.assertNotIn(thread["thread_id"],
                                 [i["thread_id"] for i in town_knowledge.public_knowledge(world, npc)])
            self.assertNotEqual((world_threads.street_talk(world, "city") or {}).get("thread_id"), thread["thread_id"])

    def test_nine_later_closings_do_not_lose_the_one_you_are_owed(self):
        world, thread = closed_job()
        state = world[world_threads.KEY]
        for number in range(9):
            state["history"].append(dict(copy.deepcopy(thread), thread_id=f"later_{number}", offered_at=None))
            world_threads._trim_history(state)
        self.assertIsNotNone(world_threads.by_id(world, thread["thread_id"]))
        self.assertTrue(world_threads.arrival_line(world, thread["place_id"]))

    def test_the_tone_is_a_word_not_a_figure(self):
        world, thread = closed_job()
        owner = person(world, "owner", thread["place_id"])
        world["location"] = thread["place_id"]
        world["relationships"] = {"owner": {"score": 3, "events": ["a"]}}
        note = town_knowledge.speech_note(world, owner)
        self.assertIn("ısınmışsın", note)
        self.assertNotIn("3", note.split("ısınmışsın")[1][:4])

    def test_the_client_never_sees_the_thread_record(self):
        source = serializers.__file__
        with open(source, encoding="utf-8") as handle:
            self.assertNotIn("world_threads", handle.read())

    def test_a_trouble_owner_offers_no_pay(self):
        world = city("trouble")
        world_threads.ensure(world)
        thread = world[world_threads.KEY]["threads"][0]
        thread.update(type="trouble", owner_line="Komşuyla aramız bozuk.")
        owner = person(world, "owner", thread["place_id"])
        note = town_knowledge.speech_note(world, owner)
        self.assertIn("kimseye para ya da ücret teklif etme", note)
        self.assertEqual(world_threads.jobs_of(world, owner), [])


if __name__ == "__main__":
    unittest.main()
