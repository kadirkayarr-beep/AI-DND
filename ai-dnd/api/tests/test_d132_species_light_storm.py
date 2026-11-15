"""D-132 (ORTA-27): two species traits the PHB 2024 gives that the engine did not honor.

- Aasimar, Light Bearer (PHB 2024 PDF page 185): "You know the Light cantrip." An Aasimar Fighter (no class spellcasting)
  may cast Light as a narrative spell; another Fighter still may not.
- Goliath, Storm's Thunder (PHB 2024 PDF page 191): "When you take damage from a creature within 60 feet of you, you can
  take a Reaction to deal 1d8 Thunder damage to that creature." It is no on-hit rider and pushes nothing (the engine
  used to add thunder to the Goliath's own hit and report a 10 ft push that never moved the target).

Engine fixtures only (no campaign is started, so no town seed is needed): test_species_traits.make_session."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import game
import spell_effects
from api.tests.test_species_traits import attack_fixture, make_session


def foe(session, **change):
    enemy = {"id": "storm-foe", "name": "Foe", "location": session.world_state["location"],
             "combat_status": "active", "current_hp": 20, "max_hp": 20, "armor_class": 10, "attack_bonus": 0,
             "damage_die": 8, "damage_dice": 1, "damage_modifier": 0, **change}
    attack_fixture(session, enemy)
    return enemy


class AasimarLightBearer(unittest.TestCase):
    def fighter(self, species):
        session = make_session(species, level=3)
        session.world_state.pop("spellcasting_v1", None)  # a Fighter has no class spellcasting
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        return session

    def test_an_aasimar_fighter_casts_light(self):
        session = self.fighter("Aasimar")
        reading = spell_effects.named("Işık büyüsü yapıyorum")
        self.assertEqual(reading, ("narrative", "Light"))
        cast = spell_effects.resolve(session, reading)
        self.assertTrue(cast["action_result"]["success"], cast["action_result"])
        self.assertEqual([fact["spell_id"] for fact in session.world_state[spell_effects.KEY]], ["Light"])

    def test_another_fighter_still_cannot(self):
        session = self.fighter("Human")
        cast = spell_effects.resolve(session, ("narrative", "Light"))
        self.assertEqual(cast["action_result"]["reason"], "spell_not_available")
        self.assertNotIn(spell_effects.KEY, session.world_state)

    def test_light_bearer_gives_only_light(self):
        session = self.fighter("Aasimar")
        cast = spell_effects.resolve(session, ("narrative", "Prestidigitation"))
        self.assertEqual(cast["action_result"]["reason"], "spell_not_available")


class GoliathStormsThunder(unittest.TestCase):
    def storm(self, hp=20):
        session = make_session("Goliath", ancestry="storm")
        session.character["current_hp"] = hp
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        return session

    def test_the_goliaths_own_hit_gets_no_thunder_and_no_push(self):
        session = self.storm()
        target = foe(session)
        with (patch("game.roll_attack", return_value=15), patch("game.roll_damage", return_value=4),
              patch.object(session.rng, "randint", return_value=6)):
            result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        self.assertEqual(result["damage"], 4)
        self.assertNotIn("storm_giant_ancestry", [e["trait"] for e in result["species_effects"]])
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 2)
        self.assertTrue(state["giant_ancestry_armed"])

    def test_taking_damage_answers_with_thunder_on_the_attacker(self):
        session = self.storm()
        enemy = foe(session)
        with (patch("game.roll_d20", return_value=15), patch("game.roll_damage", return_value=3),
              patch.object(session.rng, "randint", return_value=6)):
            result = session.resolve_enemy_attack(enemy)
        self.assertEqual(session.character["current_hp"], 17)
        thunder = [e for e in result["species_effects"] if e["trait"] == "storm_giant_ancestry"]
        self.assertEqual(len(thunder), 1)
        self.assertEqual(thunder[0]["target_id"], "storm-foe")
        self.assertEqual(thunder[0]["damage"], 6)
        self.assertEqual(thunder[0]["damage_type"], "thunder")
        self.assertEqual(thunder[0]["raw_rolls"], [6])
        self.assertNotIn("push_ft", thunder[0])
        self.assertEqual(enemy["current_hp"], 14)
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 1)
        self.assertFalse(state["giant_ancestry_armed"])

    def test_a_miss_or_an_unarmed_ancestry_answers_nothing(self):
        session = self.storm()
        enemy = foe(session)
        with patch("game.roll_d20", return_value=2):
            result = session.resolve_enemy_attack(enemy)
        self.assertEqual(result["damage"], 0)
        self.assertEqual(enemy["current_hp"], 20)
        self.assertEqual(session.character["species_trait_state"]["giant_ancestry_uses_remaining"], 2)

        session.resolve_species_trait_action("arm_giant_ancestry", armed=False)
        with (patch("game.roll_d20", return_value=15), patch("game.roll_damage", return_value=3)):
            session.resolve_enemy_attack(enemy)
        self.assertEqual(enemy["current_hp"], 20)
        self.assertEqual(session.character["species_trait_state"]["giant_ancestry_uses_remaining"], 2)

    def test_a_goliath_dropped_to_zero_cannot_react(self):
        session = self.storm(hp=2)
        enemy = foe(session)
        with (patch("game.roll_d20", return_value=15), patch("game.roll_damage", return_value=5),
              patch.object(session.rng, "randint", return_value=6)):
            session.resolve_enemy_attack(enemy)
        self.assertEqual(session.character["current_hp"], 0)
        self.assertEqual(enemy["current_hp"], 20)
        self.assertEqual(session.character["species_trait_state"]["giant_ancestry_uses_remaining"], 2)


if __name__ == "__main__":
    unittest.main()
