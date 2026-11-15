"""D-200: walking out of the courtyard Yolcu's reach with /encounter move drew no Opportunity Attack.

In a fight the move spent the player's movement (D-130) but the Yolcu never used its Reaction. 2024 rule
(ZAR_KURALLARI 5.6, C07): a creature you can see leaving your reach draws one melee attack, taken with your
Reaction right before it leaves. Disengage, a Reaction that cannot be used or a creature that cannot see the
mover means no attack.
"""
import unittest

import action_economy
import game
import monster_sense
import spell_scope


class LeavingTheYolcusReachTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4)
        self.world = self.session.world_state
        self.world["location"] = "courtyard"
        self.world.setdefault("locations", {})["courtyard"] = {"id": "courtyard", "name": "Avlu"}
        monster_sense.resolve_turn(self.session, "/encounter begin")
        monster_sense.resolve_turn(self.session, "/encounter move far")  # beside the Yolcu (5 feet)
        self.session.rng.randint = lambda low, high: 2 if high == 20 else 1  # the opening swing misses
        self.session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Yolcu"}}, "Yolcu'ya saldırıyorum")
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual(self.world["combat"]["current_actor_id"], "player")
        self.yolcu_budget = action_economy.ensure(self.session)[monster_sense.NPC_ID]
        self.yolcu_budget["reaction_spent"] = False
        self.session.rng.randint = lambda low, high: 19 if high == 20 else 3  # any swing now hits
        self.hp = self.session.character["current_hp"]

    def _leave(self):
        moved = monster_sense.resolve_turn(self.session, "/encounter move near")
        self.assertTrue(moved["success"])
        self.assertEqual(self.world[monster_sense.KEY]["player_node"], "near")
        return moved

    def test_leaving_reach_draws_one_opportunity_attack_with_the_reaction(self):
        moved = self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp - 3)
        self.assertTrue(self.yolcu_budget["reaction_spent"])
        self.assertIn("Fırsat Saldırısı", moved["direct_response"])
        self.assertEqual(action_economy.ensure(self.session)["player"]["movement_used"], 25)

    def test_a_swing_that_drops_the_player_stops_the_walk_in_reach(self):
        self.session.character["current_hp"] = 1
        moved = monster_sense.resolve_turn(self.session, "/encounter move near")
        self.assertIn("Fırsat Saldırısı", moved["direct_response"])
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.world[monster_sense.KEY]["player_node"], "far")
        self.assertFalse(action_economy.can_act(self.session, "player"))

    def test_a_spent_reaction_means_no_attack(self):
        self.yolcu_budget["reaction_spent"] = True
        moved = self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)
        self.assertNotIn("Fırsat Saldırısı", moved["direct_response"])

    def test_disengage_means_no_attack(self):
        action_economy.ensure(self.session)["player"]["disengaging"] = True
        self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)
        self.assertFalse(self.yolcu_budget["reaction_spent"])

    def test_a_shocking_grasped_yolcu_makes_no_opportunity_attack(self):
        self.world.setdefault("attack_effects", []).append({
            "kind": spell_scope.SHOCKING_GRASP_EFFECT, "source_actor": "player",
            "target_id": monster_sense.NPC_ID})
        self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)
        self.assertFalse(self.yolcu_budget["reaction_spent"])

    def test_an_incapacitated_yolcu_makes_no_opportunity_attack(self):
        yolcu = next(n for n in self.world["npcs"] if n["id"] == monster_sense.NPC_ID)
        yolcu["conditions"] = ["incapacitated"]
        self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)
        self.assertFalse(self.yolcu_budget["reaction_spent"])

    def test_a_yolcu_that_cannot_see_the_player_makes_no_opportunity_attack(self):
        self.world.setdefault("flags", {})["player_hidden"] = True
        self.world.get("attack_environment", {}).get("pairs", {}).pop(f"player|{monster_sense.NPC_ID}", None)
        self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)
        self.assertFalse(self.yolcu_budget["reaction_spent"])

    def test_walking_into_reach_draws_no_attack(self):
        self._leave()
        self.yolcu_budget["reaction_spent"] = False
        hp = self.session.character["current_hp"]
        action_economy.ensure(self.session)["player"]["movement_used"] = 0
        self.assertTrue(monster_sense.resolve_turn(self.session, "/encounter move far")["success"])
        self.assertEqual(self.session.character["current_hp"], hp)
        self.assertFalse(self.yolcu_budget["reaction_spent"])

    def test_outside_a_fight_leaving_draws_no_attack(self):
        self.world["combat"]["active"] = False
        self._leave()
        self.assertEqual(self.session.character["current_hp"], self.hp)


if __name__ == "__main__":
    unittest.main()
