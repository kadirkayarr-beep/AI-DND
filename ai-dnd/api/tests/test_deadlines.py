"""Direct unit tests for adventure.deadlines: windows open only for known adventures and close without new reveals."""

import unittest

from adventure import deadlines


def _world(location="tavern", elapsed=100):
    return {
        "location": location,
        "locations": {"tavern": {}, "harbor": {}},
        "campaign_time": {"elapsed_seconds": elapsed},
        "scheduled_events": [],
        "flags": {},
    }


def _quest(status="DISCOVERED", **extra):
    quest = {"quest_id": "adv.t", "status": status, "bindings": {}, "updated_turn": 3, "objectives": []}
    quest.update(extra)
    return quest


class ArmTests(unittest.TestCase):
    def test_hidden_or_closed_adventure_gets_no_window(self):
        for status in ("OFFERED", "HIDDEN", "FAILED", "COMPLETED"):
            with self.subTest(status=status):
                world = _world()
                self.assertIsNone(deadlines.arm(world, _quest(status)))
                self.assertEqual(world["scheduled_events"], [])

    def test_existing_deadline_is_returned_and_nothing_is_added(self):
        world = _world()
        self.assertEqual(deadlines.arm(world, _quest(deadline="adventure-deadline:old")), "adventure-deadline:old")
        self.assertEqual(world["scheduled_events"], [])

    def test_unknown_location_gets_no_window(self):
        self.assertIsNone(deadlines.arm(_world(location="nowhere"), _quest()))
        self.assertIsNone(deadlines.arm(_world(location=None), _quest()))

    def test_window_starts_now_and_is_hidden_and_non_interruptive(self):
        world = _world(elapsed=100)
        quest = _quest()
        event_id = deadlines.arm(world, quest, duration_seconds=600)
        self.assertEqual(event_id, "adventure-deadline:adv.t")
        self.assertEqual(quest["deadline"], event_id)
        event = world["scheduled_events"][0]
        self.assertEqual((event["window_start"], event["window_end"]), (100, 700))
        self.assertEqual(event["visibility"], "hidden")
        self.assertEqual(event["behavior"], "NON_INTERRUPTIVE")
        self.assertEqual(event["location_id"], "tavern")

    def test_bound_location_wins_over_player_location(self):
        world = _world(location="tavern")
        deadlines.arm(world, _quest(bindings={"location_ids": ["harbor"]}))
        self.assertEqual(world["scheduled_events"][0]["location_id"], "harbor")

    def test_non_integer_clock_counts_as_zero(self):
        world = _world(elapsed=True)
        deadlines.arm(world, _quest())
        self.assertEqual(world["scheduled_events"][0]["window_start"], 0)


class CloseMissedTests(unittest.TestCase):
    def test_wrong_status_or_missing_deadline_does_not_close(self):
        world = _world()
        self.assertFalse(deadlines.close_missed(world, _quest("FAILED", deadline="x")))
        self.assertFalse(deadlines.close_missed(world, _quest()))
        self.assertFalse(deadlines.close_missed(world, _quest(deadline=5)))

    def test_event_not_missed_does_not_close(self):
        world = _world()
        quest = _quest(deadline="adventure-deadline:adv.t")
        world["scheduled_events"].append({"event_id": "adventure-deadline:adv.t", "encounter_status": "UNKNOWN"})
        self.assertFalse(deadlines.close_missed(world, quest))
        self.assertEqual(quest["status"], "DISCOVERED")

    def test_unknown_event_does_not_close(self):
        self.assertFalse(deadlines.close_missed(_world(), _quest(deadline="adventure-deadline:gone")))


if __name__ == "__main__":
    unittest.main()
