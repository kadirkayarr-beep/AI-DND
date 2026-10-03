"""PHB turn-resource invariants and the existing HTTP receipt transaction."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import action_economy as ae
from combat_lifecycle import CombatRequestError
from api.tests.test_combat_lifecycle import ready, CombatLifecycleApiTests
from api.tests.test_species_traits import make_session
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.tests.test_campaign_time import scene


def step(session, *steps):
    return session.run_player_turn("Doğrulanmış eylem.", combat_action={"steps": list(steps)}, action_id=str(uuid4()))


class ActionEconomyTests(unittest.TestCase):
    def setUp(self):
        self.s, self.n = ready()
        self.r = ae.ensure(self.s)["player"]

    def test_turn_start_base_action_and_no_automatic_bonus(self):
        self.assertFalse(self.r["base_action_spent"])
        self.assertFalse(ae.projection(self.s)["actors"]["player"]["bonus_action_available"])

    def test_readied_movement_respects_prone_cost_in_shared_ledger(self):
        self.s.character["conditions"] = ["prone"]
        self.prepare({"kind": "move", "distance_ft": 10})
        step(self.s, {"kind": "move", "distance_ft": 5})
        identity = self.r["opportunity"]["id"]
        step(self.s, {"kind": "react", "opportunity_id": identity})
        self.assertEqual(self.r["movement_used"], 30)
        self.assertEqual(self.r["ready_movement_grant"], 20)
        self.assertEqual(ae.projection(self.s)["actors"]["player"]["movement_remaining"], 20)

    def test_existing_stone_reaction_shares_single_reaction_resource(self):
        for spent in (False, True):
            s, npc = ready(make_session("Goliath", ancestry="stone"))
            s.resolve_species_trait_action("arm_giant_ancestry")
            s.advance_combat_turn()
            r = ae.ensure(s)["player"]
            r["reaction_spent"] = spent
            before = s.character["species_trait_state"]["giant_ancestry_uses_remaining"]
            with patch("game.roll_d20", return_value=20), patch("game.roll_damage", return_value=8), patch.object(s.rng, "randint", return_value=1):
                result = s.resolve_enemy_attack(npc)
            used = s.character["species_trait_state"]["giant_ancestry_uses_remaining"]
            self.assertEqual(used, before if spent else before - 1)
            self.assertTrue(r["reaction_spent"])
            self.assertEqual(any(x["trait"] == "stone_giant_ancestry" for x in result["species_effects"]), not spent)

    def test_unavailable_natural_action_does_not_ask_model_or_spend(self):
        before = copy.deepcopy(self.s.world_state)
        with self.assertRaises(CombatRequestError):
            self.s.run_player_turn("Dodge kullanıyorum.")
        self.assertEqual(self.s.world_state, before)

    def test_session_resources_and_triggers_are_isolated(self):
        other, _ = ready()
        before = copy.deepcopy(other.world_state)
        self.prepare()
        step(self.s, {"kind": "move", "distance_ft": 5})
        self.assertIsNotNone(self.r["opportunity"])
        self.assertEqual(other.world_state, before)

    def test_speed_change_recomputes_dash_budget_without_changing_base_speed(self):
        step(self.s, {"kind": "dash"})
        self.s.character["speed_penalty_ft"] = 10
        self.assertEqual(ae.projection(self.s)["actors"]["player"]["movement_remaining"], 40)
        step(self.s, {"kind": "move", "distance_ft": 40})
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "move", "distance_ft": 1})
        self.assertEqual(self.s.character.get("speed_ft", 30), 30)

    def test_incapacitated_npc_skips_action_and_player_can_end_turn(self):
        self.n["conditions"] = ["incapacitated"]
        self.s.character["conditions"] = ["stunned"]
        hp = self.s.character["current_hp"]
        step(self.s, {"kind": "end_turn"})
        self.assertEqual(self.s.character["current_hp"], hp)
        self.assertEqual(self.s.world_state["combat"]["current_actor_id"], "player")

    def test_attack_miss_consumes_action_without_ending_explicit_turn(self):
        with patch("game.roll_attack", return_value=1):
            result = step(self.s, {"kind": "attack", "target_id": self.n["id"]})
        self.assertEqual(result["action_result"]["economy_steps"][0]["result"]["outcome"], "miss")
        self.assertTrue(self.r["base_action_spent"])
        self.assertEqual(self.s.world_state["combat"]["round"], 1)
        self.assertEqual(self.s.world_state["campaign_time"]["elapsed_seconds"], 0)

    def test_invalid_requests_preserve_world_character_rng(self):
        cases = [
            {"kind": "attack", "target_id": "foreign"},
            {"kind": "move", "distance_ft": 1000},
            {"kind": "dash", "resource": "bonus"},
            {"kind": "react", "opportunity_id": "forged"},
            {"kind": "attack", "target_id": self.n["id"], "resource": "bonus"},
            {"kind": "magic"},
        ]
        for item in cases:
            before = copy.deepcopy((self.s.world_state, self.s.character, self.s.rng.getstate()))
            with self.assertRaises(CombatRequestError):
                step(self.s, item)
            self.assertEqual((self.s.world_state, self.s.character, self.s.rng.getstate()), before)

    def test_compound_invalid_request_rolls_back_prior_step(self):
        before = copy.deepcopy(self.s.world_state)
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "move", "distance_ft": 10}, {"kind": "attack", "target_id": "foreign"})
        self.assertEqual(self.s.world_state, before)

    def test_action_before_bonus_and_bonus_before_action(self):
        for first in ("attack", "species"):
            s, npc = ready(make_session("Orc"))
            order = [{"kind": "attack", "target_id": npc["id"]},
                     {"kind": "species", "ability": "adrenaline_rush"}]
            if first == "species":
                order.reverse()
            with patch("game.roll_attack", return_value=1):
                step(s, *order)
            r = ae.ensure(s)["player"]
            self.assertTrue(r["base_action_spent"])
            self.assertTrue(r["bonus_action_spent"])
            self.assertEqual(r["movement_available"], 60)

    def test_bonus_only_once_per_creature_turn(self):
        s, _ = ready(make_session("Orc"))
        step(s, {"kind": "species", "ability": "adrenaline_rush"})
        uses = s.character["species_trait_state"]["adrenaline_rush_uses_remaining"]
        with self.assertRaises(CombatRequestError):
            step(s, {"kind": "species", "ability": "adrenaline_rush"})
        self.assertEqual(s.character["species_trait_state"]["adrenaline_rush_uses_remaining"], uses)

    def test_move_attack_move_same_movement_ledger(self):
        with patch("game.roll_attack", return_value=1):
            step(self.s, {"kind": "move", "distance_ft": 10},
                 {"kind": "attack", "target_id": self.n["id"]},
                 {"kind": "move", "distance_ft": 5})
        self.assertEqual(self.r["movement_used"], 15)
        self.assertEqual(ae.projection(self.s)["actors"]["player"]["movement_remaining"], 15)
        self.assertEqual(self.s.character.get("speed_ft", 30), 30)

    def test_dash_extra_action_and_restricted_grants(self):
        ae.grant(self.s, "player", "test-rule", ["dash"])
        step(self.s, {"kind": "dash"}, {"kind": "dash"})
        self.assertEqual(self.r["movement_available"], 90)
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "attack", "target_id": self.n["id"]})
        self.assertEqual(self.r["additional_actions"][0]["remaining"], 0)

    def test_restricted_grant_cannot_be_spent_as_other_family(self):
        step(self.s, {"kind": "dash"})
        ae.grant(self.s, "player", "test-restricted", ["dash"])
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "attack", "target_id": self.n["id"]})
        self.assertEqual(ae.ensure(self.s)["player"]["additional_actions"][0]["remaining"], 1)

    def test_bonus_dash_uses_existing_orc_feature_not_invented_resource(self):
        s, _ = ready(make_session("Orc"))
        step(s, {"kind": "dash", "resource": "bonus"})
        self.assertEqual(ae.ensure(s)["player"]["movement_available"], 60)
        self.assertFalse(ae.ensure(s)["player"]["base_action_spent"])
        self.assertTrue(ae.ensure(s)["player"]["bonus_action_spent"])

    def test_multiple_attacks_one_action_with_movement_between(self):
        self.s.character["attacks_per_action"] = 2  # Engine-only future rule hook.
        with patch("game.roll_attack", return_value=1):
            result = step(self.s, {"kind": "attack", "target_id": self.n["id"]},
                          {"kind": "move", "distance_ft": 5},
                          {"kind": "continue_attack", "target_id": self.n["id"]})
        rows = result["action_result"]["economy_steps"]
        self.assertEqual([rows[0]["action_resource_cost"], rows[2]["action_resource_cost"]], [1, 0])
        self.assertEqual(self.r["attack_action"]["remaining_attacks"], 0)

    def test_no_ungranted_extra_attack_inside_action(self):
        with patch("game.roll_attack", return_value=1):
            step(self.s, {"kind": "attack", "target_id": self.n["id"]})
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "continue_attack", "target_id": self.n["id"]})

    def prepare(self, response=None, source="player"):
        return step(self.s, {"kind": "ready",
                            "trigger": {"event": "actor_moves", "actor_id": source},
                            "response": response or {"kind": "attack", "target_id": self.n["id"]}})

    def test_ready_consumes_action_and_stores_one_response(self):
        self.prepare()
        self.assertTrue(self.r["base_action_spent"])
        self.assertEqual(self.r["ready"]["response"]["target_id"], self.n["id"])
        self.assertFalse(self.r["reaction_spent"])

    def test_invalid_ready_trigger_or_bonus_response_does_not_mutate(self):
        for trigger, response in [
            ({"event": "imagined", "actor_id": self.n["id"]}, {"kind": "attack", "target_id": self.n["id"]}),
            ({"event": "actor_moves", "actor_id": "foreign"}, {"kind": "move", "distance_ft": 5}),
            ({"event": "actor_moves", "actor_id": self.n["id"]}, {"kind": "bonus", "ability": "dash"}),
        ]:
            before = copy.deepcopy(self.s.world_state)
            with self.assertRaises(CombatRequestError):
                step(self.s, {"kind": "ready", "trigger": trigger, "response": response})
            self.assertEqual(self.s.world_state, before)

    def test_ready_own_turn_trigger_and_reaction_miss_consumes_reaction(self):
        self.prepare()
        step(self.s, {"kind": "move", "distance_ft": 5})
        identity = self.r["opportunity"]["id"]
        with patch("game.roll_attack", return_value=1):
            step(self.s, {"kind": "react", "opportunity_id": identity})
        self.assertTrue(self.r["reaction_spent"])
        self.assertIsNone(self.r["ready"])
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "react", "opportunity_id": identity})

    def test_reaction_on_other_turn_and_correct_reset_boundary(self):
        self.n["speed_ft"] = 30
        self.prepare(source=self.n["id"])
        self.s.advance_combat_turn()
        ae.move(self.s, self.n["id"], 5)  # Actual authoritative movement event.
        identity = self.r["opportunity"]["id"]
        with patch("game.roll_attack", return_value=1):
            ae.react(self.s, identity)
        self.assertTrue(self.r["reaction_spent"])
        self.s.advance_combat_turn()
        self.assertFalse(self.r["reaction_spent"])
        self.assertEqual(self.s.world_state["combat"]["round"], 2)

    def test_round_change_does_not_reset_other_creatures_reaction(self):
        enemy = ae.ensure(self.s)[self.n["id"]]
        enemy["reaction_spent"] = True
        self.s.world_state["combat"]["round"] += 1
        self.assertTrue(enemy["reaction_spent"])
        ae.begin_turn(self.s, self.n["id"])
        self.assertFalse(enemy["reaction_spent"])

    def test_ready_movement_uses_same_ledger_and_does_not_change_speed(self):
        self.prepare({"kind": "move", "distance_ft": 10})
        step(self.s, {"kind": "move", "distance_ft": 5})
        identity = self.r["opportunity"]["id"]
        step(self.s, {"kind": "react", "opportunity_id": identity})
        self.assertEqual(self.r["movement_used"], 15)
        self.assertEqual(self.r["movement_available"], 40)
        self.assertEqual(self.s.character.get("speed_ft", 30), 30)

    def test_ready_expires_at_own_next_turn_not_round_change(self):
        self.prepare()
        self.s.advance_combat_turn()
        self.assertIsNotNone(self.r["ready"])
        self.s.advance_combat_turn()
        self.assertIsNone(self.r["ready"])

    def test_end_turn_resets_only_turn_resources(self):
        self.r["reaction_spent"] = True
        before_hp = self.s.character["current_hp"]
        with patch("game.roll_d20", return_value=1):
            step(self.s, {"kind": "end_turn"})
        self.assertFalse(self.r["base_action_spent"])
        self.assertFalse(self.r["reaction_spent"])
        self.assertEqual(self.s.character["current_hp"], before_hp)
        self.assertEqual(self.s.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_conditions_and_death_cannot_bypass_any_resource_path(self):
        for condition in ("incapacitated", "unconscious"):
            s, npc = ready()
            s.character["conditions"] = [condition]
            for command in [{"kind": "move", "distance_ft": 5}, {"kind": "dash"},
                            {"kind": "attack", "target_id": npc["id"]},
                            {"kind": "species", "ability": "adrenaline_rush"}]:
                before = copy.deepcopy((s.character, s.world_state))
                with self.assertRaises((CombatRequestError, ValueError)):
                    step(s, command)
                self.assertEqual((s.character, s.world_state), before)

    def test_movement_condition_speed_zero_and_prone(self):
        self.s.character["conditions"] = ["grappled"]
        with self.assertRaises(CombatRequestError):
            step(self.s, {"kind": "move", "distance_ft": 5})
        self.s.character["conditions"] = ["prone"]
        step(self.s, {"kind": "move", "distance_ft": 5})
        self.assertEqual(ae.ensure(self.s)["player"]["movement_used"], 10)

    def test_natural_and_structured_sequences_have_same_mechanics(self):
        s, npc = ready()
        with patch("game.roll_attack", return_value=1):
            step(self.s, {"kind": "move", "distance_ft": 10}, {"kind": "attack", "target_id": self.n["id"]})
            s.run_player_turn("Önce 10 feet geri çekilip sonra saldırıyorum.", target_id=npc["id"], action_id=str(uuid4()))
        self.assertEqual(ae.ensure(s)["player"], ae.ensure(self.s)["player"])

    def test_natural_ready_uses_authoritative_trigger_not_model(self):
        self.s.run_player_turn("Rakip hareket ederse Ready ile saldıracağım.", target_id=self.n["id"])
        self.assertTrue(self.r["base_action_spent"])
        self.assertIsNone(self.r["opportunity"])

    def test_spell_hook_preserves_metadata_without_spell_implementation(self):
        ae.prepare_spell_hook(self.s, "player", {"event": "actor_moves", "actor_id": "player"},
                              {"spell_id": "future-rule", "casting_action": "action", "concentration": "future-owner"})
        self.assertEqual(self.r["ready"]["spell_metadata"]["spell_id"], "future-rule")
        self.assertTrue(self.r["base_action_spent"])

    def test_save_resume_resources_not_refreshed(self):
        step(self.s, {"kind": "move", "distance_ft": 10}, {"kind": "dash"})
        self.r["reaction_spent"] = True
        state = self.s.serialize_game_state()
        other, _ = ready()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            other.load_game(path)
        self.assertEqual(other.world_state["combat"]["turn_resources"], self.s.world_state["combat"]["turn_resources"])


class ActionEconomyApiTests(unittest.IsolatedAsyncioTestCase):
    # Reuse temporary SQLite/client fixture, not the inherited combat test matrix.
    asyncSetUp = CombatLifecycleApiTests.asyncSetUp
    asyncTearDown = CombatLifecycleApiTests.asyncTearDown
    setup_combat = CombatLifecycleApiTests.setup_combat
    request = CombatLifecycleApiTests.request
    post = CombatLifecycleApiTests.post
    assert_rejected_unchanged = CombatLifecycleApiTests.assert_rejected_unchanged
    def command(self, session, npc, *steps):
        data = self.request(session, npc, message="Hamle.", target_id=None)
        data["combat_action"] = {"steps": list(steps)}
        return data

    async def test_economy_receipt_replay_and_conflicting_payload(self):
        session, npc = self.setup_combat()
        command = self.command(session, npc, {"kind": "move", "distance_ft": 10})
        first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy(session.world_state)
        replay = await self.post(command)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(session.world_state, before)
        changed = copy.deepcopy(command)
        changed["combat_action"]["steps"][0]["distance_ft"] = 15
        self.assertEqual((await self.post(changed)).status_code, 409)

    async def test_atomic_save_failure_restores_economy_and_receipt(self):
        session, npc = self.setup_combat()
        command = self.command(session, npc, {"kind": "move", "distance_ft": 10}, {"kind": "dash"})
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("controlled")):
            await self.assert_rejected_unchanged(session, command, 503)

    async def test_forged_client_grant_and_malformed_movement_rejected(self):
        session, npc = self.setup_combat()
        for bad in [{"kind": "dash", "grant": "Action Surge"},
                    {"kind": "move", "distance_ft": True}, {"kind": "move", "distance_ft": -1}]:
            await self.assert_rejected_unchanged(session, self.command(session, npc, bad), 422)

    async def test_invalid_sequence_does_not_create_history_or_time(self):
        session, npc = self.setup_combat()
        await self.assert_rejected_unchanged(session, self.command(session, npc,
            {"kind": "move", "distance_ft": 10}, {"kind": "attack", "target_id": "foreign"}), 400)

    async def test_campaign_resume_keeps_partial_turn_and_replay(self):
        session, npc = self.setup_combat()
        command = self.command(session, npc, {"kind": "move", "distance_ft": 10})
        response = await self.post(command)
        self.assertEqual(response.status_code, 200, response.text)
        manager = SessionManager(session_factory=scene, campaign_store=CampaignStore(self.store.path))
        _, restored, _, _, _ = manager.resume_campaign(self.created["campaign_id"])
        self.assertEqual(restored.game_session.world_state["combat"]["turn_resources"],
                         session.world_state["combat"]["turn_resources"])
        self.assertEqual(manager.get_turn_action(restored, command["action_id"])["response"]["combat_result"],
                         response.json()["combat_result"])

    async def test_authoritative_ready_interrupt_can_react_then_resume_once(self):
        session, npc = self.setup_combat()
        ready_command = self.command(session, npc, {"kind": "ready",
            "trigger": {"event": "actor_attacks", "actor_id": npc["id"]},
            "response": {"kind": "attack", "target_id": npc["id"]}})
        response = await self.post(ready_command)
        self.assertEqual(response.status_code, 200, response.text)
        with patch("game.roll_d20", return_value=1):
            end = await self.post(self.command(session, npc, {"kind": "end_turn"}))
        self.assertEqual(end.status_code, 200, end.text)
        self.assertEqual(session.world_state["combat"]["current_actor_id"], npc["id"])
        identity = ae.ensure(session)["player"]["opportunity"]["id"]
        react = self.command(session, npc, {"kind": "react", "opportunity_id": identity})
        with patch("game.roll_attack", return_value=1):
            done = await self.post(react)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
        before = copy.deepcopy(session.world_state)
        self.assertEqual((await self.post(react)).json(), done.json())
        self.assertEqual(session.world_state, before)