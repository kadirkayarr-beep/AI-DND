"""Dilim 4B carry-over (Task 1 F2 / Task 4 F1): a campaign whose save is older than format 4 (formats 1..3) crossing
to level 5 — in a won fight or through a finished quest — no longer raises out of the ending and locks every later
turn. The session boundary moves the campaign to save format 6 in place and admits the result through the real save
validator; a refused admission still puts everything back, the old format included (nothing half-written).

The old saves are real ones: written by `save_game` at the old version and read back by `load_game` into a fresh
session (the product's load path), never a format number set on a live session."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adventure.play as play
import character_progression as cp
import game
import xp
from api.tests.test_dilim4b_adventure_xp import plant
from api.tests import test_wield_front as wield_front
from api.tests.journeys.runner import JourneyCase
from api.tests import test_dilim4b_combat_xp as combat_xp
from api.tests.test_dilim4b_combat_xp import ATTACK, beat, person
from api.tests.test_roadmap_c14_fighter import bundle, spec

SEED = 4843


def legacy_save(version, directory):
    """A Fighter 3 whose numeric level is 4 at 6490 XP (10 short of 5), saved at ``version`` and loaded back."""
    session = game.create_session(seed=SEED)
    cp.create_at_level(session, spec(), 3, bundle(3))
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    session.world_state["xp_awarded_event_ids"] = []
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state,
                              6490 - session.character["xp"], "quest:setup-four")
    session._xp_level_up = None
    session.character.pop("weapon_proficiencies", None)   # a format 1..3 file never held the list (read-time grant)
    session._persisted_engine_format = version
    path = Path(directory) / f"v{version}.json"
    session.save_game(path)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == version
    loaded = game.create_session(seed=SEED)
    loaded.load_game(path)
    assert loaded._persisted_engine_format == version
    assert (loaded.character["level"], loaded.character["progression_level"], loaded.character["xp"]) == (4, 3, 6490)
    return loaded


def reloaded(session, directory, name):
    path = Path(directory) / name
    session.save_game(path)
    version = json.loads(path.read_text(encoding="utf-8"))["version"]
    fresh = game.create_session(seed=SEED)
    fresh.load_game(path)
    return version, fresh


class LegacySaveCrossesToFive(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name

    def test_a_won_fight_crosses_to_five_and_the_campaign_moves_to_format_six(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                session = legacy_save(version, self.directory)
                guard = person("guard1", "muhafız")
                session.world_state["npcs"] = [guard]
                ended = beat(session, guard)
                self.assertEqual(ended["reason"], "target_defeated")
                self.assertFalse(session.world_state["combat"]["active"])
                self.assertEqual((session.character["xp"], session.character["level"]), (6515, 5))
                self.assertEqual(session.character["progression_level"], 3)
                self.assertEqual(session._persisted_engine_format, 6)
                self.assertEqual(session._xp_level_up["new_level"], 5)
                self.assertIn("combat:foe:guard1", session.world_state["xp_awarded_event_ids"])
                saved_version, fresh = reloaded(session, self.directory, f"after-fight-v{version}.json")
                self.assertEqual(saved_version, 6)
                self.assertEqual((fresh.character["xp"], fresh.character["level"], fresh._persisted_engine_format),
                                 (6515, 5, 6))
                self.assertEqual(fresh.world_state["xp_awarded_event_ids"], session.world_state["xp_awarded_event_ids"])
                # a later fight is an ordinary one: it ends and pays once
                drunk = person("drunk1", "ayyaş")
                fresh.world_state["npcs"].append(drunk)
                self.assertEqual(beat(fresh, drunk)["reason"], "target_defeated")
                self.assertEqual(fresh.character["xp"], 6525)
                self.assertFalse(fresh.world_state["combat"]["active"])

    def test_a_finished_quest_crosses_to_five_and_is_paid(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                session = legacy_save(version, self.directory)
                session.world_state["npcs"].extend([
                    {"id": "npc.source", "name": "Marek", "location": "tavern", "current_hp": 12,
                     "combat_status": "active"},
                    {"id": "npc.target", "name": "Elin", "location": "tavern", "current_hp": 9,
                     "combat_status": "active"}])
                quest = plant(session, "tavern", "npc.source", "npc.target")
                play.settle_session(session)
                self.assertEqual((session.character["xp"], session.character["level"]), (6530, 5))
                self.assertEqual(quest["reward_application_id"], "quest:adv.delivery:success")
                self.assertEqual(session._persisted_engine_format, 6)
                play.settle_session(session)                       # a later settle: nothing more, no refusal
                self.assertEqual(session.character["xp"], 6530)
                saved_version, fresh = reloaded(session, self.directory, f"after-quest-v{version}.json")
                self.assertEqual((saved_version, fresh.character["level"], fresh.character["xp"]), (6, 5, 6530))

    def test_a_crossing_below_five_keeps_the_old_format(self):
        session = legacy_save(3, self.directory)
        session.character["xp"] = 2000                             # numeric level stays 4; 2000 + 25 stays below 6500
        guard = person("guard1", "muhafız")
        session.world_state["npcs"] = [guard]
        beat(session, guard)
        self.assertEqual((session.character["level"], session._persisted_engine_format), (4, 3))

    def test_a_refused_admission_puts_everything_back_with_the_old_format(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                session = legacy_save(version, self.directory)
                before = session._capture_runtime_snapshot()
                with patch("game._validate_save_payload", side_effect=ValueError("injected admission refusal")):
                    with self.assertRaises(ValueError):
                        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 10,
                                                  "quest:refused-five")
                self.assertEqual(session._capture_runtime_snapshot(), before)
                self.assertEqual(session._persisted_engine_format, version)
                self.assertEqual((session.character["level"], session.character["xp"]), (4, 6490))


class LegacySaveCrossesToFiveRoute(JourneyCase):
    """The same through the real routes: the campaign is stored at format 3 and resumed from the store."""
    use_setup = wield_front.WieldFront.use_setup
    session = wield_front.WieldFront.session
    world = wield_front.WieldFront.world
    flag = wield_front.WieldFront.flag
    play = wield_front.WieldFront.play
    say = wield_front.WieldFront.say
    reload = wield_front.WieldFront.reload
    start = combat_xp.CombatXpRoutes.start
    win = combat_xp.CombatXpRoutes.win

    async def test_a_stored_format_three_campaign_wins_its_way_to_five(self):
        await self.start(SEED)
        session = self.session
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 6490, "quest:setup-four")
        session._xp_level_up = None
        session.character.pop("weapon_proficiencies", None)
        session._persisted_engine_format = 3
        self.manager.save_campaign(self.campaign_id)
        self.assertEqual(self.store.get_campaign(self.campaign_id).payload["engine_save"]["version"], 3)
        await self.reload()
        self.assertEqual(self.session._persisted_engine_format, 3)
        self.assertEqual((self.session.character["level"], self.session.character["xp"]), (4, 6490))
        await self.win()                                            # each turn answered 200 (no failures)
        self.assertEqual((self.session.character["level"], self.session.character["xp"]), (5, 6515))
        stored = self.store.get_campaign(self.campaign_id).payload["engine_save"]
        self.assertEqual((stored["version"], stored["player"]["level"], stored["player"]["xp"]), (6, 5, 6515))
        await self.reload()
        self.assertEqual((self.session.character["level"], self.session._persisted_engine_format), (5, 6))
        await self.say("Muhafıza saldırıyorum", intent=ATTACK)      # a later turn is answered (the foe is down)
        self.assertEqual(self.session.character["xp"], 6515)


if __name__ == "__main__":
    unittest.main()
