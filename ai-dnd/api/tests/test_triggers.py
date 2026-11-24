"""Direct unit tests for incidents.triggers: Python-only triggers and the silence-first selector."""

import unittest

from incidents import triggers

PROFILE = {
    "silence_rate": 0.0,
    "category_weights": (("disturbance", 1),),
    "reward_weights": (("none", 1),),
}


def _world(location="tavern", loc_type=None):
    return {
        "location": location,
        "locations": {location: {"type": loc_type} if loc_type else {}},
        "campaign_time": {"elapsed_seconds": 0},
        "npcs": [],
        "incidents": {},
    }


def _detect(world, action_result=None, player_text="", location_changed=False):
    return triggers.detect(world, action_result=action_result, player_text=player_text, location_changed=location_changed)


class DetectTests(unittest.TestCase):
    def test_no_current_place_means_no_trigger(self):
        self.assertIsNone(_detect({"location": None}, location_changed=True))

    def test_moving_in_town_is_an_arrival(self):
        self.assertEqual(_detect(_world(), location_changed=True), {"kind": "arrival", "location_id": "tavern"})

    def test_moving_in_the_wild_is_a_travel_segment(self):
        self.assertEqual(
            _detect(_world("trail", "road"), location_changed=True), {"kind": "travel_segment", "location_id": "trail"}
        )
        self.assertEqual(_detect(_world("forest"), location_changed=True)["kind"], "travel_segment")

    def test_successful_travel_action_counts_as_moving(self):
        self.assertEqual(_detect(_world(), {"action": "travel", "success": True})["kind"], "arrival")
        self.assertIsNone(_detect(_world(), {"action": "travel", "success": False}))

    def test_rest_actions_trigger_a_rest(self):
        for action in ("rest", "short_rest", "long_rest"):
            with self.subTest(action=action):
                self.assertEqual(_detect(_world(), {"action": action})["kind"], "rest")

    def test_looking_around_in_text_triggers(self):
        for text in ("etrafa bakıyorum", "neler oluyor", "I look around the room"):
            with self.subTest(text=text):
                self.assertEqual(_detect(_world(), player_text=text)["kind"], "look_around")

    def test_ordinary_text_and_narration_trigger_nothing(self):
        self.assertIsNone(_detect(_world(), player_text="I order an ale"))
        self.assertIsNone(_detect(_world(), player_text=None))

    def test_closed_adventure_triggers_an_aftermath_here(self):
        trigger = _detect(_world(), {"action": "adventure_completed", "source_id": "adv.one"})
        self.assertEqual(
            trigger,
            {"kind": "aftermath", "location_id": "tavern", "source_location_id": "tavern", "source_event_id": "adv.one"},
        )


class OccupiedTests(unittest.TestCase):
    def test_only_open_incidents_here_occupy_the_place(self):
        world = _world()
        self.assertFalse(triggers.occupied(world, "tavern"))
        world["incidents"] = {
            "a": {"location_id": "tavern", "lifecycle": "RESOLVED"},
            "b": {"location_id": "harbor", "lifecycle": "PRESENT"},
            "c": "junk",
        }
        self.assertFalse(triggers.occupied(world, "tavern"))
        world["incidents"]["d"] = {"location_id": "tavern", "lifecycle": "PRESENT"}
        self.assertTrue(triggers.occupied(world, "tavern"))


class SelectTests(unittest.TestCase):
    def _select(self, world, trigger, profile=PROFILE):
        return triggers.select(world, campaign_id="camp", trigger=trigger, profile=profile)

    def test_in_horizon_trigger_without_silence_is_selected_and_repeatable(self):
        world = _world()
        trigger = {"kind": "arrival", "location_id": "tavern"}
        chosen = self._select(world, trigger)
        self.assertEqual(chosen.decisions["category"], "disturbance")
        self.assertTrue(chosen.trigger_id.startswith("trg:arrival:"))
        self.assertEqual(chosen, self._select(world, trigger))
        self.assertIsNot(chosen.trigger, trigger)

    def test_silence_profile_missing_or_far_trigger_selects_nothing(self):
        world = _world()
        trigger = {"kind": "arrival", "location_id": "tavern"}
        self.assertIsNone(self._select(world, trigger, dict(PROFILE, silence_rate=1.0)))
        self.assertIsNone(self._select(world, trigger, None))
        self.assertIsNone(self._select(world, {"kind": "arrival", "location_id": "harbor"}))

    def test_occupied_place_selects_nothing(self):
        world = _world()
        world["incidents"] = {"a": {"location_id": "tavern", "lifecycle": "PRESENT"}}
        self.assertIsNone(self._select(world, {"kind": "arrival", "location_id": "tavern"}))

    def test_worn_out_motif_selects_nothing(self):
        world = _world()
        world["emergence_state"] = {
            "budget": {},
            "cooldowns": {},
            "recent_categories": ["disturbance"] * 3,
            "paid_signatures": [],
        }
        self.assertIsNone(self._select(world, {"kind": "arrival", "location_id": "tavern"}))


if __name__ == "__main__":
    unittest.main()
