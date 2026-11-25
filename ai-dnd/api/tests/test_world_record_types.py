"""The TypedDicts in world_record_types match what the real producers build.

A produced record may only carry keys the TypedDict declares, and every key it marks Required must be
there. The shapes are annotations only, so this is what keeps them from drifting from the code.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import bold_acts
import living_world
import world_record_types as shapes
import world_reactions
import world_threads
from api.tests.test_world_threads import city, person

DAY = 86400


def declared(shape):
    return shape.__required_keys__ | shape.__optional_keys__


class ShapeCheck(unittest.TestCase):
    def check(self, shape, record, label):
        extra = set(record) - declared(shape)
        missing = shape.__required_keys__ - set(record)
        self.assertEqual(extra, set(), f"{label}: keys the shape does not declare")
        self.assertEqual(missing, set(), f"{label}: Required keys the record lacks")


def thread_snapshots():
    """Real producers and moves: seed, hear, offer, accept, decline, then let the clock close them."""
    world = city("typed-threads")
    world_threads.ensure(world)
    seen: list[dict] = []
    states: list[dict] = []

    def look():
        state = world[world_threads.KEY]
        states.append(dict.fromkeys(state))
        seen.extend({**t} for t in (*state["threads"], *state["history"]))

    look()
    threads = list(world[world_threads.KEY]["threads"])
    for number, thread in enumerate(threads):
        owner = person(world, f"owner{number}", thread["place_id"])
        world_threads.mark_heard(thread, 1)
        world_threads.mark_offered(world, thread, owner, "Şu iş var.", 1)
    look()
    world_threads.accept_hired(world, threads[0], 1)
    world_threads.decline(world, threads[1], 1)
    look()
    world_threads.tick(world, 3 * DAY)
    look()
    world_threads.tick(world, 40 * DAY)
    look()
    return world, seen, states


class ThreadShapes(ShapeCheck):
    def test_threads_match_the_shape_through_their_life(self):
        _world, seen, _states = thread_snapshots()
        self.assertGreater(len(seen), 3)
        for thread in seen:
            self.check(shapes.Thread, thread, f"thread {thread['thread_id']} ({thread['status']})")
            self.check(shapes.ThreadTerms, thread["terms"], "terms")

    def test_the_state_matches_the_shape(self):
        world, _seen, states = thread_snapshots()
        for state in (*states, world[world_threads.KEY]):
            self.check(shapes.ThreadState, state, "thread state")


class ThreadKeysUsedByCallers(unittest.TestCase):
    """A key a caller writes or reads on a thread is declared; the producer census alone cannot see it."""

    FILES = ("adventure/dialogue_jobs.py", "pocket.py", "quest_log.py", "town_knowledge.py", "world_happenings.py",
             "world_reactions.py", "world_threads.py")
    USE = re.compile(r"\b(?:thread|trouble|errand)(?:\.get\(|\[)[\"'](\w+)[\"']")

    def test_every_thread_key_the_callers_touch_is_declared(self):
        root = Path(__file__).resolve().parents[2]
        used = {name for path in self.FILES for name in self.USE.findall((root / path).read_text(encoding="utf8"))}
        self.assertGreater(len(used), 20)
        self.assertEqual(used - declared(shapes.Thread), set(), "thread keys the shape does not declare")


class DeedAndFireShapes(ShapeCheck):
    def session(self):
        world = {"location": "city", "flags": {"turn_index": 3}, "npcs": [{"id": "n1", "name": "A"}],
                 "locations": {"city": {"id": "city", "name": "Neverwinter"}}, "features": []}
        return SimpleNamespace(world_state=world, active_npcs=lambda: world["npcs"], messages=[],
                               create_local_feature=lambda spec: {"id": "feature_1", **spec})

    def test_a_remembered_deed(self):
        deed = bold_acts.remember(self.session(), "theft", "bir şey çaldı", victim_id="n1")
        self.check(shapes.Deed, deed, "remember")

    def test_a_broken_promise_deed(self):
        world = city("typed-deed")
        owner = {"id": "n1", "name": "Usta", "location": "city", "role": "usta"}
        thread = {"accepted_at": 0}
        with mock.patch.object(world_reactions, "_now", return_value=5):
            world_reactions.promise_broken(world, thread, owner, "failed")
        (deed,) = bold_acts.ensure_deeds(world)
        self.check(shapes.Deed, deed, "promise_broken")

    def test_a_lit_fire(self):
        session = self.session()
        with mock.patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}), \
                mock.patch.object(bold_acts, "_reply", return_value={}):
            bold_acts._burn(session)
        (fire,) = session.world_state["flags"]["fires"]
        self.check(shapes.Fire, fire, "fire")


class SceneShapes(ShapeCheck):
    def world(self):
        return {"location": "tavern", "locations": {"tavern": {"id": "tavern", "name": "Han", "type": "tavern"}},
                "npcs": [], "flags": {}}

    def test_scene_and_referent(self):
        world = self.world()
        scene = living_world.ensure_scene_record(world, "tavern", 1)
        self.check(shapes.SceneRecord, scene, "fresh scene")
        referent = living_world.create_scene_referent(world, "tavern", 1, description="Bir adam", aliases=["adam"])
        self.check(shapes.SceneReferent, referent, "referent")

    def test_opening_and_ambient_event(self):
        world = self.world()
        event = {"event_id": "e", "variation_id": "v", "instance_id": "i", "event_type": "BLUE",
                 "repeat_group": "g", "count": 1, "text": "Bir şey oluyor.", "aliases": ["şey"]}
        living_world.set_scene_opening(world, "tavern", "Açılış.", "calm", event)
        living_world.place_scene_event(world, "tavern", 1, event)
        scene = living_world.ensure_scene_record(world, "tavern", 1)
        self.check(shapes.SceneRecord, scene, "scene with opening and event")
        self.check(shapes.SceneOpening, scene["opening"], "opening")
        self.check(shapes.AmbientEvent, scene["ambient_event"], "ambient event")


if __name__ == "__main__":
    unittest.main()
