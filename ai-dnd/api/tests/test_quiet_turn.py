"""A turn where nothing changes says so in a line drawn from the place and the hour; the stock line is kept
for when no model answered."""

from __future__ import annotations

import unittest

import campaign_time
import game
from api import ollama_adapter


def world_at(hour, kind="city", name="Neverwinter", seed="tohum1"):
    world = {"location": "yer", "locations": {"yer": {"name": name, "scene_kind": kind}},
             "scene_state": {"campaign_seed": seed}, "flags": {"turn_index": 1}}
    campaign_time.initialize(world)
    world["campaign_time"]["start_second"] = hour * 3600
    return world


class QuietLines(unittest.TestCase):
    def tearDown(self):
        ollama_adapter._TURN_USAGE.set(None)

    def line(self, world):
        session = game.create_session(seed=42)
        session.world_state = world
        session.world_metadata = None
        return game._generic_no_change_response(session=session)

    def test_quiet_lines_vary_by_place_and_hour(self):
        morning, evening = self.line(world_at(8)), self.line(world_at(18))
        self.assertNotEqual(morning, evening)
        self.assertNotEqual(self.line(world_at(13, kind="city")), self.line(world_at(13, kind="tavern", name="Han")))
        self.assertEqual(self.line(world_at(8)), self.line(world_at(8)))
        for line in (morning, evening):
            self.assertNotIn("belirgin bir değişiklik olmuyor", line)

    def test_consecutive_quiet_turns_do_not_all_repeat_one_line(self):
        def at(hour, turn):
            world = world_at(hour)
            world["flags"]["turn_index"] = turn
            return self.line(world)
        for hour in (13, 18):  # the catalog holds one city line for early morning and night, two for these
            lines = [at(hour, turn) for turn in range(1, 4)]
            self.assertGreater(len(set(lines)), 1, (hour, lines))
            self.assertEqual(lines, [at(hour, turn) for turn in range(1, 4)])

    def test_the_stock_line_stays_when_no_model_answers(self):
        ollama_adapter.begin_turn_usage()
        ollama_adapter.note_usage("model", failed=True)
        self.assertIn(self.line(world_at(8)), game._GENERIC_NO_CHANGE_RESPONSES)

    def test_the_stock_line_stays_when_the_place_has_no_line(self):
        self.assertIn(self.line(world_at(13, kind="dungeon")), game._GENERIC_NO_CHANGE_RESPONSES)


if __name__ == "__main__":
    unittest.main()
