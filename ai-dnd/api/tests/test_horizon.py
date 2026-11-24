"""Direct unit tests for incidents.horizon: only the scene the player stands in can trigger an incident."""

import unittest

from incidents import horizon


def _world():
    return {"location": "tavern", "locations": {"tavern": {}, "harbor": {}}}


class HorizonTests(unittest.TestCase):
    def test_current_scene_triggers_are_in_horizon(self):
        for kind in ("arrival", "look_around", "rest", "travel_segment"):
            with self.subTest(kind=kind):
                self.assertTrue(horizon.in_horizon(_world(), {"kind": kind, "location_id": "tavern"}))

    def test_other_place_unknown_kind_or_bad_shape_is_out(self):
        self.assertFalse(horizon.in_horizon(_world(), {"kind": "arrival", "location_id": "harbor"}))
        self.assertFalse(horizon.in_horizon(_world(), {"kind": "time_passes", "location_id": "tavern"}))
        self.assertFalse(horizon.in_horizon(_world(), "arrival"))
        self.assertFalse(horizon.in_horizon({"location": None}, {"kind": "arrival", "location_id": None}))

    def test_unregistered_current_place_is_out(self):
        world = {"location": "void", "locations": {"tavern": {}}}
        self.assertFalse(horizon.in_horizon(world, {"kind": "arrival", "location_id": "void"}))

    def test_aftermath_needs_a_source_event_here(self):
        base = {"kind": "aftermath", "location_id": "tavern"}
        self.assertFalse(horizon.in_horizon(_world(), base))
        self.assertFalse(horizon.in_horizon(_world(), dict(base, source_location_id="harbor", source_event_id="e1")))
        self.assertFalse(horizon.in_horizon(_world(), dict(base, source_location_id="tavern", source_event_id="")))
        self.assertTrue(horizon.in_horizon(_world(), dict(base, source_location_id="tavern", source_event_id="e1")))


if __name__ == "__main__":
    unittest.main()
