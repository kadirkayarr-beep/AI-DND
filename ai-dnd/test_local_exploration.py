"""Local exploration owns routes, clues, traps, and travel decisions."""

import unittest
from unittest.mock import patch

import game
import local_exploration as exploration


class LocalExplorationTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=3)
        self.world = self.session.world_state
        self.world["location"] = "tavern"
        self.world.setdefault("locations", {})["tavern"] = {
            "id": "tavern", "name": "Han", "type": "town",
        }
        self.world["inventory"] = ["Erzak", "Erzak", "Erzak", "Erzak"]
        self.session.character["current_hp"] = 12
        self.session.character["modifiers"] = {"wisdom": 0, "dexterity": 0}

    def test_begin_look_and_travel_decision(self):
        with patch.object(game, "ask_dungeon_master", side_effect=AssertionError("model")):
            started = self.session.run_player_turn("/explore begin")
        self.assertEqual(started["action_result"]["action"], "exploration")
        self.assertEqual(self.world["location"], exploration.CAMP)
        self.assertIn("patika", started["narration"].casefold())
        self.assertIsNone(exploration.resolve_turn(self.session, "yola çıkıyorum"))
        refused = exploration.resolve_turn(self.session, "/travel go missing")
        self.assertFalse(refused["success"])
        pending = exploration.resolve_turn(self.session, "/travel go " + exploration.ENTRY)
        self.assertTrue(pending["success"])
        self.assertEqual(self.world["location"], exploration.CAMP)
        stayed = exploration.resolve_turn(self.session, "/explore decision return")
        self.assertIn("vazgeçtin", stayed["direct_response"])
        self.assertIsNone(self.world[exploration.KEY]["journey"])
        exploration.resolve_turn(self.session, "/travel pace slow")
        exploration.resolve_turn(self.session, "/travel supplies enabled")
        exploration.resolve_turn(self.session, "/travel go " + exploration.ENTRY)
        arrived = exploration.resolve_turn(self.session, "/travel continue")
        self.assertEqual(self.world["location"], exploration.ENTRY)
        self.assertEqual(self.world[exploration.KEY]["elapsed_seconds"], exploration.LEG_SECONDS["slow"])
        self.assertIn(exploration.ENTRY, self.world[exploration.KEY]["known"])
        self.assertIn("vardın", arrived["direct_response"])

    def test_search_door_trap_and_supplies(self):
        exploration.resolve_turn(self.session, "/explore begin")
        exploration.resolve_turn(self.session, "/travel go " + exploration.ENTRY)
        exploration.resolve_turn(self.session, "/travel continue")
        self.session.rng.randint = lambda low, high: 20
        first = exploration.resolve_turn(self.session, "/explore search")
        self.assertIn("Gizli Geçit", first["direct_response"])
        second = exploration.resolve_turn(self.session, "/explore search")
        self.assertEqual(self.world[exploration.KEY]["trap_states"]["trap_wire"], "detected")
        self.assertIn("Gerili Tel", second["direct_response"])
        opened = exploration.resolve_turn(self.session, "/explore door door_oak unlock")
        self.assertTrue(opened["success"])
        disarmed = exploration.resolve_turn(self.session, "/explore trap trap_wire disarm")
        self.assertEqual(self.world[exploration.KEY]["trap_states"]["trap_wire"], "disarmed")
        moved = exploration.resolve_turn(self.session, "/explore exit entry_hall")
        self.assertEqual(self.world["location"], exploration.HALL)
        self.assertTrue(moved["success"])
        exploration.resolve_turn(self.session, "/explore interact lever")
        self.assertEqual(self.world[exploration.KEY]["hazard_states"]["hazard_rubble"], "neutralized")
        state = self.world[exploration.KEY]
        self.world["location"] = exploration.CAMP
        state["elapsed_seconds"] = exploration.SUPPLY_DAY - exploration.LEG_SECONDS["normal"]
        state["pace"] = "normal"
        state["supplies_enabled"] = True
        state["journey"] = {"origin": exploration.CAMP, "destination": exploration.ENTRY, "status": "pending"}
        before = self.world["inventory"].count("Erzak")
        exploration.resolve_turn(self.session, "/travel continue")
        self.assertEqual(self.world["inventory"].count("Erzak"), before - 1)
        self.assertFalse(state["supplies_short"])
        exploration.validate(self.world)

    def test_hidden_trap_damages_and_blocks(self):
        exploration.resolve_turn(self.session, "/explore begin")
        self.world["location"] = exploration.ENTRY
        self.world[exploration.KEY]["known"].append(exploration.ENTRY)
        oak = next(door for door in self.world["doors"] if door["id"] == "door_oak")
        oak["locked"] = False
        oak["open"] = True
        self.session.character["current_hp"] = 10
        blocked = exploration.resolve_turn(self.session, "/explore exit entry_hall")
        self.assertFalse(blocked["success"])
        self.assertEqual(self.world["location"], exploration.ENTRY)
        self.assertEqual(self.session.character["current_hp"], 8)
        self.assertEqual(self.world[exploration.KEY]["trap_states"]["trap_wire"], "triggered")

    def test_doors_dice_unconscious_and_travel_stay_on_one_world(self):
        exploration.resolve_turn(self.session, "/explore begin")
        ids = {door.get("id") for door in self.world["doors"]}
        self.assertIn("door_oak", ids)
        self.assertIn("door_vault", ids)
        self.assertNotIn("door_secret", ids)
        exploration.resolve_turn(self.session, "/travel go " + exploration.ENTRY)
        exploration.resolve_turn(self.session, "/travel continue")
        self.session.character["proficient_skills"] = ["Perception"]
        self.session.character["proficiency_bonus"] = 2
        self.session.rng.randint = lambda low, high: 13
        found = exploration.resolve_turn(self.session, "/explore search")
        self.assertTrue(found["success"])
        self.assertEqual(found["check"]["total"], 15)
        self.assertIn("door_secret", {door.get("id") for door in self.world["doors"]})
        self.session.character["proficient_skills"] = []
        missed = exploration.resolve_turn(self.session, "/explore search")
        self.assertFalse(missed["success"])
        oak = next(door for door in self.world["doors"] if door["id"] == "door_oak")
        oak["locked"] = False
        named = exploration.resolve_turn(self.session, "meşe kapıyı aç")
        self.assertTrue(named["success"])
        self.assertTrue(oak["open"])
        vault = next(door for door in self.world["doors"] if door["id"] == "door_vault")
        vault["location"] = exploration.ENTRY
        vague = exploration.resolve_turn(self.session, "kapıyı aç")
        self.assertFalse(vague["success"])
        self.assertIn("Hangi kapı", vague["direct_response"])
        vault["location"] = exploration.HALL
        self.world["location"] = exploration.CAMP
        exploration.resolve_turn(self.session, "/travel go " + exploration.ENTRY)
        exploration.resolve_turn(self.session, "/travel stop")
        held = exploration.resolve_turn(self.session, "/travel continue")
        self.assertFalse(held["success"])
        self.assertEqual(self.world["location"], exploration.CAMP)
        self.session.character["current_hp"] = 2
        self.world["location"] = exploration.ENTRY
        oak["open"] = True
        oak["locked"] = False
        vault["location"] = exploration.HALL
        hurt = exploration.resolve_turn(self.session, "/explore exit entry_hall")
        self.assertFalse(hurt["success"])
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.world["player_combat_status"], "unconscious")
        blocked = exploration.resolve_turn(self.session, "/explore look")
        self.assertFalse(blocked["success"])

    def test_corrupt_record_is_rejected(self):
        exploration.resolve_turn(self.session, "/explore begin")
        self.world[exploration.KEY]["trap_states"]["trap_wire"] = "open"
        with self.assertRaises(ValueError):
            exploration.validate(self.world)


if __name__ == "__main__":
    unittest.main()
