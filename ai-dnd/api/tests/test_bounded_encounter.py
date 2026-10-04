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
        self.walk_to_contact()
        state = self.session.world_state["bounded_encounter"]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == state["npc_id"])
        budget = self.session.world_state["combat"]["turn_resources"][npc["id"]]
        self.assertEqual(npc["position"], "courtyard_near")
        self.assertEqual(weapon_attack.pair(self.session, npc["id"], "player")["distance_ft"], 5)
        self.assertEqual(budget["movement_used"], 55)
        self.assertEqual(budget["dash_count"], 1)
        self.assertTrue(budget["base_action_spent"])

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
        self.assertTrue(self.session.world_state["combat"]["turn_resources"][actor]["base_action_spent"])

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


if __name__ == "__main__":
    unittest.main()