"""A two-part request said to the person in front of you reaches them (Dilim 3, Task 15; Dilim 2 leftover 5, item 4).

"bir oda tutmak istiyorum, geceyi burada geçireyim" said while talking to Marek was recorded as a private plan
(`interaction_adventure.compound_plan`, `game._run_player_turn_internal`'s compound branch) and never reached him, so
no room card opened. Rule (the model proposes, Python checks): while talk mode is open with a living person here, the
turn's reading decides; when its intent is `talk` and it names a living person here (`talk_mode.people_here`) or
nobody, the line is said to that person and their answer's `asks_for` is read as for any line said to them. Any other
reading keeps the clauses the player's own plan, as before, and costs no call beyond that reading. With no open talk
the line takes today's path. The room card opens from the money owner as today; this task decides no money. No real
model is called: replies are scripted."""
from __future__ import annotations

import copy
import traceback
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import economic_actions
import interaction_adventure
from api import serializers
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, apply_setup
from api.tests.journeys.schema import Step, load_scenario

ROOM_LINE = "bir oda tutmak istiyorum, geceyi burada geçireyim"
KNOCK_LINE = "kapıyı çalıyorum, cevap gelmezse pencereden bakıyorum"
PLAN_LINE = "Vardiya değişince bekleyeyim, arkadan gizlice gireyim"


def _talk_to(npc_id, reference="Marek", quote=""):
    return {"intent": "talk", "action": "talk",
            "target": {"type": "npc", "reference": reference, "npc_id": npc_id, "evidence_quote": quote},
            "completion": "complete"}


class _Counted(ScriptedModel):
    """The scripted model, keeping the kinds of the calls the step made."""

    kinds: list[str] = []

    @contextmanager
    def bind(self, case, step):
        with super().bind(case, step) as client:
            client.kinds = self.kinds = []
            yield client


