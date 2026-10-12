"""Regression checks for Python-owned adventure objective evidence.

Fresh in-memory sessions only. No real Qwen or persisted campaigns.
"""
import copy
import unittest

import interaction_adventure as adventure
from api.tests.test_interaction_adventure import envelope, session


class AdventureObjectiveEvidenceRegression(unittest.TestCase):
    def setUp(self):
        self.session = session()
        self.world = self.session.world_state

    def goal(self, quote, kind, target):
        result = adventure.resolve(
            self.session, quote,
            envelope("goal", quote, routes=[{"kind": kind, "target": target}]),
        )
        self.assertEqual(result["status"], "recorded")
        return self.world[adventure.KEY]["threads"][0]

    def consume(self, before, action="inventory"):
        adventure.consume(
            self.session,
            {"action": action, "status": "resolved", "success": True},
            before,
        )

    def test_acquire_canonical_item_record_completes_once(self):
        self.world["inventory"] = []
        self.goal("Hedefim Kılıç almak", "acquire", "Kılıç")
        before = copy.deepcopy(self.world)
        self.world["inventory"].append(
            {"item_id": "sword-new-1", "name": "Kılıç", "weapon_id": "longsword"}
        )
        self.consume(before)
        thread = self.world[adventure.KEY]["threads"][0]
        self.assertEqual(thread["status"], "succeeded")
        self.assertEqual(thread["objectives"][0]["status"], "completed")
        count = len(self.world[adventure.KEY]["events"])
        self.consume(before)
        self.assertEqual(len(self.world[adventure.KEY]["events"]), count)

    def test_acquire_legacy_string_still_completes_and_unchanged_count_does_not(self):
        self.world["inventory"] = ["Kılıç"]
        self.goal("Hedefim Kılıç almak", "acquire", "Kılıç")
        before = copy.deepcopy(self.world)
        self.consume(before)
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "active")
        self.world["inventory"].append("Kılıç")
        self.consume(before)
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "succeeded")

    def test_defeat_canonical_combat_status_completes_once(self):
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        target = next(n for n in self.world["npcs"] if n["id"] == "other")
        target["current_hp"] = 0
        target["combat_status"] = "dead"
        self.consume(before, "attack")
        thread = self.world[adventure.KEY]["threads"][0]
        self.assertEqual(thread["status"], "succeeded")
        count = len(self.world[adventure.KEY]["events"])
        self.consume(before, "attack")
        self.assertEqual(len(self.world[adventure.KEY]["events"]), count)

    def test_defeat_previously_defeated_target_does_not_complete(self):
        target = next(n for n in self.world["npcs"] if n["id"] == "other")
        target["current_hp"] = 0
        target["combat_status"] = "dead"
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        self.consume(before, "attack")
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "active")

    def _set_target(self, **fields):
        target = next(n for n in self.world["npcs"] if n["id"] == "other")
        target.update(fields)
        return target

    def test_unconscious_living_npc_completes_defeat(self):
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        self._set_target(current_hp=6, combat_status="unconscious")
        self.consume(before, "attack")
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "succeeded")

    def test_explicit_defeated_status_completes_defeat(self):
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        self._set_target(current_hp=4, combat_status="defeated")
        self.consume(before, "attack")
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "succeeded")

    def test_dead_status_completes_defeat(self):
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        self._set_target(current_hp=0, combat_status="dead")
        self.consume(before, "attack")
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "succeeded")

    def test_active_zero_hp_does_not_invent_defeat(self):
        self.goal("Hedefim Mira yenmek", "defeat", "other")
        before = copy.deepcopy(self.world)
        self._set_target(current_hp=0, combat_status="active", status="active")
        self.consume(before, "attack")
        self.assertEqual(self.world[adventure.KEY]["threads"][0]["status"], "active")


if __name__ == "__main__":
    unittest.main()
