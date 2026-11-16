"""D-016 (Kadir K8, 2026-11-15): a killed foe pays once, like a knocked-out one, even when no fight is on."""
from __future__ import annotations

import unittest

import game
from api.tests.test_dilim4b_combat_xp import fighter, person


class KillOutsideFightPays(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4811)
        fighter(self.session)
        self.world = self.session.world_state

    def test_a_kill_with_no_fight_pays_a_guard_25_once(self):
        guard = person("guard1", "muhafız")
        self.world["npcs"] = [guard]
        self.session.apply_npc_damage(guard, 99)
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(guard["combat_status"], "dead")
        self.assertEqual(self.session.character["xp"], 25)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard1"])
        self.session.apply_npc_damage(guard, 5)  # already dead: nothing more
        self.assertEqual(self.session.character["xp"], 25)

    def test_a_kill_in_a_fight_still_pays_once_at_the_ending(self):
        guard = person("guard1", "muhafız")
        self.world["npcs"] = [guard]
        self.session.start_combat(guard)
        self.session.apply_npc_damage(guard, 99)
        self.assertEqual(self.session._combat_end_if_decided()["reason"], "target_defeated")
        self.assertEqual(self.session.character["xp"], 25)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard1"])

    def test_undo_style_restore_returns_xp_and_receipt(self):
        import copy
        guard = person("guard1", "muhafız")
        self.world["npcs"] = [guard]
        before = copy.deepcopy((self.session.character, self.world))
        self.session.apply_npc_damage(guard, 99)
        self.assertEqual(self.session.character["xp"], 25)
        self.session.character.clear(); self.session.character.update(before[0])
        self.world.clear(); self.world.update(before[1])
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.world["xp_awarded_event_ids"], [])

    def test_a_kill_pays_at_the_kill_even_if_the_player_then_leaves_the_fight(self):
        for reason in ("player_fled", "stood_down", "location_changed"):
            with self.subTest(reason=reason):
                session = game.create_session(seed=4812)
                fighter(session)
                world = session.world_state
                guard, other = person("guard1", "muhafız"), person("guard2", "muhafız")
                world["npcs"] = [guard, other]
                session.start_combat(guard)
                session.join_combat_participants(["guard2"])
                session.apply_npc_damage(guard, 99)
                self.assertEqual(session.character["xp"], 25)
                session.end_combat(reason)
                self.assertEqual(session.character["xp"], 25)  # not paid twice
                self.assertEqual(world["xp_awarded_event_ids"], ["combat:foe:guard1"])

    def test_real_snapshot_restore_returns_xp_and_receipt(self):
        guard = person("guard1", "muhafız")
        self.world["npcs"] = [guard]
        snapshot = self.session._capture_runtime_snapshot()
        self.session.apply_npc_damage(guard, 99)
        self.assertEqual(self.session.character["xp"], 25)
        self.session._restore_runtime_snapshot(snapshot)
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.session.world_state["xp_awarded_event_ids"], [])


if __name__ == "__main__":
    unittest.main()
