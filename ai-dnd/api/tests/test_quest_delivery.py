"""Handing a job's parcel to its recipient pays once and closes the job; a wrong proposal delivers nothing and never
falls to the word reader; undo, reload, replay and a failed save return it whole (Dilim 2, Task 5)."""
from __future__ import annotations

import copy
import json
from contextlib import closing
from unittest.mock import call, patch
from uuid import uuid4

import front_proposal
import game
import world_happenings
import world_threads
from adventure import dialogue_jobs
from api.persistence.campaign_store import CampaignStore
from api.tests.journeys.runner import (SCENARIO_DIR, _NOT_STATE, JourneyCase, ScriptedModel, _front_setting,
                                       _inventory_counts, _Reader, apply_setup, read_observed)
from api.tests.journeys.schema import Step, load_scenario
from api.tests.auth_fixture import TEST_PLAYER
from api.session_manager import SessionManager

_OPEN = {"ACTIVE", "BLOCKED"}
# The turn route takes a UUID action id (the plan named them d2-deliver-1, d2-save-fail, d2-lost, d2-restart).
_D2_DELIVER_1 = "00000000-0000-4000-8000-00000000d251"
_D2_SAVE_FAIL = "00000000-0000-4000-8000-00000000d252"
_D2_LOST = "00000000-0000-4000-8000-00000000d253"
_D2_RESTART = "00000000-0000-4000-8000-00000000d254"


