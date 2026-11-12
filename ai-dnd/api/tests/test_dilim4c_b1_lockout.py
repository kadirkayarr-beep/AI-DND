"""4C.6 — B1 (D-001, D-013): an experience award that can never be recorded no longer locks the campaign.

Before: a refused award (a full 10 000-receipt list, the XP cap, an unknown class at a level step, a level-5 crossing the
real save admission refuses on an old or hand-edited save, a quest whose receipt exists but whose marker is lost) raised
out of the fight's ending, the knock-out, the turn-end job hook or the quest settle, and the next turn tried it again:
no in-game way out. Now the award alone is put back (character, receipt list, pending announcement, save format) and
logged, and play goes on without that XP:
- a fight ends and a knock-out stands (callers keep their world references);
- a finished job keeps its close and its wage; its XP is marked forfeited on the thread (``xp_forfeited: True``), so no
  later turn owes it again; old saves have no such key;
- a finished adventure pays its gold, item and standing under its marker; its XP is paid last and, when refused, is
  forfeited (no receipt); a lost marker whose receipt exists is put back without paying anything again.
Nothing is paid twice, and money never moves because of XP.
"""
from __future__ import annotations

import copy
import tempfile
import types
import unittest
from unittest.mock import patch

import adventure.play as play
import game
import spell_concentration
import world_threads
import xp
from api.tests import test_dilim4b_job_xp as jobs
from api.tests.test_dilim4b_adventure_xp import MARKER, POOL, QUEST_ID, plant, refused_admission, to_level_four
from api.tests.test_dilim4b_combat_xp import fighter, person
from api.tests.test_dilim4b_legacy_level_five import legacy_save, reloaded
from api.tests.test_phase7_package import bound_state


def _refused(*_args, **_kwargs):
    raise ValueError("injected: save admission refused")


_refused._session_bound = True


