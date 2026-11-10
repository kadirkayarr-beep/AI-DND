"""Dilim 3b Task 4: every arrival goes through arrival_narration, on every path, and stays whole under replay,
Undo and reload.

Paths (probe on seed 4401, front reading off and on, recorded in the task report):
- "demirhaneye gidiyorum" -> game._local_place_turn (action "travel"), front reading on or off;
- "<place>'ne yaklaşıyorum" then "içeri giriyorum" -> grounded_action._enter, PLACE_KINDS branch;
- "hana giriyorum" -> the scene planner's enter (grounded_action.enter_existing_place -> _enter, venue branch).
"""
import copy
import json
import os
import unittest
import uuid
from functools import wraps
from unittest.mock import patch

import arrival_narration
import campaign_time
import front_proposal
import game
import world_threads
from api.tests import test_campaign_api as fixtures
from api.tests.journeys.runner import ScriptedClient, call_kind
from api.tests.town_seed import fixed_town

START = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
         "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}


class ArrivalClient(ScriptedClient):
    """The journey harness's scripted model; the arrival kind answers the given text or raises the given error."""

    def __init__(self):
        super().__init__({})
        self.arrival = None

    def script_turn(self, *, arrival=None, spoken=None, front=None):
        self.arrival = arrival
        self.script = {key: value for key, value in (("spoken", spoken), ("front", front)) if value is not None}

    def chat(self, *args, **kwargs):
        if call_kind(kwargs.get("format")) != "arrival":
            return super().chat(*args, **kwargs)
        self.kinds.append("arrival")
        if isinstance(self.arrival, BaseException):
            raise self.arrival
        if self.arrival is None:
            raise RuntimeError("varış yazılmadı")
        packet = {"narration": self.arrival, "world_updates": {}, "lore_claims": []}
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class _ArrivalApi(unittest.IsolatedAsyncioTestCase):
    TOWN_SEED = None
    asyncSetUp_base = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    post_scene_turn = fixtures.CampaignApiTests.post_scene_turn

    async def asyncSetUp(self):
        await self.asyncSetUp_base()
        self.client = ArrivalClient()
        with fixed_town(self, self.TOWN_SEED):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": START})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_id = created.json()["campaign_id"]
        self.session_id = created.json()["session_id"]
        self.results = []

    def session(self):
        return self.manager.get(self.session_id).game_session

    def place_of(self, kind):
        world = self.session().world_state
        return next(pid for pid, rec in world["locations"].items()
                    if isinstance(rec, dict) and rec.get("place_kind") == kind
                    and rec.get("parent_location_id") == "fr:city:neverwinter")

    async def turn(self, line, *, arrival=None, spoken=None, front=None, spend_before_arrival=0, action_id=None):
        """One API turn; front given = the front reading is on and answers it. Results of run_player_turn are kept."""
        self.client.script_turn(arrival=arrival, spoken=spoken, front=front)
        session = self.session()
        real = session.run_player_turn
        if not getattr(real, "_kept", False):
            @wraps(real)
            def keep(*args, **kwargs):
                result = real(*args, **kwargs)
                self.results.append(result)
                return result
            keep._kept = True
            session.run_player_turn = keep
        real_narrate = arrival_narration.narrate

        def spend_first(*args, **kwargs):  # earlier calls of the same counted turn, through the real adapter
            for _ in range(spend_before_arrival):
                game.ollama.chat(model="qwen3:8b", messages=[{"role": "user", "content": "x"}],
                                 format=game._dm_response_schema_for_turn(narration_only=True))
            return real_narrate(*args, **kwargs)

        with (patch.dict(os.environ, {front_proposal.FLAG: "1" if front is not None else "0"}),
              patch.object(arrival_narration, "narrate", new=spend_first)):
            return await self.post_scene_turn(f"/api/game/sessions/{self.session_id}/turn", self.client,
                                              {"message": line, "action_id": action_id or str(uuid.uuid4())})

    def last_result(self):
        return self.results[-1]