class QuestDelivery(JourneyCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = load_scenario(SCENARIO_DIR / "19_quest_item_no_duplicate.json").setup
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id
        self._threads_before = frozenset()

    # --- the scenario's world -------------------------------------------------------------------------------------
    @property
    def record(self):
        return self.manager.get(self.session_id)

    @property
    def session(self):
        return self.record.game_session

    @property
    def world(self):
        return self.session.world_state

    def save(self):
        self.manager.save_campaign(self.campaign_id)

    def purse(self):
        return self.world["currency"]["player"]

    def bag(self):
        return _inventory_counts(self.world["inventory"])

    def open_quests(self):
        return [q["quest_id"] for q in self.world.get("quests", []) if q.get("status") in _OPEN]

    def thread(self):
        return world_threads.by_id(self.world, self.thread_id)

    def second_thread(self):
        return world_threads.by_id(self.world, self.thread_id + ":second")

    def rows(self, kind):
        return [row for row in world_happenings.ledger(world_threads.view(self.world)) if row.get("kind") == kind]

    def paid_rows(self):
        events = (self.world.get("interaction_adventure_v1") or {}).get("events") or []
        return [e for e in events if e.get("kind") == "thread_paid"]

    def notes(self):
        return list(getattr(self.session, "_turn_notes", None) or [])

    def quest_status(self):
        return next(q["status"] for q in self.world["quests"] if q.get("quest_id") == self.quest_id)

    def follow_on_threads(self):
        live = [t["thread_id"] for t in (world_threads.view(self.world) or {}).get("threads") or []]
        return sorted(t for t in live if t not in self._threads_before)

    def history_length(self):
        return len(self.store.get_campaign(self.campaign_id).history)

    def delivery_state(self):
        thread = self.thread()
        return (self.purse(), self.bag(), (thread["status"], thread.get("paid_cp"), len(self.paid_rows())),
                self.quest_status(), len(self.rows("delivered")), frozenset(self.follow_on_threads()),
                self.history_length())

    def observed(self):
        found = read_observed(self, self.session_id)
        return {key: value for key, value in found.items() if key not in _NOT_STATE}

    def reloaded_observed(self):
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        reloaded_id, *_ = fresh.resume_campaign(self.campaign_id)
        found = read_observed(_Reader(fresh), reloaded_id)
        return {key: value for key, value in found.items() if key not in _NOT_STATE}

    # --- turns ----------------------------------------------------------------------------------------------------
    async def post_turn(self, line, front=None, action_id=None):
        step = Step(say=line, command=None, economic_action=None, combat_action=None,
                    script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                    independent=True)
        body = {"action_id": action_id or str(uuid4()), "message": line}
        self.last_turn_action_id = body["action_id"]
        with _front_setting(self.setup), ScriptedModel().bind(self, step):
            return await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)

    async def say(self, line, front=None, action_id=None):
        response = await self.post_turn(line, front=front, action_id=action_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def undo(self):
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, undo=True)
        failures = await self._undo(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])

    async def restart(self):
        """A new SessionManager and client over the same store (the journey `reload` step's own path)."""
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, reload=True)
        failures, _ = await self._reload(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])
        self.session_id = self.last_session_id

    # --- the job --------------------------------------------------------------------------------------------------
    async def accept(self):
        await self.say("olur, götürürüm")
        [thread] = [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "accepted"]
        self.thread_id = thread["thread_id"]
        self.quest_id = thread["quest_id"]
        self.parcel_id = "parcel:" + self.quest_id
        self.tuna = thread["recipient_npc_id"]
        self.assertEqual((self.purse(), self.bag()), (100, {"İade takımı": 1}))

    def person(self, person_id):
        return next(n for n in self.world["npcs"] if n.get("id") == person_id)

    def stand_with(self, person_id):
        if person_id == "stranger" and not any(n.get("id") == "stranger" for n in self.world["npcs"]):
            self.world["npcs"].append({"id": "stranger", "name": "Selin", "role": "Yolcu", "current_hp": 10,
                                       "location": self.world["location"]})
        self.world["location"] = self.person(person_id)["location"]
        self.save()

    async def at_recipient(self):
        place = self.thread()["target_place_id"]
        self.world["location"] = place
        self.assertEqual(self.person(self.tuna).get("location"), place)
        self._threads_before = frozenset(t["thread_id"] for t in world_threads.view(self.world)["threads"])
        self.save()

    def add_second_accepted_errand(self, item_noun, recipient):
        first = self.thread()
        second = copy.deepcopy(first)
        second.update(thread_id=first["thread_id"] + ":second", quest_id=first["quest_id"] + "2", item_noun=item_noun,
                      recipient_npc_id=recipient)
        world_threads.view(self.world)["threads"].append(second)
        quest = copy.deepcopy(next(q for q in self.world["quests"] if q.get("quest_id") == first["quest_id"]))
        quest["quest_id"] = second["quest_id"]
        self.world["quests"].append(quest)
        self.world["inventory"].append({"item_id": "parcel:" + second["quest_id"], "name": "Mühürlü mektup",
                                        "quantity": 1})
        self._threads_before = self._threads_before | {second["thread_id"]}
        self.save()

    # --- Step 1: which cause kept scenario 19 step 4 from delivering (defter: "teslim nedeni") ---------------------
    async def test_step1_walking_to_the_harbor_reaches_tuna(self):
        # not the arrival: the scenario's walk puts the player at the job's target place, and Tuna is there
        await self.accept()
        await self.say("iskeleye gidiyorum")
        place = self.thread()["target_place_id"]
        self.assertEqual((self.world["location"], self.person(self.tuna).get("location")), (place, place))

    async def test_step1_the_setup_hand_holds_only_what_the_bag_has(self):
        # the setup empties the bag; a hand still naming the starting sword made every transfer out of the bag refuse
        # (equipment_identity_unresolved), so even the old reader's "give" could not move the parcel
        self.assertEqual(self.world["equipment"], {"main_hand": None, "off_hand": None})

    async def test_step1_an_idless_hand_over_at_tunas_door(self):
        # the idless proposal went to the old word reader; now the one parcel due to Tuna is handed over
        await self.accept(); await self.at_recipient()
        with patch.object(game, "_thread_gate", wraps=game._thread_gate) as gate:
            await self.say("Tuna, iade takımını getirdim, buyur", front={"kind": "hand_over"})
        self.assertEqual(gate.call_count, 0)
        self.assertEqual((self.purse(), self.bag(), self.thread()["status"]), (112, {}, "done"))

    # --- Step 2 ---------------------------------------------------------------------------------------------------
    async def test_hand_over_to_the_recipient_pays_once_and_closes_the_job(self):
        await self.accept(); await self.at_recipient()
        await self.say("Tuna, iade takımını getirdim, buyur",
                       front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        self.assertEqual((self.purse(), self.bag(), self.open_quests()), (112, {}, []))
        self.assertEqual((self.thread()["status"], self.thread()["paid_cp"]), ("done", 12))

    async def test_hand_over_without_item_needs_exactly_one_parcel_due(self):
        await self.accept(); await self.at_recipient()
        self.add_second_accepted_errand(item_noun="mühürlü mektup", recipient=self.tuna)
        before = copy.deepcopy(self.world)
        await self.say("Tuna, getirdim, buyur", front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        self.assertEqual((self.purse(), sum(self.bag().values()), len(self.open_quests())), (100, 2, 2))
        self.assertEqual(self.world["inventory"], before["inventory"])
        self.assertIn((self.tuna, "olmadı: hangi eşyayı verdiğin belli değil"), self.notes())

    async def test_a_failed_hand_over_proposal_never_falls_to_the_word_reader(self):
        await self.accept(); await self.at_recipient()
        self.add_second_accepted_errand(item_noun="mühürlü mektup", recipient="potter")  # its parcel is not Tuna's
        other = "parcel:" + self.second_thread()["quest_id"]
        with patch.object(game, "_thread_gate", side_effect=AssertionError("word reader called")):
            await self.say("Tuna, şunu al", front={"kind": "hand_over", "person_id": self.tuna, "item_id": other})
        self.assertEqual((self.purse(), sum(self.bag().values()), len(self.open_quests())), (100, 2, 2))

    async def test_delivery_replay_pays_once_and_undo_restores_everything(self):
        await self.accept(); await self.at_recipient()
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        first = await self.say("Tuna, iade takımını getirdim", front=front, action_id=_D2_DELIVER_1)
        again = await self.say("Tuna, iade takımını getirdim", front=front, action_id=_D2_DELIVER_1)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(again, sort_keys=True))   # byte-identical replay
        self.assertEqual(self.purse(), 112)
        live_after = self.observed()
        await self.undo()
        self.assertEqual((self.purse(), self.bag(), self.open_quests()), (100, {"İade takımı": 1}, [self.quest_id]))
        self.assertEqual(self.thread()["status"], "accepted")
        self.assertEqual(self.rows("delivered"), [])                      # Görev 7 writes it; undo removes it
        self.assertEqual(self.follow_on_threads(), [])                    # threads opened by the delivery: none left
        self.assertEqual(self.reloaded_observed(), self.observed())       # new SessionManager over the same store
        self.assertNotEqual(live_after, self.observed())

    async def test_a_delivery_with_a_second_word_keeps_the_delivery_evidence(self):
        # rc6 real chain: the reading splits "Tuna, iade takımını getirdim, buyur" into the hand-over and also_says
        # "buyur"; the second part is its own talk call, and the turn's evidence must still carry the delivery
        await self.accept(); await self.at_recipient()
        import api.main as api_main
        seen = []
        real_stage = api_main._stage_engine_lore_state

        def stage(state, evidence, action_result, before_world, after_world):
            seen.append((copy.deepcopy(evidence), copy.deepcopy(action_result)))
            return real_stage(state, evidence, action_result, before_world, after_world)

        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none", "also_says": "buyur"}
        with patch.object(api_main, "_stage_engine_lore_state", side_effect=stage):
            response = await self.post_turn("Tuna, iade takımını getirdim, buyur", front=front)
        self.assertEqual(response.status_code, 200, response.text)
        [(evidence, action_result)] = seen
        self.assertTrue(action_result.get("quest_outcomes"))
        self.assertEqual(evidence["quest_outcomes"], action_result["quest_outcomes"])
        self.assertEqual((self.purse(), self.bag(), self.open_quests()), (112, {}, []))
        self.assertEqual((self.thread()["status"], self.thread()["paid_cp"], len(self.paid_rows())), ("done", 12, 1))
        live = self.observed()
        self.assertEqual(live["gunluk"]["sayac"], 0)
        self.assertEqual(self.reloaded_observed(), live)                    # the saved record says the same
        await self.undo()
        self.assertEqual((self.purse(), self.bag(), self.open_quests()), (100, {"İade takımı": 1}, [self.quest_id]))
        self.assertEqual((self.thread()["status"], len(self.paid_rows())), ("accepted", 0))
        self.assertEqual(self.reloaded_observed(), self.observed())

    async def test_handing_it_to_the_wrong_person_pays_nothing(self):
        await self.accept()
        for person in ("potter", "stranger"):                             # the giver; a person with no part in the job
            with self.subTest(person=person):
                self.stand_with(person)
                await self.say("al bunu", front={"kind": "hand_over", "person_id": person, "item_id": self.parcel_id})
                self.assertEqual((self.purse(), self.bag(), self.thread()["status"]), (100, {"İade takımı": 1}, "accepted"))

    async def test_an_invalid_id_or_person_is_unclear_not_the_old_path(self):
        # J-014 #2: a filled id or person that is not listed is unclear; neither the word reader nor the old pipeline runs
        await self.accept(); await self.at_recipient()
        listed = front_proposal.listing(self.session)
        for front in ({"kind": "hand_over", "person_id": self.tuna, "item_id": "item:not-in-the-bag"},
                      {"kind": "hand_over", "person_id": "nobody-listed", "item_id": self.parcel_id}):
            with self.subTest(front=front):
                self.assertEqual(front_proposal.validate({"front": front}, listed), {"kind": "unclear"})
                before = self.delivery_state()
                with patch.object(game, "_thread_gate", side_effect=AssertionError("word reader called")), \
                     patch.object(game, "_front_hand_over", side_effect=AssertionError("hand-over called")), \
                     patch.object(front_proposal, "note", wraps=front_proposal.note) as noted:
                    await self.say("Tuna, şunu al", front=front)
                after = self.delivery_state()
                self.assertEqual(after[:6], before[:6])                   # purse, bag, job, quest row, rows, follow-ons
                self.assertEqual(after[6], before[6] + 1)                 # the turn itself is one history row
                self.assertNotIn(call(self.session, "fallback:invalid", reached=True), noted.call_args_list)
        self.assertEqual(front_proposal.validate({"front": {"kind": "hand_over", "person_id": "none", "item_id": "none"}},
                                                 {**listed, "people": [], "speaking_with": None}), None)   # nobody to bind: today's None

    async def test_a_save_failure_during_delivery_changes_nothing_then_the_retry_pays_once(self):
        # J-014 #7, same injection as test_persistence_idempotency.py (trigger on campaign_turn_actions)
        await self.accept(); await self.at_recipient()
        before = self.delivery_state()
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        with closing(self.store._connect()) as db:
            db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON campaign_turn_actions
                          BEGIN SELECT RAISE(ABORT, 'injected late failure'); END""")
        failed = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_SAVE_FAIL)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(self.delivery_state(), before)                           # purse 100, parcel in bag, job accepted, no rows
        self.assertIsNone(self.manager.get_turn_action(self.record, _D2_SAVE_FAIL))
        with closing(self.store._connect()) as db:
            db.execute("DROP TRIGGER reject_receipt")
        done = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_SAVE_FAIL)
        self.assertEqual(done.status_code, 200, done.text)
        after = self.delivery_state()
        self.assertEqual(after[:4], (112, {}, ("done", 12, 1), "COMPLETED"))
        self.assertEqual(after[6], before[6] + 1)                                 # one turn in the campaign history

    async def test_a_lost_response_after_the_delivery_replays_without_paying_again(self):
        await self.accept(); await self.at_recipient()
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        committed = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_LOST)   # the reply is dropped
        state = self.delivery_state()
        replay = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_LOST)
        self.assertEqual(json.dumps(replay.json(), sort_keys=True), json.dumps(committed.json(), sort_keys=True))
        self.assertEqual(self.delivery_state(), state)
        self.assertEqual(state[:4], (112, {}, ("done", 12, 1), "COMPLETED"))

    async def test_after_a_restart_the_same_delivery_replays_and_pays_once(self):
        await self.accept(); await self.at_recipient()
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        first = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_RESTART)
        state = self.delivery_state()
        await self.restart()                                                     # a new SessionManager over the same store
        replay = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=_D2_RESTART)
        same = {**first.json(), "session_id": self.session_id}                   # the reopened session's own id
        self.assertEqual(json.dumps(replay.json(), sort_keys=True), json.dumps(same, sort_keys=True))
        self.assertEqual(self.delivery_state(), state)
        # Plan: undo here returns (100, {"İade takımı": 1}, ("accepted", 0, 0), "ACTIVE"). The product keeps no trusted
        # pre-turn state across a restart (test_lr00_p7_undo.test_no_undo_after_restart), so the undo is refused and
        # the one payment stands exactly as it was; undo before a restart is test_delivery_replay_pays_once_and_undo_...
        refused = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                       json={"action_id": str(uuid4()), "target_action_id": _D2_RESTART})
        self.assertEqual((refused.status_code, refused.json()["detail"]["code"]), (409, "undo_unavailable"))
        self.assertEqual(self.delivery_state(), state)
        self.assertEqual(state[:4], (112, {}, ("done", 12, 1), "COMPLETED"))
