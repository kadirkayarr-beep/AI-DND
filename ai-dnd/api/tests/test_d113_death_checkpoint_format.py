"""D-113 (YÜK-10): a Normal-mode death rollback puts the save format back together with the character.

A real format-5 save (written by `save_game`, read back by `load_game`) holds a level-4 hero at 10 000 XP: format 5
caps the earned level at 4, format 6 would require level 5. The fight's checkpoint is taken at format 5; an XP award
inside the fight crosses to level 5 and moves the campaign to format 6. A later Normal-mode death restores the
level-4 hero, so it must restore format 5 too, or the save validator refuses every later turn.

No live model, no shared database; the session seed is fixed.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import character_progression as cp
import game
import xp
from api.tests.test_roadmap_c14_fighter import bundle, spec

SEED = 4843


def legacy_v5_at_ten_thousand(directory):
    session = game.create_session(seed=SEED)
    cp.create_at_level(session, spec(), 3, bundle(3))
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    session.world_state["xp_awarded_event_ids"] = []
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state,
                              6490 - session.character["xp"], "quest:setup-four")
    session._xp_level_up = None
    session.character["xp"] = 10_000          # format 5 caps the earned level at 4
    session._persisted_engine_format = 5
    path = Path(directory) / "v5.json"
    session.save_game(path)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 5
    loaded = game.create_session(seed=SEED)
    loaded.load_game(path)
    assert loaded._persisted_engine_format == 5
    assert (loaded.character["level"], loaded.character["xp"]) == (4, 10_000)
    return loaded


class DeathRollbackKeepsSaveFormat(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name

    def _cross_then_die(self):
        session = legacy_v5_at_ten_thousand(self.directory)
        game._capture_combat_death_checkpoint(session=session)
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 10, "combat:foe:first")
        self.assertEqual((session.character["level"], session._persisted_engine_format), (5, 6))
        result = game._apply_player_damage(10_000, critical=False, took_damage=True, session=session)
        self.assertTrue(result["death_resolution"]["rolled_back"])
        return session

    def test_normal_death_restores_the_checkpoint_format_with_the_character(self):
        session = self._cross_then_die()
        self.assertEqual((session.character["level"], session.character["xp"]), (4, 10_000))
        self.assertEqual(session._persisted_engine_format, 5)
        payload = session.serialize_game_state()
        self.assertEqual(payload["version"], 5)
        game._validate_save_payload(payload)    # the real admission accepts the rolled-back campaign

    def test_rolled_back_campaign_saves_and_reloads_at_format_five(self):
        session = self._cross_then_die()
        path = Path(self.directory) / "after-death.json"
        session.save_game(path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 5)
        fresh = game.create_session(seed=SEED)
        fresh.load_game(path)
        self.assertEqual((fresh.character["level"], fresh._persisted_engine_format), (4, 5))

    def test_tampered_checkpoint_format_is_refused_before_anything_changes(self):
        session = legacy_v5_at_ten_thousand(self.directory)
        game._capture_combat_death_checkpoint(session=session)
        session.world_state["death_state"]["combat_checkpoint"]["persisted_engine_format"] = 99
        before = session._capture_runtime_snapshot()
        with self.assertRaises(ValueError):
            game._restore_combat_death_checkpoint("massive_damage", session=session)
        self.assertEqual(session._capture_runtime_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
