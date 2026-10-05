"""Current Package 3 gates; production RNG is patched only in offline tests."""
import copy
import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import action_economy
import exploration
import game
import local_adventure_catalog as catalog
import timed_gameplay
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.test_bounded_encounter import NativeBase
from api.tests import test_exploration_package as baseline
from fastapi.testclient import TestClient


class CloseoutTests(NativeBase):
    canonical = baseline.ExplorationPackageTests.canonical
    arrive = baseline.ExplorationPackageTests.arrive
    enter = baseline.ExplorationPackageTests.enter
    check = baseline.ExplorationPackageTests.check
    open_hall = baseline.ExplorationPackageTests.open_hall

    def test_whole_player_payload_hides_future_catalog(self):
        self.call("/explore begin")
        before = self.canonical()
        payload = self.client.get(f"/api/sessions/{self.sid}/state").json()
        text = json.dumps(payload, ensure_ascii=False)
        for value in (catalog.FORK, catalog.ENTRY, catalog.HALL, catalog.VAULT,
                      "Sessiz Salon", "Eski Mahzen", "stone_secret", "stone_wire",
                      "stone_rubble", "stone_lever", "stone_oak_door", "stone_vault_door"):
            self.assertNotIn(value, text, value)
        self.assertEqual(self.canonical(), before)
        self.enter()
        text = json.dumps(self.client.get(f"/api/sessions/{self.sid}/state").json(), ensure_ascii=False)
        for value in (catalog.HALL, catalog.VAULT, "Sessiz Salon", "Eski Mahzen",
                      "stone_secret_door", "stone_wire", "stone_rubble", "stone_lever"):
            self.assertNotIn(value, text, value)
        self.assertNotIn("Sessiz Salon", self.call("/explore look")[1]["narration"])

    def test_future_features_and_hidden_interactables_are_not_projected(self):
        self.enter()
        world = self.session.world_state
        # Fixture injection proves the server boundary independently of React.
        world["features"].extend([
            {"id": "future_treasure", "location": catalog.VAULT, "name": "Future treasure", "description": "private"},
            {"id": "hidden_lever", "location": catalog.ENTRY, "name": "Hidden lever", "description": "private", "hidden": True},
        ])
        payload = self.client.get(f"/api/sessions/{self.sid}/state").json()
        self.assertNotIn("future_treasure", json.dumps(payload))
        self.assertNotIn("hidden_lever", json.dumps(payload))

    def test_opening_a_known_door_reveals_only_its_adjacent_room(self):
        self.enter()
        self.open_hall()
        payload = self.client.get(f"/api/sessions/{self.sid}/state").json()
        self.assertIn(catalog.HALL, payload["locations"])
        self.assertNotIn(catalog.VAULT, payload["locations"])
        self.assertEqual(payload["exploration"]["exits"][0]["destination"], catalog.HALL)

    def test_stopped_interrupted_and_combat_checks_do_not_inherit_pace(self):
        world = self.session.world_state
        for status in ("STOPPED", "INTERRUPTED", "ARRIVED"):
            world["journey"] = {"status": status, "pace": "fast"}
            self.assertEqual(timed_gameplay.pace_effects(world, "Survival"), (False, False))
        world["journey"]["status"] = "TRAVELLING"
        self.assertEqual(timed_gameplay.pace_effects(world, "Survival"), (False, True))
        world["combat"]["active"] = True
        self.assertEqual(timed_gameplay.pace_effects(world, "Survival"), (False, False))

    def test_terrain_good_roads_and_slowed_speed_use_existing_speed_owner(self):
        self.call("/explore begin")
        world = self.session.world_state
        route = copy.deepcopy(world["locations"][world["location"]]["travel_routes"][catalog.CAMP])
        route["policy"] = {"terrain_max_pace": "slow", "good_road": False}
        self.assertEqual(timed_gameplay.effective_pace(world, route, "fast", self.session), "slow")
        route["policy"]["good_road"] = True
        self.assertEqual(timed_gameplay.effective_pace(world, route, "fast", self.session), "normal")
        self.session.character["speed_penalty_ft"] = 20
        self.assertLessEqual(action_economy.speed(self.session, "player"), 15)
        self.assertEqual(timed_gameplay.effective_pace(world, route, "fast", self.session), "slow")

    def test_search_is_perception_paid_bounded_retry_and_persistent(self):
        self.enter()
        before = self.session.world_state["campaign_time"]["elapsed_seconds"]
        failed = self.check("/explore search", 1)
        self.assertEqual(failed["skill_check_result"]["skill"], "Perception")
        self.assertEqual(self.session.world_state[catalog.KEY]["discoveries"], [])
        with patch("game.roll_d20", side_effect=AssertionError("No infinite reroll")):
            self.call("/explore search")
        self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"] - before, 720)
        self.assertIn("stone_secret", self.session.world_state[catalog.KEY]["discoveries"])
        restored = game.GameSession(seed=14)
        path = self.path.parent / "search.json"
        self.session.save_game(path)
        restored.load_game(path)
        self.assertEqual(restored.world_state[catalog.KEY]["search_attempts"][catalog.ENTRY], 2)

    def test_passive_notice_is_local_once_only_and_not_get_side_effect(self):
        self.enter()
        self.session.character["modifiers"]["wisdom"] = 10
        before_rng = self.session.rng.getstate()
        with patch("game.roll_d20", side_effect=AssertionError("Passive must not roll")):
            self.assertTrue(exploration.notice_passively(self.session))
            self.assertFalse(exploration.notice_passively(self.session))
        self.assertEqual(self.session.rng.getstate(), before_rng)
        self.assertNotIn("stone_marker", self.session.world_state[catalog.KEY]["discoveries"])
        before = self.canonical()
        self.client.get(f"/api/sessions/{self.sid}/state")
        self.assertEqual(self.canonical(), before)

    def test_old_distance_journey_keeps_saved_timing(self):
        self.call("/explore begin")
        world = self.session.world_state
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel pace fast")
            self.call("/travel go " + catalog.CAMP)
        old = copy.deepcopy(world)
        journey = old["journey"]
        journey.pop("pace_rules")
        journey.pop("stage_metadata")
        journey.update(stages=[2880, 2880], duration_seconds=5760, stage_spent_seconds=2880)
        timed_gameplay.validate_state(old)

    def test_stage_metadata_persists_without_invented_midpoint_nodes(self):
        self.call("/explore begin")
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel go " + catalog.CAMP)
        journey = self.session.world_state["journey"]
        self.assertEqual(journey["stage_metadata"][0]["start_mile"], 0)
        self.assertEqual(journey["stage_metadata"][0]["end_mile"], 3)
        self.assertIsNone(journey["stage_metadata"][0]["end"])
        self.assertEqual(journey["stage_metadata"][1]["end"], catalog.CAMP)
        timed_gameplay.validate_state(self.session.world_state)

    def test_changed_request_conflicts_and_stale_manager_cannot_overwrite(self):
        self.call("/explore begin")
        manager = SessionManager(campaign_store=CampaignStore(self.path))
        with TestClient(create_app(session_manager=manager, ollama_adapter=None)) as client:
            resumed = client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume").json()
            stale_sid = resumed["session_id"]
            body, reply = self.call("/travel pace fast")
            before = self.canonical()
            changed = {**body, "message": "/travel pace slow"}
            self.assertEqual(self.client.post(f"/api/sessions/{self.sid}/turn", json=changed).status_code, 409)
            self.assertEqual(self.canonical(), before)
            replay = client.post(f"/api/sessions/{stale_sid}/turn", json=body)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.json(), dict(reply, session_id=stale_sid))
            response = client.post(f"/api/sessions/{stale_sid}/turn", json={
                "message": "/travel pace normal", "action_id": str(uuid4())})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self.canonical(), before)

    def test_third_model_call_is_blocked_before_network(self):
        client = MagicMock()
        adapter = AuthenticatedOllamaAdapter(client)
        with adapter.capture_model_calls() as calls:
            adapter.chat(model="qwen3:8b")
            adapter.chat(model="qwen3:8b")
            with self.assertRaises(RuntimeError):
                adapter.chat(model="qwen3:8b")
        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(len(calls), 2)

    def test_narration_rejection_falls_back_once_without_world_mutation(self):
        self.enter()
        before = self.canonical()
        response = {"message": {"content": json.dumps({
            "narration": "Gizli mahzeni buldun ve altın kazandın.",
            "world_updates": {}, "lore_claims": [],
        })}}
        with patch.object(game.ollama, "chat", return_value=response) as chat:
            token = game._ACTIVE_SESSION.set(self.session)
            try:
                details = game.ask_dungeon_master([], "test", return_details=True, narration_only=True,
                    action_result={"action": "exploration_resolved", "direct_response": "Kapı açıldı.", "weather": "clear"})
            finally:
                game._ACTIVE_SESSION.reset(token)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(details["narration"], "Kapı açıldı.")
        self.assertFalse(details["valid_response"])
        self.assertEqual(self.canonical(), before)

    def test_investigation_requires_a_discovered_local_clue_and_never_discovers_from_prose(self):
        self.enter()
        before = self.canonical()
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            "message": "/explore investigate stone_marker", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.canonical(), before)
        self.check("/explore search", 20)
        result = self.check("/explore investigate stone_secret", 20)
        self.assertEqual(result["skill_check_result"]["skill"], "Investigation")
        self.assertEqual(self.session.world_state[catalog.KEY]["inferences"], ["stone_secret"])
        before = self.canonical()
        with patch("game.roll_d20", side_effect=AssertionError("Known clue must not reroll")):
            self.call("/explore investigate stone_secret")
        after = self.canonical()
        self.assertEqual(before[0]["world_state"]["campaign_time"], after[0]["world_state"]["campaign_time"])
        self.assertEqual(before[1], after[1])
