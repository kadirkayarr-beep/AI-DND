"""What the character is after can make a matching thread likelier. It is a tilt in the odds, never a story laid out for them."""
import unittest
from unittest.mock import patch

import front_proposal
import world_threads

from api.tests.test_front_proposal import FrontTable
from api.tests.test_world_threads import city

WANT = "serve_the_great"


def fits(world, thread):
    return world_threads.serves(next(t for t in world_threads.catalog()["templates"] if t["id"] == thread["template_id"]),
                                [WANT])


def count_fitting(*, wants, seeds=60):
    found = 0
    for number in range(seeds):
        world = city(f"seed-wants-{number}")
        if wants:
            world_threads.note_want(world, WANT)
        world_threads.ensure(world)
        found += sum(1 for thread in world_threads.view(world)["threads"] if fits(world, thread))
    return found


class TheOdds(unittest.TestCase):
    def test_a_town_opens_more_of_what_the_character_is_after(self):
        self.assertGreater(count_fitting(wants=True), count_fitting(wants=False) * 1.2)

    def test_it_is_a_tilt_not_a_promise(self):
        opened = []
        for number in range(40):
            world = city(f"seed-wants-{number}")
            world_threads.note_want(world, WANT)
            world_threads.ensure(world)
            opened.append(sum(1 for thread in world_threads.view(world)["threads"] if fits(world, thread)))
        self.assertLessEqual(max(opened), 2 + 1)  # one more than chance, never a whole town of it
        self.assertLess(sum(opened) / len(opened), 2)

    def test_a_town_that_runs_short_later_leans_the_same_way(self):
        leaning, plain = 0, 0
        for number in range(40):
            for wanted in (True, False):
                world = city(f"seed-later-{number}")
                world_threads.ensure(world)
                state = world_threads.view(world)
                state["threads"] = []
                if wanted:
                    world_threads.note_want(world, WANT)
                world_threads.tick(world, 86400)
                found = sum(1 for thread in world_threads.view(world)["threads"] if fits(world, thread))
                leaning, plain = (leaning + found, plain) if wanted else (leaning, plain + found)
        self.assertGreater(leaning, plain)

    def test_the_thread_is_an_ordinary_thread_with_nothing_of_the_character_in_it(self):
        world = city("seed-wants-1")
        plain_world = city("seed-wants-1")
        world_threads.note_want(world, WANT)
        world_threads.ensure(world)
        world_threads.ensure(plain_world)
        keys = {key for thread in world_threads.view(plain_world)["threads"] for key in thread}
        self.assertLessEqual({key for thread in world_threads.view(world)["threads"] for key in thread}, keys | {"night_only", "item_noun", "status_lines"})

    def test_the_same_campaign_with_the_same_want_opens_the_same_town(self):
        seen = []
        for _ in range(2):
            world = city("seed-wants-2")
            world_threads.note_want(world, WANT)
            world_threads.ensure(world)
            seen.append([thread["template_id"] for thread in world_threads.view(world)["threads"]])
        self.assertEqual(seen[0], seen[1])


class WhatIsKept(unittest.TestCase):
    def test_an_id_the_list_never_had_is_not_kept(self):
        world = city("seed")
        world_threads.note_want(world, "krallik")
        self.assertEqual(world_threads.wants_of(world), [])

    def test_two_at_most_the_newest_stay_and_saying_it_twice_is_once(self):
        world = city("seed")
        for want in ("coin", "coin", "faith", WANT):
            world_threads.note_want(world, want)
        self.assertEqual(world_threads.wants_of(world), ["faith", WANT])


class TheFrontReading(FrontTable):
    async def test_a_goal_said_in_play_is_kept_from_the_listed_ones(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "want": WANT}
        await self.line("usta ben aslinda buyuk bi lordun yaninda koruma olmak istiyorum")
        self.assertEqual(world_threads.wants_of(self.world), [WANT])

    async def test_the_list_and_the_field_are_on_the_reading(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bi bakayim su sokakta ne var")
        schema = self.front_calls()[-1]["properties"]["front"]
        self.assertIn(WANT, schema["properties"]["want"]["enum"])

    async def test_a_line_with_no_goal_keeps_none(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bi bakayim")
        self.assertEqual(world_threads.wants_of(self.world), [])

    async def test_what_the_sheet_says_is_read_on_the_first_lines_only(self):
        await self.begin()
        self.session.character["backstory"] = "Orduyu bıraktı, güçlü bir lordun koruması olmak istiyor."
        listed = front_proposal.listing(self.session)
        self.assertIn("koruması", listed["sheet"])
        self.world["flags"]["turn_index"] = 9
        self.assertNotIn("sheet", front_proposal.listing(self.session))