class CombatAwardRefused(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name

    def test_a_refused_level_five_admission_still_ends_the_fight_without_the_xp(self):
        """D-013: a format 1..3 save whose crossing the admission refuses used to keep the fight active forever."""
        for version in (1, 2, 3):
            with self.subTest(version=version):
                session = legacy_save(version, self.directory)
                guard = person("guard1", "muhafız")
                session.world_state["npcs"] = [guard]
                session.start_combat(guard)
                guard.update(current_hp=0, combat_status="dead")
                session.ensure_combat_state()
                receipts = list(session.world_state["xp_awarded_event_ids"])
                with patch.object(game, "_validate_save_payload", _refused):
                    ended = session._combat_end_if_decided()
                self.assertEqual(ended["reason"], "target_defeated")
                self.assertFalse(session.world_state["combat"]["active"])
                self.assertEqual((session.character["xp"], session.character["level"]), (6490, 4))
                self.assertEqual(session._persisted_engine_format, version)
                self.assertIsNone(session._xp_level_up)
                self.assertEqual(session.world_state["xp_awarded_event_ids"], receipts)
                saved_version, fresh = reloaded(session, self.directory, f"forfeit-v{version}.json")
                self.assertEqual((saved_version, fresh.character["xp"], fresh.character["level"]), (version, 6490, 4))
                # nothing is locked: the next fight is an ordinary one and crosses to 5
                drunk = person("drunk1", "ayyaş")
                fresh.world_state["npcs"].append(drunk)
                fresh.start_combat(drunk)
                drunk.update(current_hp=0, combat_status="dead")
                fresh.ensure_combat_state()
                fresh._combat_end_if_decided()
                self.assertEqual((fresh.character["xp"], fresh.character["level"], fresh._persisted_engine_format),
                                 (6500, 5, 6))
                self.assertNotIn("combat:foe:guard1", fresh.world_state["xp_awarded_event_ids"])

    def test_an_unknown_class_at_a_level_step_ends_the_fight_without_the_xp(self):
        session = game.create_session(seed=4801)
        fighter(session)
        session.character["xp"] = 280                              # +25 crosses to level 2: hit points need the class
        guard = person("guard1", "muhafız")
        session.world_state["npcs"] = [guard]
        session.start_combat(guard)
        guard.update(current_hp=0, combat_status="dead")
        session.ensure_combat_state()
        session.character["class"] = "Jester"
        before = copy.deepcopy(session.character)
        ended = session._combat_end_if_decided()
        self.assertEqual(ended["reason"], "target_defeated")
        self.assertFalse(session.world_state["combat"]["active"])
        self.assertEqual(session.character, before)
        self.assertEqual(session.world_state["xp_awarded_event_ids"], [])
        self.assertIsNone(session._xp_level_up)

    def test_a_refused_knock_out_award_still_knocks_out_and_keeps_the_callers_references(self):
        """Task 8 park: the award at the blow used to raise with the knock-out half-written."""
        session = legacy_save(3, tempfile.mkdtemp(dir=self.directory))
        guard, other = person("guard1", "muhafız"), person("guard2", "muhafız")
        session.world_state["npcs"] = [guard, other]
        session.start_combat(guard)
        session.join_combat_participants(["guard2"])
        combat = session.world_state["combat"]
        receipts = list(session.world_state["xp_awarded_event_ids"])
        token = game._ACTIVE_SESSION.set(session)
        try:
            with patch.object(game, "_validate_save_payload", _refused):
                session.apply_npc_damage(guard, 8, knock_out=True)
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual((guard["combat_status"], guard["current_hp"]), ("unconscious", 1))
        self.assertTrue(any(npc is guard for npc in session.world_state["npcs"]))   # still the live record
        self.assertIs(session.world_state["combat"], combat)
        self.assertTrue(combat["active"])
        self.assertEqual((session.character["xp"], session.character["level"], session._persisted_engine_format),
                         (6490, 4, 3))
        self.assertEqual(session.world_state["xp_awarded_event_ids"], receipts)
        self.assertIsNone(session._xp_level_up)


class QuestAwardRefused(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4831)
        self.world = self.session.world_state
        self.world["location"] = "tavern"
        self.world["npcs"].extend([
            {"id": "npc.source", "name": "Marek", "location": "tavern", "current_hp": 12, "combat_status": "active"},
            {"id": "npc.target", "name": "Elin", "location": "tavern", "current_hp": 9, "combat_status": "active"},
        ])
        self.world["xp_awarded_event_ids"] = []
        self.session.campaign_lore_state = bound_state()

    def purse(self):
        return self.world.get("currency", {}).get("player", 0)

    def quest(self):
        return next(q for q in self.world["quests"] if q.get("quest_id") == QUEST_ID)

    def plant(self, **kwargs):
        return plant(self.session, "tavern", "npc.source", "npc.target", **kwargs)

    def assert_gold_without_xp(self, purse, xp_before, receipts):
        self.assertEqual(self.purse(), purse + 25)
        self.assertNotIn(POOL, self.world.get("currency", {}))
        self.assertEqual(self.quest()["reward_application_id"], MARKER)
        self.assertEqual(self.session.character.get("xp", 0), xp_before)
        self.assertEqual(self.world["xp_awarded_event_ids"], receipts)
        self.assertIsNone(self.session._xp_level_up)

    def test_a_full_receipt_list_pays_the_gold_and_forfeits_the_xp_once(self):
        self.plant()
        self.world["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        receipts, purse = list(self.world["xp_awarded_event_ids"]), self.purse()
        play.settle_session(self.session)
        self.assert_gold_without_xp(purse, 0, receipts)
        play.settle_session(self.session)                           # a later settle: nothing more, no refusal
        self.assert_gold_without_xp(purse, 0, receipts)

    def test_the_xp_cap_pays_the_gold_and_forfeits_the_xp(self):
        self.plant()
        purse = self.purse()
        with patch.object(xp, "MAX_STORED_XP", 10):
            play.settle_session(self.session)
        self.assert_gold_without_xp(purse, 0, [])

    def test_a_refused_level_five_admission_pays_gold_and_standing_and_forfeits_the_xp(self):
        to_level_four(self.session)
        self.plant(faction={"id": "faction:watch", "standing": 1})
        receipts, purse = list(self.world["xp_awarded_event_ids"]), self.purse()
        with patch.object(game, "_validate_save_payload", refused_admission):
            play.settle_session(self.session)
        self.assert_gold_without_xp(purse, 6490, receipts)
        self.assertEqual(self.session.character["level"], 4)
        self.assertEqual(self.session._persisted_engine_format, game.SAVE_FORMAT_VERSION)
        self.assertEqual(self.session.campaign_lore_state.faction_standings[0].standing, 1)
        play.settle_session(self.session)                           # admitted now, but the branch is settled: nothing
        self.assert_gold_without_xp(purse, 6490, receipts)

    def test_a_lost_marker_whose_receipt_exists_is_put_back_without_paying_again(self):
        self.plant()
        play.settle_session(self.session)
        paid = (self.purse(), self.session.character["xp"], list(self.world["xp_awarded_event_ids"]))
        self.assertEqual(paid[1:], (40, [MARKER]))
        self.session._xp_level_up = None
        self.quest()["reward_application_id"] = None                # a hand-edited save lost the marker
        play.settle_session(self.session)
        self.assertEqual((self.purse(), self.session.character["xp"], self.world["xp_awarded_event_ids"]), paid)
        self.assertEqual(self.quest()["reward_application_id"], MARKER)
        self.assertIsNone(self.session._xp_level_up)


class JobAwardRefused(jobs._JobCase):
    """The 19d errand: a delivery whose XP cannot be recorded is answered, paid its wage once, and never owed again."""
    deliver_turn = jobs.JobXp.deliver_turn
    ready_to_deliver = jobs.JobXp.ready_to_deliver
    assert_untouched = jobs.JobXp.assert_untouched

    def assert_forfeited(self, purse, receipts):
        thread = self.delivered_thread()
        self.assertEqual((thread["status"], thread["xp_due"], thread.get("xp_forfeited")), ("done", 25, True))
        self.assertEqual(self.xp(), 0)
        self.assertEqual(self.world.get("xp_awarded_event_ids", []), receipts)
        self.assertEqual(self.purse() - purse, jobs.WAGE)
        self.assertEqual(xp.job_grants_due(self.world), [])

    async def test_a_full_receipt_list_delivers_pays_the_wage_and_forfeits_the_xp(self):
        purse = self.purse()
        await self.ready_to_deliver()
        self.world["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        receipts = list(self.world["xp_awarded_event_ids"])
        self.save()
        out = (await self.deliver_turn()).json()
        self.assertIsNone(out.get("level_up"))
        self.assert_forfeited(purse, receipts)
        await self.say("etrafa bakıyorum")                          # the next turn is answered and owes nothing
        self.assert_forfeited(purse, receipts)
        await self.restart()                                       # the save holds the mark and reloads
        self.assert_forfeited(purse, receipts)
        await self.say("etrafa bakıyorum")
        self.assert_forfeited(purse, receipts)

    async def test_undo_takes_back_the_delivery_and_its_forfeit_mark(self):
        purse = self.purse()
        await self.ready_to_deliver()
        self.world["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        receipts = list(self.world["xp_awarded_event_ids"])
        self.save()
        await self.deliver_turn()
        self.assert_forfeited(purse, receipts)
        await self.undo()
        self.assert_untouched(purse)
        self.assertNotIn("xp_forfeited", self.delivered_thread())
        self.assertEqual(self.world["xp_awarded_event_ids"], receipts)
        self.at_recipient()
        await self.deliver_turn()                                  # delivered again: one wage, still no XP
        self.assert_forfeited(purse, receipts)

    async def test_the_xp_cap_delivers_and_forfeits_the_xp(self):
        purse = self.purse()
        await self.ready_to_deliver()
        with patch.object(xp, "MAX_STORED_XP", 10):
            await self.deliver_turn()
        self.assert_forfeited(purse, [])

    async def test_the_forfeit_mark_is_validated_and_a_forfeited_job_may_be_trimmed(self):
        await self.accept()
        thread = self.delivered_thread()
        good = copy.deepcopy(self.state())
        record = world_threads.by_id({world_threads.KEY: good}, thread["thread_id"])
        record.update(status="done", xp_due=25, xp_forfeited=True)
        world_threads.validate(good)
        for bad in (False, 1, "true", None):
            with self.subTest(bad=bad):
                broken = copy.deepcopy(good)
                world_threads.by_id({world_threads.KEY: broken}, thread["thread_id"])["xp_forfeited"] = bad
                with self.assertRaises(ValueError):
                    world_threads.validate(broken)
        without_due = copy.deepcopy(good)
        world_threads.by_id({world_threads.KEY: without_due}, thread["thread_id"]).pop("xp_due")
        with self.assertRaises(ValueError):
            world_threads.validate(without_due)
        self.assertFalse(world_threads._unpaid(self.world, record))          # forfeited: an old closing like any other
        record.pop("xp_forfeited")
        self.assertTrue(world_threads._unpaid(self.world, record))

    async def test_xp_due_is_bounded_by_the_xp_owner_cap(self):
        """D-004: the thread validator reads `xp.MAX_GRANT`, so a save-valid ``xp_due`` is always payable."""
        await self.accept()
        thread = self.delivered_thread()
        done = copy.deepcopy(self.state())
        record = world_threads.by_id({world_threads.KEY: done}, thread["thread_id"])
        record.update(status="done", xp_due=60)
        world_threads.validate(done)
        with patch.object(xp, "MAX_GRANT", 50):
            with self.assertRaises(ValueError):
                world_threads.validate(done)
            record["xp_due"] = 50
            world_threads.validate(done)


class ConcentrationIsCheckedBeforeItIsWritten(unittest.TestCase):
    """Design §8: a new 4C field is tried on a copy before it is written, so a bad record never reaches a save."""

    def test_a_record_the_save_would_refuse_is_never_written(self):
        stale = {"spell_id": "Bless", "combat_id": "old", "started_round": 1, "slot_level": 1, "targets": ["player"]}
        session = types.SimpleNamespace(
            world_state={"combat": {"active": True, "combat_id": "c1", "round": 2}, spell_concentration.KEY: dict(stale)},
            character={})
        with self.assertRaises(ValueError):
            spell_concentration.start(session, "Bless", 10, ["player"])
        self.assertEqual(session.world_state[spell_concentration.KEY], stale)
        spell_concentration.start(session, "Bless", 1, ["player"])
        self.assertEqual(session.world_state[spell_concentration.KEY]["combat_id"], "c1")


if __name__ == "__main__":
    unittest.main()
