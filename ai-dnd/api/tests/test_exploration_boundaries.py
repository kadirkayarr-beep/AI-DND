"""Package 3 blocker boundaries through existing session and transaction owners."""
import copy
from uuid import uuid4
from unittest.mock import patch

import equipment_economy
import game
import timed_gameplay
import weapon_attack
from api.tests.test_bounded_encounter import NativeBase
from api.tests import test_exploration_package as baseline


class BoundaryTests(NativeBase):
    canonical = baseline.ExplorationPackageTests.canonical

    def clock_zero(self):
        self.session.ensure_campaign_clock()
        self.session.world_state["campaign_time"]["start_second"] = 0
        self.session.world_state["campaign_time"]["elapsed_seconds"] = 0

    def test_eight_nine_ten_hour_boundaries_and_penalty(self):
        self.clock_zero()
        with patch.object(self.session.rng, "randint", return_value=1):
            timed_gameplay.advance_walking(self.session, 8 * 3600)
            self.assertEqual(self.session.world_state["travel_effort"]["checks"], [])
            timed_gameplay.advance_walking(self.session, 3600)
            self.assertEqual(self.session.character["exhaustion"], 1)
            timed_gameplay.advance_walking(self.session, 3600)
        checks = self.session.world_state["travel_effort"]["checks"]
        self.assertEqual([c["dc"] for c in checks], [11, 12])
        self.assertEqual(checks[1]["modifier_breakdown"]["circumstantial_modifier"], -2)
        self.assertEqual(self.session.character["exhaustion"], 2)
        timed_gameplay.validate_state(self.session.world_state)

    def test_time_passage_does_not_rest_or_remove_exhaustion(self):
        self.clock_zero()
        self.session.character["exhaustion"] = 2
        timed_gameplay._advance(self.session, 2 * 86400, "wait")
        self.assertEqual(self.session.character["exhaustion"], 2)
        self.session.resolve_species_trait_action("long_rest")
        self.assertEqual(self.session.character["exhaustion"], 1)

    def test_public_daily_save_history_survives_reload_and_is_read_only(self):
        self.clock_zero()
        with patch.object(self.session.rng, "randint", return_value=1):
            timed_gameplay.advance_walking(self.session, 10 * 3600)
        before = self.canonical()
        view = self.client.get(f"/api/sessions/{self.sid}/state").json()["expedition"]
        self.assertEqual([save["dc"] for save in view["extended_travel_saves"]], [11, 12])
        self.assertEqual(view["extended_travel_saves"][1]["modifier_breakdown"]["circumstantial_modifier"], -2)
        self.assertEqual(self.canonical(), before)
        path = self.path.parent / "public-travel-saves.json"
        self.session.save_game(path)
        restored = game.GameSession(seed=99)
        restored.load_game(path)
        self.assertEqual(timed_gameplay.public_expedition(restored)["extended_travel_saves"],
                         view["extended_travel_saves"])
        self.session.world_state["campaign_time"]["elapsed_seconds"] = 86400
        next_day = timed_gameplay.public_expedition(self.session)
        self.assertEqual(next_day["walking_seconds"], 0)
        self.assertEqual(next_day["extended_travel_saves"], [])

    def test_exhaustion_six_uses_existing_death_policy(self):
        self.session.character["exhaustion"] = 5
        with patch.object(self.session, "_finalize_player_death") as death:
            weapon_attack.add_exhaustion(self.session, "extended_travel")
            death.assert_called_once_with("extended_travel")
        self.assertEqual(self.session.character["exhaustion"], 6)

    def tracking_fixture(self, confined):
        world = self.session.world_state
        world["features"].append({"id": "known_track", "name": "Bilinen ayak izleri",
                                  "location": world["location"],
                                  "trail_policy": {"confined": confined, "dc": 10}})

    def test_tracking_confined_600_and_outdoors_3600_and_replay(self):
        for confined, seconds in ((True, 600), (False, 3600)):
            with self.subTest(confined=confined):
                world = self.session.world_state
                world["tracking"] = None
                world["features"] = []
                self.tracking_fixture(confined)
                before = world["campaign_time"]["elapsed_seconds"]
                with patch("game.roll_d20", return_value=20):
                    body, reply = self.call("/travel track known_track")
                self.assertEqual(world["campaign_time"]["elapsed_seconds"] - before, seconds)
                self.assertEqual(world["tracking"]["status"], "REACQUIRED")
                before = self.canonical()
                replay = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
                self.assertEqual(replay.json(), reply)
                self.assertEqual(self.canonical(), before)

    def test_missing_trail_rejected_without_time_or_rng(self):
        before = self.canonical()
        reply = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            "message": "/travel track hidden", "action_id": str(uuid4())})
        self.assertEqual(reply.status_code, 400)
        self.assertEqual(before, self.canonical())

    def lock_fixture(self, quality, complexity):
        world = self.session.world_state
        world["doors"].append({"id": "standard_gate", "name": "Standart Kapı",
            "location": world["location"], "description": "Görünen kapı",
            "open": False, "locked": True, "broken": False,
            "lock_policy": {"quality": quality, "complexity": complexity}})
        world["inventory"].append("Thieves' Tools")

    def test_standard_lock_quality_complexity_and_tools(self):
        for quality, dc in (("inferior", 10), ("good", 15), ("superior", 20)):
            for complexity, seconds in (("simple", 6), ("complex", 60)):
                with self.subTest(quality=quality, complexity=complexity):
                    self.session.world_state["doors"] = []
                    self.lock_fixture(quality, complexity)
                    before = self.session.world_state["campaign_time"]["elapsed_seconds"]
                    with patch("game.roll_d20", return_value=20):
                        _, reply = self.call("/explore door standard_gate unlock")
                    self.assertEqual(reply["skill_check_result"]["dc"], dc)
                    self.assertEqual(self.session.world_state["campaign_time"]["elapsed_seconds"] - before, seconds)

    def test_missing_tools_rejected_without_mutation(self):
        self.lock_fixture("good", "simple")
        self.session.world_state["inventory"] = []
        before = self.canonical()
        result = self.client.post(f"/api/sessions/{self.sid}/turn", json={
            "message": "/explore door standard_gate unlock", "action_id": str(uuid4())})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(before, self.canonical())

    def test_supplies_legacy_disabled_no_consumption(self):
        world = self.session.world_state
        world["inventory"] = ["Rations (1 day)", "Water (1 gallon)"]
        before = copy.deepcopy(world["inventory"])
        self.assertEqual(equipment_economy.consume_daily_supplies(self.session), {})
        self.assertEqual(world["inventory"], before)

    def test_enabled_supplies_use_inventory_not_duplicate_resource_pool(self):
        world = self.session.world_state
        world["inventory"] = ["Rations (1 day)", "Water (1 gallon)"]
        world["supplies_policy"] = {"enabled": True}
        result = equipment_economy.consume_daily_supplies(self.session)
        self.assertEqual(len(result["consumed"]), 2)
        self.assertEqual(result["missing"], [])
        self.assertEqual(world["inventory"], [])

    def test_hidden_track_is_not_player_action(self):
        self.tracking_fixture(False)
        self.session.world_state["features"][-1]["hidden"] = True
        view = timed_gameplay.public_expedition(self.session)
        self.assertNotIn("known_track", str(view))

    def test_daily_supply_receipt_cannot_consume_twice(self):
        world = self.session.world_state
        world["supplies_policy"] = {"enabled": True}
        world["inventory"] = ["Rations (1 day)", "Water (1 gallon)"] * 2
        equipment_economy.consume_daily_supplies(self.session, day=1)
        before = copy.deepcopy(world["inventory"])
        self.assertEqual(equipment_economy.consume_daily_supplies(self.session, day=1), {})
        self.assertEqual(world["inventory"], before)

    def test_tracking_save_reload_and_partial_resume(self):
        self.tracking_fixture(True)
        world = self.session.world_state
        world["tracking"] = {"trail_id": "known_track", "location_id": world["location"],
            "status": "LOST", "confined": True, "dc": 10, "spent_seconds": 300, "attempts": 0}
        path = self.path.parent / "tracking.json"
        self.session.save_game(path)
        restored = game.GameSession(seed=99)
        restored.load_game(path)
        self.assertEqual(restored.world_state["tracking"], world["tracking"])
        before = world["campaign_time"]["elapsed_seconds"]
        with patch("game.roll_d20", return_value=20):
            self.call("/travel reacquire")
        self.assertEqual(world["campaign_time"]["elapsed_seconds"] - before, 300)

    def test_exhaustion_and_optional_supplies_survive_save_reload(self):
        self.clock_zero()
        self.session.character["exhaustion"] = 2
        self.session.world_state["supplies_policy"] = {"enabled": True}
        path = self.path.parent / "exhaustion.json"
        self.session.save_game(path)
        restored = game.GameSession(seed=99)
        restored.load_game(path)
        self.assertEqual(restored.character["exhaustion"], 2)
        self.assertEqual(restored.world_state["supplies_policy"], {"enabled": True})

    def test_standard_tool_proficiency_and_skill_grant_do_not_stack_bonus(self):
        self.lock_fixture("good", "simple")
        self.session.character["proficient_tools"] = ["Thieves' Tools"]
        self.session.character["proficient_skills"] = ["Sleight of Hand"]
        with patch("game.roll_d20", return_value=10):
            _, reply = self.call("/explore door standard_gate unlock")
        card = reply["skill_check_result"]
        self.assertEqual(card["proficiency_modifier"], self.session.character["proficiency_bonus"])
        self.assertEqual(len(card["d20_rolls"]), 2)

    def test_enabled_missing_resources_apply_conditions_not_fake_items(self):
        world = self.session.world_state
        world["supplies_policy"] = {"enabled": True}
        world["inventory"] = []
        with patch.object(self.session.rng, "randint", return_value=20):
            result = equipment_economy.consume_daily_supplies(self.session, day=1)
        self.assertEqual(result["missing"], ["food", "water"])
        self.assertEqual(self.session.character["exhaustion"], 1)
        self.assertEqual(world["inventory"], [])

    def test_general_narration_cannot_commit_model_world_proposals(self):
        world = self.session.world_state
        before = {k: copy.deepcopy(world[k]) for k in ("locations", "npcs", "features", "shops")}
        resolved = game.ResolvedTurn(
            action_result={"action": "observe", "status": "completed",
                           "direct_response": "Çevreye baktın.", "success": True},
            fallback_response="Çevreye baktın.", raw_result={},
            allow_new_npcs=True, allow_new_features=True, allow_new_locations=True)
        packet = {"valid_response": True, "narration": "Çevreye baktın.",
                  "lore_claims": [], "world_updates": {
                      "create_locations": [{"id": "model_place", "name": "Model Place", "type": "road"}],
                      "create_npcs": [{"name": "Model NPC", "location": world["location"]}],
                      "create_features": [{"name": "Model Feature", "location": world["location"]}]}}
        with patch("game.ask_dungeon_master", return_value=packet):
            self.session._narrate_resolved_turn(resolved, "Çevreye bakıyorum.", [], None)
        for key, value in before.items():
            self.assertEqual(world[key], value, key)

    def test_malformed_new_state_rejected_before_loading(self):
        world = self.session.world_state
        for field, value in (("tracking", {"trail_id": "forged"}),
                             ("travel_effort", {"day": 0, "walking_seconds": 32400, "checks": [{}]})):
            with self.subTest(field=field):
                candidate = copy.deepcopy(world)
                candidate[field] = value
                with self.assertRaises(ValueError):
                    timed_gameplay.validate_state(candidate)

    def test_supply_death_interrupts_rest_at_midnight_without_revival(self):
        self.clock_zero()
        world = self.session.world_state
        world["campaign_time"]["elapsed_seconds"] = 23 * 3600
        world["supplies_policy"] = {"enabled": True}
        world["inventory"] = ["Rations (1 day)"]
        self.session.character["exhaustion"] = 5
        with patch.object(self.session.rng, "randint", return_value=20):
            result = self.session.resolve_species_trait_action("long_rest")
        self.assertTrue(result["time_advance"]["condition_death"])
        self.assertEqual(result["time_advance"]["elapsed_seconds"], 3600)
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.session.character["exhaustion"], 6)
        self.assertTrue(world["death_state"]["dead"])

    def test_fatal_extended_travel_stops_without_another_hour(self):
        self.clock_zero()
        timed_gameplay.advance_walking(self.session, 8 * 3600)
        self.session.character["exhaustion"] = 5
        with patch.object(self.session.rng, "randint", return_value=1):
            result = timed_gameplay.advance_walking(self.session, 2 * 3600)
        self.assertEqual(result["elapsed_seconds"], 3600)
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["death_results"][0]["death_resolution"]["cause"], "extended_travel")
