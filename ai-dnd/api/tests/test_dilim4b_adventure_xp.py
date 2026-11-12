"""Dilim 4B Task 4: an adventure quest's reward-plan XP goes through the session boundary (since 4C.6 the forfeiting
one, `_forfeit_unrecordable_xp`, after the branch's gold, item and standing).

Route tests play real HTTP turns on a fixed town (4831) with a finished DELIVERY quest planted the way the engine
leaves one (COMPLETED, outcome success, not yet paid); `adventure.play.settle_session` pays it at the turn's end.
Engine tests cover the rollback, the replay and the lore (J-099 finding 4). Every test pins purse, XP and receipts."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import adventure.play as play
import adventure.rewards as rewards
import adventure.templates as templates
import equipment_economy
import game
import xp
from api.persistence.campaign_validation import restore_campaign_session
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_hiring as hiring
from api.tests.test_phase7_package import bound_state
from api.tests.town_seed import fixed_town

QUEST_ID = "adv.delivery"
MARKER = "quest:adv.delivery:success"
POOL = f"adventure-pool:{QUEST_ID}"


def plant(session, place, source, target, *, faction=None):
    """A DELIVERY quest the player has finished (every required step done), its reward not yet applied."""
    quest = templates.instantiate(
        "DELIVERY", quest_id=QUEST_ID, turn=1, opportunity_key="opportunity:delivery",
        creation_evidence="event:delivery",
        bindings=templates.prepared_bindings(source_npc_id=source, target_npc_id=target, location_ids=[place]),
        rumor="Bir paket taşınacak.")
    for item in quest["objectives"]:
        if not item["optional"]:
            item.update(graph_state="COMPLETE", status="completed", visibility="known", progress=item["required_count"])
    quest.update(status="COMPLETED", outcome="success", accepted_turn=1)
    if faction is not None:
        quest["reward_plan"]["success"]["faction"] = faction
    session.world_state["quests"].append(quest)
    return quest


def to_level_four(session):
    """Earned level 4 at 6490 XP through the real XP owner (the 10 XP short of 6500 is what the quest crosses)."""
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 6490, "quest:setup-four")
    session._xp_level_up = None
    assert (session.character["level"], session.character["xp"]) == (4, 6490), session.character


def refused_admission(*_args, **_kwargs):
    raise ValueError("injected: save admission refused")


refused_admission._session_bound = True


class _Money:
    def purse(self):
        return self.world.get("currency", {}).get("player", 0)

    def xp(self):
        return self.session.character.get("xp", 0)

    def receipts(self):
        return list(self.world.get("xp_awarded_event_ids") or [])

    def quest(self):
        return next(q for q in self.world["quests"] if q.get("quest_id") == QUEST_ID)

    def state(self):
        return (self.purse(), self.xp(), self.receipts(), self.session.character.get("level"),
                self.quest().get("reward_application_id"), POOL in self.world.get("currency", {}))

    def assert_paid_once(self, before):
        purse, gained, receipts, *_ = before
        self.assertEqual(self.purse(), purse + 25)
        self.assertEqual(self.xp(), gained + 40)
        self.assertEqual(self.receipts(), receipts + [MARKER])
        self.assertEqual(self.quest()["reward_application_id"], MARKER)
        self.assertNotIn(POOL, self.world.get("currency", {}))


class AdventureXp(_Money, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = hiring.HiringTable.asyncSetUp
    asyncTearDown = hiring.HiringTable.asyncTearDown
    campaign_with_npc = hiring.HiringTable.campaign_with_npc
    line = hiring.HiringTable.line

    async def start(self):
        with fixed_town(self, 4831):
            self.city, self.session_id, self.session, self.turn_url, self.owner = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state

    async def turn(self, message="etrafa bakıyorum", expect=200):
        import uuid
        response = await self.http.post(self.turn_url, json={"message": message, "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, expect, response.text)
        self.world = self.session.world_state
        return response.json()

    def stored_session(self):
        fresh = game.create_session(seed=4831)
        restore_campaign_session(fresh, self.store.get_campaign(self.session.world_state["campaign_id"]).payload)
        return fresh

    async def test_adventure_success_announces_its_xp(self):
        await self.start()
        plant(self.session, self.city, self.owner["id"], "npc_private_sera")
        before = self.state()
        reply = await self.turn()
        self.assertEqual(reply["level_up"]["xp_gained"], 40)
        self.assertEqual((reply["level_up"]["previous_level"], reply["level_up"]["new_level"]), (1, 1))
        self.assert_paid_once(before)
        again = await self.turn()                                   # paid once: the next turn announces nothing
        self.assertIsNone(again["level_up"])
        self.assert_paid_once(before)
        stored = self.stored_session()                              # the accepted save holds the same
        self.assertEqual((stored.character["xp"], stored.world_state["xp_awarded_event_ids"],
                          stored.world_state["currency"]["player"]), (self.xp(), self.receipts(), self.purse()))

    async def test_adventure_xp_crossing_five_is_admitted_and_announced(self):
        await self.start()
        to_level_four(self.session)
        plant(self.session, self.city, self.owner["id"], "npc_private_sera")
        before = self.state()
        reply = await self.turn()
        self.assertEqual((reply["level_up"]["previous_level"], reply["level_up"]["new_level"],
                          reply["level_up"]["xp_gained"]), (4, 5, 40))
        self.assert_paid_once(before)
        self.assertEqual((self.session.character["level"], self.session._persisted_engine_format), (5, 6))
        stored = self.stored_session()                              # the save at level 5 was admitted and reloads
        self.assertEqual((stored.character["level"], stored.character["xp"], stored._persisted_engine_format),
                         (5, 6530, 6))
        self.assertEqual(stored.world_state["xp_awarded_event_ids"], self.receipts())

    async def test_reward_plan_failure_restores_gold_and_xp(self):
        await self.start()
        plant(self.session, self.city, self.owner["id"], "npc_private_sera")
        before = self.state()
        with patch.object(equipment_economy, "pay", side_effect=RuntimeError("injected pay failure")):
            await self.turn(expect=500)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.session._xp_level_up)
        reply = await self.turn()                                   # once the pay works, it pays once
        self.assertEqual(reply["level_up"]["xp_gained"], 40)
        self.assert_paid_once(before)

    async def test_replayed_plan_pays_nothing_again(self):
        await self.start()
        plant(self.session, self.city, self.owner["id"], "npc_private_sera")
        before = self.state()
        await self.turn()
        self.assert_paid_once(before)
        quest = copy.deepcopy(self.quest())
        again = rewards.apply_plan(self.session.character, self.world, quest)
        # YENİDEN YAZIM (4C.6 fix 1): the plan hands XP over as ``xp_due``; a replay owes none (was the renamed key)
        self.assertEqual((again["replayed"], again["marker"], again["xp_due"]), (True, MARKER, 0))
        reply = await self.turn()
        self.assertIsNone(reply["level_up"])
        self.assert_paid_once(before)


class AdventureXpEngine(_Money, unittest.TestCase):
    """The settle path: the plan's own rollback puts back gold, item, standing and the marker together; the branch XP is
    paid last through the forfeiting boundary, so a refused XP never takes the gold or the standing back (4C.6, B1)."""

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

    def plant(self, **kwargs):
        return plant(self.session, "tavern", "npc.source", "npc.target", **kwargs)

    # YENİDEN YAZIM (4C.6, B1): apply_plan pays gold, item and standing under the marker and hands the XP to the
    # session's boundary (``xp_due``), which pays it last; it no longer writes XP or a receipt itself.
    def test_apply_plan_returns_its_xp_due(self):
        quest = self.plant()
        before = (self.purse(), self.xp(), self.receipts())
        paid = rewards.apply_plan(self.session.character, self.world, quest)
        self.assertEqual((paid["xp_due"], paid["marker"], paid["replayed"]), (40, MARKER, False))
        self.assertEqual(set(paid), {"replayed", "marker", "lore_state", "xp_due"})
        self.assertEqual((self.purse(), self.xp(), self.receipts()), (before[0] + 25, before[1], before[2]))
        self.assertEqual(quest["reward_application_id"], MARKER)

    def test_a_gold_only_plan_has_no_xp_due(self):
        quest = self.plant()
        quest["reward_plan"]["success"]["xp"] = 0
        before = (self.purse(), self.xp(), self.receipts())
        paid = rewards.apply_plan(self.session.character, self.world, quest)
        self.assertEqual(paid["xp_due"], 0)
        self.assertEqual((self.purse(), self.xp(), self.receipts()), (before[0] + 25, before[1], before[2]))
        play.settle_session(self.session)
        self.assertIsNone(self.session._xp_level_up)

    def test_settle_session_pays_through_the_boundary(self):
        self.plant()
        before = self.state()
        play.settle_session(self.session)
        self.assert_paid_once(before)
        self.assertEqual(self.session._xp_level_up["xp_gained"], 40)
        play.settle_session(self.session)                           # replay: nothing more
        self.assert_paid_once(before)

    def test_a_failed_pay_rolls_back_gold_xp_receipts_and_quest(self):
        self.plant()
        before = self.state()
        lore = self.session.campaign_lore_state
        with patch.object(equipment_economy, "pay", side_effect=RuntimeError("injected pay failure")):
            with self.assertRaises(RuntimeError):
                play.settle_session(self.session)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.session._xp_level_up)
        self.assertIs(self.session.campaign_lore_state, lore)

    # YENİDEN YAZIM (4C.6, B1) [GEVŞETME OLABİLİR]: was "a refused 4→5 admission rolls gold/XP back and keeps the old
    # lore; a later settle pays all" (J-099 finding 4). The refusal repeated on every turn (B1); now gold, standing and
    # marker stand, only the XP is forfeited (no receipt, level 4, format unchanged), a later settle pays nothing more.
    def test_faction_reward_with_a_refused_level_five_admission_forfeits_only_the_xp(self):
        to_level_four(self.session)
        self.plant(faction={"id": "faction:watch", "standing": 1})
        purse, gained, receipts, *_ = self.state()
        self.assertEqual(self.session.campaign_lore_state.faction_standings, ())
        with patch.object(game, "_validate_save_payload", refused_admission):
            play.settle_session(self.session)
        settled = (purse + 25, gained, receipts, 4, MARKER, False)
        self.assertEqual(self.state(), settled)
        self.assertEqual(self.session._persisted_engine_format, game.SAVE_FORMAT_VERSION)
        self.assertIsNone(self.session._xp_level_up)
        self.assertEqual(self.session.campaign_lore_state.faction_standings[0].standing, 1)
        play.settle_session(self.session)                           # settled: nothing more, no refusal
        self.assertEqual(self.state(), settled)
        self.assertEqual(len(self.session.campaign_lore_state.faction_standings), 1)

    def test_faction_reward_without_a_campaign_bond_pays_nothing(self):
        self.session.campaign_lore_state = None
        self.plant(faction={"id": "faction:watch", "standing": 1})
        before = self.state()
        with self.assertRaises(ValueError):
            play.settle_session(self.session)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.session._xp_level_up)


if __name__ == "__main__":
    unittest.main()

