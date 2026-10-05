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
                s.ensure_death_state().update(successes=1, failures=1)
                with patch("game.roll_d20", return_value=roll) as medicine:
                    result = s.attempt_player_stabilization("medic")
                self.assertEqual(medicine.call_count, 1)
                self.assertEqual(result["resolution"]["target_value"], 10)
                self.assertEqual(result["resolution"]["modifier_breakdown"]["ability_modifier"], 0)
                self.assertEqual(result["success"], stable)
                self.assertEqual(s.ensure_death_state()["stable"], stable)
                self.assertEqual(s.character["current_hp"], 0)
                self.assertEqual((s.ensure_death_state()["successes"], s.ensure_death_state()["failures"]),
                                 (0, 0) if stable else (1, 1))
                self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 0)
                if stable:
                    self.assertIsNotNone(s.ensure_death_state()["recovery"])
                    s._apply_player_damage(20, took_damage=True)
                    self.assertTrue(s.ensure_death_state()["dead"])
                    self.assertIsNone(s.ensure_death_state()["recovery"])
                else:
                    self.assertIsNone(s.ensure_death_state()["recovery"])
        for invalid in (
            {"current_hp": 0}, {"combat_status": "unconscious"},
            {"conditions": ["incapacitated"]}, {"hostile": True},
            {"location": "elsewhere"}, {"medicine_bonus": None},
        ):
            with self.subTest(ineligible_healer=invalid):
                s = self.unconscious()
                s.world_state["npcs"].append({
                    "id": "medic", "location": s.world_state["location"],
                    "current_hp": 5, "combat_status": "active", "medicine_bonus": 0, **invalid,
                })
                before = s.serialize_game_state(), s.rng.getstate()
                with patch("game.roll_d20", side_effect=AssertionError("Ineligible healer must not roll")):
                    with self.assertRaises(ValueError):
                        s.attempt_player_stabilization("medic")
                self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)
        for target in ("conscious", "dead"):
            with self.subTest(ineligible_target=target):
                s = self.unconscious()
                s.world_state["npcs"].append({
                    "id": "medic", "location": s.world_state["location"],
                    "current_hp": 5, "combat_status": "active", "medicine_bonus": 0,
                })
                if target == "conscious":
                    s.heal_player(1)
                else:
                    s.set_player_max_hp(0)
                before = s.serialize_game_state(), s.rng.getstate()
                with patch("game.roll_d20", side_effect=AssertionError("Ineligible target must not roll")):
                    with self.assertRaises(ValueError):
                        s.attempt_player_stabilization("medic")
                self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)

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

    async def test_third_success_stays_stable_on_http_replay_after_reopen(self):
        import uuid
        import httpx
        import action_economy as ae

        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state()["successes"] = 2
        self.assertFalse(s.ensure_death_state()["stable"])
        self.assertEqual(s.ensure_combat_state()["current_actor_id"], "player")
        before_combat = copy.deepcopy(s.ensure_combat_state())
        before_economy = copy.deepcopy(ae.ensure(s))
        self.app.state.ollama_adapter = None
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        url = f"/api/game/sessions/{a['session_id']}/turn"
        with patch("game.roll_d20", return_value=10) as die, patch(
            "game.resolve_enemy_attack",
            side_effect=AssertionError("New stability must stop enemy attacks"),
        ) as enemy_attack, patch(
            "game.advance_combat_turn",
            side_effect=AssertionError("New stability must preserve initiative"),
        ) as advance, patch(
            "game._mark_combat_action_used",
            side_effect=AssertionError("New stability must not consume an action"),
        ) as consume:
            first = await self.http.post(url, json=request)
            self.assertEqual(first.status_code, 200, first.text)
            die.assert_called_once_with()
            enemy_attack.assert_not_called()
            advance.assert_not_called()
            consume.assert_not_called()

        result = first.json()["combat_result"]
        self.assertEqual(result["action"], "death_save")
        self.assertEqual(result["outcome"], "stable")
        self.assertTrue(result["success"])
        self.assertEqual(result["death_save"]["roll"], 10)
        self.assertTrue(result["death_save"]["stable"])
        self.assertEqual(result["enemy_actions"], [])
        self.assertIsNone(result["enemy_action"])
        self.assertFalse(result["combat_ended"])
        self.assertTrue(s.ensure_death_state()["stable"])
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        for key in ("active", "current_actor_id", "initiative_order",
                    "initiative_results", "round", "current_turn_index", "actions_used"):
            self.assertEqual(s.ensure_combat_state()[key], before_combat[key], key)
        self.assertEqual(ae.ensure(s), before_economy)
        committed_state = copy.deepcopy(s.serialize_game_state())
        committed_rng = s.rng.getstate()
        receipt = copy.deepcopy(
            self.store.get_turn_action(a["campaign_id"], request["action_id"])
        )
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["response"], first.json())

        # A fresh store, manager, and HTTP app ensure replay is disk-backed,
        # not served from the original session's in-memory receipt cache.
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = campaign_fixtures.create_app(
            session_manager=reopened_manager, ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            restored = reopened_manager.get(session_id).game_session
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            stored_before_replay = reopened_store.get_campaign(a["campaign_id"])
            with patch.object(
                restored, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not run the engine"),
            ), patch(
                "game.roll_d20", side_effect=AssertionError("Replay must not reroll"),
            ), patch.object(
                restored.rng, "randint",
                side_effect=AssertionError("Replay must not roll any dice"),
            ), patch(
                "game.resolve_enemy_attack",
                side_effect=AssertionError("Replay must not attack"),
            ), patch(
                "game.advance_combat_turn",
                side_effect=AssertionError("Replay must not advance initiative"),
            ), patch(
                "game._mark_combat_action_used",
                side_effect=AssertionError("Replay must not consume an action"),
            ):
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=request,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**first.json(), "session_id": session_id})
            self.assertEqual(replay.json()["combat_result"]["enemy_actions"], [])
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            self.assertEqual(ae.ensure(restored), before_economy)
            self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                             stored_before_replay)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )

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

    async def test_natural_one_penalty_on_http_replay_after_reopen(self):
        import uuid
        import httpx
        import action_economy as ae

        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        s.ensure_death_state()["mode"] = "PERMADEATH"
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        self.assertEqual(s.ensure_death_state()["failures"], 0)
        self.assertEqual(s.ensure_combat_state()["current_actor_id"], "player")
        self.app.state.ollama_adapter = None
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        # Isolate one real death save: the enemy scheduler would otherwise
        # continue through further saves until revival, stability, or death.
        with patch("game.roll_d20", return_value=1) as die, patch(
            "game._resolve_enemy_turns_until_player", return_value=[],
        ) as scheduler:
            first = await self.http.post(
                f"/api/game/sessions/{a['session_id']}/turn", json=request,
            )
            self.assertEqual(first.status_code, 200, first.text)
            die.assert_called_once_with()
            scheduler.assert_called_once_with()

        result = first.json()["combat_result"]
        self.assertEqual(result["action"], "death_save")
        self.assertEqual(result["outcome"], "natural_1")
        self.assertFalse(result["success"])
        self.assertEqual(result["death_save"]["roll"], 1)
        self.assertFalse(result["combat_ended"])
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        self.assertEqual(s.ensure_death_state()["failures"], 2)
        self.assertFalse(s.ensure_death_state()["dead"])
        self.assertFalse(s.ensure_death_state()["stable"])
        committed_combat = copy.deepcopy(s.ensure_combat_state())
        committed_economy = copy.deepcopy(ae.ensure(s))
        committed_state = copy.deepcopy(s.serialize_game_state())
        committed_rng = s.rng.getstate()
        receipt = copy.deepcopy(
            self.store.get_turn_action(a["campaign_id"], request["action_id"])
        )
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["response"], first.json())

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = campaign_fixtures.create_app(
            session_manager=reopened_manager, ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            self.assertNotEqual(session_id, a["session_id"])
            restored = reopened_manager.get(session_id).game_session
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            stored_before_replay = reopened_store.get_campaign(a["campaign_id"])
            with patch.object(
                restored, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not run the engine"),
            ) as engine, patch(
                "game.roll_d20", side_effect=AssertionError("Replay must not reroll"),
            ) as reroll, patch.object(
                restored.rng, "randint",
                side_effect=AssertionError("Replay must not roll any dice"),
            ) as rng_roll, patch(
                "game.advance_combat_turn",
                side_effect=AssertionError("Replay must not advance initiative"),
            ) as advance, patch(
                "game._mark_combat_action_used",
                side_effect=AssertionError("Replay must not consume an action"),
            ) as consume, patch.object(
                reopened_store, "save_campaign",
                side_effect=AssertionError("Replay must not write the campaign"),
            ) as save:
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=request,
                )
                self.assertEqual(replay.status_code, 200, replay.text)
                for forbidden in (engine, reroll, rng_roll, advance, consume, save):
                    forbidden.assert_not_called()
            self.assertEqual(replay.json(), {**first.json(), "session_id": session_id})
            self.assertEqual(restored.character["current_hp"], 0)
            self.assertEqual(restored.world_state["player_combat_status"], "unconscious")
            self.assertEqual(restored.ensure_death_state()["failures"], 2)
            self.assertFalse(restored.ensure_death_state()["dead"])
            self.assertFalse(restored.ensure_death_state()["stable"])
            self.assertEqual(restored.ensure_combat_state(), committed_combat)
            self.assertEqual(ae.ensure(restored), committed_economy)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                             stored_before_replay)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )

    async def test_fatal_death_save_on_http_replay_after_reopen(self):
        import uuid
        import httpx

        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        s.ensure_death_state()["mode"] = "PERMADEATH"
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state()["failures"] = 2
        self.assertFalse(s.ensure_death_state()["dead"])
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        self.assertEqual(s.ensure_combat_state()["current_actor_id"], "player")
        before_rng = s.rng.getstate()
        self.app.state.ollama_adapter = None
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        # Consume the session's real RNG while guaranteeing one ordinary failure.
        # No enemy damage or later scheduled save may cause this death.
        with patch(
            "game.roll_d20", side_effect=lambda: s.rng.randint(2, 9),
        ) as die, patch(
            "game._resolve_enemy_turns_until_player",
            side_effect=AssertionError("Fatal save must stop the enemy scheduler"),
        ) as scheduler:
            first = await self.http.post(
                f"/api/game/sessions/{a['session_id']}/turn", json=request,
            )
            self.assertEqual(first.status_code, 200, first.text)
            die.assert_called_once_with()
            scheduler.assert_not_called()

        result = first.json()["combat_result"]
        expected_resolution = {
            "mode": "PERMADEATH", "outcome": "dead",
            "cause": "failed_death_saves", "rolled_back": False, "terminal": False,
        }
        self.assertEqual(first.json()["action_id"], request["action_id"])
        self.assertEqual(result["action"], "death_save")
        self.assertEqual(result["outcome"], "dead")
        self.assertFalse(result["success"])
        self.assertIn(result["death_save"]["roll"], range(2, 10))
        self.assertEqual(result["death_save"]["failures"], 3)
        self.assertTrue(result["death_save"]["dead"])
        self.assertEqual(result["death_resolution"], expected_resolution)
        self.assertEqual(result["death_save"]["death_resolution"], expected_resolution)
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["end_reason"], "player_dead")
        self.assertEqual(result["enemy_actions"], [])
        self.assertIsNone(result["enemy_action"])

        def assert_dead(owner):
            self.assertEqual(owner.character["current_hp"], 0)
            self.assertEqual(owner.world_state["player_combat_status"], "dead")
            death = owner.ensure_death_state()
            self.assertEqual(death["mode"], "PERMADEATH")
            self.assertEqual(death["failures"], 3)
            self.assertTrue(death["dead"])
            self.assertFalse(death["stable"])
            self.assertFalse(death["terminal"])
            self.assertEqual(death["last_resolution"], expected_resolution)
            self.assertEqual(death["last_death_save_result"], result["death_save"])
            self.assertFalse(owner.ensure_combat_state()["active"])
            self.assertEqual(owner.ensure_combat_state()["end_reason"], "player_dead")

        assert_dead(s)
        committed_state = copy.deepcopy(s.serialize_game_state())
        committed_rng = s.rng.getstate()
        self.assertNotEqual(committed_rng, before_rng)
        committed_campaign = self.store.get_campaign(a["campaign_id"])
        receipt = copy.deepcopy(
            self.store.get_turn_action(a["campaign_id"], request["action_id"])
        )
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["response"], first.json())

        # Reconstruct every owner so replay must retrieve a durable receipt.
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = campaign_fixtures.create_app(
            session_manager=reopened_manager, ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            self.assertNotEqual(session_id, a["session_id"])
            restored = reopened_manager.get(session_id).game_session
            assert_dead(restored)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            # Resume may update metadata, but cannot change accepted history.
            stored_before_replay = reopened_store.get_campaign(a["campaign_id"])
            self.assertEqual(stored_before_replay.history, committed_campaign.history)
            self.assertEqual(stored_before_replay.combat_history,
                             committed_campaign.combat_history)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )
            with patch.object(
                restored, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not run the engine"),
            ) as engine, patch(
                "game.roll_d20", side_effect=AssertionError("Replay must not reroll"),
            ) as reroll, patch.object(
                restored.rng, "randint",
                side_effect=AssertionError("Replay must not roll any dice"),
            ) as rng_roll, patch.object(
                reopened_store, "save_campaign",
                side_effect=AssertionError("Replay must not write the campaign"),
            ) as save:
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=request,
                )
                self.assertEqual(replay.status_code, 200, replay.text)
                for forbidden in (engine, reroll, rng_roll, save):
                    forbidden.assert_not_called()
            self.assertEqual(replay.json(), {**first.json(), "session_id": session_id})
            assert_dead(restored)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                             stored_before_replay)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )

    async def test_normal_fatal_death_save_rollback_on_http_replay_after_reopen(self):
        await self._assert_accepted_fatal_death_save_replay_after_reopen("NORMAL")

    async def test_ironman_fatal_death_save_terminal_on_http_replay_after_reopen(self):
        await self._assert_accepted_fatal_death_save_replay_after_reopen("IRONMAN")

    async def test_normal_fatal_death_save_conflict_after_reopen_preserves_rollback(self):
        await self._assert_accepted_fatal_death_save_replay_after_reopen(
            "NORMAL", reject_changed_message=True,
        )

    async def test_ironman_fatal_death_save_conflict_after_reopen_preserves_terminal_death(self):
        await self._assert_accepted_fatal_death_save_replay_after_reopen(
            "IRONMAN", reject_changed_message=True,
        )

    async def _assert_accepted_fatal_death_save_replay_after_reopen(
        self, mode, *, reject_changed_message=False,
    ):
        import random
        import uuid
        import httpx

        created = await self.http.post(
            "/api/game/campaigns", json={"death_mode": mode},
        )
        self.assertEqual(created.status_code, 200, created.text)
        a = created.json()
        s = self.manager.get(a["session_id"]).game_session
        campaign_time.initialize(s.world_state)
        death_fixtures.start_test_combat(s)
        checkpoint = copy.deepcopy(s.ensure_death_state()["combat_checkpoint"])
        self.assertEqual(checkpoint is not None, mode == "NORMAL")
        s.world_state["inventory"].append("post-checkpoint reward")
        s.advance_campaign_time(18, "wait")
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state()["failures"] = 2
        self.assertFalse(s.ensure_death_state()["dead"])
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        self.assertEqual(s.ensure_combat_state()["current_actor_id"], "player")
        expected_rng = random.Random()
        expected_rng.setstate(s.rng.getstate())
        expected_roll = expected_rng.randint(2, 9)
        self.app.state.ollama_adapter = None
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        # Resolve the fatal save itself, not a later enemy's lethal damage.
        with patch(
            "game.roll_d20", side_effect=lambda: s.rng.randint(2, 9),
        ) as die, patch(
            "game._resolve_enemy_turns_until_player",
            side_effect=AssertionError("Fatal save must stop the enemy scheduler"),
        ) as scheduler:
            first = await self.http.post(
                f"/api/game/sessions/{a['session_id']}/turn", json=request,
            )
            self.assertEqual(first.status_code, 200, first.text)
            die.assert_called_once_with()
            scheduler.assert_not_called()

        result = first.json()["combat_result"]
        expected_resolution = {
            "mode": mode,
            "outcome": "rolled_back" if mode == "NORMAL" else "dead",
            "cause": "failed_death_saves",
            "rolled_back": mode == "NORMAL",
            "terminal": mode == "IRONMAN",
        }
        self.assertEqual(first.json()["action_id"], request["action_id"])
        self.assertEqual(result["action"], "death_save")
        self.assertEqual(result["outcome"], expected_resolution["outcome"])
        self.assertFalse(result["success"])
        self.assertEqual(result["death_save"]["roll"], expected_roll)
        self.assertEqual(result["death_save"]["failures"], 3)
        self.assertTrue(result["death_save"]["dead"])
        self.assertEqual(result["death_resolution"], expected_resolution)
        self.assertEqual(result["death_save"]["death_resolution"], expected_resolution)
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["enemy_actions"], [])
        self.assertIsNone(result["enemy_action"])

        def assert_mode_outcome(owner):
            death = owner.ensure_death_state()
            self.assertEqual(death["mode"], mode)
            self.assertEqual(death["last_resolution"], expected_resolution)
            self.assertEqual(death["last_death_save_result"], result["death_save"])
            self.assertEqual(death["dead"], mode == "IRONMAN")
            self.assertEqual(death["terminal"], mode == "IRONMAN")
            self.assertFalse(death["stable"])
            self.assertIsNone(death["combat_checkpoint"])
            self.assertFalse(owner.ensure_combat_state()["active"])
            if mode == "NORMAL":
                # Loading adds species defaults absent from the raw checkpoint.
                for field, value in checkpoint["player"].items():
                    self.assertEqual(owner.character[field], value, field)
                self.assertGreater(owner.character["current_hp"], 0)
                self.assertEqual(owner.world_state["player_combat_status"], "active")
                for field in ("inventory", "campaign_time"):
                    self.assertEqual(owner.world_state[field],
                                     checkpoint["world_state"][field], field)
            else:
                self.assertEqual(owner.character["current_hp"], 0)
                self.assertEqual(owner.world_state["player_combat_status"], "dead")
                self.assertEqual(death["failures"], 3)
                self.assertEqual(owner.ensure_combat_state()["end_reason"], "player_dead")
                self.assertEqual(result["end_reason"], "player_dead")
                self.assertIn("post-checkpoint reward", owner.world_state["inventory"])
                self.assertEqual(owner.world_state["campaign_time"]["elapsed_seconds"], 18)

        assert_mode_outcome(s)
        committed_state = copy.deepcopy(s.serialize_game_state())
        committed_rng = s.rng.getstate()
        self.assertEqual(committed_rng, expected_rng.getstate())
        committed_campaign = self.store.get_campaign(a["campaign_id"])
        self.assertEqual(len(committed_campaign.history), 1)
        self.assertEqual(len(committed_campaign.combat_history), 1)
        stored_entry = committed_campaign.combat_history[0]
        response_entry = first.json()["combat_history_entry"]
        for field in ("event_id", "turn_index"):
            self.assertEqual(stored_entry[field], response_entry[field], field)
        # HTTP models add optional defaults; storage keeps the engine's sparse
        # result. Compare the fatal outcome, then preserve the entire saved row.
        for field in ("action", "outcome", "death_save", "death_resolution"):
            self.assertEqual(stored_entry["result"][field], result[field], field)
        receipt = copy.deepcopy(
            self.store.get_turn_action(a["campaign_id"], request["action_id"])
        )
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["response"], first.json())

        # New persistence, session and HTTP owners must use the accepted receipt.
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = campaign_fixtures.create_app(
            session_manager=reopened_manager, ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            self.assertNotEqual(session_id, a["session_id"])
            restored = reopened_manager.get(session_id).game_session
            assert_mode_outcome(restored)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            # Resuming can refresh metadata, but not accepted history or receipts.
            stored_before_replay = reopened_store.get_campaign(a["campaign_id"])
            self.assertEqual(stored_before_replay.history, committed_campaign.history)
            self.assertEqual(stored_before_replay.combat_history,
                             committed_campaign.combat_history)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )
            if reject_changed_message:
                changed_request = {**request, "message": "1 saat bekle."}
                with patch.object(
                    restored, "run_player_turn",
                    side_effect=AssertionError("Conflict must not run the engine"),
                ) as engine, patch(
                    "game.roll_d20",
                    side_effect=AssertionError("Conflict must not reroll"),
                ) as reroll, patch.object(
                    restored.rng, "randint",
                    side_effect=AssertionError("Conflict must not roll any dice"),
                ) as rng_roll, patch.object(
                    reopened_store, "save_campaign",
                    side_effect=AssertionError("Conflict must not write the campaign"),
                ) as save:
                    rejected = await http.post(
                        f"/api/game/sessions/{session_id}/turn", json=changed_request,
                    )
                    self.assertEqual(rejected.status_code, 409, rejected.text)
                    self.assertEqual(rejected.json(), {"detail": {
                        "code": "action_id_conflict",
                        "message": "This action ID was already used for a different turn.",
                    }})
                    for forbidden in (engine, reroll, rng_roll, save):
                        forbidden.assert_not_called()
                assert_mode_outcome(restored)
                self.assertEqual(restored.serialize_game_state(), committed_state)
                self.assertEqual(restored.rng.getstate(), committed_rng)
                self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                                 stored_before_replay)
                self.assertEqual(
                    reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                    receipt,
                )
            with patch.object(
                restored, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not run the engine"),
            ) as engine, patch(
                "game.roll_d20", side_effect=AssertionError("Replay must not reroll"),
            ) as reroll, patch.object(
                restored.rng, "randint",
                side_effect=AssertionError("Replay must not roll any dice"),
            ) as rng_roll, patch.object(
                reopened_store, "save_campaign",
                side_effect=AssertionError("Replay must not write the campaign"),
            ) as save:
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=request,
                )
                self.assertEqual(replay.status_code, 200, replay.text)
                for forbidden in (engine, reroll, rng_roll, save):
                    forbidden.assert_not_called()
            self.assertEqual(replay.json(), {**first.json(), "session_id": session_id})
            assert_mode_outcome(restored)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                             stored_before_replay)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )

    async def test_natural_twenty_revival_on_http_replay_after_reopen(self):
        import uuid
        import httpx
        import action_economy as ae

        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        s.ensure_death_state()["mode"] = "PERMADEATH"
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state().update(successes=1, failures=1)
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        self.assertEqual(s.ensure_combat_state()["current_actor_id"], "player")
        before_combat = copy.deepcopy(s.ensure_combat_state())
        before_economy = copy.deepcopy(ae.ensure(s))
        self.app.state.ollama_adapter = None
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with patch("game.roll_d20", return_value=20) as die, patch(
            "game.resolve_enemy_attack",
            side_effect=AssertionError("Revival must not start enemy attacks"),
        ) as enemy_attack, patch(
            "game.advance_combat_turn",
            side_effect=AssertionError("Revival must preserve initiative"),
        ) as advance, patch(
            "game._mark_combat_action_used",
            side_effect=AssertionError("Revival must not consume an action"),
        ) as consume:
            first = await self.http.post(
                f"/api/game/sessions/{a['session_id']}/turn", json=request,
            )
            self.assertEqual(first.status_code, 200, first.text)
            die.assert_called_once_with()
            enemy_attack.assert_not_called()
            advance.assert_not_called()
            consume.assert_not_called()

        result = first.json()["combat_result"]
        self.assertEqual(result["action"], "death_save")
        self.assertEqual(result["outcome"], "revived")
        self.assertTrue(result["success"])
        self.assertEqual(result["death_save"]["roll"], 20)
        self.assertTrue(result["death_save"]["prone"])
        self.assertEqual(result["enemy_actions"], [])
        self.assertIsNone(result["enemy_action"])
        self.assertFalse(result["combat_ended"])
        self.assertEqual(s.character["current_hp"], 1)
        self.assertEqual(s.world_state["player_combat_status"], "active")
        self.assertTrue(s.ensure_death_state()["prone"])
        self.assertEqual(s.ensure_death_state()["successes"], 0)
        self.assertEqual(s.ensure_death_state()["failures"], 0)
        for key in ("active", "current_actor_id", "initiative_order",
                    "initiative_results", "round", "current_turn_index", "actions_used"):
            self.assertEqual(s.ensure_combat_state()[key], before_combat[key], key)
        self.assertEqual(ae.ensure(s), before_economy)
        committed_combat = copy.deepcopy(s.ensure_combat_state())
        committed_state = copy.deepcopy(s.serialize_game_state())
        committed_rng = s.rng.getstate()
        receipt = copy.deepcopy(
            self.store.get_turn_action(a["campaign_id"], request["action_id"])
        )
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["response"], first.json())

        # Reconstruct every HTTP/persistence owner so replay uses the saved receipt.
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = campaign_fixtures.create_app(
            session_manager=reopened_manager, ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            self.assertNotEqual(session_id, a["session_id"])
            restored = reopened_manager.get(session_id).game_session
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            stored_before_replay = reopened_store.get_campaign(a["campaign_id"])
            with patch.object(
                restored, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not run the engine"),
            ) as engine, patch(
                "game.roll_d20", side_effect=AssertionError("Replay must not reroll"),
            ) as reroll, patch.object(
                restored.rng, "randint",
                side_effect=AssertionError("Replay must not roll any dice"),
            ) as rng_roll, patch(
                "game.heal_player",
                side_effect=AssertionError("Replay must not heal again"),
            ) as healing, patch(
                "game.resolve_enemy_attack",
                side_effect=AssertionError("Replay must not attack"),
            ) as enemy_attack, patch.object(
                reopened_store, "save_campaign",
                side_effect=AssertionError("Replay must not write the campaign"),
            ) as save:
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=request,
                )
                self.assertEqual(replay.status_code, 200, replay.text)
                for forbidden in (engine, reroll, rng_roll, healing, enemy_attack, save):
                    forbidden.assert_not_called()
            self.assertEqual(replay.json(), {**first.json(), "session_id": session_id})
            self.assertEqual(restored.character["current_hp"], 1)
            self.assertEqual(restored.world_state["player_combat_status"], "active")
            self.assertTrue(restored.ensure_death_state()["prone"])
            self.assertEqual(restored.ensure_combat_state(), committed_combat)
            self.assertEqual(ae.ensure(restored), before_economy)
            self.assertEqual(restored.serialize_game_state(), committed_state)
            self.assertEqual(restored.rng.getstate(), committed_rng)
            self.assertEqual(reopened_store.get_campaign(a["campaign_id"]),
                             stored_before_replay)
            self.assertEqual(
                reopened_store.get_turn_action(a["campaign_id"], request["action_id"]),
                receipt,
            )

    async def test_real_damage_at_zero_normal_rollback_and_receipt_replay(self):
        import uuid
        a = await self.create_campaign()
        s = self.manager.get(a["session_id"]).game_session
        campaign_time.initialize(s.world_state)
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
        # The module d20 provider also feeds session-bound NPC attack rolls.
        # One failed death save, then the two real attack-resolution dice.
        # Damage uses real session RNG; observe it without replacing its results.
        with patch("game.roll_d20", side_effect=[9, 20, 20]) as d20, patch.object(
            s.rng, "randint", wraps=s.rng.randint
        ) as damage_dice, patch(
            "game._apply_player_damage", wraps=game._apply_player_damage
        ) as damage_owner, patch(
            "game._finalize_player_death", wraps=game._finalize_player_death
        ) as death_owner, patch(
            "game.advance_campaign_time", wraps=game.advance_campaign_time
        ) as time_owner:
            first = await self.http.post(url, json=request)
            self.assertEqual(first.status_code, 200, first.text)
            result = first.json()["combat_result"]
            self.assertEqual(result["death_save"]["roll"], 9)
            self.assertEqual(result["death_save"]["failures"], 1)
            self.assertEqual(len(result["enemy_actions"]), 1)
            attack = result["enemy_actions"][0]
            self.assertEqual(attack["actor"], enemy["id"])
            self.assertEqual(attack["target_id"], "player")
            self.assertEqual(attack["attack_rolls"], [20, 20])
            self.assertTrue(attack["critical"])
            self.assertEqual(attack["outcome"], "critical_hit")
            self.assertEqual(attack["target_hp_before"], 0)
            self.assertGreater(attack["damage"], 0)
            self.assertEqual(attack["hp_damage"], attack["damage"])
            self.assertEqual(d20.call_count, 3)
            self.assertEqual(damage_dice.call_count, 2)
            self.assertEqual(damage_dice.call_args_list, [unittest.mock.call(1, 4)] * 2)
            self.assertEqual(damage_owner.call_count, 1)
            self.assertTrue(damage_owner.call_args.kwargs["critical"])
            self.assertEqual(damage_owner.call_args.kwargs["resolved_damage"], attack["damage"])
            self.assertEqual(death_owner.call_count, 1)
            self.assertTrue(s.ensure_death_state()["last_resolution"]["rolled_back"])
            self.assertEqual(s.ensure_death_state()["last_resolution"]["cause"], "failed_death_saves")
            self.assertGreater(s.character["current_hp"], 0)
            self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 0)
            record = self.manager.get(a["session_id"])
            before = (
                s.serialize_game_state(), s.rng.getstate(), copy.deepcopy(record.journal),
                copy.deepcopy(record.narrative_memory), record.lore_authority.to_dict(),
                copy.deepcopy(record.turn_action_receipts), self.store.get_campaign(a["campaign_id"]),
            )
            calls = (d20.call_count, damage_dice.call_count, damage_owner.call_count,
                     death_owner.call_count, time_owner.call_count)
            repeated = await self.http.post(url, json=request)
            self.assertEqual(repeated.json(), first.json())
            self.assertEqual((
                s.serialize_game_state(), s.rng.getstate(), record.journal,
                record.narrative_memory, record.lore_authority.to_dict(),
                record.turn_action_receipts, self.store.get_campaign(a["campaign_id"]),
            ), before)
            self.assertEqual((d20.call_count, damage_dice.call_count, damage_owner.call_count,
                              death_owner.call_count, time_owner.call_count), calls)

    async def test_failed_fatal_turn_persistence_restores_engine_and_rng(self):
        await self._assert_failed_fatal_turn_retry(reopen_before_retry=False)

    async def test_failed_fatal_turn_retries_after_campaign_reopen(self):
        await self._assert_failed_fatal_turn_retry(reopen_before_retry=True)

    async def test_permadeath_failed_fatal_turn_retries_after_campaign_reopen(self):
        with patch.object(CampaignStore, "delete_campaign",
                          side_effect=AssertionError("Death cannot delete a campaign")) as delete:
            await self._assert_failed_fatal_turn_retry(
                reopen_before_retry=True, mode="PERMADEATH",
            )
            delete.assert_not_called()

    async def test_ironman_failed_fatal_turn_retries_after_campaign_reopen(self):
        with patch.object(CampaignStore, "delete_campaign",
                          side_effect=AssertionError("Death cannot delete a campaign")) as delete:
            await self._assert_failed_fatal_turn_retry(
                reopen_before_retry=True, mode="IRONMAN",
            )
            delete.assert_not_called()

    async def _assert_failed_fatal_turn_retry(self, *, reopen_before_retry, mode="NORMAL"):
        import uuid
        from api.lore_authority.models import CampaignLoreState

        a = await self.create_campaign()
        b = await self.create_campaign()
        record = self.manager.get(a["session_id"])
        other = self.manager.get(b["session_id"])
        s = record.game_session
        s.ensure_death_state()["mode"] = mode
        timestamp = "2026-01-01T00:00:00+00:00"
        quest_id = str(uuid.uuid4())
        record.journal["quests"].append({
            "quest_id": quest_id, "title": "Find the lost map",
            "description": "Recover the map before leaving town.",
            "status": "active", "giver_npc_id": None,
            "objectives": [{
                "objective_id": str(uuid.uuid4()),
                "description": "Find the map.", "status": "active",
            }],
            "created_at": timestamp, "updated_at": timestamp,
            "completed_at": None,
        })
        record.narrative_memory["quest_memory"][quest_id] = {
            "quest_id": quest_id, "title": "Find the lost map",
            "authority": "canonical",
        }
        record.narrative_memory["story_summary"]["player_history"] = [{
            "text": "The map is still missing.", "source": "player_message",
            "authority": "narrative_continuity",
        }]
        lore = record.lore_authority.to_dict()
        lore["player_known_fact_ids"] = ["fact:map:missing"]
        record.lore_authority = CampaignLoreState.from_mapping(lore)
        previous_action_id = str(uuid.uuid4())
        previous_receipt = {
            "action_id": previous_action_id, "request_hash": "a" * 64,
            "response": {"action_id": previous_action_id},
        }
        self.manager.autosave_turn(
            record, "Look for the map.", "The search continues.",
            turn_action_receipt=previous_receipt,
        )
        record.turn_action_receipts[previous_action_id] = copy.deepcopy(previous_receipt)
        death_fixtures.start_test_combat(s)
        checkpoint = copy.deepcopy(s.ensure_death_state()["combat_checkpoint"])
        if mode == "NORMAL":
            self.assertIsNotNone(checkpoint)
            checkpoint_campaign = checkpoint["campaign_state"]
        else:
            self.assertIsNone(checkpoint)

        # Progress earned after the checkpoint must survive a failed save,
        # and permanent-death modes must retain it after a successful death too.
        quest = record.journal["quests"][0]
        quest.update(status="completed", updated_at="2026-01-02T00:00:00+00:00",
                     completed_at="2026-01-02T00:00:00+00:00")
        quest["objectives"][0]["status"] = "completed"
        record.narrative_memory["story_summary"]["player_history"][0]["text"] = "The map was found."
        record.narrative_memory["quest_memory"][quest_id]["title"] = "The recovered map"
        lore["player_known_fact_ids"].append("fact:map:found")
        record.lore_authority = CampaignLoreState.from_mapping(lore)
        s.messages.append({"role": "user", "content": "I found the map."})
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state()["failures"] = 1
        s.ensure_combat_state()
        self.manager.save_campaign(a["campaign_id"])
        request = {
            "message": "Ölüm kurtarmasını bekliyorum.",
            "action_id": str(uuid.uuid4()),
        }

        def snapshot(managed):
            session = managed.game_session
            return copy.deepcopy({
                "engine": session.serialize_game_state(),
                "rng": session.rng.getstate(),
                "journal": managed.journal,
                "narrative_memory": managed.narrative_memory,
                "lore_authority": managed.lore_authority.to_dict(),
                "world_metadata": session.world_metadata,
                "messages": session.messages,
                "receipts": managed.turn_action_receipts,
                "combat_history": managed.combat_history,
                "stored_campaign": self.store.get_campaign(managed.campaign_id),
                "stored_receipt": self.store.get_turn_action(
                    managed.campaign_id, previous_action_id,
                ),
            })

        before, other_before = snapshot(record), snapshot(other)
        expected_campaign = checkpoint_campaign if mode == "NORMAL" else before
        if mode == "NORMAL":
            for field in ("journal", "narrative_memory", "lore_authority"):
                self.assertNotEqual(before[field], checkpoint_campaign[field], field)
        # A fatal attempt consumes exactly one real session RNG draw. Failed
        # persistence must restore it; retry consumes it once, replay not at all.
        import random
        expected_rng = random.Random()
        expected_rng.setstate(before["rng"])
        expected_rng.randint(1, 20)

        def assert_campaign_progress(managed):
            if mode == "NORMAL":
                for field in ("journal", "narrative_memory"):
                    self.assertEqual(getattr(managed, field), expected_campaign[field], field)
            else:
                # Terminal death legitimately adds a combat-ended event and
                # refreshes continuity, but must not rewind earned quest facts.
                for key, value in before["journal"].items():
                    if key != "notable_events":
                        self.assertEqual(managed.journal[key], value, key)
                events = managed.journal["notable_events"]
                earlier_events = before["journal"]["notable_events"]
                self.assertEqual(events[:-1], earlier_events)
                self.assertEqual(events[-1]["event_type"], "combat_ended")
                for key, value in before["narrative_memory"].items():
                    if key != "recent_turns":
                        self.assertEqual(managed.narrative_memory[key], value, key)
            self.assertEqual(managed.lore_authority.to_dict(), expected_campaign["lore_authority"])

        def fatal_roll(*args, **kwargs):
            # Exercise RNG restoration too, rather than a constant mock that
            # leaves the pre-request RNG unchanged.
            s.rng.randint(1, 20)
            return 1

        def fail_save(campaign_id, session, **kwargs):
            self.assertEqual(campaign_id, a["campaign_id"])
            self.assertIs(session, s)
            resolution = s.ensure_death_state()["last_resolution"]
            self.assertEqual(resolution["rolled_back"], mode == "NORMAL")
            self.assertEqual(resolution["mode"], mode)
            self.assertEqual(resolution["cause"], "failed_death_saves")
            if mode == "NORMAL":
                self.assertGreater(s.character["current_hp"], 0)
            else:
                self.assertTrue(s.ensure_death_state()["dead"])
                self.assertEqual(s.ensure_death_state()["terminal"], mode == "IRONMAN")
                self.assertEqual(s.character["current_hp"], 0)
                self.assertEqual(s.world_state["player_combat_status"], "dead")
            self.assertNotEqual(s.rng.getstate(), before["rng"])
            assert_campaign_progress(record)
            self.assertEqual(kwargs["journal"], record.journal)
            if mode == "NORMAL":
                self.assertEqual(kwargs["narrative_memory"], record.narrative_memory)
            else:
                # Persistence strips presentation narration from continuity.
                for key, value in record.narrative_memory.items():
                    if key != "recent_turns":
                        self.assertEqual(kwargs["narrative_memory"][key], value, key)
                self.assertEqual(
                    kwargs["narrative_memory"]["recent_turns"][-1]["player"],
                    request["message"],
                )
            self.assertEqual(kwargs["lore_authority"].to_dict(), expected_campaign["lore_authority"])
            self.assertEqual(kwargs["turn_action_receipt"]["action_id"], request["action_id"])
            raise CampaignStorageError("failure")

        with patch("game.roll_d20", side_effect=fatal_roll) as die, patch(
            "game.resolve_enemy_attack", return_value={"action": "enemy_attack", "outcome": "miss"}
        ), patch.object(self.store, "save_campaign", side_effect=fail_save) as save:
            response = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json=request)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "campaign_storage_unavailable")
        self.assertEqual(die.call_count, 1)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(snapshot(record), before)
        self.assertEqual(snapshot(other), other_before)
        for campaign_id in (a["campaign_id"], b["campaign_id"]):
            self.assertIsNone(self.store.get_turn_action(campaign_id, request["action_id"]))
        self.assertNotIn(request["action_id"], record.turn_action_receipts)

        session_id = a["session_id"]
        if reopen_before_retry:
            # Replace both the manager and HTTP app, so no in-memory recovery
            # from the failed request can supply the retried turn's state.
            import httpx
            from api.main import create_app

            original_record, original_session = record, s
            self.store = CampaignStore(self.store.path)
            self.manager = SessionManager(campaign_store=self.store)
            self.app = create_app(session_manager=self.manager, ollama_adapter=None)
            await self.http.aclose()
            self.http = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            )
            resumed = await self.http.post(
                f"/api/game/campaigns/{a['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = self.manager.get(session_id)
            s = record.game_session
            self.assertIsNot(record, original_record)
            self.assertIsNot(s, original_session)
            restored_before = snapshot(record)
            for field in (
                "engine", "rng", "journal", "narrative_memory",
                "lore_authority", "world_metadata", "combat_history",
                "stored_receipt",
            ):
                self.assertEqual(restored_before[field], before[field], field)
            # Resume may refresh metadata and rebuild transient model messages;
            # durable gameplay, history, and earlier receipts must not change.
            for field in ("payload", "history", "combat_history"):
                self.assertEqual(
                    getattr(restored_before["stored_campaign"], field),
                    getattr(before["stored_campaign"], field),
                    field,
                )
            self.assertEqual(s.ensure_death_state()["combat_checkpoint"], checkpoint)
            self.assertEqual(s.character["current_hp"], 0)
            self.assertEqual(s.ensure_death_state()["failures"], 1)
            self.assertEqual(s.ensure_death_state()["mode"], mode)
            self.assertFalse(s.ensure_death_state()["dead"])
            self.assertFalse(s.ensure_death_state()["terminal"])
            self.assertIsNone(s.ensure_death_state()["last_resolution"])
            self.assertIsNone(self.store.get_turn_action(a["campaign_id"], request["action_id"]))
            self.assertNotIn(request["action_id"], record.turn_action_receipts)
            self.assertEqual(snapshot(original_record)["engine"], before["engine"])

        previous_cached_receipt = copy.deepcopy(record.turn_action_receipts.get(previous_action_id))
        # Retry the identical request after removing the storage failure. The
        # real death owner must run once and commit the mode-specific result.
        url = f"/api/game/sessions/{session_id}/turn"
        with patch("game.roll_d20", side_effect=fatal_roll) as retry_die, patch(
            "game.resolve_enemy_attack",
            return_value={"action": "enemy_attack", "outcome": "miss"},
        ) as enemy_attack, patch(
            "game._restore_combat_death_checkpoint",
            wraps=game._restore_combat_death_checkpoint,
        ) as rollback, patch(
            "game._finalize_player_death", wraps=game._finalize_player_death,
        ) as death_owner, patch.object(
            self.store, "save_campaign", wraps=self.store.save_campaign,
        ) as committed_save:
            retried = await self.http.post(url, json=request)
            self.assertEqual(retried.status_code, 200, retried.text)
            self.assertEqual(retried.json()["action_id"], request["action_id"])
            self.assertEqual(retry_die.call_count, 1)
            if mode == "NORMAL":
                rollback.assert_called_once_with("failed_death_saves")
            else:
                rollback.assert_not_called()
                enemy_attack.assert_not_called()
            death_owner.assert_called_once_with("failed_death_saves")
            self.assertEqual(committed_save.call_count, 1)
            resolution = s.ensure_death_state()["last_resolution"]
            self.assertEqual(resolution["rolled_back"], mode == "NORMAL")
            self.assertEqual(resolution["mode"], mode)
            self.assertEqual(resolution["cause"], "failed_death_saves")
            self.assertEqual(s.ensure_death_state()["dead"], mode != "NORMAL")
            self.assertEqual(s.ensure_death_state()["terminal"], mode == "IRONMAN")
            self.assertIsNone(s.ensure_death_state()["combat_checkpoint"])
            if mode == "NORMAL":
                self.assertEqual(s.character["current_hp"], checkpoint["player"]["current_hp"])
            else:
                self.assertEqual(resolution["outcome"], "dead")
                self.assertEqual(s.character["current_hp"], 0)
                self.assertEqual(s.ensure_death_state()["failures"], 3)
                self.assertEqual(s.world_state["player_combat_status"], "dead")
                self.assertFalse(s.world_state["combat"]["active"])
            self.assertNotEqual(s.rng.getstate(), before["rng"])
            self.assertEqual(s.rng.getstate(), expected_rng.getstate())
            assert_campaign_progress(record)
            self.assertEqual(record.turn_action_receipts.get(previous_action_id), previous_cached_receipt)
            self.assertEqual(self.store.get_turn_action(a["campaign_id"], previous_action_id),
                             before["stored_receipt"])
            saved_receipt = self.store.get_turn_action(a["campaign_id"], request["action_id"])
            self.assertIsNotNone(saved_receipt)
            self.assertEqual(saved_receipt["response"], retried.json())

            # Reopen from disk to prove that the successful retry persisted the
            # mode outcome, rather than only repairing the active session.
            reopened = SessionManager(campaign_store=CampaignStore(self.store.path))
            _, restored, _, _, _ = reopened.resume_campaign(a["campaign_id"])
            self.assertEqual(restored.game_session.serialize_game_state(), s.serialize_game_state())
            self.assertEqual(restored.game_session.rng.getstate(), s.rng.getstate())
            for field in ("journal", "narrative_memory"):
                self.assertEqual(getattr(restored, field), getattr(record, field), field)
            self.assertEqual(restored.lore_authority.to_dict(), record.lore_authority.to_dict())
            self.assertEqual(
                {c["campaign_id"] for c in reopened.list_campaigns()},
                {a["campaign_id"], b["campaign_id"]},
            )
            self.assertEqual(snapshot(other), other_before)

            committed = snapshot(record)
            calls = (retry_die.call_count, enemy_attack.call_count, rollback.call_count,
                     death_owner.call_count, committed_save.call_count)
            with patch.object(s, "run_player_turn", side_effect=AssertionError("Replay ran the engine")):
                repeated = await self.http.post(url, json=request)
            self.assertEqual(repeated.status_code, 200, repeated.text)
            self.assertEqual(repeated.json(), retried.json())
            self.assertEqual(snapshot(record), committed)
            self.assertEqual(snapshot(other), other_before)
            self.assertEqual(self.store.get_turn_action(a["campaign_id"], request["action_id"]),
                             saved_receipt)
            self.assertEqual((retry_die.call_count, enemy_attack.call_count, rollback.call_count,
                              death_owner.call_count, committed_save.call_count), calls)

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