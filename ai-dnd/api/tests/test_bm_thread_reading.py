"""BM Task 4 (B1): a job decision needs the model's reading. A question that names another person is not job talk;
the owner's terms, the accept and the pay stay with Python, written only from a reading that says work.

Real app and engine through the journey harness (scenario 19: Halil offers an errand to Tuna, 12 bakir); only the model
is scripted. The scenario pins the town (seed 7)."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

import front_proposal
import game
import living_world
import world_threads
from api.tests import test_quest_delivery as delivery
from api.tests.journeys.runner import SCENARIO_DIR, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import Step, load_scenario

OWNER = "potter"


class ThreadReading(delivery.JourneyCase):
    """The owner (Halil) has one offered errand; a listed stranger (Selin) stands beside the player."""

    record = delivery.QuestDelivery.record
    session = delivery.QuestDelivery.session
    world = delivery.QuestDelivery.world
    save = delivery.QuestDelivery.save
    purse = delivery.QuestDelivery.purse
    bag = delivery.QuestDelivery.bag
    thread = delivery.QuestDelivery.thread
    person = delivery.QuestDelivery.person
    stand_with = delivery.QuestDelivery.stand_with
    history_length = delivery.QuestDelivery.history_length
    notes = delivery.QuestDelivery.notes
    undo = delivery.QuestDelivery.undo
    open_quests = delivery.QuestDelivery.open_quests
    observed = delivery.QuestDelivery.observed

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = load_scenario(SCENARIO_DIR / "19_quest_item_no_duplicate.json").setup
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id
        self._threads_before = frozenset()
        self.stand_with("stranger")
        [thread] = [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "offered"]
        self.thread_id = thread["thread_id"]

    def reading(self, **extra):
        return {"kind": "speak_to", "person_id": OWNER, "asks": "none", "about_person_id": "none",
                "job_id": "none", **extra}

    async def post_turn(self, line, front=None, action_id=None):
        """As the UI sends a line said to the owner: say mode, the owner chosen."""
        step = Step(say=line, command=None, economic_action=None, combat_action=None,
                    script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                    independent=True)
        body = {"action_id": action_id or str(uuid4()), "message": line, "interaction_mode": "say", "target_id": OWNER}
        self.last_turn_action_id = body["action_id"]
        with _front_setting(self.setup), ScriptedModel().bind(self, step):
            return await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)

    async def say(self, line, front=None, action_id=None):
        response = await self.post_turn(line, front=front, action_id=action_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # --- B1 -------------------------------------------------------------------------------------------------------
    async def test_question_naming_recipient_is_not_job_talk(self):
        line = "Selin nerede?"  # an offer is open and the line is short: the word reader takes it for the owner's job talk
        self.assertIsNotNone(world_threads.turn_gate(self.world, self.person(OWNER), line))
        before = (self.purse(), self.thread()["status"], len(self.world["quests"]))
        with patch.object(world_threads, "turn_gate", wraps=world_threads.turn_gate) as words:
            out = await self.say(line, front=self.reading(asks="person", about_person_id="stranger"))
        self.assertEqual(words.call_count, 0)  # the reading is there: the word checks do not run
        self.assertNotIn("Teslim edene", out["narration"])
        self.assertNotIn("bakır", out["narration"])
        self.assertEqual((self.purse(), self.thread()["status"], len(self.world["quests"])), before)
        self.assertIsNone(getattr(self.session, "_thread_turn", None))

    def reopen(self):
        """The job as the owner has not put it yet (open, not offered): this is when the terms line is added."""
        thread = self.thread()
        thread["status"] = "open"
        seed = living_world.ensure_scene_state(self.world)["campaign_seed"]  # a stranger's welcome follows the id: pin it
        thread["thread_id"] = self.thread_id = next(
            f"thread_{n:03d}" for n in range(500, 1000)
            if world_threads._rank(seed, f"thread_{n:03d}", "wary") % 100 >= world_threads.WARY_PERCENT)
        world_threads.view(self.world)["threads"] = [thread]
        for key in ("offered_at", "offered_turn", "offer_line", "offer_line_turn", "offered_terms_shown"):
            thread.pop(key, None)
        self.world["npc_speech_log"] = {}
        self.assertEqual(world_threads.owner_mood(self.world, thread, self.person(OWNER)), "yes")

    async def test_no_work_reading_adds_no_terms_line(self):
        """B1's second half: a word table adds the terms line to a reply; a reading that is not work stops it."""
        self.reopen()
        out = await self.say("Bana iş ver, Selin nerede?", front=self.reading(asks="person", about_person_id="stranger"))
        self.assertNotIn("bakır", out["narration"])
        self.assertEqual(self.thread()["status"], "open")

    async def test_reading_job_id_still_opens_terms(self):
        self.reopen()
        out = await self.say("Bu iş neydi?", front=self.reading(asks="work", job_id=self.thread_id))
        self.assertIn("On iki bakır", out["narration"])
        self.assertEqual(self.thread()["status"], "offered")

    async def test_accept_and_question_once(self):
        quests = len(self.world["quests"])
        out = await self.say("Tamam yaparım, Selin nerede?",
                             front=self.reading(kind="offer_answer", answer="accept", offer_id=self.thread_id,
                                                asks="person", about_person_id="stranger"))
        self.assertEqual(self.thread()["status"], "accepted")
        self.assertEqual(len(self.world["quests"]), quests + 1)
        self.assertLessEqual(out["narration"].count("On iki bakır"), 1)  # the accept is written once, no terms line again

    async def test_accept_then_undo_returns_to_offered(self):
        quests, before = len(self.world["quests"]), self.observed()
        await self.say("Tamam yaparım, Selin nerede?",
                       front=self.reading(kind="offer_answer", answer="accept", offer_id=self.thread_id,
                                          asks="person", about_person_id="stranger"))
        self.assertEqual(self.thread()["status"], "accepted")
        await self.undo()
        self.assertEqual(self.thread()["status"], "offered")
        self.assertEqual(len(self.world["quests"]), quests)
        self.assertEqual(self.observed(), before)

    async def test_no_reading_keeps_the_old_words(self):
        """The reading call failed: the word reader runs as before. The line says 'iş' (a work term), so it opens the job
        talk exactly as `turn_gate` does; B1 reproduced, the word is the work term."""
        line = "Selin'in iş hakkında söylediği ne?"
        gate = world_threads.turn_gate(self.world, self.person(OWNER), line)
        self.assertIsNotNone(gate)
        with patch.object(game, "_thread_gate", wraps=game._thread_gate) as spy:
            with patch.object(front_proposal, "enabled", return_value=False):
                await self.say(line)
        self.assertEqual(spy.call_count, 1)

    # --- money stays with Python ----------------------------------------------------------------------------------
    def hire(self):
        """The same owner, now with a hired hand's job in hand: a day's wage is due on asking."""
        thread = self.thread()
        thread.update(type="hiring", template_id="hand_wanted", target_place_id=None, recipient_name=None,
                      terms={"pay": 20, "work_days": 2, "pay_basis": "daily", "pay_timing": "end_of_day",
                             "deadline_text": "iki gün içinde"})
        self.assertTrue(world_threads.accept_hired(self.world, thread))
        thread["accepted_turn"] = -10
        self.save()

    async def test_pay_still_python(self):
        self.hire()
        purse = self.purse()
        out = await self.say("sen söyledin yirmi bakır diye, paramı ver",
                             front=self.reading(asks="work", job_id=self.thread_id))
        self.assertEqual(self.purse() - purse, 20)  # the stored day wage, paid once, written by Python
        self.assertEqual(self.thread()["paid_cp"], 20)
        self.assertEqual(out["narration"].count("20 bakır"), 1)

    async def test_pay_asked_with_no_work_reading_pays_nothing(self):
        self.hire()
        purse = self.purse()
        await self.say("sen söyledin yirmi bakır diye, paramı ver", front=self.reading(asks="none"))
        self.assertEqual(self.purse(), purse)


if __name__ == "__main__":
    unittest.main()
