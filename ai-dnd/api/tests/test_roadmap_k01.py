"""K01: effect targets are resolved by one rule-aware owner (species effects included).

The Necrotic Shroud adapter must not treat the whole NPC list as "active"; a target is affected only when it is a
canonical creature of the current scene, alive and active, a combat participant when combat is open, and inside the
rule's own range. An unknown distance is never invented.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import effect_targeting
from api.tests.test_species_traits import make_session


def creature(session, creature_id, **facts):
    npc = {
        "id": creature_id, "name": creature_id, "location": session.world_state["location"],
        "combat_status": "active", "current_hp": 10, "max_hp": 10, "armor_class": 10,
        "charisma_save_bonus": 0,
    }
    npc.update(facts)
    session.world_state["npcs"].append(npc)
    return npc


class TargetEligibilityTests(unittest.TestCase):
    def build(self):
        session = make_session("Aasimar", level=3)
        session.world_state["npcs"].clear()  # the default scene NPC is not part of this matrix
        creature(session, "near-fail", distance_ft=5)
        creature(session, "near-pass", distance_ft=10)
        creature(session, "far-active", distance_ft=60)
        creature(session, "other-scene", distance_ft=5, location="harbour")
        creature(session, "ineligible", distance_ft=5, combat_status="dead")
        creature(session, "unknown-distance")
        creature(session, "ally", distance_ft=5, combat_side="party")  # PHB 2024: "other than your allies"
        return session

    def test_shroud_only_reaches_rule_eligible_targets(self):
        session = self.build()
        calls = {"count": 0}

        def d20():
            calls["count"] += 1
            return 1 if calls["count"] != 2 else 20  # 2nd roller (near-pass) succeeds; any extra roller fails

        with patch("game.roll_d20", side_effect=d20):
            result = session.resolve_species_trait_action("celestial_revelation", form="necrotic_shroud")
        npcs = {npc["id"]: npc for npc in session.world_state["npcs"]}
        frightened = {key: "frightened_until_player_turn" in npc for key, npc in npcs.items()}
        obs = {
            "near_failed_save_frightened": frightened["near-fail"],
            "far_active_frightened": frightened["far-active"],
            "near_successful_save_frightened": frightened["near-pass"],
            "ineligible_target_affected": frightened["ineligible"] or frightened["other-scene"],
        }
        self.assertIs(obs["near_failed_save_frightened"], True)
        self.assertIs(obs["far_active_frightened"], False)
        self.assertIs(obs["near_successful_save_frightened"], False)
        self.assertIs(obs["ineligible_target_affected"], False)
        self.assertFalse(frightened["unknown-distance"], "an unknown distance is never invented")
        self.assertFalse(frightened["ally"], "the source excludes the caster's allies")
        self.assertEqual([save["target_id"] for save in result["effects"]["saves"]], ["near-fail", "near-pass"])

    def test_owner_returns_the_same_matrix_outside_combat_and_in_combat(self):
        session = self.build()
        spec = effect_targeting.EffectSpec("necrotic_shroud", range_ft=10, source_ref="PHB 2024 Aasimar: Necrotic Shroud",
                                           excludes_allies=True)
        self.assertEqual(effect_targeting.eligible_effect_targets(session, "player", spec), ["near-fail", "near-pass"])
        combat = session.world_state["combat"]
        combat.update(active=True, participants=["player", "near-fail", "far-active", "ineligible"])
        self.assertEqual(effect_targeting.eligible_effect_targets(session, "player", spec), ["near-fail"],
                         "in combat a target must also be a participant")

    def test_a_rule_without_a_range_keeps_every_other_requirement(self):
        session = self.build()
        spec = effect_targeting.EffectSpec("explicit_exception", range_ft=None, source_ref="explicit rule exception")
        self.assertEqual(effect_targeting.eligible_effect_targets(session, "player", spec),
                         ["near-fail", "near-pass", "far-active", "unknown-distance", "ally"])

    def test_an_accepted_companion_is_an_ally_even_without_a_combat_side(self):
        session = self.build()
        creature(session, "companion", distance_ft=5)
        session.world_state["companions"] = [{"npc_id": "companion", "joined_turn": 0, "source": "test"}]
        spec = effect_targeting.EffectSpec("necrotic_shroud", range_ft=10, source_ref="test", excludes_allies=True)
        self.assertNotIn("companion", effect_targeting.eligible_effect_targets(session, "player", spec))

    def test_an_authoritative_pair_distance_overrides_the_creature_field(self):
        session = self.build()
        session.world_state["attack_environment"] = {"pairs": {"player|far-active": {"distance_ft": 5},
                                                               "player|near-fail": {"distance_ft": 40}}}
        spec = effect_targeting.EffectSpec("necrotic_shroud", range_ft=10, source_ref="test", excludes_allies=True)
        self.assertEqual(effect_targeting.eligible_effect_targets(session, "player", spec), ["near-pass", "far-active"])

    def test_combat_path_through_the_game_uses_the_same_matrix(self):
        session = self.build()
        npcs = {npc["id"]: npc for npc in session.world_state["npcs"]}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(npcs["near-fail"])
        combat = session.world_state["combat"]
        self.assertTrue(combat["active"])
        self.assertIn("near-fail", combat["participants"])
        self.assertNotIn("far-active", combat["participants"], "only the engaged creature joined combat")
        with patch("game.roll_d20", return_value=1):
            result = session.resolve_species_trait_action("celestial_revelation", form="necrotic_shroud")
        self.assertEqual([save["target_id"] for save in result["effects"]["saves"]], ["near-fail"])

    def test_a_malformed_spec_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            effect_targeting.EffectSpec("x", range_ft=-5, source_ref="r")
        with self.assertRaises(ValueError):
            effect_targeting.EffectSpec("x", range_ft=10, source_ref="")


if __name__ == "__main__":
    unittest.main()
