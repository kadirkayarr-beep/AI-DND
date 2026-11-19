"""BM Task 8: the everyday words (follow, knock, ring, read) wait for the front reading. They run only when the reading
gave nothing or said `unclear` / `attempt`; a reading that names a listed place or person belongs to its own owner.
The old `perform` branch was never reachable (classify never returns it) and is gone."""
from __future__ import annotations

import unittest

import everyday_actions
from api.tests import test_front_proposal
from api.tests.test_world_keeps_its_word import FrontScene
from api.tests.town_seed import fixed_town

FOLLOW_LINES = ("arkasından yürüyorsun", "izini kaybediyorsun")


def _followed(text):
    return any(line in text for line in FOLLOW_LINES)


class EverydayWaitsForTheReading(FrontScene):
    a_place = test_front_proposal.FrontTable.a_place

    async def test_everyday_waits_for_reading(self):
        with fixed_town(self, 2731):
            await self.begin()
        self.npc["name_known_to_player"] = True
        place = self.a_place()
        self.client.front = {"kind": "go_to", "place_id": place}
        # the line names the listed place (Dilim 3D T5), so the walk owner answers
        name = self.world["locations"][place]["name"]
        out = await self.line(f"Adamın peşinden {name} yerine gidiyorum")
        self.assertEqual(self.routes()[-1]["route"], "front:go_to")
        self.assertIn(name, out["narration"])
        self.assertFalse(_followed(out["narration"]), out["narration"])

    async def test_everyday_without_reading(self):
        with fixed_town(self, 2731):
            await self.begin()
        self.npc["name_known_to_player"] = True
        self.client.unusable = ("tamam, anladım", "stop")  # a lost provider is a 503 now (G6); no usable reading here
        out = await self.line(f"{self.npc['name']}'in peşinden gidiyorum")
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable")
        self.assertTrue(_followed(out["narration"]), out["narration"])

    async def test_everyday_after_an_unclear_reading(self):
        with fixed_town(self, 2731):
            await self.begin()
        self.npc["name_known_to_player"] = True
        self.client.front = {"kind": "unclear"}
        out = await self.line(f"{self.npc['name']}'in peşinden gidiyorum")
        self.assertTrue(_followed(out["narration"]), out["narration"])

    async def test_a_reading_of_another_kind_keeps_the_everyday_words_out(self):
        with fixed_town(self, 2731):
            await self.begin()
        self.npc["name_known_to_player"] = True
        self.client.front = {"kind": "look"}
        out = await self.line(f"{self.npc['name']}'in peşinden gidiyorum")
        self.assertFalse(_followed(out["narration"]), out["narration"])


class NoPerformBranch(unittest.TestCase):
    def test_no_perform_branch(self):
        self.assertFalse(hasattr(everyday_actions, "_PERFORM"))
