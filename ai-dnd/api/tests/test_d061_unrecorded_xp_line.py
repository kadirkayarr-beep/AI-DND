"""D-061 (Kadir kararı 2026-11-15, karar 4): an award that cannot be recorded is shown to the player as one line,
"<X> XP kaydedilemedi: <neden>.", in the turn's reply and in its history entry; Undo takes the line back with the turn.
Only a known refusal is forfeited (a full receipt list, the XP cap, a level step for an unknown class, a level-5 crossing
the save admission refuses on a record it admitted before the award). Any other ``ValueError`` is a bug: it is raised,
nothing is half-written, and the turn falls back whole.

Out of this decision (unchanged, see the ledger's Ruling): several jobs finished in one turn still forfeit together,
and a fight's forfeit still leaves no mark (the creature may be tried again).
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from unittest.mock import patch

import adventure.play as play
import game
import xp
from api.tests import test_d003_out_of_turn_xp_line as d003
from api.tests import test_dilim4b_job_xp as jobs
from api.tests.test_dilim4b_adventure_xp import plant
from api.tests.test_dilim4b_combat_xp import fighter, person
from api.tests.test_dilim4b_legacy_level_five import legacy_save
from api.tests.test_phase7_package import bound_state
from api.tests.test_species_action_quest_evidence import _stage_radiant_bounty
from api.tests.town_seed import fixed_town

FULL = "25 XP kaydedilemedi: kampanyanın ödül kaydı doldu."
PANEL_LINES = ("10 XP kaydedilemedi: kampanyanın ödül kaydı doldu. "
               "60 XP kaydedilemedi: kampanyanın ödül kaydı doldu.")


def _refuses_level_five(payload, *_args, **_kwargs):
    """The admission refuses the crossing itself: a level-5 record. A level-4 record passes."""
    if payload["player"]["level"] >= 5:
        raise ValueError("injected: save admission refused at level 5")


_refuses_level_five._session_bound = True


def _refuses_every_record(*_args, **_kwargs):
    """The record is invalid for a reason that has nothing to do with the award (a hand-edited field)."""
    raise ValueError("injected: unrelated record field")


_refuses_every_record._session_bound = True


class EngineLines(unittest.TestCase):
    """Each known refusal leaves exactly one line for the turn; the award writes nothing."""

    def fight_session(self, seed):
        session = game.create_session(seed=seed)
        fighter(session)
        guard = person("guard1", "muhafız")
        session.world_state["npcs"] = [guard]
        session.start_combat(guard)
        guard.update(current_hp=0, combat_status="dead")
        session.ensure_combat_state()
        return session

    def test_a_full_receipt_list_ends_the_fight_with_one_line(self):
        session = self.fight_session(6101)
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        receipts, character = list(session.world_state["xp_awarded_event_ids"]), copy.deepcopy(session.character)
        ended = session._combat_end_if_decided()
        self.assertEqual(ended["reason"], "target_defeated")
        self.assertFalse(session.world_state["combat"]["active"])
        self.assertEqual((session.character, session.world_state["xp_awarded_event_ids"]), (character, receipts))
        self.assertEqual(session._take_xp_unrecorded(), [FULL])
        self.assertEqual(session._take_xp_unrecorded(), [])          # taken once: the next turn has no line

    def test_an_unknown_class_at_a_level_step_has_its_own_line(self):
        session = self.fight_session(6102)
        session.character["xp"] = 280                              # +25 crosses to level 2: hit points need the class
        session.character["class"] = "Jester"
        before = copy.deepcopy(session.character)
        session._combat_end_if_decided()
        self.assertEqual(session.character, before)
        self.assertEqual(session._take_xp_unrecorded(),
                         ["25 XP kaydedilemedi: karakterinin sınıfı tanınmadığı için yeni seviyenin canı hesaplanamıyor."])

    def test_the_xp_cap_on_an_adventure_has_its_own_line(self):
        session = game.create_session(seed=6103)
        world = session.world_state
        world["location"] = "tavern"
        world["npcs"].extend([
            {"id": "npc.source", "name": "Marek", "location": "tavern", "current_hp": 12, "combat_status": "active"},
            {"id": "npc.target", "name": "Elin", "location": "tavern", "current_hp": 9, "combat_status": "active"},
        ])
        world["xp_awarded_event_ids"] = []
        session.campaign_lore_state = bound_state()
        plant(session, "tavern", "npc.source", "npc.target")
        with patch.object(xp, "MAX_STORED_XP", 10):
            play.settle_session(session)
        self.assertEqual((session.character.get("xp", 0), world["xp_awarded_event_ids"]), (0, []))
        self.assertEqual(session._take_xp_unrecorded(),
                         ["40 XP kaydedilemedi: deneyim puanın kaydın tutabileceği en yüksek değere ulaştı."])

    def test_a_level_five_crossing_the_admission_refuses_has_its_own_line(self):
        with tempfile.TemporaryDirectory() as directory:
            session = legacy_save(4, directory)                    # 6490 XP, level 4: +10 crosses to 5
            character, world = copy.deepcopy(session.character), copy.deepcopy(session.world_state)
            with patch.object(game, "_validate_save_payload", _refuses_level_five):
                self.assertIsNone(session._forfeit_unrecordable_xp(
                    xp.apply_xp, session.character, session.world_state, 10, "quest:refused-five"))
            self.assertEqual((session.character, session.world_state), (character, world))
            self.assertEqual((session._persisted_engine_format, session._xp_level_up), (4, None))
            self.assertEqual(session._take_xp_unrecorded(),
                             ["10 XP kaydedilemedi: eski kayıt dosyan 5. seviyeye geçişi taşıyamıyor."])


    def test_a_current_save_refused_at_the_crossing_is_not_called_an_old_save(self):
        """Review finding (DÜŞÜK): the old-save reason is only for a record still on an older save format."""
        with tempfile.TemporaryDirectory() as directory:
            session = legacy_save(4, directory)
            session._persisted_engine_format = 6
            with patch.object(game, "_validate_save_payload", _refuses_level_five):
                self.assertIsNone(session._forfeit_unrecordable_xp(
                    xp.apply_xp, session.character, session.world_state, 10, "quest:refused-five"))
            self.assertEqual(session._persisted_engine_format, 6)
            self.assertEqual(session._take_xp_unrecorded(),
                             ["10 XP kaydedilemedi: kayıt 5. seviyeye geçişi kabul etmedi."])


class OneLinePerForfeitedAward(unittest.TestCase):
    """Review finding (ORTA): a creature knocked out and then counted again when the fight ends is one forfeited
    award, so it is one line; another creature's award in the same fight still has its own amount."""

    def fight_session(self, seed, *foes):
        session = game.create_session(seed=seed)
        fighter(session)
        session.world_state["npcs"] = list(foes)
        session.start_combat(foes[0])
        session.ensure_combat_state()
        return session

    def knock_out_and_end(self, session, guard):
        session.apply_npc_damage(guard, guard.get("current_hp", 1), knock_out=True)
        self.assertEqual(guard["combat_status"], "unconscious")
        session._combat_end_if_decided()
        return session._take_xp_unrecorded()

    def test_a_knocked_out_guard_with_a_full_receipt_list_is_one_line(self):
        guard = person("guard1", "muhafız")
        session = self.fight_session(6111, guard)
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        self.assertEqual(self.knock_out_and_end(session, guard), [FULL])

    def test_an_unknown_class_knock_out_is_one_line(self):
        guard = person("guard1", "muhafız")
        session = self.fight_session(6112, guard)
        session.character["xp"] = 280
        session.character["class"] = "Jester"
        self.assertEqual(self.knock_out_and_end(session, guard),
                         ["25 XP kaydedilemedi: karakterinin sınıfı tanınmadığı için yeni seviyenin canı hesaplanamıyor."])

    def test_a_second_foe_at_the_fight_end_keeps_only_its_own_amount(self):
        guard, other = person("guard1", "muhafız"), person("guard2", "muhafız")
        session = self.fight_session(6113, guard, other)
        session.join_combat_participants(["guard2"])
        other.update(current_hp=0, combat_status="dead")
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        self.assertEqual(self.knock_out_and_end(session, guard), [FULL, FULL])  # 25 + 25 = the 50 really lost

    def test_the_next_turn_shows_a_new_forfeit_again(self):
        guard = person("guard1", "muhafız")
        session = self.fight_session(6114, guard)
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        self.assertEqual(self.knock_out_and_end(session, guard), [FULL])
        self.assertIsNone(session._forfeit_unrecordable_xp(
            xp.award_downed, guard, session.world_state, session.character,
            person_kind=game.person_fight_kind(guard)))
        self.assertEqual(session._take_xp_unrecorded(), [FULL])         # the memory is for one turn only


