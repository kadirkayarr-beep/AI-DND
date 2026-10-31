"""Hired work: a shift moves the real clock, a finished day pays through the real wallet."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import campaign_time
import equipment_economy
import game
import living_world
import world_threads
from api.tests import test_experimental_npc_dialogue as speech

HOUR = 3600
DAY = 86400


class HiringTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def job(self, *, status="accepted", pay=20, days=2, basis="daily", night=False):
        self.city, self.session_id, self.session, self.turn_url, self.owner = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        living_world.ensure_scene_state(self.world)
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"], active_npc_until_turn=99)
        self.world.pop(world_threads.KEY, None)
        world_threads.ensure(self.world)
        state = world_threads.view(self.world)
        self.owner["place_role_of"] = self.city
        self.thread = state["threads"][0]
        self.thread.update(type="hiring", template_id="hand_wanted", status="offered", place_id=self.city,
                           target_place_id=None, recipient_name=None, owner_name="Kalila", expires_at=30 * DAY,
                           offered_at=0, offered_turn=0, offer_line="Günlüğü yirmi bakır, iki gün. Yapar mısın?",
                           owner_line="Günlüğü yirmi bakır, iki gün.",
                           terms={"pay": pay, "work_days": days, "pay_basis": basis, "pay_timing": "end_of_day",
                                  "deadline_text": "iki gün içinde"})
        if night:
            self.thread["night_only"] = True
        state["threads"] = [self.thread]
        self.world["npc_speech_log"] = {self.owner["id"]: [{"player": "iş var mı", "npc": self.thread["offer_line"]}]}
        self.tid = self.thread["thread_id"]
        self.world["campaign_time"]["start_second"] = 9 * HOUR
        if status == "accepted":
            world_threads.accept_hired(self.world, self.thread)

    async def line(self, message, reply=None, *, mode=None):
        if reply is not None:
            self.client.narration = reply
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
            body["target_id"] = self.owner["id"]
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.world = self.session.world_state
        return response.json()

    def t(self):
        return world_threads.by_id(self.world, self.tid)

    def wallet(self):
        return self.world.get("currency", {}).get("player", 0)

    def now(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def test_a_shift_moves_the_clock_and_pays_the_day(self):
        await self.job()
        start, money = self.now(), self.wallet()
        reply = await self.line("başlayalım")
        self.assertEqual(self.now() - start, 8 * HOUR)
        self.assertEqual(self.wallet() - money, 20)
        self.assertEqual(self.t()["days_worked"], 1)
        self.assertIn("20 bakır", reply["narration"])
        self.assertNotIn("shift_until", self.t())

    async def test_a_name_not_yet_learned_stays_off_the_screen(self):
        await self.job()
        self.owner["name_known_to_player"] = False
        self.owner["name"] = "Eldon"
        self.owner["role"] = "Kâhya"
        for line in world_threads.job_lines("shift"):
            self.assertIn("{owner}", line)
        reply = await self.line("başlayalım")
        self.assertNotIn("Eldon", reply["narration"])
        self.assertNotIn("Kalila", reply["narration"])

    async def test_say_mode_works_the_same(self):
        await self.job()
        money = self.wallet()
        await self.line("işe başlıyorum", mode="say")
        self.assertEqual(self.wallet() - money, 20)

    async def test_nobody_s_purse_needs_to_hold_the_wage(self):
        await self.job()
        self.world["currency"] = {"player": self.wallet()}
        await self.line("başlayalım")
        equipment_economy.validate_world(self.world)
        self.assertEqual(sorted(self.world["currency"]), ["player"])

    async def test_a_second_shift_on_the_same_day_pays_nothing(self):
        await self.job(days=3)
        self.world["campaign_time"]["start_second"] = HOUR
        await self.line("başlayalım")
        money, worked = self.wallet(), self.t()["days_worked"]
        await self.line("başlayalım")
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.t()["days_worked"], worked)

    async def test_a_long_shift_is_still_one_day(self):
        await self.job(days=3)
        money = self.wallet()
        await self.line("16 saat çalışıyorum")
        self.assertEqual(self.t()["days_worked"], 1)
        self.assertEqual(self.wallet() - money, 20)

    async def test_the_last_day_closes_the_job_with_a_warm_owner(self):
        await self.job(days=1)
        await self.line("başlayalım")
        self.assertEqual(self.t()["status"], "done")
        self.assertEqual(self.world["relationships"][self.owner["id"]]["score"], 1)

    async def test_a_last_shift_running_past_the_limit_is_done_not_failed(self):
        await self.job(days=1)
        self.t()["work_until"] = self.now() + HOUR
        await self.line("başlayalım")
        self.assertEqual(self.t()["status"], "done")

    async def test_a_total_splits_by_day_and_the_last_takes_the_rest(self):
        await self.job(pay=62, days=3, basis="total")
        paid = []
        for _ in range(3):
            money = self.wallet()
            await self.line("başlayalım")
            paid.append(self.wallet() - money)
            if self.t()["status"] == "accepted":
                self.world["campaign_time"]["elapsed_seconds"] += DAY - 8 * HOUR
        self.assertEqual(paid, [20, 20, 22])
        self.assertEqual(self.t()["status"], "done")
        self.assertEqual(self.t()["paid_cp"], 62)

    async def test_saying_yes_and_start_in_one_breath_is_one_turn(self):
        await self.job(status="offered")
        money = self.wallet()
        await self.line("başlayalım")
        self.assertEqual(self.t()["status"], "accepted")
        self.assertEqual(self.wallet() - money, 20)

    async def test_a_yes_alone_does_not_start_the_shift(self):
        await self.job(status="offered")
        start = self.now()
        await self.line("olur", "Yarın gel.")
        self.assertEqual(self.t()["status"], "accepted")
        self.assertEqual(self.now(), start)

    async def test_night_work_does_not_start_by_day(self):
        await self.job(night=True)
        start = self.now()
        await self.line("başlayalım", "Akşam gel.")
        self.assertEqual(self.now(), start)
        self.assertIn("Akşam olunca", str(self.client.message_batches))

    async def test_night_work_starts_at_night(self):
        await self.job(night=True)
        self.world["campaign_time"]["start_second"] = 21 * HOUR
        money = self.wallet()
        await self.line("başlayalım")
        self.assertEqual(self.wallet() - money, 20)

    async def test_an_interrupted_shift_pays_nothing_for_hours_not_worked(self):
        await self.job()
        money = self.wallet()
        original = game.advance_campaign_time

        def cut(seconds, reason, source=None, observation=None):
            return original(2 * HOUR, reason, source, observation)

        with patch.object(game, "advance_campaign_time", side_effect=cut):
            await self.line("başlayalım")
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.t()["days_worked"], 0)
        self.assertEqual(self.t()["shift_seconds"], 2 * HOUR)
        self.assertNotIn("shift_until", self.t())

    async def test_no_time_passing_earns_nothing(self):
        await self.job()
        money = self.wallet()
        with patch.object(game, "advance_campaign_time",
                          return_value={"elapsed_seconds": 0, "interrupted": True}):
            await self.line("başlayalım")
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.t()["days_worked"], 0)

    async def test_a_shift_is_not_started_in_a_fight_or_on_the_road(self):
        await self.job()
        start = self.now()
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            self.world["journey"] = {"status": "TRAVELLING"}
            self.assertIsNone(game._thread_gate("başlayalım", None, "do"))
            self.world.pop("journey")
            self.world["combat"]["active"] = True
            self.assertIsNone(game._thread_gate("başlayalım", None, "do"))
            self.world["combat"]["active"] = False
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(self.now(), start)

    async def test_money_owed_is_untouched_by_a_day_that_was_not_worked(self):
        await self.job()
        money = self.wallet()
        await self.line("bir gün bekliyorum")
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.t()["days_worked"], 0)

    async def test_walking_out_ends_it_and_cools_the_owner(self):
        await self.job()
        await self.line("bırakıyorum", "Peki.")
        self.assertEqual(self.t()["status"], "abandoned")
        self.assertEqual(self.world["relationships"][self.owner["id"]]["score"], -1)

    async def test_a_job_never_turned_up_for_fails_and_pays_nothing(self):
        await self.job()
        money = self.wallet()
        await self.line("beş gün bekliyorum")
        self.assertEqual(self.t()["status"], "failed")
        self.assertEqual(self.wallet(), money)


class Wages(unittest.TestCase):
    def test_daily_pay_is_the_spoken_figure(self):
        thread = {"terms": {"pay": 15, "work_days": 3, "pay_basis": "daily"}, "days_worked": 2}
        self.assertEqual(world_threads._day_wage(thread), 15)

    def test_a_total_never_pays_more_than_its_figure(self):
        for pay, days in ((60, 3), (61, 3), (20, 7), (5, 2)):
            total = sum(world_threads._day_wage({"terms": {"pay": pay, "work_days": days, "pay_basis": "total"},
                                                 "days_worked": day}) for day in range(1, days + 1))
            self.assertEqual(total, pay)

    def test_the_clock_day_comes_from_the_campaign_clock(self):
        world = {}
        campaign_time.initialize(world)
        self.assertEqual(campaign_time.public_time(world)["day_index"], 0)


if __name__ == "__main__":
    unittest.main()
