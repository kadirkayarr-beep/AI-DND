"""D-138: finished scheduled events never fill the active event capacity.

The 256 cap bounds the events that can still happen (PENDING) or still wait
for a player decision. Occurred and expired events are history: a long
campaign keeps them, and a new quest deadline is still accepted.
"""
import unittest

import adventure.deadlines as deadlines
import scheduled_events


def _world():
    return {
        "locations": {"town": {"id": "town", "name": "Kasaba"}},
        "npcs": [],
        "location": "town",
        "campaign_time": {"elapsed_seconds": 5000},
    }


def _finish(event, status):
    event["status"] = status
    event["encounter_status"] = "MISSED"
    if status == "OCCURRED":
        event["canonical_result"] = {"resolved_at": event["window_end"],
                                     "effects_applied": len(event["effects"])}


def _register(world, number):
    return scheduled_events.register_event(
        world, event_id=f"old:{number}", window_start=number, window_end=number + 10,
        location_id="town", behavior="NON_INTERRUPTIVE", visibility="hidden")


def _quest():
    return {"quest_id": "q-new", "status": "ACTIVE",
            "bindings": {"location_ids": ["town"]}}


class FinishedEventsDoNotFillCapacity(unittest.TestCase):
    def test_a_new_deadline_is_armed_after_256_finished_events(self):
        world = _world()
        for number in range(256):
            _finish(_register(world, number), "OCCURRED" if number % 2 else "EXPIRED")
        quest = _quest()
        self.assertEqual(deadlines.arm(world, quest), "adventure-deadline:q-new")
        self.assertEqual(quest["deadline"], "adventure-deadline:q-new")
        self.assertEqual(len(world["scheduled_events"]), 257)
        # The save and load check accepts the same list.
        scheduled_events.validate_events(world["scheduled_events"], world)

    def test_256_active_events_still_refuse_one_more(self):
        world = _world()
        for number in range(256):
            _register(world, number)
        with self.assertRaises(ValueError):
            deadlines.arm(world, _quest())
        self.assertEqual(len(world["scheduled_events"]), 256)

    def test_an_event_waiting_for_a_decision_still_counts_as_active(self):
        world = _world()
        for number in range(256):
            event = _register(world, number)
            _finish(event, "OCCURRED")
            if number == 0:
                event.update(behavior="FORCED", visibility="public", player_observed=True,
                             player_known_summary="Bir karar bekleniyor.",
                             encounter_status="OBSERVED", decision_status="PENDING")
        for number in range(256, 511):
            _register(world, number)
        with self.assertRaises(ValueError):
            deadlines.arm(world, _quest())


if __name__ == "__main__":
    unittest.main()
