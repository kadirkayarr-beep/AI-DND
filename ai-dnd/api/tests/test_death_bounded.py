"""Focused #08 tests: real engine transitions and temporary campaign stores."""
import copy
import unittest
from unittest.mock import patch

from api.tests import test_death_system as death_fixtures
from api.tests import test_campaign_api as campaign_fixtures
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
import game
import campaign_time


class DeathBoundedTests(unittest.TestCase):
    def unconscious(self):
        s = death_fixtures.make_session()
        campaign_time.initialize(s.world_state)
        s.world_state["death_state"]["mode"] = "PERMADEATH"
        s._apply_player_damage(20, took_damage=True)
        return s

    def test_critical_failure_saturates(self):
        s = self.unconscious()
        s.ensure_death_state()["failures"] = 2
        s._apply_player_damage(1, critical=True, took_damage=True)
        self.assertEqual(s.ensure_death_state()["failures"], 3)
        self.assertTrue(s.ensure_death_state()["dead"])

    def test_zero_hp_massive_damage_uses_damage_before_temporary_hp(self):
        s = self.unconscious()
        s.character["max_hp"] = 2
        s._species_trait_state()["temporary_hit_points"] = 2
        result = s._apply_attack_damage_to_player(2, False, True)
        self.assertEqual(result["death_resolution"]["cause"], "massive_damage")

    def test_recovery_once_and_cancellation(self):
        s = self.unconscious()
        with patch.object(s.rng, "randint", return_value=2) as die:
            s.stabilize_player()
            s.stabilize_player()
            self.assertEqual(die.call_count, 1)
        s.advance_campaign_time(7199, "wait")
        self.assertEqual(s.character["current_hp"], 0)
        s.advance_campaign_time(1, "wait")
        self.assertEqual(s.character["current_hp"], 1)
        rng = s.rng.getstate()
        s.advance_campaign_time(7200, "wait")
        self.assertEqual(s.rng.getstate(), rng)
        s._apply_player_damage(1, took_damage=True)
        with patch.object(s.rng, "randint", return_value=1):
            s.stabilize_player()
        s._apply_player_damage(1, took_damage=True)
        self.assertIsNone(s.ensure_death_state()["recovery"])
        self.assertFalse(s.ensure_death_state()["stable"])

    def test_healing_dead_guard_and_maximum_zero(self):
        s = self.unconscious()
        s.heal_player(3)
        self.assertEqual(s.world_state["player_combat_status"], "active")
        self.assertEqual(s.ensure_death_state()["failures"], 0)
        s.set_player_max_hp(0)
        self.assertTrue(s.ensure_death_state()["dead"])
        before = copy.deepcopy(s.character)
        with self.assertRaises(ValueError):
            s.heal_player(1)
        self.assertEqual(s.character, before)
        game._validate_save_payload(s.serialize_game_state())

    def test_npc_policy_and_historical_unconscious(self):
        s = death_fixtures.make_session()
        n = {"id": "victim", "current_hp": 3, "max_hp": 3, "combat_status": "active"}
        s.world_state["npcs"].append(n)
        s.apply_npc_damage(n, 3)
        self.assertEqual(n["combat_status"], "dead")
        old = {"id": "old", "current_hp": 0, "max_hp": 3, "combat_status": "unconscious"}
        s.world_state["npcs"].append(old)
        s.ensure_combat_state()
        self.assertEqual(old["combat_status"], "unconscious")

    def test_medicine_success_failure_and_stable_damage(self):
        for roll, stable in ((9, False), (10, True)):
            with self.subTest(roll=roll):
                s = self.unconscious()
                s.world_state["npcs"].append({
                    "id": "medic", "location": s.world_state["location"],
                    "current_hp": 5, "combat_status": "active", "medicine_bonus": 0,
                })
                with patch("game.roll_d20", return_value=roll):
                    result = s.attempt_player_stabilization("medic")
                self.assertEqual(result["success"], stable)
                self.assertEqual(s.ensure_death_state()["stable"], stable)
                self.assertEqual(s.character["current_hp"], 0)
                if stable:
                    s._apply_player_damage(20, took_damage=True)
                    self.assertTrue(s.ensure_death_state()["dead"])
                    self.assertIsNone(s.ensure_death_state()["recovery"])

    def test_noncombat_timing_and_natural_twenty(self):
        s = self.unconscious()
        with patch("game.roll_d20", return_value=20) as die:
            s.advance_campaign_time(5, "hazard_aftermath")
            self.assertEqual(die.call_count, 0)
            s.advance_campaign_time(1, "hazard_aftermath")
            self.assertEqual(die.call_count, 1)
            s.advance_campaign_time(60, "wait")
            self.assertEqual(die.call_count, 1)
        self.assertEqual(s.character["current_hp"], 1)
        self.assertTrue(s.ensure_death_state()["prone"])

    def test_recovery_on_all_existing_duration_sources(self):
        for reason in ("wait", "travel", "rest", "task", "combat_round"):
            with self.subTest(reason=reason):
                s = self.unconscious()
                with patch.object(s.rng, "randint", return_value=1):
                    s.stabilize_player()
                s.advance_campaign_time(3600, reason)
                self.assertEqual(s.character["current_hp"], 1)
                self.assertIsNone(s.ensure_death_state()["recovery"])

    def test_inner_radiance_uses_policy_a(self):
        s = death_fixtures.make_session()
        s.character.update(species="Aasimar", race="Aasimar")
        s.initialize_species_trait_state()
        state = s._species_trait_state()
        state.update(active_celestial_form="inner_radiance", celestial_revelation_turns_remaining=10)
        n = {"id": "radiance-target", "current_hp": 1, "max_hp": 1,
             "combat_status": "active", "location": s.world_state["location"]}
        s.world_state["npcs"].append(n)
        s._finish_species_player_turn()
        self.assertEqual(n["combat_status"], "dead")

    def test_normal_rollback_preserves_consumed_rng_and_restores_time_inventory(self):
        s = death_fixtures.make_session()
        campaign_time.initialize(s.world_state)
        s.advance_campaign_time(12, "wait")
        inventory = copy.deepcopy(s.world_state["inventory"])
        s._capture_combat_death_checkpoint()
        s.world_state["inventory"].append("post-checkpoint reward")
        s.advance_campaign_time(8, "wait")
        s.rng.randint(1, 20)
        rng = s.rng.getstate()
        s._apply_player_damage(40, took_damage=True)
        self.assertEqual(s.rng.getstate(), rng)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 12)
        self.assertEqual(s.world_state["inventory"], inventory)

    def test_noncombat_episode_identity_survives_rewound_clock(self):
        s = death_fixtures.make_session()
        campaign_time.initialize(s.world_state)
        with patch("game.roll_d20", return_value=2) as die:
            for attempt in range(2):
                s._capture_combat_death_checkpoint()
                s._apply_player_damage(20, took_damage=True)
                s.ensure_death_state()["failures"] = 2
                s.advance_campaign_time(6, "wait")
                self.assertEqual(s.character["current_hp"], 20)
                self.assertEqual(die.call_count, attempt + 1)


class SaveDeleteTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown
    create_campaign = campaign_fixtures.CampaignApiTests.create_campaign

    async def test_selected_delete_cascade_restart_repeat_and_stale_session(self):
        a, b = await self.create_campaign(), await self.create_campaign()
        record = self.manager.get(a["session_id"])
        import uuid
        action_id = str(uuid.uuid4())
        self.manager.autosave_turn(record, "test", "test", turn_action_receipt={
            "action_id": action_id, "request_hash": "a" * 64, "response": {"action_id": action_id},
        })
        response = await self.http.delete(f"/api/game/campaigns/{a['campaign_id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["deleted"])
        for suffix in ("", "/resume"):
            method = self.http.get if not suffix else self.http.post
            self.assertEqual((await method(f"/api/game/campaigns/{a['campaign_id']}{suffix}")).status_code, 404)
        self.assertEqual((await self.http.get(f"/api/game/sessions/{a['session_id']}/state")).status_code, 404)
        self.assertEqual((await self.http.post(f"/api/game/sessions/{a['session_id']}/turn", json={"message": "Bekle."})).status_code, 404)
        with self.assertRaises(Exception):
            self.manager.autosave_turn(record, "old", "old")
        again = await self.http.delete(f"/api/game/campaigns/{a['campaign_id']}")
        self.assertFalse(again.json()["deleted"])
        import sqlite3
        with sqlite3.connect(self.store.path) as connection:
            for table in ("campaign_history", "campaign_combat_history", "campaign_turn_actions"):
                self.assertEqual(connection.execute(
                    f"SELECT count(*) FROM {table} WHERE campaign_id=?", (a["campaign_id"],)
                ).fetchone()[0], 0)
        restarted = SessionManager(campaign_store=CampaignStore(self.store.path))
        self.assertEqual([c["campaign_id"] for c in restarted.list_campaigns()], [b["campaign_id"]])
        other = await self.http.get(f"/api/game/campaigns/{b['campaign_id']}")
        self.assertEqual(other.status_code, 200, other.text)

    async def test_failure_does_not_revoke_or_report_success(self):
        a = await self.create_campaign()
        with patch.object(self.store, "delete_campaign", side_effect=CampaignStorageError("failure")):
            response = await self.http.delete(f"/api/game/campaigns/{a['campaign_id']}")
        self.assertNotEqual(response.status_code, 200)
        self.manager.get(a["session_id"])
        self.assertEqual(len(self.manager.list_campaigns()), 1)

    async def test_unknown_and_death_never_delete(self):
        import uuid
        a = await self.create_campaign()
        response = await self.http.delete(f"/api/game/campaigns/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 200)
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            record = self.manager.get(a["session_id"])
            s = record.game_session
            s.character.update(max_hp=20, current_hp=20)
            s.world_state["player_combat_status"] = "active"
            s.world_state["death_state"] = game._death_state_defaults()
            s.ensure_death_state()["mode"] = mode
            if mode == "NORMAL":
                s._capture_combat_death_checkpoint()
            with patch.object(self.store, "delete_campaign", side_effect=AssertionError("death cannot delete")):
                s._apply_player_damage(40, took_damage=True)
                self.manager.save_campaign(a["campaign_id"])
            self.assertEqual(len(self.manager.list_campaigns()), 1)

    async def test_stable_resume_rng_and_http_replay_without_model(self):
        import uuid
        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        campaign_time.initialize(s.world_state)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        with patch.object(s.rng, "randint", return_value=1):
            s.stabilize_player()
        self.manager.save_campaign(a["campaign_id"])
        before = s.rng.getstate()
        restarted = SessionManager(campaign_store=CampaignStore(self.store.path))
        _, record, _, _, _ = restarted.resume_campaign(a["campaign_id"])
        self.assertEqual(record.game_session.rng.getstate(), before)
        self.assertEqual(record.game_session.ensure_death_state()["recovery"], s.ensure_death_state()["recovery"])
        self.app.state.ollama_adapter = None
        request = {"message": "1 saat bekle.", "action_id": str(uuid.uuid4())}
        url = f"/api/game/sessions/{a['session_id']}/turn"
        first = await self.http.post(url, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        snapshot = s.serialize_game_state()
        repeated = await self.http.post(url, json=request)
        self.assertEqual(repeated.json(), first.json())
        self.assertEqual(s.serialize_game_state(), snapshot)
        self.assertEqual(s.rng.getstate(), before)
        self.assertEqual(s.character["current_hp"], 1)

    async def test_death_save_natural_one_twenty_and_replay(self):
        import uuid
        for roll in (1, 20):
            with self.subTest(roll=roll):
                a = await self.create_campaign()
                s = self.manager.get(a["session_id"]).game_session
                s.ensure_death_state()["mode"] = "PERMADEATH"
                death_fixtures.start_test_combat(s)
                s._apply_player_damage(s.character["current_hp"], took_damage=True)
                self.app.state.ollama_adapter = None
                request = {"message": "Ölüm kurtarmasını bekliyorum.", "action_id": str(uuid.uuid4())}
                url = f"/api/game/sessions/{a['session_id']}/turn"
                with patch("game.roll_d20", return_value=roll) as die, patch(
                    "game.resolve_enemy_attack", return_value={"action": "enemy_attack", "outcome": "miss"}
                ):
                    first = await self.http.post(url, json=request)
                    self.assertEqual(first.status_code, 200, first.text)
                    calls = die.call_count
                    before = s.serialize_game_state(), s.rng.getstate()
                    repeated = await self.http.post(url, json=request)
                    self.assertEqual(repeated.json(), first.json())
                    self.assertEqual(die.call_count, calls)
                    self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)
                self.assertEqual(s.character["current_hp"], 1 if roll == 20 else 0)

    async def test_real_damage_at_zero_normal_rollback_and_receipt_replay(self):
        import uuid
        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        import bounded_encounter
        enemy = s.world_state["npcs"][-1]
        enemy.update(monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER),
                     speed_ft=30, faction="raiders", faction_relationships={"heroes": "enemy"})
        s.character["faction"] = "heroes"
        s.world_state["monster_perception"] = {enemy["id"]: {"player": {"visible": True}}}
        s.world_state["attack_environment"] = {"pairs": {
            enemy["id"] + "|player": {"distance_ft": 5, "attacker_sees_target": True,
                                     "target_sees_attacker": True},
        }}
        request = {"message": "Ölüm kurtarmasını bekliyorum.", "action_id": str(uuid.uuid4())}
        url = f"/api/game/sessions/{a['session_id']}/turn"
        with patch("game.roll_d20", return_value=9) as die, patch.object(
            s.rng, "randint", side_effect=[20, 20, 1, 1]
        ) as attack_dice:
            first = await self.http.post(url, json=request)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertTrue(s.ensure_death_state()["last_resolution"]["rolled_back"])
            before = s.serialize_game_state(), s.rng.getstate()
            repeated = await self.http.post(url, json=request)
            self.assertEqual(repeated.json(), first.json())
            self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)
            self.assertEqual(attack_dice.call_count, 4)
            self.assertEqual(die.call_count, 1)

    async def test_failed_fatal_turn_persistence_restores_engine_and_rng(self):
        import uuid
        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_combat_state()
        before = s.serialize_game_state(), s.rng.getstate()
        with patch("game.roll_d20", return_value=1), patch(
            "game.resolve_enemy_attack", return_value={"action": "enemy_attack", "outcome": "miss"}
        ), patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("failure")):
            response = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json={"message": "Ölüm kurtarmasını bekliyorum.", "action_id": str(uuid.uuid4())})
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)

    async def test_checkpoint_validation_precedes_all_mutation(self):
        a = await self.create_campaign()
        record = self.manager.get(a["session_id"])
        s = record.game_session
        s._capture_combat_death_checkpoint()
        s.world_state["death_state"]["combat_checkpoint"]["campaign_state"]["narrative_memory"] = []
        before = copy.deepcopy(s.world_state), copy.deepcopy(s.character), copy.deepcopy(record.journal), s.rng.getstate()
        with self.assertRaises(CampaignStorageError):
            s._restore_combat_death_checkpoint("test")
        self.assertEqual((s.world_state, s.character, record.journal, s.rng.getstate()), before)

    async def test_resume_death_states_and_counter_progress_without_load_rng(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for phase in ("unconscious", "stable", "dead", "one_failure", "two_successes"):
                with self.subTest(mode=mode, phase=phase):
                    a = await self.create_campaign()
                    s = self.manager.get(a["session_id"]).game_session
                    s.ensure_death_state()["mode"] = mode
                    campaign_time.initialize(s.world_state)
                    s._apply_player_damage(s.character["current_hp"], took_damage=True)
                    if phase == "stable":
                        s.stabilize_player()
                    elif phase == "dead":
                        s._apply_player_damage(s.character["max_hp"], took_damage=True)
                    elif phase == "one_failure":
                        s.ensure_death_state()["failures"] = 1
                    elif phase == "two_successes":
                        s.ensure_death_state()["successes"] = 2
                    self.manager.save_campaign(a["campaign_id"])
                    before_rng = s.rng.getstate()
                    before_death = copy.deepcopy(s.ensure_death_state())
                    restarted = SessionManager(campaign_store=CampaignStore(self.store.path))
                    _, record, _, _, _ = restarted.resume_campaign(a["campaign_id"])
                    self.assertEqual(record.game_session.rng.getstate(), before_rng)
                    self.assertEqual(record.game_session.ensure_death_state(), before_death)