class ArrivalWiring(_ArrivalApi):
    TOWN_SEED = 4401  # a smithy (location_005, with a trouble thread) is already in this town

    async def stand_at_front_of_a_local_place(self):
        forge = self.session().world_state["locations"][self.place_of("smithy")]
        reply = await self.turn(f"{forge['name']}ne yaklaşıyorum")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.session().world_state["location"], "fr:city:neverwinter")

    async def stand_at_the_inn_door(self):
        # the same set-up as test_campaign_api's inn: a tavern found by day, its door not locked
        reply = await self.turn("Yakınlarda bir taverna arıyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)

    async def give_the_town_a_job_at(self, kind):
        """The town's own trouble at that place comes to its moment on the clock (world_threads' own writer)."""
        world = self.session().world_state
        place = self.place_of(kind)
        thread = next(t for t in world[world_threads.KEY]["threads"]
                      if t["place_id"] == place and t["type"] == "trouble")
        campaign_time.advance(world, max(0, thread["fires_at"] - world_threads._now(world)), "wait", "test")
        row = next(r for r in world[world_threads.KEY]["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertFalse(row["known_to_player"])
        self._job_line = row["line"]

    def job_news_line(self):
        return self._job_line

    async def test_local_place_walk_is_told_by_the_model(self):
        reply = await self.turn("demirhaneye gidiyorum", arrival="Ocak harlı yanıyor.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertTrue(reply.json()["narration"].startswith("Ocak harlı yanıyor."), reply.json()["narration"])
        self.assertEqual(self.session().last_arrival_narration["source"], "model")
        result = self.last_result()
        self.assertEqual(result["action_result"]["action"], "travel")
        self.assertEqual(result["action_result"]["arrival_narration"], {"source": "model", "reason_code": None})
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(self.client.kinds, ["arrival"])

    async def test_grounded_entry_uses_the_same_function(self):
        await self.stand_at_front_of_a_local_place()
        reply = await self.turn("içeri giriyorum", arrival="Ocak harlı yanıyor.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertTrue(reply.json()["narration"].startswith("Ocak harlı yanıyor."), reply.json()["narration"])
        result = self.last_result()
        self.assertEqual(result["action_result"]["action"], "grounded_action")
        self.assertEqual(result["action_result"]["arrival_narration"], {"source": "model", "reason_code": None})
        self.assertEqual(result["model_calls"], 1)  # the arrival call is counted in what the turn spent
        self.assertEqual(result["action_result"]["grounding"]["source"], "deterministic")  # Ruling R7
        self.assertEqual(result["action_result"]["grounding"]["model_calls"], 0)

    async def test_inn_entry_is_told_by_the_model(self):
        await self.stand_at_the_inn_door()
        reply = await self.turn("hana giriyorum", arrival="İçerisi sıcak ve gürültülü.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("İçerisi sıcak ve gürültülü.", reply.json()["narration"])
        self.assertNotIn("Kapıdan içeri giriyorsun.", reply.json()["narration"])
        self.assertEqual(self.session().last_arrival_narration["source"], "model")
        self.assertEqual(self.last_result()["action_result"]["arrival_narration"],
                         {"source": "model", "reason_code": None})

    async def test_inn_walk_and_ask_counts_the_planner_call_in_the_turn(self):
        # the planner's entry runs after the front reading, in the same counted window: one call left, speech keeps it
        await self.stand_at_the_inn_door()
        self.client.kinds.clear()
        reply = await self.turn("hana girip bir bira istiyorum", arrival="İçerisi sıcak.", front={})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertNotIn("arrival", self.client.kinds)
        self.assertLessEqual(len(self.client.kinds), 2)
        self.assertEqual(self.session().last_arrival_narration["reason_code"], "speech_first")

    async def test_a_failing_arrival_call_keeps_the_turn(self):
        reply = await self.turn("demirhaneye gidiyorum", arrival=RuntimeError("down"))
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("karşına çıkıyor", reply.json()["narration"])
        self.assertEqual(self.session().last_arrival_narration["reason_code"], "model_error")
        self.assertEqual(self.session().world_state["location"], self.place_of("smithy"))

    async def test_walk_and_speak_line_gives_the_call_to_speech(self):
        # the front reading is on and names the smithy: it spends one call, so one is left and the speech keeps it
        reply = await self.turn("demirhaneye gidip bir nal istiyorum", arrival="Ocak.", spoken="Bekle biraz.",
                                front={"kind": "go_to", "place_id": self.place_of("smithy")})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertNotIn("arrival", self.client.kinds)
        self.assertLessEqual(len(self.client.kinds), 2)
        self.assertEqual(self.session().last_arrival_narration["reason_code"], "speech_first")

    async def test_two_calls_spent_before_arrival_means_no_call(self):
        reply = await self.turn("demirhaneye gidiyorum", arrival="Ocak.", spend_before_arrival=2)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.session().last_arrival_narration["reason_code"], "no_budget")
        self.assertNotIn("arrival", self.client.kinds)

    async def test_job_news_follows_the_model_text(self):
        await self.give_the_town_a_job_at("smithy")
        narration = (await self.turn("demirhaneye gidiyorum", arrival="Ocak harlı yanıyor.")).json()["narration"]
        self.assertTrue(narration.startswith("Ocak harlı yanıyor."), narration)
        self.assertIn(self.job_news_line(), narration)
        self.assertEqual(narration.count(self.job_news_line()), 1)


class ArrivalUndoReplay(_ArrivalApi):
    TOWN_SEED = 4411  # no smithy in this town: the walk makes one

    def snapshot(self):
        session = self.session()
        return copy.deepcopy((session.world_state, session.messages, session.recent_dm_narrations))

    async def undo(self):
        target = self._last_action_id
        reply = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                     json={"action_id": str(uuid.uuid4()), "target_action_id": target})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply

    async def turn(self, line, **kwargs):
        kwargs.setdefault("action_id", str(uuid.uuid4()))
        self._last_action_id = kwargs["action_id"]
        return await super().turn(line, **kwargs)

    async def reload(self):
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        fresh_id, *_ = fresh.resume_campaign(self.campaign_id)
        return fresh.get(fresh_id).game_session

    async def load_old_save(self):
        """A save as written before this task: the engine save has no arrival field anywhere; it is resumed."""
        saved = self.store.get_campaign(self.campaign_id).payload["engine_save"]
        self.assertNotIn("arrival_narration", json.dumps(saved, ensure_ascii=False))
        resumed = await self.http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.session_id = resumed.json()["session_id"]
        self.assertIsNone(self.session().last_arrival_narration)

    async def test_replayed_action_id_does_not_call_again(self):
        action_id = str(uuid.uuid4())
        first = await self.turn("demirhaneye gidiyorum", arrival="Ocak.", action_id=action_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn("arrival", self.client.kinds)
        calls = len(self.client.kinds)
        again = await self.turn("demirhaneye gidiyorum", arrival="Başka.", action_id=action_id)
        self.assertEqual(again.json()["narration"], first.json()["narration"])
        self.assertEqual(len(self.client.kinds), calls)

    async def test_undo_takes_the_arrival_back_whole(self):
        before = self.snapshot()  # world_state, messages, recent_dm_narrations
        reply = await self.turn("demirhaneye gidiyorum", arrival="Ocak.")
        self.assertTrue(reply.json()["narration"].startswith("Ocak."), reply.json()["narration"])
        self.assertNotEqual(self.snapshot(), before)
        await self.undo()
        self.assertEqual(self.snapshot(), before)

    async def test_reload_reads_the_same_arrival_text(self):
        # session.messages is not saved (a reload starts it from the system prompt); what a reload reads back is the
        # stored history row the player sees and the saved narration memory.
        narration = (await self.turn("demirhaneye gidiyorum", arrival="Ocak.")).json()["narration"]
        self.assertTrue(narration.startswith("Ocak."), narration)
        live_memory = copy.deepcopy(self.session().recent_dm_narrations)
        reloaded = await self.reload()
        self.assertEqual(self.store.get_campaign(self.campaign_id).history[-1]["narration"], narration)
        self.assertEqual(reloaded.recent_dm_narrations, live_memory)
        self.assertEqual(reloaded.world_state["location"], self.session().world_state["location"])

    async def test_an_old_save_loads_and_arrives(self):  # a c65ddb37-shaped save: no new field anywhere
        await self.load_old_save()
        reply = await self.turn("demirhaneye gidiyorum", arrival="Ocak.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.session().last_arrival_narration["source"], "model")


if __name__ == "__main__":
    unittest.main()
