"""Package 3 through the real public API/catalog; disposable saves, no LLM."""
import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import exploration
import local_adventure_catalog as catalog
import timed_gameplay
from combat_lifecycle import CombatRequestError
from api.main import create_app
from api.persistence.campaign_store import CampaignStore, CampaignStorageError
from api.session_manager import SessionManager
from api.tests.test_bounded_encounter import NativeBase


from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
class ExplorationPackageTests(NativeBase):
    def canonical(self):
        return copy.deepcopy((self.session.serialize_game_state(), self.session.rng.getstate(), self.session.messages))

    def reject(self, message):
        before = self.canonical()
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            "message": message, "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.canonical(), before)

    def arrive(self, destination, *, roll=20):
        with patch("game.roll_d20", return_value=roll), patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel go " + destination)
            for _ in range(48):
                if self.session.world_state["journey"]["status"] == "ARRIVED":
                    break
                self.call("/travel continue")
        self.assertEqual(self.session.world_state["journey"]["status"], "ARRIVED")

    def enter(self):
        self.call("/explore begin")
        self.arrive(catalog.CAMP)
        self.arrive(catalog.ENTRY)

    def check(self, command, roll=20):
        with patch("game.roll_d20", return_value=roll):
            return self.call(command)[1]

    def open_hall(self):
        self.check("/explore door stone_oak_door unlock")
        self.call("/explore door stone_oak_door open")

    def test_catalog_is_opt_in_and_does_not_claim_visits(self):
        before = self.canonical()
        state = self.client.get(f"/api/sessions/{self.sid}/state").json()
        self.assertIsNone(state["exploration"])
        self.assertFalse(set(catalog.LOCATIONS) & set(self.session.world_state["locations"]))
        self.assertEqual(self.canonical(), before)
        with patch("game.ask_dungeon_master", side_effect=AssertionError("No model")):
            result = self.call("/explore begin")[1]
        self.assertEqual(result["state"]["location"], self.start["starting_location_id"])
        visited = {r["location_id"] for r in result["state"]["journal"]["discovered_locations"]}
        self.assertFalse(set(catalog.LOCATIONS) & visited)
        self.assertNotIn("stone_secret", json.dumps(result["state"]["exploration"]))
        self.assertNotIn("stone_secret_door", {d["id"] for d in result["state"]["doors"]})

    def test_pace_distances_and_duration_are_owned_and_legacy_is_unchanged(self):
        self.call("/explore begin")
        world = self.session.world_state
        for pace, duration in (("fast", 5400), ("normal", 7200), ("slow", 10800)):
            self.call("/travel pace " + pace)
            self.assertEqual(sum(timed_gameplay.route_stages(world, catalog.CAMP)), duration)
        legacy = copy.deepcopy(world)
        legacy.pop(catalog.KEY)
        origin = legacy["location"]
        legacy["locations"][origin]["travel_routes"][catalog.CAMP] = [120, 240]
        self.assertEqual(timed_gameplay.route_stages(legacy, catalog.CAMP, "fast"), [120, 240])
        self.assertEqual(timed_gameplay.route_stages(legacy, catalog.CAMP, "slow"), [120, 240])
        legacy["flags"]["travel_pace"] = "fast"
        legacy["journey"] = {"status": "TRAVELLING"}
        self.assertEqual(timed_gameplay.pace_effects(legacy, "Survival"), (False, True))
        for pace, skill, expected in (
            ("fast", "Perception", (False, True)), ("fast", "Survival", (False, True)),
            ("fast", "Stealth", (False, True)), ("normal", "Stealth", (False, True)),
            ("normal", "Survival", (False, False)), ("slow", "Perception", (True, False)),
            ("slow", "Survival", (True, False)), ("slow", "Stealth", (False, False)),
        ):
            self.assertEqual(timed_gameplay.pace_effects(world, skill, pace=pace), expected)

    def test_travel_advances_once_and_replay_survives_reopening(self):
        self.call("/explore begin")
        self.call("/travel pace fast")
        before = self.session.world_state["campaign_time"]["elapsed_seconds"]
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            body, reply = self.call("/travel go " + catalog.CAMP)
        canonical = self.canonical()
        self.assertEqual(reply["state"]["journey"]["distance_miles"], 6)
        self.assertEqual(reply["state"]["journey"]["duration_seconds"], 5400)
        self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"] - before, 2700)
        self.assertEqual(self.client.post(f"/api/sessions/{self.sid}/turn", json=body).json(), reply)
        self.assertEqual(self.canonical(), canonical)
        manager = SessionManager(campaign_store=CampaignStore(self.path, bound_principal=TEST_PLAYER))
        with TestClient(create_app(session_manager=manager, ollama_adapter=None, authenticator=FixedAuthenticator(TEST_PLAYER))) as client:
            resumed = client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume").json()
            sid = resumed["session_id"]
            session = manager.get(sid).game_session
            expected = copy.deepcopy((session.serialize_game_state(), session.rng.getstate()))
            self.assertEqual(client.post(f"/api/sessions/{sid}/turn", json=body).json(), dict(reply, session_id=sid))
            self.assertEqual((session.serialize_game_state(), session.rng.getstate()), expected)

    def test_failure_can_only_choose_an_authored_lost_route(self):
        self.call("/explore begin")
        self.arrive(catalog.CAMP)
        self.call("/travel pace fast")
        with patch("game.roll_d20", return_value=1), patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            result = self.call("/travel go " + catalog.ENTRY)[1]
        journey = self.session.world_state["journey"]
        self.assertEqual(journey["destination"], catalog.FORK)
        self.assertEqual(result["skill_check_result"]["skill"], "Survival")
        # An unmarked footpath caps effective pace at normal, independently of
        # the player's requested fast setting.
        self.assertFalse(result["skill_check_result"]["disadvantage"])
        self.assertEqual(journey["pace"], "normal")
        self.assertEqual(journey["route_id"], "stone_camp_fork")
        self.reject("/travel pace slow")

    def test_unknown_nonadjacent_and_hidden_routes_leave_everything_unchanged(self):
        self.call("/explore begin")
        self.reject("/travel go unknown")
        self.reject("/travel go " + catalog.VAULT)
        with self.assertRaises(CombatRequestError):
            self.session.commit_location_change(catalog.CAMP)
        self.enter()
        self.reject("/explore exit entry_secret")
        self.reject("/explore door stone_secret_door open")
        self.reject("/explore trap stone_wire bypass")
        self.reject("/explore interact stone_lever")
        self.reject("/explore exit hall_vault")

    def test_search_is_local_and_secret_door_requires_exact_target(self):
        self.enter()
        self.check("/explore search")
        state = self.client.get(f"/api/sessions/{self.sid}/state").json()
        identities = {r["id"] for r in state["exploration"]["discoveries"]}
        self.assertEqual(identities, {"stone_secret", "stone_wire"})
        self.assertNotIn("stone_marker", identities)
        self.assertEqual({e["id"] for e in state["exploration"]["exits"]}, {"entry_hall", "entry_secret"})
        before = copy.deepcopy(self.session.world_state["doors"])
        reply = self.call("Kapıyı açıyorum.")[1]
        self.assertIn("Hangi", reply["narration"])
        self.assertEqual(self.session.world_state["doors"], before)
        self.check("/explore door stone_secret_door unlock")
        self.call("/explore door stone_secret_door open")
        self.call("/explore exit entry_secret")
        self.assertEqual(self.session.world_state["location"], catalog.VAULT)
        self.reject("/explore trap stone_wire disarm")

    def test_trap_disarm_and_bypass_survive_save_and_reload(self):
        for operation, expected in (("disarm", "disarmed"), ("bypass", "bypassed")):
            with self.subTest(operation=operation):
                campaign = self.create_campaign()
                self.campaign, self.sid = campaign, campaign["session_id"]
                self.enter()
                self.check("/explore search")
                self.check("/explore trap stone_wire " + operation)
                self.open_hall()
                hp = self.session.character["current_hp"]
                self.call("/explore exit entry_hall")
                self.assertEqual(self.session.character["current_hp"], hp)
                payload = self.session.serialize_game_state()
                path = self.path.parent / "engine.json"
                path.write_text(json.dumps(payload))
                self.session.load_game(path)
                self.assertEqual(self.session.world_state[catalog.KEY]["trap_states"]["stone_wire"], expected)

    def test_triggered_trap_damages_once_and_can_be_neutralized(self):
        self.enter()
        self.open_hall()
        hp = self.session.character["current_hp"]
        body, result = self.call("/explore exit entry_hall")
        self.assertEqual(self.session.character["current_hp"], hp - 2)
        self.assertEqual(self.session.world_state[catalog.KEY]["trap_states"]["stone_wire"], "triggered")
        canonical = self.canonical()
        self.assertEqual(self.client.post(f"/api/sessions/{self.sid}/turn", json=body).json(), result)
        self.assertEqual(self.canonical(), canonical)
        self.call("/explore exit hall_entry")
        self.call("/explore trap stone_wire neutralize")
        self.call("/explore exit entry_hall")
        self.assertEqual(self.session.character["current_hp"], hp - 2)
        self.assertEqual(self.session.world_state[catalog.KEY]["trap_states"]["stone_wire"], "neutralized")

    def test_blocked_path_requires_authored_interaction_and_open_door(self):
        self.enter()
        self.open_hall()
        self.call("/explore exit entry_hall")
        self.reject("/explore exit hall_vault")
        self.call("/explore interact stone_lever")
        self.reject("/explore exit hall_vault")
        self.call("/explore door stone_vault_door open")
        self.call("/explore exit hall_vault")
        self.assertEqual(self.session.world_state["location"], catalog.VAULT)

    def test_failed_autosave_restores_rng_clock_doors_and_knowledge(self):
        self.enter()
        before = self.canonical()
        body = {"message": "/explore search", "action_id": str(uuid4())}
        with patch.object(self.manager._campaign_store, "save_campaign", side_effect=CampaignStorageError("test")):
            response = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.canonical(), before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), body["action_id"]))
        with patch("game.roll_d20", return_value=20):
            accepted = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn("stone_secret", self.session.world_state[catalog.KEY]["discoveries"])

    def test_altered_catalog_state_is_rejected_without_partial_load(self):
        self.enter()
        before = self.canonical()
        for kind in ("route", "trap", "door", "discovery"):
            bad = self.session.serialize_game_state()
            world = bad["world_state"]
            if kind == "route":
                world["locations"][catalog.CAMP]["travel_routes"][catalog.ENTRY]["distance_miles"] = 1
            elif kind == "trap":
                world[catalog.KEY]["trap_states"]["stone_wire"] = "invented"
            elif kind == "door":
                next(d for d in world["doors"] if d["id"] == "stone_oak_door")["open"] = True
            else:
                world[catalog.KEY]["discoveries"].append("model_invented")
            path = self.path.parent / "bad.json"
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.session.load_game(path)
            self.assertEqual(self.canonical(), before)

    def test_sessions_are_isolated_and_model_is_never_called(self):
        other = self.create_campaign()
        before = copy.deepcopy(self.manager.get(other["session_id"]).game_session.serialize_game_state())
        with patch("game.ask_dungeon_master", side_effect=AssertionError("No model")):
            self.enter()
            self.check("/explore search")
        self.assertEqual(self.manager.get(other["session_id"]).game_session.serialize_game_state(), before)

    def test_journey_interruption_stops_and_retraces_actual_progress(self):
        self.call("/explore begin")
        before = self.session.world_state["campaign_time"]["elapsed_seconds"]
        # Real owner, real RNG with a deterministic seed; no injected encounter data.
        self.session.rng.seed(1)
        result = self.call("/travel go " + catalog.CAMP)[1]
        self.assertEqual(self.session.world_state["journey"]["status"], "INTERRUPTED")
        self.assertEqual(result["state"]["journey"]["remaining_seconds"], 5400)
        self.call("/travel stop")
        self.call("/travel return")
        self.assertEqual(self.session.world_state["journey"]["status"], "ARRIVED")
        self.assertEqual(self.session.world_state["location"], self.start["starting_location_id"])
        self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"] - before, 3600)

    def test_encounter_handoff_uses_existing_statblock_and_combat_owner(self):
        self.enter()
        with patch("game.ask_dungeon_master", side_effect=AssertionError("No model")):
            result = self.call("/explore encounter")[1]
        self.assertFalse(result["state"]["combat"]["active"])
        npc_id = self.session.world_state["bounded_encounter"]["npc_id"]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == npc_id)
        self.assertEqual(npc["monster_stat_block_id"], "mm2024.commoner")
        self.call("Avlu çatışmasını başlat")
        self.assertTrue(self.session.world_state["combat"]["active"])
        self.reject("/explore exit entry_hall")

    def test_scanning_uses_pace_and_time_without_advancing_travel_or_discoveries(self):
        self.call("/explore begin")
        self.call("/travel pace slow")
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel go " + catalog.CAMP)
        world = self.session.world_state
        journey = copy.deepcopy(world["journey"])
        discoveries = copy.deepcopy(world[catalog.KEY]["discoveries"])
        before = world["campaign_time"]["elapsed_seconds"]
        result = self.check("/travel scout")
        self.assertTrue(result["skill_check_result"]["advantage"])
        self.assertEqual(len(result["skill_check_result"]["d20_rolls"]), 2)
        self.assertEqual(world["campaign_time"]["elapsed_seconds"] - before, 60)
        self.assertEqual(world["journey"], journey)
        self.assertEqual(world[catalog.KEY]["discoveries"], discoveries)
        self.assertEqual(world["location"], self.start["starting_location_id"])

    def test_lethal_trap_keeps_death_owner_and_blocks_arrival(self):
        self.enter()
        self.open_hall()
        self.session.character["current_hp"] = 1
        before = self.session.world_state["campaign_time"]["elapsed_seconds"]
        self.call("/explore exit entry_hall")
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.session.world_state["location"], catalog.ENTRY)
        self.assertEqual(self.session.world_state["player_combat_status"], "unconscious")
        self.assertTrue(self.session.world_state["death_state"]["prone"])
        self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"] - before, 30)
        manager = SessionManager(campaign_store=CampaignStore(self.path, bound_principal=TEST_PLAYER))
        _, resumed, _, _, _ = manager.resume_campaign(self.campaign["campaign_id"])
        self.assertEqual(resumed.game_session.world_state["location"], catalog.ENTRY)
        self.assertEqual(resumed.game_session.character["current_hp"], 0)
        self.assertEqual(resumed.game_session.world_state[catalog.KEY]["trap_states"]["stone_wire"], "triggered")

    def test_failed_hazard_persists_damage_and_remains_blocked(self):
        self.enter()
        self.open_hall()
        self.call("/explore exit entry_hall")
        before = self.session.character["current_hp"]
        self.check("/explore hazard stone_rubble clear", roll=1)
        self.assertEqual(self.session.character["current_hp"], before - 2)
        self.assertEqual(self.session.world_state[catalog.KEY]["hazard_states"]["stone_rubble"], "active")
        self.reject("/explore exit hall_vault")

    def test_unrelated_feature_search_does_not_reveal_room_secrets(self):
        self.enter()
        world = self.session.world_state
        before = copy.deepcopy(world[catalog.KEY])
        self.assertEqual(exploration.complete_search(world, catalog.ENTRY, True, "different-feature"), [])
        self.assertEqual(world[catalog.KEY], before)

    def test_unknown_named_door_does_not_open_the_only_known_door(self):
        self.enter()
        self.check("/explore door stone_oak_door unlock")
        before = copy.deepcopy(self.session.world_state["doors"])
        self.call("Ejder kapısını açıyorum.")
        self.assertEqual(self.session.world_state["doors"], before)

    def test_authored_weather_reaches_the_public_world_projection(self):
        self.call("/explore begin")
        self.arrive(catalog.CAMP)
        self.arrive(catalog.ENTRY, roll=1)
        self.assertEqual(self.session.world_state["location"], catalog.FORK)
        state = self.client.get(f"/api/sessions/{self.sid}/state").json()
        self.assertEqual(state["world"]["weather"], "fog")
        self.assertEqual(state["world"]["environment"], "wilderness")
        self.assertEqual(state["exploration"]["weather"], "fog")

    def test_malformed_new_metadata_fails_as_value_error(self):
        self.call("/explore begin")
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel go " + catalog.CAMP)
        for kind in ("lost", "stages", "pace", "route_id", "distance"):
            bad = copy.deepcopy(self.session.world_state)
            if kind == "lost":
                bad["locations"][catalog.CAMP]["travel_routes"][catalog.ENTRY]["lost_destinations"] = [{}]
            elif kind == "stages":
                bad["journey"]["stages"] = [None]
            elif kind == "pace":
                bad["journey"]["pace"] = []
            elif kind == "route_id":
                bad["journey"]["route_id"] = "invented"
            else:
                bad["journey"]["distance_miles"] = 1
            with self.assertRaises(ValueError, msg=kind):
                timed_gameplay.validate_state(bad)

    def test_fog_visual_disadvantage_cancels_slow_pace_advantage(self):
        self.call("/explore begin")
        self.arrive(catalog.CAMP)
        self.arrive(catalog.ENTRY, roll=1)
        self.call("/travel pace slow")
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {})):
            self.call("/travel go " + catalog.CAMP)
        with patch("game.roll_d20", return_value=20) as dice:
            result = self.call("/travel scout")[1]["skill_check_result"]
        self.assertEqual(dice.call_count, 1)
        self.assertTrue(result["advantage"])
        self.assertTrue(result["disadvantage"])
        self.assertEqual(result["d20"], 20)
        self.assertNotIn("d20_rolls", result)

    def test_scheduled_decision_holds_progress_until_explicit_native_choice(self):
        import scheduled_events
        self.enter()
        world = self.session.world_state
        now = world["campaign_time"]["elapsed_seconds"]
        scheduled_events.register_event(
            world, event_id="authored-road-decision", window_start=now + 60,
            window_end=now + 3600, location_id=world["location"],
            summary="Patikanın başında iki yolcu seni durdurdu.", requires_decision=True,
            behavior="INTERRUPTIVE")
        self.call("/explore search")
        self.assertEqual(world["active_task"]["spent_seconds"], 60)
        self.reject("/explore search")
        before = copy.deepcopy(world["active_task"])
        self.call("/explore decision continue")
        event = next(e for e in world["scheduled_events"] if e["event_id"] == "authored-road-decision")
        self.assertEqual(event["decision_status"], "RESOLVED")
        self.assertEqual(world["active_task"], before)
        self.check("/explore search")
        self.assertIsNone(world["active_task"])
        self.assertEqual(world["campaign_time"]["elapsed_seconds"] - now, 360)

    def test_existing_conditions_block_exploration_without_spending_time(self):
        self.call("/explore begin")
        self.session.character["conditions"] = ["paralyzed"]
        self.reject("/travel go " + catalog.CAMP)
        self.reject("/explore search")
        self.session.character["conditions"] = ["restrained"]
        self.reject("/travel go " + catalog.CAMP)


if __name__ == "__main__":
    unittest.main()
