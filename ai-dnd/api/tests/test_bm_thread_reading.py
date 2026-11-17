"""BM Task 4 (B1): a job decision needs the model's reading. A question that names another person is not job talk;
the owner's terms, the accept and the pay stay with Python, written only from a reading that says work.

Real app and engine through the journey harness (scenario 19: Halil offers an errand to Tuna, 12 bakir); only the model
is scripted. The scenario pins the town (seed 7)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import front_proposal
import game
import living_world
import talk_front
import town_knowledge
import world_threads
from api.tests import test_quest_delivery as delivery
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_gate as gate_tests
from api.tests.test_front_proposal import FrontClient
from api.tests.town_seed import fixed_town
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

    async def test_work_asked_about_another_person_is_not_this_persons_job_talk(self):
        """I1: `asks=work` plus `about_person_id` naming someone else, no job id: the owner's own job is not started."""
        self.reopen()
        self.assertIn(self.thread(), world_threads.jobs_of(self.world, self.person(OWNER)))
        out = await self.say("Selin'in işi ne, biliyor musun?", front=self.reading(asks="work", about_person_id="stranger"))
        self.assertNotIn("bakır", out["narration"])
        self.assertEqual(self.thread()["status"], "open")
        self.assertIsNone(getattr(self.session, "_thread_turn", None))

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
        """Flag on, the reading failed (no reading held): the word reader `turn_gate` runs and its answer drives the turn.
        'Selin nerede?' after an open offer is a short line: the old gate takes it for the owner's job talk."""
        line = "Selin nerede?"
        expected = world_threads.turn_gate(self.world, self.person(OWNER), line)
        self.assertIsNotNone(expected)
        answers = []
        real = world_threads.turn_gate

        def spy(*args):
            answers.append(real(*args))
            return answers[-1]

        with patch.object(talk_front, "current", return_value=None), patch.object(world_threads, "turn_gate", spy):
            await self.say(line)
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["thread_id"], expected["thread_id"])
        self.assertIsNone(answers[0]["decision"])
        # and the old word 'iş' (a work term) is read as work, too
        line = "Selin'in iş hakkında söylediği ne?"
        self.assertIsNotNone(world_threads.turn_gate(self.world, self.person(OWNER), line))

    async def test_b1_play_shape_names_the_recipient_and_asks_a_rumour(self):
        """The play's line: five words, the job's recipient named, a rumour asked of the owner. The old gate took it for job
        talk twice (the short-line rule and the work-term table that adds the owner's terms line); the reading says rumour."""
        self.reopen()
        self.person("stranger")["name"] = "Tuna"  # the job's recipient stands here, listed
        self.thread()["recipient_name"] = "Tuna"
        line = "Tuna'nın iş yerindeki gerginlik ne?"
        self.assertIsNotNone(world_threads.turn_gate(self.world, self.person(OWNER), line))
        self.assertTrue(town_knowledge.asks_about_work(line, self.thread()))
        purse, quests = self.purse(), len(self.world["quests"])
        out = await self.say(line, front=self.reading(asks="rumour", about_person_id="stranger"))
        self.assertNotIn("bakır", out["narration"])
        self.assertNotIn("Teslim edene", out["narration"])
        self.assertEqual((self.purse(), len(self.world["quests"]), self.thread()["status"]), (purse, quests, "open"))

    async def test_a_list_valued_job_id_is_none(self):
        self.reopen()
        out = await self.say("Bu iş neydi?", front=self.reading(asks="work", job_id=["x"], offer_id={"a": 1}))
        self.assertIn("On iki bakır", out["narration"])  # asks=work still opens the terms; no crash, no lost gate

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


class ReadingDecisions(unittest.IsolatedAsyncioTestCase):
    """The decisions the word reader used to make alone (`take_up`, `matter`, `lapsed`) still happen when the reading
    says the line speaks of that job: the reading chooses the thread, Python's validators decide."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status

    async def trouble(self):
        self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}))
        with fixed_town(self, 4401):
            await gate_tests.ThreadTable.open_job(self, kind="trouble")
        self.client = FrontClient("Sağ ol.")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "asks": "work", "about_person_id": "none"}
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.thread.update(owner_line="Hesap tutmuyor, bakan biri lazım.", fires_at=2 * 86400, expires_at=2 * 86400,
                           public_line="Burada hesap tutmuyormuş.",
                           terms={"pay": None, "work_days": None, "pay_basis": None, "pay_timing": None,
                                  "deadline_text": None})
        self.thread.pop("night_only", None)
        self.thread.update(target_place_id=None, recipient_name=None)
        world_threads.mark_heard(self.thread, 0)

    async def test_take_up_from_the_reading(self):
        await self.trouble()
        await self.line("derdini ben hallederim abi", mode="say", target=True)
        self.assertEqual(self.status(), "accepted")

    async def test_no_work_reading_takes_nothing_up(self):
        await self.trouble()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "asks": "rumour", "about_person_id": "none"}
        await self.line("derdini ben hallederim abi", mode="say", target=True)
        self.assertNotEqual(self.status(), "accepted")

    async def test_matter_from_the_reading(self):
        """A trouble that comes down to speaking with this person: the player brings it up, the trouble is over."""
        await self.trouble()
        world_threads.accept_hired(self.world, self.thread, 0)
        self.thread.update(status="accepted", target_place_id=self.place_id, owner_name="Kalila")
        self.assertIn(self.thread, world_threads.matters_with(self.world, self.npc))
        await self.line("Kalila gönderdi, derdi konuşmaya geldim", mode="say", target=True)
        self.assertEqual(self.status(), "done")

    async def test_lapsed_from_the_reading(self):
        """A yes to an offer the clock took back, read as the very yes the open offer would have heard."""
        await self.trouble()
        state = world_threads.view(self.world)
        thread = self.thread
        turn = self.world["flags"].get("turn_index", 0)
        thread.update(status="expired", offered_at=0, offered_turn=turn, offer_line_turn=turn, offer_line="Hesap tutmuyor, bakan biri lazım.",
                      closed_at=world_threads._now(self.world))
        thread.pop("accepted_at", None)
        state["threads"] = []
        state["history"] = [thread]
        self.world["npc_speech_log"] = {self.npc["id"]: [{"player": "selam", "npc": thread["offer_line"]}]}
        text = "tamam ben hallederim"
        self.assertTrue(world_threads.lapsed_yes(self.world, thread, text, self.npc))
        found = talk_front.work_reading(self.client.front, self.npc, self.world)
        gate = world_threads.reading_gate(self.world, self.npc, found["thread_id"], text, self.client.front)
        self.assertEqual(gate["decision"], "lapsed")


if __name__ == "__main__":
    unittest.main()