class UnrelatedErrorsAreRaised(unittest.TestCase):
    """The forfeit no longer swallows every ``ValueError``: an unknown one is raised and nothing is half-written."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.session = legacy_save(4, directory.name)

    def assert_put_back(self, character, world):
        self.assertEqual((self.session.character, self.session.world_state), (character, world))
        self.assertEqual((self.session._persisted_engine_format, self.session._xp_level_up), (4, None))
        self.assertEqual(self.session._take_xp_unrecorded(), [])

    def test_an_unrelated_value_error_from_the_award_is_raised(self):
        def broken(character, world):
            character["xp"] = 9999
            world["xp_awarded_event_ids"].append("quest:half-written")
            raise ValueError("an unrelated bug")

        character, world = copy.deepcopy(self.session.character), copy.deepcopy(self.session.world_state)
        with self.assertRaisesRegex(ValueError, "an unrelated bug"):
            self.session._forfeit_unrecordable_xp(broken, self.session.character, self.session.world_state)
        self.assert_put_back(character, world)

    def test_a_record_the_admission_refused_before_the_award_is_raised_at_the_crossing(self):
        """The debt row's case: a level-5 crossing on a record invalid for another reason is no XP forfeit."""
        character, world = copy.deepcopy(self.session.character), copy.deepcopy(self.session.world_state)
        self.session.world_state.pop("scene_state", None)
        world.pop("scene_state", None)
        with patch.object(game, "_validate_save_payload", _refuses_every_record):
            with self.assertRaisesRegex(ValueError, "injected: unrelated record field"):
                self.session._forfeit_unrecordable_xp(xp.apply_xp, self.session.character, self.session.world_state,
                                                      10, "quest:refused-five")
        self.assert_put_back(character, world)                     # the check's scene default-fill went back too

    def test_a_level_step_error_that_is_not_the_class_is_raised(self):
        character, world = copy.deepcopy(self.session.character), copy.deepcopy(self.session.world_state)
        with patch.object(xp, "_apply_numeric_level", side_effect=ValueError("numeric owner bug")):
            with self.assertRaisesRegex(ValueError, "numeric owner bug"):
                self.session._forfeit_unrecordable_xp(xp.apply_xp, self.session.character,
                                                      self.session.world_state, 10, "quest:refused-five")
        self.assert_put_back(character, world)