class SpokenPlan(JourneyCase):
    """Scenario 08's inn: Marek the barman serves rooms; the purse holds 100 copper; no front reading."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.scenario = load_scenario(SCENARIO_DIR / "08_talk_mode.json")
        campaign = await self._journey_campaign(self.scenario.setup)
        apply_setup(self, campaign, self.scenario.setup)
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None
        self.calls = []

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    def world(self):
        return self.session.world_state

    def card(self):
        return serializers.serialize_session_state(self.session).get("economic_offer")

    def purse(self):
        return self.world()["currency"]["player"]

    def plan(self):
        return (self.world().get(interaction_adventure.KEY) or {}).get("plan")

    def open_cards(self):
        return sum(1 for record in economic_actions.offer_records(self.world()).values()
                   if (offer := economic_actions.offer_from_record(record)) is not None and offer.status == "prepared")

    async def say(self, line, intent=None, speech=None):
        """One plain line (no `konus`), as scenario 08's step 2 sends it; `self.calls` keeps its model call kinds."""
        script = {}
        if intent is not None:
            script["intent"] = copy.deepcopy(intent)
        if speech is not None:
            script["speech"] = copy.deepcopy(speech)
        step = Step(say=line, command=None, economic_action=None, combat_action=None, script=script or None,
                    expect={}, known_broken=(), real_chain=False, independent=True)
        model = _Counted()
        failures = await self._play(self.session_id, step, model)
        self.assertEqual(failures, [])
        self.calls = model.kinds
        return {"narration": self.last_narration, "action_id": self.last_turn_action_id}

    async def talk_to_marek(self):
        await self.say("Marek'e selam veriyorum", intent=_talk_to("barman", quote="Marek"))
        self.assertEqual((self.world().get("flags") or {}).get("active_npc_id"), "barman")

    async def say_room_line(self):
        return await self.say(ROOM_LINE, intent=_talk_to("barman"), speech={"asks_for": "room"})

    async def undo(self, action_id):
        self.last_turn_action_id = action_id
        failures = await self._undo(self.session_id, Step(
            say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
            known_broken=(), real_chain=False, independent=True, undo=True), ScriptedModel())
        self.assertEqual(failures, [])

    # --- root check (Step 1, first): which branch took scenario 08's step 2 line ---

    async def test_root_the_line_no_longer_ends_in_the_private_plan_branch(self):
        # Traced before the fix (see the task ledger): the line ran `compound_plan` in `_run_player_turn_internal`'s
        # compound branch, which recorded a private plan (intent_source python_compound_plan) with the plan's own
        # line; no person heard it, so no stock "heard" line (`_HEARD_LINES`) and no card. Routed to the person with
        # the reading's `interaction` missing, `finish_conversation_rejection` gives the `_HEARD_LINES` answer ("Sen
        # bilirsin."): that is the branch the owner met in live play.
        await self.talk_to_marek()
        said, recorded = [], []
        real_unknown, real_resolve = interaction_adventure.immersive_unknown, interaction_adventure.resolve

        def traced_unknown(*args, **kwargs):
            line = real_unknown(*args, **kwargs)
            said.append([frame.name for frame in traceback.extract_stack()])
            return line

        def traced_resolve(session, text, raw, *args, **kwargs):
            recorded.append(raw.get("operation") if isinstance(raw, dict) else raw)
            return real_resolve(session, text, raw, *args, **kwargs)

        with patch.object(interaction_adventure, "immersive_unknown", traced_unknown), \
                patch.object(interaction_adventure, "resolve", traced_resolve):
            turn = await self.say_room_line()
        self.assertEqual((said, recorded), ([], []))                     # neither the stock line nor a plan
        self.assertNotIn("Sen bilirsin", turn["narration"])

    # --- tests (plan Task 15 Step 1) ---

    async def test_a_spoken_request_to_the_person_is_no_private_plan(self):
        await self.talk_to_marek()
        turn = await self.say(ROOM_LINE, intent=_talk_to("barman"), speech={"asks_for": "room"})
        self.assertEqual((self.card()["max_total_cp"], self.card()["counterparty_label"]), (50, "Marek"))
        self.assertEqual(self.purse(), 100)
        self.assertFalse((self.world().get("flags") or {}).get("inn_room"))
        self.assertNotIn("Sen bilirsin", turn["narration"])
        self.assertIsNone(self.plan())
        self.assertEqual(self.calls, ["intent", "speech"])               # the reading and the person's answer

    async def test_a_reading_naming_nobody_while_talking_goes_to_the_one_talked_to(self):
        await self.talk_to_marek()
        await self.say(ROOM_LINE, intent={**_talk_to(""), "target": {"type": "none", "reference": "", "npc_id": "",
                                                                    "evidence_quote": ""}},
                       speech={"asks_for": "room"})
        self.assertEqual((self.card()["max_total_cp"], self.card()["counterparty_label"]), (50, "Marek"))
        self.assertIsNone(self.plan())

    async def test_a_chain_of_acts_is_still_a_plan(self):
        # talking with Marek, a line whose reading is no talk stays the player's plan, with no call beyond the reading
        await self.talk_to_marek()
        await self.say(PLAN_LINE, intent={"intent": "explore"})
        self.assertIsNotNone(self.plan())
        self.assertEqual(len(self.plan()["steps"]), 2)
        self.assertIsNone(self.card())
        self.assertEqual(self.calls, ["intent"])
        self.assertIsNone(self.last_speech_input)                        # nothing was said to Marek

    async def test_the_knock_chain_keeps_its_owner(self):
        # Review Focus 11's line: in this inn the knock owner answers it before any plan logic, as before the fix,
        # talking or not; it is never said to Marek
        for talking in (False, True):
            with self.subTest(talking=talking):
                await self.asyncTearDown(); await self.asyncSetUp()
                if talking:
                    await self.talk_to_marek()
                turn = await self.say(KNOCK_LINE, intent={"intent": "explore"})
                self.assertEqual(turn["narration"], "Vurabileceğin bir kapı yakınında değil.")
                self.assertIsNone(self.last_speech_input)
                self.assertIsNone(self.card())

    async def test_a_chain_of_acts_with_no_one_talked_to_is_a_plan_as_before(self):
        await self.say(PLAN_LINE, intent={"intent": "explore"})
        self.assertIsNotNone(self.plan())
        self.assertNotIn("intent", self.calls)                           # no reading was asked for, as before

    async def test_a_talk_reading_at_someone_absent_keeps_todays_path(self):
        await self.say(ROOM_LINE, intent=_talk_to("nobody", reference="Kimse"))
        self.assertIsNone(self.card())                                   # no card for a person who is not here
        await self.talk_to_marek()
        await self.say(ROOM_LINE, intent=_talk_to("nobody", reference="Kimse"), speech={"asks_for": "room"})
        self.assertIsNone(self.card())                                   # nobody here by that id: the plan, no card
        self.assertIsNotNone(self.plan())

    async def test_a_talk_reading_at_someone_dead_keeps_the_plan(self):
        await self.talk_to_marek()
        self.world()["npcs"].append({"id": "corpse", "name": "Orsik", "role": "Yolcu", "location": self.world()["location"],
                                     "current_hp": 0, "combat_status": "dead"})
        await self.say(ROOM_LINE, intent=_talk_to("corpse", reference="Orsik"), speech={"asks_for": "room"})
        self.assertIsNone(self.card())
        self.assertIsNotNone(self.plan())

    async def test_the_card_opens_once(self):
        await self.talk_to_marek()
        await self.say_room_line()
        first = self.card()
        await self.say_room_line()
        self.assertEqual(self.card(), first)
        self.assertEqual((self.open_cards(), self.purse()), (1, 100))

    async def test_undo_of_the_card_turn_closes_the_card(self):
        await self.talk_to_marek()
        turn = await self.say_room_line()
        self.assertIsNotNone(self.card())
        await self.undo(turn["action_id"])
        self.assertIsNone(self.card())
        self.assertEqual(self.purse(), 100)
        self.assertFalse((self.world().get("flags") or {}).get("inn_room"))


if __name__ == "__main__":
    unittest.main()
