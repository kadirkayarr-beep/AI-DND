"""Focused Campaign Time V1 regressions; no real model or real campaign data."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import game
import campaign_time as clock
import scheduled_events as events
import timed_gameplay
from api.campaign_journal import empty_campaign_journal, update_campaign_journal
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.serializers import serialize_session_state, serialize_skill_check_result
from api.session_manager import SessionManager


def scene():
    session = game.create_session(seed=11)
    session.commit_location_change("tavern")
    session.world_state["locations"]["tavern"]["travel_routes"] = {"forest": [600, 600]}
    return session


def turn(session, message):
    return session.run_player_turn(message, action_id=str(uuid4()))


class ClockTests(unittest.TestCase):
    def test_first_scene_anchor_and_canonical_start(self):
        session = game.create_session()
        self.assertIsNone(session.ensure_campaign_clock())
        session.world_state["canonical_start_time"] = {
            "year": 1501, "month": "Kythorn", "day": 12, "hour": 18, "minute": 42,
        }
        session.commit_location_change("tavern")
        self.assertEqual(clock.public_time(session.world_state)["detail"], "12 Kythorn 1501 DR — 18:42:00")
        anchor = copy.deepcopy(session.world_state["campaign_time"])
        session.commit_location_change("forest")
        self.assertEqual(session.world_state["campaign_time"], anchor)
        other = scene()
        self.assertEqual(clock.public_time(other.world_state)["detail"], "1 Mirtul 1501 DR — 09:00:00")
        self.assertEqual(clock.public_time(other.world_state)["day_index"], 0)

    def test_calendar_rollovers_and_no_wall_clock(self):
        session = scene()
        session.world_state["campaign_time"]["start_date"] = {"year": 1500, "month": "Flamerule", "day": 30}
        session.world_state["campaign_time"]["start_second"] = 23 * 3600 + 59 * 60
        session.advance_campaign_time(60, "explicit_wait")
        self.assertEqual(clock.public_time(session.world_state)["month"], "Midsummer")
        session.advance_campaign_time(clock.DAY, "explicit_wait")
        self.assertEqual(clock.public_time(session.world_state)["month"], "Shieldmeet")
        session.advance_campaign_time(clock.DAY, "explicit_wait")
        self.assertEqual(clock.public_time(session.world_state)["month"], "Eleasis")

    def test_wait_task_budget_and_sleep_rest(self):
        session = scene()
        self.assertEqual(turn(session, "3 saat bekliyorum")["action_result"]["time_result"]["elapsed_seconds"], 10800)
        self.assertEqual(turn(session, "Bir saat araştırıyorum.")["action_result"]["time_result"]["elapsed_seconds"], 360)
        first = turn(session, "2 dakika araştırıyorum.")
        self.assertEqual(first["action_result"]["status"], "in_progress")
        self.assertEqual(session.world_state["active_task"]["spent_seconds"], 120)
        last = turn(session, "1 saat araştırıyorum.")
        self.assertEqual(last["action_result"]["time_result"]["elapsed_seconds"], 240)
        self.assertIsNone(session.world_state["active_task"])
        sleep = turn(session, "Sabaha kadar uyuyorum.")
        self.assertEqual(sleep["action_result"]["action"], "rest")
        self.assertEqual(clock.public_time(session.world_state)["hour"], 7)
        self.assertEqual(session.character["current_hp"], session.character["max_hp"])

    def test_task_check_uses_existing_core_and_public_result(self):
        session = scene()
        session.world_state["locations"]["tavern"]["search_dc"] = 15
        action = turn(session, "1 saat araştırıyorum.")["action_result"]
        self.assertEqual(action["action"], "skill_check")
        projected = serialize_skill_check_result(action, session)
        self.assertIsNotNone(projected)
        self.assertEqual(action["time_result"]["elapsed_seconds"], 360)

    def test_save_resume_isolation_and_corrupt_time_rejection(self):
        first, other = scene(), scene()
        turn(first, "3 saat bekliyorum")
        events.register_event(first.world_state, event_id="future", window_start=20000, window_end=21000, location_id="tavern")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            first.save_game(path)
            restarted = game.create_session(seed=100)
            restarted.load_game(path)
            self.assertEqual(restarted.world_state["campaign_time"], first.world_state["campaign_time"])
            self.assertEqual(restarted.world_state["scheduled_events"], first.world_state["scheduled_events"])
            self.assertEqual(other.world_state["campaign_time"]["elapsed_seconds"], 0)
            payload = json.loads(path.read_text())
            payload["world_state"]["campaign_time"]["elapsed_seconds"] = -1
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                restarted.load_game(path)

    def test_window_long_action_missed_aftermath_and_idempotent_effect(self):
        session = scene()
        event = events.register_event(
            session.world_state, event_id="meeting", window_start=3600, window_end=5400,
            location_id="tavern", behavior="INTERRUPTIVE",
            summary="Toplantı başladı.", aftermath="Toplantıdan kalan kâğıtlar masada.",
            effects=[{"kind": "flag", "key": "scheduled:meeting", "value": True}],
        )
        self.assertEqual(event["status"], "PENDING")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)
        result = turn(session, "5 saat bekliyorum")
        self.assertEqual(result["action_result"]["time_result"]["elapsed_seconds"], 18000)
        self.assertEqual(event["status"], "OCCURRED")
        self.assertEqual(event["encounter_status"], "MISSED")
        self.assertFalse(event["player_observed"])
        self.assertEqual(events.public_events(session.world_state), [])
        canonical = copy.deepcopy(event["canonical_result"])
        session.advance_campaign_time(60, "explicit_wait")
        self.assertEqual(event["canonical_result"], canonical)
        now = session.world_state["campaign_time"]["elapsed_seconds"]
        learned = events.process_events(session.world_state, now, now, observation={"kind": "look", "location_id": "tavern"})
        self.assertEqual(learned[0]["summary"], "Toplantıdan kalan kâğıtlar masada.")

    def test_encounter_inside_window_and_hidden_projections(self):
        session = scene()
        npc = session.create_npc_from_ai({"name": "Gizli Yolcu", "role": "Yolcu", "location": "tavern"})
        event = events.register_event(
            session.world_state, event_id="secret", window_start=60, window_end=120,
            location_id="tavern", visibility="hidden", summary="Saklı haber.",
            effects=[{"kind": "npc_location", "npc_id": npc["id"], "location_id": "forest"}],
        )
        before = session.serialize_game_state()
        turn(session, "3 dakika bekliyorum")
        public = serialize_session_state(session)
        self.assertNotIn(npc["id"], {n["id"] for n in public["npcs"]})
        self.assertEqual(public["known_scheduled_events"], [])
        context = game.build_world_context(npc, session=session)
        self.assertNotIn(npc["id"], {n["id"] for n in context["npcs"]})
        self.assertNotIn("Saklı haber", json.dumps(context))
        journal = update_campaign_journal(empty_campaign_journal(), before, session.serialize_game_state(), {"action": "wait"}, public["world"])
        self.assertNotIn("Saklı haber", json.dumps(journal))
        self.assertFalse(event["player_observed"])
        visible = events.register_event(session.world_state, event_id="public", window_start=200, window_end=1000, location_id="tavern",
                                        summary="Toplantı sürüyor.", aftermath="Gizli sonuçlar masada.")
        session.advance_campaign_time(100, "explicit_wait", observation={"kind": "look", "location_id": "tavern"})
        self.assertTrue(visible["player_observed"])
        self.assertEqual(events.public_events(session.world_state)[0]["summary"], "Toplantı sürüyor.")
        session.commit_location_change("forest")
        session.advance_campaign_time(1000, "explicit_wait")
        self.assertEqual(events.public_events(session.world_state)[0]["summary"], "Toplantı sürüyor.")

    def test_travel_dice_no_event_and_decisions(self):
        session = scene()
        with patch.object(session.rng, "randint", side_effect=[1, 2, 6, 6]):
            initial = timed_gameplay.start_travel(session, "forest")
            self.assertEqual(initial["status"], "interrupted")
            self.assertEqual(initial["time_result"]["elapsed_seconds"], 300)
            encounter = session.world_state["journey"]["encounter"]
            self.assertEqual(set(encounter["dice"]), {"occurrence", "type", "disposition"})
            paused_time = session.world_state["campaign_time"]["elapsed_seconds"]
            stopped = turn(session, "Yolculuğu durduruyorum.")
            self.assertEqual(stopped["action_result"]["status"], "stopped")
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], paused_time)
            continuation = turn(session, "Yolculuğa devam ediyorum.")
            self.assertEqual(continuation["action_result"]["status"], "stage_completed")
            arrival = turn(session, "Yolculuğa devam ediyorum.")
            self.assertEqual(arrival["action_result"]["new_location"], "forest")
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 1200)
            self.assertIsNone(serialize_session_state(session)["journey"])
        with patch.object(session.rng, "randint", return_value=6) as roll:
            encounter, dice = timed_gameplay.travel_dice(session.rng, [])
            self.assertIsNone(encounter)
            self.assertIsNone(dice["type"])
            self.assertEqual(roll.call_count, 1)
        for decision in ("Geri dönüyorum.", "Kale'ye gidiyorum."):
            other = scene()
            other.world_state["locations"]["tavern"]["travel_routes"]["castle"] = [300]
            with patch.object(other.rng, "randint", side_effect=[1, 2, 6, 6]):
                timed_gameplay.start_travel(other, "forest")
                result = turn(other, decision)["action_result"]
            self.assertEqual(other.world_state["location"], "tavern" if decision.startswith("Geri") else "castle")
            self.assertEqual(result["time_result"]["elapsed_seconds"], 300 if decision.startswith("Geri") else 600)

    def test_round_once_partial_end_and_normal_rollback_rng(self):
        session = scene()
        events.register_event(session.world_state, event_id="combat-window", window_start=1, window_end=6, location_id="tavern",
                              effects=[{"kind": "flag", "key": "scheduled:combat", "value": True}])
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Muhafız", "location": "tavern"})
        session.start_combat(npc)
        combat = session.ensure_combat_state()
        before_time = session.world_state["campaign_time"]["elapsed_seconds"]
        for _ in range(len(combat["initiative_order"])):
            session.advance_combat_turn()
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before_time + 6)
        self.assertEqual(session.world_state["scheduled_events"][0]["status"], "OCCURRED")
        rng = session.rng.getstate()
        session.rng.randint(1, 20)
        progressed_rng = session.rng.getstate()
        self.assertNotEqual(rng, progressed_rng)
        session._restore_combat_death_checkpoint("test")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)
        self.assertEqual(session.world_state["scheduled_events"][0]["status"], "PENDING")
        self.assertNotIn("scheduled:combat", session.world_state["flags"])
        self.assertEqual(session.rng.getstate(), progressed_rng)
        session.end_combat()
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)
        for mode in ("PERMADEATH", "IRONMAN"):
            other = scene()
            other.ensure_death_state()["mode"] = mode
            other.advance_campaign_time(6, "combat_round")
            other._finalize_player_death("test")
            self.assertEqual(other.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_frontend_cannot_supply_time_and_narration_cannot_invent_duration(self):
        session = scene()
        from api.schemas import TurnRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TurnRequest(message="merhaba", elapsed_seconds=300)
        decision = session._narration_safety_decision(
            "Üç saat sonra çevrene bakıyorsun.", "Bakıyorum.",
            action_result={"action": "explore"},
        )
        self.assertTrue(decision["unsafe"])
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)


class NoModel:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Time tests must not call a model.")


class ClockApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.folder.name) / "campaign.sqlite3")
        self.manager = SessionManager(session_factory=scene, campaign_store=self.store)
        self.app = create_app(session_manager=self.manager, ollama_adapter=AuthenticatedOllamaAdapter(NoModel()))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.sid = self.created["session_id"]

    async def asyncTearDown(self):
        await self.http.aclose()
        self.folder.cleanup()

    async def test_wait_atomic_replay_conflict_and_restart(self):
        action = str(uuid4())
        session = self.manager.get(self.sid).game_session
        event = events.register_event(
            session.world_state, event_id="receipt-event", window_start=60, window_end=120,
            location_id="tavern", effects=[{"kind": "flag", "key": "scheduled:receipt", "value": True}],
        )
        path = f"/api/game/sessions/{self.sid}/turn"
        request = {"message": "3 saat bekliyorum", "action_id": action}
        first = await self.http.post(path, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        replay = await self.http.post(path, json=request)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(event["canonical_result"]["effects_applied"], 1)
        self.assertEqual(first.json()["state"]["campaign_time"]["hour"], 12)
        conflict = await self.http.post(path, json={**request, "message": "1 saat bekliyorum"})
        self.assertEqual(conflict.status_code, 409)
        restarted = SessionManager(session_factory=scene, campaign_store=CampaignStore(self.store.path))
        sid, record, _, _, _ = restarted.resume_campaign(self.created["campaign_id"])
        self.assertEqual(clock.public_time(record.game_session.world_state)["hour"], 12)
        self.assertEqual(record.game_session.world_state["scheduled_events"][0]["status"], "OCCURRED")
        self.assertEqual(restarted.get_turn_action(record, action)["response"]["state"]["campaign_time"]["hour"], 12)
        failed_action = str(uuid4())
        before = copy.deepcopy(session.world_state)
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("test")):
            failed = await self.http.post(path, json={"message": "1 saat bekliyorum", "action_id": failed_action})
        self.assertGreaterEqual(failed.status_code, 400)
        self.assertEqual(session.world_state, before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), failed_action))

    async def test_rest_replay_and_failed_save_restores_time_and_rng(self):
        action = str(uuid4())
        path = f"/api/game/sessions/{self.sid}/species-actions"
        request = {"action": "short_rest", "action_id": action}
        first = await self.http.post(path, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        replay = await self.http.post(path, json=request)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(first.json()["state"]["campaign_time"]["hour"], 10)
        record = self.manager.get(self.sid)
        clock_before = copy.deepcopy(record.game_session.world_state["campaign_time"])
        rng_before = record.game_session.rng.getstate()
        failed_action = str(uuid4())
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("test")):
            failed = await self.http.post(path, json={"action": "long_rest", "action_id": failed_action})
        self.assertGreaterEqual(failed.status_code, 400)
        self.assertEqual(record.game_session.world_state["campaign_time"], clock_before)
        self.assertEqual(record.game_session.rng.getstate(), rng_before)
        self.assertIsNone(self.manager.get_turn_action(record, failed_action))


if __name__ == "__main__":
    unittest.main()