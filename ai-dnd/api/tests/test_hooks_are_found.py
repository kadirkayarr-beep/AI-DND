"""A hook reaches a player who reads no save: people, a board in the street and a paper on the door point to it."""
import unittest

import game
import town_knowledge
import world_happenings
import world_threads

from api.tests.test_said_is_real import ClassifiedClient, Table
from api.tests.test_story_links import resident, town
from unittest.mock import patch


def work_town(seed="seed-hooks"):
    world, state = town(seed)
    jobs = [t for t in state["threads"] if t["type"] in {"hiring", "errand"}]
    return world, state, jobs


def seeded_with_two_jobs():
    for number in range(100):
        world, state, jobs = work_town(f"seed-hooks-{number}")
        if len(jobs) >= 2:
            return world, state, jobs
    raise AssertionError("no town with two jobs")


def passer_by(world, npc_id="gecen"):
    npc = {"id": npc_id, "name": "Geçen", "role": "yolcu", "location": world["location"]}
    world["npcs"].append(npc)
    return npc


def not_closed_mouthed(world):
    for number in range(100):
        npc = passer_by(world, f"gecen-{number}")
        if not town_knowledge.is_closed_mouthed(world, npc):
            return npc
    raise AssertionError("everyone is silent")


class PeoplePoint(unittest.TestCase):
    def test_what_the_player_has_not_heard_comes_before_what_they_have(self):
        world, state, jobs = seeded_with_two_jobs()
        for thread in state["threads"]:
            thread["public_line"] = thread["public_line"][:60]
        npc = not_closed_mouthed(world)
        with patch.object(town_knowledge, "_coverage", return_value=100):
            first = [i["thread_id"] for i in town_knowledge.public_knowledge(world, npc) if i["kind"] == "thread"][0]
            world_threads.mark_heard(world_threads.by_id(world, first), 1)
            again = [i["thread_id"] for i in town_knowledge.public_knowledge(world, npc) if i["kind"] == "thread"]
        self.assertNotEqual(again[0], first)

    def test_work_comes_before_trouble_among_what_is_new(self):
        for number in range(100):
            world, state, jobs = work_town(f"seed-hooks-{number}")
            if jobs and any(t["type"] == "trouble" for t in state["threads"]):
                break
        npc = not_closed_mouthed(world)
        with patch.object(town_knowledge, "_coverage", return_value=100):
            listed = [i["thread_id"] for i in town_knowledge.public_knowledge(world, npc) if i["kind"] == "thread"]
        self.assertIn(world_threads.by_id(world, listed[0])["type"], {"hiring", "errand"})

    def test_even_someone_who_knows_little_knows_one_thing_going_on(self):
        for number in range(40):
            world, state, jobs = work_town(f"seed-hooks-{number}")
            npc = not_closed_mouthed(world)
            with patch.object(town_knowledge, "_coverage", return_value=0):
                known = town_knowledge.public_knowledge(world, npc)
            self.assertTrue([item for item in known if item["kind"] == "thread"], number)

    def test_the_same_person_keeps_the_same_story_while_nothing_is_heard(self):
        world, state, jobs = seeded_with_two_jobs()
        npc = not_closed_mouthed(world)
        self.assertEqual(town_knowledge.public_knowledge(world, npc), town_knowledge.public_knowledge(world, npc))


class TheStreet(unittest.TestCase):
    def test_asking_with_nobody_around_goes_through_what_is_new_before_repeating(self):
        world, state, jobs = seeded_with_two_jobs()
        heard = set()
        for turn in range(len(world_threads.active(world))):
            world["flags"]["turn_index"] = 0  # the old way picked by the turn number: the same one, over and over
            line = game._overheard_work(world)
            heard.add(next(t["thread_id"] for t in state["threads"] if t["public_line"] in line))
        self.assertEqual(len(heard), len(state["threads"]))


class TheBoard(unittest.TestCase):
    def test_it_carries_real_work_in_the_street_words_and_they_count_as_heard(self):
        world, state, jobs = seeded_with_two_jobs()
        text = town_knowledge.read_board(world)
        for thread in jobs[:town_knowledge.BOARD_LINES]:
            self.assertIn(thread["public_line"], text)
            self.assertEqual(thread["status"], "heard")

    def test_work_someone_took_or_a_trouble_is_not_on_it(self):
        world, state, jobs = seeded_with_two_jobs()
        jobs[0]["status"] = "accepted"
        troubles = [t for t in state["threads"] if t["type"] == "trouble"]
        text = town_knowledge.read_board(world)
        self.assertNotIn(jobs[0]["public_line"], text)
        for thread in troubles:
            self.assertNotIn(thread["public_line"], text)

    def test_a_town_with_nothing_posted_has_no_board_text(self):
        world, state, jobs = seeded_with_two_jobs()
        state["threads"] = [t for t in state["threads"] if t["type"] == "trouble"]
        self.assertIsNone(town_knowledge.read_board(world))

    def test_new_paper_catches_the_eye_in_the_street_once_a_day(self):
        world, state, jobs = seeded_with_two_jobs()
        self.assertTrue(town_knowledge.board_hint(world))
        self.assertIsNone(town_knowledge.board_hint(world))

    def test_with_nothing_new_it_says_nothing(self):
        world, state, jobs = seeded_with_two_jobs()
        for thread in jobs:
            world_threads.mark_heard(thread, 1)
        self.assertIsNone(town_knowledge.board_hint(world))


class ThePaperOnTheDoor(unittest.TestCase):
    def test_walking_up_to_a_place_with_open_work_shows_it_once(self):
        world, state, jobs = seeded_with_two_jobs()
        line = world_threads.arrival_line(world, jobs[0]["place_id"])
        self.assertIn(jobs[0]["public_line"], line)
        self.assertEqual(jobs[0]["status"], "heard")
        self.assertIsNone(world_threads.arrival_line(world, jobs[0]["place_id"]))

    def test_news_of_a_job_of_yours_comes_before_the_paper(self):
        world, state, jobs = seeded_with_two_jobs()
        row = world_happenings.write(state, jobs[0], "visit", 0, "Bir şey oldu.")
        self.assertEqual(world_threads.arrival_line(world, jobs[0]["place_id"]), row["line"])


class AtTheTable(Table):
    async def test_reading_the_board_in_the_street_works_however_it_is_said(self):
        for line in ("ilan panosuna bi bakayim", "panoda ne yaziyor okuyayim", "duvardaki ilanlari okuyorum"):
            await self.begin()
            self.client = ClassifiedClient()
            self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
            state = world_threads.view(self.world)
            self.thread.update(status="open", type="errand", public_line="Biri mühürlü mektup için ulak arıyor.")
            self.world["location"] = self.city
            self.client.front = {"kind": "look"}
            reply = await self.line(line)
            self.assertIn("mühürlü mektup", reply["narration"], line)
            self.assertEqual(self.status(), "heard")
