"""Bounded XP receipt regressions; no saved campaigns or real model."""
import copy
import unittest

import xp


def character():
    return {"class": "Fighter", "level": 1, "xp": 0,
            "max_hp": 12, "current_hp": 12, "proficiency_bonus": 2}


class XpReceiptRegression(unittest.TestCase):
    def test_many_defeated_participants_grant_once_with_bounded_receipt(self):
        player = character()
        ids = [f"monster_{i:02d}_long_creature_id" for i in range(20)]
        world = {"npcs": [{"id": identity, "combat_status": "dead",
                           "current_hp": 0, "xp_reward": 5} for identity in ids],
                 "flags": {"turn_index": 42}, "xp_awarded_event_ids": []}
        combat = {"participants": ["player", *ids]}
        first = xp.award_defeated_combat(combat, world, player)
        self.assertIsNotNone(first)
        self.assertEqual(first["xp_gained"], 100)
        self.assertEqual(player["xp"], 100)
        self.assertEqual(len(world["xp_awarded_event_ids"]), 1)
        self.assertLessEqual(len(world["xp_awarded_event_ids"][0]), 187)
        self.assertIsNone(xp.award_defeated_combat(combat, world, player))
        self.assertEqual(player["xp"], 100)
        xp.validate_saved_advancement(player, world)

    def test_more_than_500_distinct_server_awards_do_not_disappear(self):
        player = character()
        world = {"xp_awarded_event_ids": [f"combat:{i}" for i in range(500)]}
        before = copy.deepcopy(world)
        awarded = xp.apply_xp(player, world, 50, "combat:500")
        self.assertIsNotNone(awarded)
        self.assertEqual(player["xp"], 50)
        self.assertEqual(len(world["xp_awarded_event_ids"]), len(before["xp_awarded_event_ids"]) + 1)
        xp.validate_saved_advancement(player, world)


if __name__ == "__main__":
    unittest.main()
