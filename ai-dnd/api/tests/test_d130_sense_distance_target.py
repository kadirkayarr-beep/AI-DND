"""D-130: the courtyard Yolcu's authored distance belongs to the Yolcu alone.

execute_intent's melee path copied monster_sense.observable_pair's distance onto whatever NPC was attacked,
so a bandit beside the player read 30 feet (refused as out of range) and a commoner 60 feet away read 5 feet
(struck in melee) while the Yolcu scene was in the courtyard.
"""
import unittest

import action_economy
import game
import monster_sense
from combat_lifecycle import CombatRequestError


def _person(npc_id, name, distance_ft):
    return {
        "id": npc_id, "name": name, "role": "bandit", "location": "courtyard",
        "hostile": True, "combat_role": "enemy", "combat_status": "active",
        "armor_class": 10, "max_hp": 20, "current_hp": 20, "attack_bonus": 2,
        "damage_die": 4, "damage_dice": 1, "damage_modifier": 0, "hidden": False,
        "memory": [], "distance_ft": distance_ft,
    }


class SenseDistanceStaysOnTheYolcuTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4)
        self.world = self.session.world_state
        self.world["location"] = "courtyard"
        self.world.setdefault("locations", {})["courtyard"] = {"id": "courtyard", "name": "Avlu"}
        self.assertTrue(monster_sense.resolve_turn(self.session, "/encounter begin")["success"])
        self.session.rng.randint = lambda low, high: 15 if high == 20 else 4

    def _attack(self, name):
        return self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": name}},
            f"{name}'a saldırıyorum",
        )

    def test_bandit_beside_the_player_is_not_given_the_yolcu_thirty_feet(self):
        bandit = _person("npc_bandit_d130", "Haydut", 5)
        self.world["npcs"].append(bandit)
        self.assertEqual(monster_sense.snapshot(self.session)["targets"][0]["distance_ft"], 30)
        result = self._attack("Haydut")
        self.assertNotEqual(result.get("outcome"), "out_of_range")
        self.assertEqual(bandit["distance_ft"], 5)
        self.assertLess(bandit["current_hp"], 20)

    def test_commoner_sixty_feet_away_is_not_given_the_yolcu_five_feet(self):
        monster_sense.resolve_turn(self.session, "/encounter move far")
        self.assertEqual(monster_sense.snapshot(self.session)["targets"][0]["distance_ft"], 5)
        commoner = _person("npc_commoner_d130", "Ahali", 60)
        self.world["npcs"].append(commoner)
        with self.assertRaises(CombatRequestError) as refused:
            self._attack("Ahali")
        self.assertEqual(refused.exception.code, "out_of_range")
        self.assertEqual(commoner["distance_ft"], 60)
        self.assertEqual(commoner["current_hp"], 20)

    def test_the_yolcu_still_takes_its_authored_distance(self):
        yolcu = next(n for n in self.world["npcs"] if n["id"] == monster_sense.NPC_ID)
        blocked = self._attack("Yolcu")
        self.assertEqual(blocked.get("outcome"), "out_of_reach")
        self.assertEqual(yolcu["distance_ft"], 30)
        self.assertEqual(yolcu["current_hp"], 4)


class ScenarioMoveSpendsCombatMovementTests(unittest.TestCase):
    """In a fight, /encounter move walked 25 feet in or out of the Yolcu's reach without spending movement."""

    def setUp(self):
        self.session = game.create_session(seed=4)
        self.world = self.session.world_state
        self.world["location"] = "courtyard"
        self.world.setdefault("locations", {})["courtyard"] = {"id": "courtyard", "name": "Avlu"}
        monster_sense.resolve_turn(self.session, "/encounter begin")
        monster_sense.resolve_turn(self.session, "/encounter move far")
        self.session.rng.randint = lambda low, high: 2 if high == 20 else 1  # the opening swing misses
        self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Yolcu"}}, "Yolcu'ya saldırıyorum")
        combat = self.world["combat"]
        self.assertTrue(combat["active"])
        self.assertEqual(combat["current_actor_id"], "player")

    def test_moving_out_of_reach_spends_twenty_five_feet(self):
        budget = action_economy.ensure(self.session)["player"]
        self.assertEqual(budget["movement_used"], 0)
        moved = monster_sense.resolve_turn(self.session, "/encounter move near")
        self.assertTrue(moved["success"])
        self.assertEqual(budget["movement_used"], 25)
        self.assertEqual(self.world[monster_sense.KEY]["player_node"], "near")

    def test_moving_away_updates_the_distance_the_yolcu_attacks_from(self):
        # Review of D-130: the Yolcu's own swing reads its record's distance (weapon_attack.pair); a move must set it.
        import weapon_attack
        self.assertEqual(weapon_attack.pair(self.session, monster_sense.NPC_ID, "player")["distance_ft"], 5)
        self.assertTrue(monster_sense.resolve_turn(self.session, "/encounter move near")["success"])
        self.assertEqual(weapon_attack.pair(self.session, monster_sense.NPC_ID, "player")["distance_ft"], 30)

    def test_walking_up_to_the_yolcu_in_a_fight_puts_it_in_reach(self):
        # Second review of D-130: combat_lifecycle.approach spent 25 feet and wrote 5 feet on the Yolcu, but the next
        # swing re-read the authored node pair (30 feet): the walk was spent and the swing was out of reach.
        self.assertTrue(monster_sense.resolve_turn(self.session, "/encounter move near")["success"])
        budget = action_economy.ensure(self.session)["player"]
        budget["movement_used"] = 0  # the player's next turn: a fresh movement budget
        self.session.execute_intent(
            {"intent": "travel", "target": {"type": "npc", "reference": "Yolcu"}}, "Yolcu'ya doğru yürüyorum")
        self.assertEqual(budget["movement_used"], 25)
        self.assertEqual(monster_sense.observable_pair(self.session)["distance_ft"], 5)
        self.session.rng.randint = lambda low, high: 15 if high == 20 else 4
        swing = self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Yolcu"}}, "Yolcu'ya saldırıyorum")
        self.assertNotEqual(swing.get("outcome"), "out_of_reach")
        yolcu = next(n for n in self.world["npcs"] if n["id"] == monster_sense.NPC_ID)
        self.assertEqual(yolcu["distance_ft"], 5)
        self.assertLess(yolcu["current_hp"], 4)

    def test_no_movement_left_keeps_the_player_in_place(self):
        budget = action_economy.ensure(self.session)["player"]
        budget["movement_used"] = action_economy.movement_limit(self.session, "player")
        refused = monster_sense.resolve_turn(self.session, "/encounter move near")
        self.assertFalse(refused["success"])
        self.assertEqual(self.world[monster_sense.KEY]["player_node"], "far")
        self.assertEqual(budget["movement_used"], action_economy.movement_limit(self.session, "player"))

    def test_outside_a_fight_the_scenario_move_spends_nothing(self):
        self.world["combat"]["active"] = False
        moved = monster_sense.resolve_turn(self.session, "/encounter move near")
        self.assertTrue(moved["success"])
        self.assertEqual(self.world[monster_sense.KEY]["player_node"], "near")


if __name__ == "__main__":
    unittest.main()
