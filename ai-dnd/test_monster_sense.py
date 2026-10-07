"""Monster sense reports distance and identity, never hit points."""

import unittest

import game
import monster_sense


class MonsterSenseTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4)
        self.world = self.session.world_state
        self.world["location"] = "courtyard"
        self.world.setdefault("locations", {})["courtyard"] = {"id": "courtyard", "name": "Avlu"}

    def test_begin_route_and_snapshot_hide_hp(self):
        started = monster_sense.resolve_turn(self.session, "/encounter begin")
        self.assertTrue(started["success"])
        npc = next(item for item in self.world["npcs"] if item["id"] == monster_sense.NPC_ID)
        self.assertEqual(npc["statblock"]["armor_class"], 10)
        self.assertEqual(npc["statblock"]["hit_points"], 4)
        self.assertNotIn("current_hp", npc["statblock"])
        self.assertEqual(npc["current_hp"], 4)
        view = monster_sense.resolve_turn(self.session, "/sense")
        target = view["snapshot"]["targets"][0]
        self.assertEqual(target["distance_ft"], 30)
        self.assertNotIn("current_hp", target)
        self.assertNotIn("hit_points", target)
        moved = monster_sense.resolve_turn(self.session, "/encounter move far")
        self.assertIn("5 ayak", moved["direct_response"])
        monster_sense.validate(self.world)

    def test_blinded_or_hidden_creature_is_omitted(self):
        monster_sense.resolve_turn(self.session, "/encounter begin")
        self.session.character["conditions"] = ["blinded"]
        blind = monster_sense.snapshot(self.session)
        self.assertEqual(blind["targets"], [])
        self.session.character["conditions"] = []
        self.world["npcs"][0]["hidden"] = True
        hidden = monster_sense.snapshot(self.session)
        self.assertEqual(hidden["targets"], [])

    def test_melee_uses_the_same_distance_as_sense(self):
        monster_sense.resolve_turn(self.session, "/encounter begin")
        view = monster_sense.snapshot(self.session)
        self.assertEqual(view["targets"][0]["distance_ft"], 30)
        self.session.rng.randint = lambda low, high: 15 if high == 20 else 4
        blocked = self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Yolcu"}},
            "Yolcu'ya saldırıyorum",
        )
        npc = next(item for item in self.world["npcs"] if item["id"] == monster_sense.NPC_ID)
        self.assertEqual(blocked.get("outcome"), "out_of_reach")
        self.assertEqual(blocked.get("distance_ft"), 30)
        self.assertEqual(npc["current_hp"], 4)
        self.assertFalse(self.world["combat"]["active"])
        monster_sense.resolve_turn(self.session, "/encounter move far")
        self.assertEqual(monster_sense.snapshot(self.session)["targets"][0]["distance_ft"], 5)
        opened = self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Yolcu"}},
            "Yolcu'ya saldırıyorum",
        )
        self.assertNotEqual(opened.get("outcome"), "out_of_reach")
        self.assertLess(npc["current_hp"], 4)

    def test_corrupt_binding_is_rejected(self):
        monster_sense.resolve_turn(self.session, "/encounter begin")
        self.world[monster_sense.KEY]["npc_node"] = "secret"
        with self.assertRaises(ValueError):
            monster_sense.validate(self.world)


if __name__ == "__main__":
    unittest.main()
