"""A table changes once when the player comes back, never while they are away.

Approved trigger: leaving a place with a mark or a surface item arms one hidden
table_absence event. Returning while the window is open applies it once, the
oldest mark first, otherwise the first item. No living NPC, or a closed
window, expires the event and changes nothing. The player never learns the cause.
"""
import unittest

import equipment_economy
import game
import campaign_time
import scheduled_events


class TableAbsenceTriggerTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=7)
        self.world = self.session.world_state
        self.world["locations"]["room_here"] = {
            "id": "room_here", "name": "Han salonu", "type": "building",
            "description": "Sade bir salon."}
        self.world["locations"]["room_away"] = {
            "id": "room_away", "name": "Arka oda", "type": "building",
            "description": "Boş bir oda."}
        self.world["location"] = "room_here"
        self.here = "room_here"
        campaign_time.initialize(self.world)
        self.world["campaign_time"]["elapsed_seconds"] = 1000
        self.table = self.session.create_local_feature({
            "name": "Kil masa", "location": self.here, "kind": "table",
            "description": "Sağlam bir masa."}, session=self.session)
        self.npc = {"id": "barmen", "name": "Barmen", "role": "han sahibi",
                    "location": self.here, "inventory": [], "current_hp": 8, "max_hp": 8,
                    "alive": True, "hostile": False}
        self.world.setdefault("npcs", []).append(self.npc)

    def mark(self, text):
        result = equipment_economy.execute(self.session, f'/item mark {self.table["id"]} "{text}"')
        self.assertTrue(result["action_result"]["success"], result["narration"])

    def place(self, name="Kil bardak"):
        item = equipment_economy.grant_named_item(self.world, name)
        result = equipment_economy.execute(
            self.session, f'/item place {item["item_id"]} {self.table["id"]}')
        self.assertTrue(result["action_result"]["success"], result["narration"])
        return item

    def live_npc(self):
        return next(record for record in self.world["npcs"] if record.get("id") == "barmen")

    def texts(self):
        return [m["text"] for m in self.world.get("feature_marks", {}).get(self.table["id"], [])]

    def arm(self):
        return scheduled_events.arm_table_absence(self.world, self.here)

    def arrive(self, location, now=None):
        self.world["location"] = location
        if now is not None:
            self.world["campaign_time"]["elapsed_seconds"] = now
        return scheduled_events.process_events(
            self.world, self.world["campaign_time"]["elapsed_seconds"],
            self.world["campaign_time"]["elapsed_seconds"],
            observation={"kind": "arrival", "location_id": location})

    def test_return_removes_oldest_mark_once(self):
        self.mark("eski iz")
        self.mark("yeni iz")
        self.world["feature_marks"][self.table["id"]][1]["turn"] = 5
        event = self.arm()
        self.arrive("room_away")
        self.assertEqual(self.texts(), ["eski iz", "yeni iz"])
        known = self.arrive(self.here)
        self.assertEqual(self.texts(), ["yeni iz"])
        self.assertEqual(event["status"], "OCCURRED")
        self.assertEqual(known, [])
        self.arrive(self.here, now=1100)
        self.assertEqual(self.texts(), ["yeni iz"])

    def test_return_moves_first_item_when_no_mark(self):
        item = self.place()
        self.arm()
        self.arrive("room_away")
        self.assertEqual(self.world["surface_items"][self.table["id"]], [item])
        self.arrive(self.here)
        self.assertNotIn(self.table["id"], self.world.get("surface_items", {}))
        self.assertEqual(self.live_npc()["inventory"], [item])

    def test_return_without_npc_changes_nothing(self):
        self.mark("eski iz")
        self.live_npc()["location"] = "room_away"
        event = self.arm()
        self.arrive("room_away")
        self.arrive(self.here)
        self.assertEqual(self.texts(), ["eski iz"])
        self.assertEqual(event["status"], "EXPIRED")
        self.assertEqual(self.world.get("player_knowledge", []), [])

    def test_second_departure_does_not_stack(self):
        self.mark("eski iz")
        self.arm()
        self.arm()
        pending = [e for e in self.world["scheduled_events"] if e["status"] == "PENDING"]
        self.assertEqual(len(pending), 1)

    def test_absence_cause_stays_out_of_player_knowledge(self):
        self.mark("eski iz")
        before = list(self.world.get("player_knowledge", []))
        event = self.arm()
        self.arrive("room_away")
        self.arrive(self.here)
        self.assertEqual(self.world.get("player_knowledge", []), before)
        self.assertEqual(scheduled_events.public_events(self.world), [])
        self.assertEqual(event["summary"], "")
        self.assertFalse(event["player_observed"])

    def test_nothing_to_change_arms_no_event(self):
        self.assertIsNone(self.arm())
        self.assertEqual(self.world.get("scheduled_events", []), [])

    def test_expired_window_changes_nothing(self):
        self.mark("eski iz")
        event = self.arm()
        self.arrive(self.here, now=1000 + 86400)
        self.assertEqual(self.texts(), ["eski iz"])
        self.assertEqual(event["status"], "EXPIRED")

    def test_real_location_change_arms_the_place_left_behind(self):
        self.mark("eski iz")
        self.session.commit_location_change("room_away", session=self.session)
        pending = [e for e in self.world.get("scheduled_events", []) if e["status"] == "PENDING"]
        self.assertEqual([e["location_id"] for e in pending], [self.here])
        self.session.commit_location_change(self.here, session=self.session)
        self.assertEqual(self.texts(), [])


if __name__ == "__main__":
    unittest.main()
