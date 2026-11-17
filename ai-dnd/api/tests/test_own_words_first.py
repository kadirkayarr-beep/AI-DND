"""BM T5 (play finding B2): what a person said aloud themselves comes first in what they know."""

from __future__ import annotations

import copy
import unittest

import town_knowledge
import town_rumours
import world_threads
from api.tests.test_town_knowledge import person, seeded

OWN = "Kuyunun dibinde bir kapı var"


def _add_threads(world, count, kind=None):
    """Copies of a real open thread, all standing at the NPC's own place so the NPC always knows them."""
    state = world_threads.view(world)
    base = next(t for t in state["threads"] if t["status"] == "open")
    for index in range(count):
        thread = copy.deepcopy(base)
        thread["thread_id"] = f"thr_extra_{index}"
        thread["place_id"] = "city"
        if kind:
            thread["type"] = kind
        state["threads"].append(thread)


def _heard(world, npc, text=OWN, entry_id="rum_own"):
    world.setdefault("heard_rumours", []).append(
        {"id": entry_id, "settlement_id": town_knowledge._settlement(world), "text": text,
         "place_id": "city", "said_by": npc["id"], "speakers": [npc["id"]]})


def _open_person(world):
    for index in range(200):
        npc = person(f"npc_own_{index}", "Barmen")
        if not town_knowledge.is_closed_mouthed(world, npc):
            return npc
    raise AssertionError("no talkative person found")


class OwnWordsFirst(unittest.TestCase):
    def test_own_spoken_rumour_is_first(self):
        world = seeded("own-first")
        _add_threads(world, 3)
        npc = _open_person(world)
        _heard(world, npc)
        known = town_knowledge.public_knowledge(world, npc)
        texts = [item["text"] for item in known]
        self.assertIn(OWN, texts[:2])
        first_thread = next(i for i, item in enumerate(known) if item["kind"] == "thread")
        self.assertLess(texts.index(OWN), first_thread)
        self.assertEqual(texts.count(OWN), 1)

    def test_own_rumour_survives_the_cap(self):
        world = seeded("own-cap")
        _add_threads(world, 12)
        npc = _open_person(world)
        _heard(world, npc)
        known = town_knowledge.public_knowledge(world, npc)
        self.assertIn(OWN, [item["text"] for item in known])
        self.assertLessEqual(len(known), town_knowledge.MAX_ITEMS)

    def test_rumour_for_own_before_trouble(self):
        world = seeded("own-trouble")
        _add_threads(world, 1, kind="trouble")
        npc = _open_person(world)
        _heard(world, npc)
        items = town_rumours.rumour_for(world, npc, town_knowledge._settlement(world), lambda *parts: 0, set())
        self.assertEqual(items[0]["text"], OWN)


if __name__ == "__main__":
    unittest.main()
