"""Authored fixture through public turn/save APIs; no model or topology injection."""
import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import authored_dungeon as owner
from combat_lifecycle import CombatRequestError
from api.main import create_app
from api.persistence.campaign_store import CampaignStore, CampaignStorageError
from api.session_manager import SessionManager
from api.tests.test_bounded_encounter import NativeBase


class DungeonTests(NativeBase):
    def state(self):
        return copy.deepcopy((self.session.serialize_game_state(),
                              self.session.rng.getstate(), self.session.messages))

    def reject(self, text):
        before = self.state()
        action = str(uuid4())
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            "message": text, "action_id": action})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), action))

    def test_enter_and_valid_exit_use_existing_location_owner_without_model(self):
        origin = self.session.world_state["location"]
        clock = copy.deepcopy(self.session.world_state["campaign_time"])
        with patch("game.ask_dungeon_master", side_effect=AssertionError("No model permitted")):
            self.call("/dungeon enter")
            self.assertEqual(self.session.world_state["location"], owner.ENTRY)
            _, result = self.call("/dungeon exit entry_hall")
        self.assertEqual(result["state"]["location"], owner.HALL)
        self.assertEqual(result["state"]["locations"][owner.HALL]["name"], "Sessiz Salon")
        self.assertEqual(self.session.world_state["campaign_time"], clock)
        self.assertEqual(self.session.world_state[owner.KEY], owner.definition(origin))
        self.assertEqual(set(owner.ROOMS), set(self.session.world_state[owner.KEY]["rooms"]))
        self.assertEqual(self.session.world_state["scene_state"]["player_position"]["location_id"], owner.HALL)
        self.assertTrue(any(
            location["location_id"] == owner.HALL
            for location in result["state"]["journal"]["discovered_locations"]
        ))

    def test_nonexistent_wrong_room_and_blocked_exit_leave_complete_state_unchanged(self):
        self.call("/dungeon enter")
        self.reject("/dungeon exit nonexistent")
        self.reject("/dungeon exit hall_entry")
        self.call("/dungeon exit entry_hall")
        self.reject("/dungeon exit hall_vault")
        self.reject("/dungeon exit origin_entry")

    def test_implicit_travel_cannot_bypass_graph_or_advance_time(self):
        self.call("/dungeon enter")
        self.reject("Kapalı Mahzen'e gidiyorum.")
        before = self.state()
        with self.assertRaises(CombatRequestError):
            self.session.commit_location_change(owner.VAULT)
        self.assertEqual(self.state(), before)

    def test_return_to_origin_does_not_change_existing_travel_state(self):
        origin = self.session.world_state["location"]
        self.call("/dungeon enter")
        self.call("/dungeon exit entry_hall")
        self.call("/dungeon exit hall_entry")
        self.call("/dungeon exit entry_origin")
        self.assertEqual(self.session.world_state["location"], origin)
        graph = copy.deepcopy(self.session.world_state[owner.KEY])
        self.call("/dungeon enter")
        self.assertEqual(self.session.world_state[owner.KEY], graph)

    def test_replay_conflict_and_restart_keep_same_transition_once(self):
        self.call("/dungeon enter")
        body, accepted = self.call("/dungeon exit entry_hall")
        before = self.state()
        replay = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(replay.json(), accepted)
        self.assertEqual(self.state(), before)
        conflict = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            **body, "message": "/dungeon exit hall_entry"})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.state(), before)
        manager = SessionManager(campaign_store=CampaignStore(self.path))
        with TestClient(create_app(session_manager=manager, ollama_adapter=None)) as client:
            resumed = client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            session = manager.get(sid).game_session
            self.assertEqual(session.world_state["location"], owner.HALL)
            self.assertEqual(session.world_state[owner.KEY], self.session.world_state[owner.KEY])
            loaded = copy.deepcopy(session.serialize_game_state())
            replay = client.post(f"/api/sessions/{sid}/turn", json=body)
            self.assertEqual(replay.json(), dict(accepted, session_id=sid))
            self.assertEqual(session.serialize_game_state(), loaded)

    def test_session_isolation_and_missing_graph_rejection(self):
        self.call("/dungeon enter")
        other = self.create_campaign()
        session = self.manager.get(other["session_id"]).game_session
        before = copy.deepcopy((session.serialize_game_state(), session.rng.getstate()))
        denied = self.client.post(f"/api/sessions/{other['session_id']}/turn", json={
            "message": "/dungeon exit entry_hall", "action_id": str(uuid4())})
        self.assertEqual(denied.status_code, 400)
        self.assertEqual((session.serialize_game_state(), session.rng.getstate()), before)
        self.assertNotIn(owner.KEY, session.world_state)
        self.assertFalse(set(owner.ROOMS).intersection(session.world_state["locations"]))

    def test_failed_autosave_rolls_back_graph_and_retry_uses_same_action(self):
        before = self.state()
        body = {"message": "/dungeon enter", "action_id": str(uuid4())}
        store = self.manager._campaign_store
        with patch.object(store, "save_campaign", side_effect=CampaignStorageError("test")):
            failed = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertGreaterEqual(failed.status_code, 400)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), body["action_id"]))
        accepted = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.session.world_state["location"], owner.ENTRY)

    def test_failed_traversal_save_restores_location_scene_clock_rng_and_receipt(self):
        self.call("/dungeon enter")
        before = self.state()
        body = {"message": "/dungeon exit entry_hall", "action_id": str(uuid4())}
        with patch.object(self.manager._campaign_store, "save_campaign",
                          side_effect=CampaignStorageError("test")):
            response = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.state(), before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), body["action_id"]))
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.world_state["location"], owner.HALL)

    def test_nonadjacent_direct_destination_and_nonexistent_destination_are_rejected(self):
        self.call("/dungeon enter")
        before = self.state()
        for target in (owner.VAULT, "nonexistent_room"):
            with self.assertRaises(CombatRequestError):
                self.session.commit_location_change(target)
            self.assertEqual(self.state(), before)

    def test_legacy_load_and_invalid_saved_graph_are_fail_closed(self):
        legacy = self.session.serialize_game_state()
        self.assertNotIn(owner.KEY, legacy["world_state"])
        path = self.path.parent / "engine.json"
        path.write_text(json.dumps(legacy))
        self.session.load_game(path)
        self.assertNotIn(owner.KEY, self.session.world_state)
        self.call("/dungeon enter")
        before = self.state()
        bad = self.session.serialize_game_state()
        bad["world_state"][owner.KEY]["exits"]["hall_vault"]["blocked"] = False
        path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            self.session.load_game(path)
        self.assertEqual(self.state(), before)

    def test_server_lists_only_current_room_exits(self):
        self.call("/dungeon enter")
        _, result = self.call("/dungeon exits")
        self.assertIn("entry_hall", result["narration"])
        self.assertNotIn("hall_vault", result["narration"])


if __name__ == "__main__":
    unittest.main()
