"""4B Task 3: a town job the player finished pays a fixed table-rule XP once (errand 25, hiring 50, trouble 50).

The job's own money path does not change (the errand's wage by its journal row, the hired day's wage by the entitlement
ledger, a trouble pays nothing). The experience is written at the job's close as ``xp_due`` and paid at the end of the
same turn under one ``job:<thread_id>`` receipt, through the session's XP boundary. A due grant the receipt list or the
XP cap refuses is forfeited (4C.6, B1): the turn stands with its wage, parcel and close, the thread is marked
``xp_forfeited`` and no later turn owes it (before 4C.6 the whole turn was refused, on every later turn too).
Every test holds the MONEY invariant: the purse moves by exactly the job's own wage, or not at all.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import game
import world_happenings
import world_threads
import xp
from adventure import dialogue_jobs
from api.tests import test_thread_hiring as hiring
from api.tests.journeys.runner import apply_setup
from api.tests.test_trails import TrailCase

DAY = hiring.DAY
from api.tests.town_seed import fixed_town

WAGE = 12  # the 19d job: "İade takımını iskeledeki Tuna'ya götür. On iki bakır."


def _filler_ids(count, *, include=()):
    return [*include, *(f"quest:filler_{number}" for number in range(count - len(include)))]


class _JobCase(TrailCase):
    """The 19d errand on a real seeded town (campaign seed 4821 and up)."""

    async def fresh_campaign(self):
        # the 19d setup on this module's own fixed towns: 4821 for the first campaign of a test, one more for each after
        self.campaigns_made = getattr(self, "campaigns_made", 0) + 1
        setup = {**self.setup, "campaign_seed": 4821 + (self.campaigns_made - 1)}
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id

    def purse(self):
        return self.world["currency"]["player"]

    def xp(self):
        return self.session.character.get("xp", 0)

    def receipts(self):
        return [r for r in self.world.get("xp_awarded_event_ids") or [] if r.startswith("job:")]


class JobXpRules(_JobCase):
    """Engine reads of the rule."""

    def test_job_xp_is_the_table_rule(self):
        self.assertEqual(xp.JOB_XP_BY_TYPE, {"errand": 25, "hiring": 50, "trouble": 50})
        self.assertIsNotNone(xp._AWARD_ID.fullmatch("job:thread_001"))
        self.assertIsNotNone(xp._AWARD_ID.fullmatch("quest:q1"))      # old receipts stay valid
        self.assertIsNotNone(xp._AWARD_ID.fullmatch("combat:foe:npc_1"))

    async def test_xp_due_must_be_a_positive_int_on_a_done_job(self):
        purse = self.purse()
        await self.accept()
        thread = self.delivered_thread()
        world_threads.validate(self.state())
        for bad in (0, -25, True, False, "25", 25.0, None):
            with self.subTest(bad=bad):
                done = copy.deepcopy(self.state())
                record = world_threads.by_id({world_threads.KEY: done}, thread["thread_id"])
                record["status"] = "done"
                record["xp_due"] = bad
                with self.assertRaises(ValueError):
                    world_threads.validate(done)
        on_open_job = copy.deepcopy(self.state())
        world_threads.by_id({world_threads.KEY: on_open_job}, thread["thread_id"])["xp_due"] = 25  # still accepted
        with self.assertRaises(ValueError):
            world_threads.validate(on_open_job)
        good = copy.deepcopy(self.state())
        record = world_threads.by_id({world_threads.KEY: good}, thread["thread_id"])
        record.update(status="done", xp_due=25)
        world_threads.validate(good)
        self.assertEqual(self.purse(), purse)

    async def test_job_filled_by_another_pays_nothing(self):
        """Only a job the player took on and finished is owed anything: no other close writes ``xp_due``."""
        purse = self.purse()
        await self.accept()
        for status in ("filled_by_other", "expired", "abandoned", "failed", "fired"):
            with self.subTest(status=status), self.engine():
                thread = copy.deepcopy(self.delivered_thread())
                thread["status"] = status
                world_threads._close_effects(self.world, thread["thread_id"], thread, status)
                self.assertNotIn("xp_due", thread)
        never_taken = copy.deepcopy(self.delivered_thread())
        never_taken.pop("accepted_at")
        with self.engine():
            world_threads._close_effects(self.world, never_taken["thread_id"], never_taken, "done")
        self.assertNotIn("xp_due", never_taken)
        # a real close by the clock: the recipient is gone, the job expires on the next turn, nothing is paid
        self.npc(self.tuna)["combat_status"] = "dead"
        self.save()
        await self.say("biraz bekliyorum")
        closed = self.delivered_thread()
        self.assertEqual(closed["status"], "expired")
        self.assertNotIn("xp_due", closed)
        self.assertEqual((self.xp(), self.receipts(), self.purse()), (0, [], purse))

    async def test_already_paid_is_a_no_op_and_a_refused_new_grant_raises(self):
        purse = self.purse()
        await self.accept()
        thread = self.delivered_thread()
        record = copy.deepcopy(thread)
        record.update(status="done", xp_due=25)
        self.state()["threads"].remove(thread)
        self.state()["history"].append(record)
        character = self.session.character
        # a full receipt list that already holds this job: nothing new is due, no error
        self.world["xp_awarded_event_ids"] = _filler_ids(xp.MAX_AWARD_IDS, include=[f"job:{record['thread_id']}"])
        self.assertEqual(xp.job_grants_due(self.world), [])
        self.assertIsNone(xp.award_finished_jobs(self.world, character))
        # a full receipt list without it: the new grant is refused loudly, nothing written
        self.world["xp_awarded_event_ids"] = _filler_ids(xp.MAX_AWARD_IDS)
        before = (copy.deepcopy(self.world["xp_awarded_event_ids"]), copy.deepcopy(character))
        with self.assertRaises(xp.JobXpRefused):
            xp.award_finished_jobs(self.world, character)
        self.assertEqual((self.world["xp_awarded_event_ids"], character), before)
        # the XP cap refuses it the same way
        self.world["xp_awarded_event_ids"] = []
        with patch.object(xp, "MAX_STORED_XP", 10), self.assertRaises(xp.JobXpRefused):
            xp.award_finished_jobs(self.world, character)
        self.assertEqual((self.world["xp_awarded_event_ids"], character.get("xp", 0)), ([], 0))
        # and with room it pays once, then is a no-op
        summary = xp.award_finished_jobs(self.world, character)
        self.assertEqual((summary["xp_gained"], character["xp"]), (25, 25))
        self.assertIsNone(xp.award_finished_jobs(self.world, character))
        self.assertEqual((character["xp"], self.receipts(), record["xp_due"]), (25, [f"job:{record['thread_id']}"], 25))
        self.assertEqual(self.purse(), purse)

    async def test_an_unpaid_finished_job_is_not_trimmed_away(self):
        """Ten newer known closings would push it out of the history; until its receipt exists it stays."""
        purse = self.purse()
        await self.accept()
        state = self.state()
        thread = self.delivered_thread()
        state["threads"].remove(thread)
        record = {**copy.deepcopy(thread), "status": "done", "xp_due": 25, "closed_at": 1, "outcome_known_turn": 1}
        newer = []
        for number in range(10):
            row = {**copy.deepcopy(record), "thread_id": f"thread_9{number:02d}", "closed_at": 2 + number}
            row.pop("xp_due")
            newer.append(row)
        ids = lambda: [t["thread_id"] for t in state["history"]]  # noqa: E731
        state["history"] = [copy.deepcopy(record), *copy.deepcopy(newer)]
        world_threads._trim_history(state)                          # without the world (the old rule): it is lost
        self.assertNotIn(record["thread_id"], ids())
        state["history"] = [copy.deepcopy(record), *copy.deepcopy(newer)]
        world_threads._trim_history(state, self.world)              # unpaid: kept
        self.assertIn(record["thread_id"], ids())
        world_threads.validate(state)
        self.assertEqual(xp.job_grants_due(self.world), [(f"job:{record['thread_id']}", 25)])
        xp.award_finished_jobs(self.world, self.session.character)
        world_threads._trim_history(state, self.world)              # paid: an old closing like any other
        self.assertNotIn(record["thread_id"], ids())
        self.assertEqual((self.xp(), self.receipts(), self.purse()), (25, [f"job:{record['thread_id']}"], purse))

    def test_an_odd_thread_id_gets_a_bounded_receipt(self):
        self.assertEqual(xp._job_award_id("thread_001"), "job:thread_001")
        for odd in ("x" * 200, "has space"):
            event_id = xp._job_award_id(odd)
            self.assertTrue(event_id.startswith("job:sha256:"))
            self.assertIsNotNone(xp._AWARD_ID.fullmatch(event_id))


class JobXp(_JobCase):
    """The errand through the product's turns: delivery, its messenger, Undo, replay, reload and refusals."""

    async def deliver_turn(self, *, action_id=None, expect=200):
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        response = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=action_id)
        self.assertEqual(response.status_code, expect, response.text)
        return response

    async def ready_to_deliver(self):
        await self.accept()
        self.at_recipient()
        self.assertTrue(dialogue_jobs.holds_parcel(self.world, self.delivered_thread()))

    def assert_untouched(self, purse):
        thread = self.delivered_thread()
        self.assertEqual(thread["status"], "accepted")
        self.assertNotIn("xp_due", thread)
        self.assertTrue(dialogue_jobs.holds_parcel(self.world, thread))
        self.assertEqual((self.xp(), self.receipts(), self.purse()), (0, [], purse))

    def assert_paid_once(self, purse):
        thread = self.delivered_thread()
        self.assertEqual((thread["status"], thread["xp_due"]), ("done", 25))
        self.assertEqual(self.xp(), 25)
        self.assertEqual(self.receipts(), [f"job:{self.thread_id}"])
        self.assertEqual(self.purse() - purse, WAGE)

    async def test_a_delivered_parcel_pays_25_xp_and_its_wage_once(self):
        purse = self.purse()
        await self.ready_to_deliver()
        self.assertEqual((self.xp(), self.purse()), (0, purse))
        out = (await self.deliver_turn()).json()
        self.assert_paid_once(purse)                               # paid in the delivering turn itself
        self.assertIn(f"job:{self.thread_id}", self.session.world_state["xp_awarded_event_ids"])
        self.assertEqual((out.get("level_up") or out.get("action_result", {}).get("level_up") or {}).get("xp_gained", 25), 25)
        await self.say("etrafa bakıyorum")                          # a later turn pays nothing more
        self.assert_paid_once(purse)

    async def test_a_delivered_courier_parcel_sends_a_thank_you_messenger_without_money(self):
        purse = self.purse()
        await self.ready_to_deliver()
        await self.deliver_turn()
        self.assert_paid_once(purse)
        [link] = [row for row in world_happenings.links(self.state()) if row.get("about_thread_id") == self.thread_id]
        self.assertEqual((link["kind"], link["tone"], link["owner_npc_id"]), (world_happenings.CALLER, "delivered", "potter"))
        hours = -(-(link["fires_at"] - world_threads._now(self.world)) // world_threads.HOUR)
        out = await self.say(f"{hours} saat bekliyorum")
        self.assertNotIn("fires_at", link := next(r for r in world_happenings.links(self.state())
                                                  if r["thread_id"] == link["thread_id"]))
        self.assertIn("Halil", out["narration"])                   # the owner's thanks, by the owner's known name
        self.assert_paid_once(purse)                               # the messenger brings no money and no XP

    async def test_a_sealed_letter_keeps_its_seal_rules(self):
        """Only the courier rule is new: an opened seal still sends no thanks, and an unopened letter still does."""
        await self.accept()
        thread = copy.deepcopy(self.delivered_thread())
        for sealed, broken, expected in ((True, True, None), (True, False, "delivered"), (False, False, "delivered")):
            with self.subTest(sealed=sealed, broken=broken), self.engine():
                state = self.state()
                state[world_happenings.LINKS] = []
                line = "Mühürlü mektubu götür, mührü sakın bozma." if sealed else thread["owner_line"]
                record = {**thread, "thread_id": "thread_960", "owner_line": line, "seal_broken": broken}
                self.assertEqual(dialogue_jobs.sealed(record), sealed)
                world_happenings._letter_closed(self.world, record, "done")
                tones = [row["tone"] for row in world_happenings.links(state)]
                self.assertEqual(tones, [expected] if expected else [])

    async def test_job_chain_deliver_save_load_undo_replay(self):
        purse = self.purse()
        await self.ready_to_deliver()
        action_id = str(uuid4())
        await self.deliver_turn(action_id=action_id)
        self.assert_paid_once(purse)
        await self.deliver_turn(action_id=action_id)                # the same action again is the receipt's replay
        self.assert_paid_once(purse)
        await self.undo()                                          # Undo takes back the wage, the close and the XP together
        self.assert_untouched(purse)
        self.at_recipient()
        await self.deliver_turn()                                  # delivered again: one wage, one XP
        self.assert_paid_once(purse)
        await self.restart()                                       # reload reads the same
        self.assert_paid_once(purse)
        await self.say("etrafa bakıyorum")
        self.assert_paid_once(purse)

    async def test_a_failed_save_puts_back_the_wage_the_close_and_the_xp(self):
        purse = self.purse()
        await self.ready_to_deliver()
        action_id = str(uuid4())
        with closing(self.store._connect()) as db:
            db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON campaign_turn_actions
                          BEGIN SELECT RAISE(ABORT, 'injected late failure'); END""")
        await self.deliver_turn(action_id=action_id, expect=503)
        self.assert_untouched(purse)
        with closing(self.store._connect()) as db:
            db.execute("DROP TRIGGER reject_receipt")
        await self.deliver_turn(action_id=action_id)
        self.assert_paid_once(purse)

    def assert_paid_without_xp(self, purse, receipts):
        thread = self.delivered_thread()
        self.assertEqual((thread["status"], thread["xp_due"], thread["xp_forfeited"]), ("done", 25, True))
        self.assertEqual((self.xp(), self.receipts()), (0, []))
        self.assertEqual(self.world.get("xp_awarded_event_ids", []), receipts)
        self.assertEqual(self.purse() - purse, WAGE)

    # YENİDEN YAZIM (4C.6, B1) [GEVŞETME OLABİLİR]: was "refuses the whole delivery" (500, nothing changed). The refusal
    # locked every later turn; now the delivery stands (one wage, done), the XP alone is forfeited and marked.
    async def test_a_full_receipt_list_forfeits_only_the_xp_of_the_delivery(self):
        purse = self.purse()
        await self.ready_to_deliver()
        self.world["xp_awarded_event_ids"] = _filler_ids(xp.MAX_AWARD_IDS)
        receipts = list(self.world["xp_awarded_event_ids"])
        self.save()
        await self.deliver_turn()
        self.assert_paid_without_xp(purse, receipts)
        self.assertEqual(len(self.world["xp_awarded_event_ids"]), xp.MAX_AWARD_IDS)

    # YENİDEN YAZIM (4C.6, B1) [GEVŞETME OLABİLİR]: was "the XP cap refuses the whole delivery" (500, nothing changed).
    async def test_the_xp_cap_forfeits_only_the_xp_of_the_delivery(self):
        purse = self.purse()
        await self.ready_to_deliver()
        with patch.object(xp, "MAX_STORED_XP", 10):
            await self.deliver_turn()
        self.assert_paid_without_xp(purse, [])

    async def test_old_save_done_job_pays_nothing(self):
        """A save from before 4B holds a finished job with no ``xp_due``: loading it and playing on pays nothing."""
        purse = self.purse()
        await self.ready_to_deliver()
        with patch.object(world_threads, "_close_effects", wraps=world_threads._close_effects) as close:
            await self.deliver_turn()
        self.assertTrue(close.called)
        self.assert_paid_once(purse)
        old = self.delivered_thread()
        old.pop("xp_due")
        self.world["xp_awarded_event_ids"] = []
        self.session.character["xp"] = 0
        self.save()
        await self.restart()
        await self.say("etrafa bakıyorum")
        self.assertEqual((self.xp(), self.receipts(), self.purse() - purse), (0, [], WAGE))
        self.assertNotIn("xp_due", self.delivered_thread())


class _FixedHiring(unittest.IsolatedAsyncioTestCase):
    """test_thread_hiring's table (its methods borrowed, not its tests) on this module's fixed town 4825."""
    asyncSetUp = hiring.HiringTable.asyncSetUp
    asyncTearDown = hiring.HiringTable.asyncTearDown
    campaign_with_npc = hiring.HiringTable.campaign_with_npc
    line = hiring.HiringTable.line
    t = hiring.HiringTable.t
    wallet = hiring.HiringTable.wallet

    async def job(self, **kwargs):
        with fixed_town(self, 4825):
            await hiring.HiringTable.job(self, **kwargs)

    def xp(self):
        return self.session.character.get("xp", 0)

    def receipts(self):
        return [r for r in self.world.get("xp_awarded_event_ids") or [] if r.startswith("job:")]


class HiringXp(_FixedHiring):
    async def test_a_finished_hiring_job_pays_50_on_its_last_day_only(self):
        await self.job(days=2, pay=20)
        purse = self.wallet()
        await self.line("başlayalım")
        self.assertEqual((self.t()["status"], self.t()["days_worked"]), ("accepted", 1))
        self.assertNotIn("xp_due", self.t())
        self.assertEqual((self.xp(), self.receipts(), self.wallet() - purse), (0, [], 20))
        self.world["campaign_time"]["elapsed_seconds"] += DAY - 8 * 3600
        await self.line("başlayalım")
        self.assertEqual((self.t()["status"], self.t()["xp_due"]), ("done", 50))
        self.assertEqual((self.xp(), self.receipts(), self.wallet() - purse), (50, [f"job:{self.tid}"], 40))
        await self.line("başlayalım")                              # a done job: no shift, no wage, no XP again
        self.assertEqual((self.xp(), self.receipts(), self.wallet() - purse), (50, [f"job:{self.tid}"], 40))


class TroubleXp(_FixedHiring):
    async def test_a_settled_trouble_pays_50(self):
        await self.job(status="offered", days=1, pay=0)
        self.thread.update(type="trouble", template_id=None, target_place_id=self.city, recipient_name="Kalila",
                           owner_line="Kalila'nın komşusuyla arası bozuk, biri konuşup çözmeli.",
                           public_line="Kalila'nın komşusuyla arası bozuk.")
        self.thread.pop("fires_at", None)
        self.thread["terms"].update(pay=None, pay_basis=None, pay_timing=None)
        self.assertTrue(world_threads.accept_hired(self.world, self.thread))
        purse = self.wallet()
        await self.line("Kalila'nın meselesi için geldim, konuşalım")
        self.assertEqual((self.t()["status"], self.t()["xp_due"]), ("done", 50))
        self.assertEqual((self.xp(), self.receipts(), self.wallet()), (50, [f"job:{self.tid}"], purse))


class CorruptReceiptListInASave(unittest.TestCase):
    """Task 3 review F1: a receipt list that is not a list of strings is refused at load, never repaired to [].

    A repair to [] would pay every finished job still in history (its ``xp_due`` stays) a second time."""

    def setUp(self):
        self.session = game.create_session(seed=4832)
        self.session.world_state["xp_awarded_event_ids"] = ["job:thread_001"]
        self.payload = self.session.serialize_game_state()

    def load(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.session.load_game(path)

    def test_a_non_list_or_non_string_receipt_list_is_refused(self):
        for bad in ("corrupt", None, {"job:thread_001": True}, 7, ["job:thread_001", 3], [None]):
            payload = copy.deepcopy(self.payload)
            payload["world_state"]["xp_awarded_event_ids"] = bad
            before = copy.deepcopy((self.session.character, self.session.world_state))
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.load(payload)
                self.assertEqual((self.session.character, self.session.world_state), before)

    def test_a_valid_list_and_a_missing_one_still_load(self):
        self.load(copy.deepcopy(self.payload))
        self.assertEqual(self.session.world_state["xp_awarded_event_ids"], ["job:thread_001"])
        legacy = copy.deepcopy(self.payload)
        legacy["world_state"].pop("xp_awarded_event_ids")
        self.load(legacy)
        self.assertNotIn("job:thread_001", self.session.world_state.get("xp_awarded_event_ids", []))
