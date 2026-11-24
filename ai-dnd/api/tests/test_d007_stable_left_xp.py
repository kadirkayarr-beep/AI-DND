"""D-007 (Kadir K8, 2026-11-15): a creature that went down is paid once, also when the fight ends as
`player_stable` or `participants_left` (before this, only target_defeated / parley / relocated paid)."""
from __future__ import annotations

import unittest

import game
from api.tests.test_dilim4b_combat_xp import fighter, person


class StableAndLeftXp(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7001)
        fighter(self.s)
        self.world = self.s.world_state

    def fight(self, *people):
        self.world["npcs"] = list(people)
        self.s.start_combat(people[0])
        for foe in people[1:]:
            self.s.join_combat_participants([foe["id"]])

    def stable_player(self):
        self.s.character["current_hp"] = 0
        self.world["player_combat_status"] = "unconscious"
        self.s.ensure_death_state()["stable"] = True

    def spare_type(self, npc):
        npc.update(hostile=False, reality_layer="PROCEDURAL_LOCAL_FICTION")

    def test_dead_foe_is_paid_when_the_fight_ends_player_stable(self):
        dead = person("drunk1", "ayyaş")
        spare = person("towns1", "ayyaş")
        self.fight(dead, spare)
        self.spare_type(spare)
        dead.update(current_hp=0, combat_status="dead")
        self.stable_player()
        ended = self.s._combat_end_if_decided()
        self.assertEqual(ended["reason"], "player_stable")
        self.assertEqual(self.s.character["xp"], 10)
        self.assertEqual(self.world["xp_awarded_event_ids"].count("combat:foe:drunk1"), 1)

    def test_same_foe_is_not_paid_twice_across_two_fights(self):
        dead = person("drunk1", "ayyaş")
        spare = person("towns1", "ayyaş")
        self.fight(dead, spare)
        self.spare_type(spare)
        dead.update(current_hp=0, combat_status="dead")
        self.stable_player()
        self.s._combat_end_if_decided()
        self.assertEqual(self.s.character["xp"], 10)
        import xp
        again = {"combat_id": "c2", "participants": ["player", "drunk1"]}
        self.assertIsNone(xp.award_defeated_combat(again, self.world, self.s.character, person_kind=game.person_fight_kind))
        self.assertEqual(self.s.character["xp"], 10)
        self.assertEqual(self.world["xp_awarded_event_ids"].count("combat:foe:drunk1"), 1)

    def test_snapshot_restore_takes_the_xp_back_and_replay_pays_once(self):
        dead = person("drunk1", "ayyaş")
        spare = person("towns1", "ayyaş")
        self.fight(dead, spare)
        self.spare_type(spare)
        dead.update(current_hp=0, combat_status="dead")
        self.stable_player()
        snapshot = self.s._capture_runtime_snapshot()  # the real undo path, not a hand copy
        self.s._combat_end_if_decided()
        self.assertEqual(self.s.character["xp"], 10)
        self.s._restore_runtime_snapshot(snapshot)
        self.world = self.s.world_state
        self.assertEqual(self.s.character["xp"], 0)
        self.assertNotIn("combat:foe:drunk1", self.world["xp_awarded_event_ids"])
        self.s._combat_end_if_decided()
        self.assertEqual(self.s.character["xp"], 10)

    def test_participants_left_pays_a_downed_leaver_once(self):
        leaver = person("drunk1", "ayyaş")
        self.fight(leaver)
        leaver.update(current_hp=0, combat_status="dead")
        ended = self.s._combat_end_if_decided(excluded_participant_ids=("drunk1",))
        self.assertEqual(ended["reason"], "participants_left")
        self.assertEqual(self.s.character["xp"], 10)

    def test_a_foe_that_only_left_alive_pays_nothing(self):
        leaver = person("drunk1", "ayyaş")
        self.fight(leaver)
        self.s.remove_combat_participant("drunk1")
        self.assertEqual(self.world["combat"]["end_reason"], "participants_left")
        self.assertEqual(self.s.character["xp"], 0)


if __name__ == "__main__":
    unittest.main()
