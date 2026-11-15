"""D-131: the courtyard Yolcu's authored 30-foot Speed reaches its combat actor.

monster_sense built the Yolcu NPC without its statblock's speed_ft, so action_economy.speed read 0 for it.
A Dodge it took was spent and saved, yet attacks against it lost the Disadvantage (Dodge needs Speed above 0).
"""
import unittest
from unittest import mock

import action_economy
import game
import monster_sense
import weapon_attack


class YolcuSpeedReachesCombatTests(unittest.TestCase):
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
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual(self.world["combat"]["current_actor_id"], "player")

    def test_the_yolcu_moves_at_its_authored_thirty_feet(self):
        self.assertEqual(monster_sense.STATBLOCK["speed_ft"], 30)
        self.assertEqual(action_economy.speed(self.session, monster_sense.NPC_ID), 30)

    def test_a_dodging_yolcu_gives_the_attack_against_it_disadvantage(self):
        action_economy.ensure(self.session)[monster_sense.NPC_ID]["dodging"] = True
        prepared = weapon_attack.prepare(self.session, "player", monster_sense.NPC_ID, "unarmed")
        self.assertIn("target_dodging", prepared["disadvantage_sources"])

    def test_a_dodging_yolcu_makes_its_dexterity_save_with_advantage(self):
        action_economy.ensure(self.session)[monster_sense.NPC_ID]["dodging"] = True
        seen = {}

        def capture(**kwargs):
            seen.update(kwargs)
            return {"ability": kwargs["ability"], "dc": kwargs["dc"], "outcome": "SUCCESS"}

        with mock.patch.object(weapon_attack, "resolve_saving_throw", side_effect=capture):
            weapon_attack._save(self.session, monster_sense.NPC_ID, ["dexterity"], 12)
        self.assertIs(seen["advantage"], True)

    def test_without_dodge_the_attack_has_no_dodge_disadvantage(self):
        prepared = weapon_attack.prepare(self.session, "player", monster_sense.NPC_ID, "unarmed")
        self.assertNotIn("target_dodging", prepared["disadvantage_sources"])


if __name__ == "__main__":
    unittest.main()
