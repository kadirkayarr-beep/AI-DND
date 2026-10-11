"""Production source integration: no injected statblock/perception/route maps.

All encounters enter through the normal creation/turn APIs. Negative owner
checks invalidate canonical state; they do not supply replacement geometry.
"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import action_economy
import bounded_encounter as owner
import living_world
import monster_perception
import weapon_attack
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from dictionaries(item)
    elif isinstance(value, list):
        for item in value:
            yield from dictionaries(item)


class NativeBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "campaigns.sqlite3"
        self.manager = SessionManager(campaign_store=CampaignStore(self.path))
        self.client = TestClient(create_app(session_manager=self.manager, ollama_adapter=None))
        options = self.client.get("/api/campaign-start-options").json()["settings"][0]
        region = options["regions"][0]
        self.start = {
            "setting_id": options["setting_id"], "region_pack_id": region["region_pack_id"],
            "region_id": region["region_id"],
            "starting_location_id": region["starting_locations"][0]["entity_id"],
        }
        self.campaign = self.create_campaign()
        self.sid = self.campaign["session_id"]

    def create_campaign(self):
        response = self.client.post("/api/campaigns", json={
            "name": "Disposable bounded integration", "campaign_start": self.start,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @property
    def session(self):
        # Read-only evidence; no campaign mechanics are injected.
        return self.manager.get(self.sid).game_session

    def call(self, message, steps=None, action_id=None):
        body = {"message": message, "action_id": str(action_id or uuid4())}
        if steps is not None:
            state_response = self.client.get(f"/api/sessions/{self.sid}/state")
            self.assertEqual(state_response.status_code, 200, state_response.text)
            state = state_response.json()
            combat = state["combat"]
            body.update(
                combat_action={"steps": steps}, combat_id=combat["combat_id"],
                combat_round=combat["round"], combat_turn_index=combat["current_turn_index"],
            )
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return body, response.json()

    def enter(self):
        return self.call(owner.ENTER)[1]

    def begin(self):
        return self.call(owner.START)[1]

    def walk_to_contact(self):
        self.enter()
        result = self.begin()
        if not any(d.get("action") == "monster_dash" for d in dictionaries(result)):
            _, result = self.call("Turumu bitiriyorum", [{"kind": "end_turn"}])
        self.assertTrue(any(d.get("action") == "monster_dash" for d in dictionaries(result)))
        return result

    def canonical(self):
        return copy.deepcopy((self.session.serialize_game_state(),
                              self.session.rng.getstate()))


class ProductionOwnerIntegrationTests(NativeBase):
    def test_definition_is_not_campaign_canon_before_entry(self):
        self.assertNotIn("bounded_encounter", self.session.world_state)
        self.assertFalse(any(n.get("monster_stat_block_id") == owner.STATBLOCK_ID
                             for n in self.session.world_state["npcs"]))
        self.assertFalse(self.session.world_state["combat"]["active"])

    def test_source_verified_commoner_attaches_by_explicit_id(self):
        self.enter()
        state = self.session.world_state["bounded_encounter"]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == state["npc_id"])
        self.assertEqual(npc["monster_stat_block_id"], "mm2024.commoner")
        self.assertEqual(npc["monster_stat_block"], owner.COMMONER)
        self.assertEqual((npc["armor_class"], npc["max_hp"], npc["speed_ft"]), (10, 4, 30))
        self.assertEqual(npc["monster_stat_block"]["source"], owner.SOURCE)
        self.assertEqual(npc["monster_stat_block"]["abilities"]["dexterity"], 10)
        self.assertIsNone(npc["monster_stat_block"]["multiattack"])
        self.assertEqual(npc["monster_stat_block"]["limited_resources"], [])
        self.assertEqual(npc["monster_stat_block"]["recharge_resources"], [])

    def test_enter_does_not_force_combat(self):
        self.enter()
        self.assertFalse(self.session.world_state["combat"]["active"])
        self.assertEqual(self.session.world_state["scene_state"]["player_position"]["bounded_node_id"],
                         "courtyard_entry")

    def test_directional_pair_and_perception_come_from_nodes(self):
        self.enter()
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        pair = weapon_attack.pair(self.session, actor, "player")
        self.assertEqual(pair["distance_ft"], 60)
        self.assertTrue(pair["attacker_sees_target"])
        self.assertTrue(self.session.world_state["monster_perception"][actor]["player"]["visible"])
        self.assertEqual(self.session.world_state["monster_routes"][actor][0]["distance_ft"], 55)

    def test_route_updates_position_and_existing_action_budget(self):
        result = self.walk_to_contact()
        self.assertIn("5 feet", result["narration"])
        self.assertIn("koşarak yer değiştirir", result["narration"])
        self.assertNotIn("Python", result["narration"])
        state = self.session.world_state["bounded_encounter"]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == state["npc_id"])
        budget = self.session.world_state["combat"]["turn_resources"][npc["id"]]
        self.assertEqual(npc["position"], "courtyard_near")
        self.assertEqual(weapon_attack.pair(self.session, npc["id"], "player")["distance_ft"], 5)
        self.assertEqual(budget["movement_used"], 55)
        self.assertEqual(budget["dash_count"], 1)
        combat = self.session.world_state["combat"]
        # An enemy-first encounter is still in round one; a player-first
        # encounter has rolled over after the enemy Dash. Only the base Action
        # marker resets at that boundary, not the enemy's movement evidence.
        self.assertIn(combat["round"], (1, 2))
        self.assertEqual(budget["base_action_spent"], combat["round"] == 1)
        self.assertEqual(budget["base_action_spent"], npc["id"] in combat["actions_used"])

    def test_visible_descriptor_and_dash_never_reveal_hidden_identity(self):
        entered = self.enter()
        npc = next(n for n in self.session.world_state["npcs"]
                   if n["id"] == self.session.world_state["bounded_encounter"]["npc_id"])
        self.assertIn(living_world.public_npc_name(npc), entered["narration"])
        before = self.canonical()
        self.assertEqual(owner.visible_dash_narration(self.session, {"outcome": "hit", "actor": npc["id"]}), "")
        self.assertEqual(owner.visible_dash_narration(self.session, {"outcome": "dash", "actor": "missing"}), "")
        self.assertEqual(before, self.canonical())
        npc["hidden"] = True
        self.assertEqual(owner.visible_dash_narration(self.session, {"outcome": "dash", "actor": npc["id"]}), "")

    def test_repeat_entry_does_not_heal_or_respawn(self):
        self.enter()
        before = self.canonical()[0]
        self.enter()
        after = self.canonical()[0]
        self.assertEqual(before["world_state"]["npcs"], after["world_state"]["npcs"])
        self.assertEqual(before["world_state"]["bounded_encounter"], after["world_state"]["bounded_encounter"])

    def test_separate_campaigns_do_not_share_scenario_state(self):
        other = self.create_campaign()
        self.enter()
        other_session = self.manager.get(other["session_id"]).game_session
        self.assertNotIn("bounded_encounter", other_session.world_state)
        self.assertFalse(other_session.world_state["combat"]["active"])

    def test_turkish_uppercase_and_ascii_commands_are_native(self):
        self.call("AVLU KARŞILAŞMASINA GİR")
        self.assertIn("bounded_encounter", self.session.world_state)
        self.call("avlu catismasini baslat")
        self.assertTrue(self.session.world_state["combat"]["active"])


class OwnerUncertaintyTests(NativeBase):
    """Negative/fault checks, not claimed as HTTP encounter acceptance."""
    def test_unlocated_player_movement_cannot_keep_stale_geometry(self):
        self.enter()
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        living_world.set_player_position(self.session.world_state, self.start["starting_location_id"], "standing")
        owner.refresh(self.session)
        self.assertNotIn(actor, self.session.world_state["monster_routes"])
        self.assertNotIn(actor, self.session.world_state["monster_perception"])
        with self.assertRaisesRegex(Exception, "distance"):
            weapon_attack.pair(self.session, actor, "player")

    def test_budget_only_move_invalidates_endpoint_instead_of_inventing_one(self):
        self.enter()
        self.begin()
        self.call("Biraz ilerliyorum", [{"kind": "move", "distance_ft": 5}])
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        self.assertNotIn("bounded_node_id", self.session.world_state["scene_state"]["player_position"])
        self.assertNotIn(actor, self.session.world_state["monster_routes"])

    def test_canonical_blinded_condition_does_not_gain_visibility(self):
        self.enter()
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == actor)
        npc.setdefault("conditions", []).append("blinded")
        owner.refresh(self.session)
        self.assertFalse(weapon_attack.pair(self.session, actor, "player")["attacker_sees_target"])
        self.assertNotIn(actor, self.session.world_state["monster_routes"])
        self.assertTrue(weapon_attack.pair(self.session, "player", actor)["attacker_sees_target"])

    def test_unknown_npc_node_does_not_reset_to_start(self):
        self.enter()
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        next(n for n in self.session.world_state["npcs"] if n["id"] == actor).pop("position")
        owner.refresh(self.session)
        self.assertNotIn(actor, self.session.world_state["monster_routes"])
        self.assertNotIn(f"{actor}|player", self.session.world_state["attack_environment"]["pairs"])


class HttpPersistenceAcceptanceTests(NativeBase):
    def test_normal_http_target_attack_and_resource_result(self):
        self.walk_to_contact()
        _, result = self.call("Turumu bitiriyorum", [{"kind": "end_turn"}])
        attack = next(d for d in dictionaries(result) if d.get("action") == "enemy_attack")
        self.assertEqual(attack["target_id"], "player")
        self.assertEqual(attack["weapon_id"], "commoner_club")
        self.assertEqual(attack["attack_bonus"], 2)
        self.assertEqual(attack["damage_type"], "bludgeoning")
        self.assertIn(attack["outcome"], ("hit", "miss", "critical_hit"))
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        combat = self.session.world_state["combat"]
        self.assertEqual(combat["current_actor_id"], "player")
        expected_spent = combat["initiative_order"].index(actor) < combat["current_turn_index"]
        self.assertEqual(combat["turn_resources"][actor]["base_action_spent"], expected_spent)
        self.assertEqual(actor in combat["actions_used"], expected_spent)

    def test_save_resume_after_process_restart_retains_all_canonical_state(self):
        self.walk_to_contact()
        self.call("Turumu bitiriyorum", [{"kind": "end_turn"}])
        before = self.canonical()
        response = self.client.post(f"/api/campaigns/{self.campaign['campaign_id']}/save")
        self.assertEqual(response.status_code, 200, response.text)
        # New manager/app reads the same production persistence owner.
        self.manager = SessionManager(campaign_store=CampaignStore(self.path))
        self.client = TestClient(create_app(session_manager=self.manager, ollama_adapter=None))
        response = self.client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume")
        self.assertEqual(response.status_code, 200, response.text)
        self.sid = response.json()["session_id"]
        self.assertEqual(before, self.canonical())

    def test_receipt_replay_after_restart_has_no_second_rng_or_state_mutation(self):
        self.walk_to_contact()
        body, original = self.call("Turumu bitiriyorum", [{"kind": "end_turn"}])
        before = self.canonical()
        self.assertEqual(self.client.post(f"/api/campaigns/{self.campaign['campaign_id']}/save").status_code, 200)
        self.manager = SessionManager(campaign_store=CampaignStore(self.path))
        self.client = TestClient(create_app(session_manager=self.manager, ollama_adapter=None))
        self.sid = self.client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume").json()["session_id"]
        # LLM message buffers are intentionally ephemeral in the existing save
        # owner. Canonical state/RNG survive; replay must not modify the fresh
        # process's buffer or append persistent history a second time.
        resumed_messages = copy.deepcopy(self.session.messages)
        history_before = self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json()["history"]
        replay = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        original["session_id"] = self.sid
        self.assertEqual(replay.json(), original)
        self.assertEqual(self.canonical(), before)
        self.assertEqual(self.session.messages, resumed_messages)
        self.assertEqual(self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json()["history"],
                         history_before)

    def test_action_id_conflict_is_not_a_second_turn(self):
        self.enter()
        body, _ = self.call(owner.START)
        before = self.canonical()
        body["message"] = "Farklı bir hamle"
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(before, self.canonical())

    def test_unrelated_free_text_still_requires_existing_model_service(self):
        before = self.canonical()
        response = self.client.post(f"/api/sessions/{self.sid}/turn", json={"message": "Etrafa bakıyorum"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(before, self.canonical())


class MovementRegressionBase(NativeBase):
    def assert_geometry_unknown(self):
        world = self.session.world_state
        actor = world["bounded_encounter"]["npc_id"]
        self.assertNotIn("bounded_node_id", world["scene_state"]["player_position"])
        self.assertNotIn(actor, world["monster_routes"])
        self.assertNotIn(actor, world["monster_perception"])
        self.assertNotIn(f"{actor}|player", world["attack_environment"]["pairs"])
        self.assertNotIn(f"player|{actor}", world["attack_environment"]["pairs"])
        self.assertIsNone(owner.public_projection(self.session)["visible_opponent"])
        for observer, target in ((actor, "player"), ("player", actor)):
            with self.assertRaisesRegex(Exception, "distance"):
                weapon_attack.pair(self.session, observer, target)
        owner.refresh(self.session)
        self.assertNotIn(actor, world["monster_perception"])
        self.assertNotIn(f"{actor}|player", world["attack_environment"]["pairs"])

    def assert_saved_replay(self, body, original, *, species_endpoint=False):
        before = self.canonical()
        self.assertEqual(self.client.post(
            f"/api/campaigns/{self.campaign['campaign_id']}/save"
        ).status_code, 200)
        self.manager = SessionManager(campaign_store=CampaignStore(self.path))
        self.client = TestClient(create_app(session_manager=self.manager, ollama_adapter=None))
        response = self.client.post(f"/api/campaigns/{self.campaign['campaign_id']}/resume")
        self.assertEqual(response.status_code, 200, response.text)
        self.sid = response.json()["session_id"]
        self.assertEqual(before, self.canonical())
        self.assert_geometry_unknown()
        history = self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json()["history"]
        messages = copy.deepcopy(self.session.messages)
        endpoint = "species-actions" if species_endpoint else "turn"
        replay = self.client.post(f"/api/sessions/{self.sid}/{endpoint}", json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), dict(original, session_id=self.sid))
        self.assertEqual(before, self.canonical())
        self.assertEqual(messages, self.session.messages)
        self.assertEqual(history, self.client.get(
            f"/api/campaigns/{self.campaign['campaign_id']}"
        ).json()["history"])


class ReadiedMovementRegressionTests(MovementRegressionBase):
    def prepare_movement(self):
        self.walk_to_contact()
        actor = self.session.world_state["bounded_encounter"]["npc_id"]
        self.call("Hareket için hazırlanıyorum", [{
            "kind": "ready", "trigger": {"event": "actor_attacks", "actor_id": actor},
            "response": {"kind": "move", "distance_ft": 10},
        }])
        self.call("Turumu bitiriyorum", [{"kind": "end_turn"}])
        return action_economy.ensure(self.session)["player"]["opportunity"]["id"]

    def test_http_readied_move_invalidates_geometry_and_survives_resume_replay(self):
        identity = self.prepare_movement()
        body, result = self.call("Tepkimi kullanıyorum", [{
            "kind": "react", "opportunity_id": identity,
        }])
        reaction = result["combat_result"]["economy_steps"][0]["response"]
        self.assertEqual(reaction, {"kind": "move", "distance_ft": 10, "movement_cost_ft": 10})
        self.assert_geometry_unknown()
        self.assert_saved_replay(body, result)

    def test_invalid_reaction_does_not_invalidate_geometry_or_spend_resources(self):
        self.prepare_movement()
        before = self.canonical()
        with self.assertRaisesRegex(Exception, "matching"):
            action_economy.execute(self.session, {"steps": [{
                "kind": "react", "opportunity_id": "not-the-opportunity",
            }]})
        self.assertEqual(before, self.canonical())
        self.assertIn("bounded_node_id", self.session.world_state["scene_state"]["player_position"])

    def test_failed_compound_reaction_restores_geometry_resources_and_rng(self):
        identity = self.prepare_movement()
        before = self.canonical()
        with self.assertRaises(Exception):
            action_economy.execute(self.session, {"steps": [
                {"kind": "react", "opportunity_id": identity},
                {"kind": "attack", "target_id": "foreign"},
            ]})
        self.assertEqual(before, self.canonical())

    def test_newly_unavailable_readied_movement_keeps_known_geometry(self):
        identity = self.prepare_movement()
        # Negative fixture: the actor becomes unable to move after readying.
        self.session.character.setdefault("conditions", []).append("grappled")
        before = self.canonical()
        with self.assertRaisesRegex(Exception, "movement"):
            action_economy.execute(self.session, {"steps": [
                {"kind": "react", "opportunity_id": identity},
            ]})
        self.assertEqual(before, self.canonical())


class CloudJauntRegressionTests(MovementRegressionBase):
    def create_campaign(self):
        # Normal character choices, not injected species/resources/geometry.
        response = self.client.post("/api/campaigns", json={
            "name": "Disposable Cloud Goliath regression", "campaign_start": self.start,
            "character": {
                "mode": "custom", "name": "Cloud traveller", "species": "Goliath",
                "giant_ancestry": "cloud", "class": "Fighter", "background": "Soldier",
                "alignment": "Neutral Good", "ability_score_method": "standard_array",
                "ability_scores": {"strength": 15, "dexterity": 14, "constitution": 13,
                                   "wisdom": 12, "intelligence": 10, "charisma": 8},
                "background_ability_bonuses": {"strength": 2, "constitution": 1},
                "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival"],
                "fighting_style": "Defense", "equipment_package": "A",
                "background_equipment_option": "A",
                "languages": ["Common", "Dwarvish", "Elvish"],
            },
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_structured_cloud_jaunt_invalidates_geometry_and_preserves_budgets(self):
        self.walk_to_contact()
        uses = self.session.character["species_trait_state"]["giant_ancestry_uses_remaining"]
        budget = copy.deepcopy(action_economy.ensure(self.session)["player"])
        body, result = self.call("Işınlanıyorum", [{"kind": "species", "ability": "cloud_jaunt"}])
        after = action_economy.ensure(self.session)["player"]
        self.assertTrue(after["bonus_action_spent"])
        self.assertEqual(after["base_action_spent"], budget["base_action_spent"])
        self.assertEqual(after["movement_used"], budget["movement_used"])
        self.assertEqual(self.session.character["species_trait_state"]["giant_ancestry_uses_remaining"],
                         uses - 1)
        self.assert_geometry_unknown()
        self.assert_saved_replay(body, result)

    def test_species_endpoint_outside_combat_also_invalidates_geometry(self):
        self.enter()
        body = {"action": "cloud_jaunt", "action_id": str(uuid4())}
        uses = self.session.character["species_trait_state"]["giant_ancestry_uses_remaining"]
        response = self.client.post(f"/api/sessions/{self.sid}/species-actions", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.character["species_trait_state"]["giant_ancestry_uses_remaining"],
                         uses - 1)
        self.assertFalse(self.session.world_state["combat"]["active"])
        self.assert_geometry_unknown()
        self.assert_saved_replay(body, response.json(), species_endpoint=True)

    def test_unavailable_cloud_jaunt_preserves_known_geometry_and_resources(self):
        self.walk_to_contact()
        # Negative fixture: consume the shared Bonus Action, not the teleport.
        action_economy.use_species_bonus(self.session, "cloud_jaunt")
        before = self.canonical()
        with self.assertRaises(Exception):
            action_economy.execute(self.session, {"steps": [
                {"kind": "species", "ability": "cloud_jaunt"},
            ]})
        self.assertEqual(before, self.canonical())
        self.assertIn("bounded_node_id", self.session.world_state["scene_state"]["player_position"])

    def test_exhausted_cloud_jaunt_does_not_invalidate_geometry(self):
        self.enter()
        # Negative fixture only: exhaust uses, never supply geometry.
        self.session.character["species_trait_state"]["giant_ancestry_uses_remaining"] = 0
        before = self.canonical()
        response = self.client.post(f"/api/sessions/{self.sid}/species-actions", json={
            "action": "cloud_jaunt", "action_id": str(uuid4()),
        })
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(before, self.canonical())

    def test_compound_failure_restores_cloud_jaunt_anchor_and_use(self):
        self.walk_to_contact()
        before = self.canonical()
        with self.assertRaises(Exception):
            action_economy.execute(self.session, {"steps": [
                {"kind": "species", "ability": "cloud_jaunt"},
                {"kind": "attack", "target_id": "foreign"},
            ]})
        self.assertEqual(before, self.canonical())

    def test_cloud_jaunt_without_bounded_binding_does_not_change_world_or_rng(self):
        world = copy.deepcopy(self.session.world_state)
        rng = self.session.rng.getstate()
        response = self.client.post(f"/api/sessions/{self.sid}/species-actions", json={
            "action": "cloud_jaunt", "action_id": str(uuid4()),
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(world, self.session.world_state)
        self.assertEqual(rng, self.session.rng.getstate())


if __name__ == "__main__":
    unittest.main()