class TurnLine(jobs._JobCase):
    """The 19d errand through the product's turns: the line is in the reply and the history; Undo takes it back."""
    deliver_turn = jobs.JobXp.deliver_turn
    ready_to_deliver = jobs.JobXp.ready_to_deliver
    assert_untouched = jobs.JobXp.assert_untouched

    async def history(self):
        detail = await self.http.get(f"/api/game/campaigns/{self.campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        return detail.json()["history"]

    async def history_text(self):
        """The history the story shows: an undone entry is marked ``undone`` and is not part of it."""
        return json.dumps([row for row in await self.history() if row.get("undone") is not True], ensure_ascii=False)

    async def full_delivery(self):
        await self.ready_to_deliver()
        self.world["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        self.save()
        return (await self.deliver_turn()).json()

    async def test_the_line_is_in_the_reply_and_the_history_once(self):
        purse = self.purse()
        out = await self.full_delivery()
        self.assertEqual(out["narration"].count(FULL), 1, out["narration"])
        self.assertTrue(out["narration"].endswith(FULL), out["narration"])
        self.assertIsNone(out.get("level_up"))
        self.assertEqual(self.purse() - purse, jobs.WAGE)            # the wage stands; money never moves for XP
        self.assertEqual((await self.history_text()).count(FULL), 1)
        later = await self.say("etrafa bakıyorum")                   # forfeited once: no later turn repeats it
        self.assertNotIn("kaydedilemedi", later["narration"])
        self.assertEqual((await self.history_text()).count(FULL), 1)

    async def test_undo_takes_the_line_back_with_the_turn(self):
        purse = self.purse()
        await self.full_delivery()
        self.assertEqual((await self.history_text()).count(FULL), 1)
        await self.undo()
        self.assert_untouched(purse)
        self.assertNotIn(FULL, await self.history_text())
        [undone] = [row for row in await self.history() if FULL in json.dumps(row, ensure_ascii=False)]
        self.assertIs(undone.get("undone"), True)                  # the turn's own entry, marked undone with it

    async def test_an_unrelated_error_at_the_job_award_falls_back_the_whole_turn(self):
        purse = self.purse()
        await self.ready_to_deliver()
        self.save()
        with patch.object(xp, "award_finished_jobs", side_effect=ValueError("an unrelated bug")):
            response = await self.post_turn("Tuna, iade takımını getirdim",
                                            front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        self.assertNotEqual(response.status_code, 200, response.text)
        self.assert_untouched(purse)                               # no wage, no close, no forfeit mark
        self.assertNotIn("xp_forfeited", self.delivered_thread())
        self.assertNotIn("kaydedilemedi", await self.history_text())


class SpeciesActionLine(unittest.IsolatedAsyncioTestCase):
    """Review finding (DÜŞÜK): the species-actions panel command (D-003) shows its own forfeited award's line in its
    answer and its history entry, and the next play turn does not carry it."""
    # D-003's stored campaign and scripted model, without running D-003's own tests here.
    asyncSetUp = d003.OutOfTurnXpLine.asyncSetUp
    asyncTearDown = d003.OutOfTurnXpLine.asyncTearDown
    turn = d003.OutOfTurnXpLine.turn
    history = d003.OutOfTurnXpLine.history

    async def forfeited_by_the_panel(self):
        with fixed_town(self, 10531):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign = created.json()
        session_id = self.campaign["session_id"]
        session = self.manager.get(session_id).game_session
        _stage_radiant_bounty(session, target_hp=1)
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        xp_before = session.character.get("xp", 0)
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(session.character.get("xp", 0), xp_before)
        return session_id, session, response.json()

    async def test_the_panel_command_shows_the_forfeited_line(self):
        _session_id, session, answer = await self.forfeited_by_the_panel()
        message = answer["result"]["message"]
        self.assertTrue(message.endswith(" " + PANEL_LINES), message)
        self.assertNotIn("deneyim puanı", message)
        self.assertEqual(session._take_xp_unrecorded(), [])
        self.assertEqual(self.history()[-1]["narration"], message)

    async def test_the_next_turn_does_not_carry_the_panel_line(self):
        session_id, _session, _answer = await self.forfeited_by_the_panel()
        later = await self.turn(session_id)
        self.assertNotIn("kaydedilemedi", later["narration"])
        narrations = [entry.get("narration") or "" for entry in self.history()]
        self.assertEqual(sum(text.count(PANEL_LINES) for text in narrations), 1, narrations)


if __name__ == "__main__":
    unittest.main()
