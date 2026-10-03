"""Focused lifecycle evidence; controlled mechanics, temporary campaign storage."""

import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import combat_lifecycle
import game
from api.serializers import serialize_session_state
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.tests import test_campaign_time as v1


class ControlledModel(v1.NoModel):
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": json.dumps({
            "intent": "attack", "target": {"type": "npc", "reference": "Rakip"},
            "dm_response": "Hamlenin sonucu bellidir.", "world_updates": {},
        })}}


def ready(session=None):
    session = session or v1.scene()
    npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
    npc.update(current_hp=40, max_hp=40, armor_class=20, hostile=True)
    if not session.find_weapon_in_inventory("Kılıç")[0]:
        session.world_state["inventory"].append({"name": "Kılıç"})
    with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
        session.start_combat(npc)
    return session, npc


class CombatLifecycleTests(unittest.TestCase):
    def test_existing_pronoun_target_resolution_is_not_blocked_or_mutating(self):
        session, npc = ready()
        session.world_state["flags"]["active_npc_id"] = npc["id"]
        before = copy.deepcopy(session.world_state)
        combat_lifecycle.validate_request(session, "Ona saldırıyorum.")
        self.assertEqual(session.world_state, before)

    def test_active_identity_is_required_not_repaired(self):
        session, _ = ready()
        session.world_state["combat"]["combat_id"] = None
        before = copy.deepcopy(session.world_state)
        with self.assertRaises(ValueError):
            session.ensure_combat_state()
        self.assertEqual(session.world_state, before)

    def test_current_actor_and_participant_identity_are_validated(self):
        for change in ("actor", "duplicate", "missing"):
            session, npc = ready()
            state = session.world_state["combat"]
            if change == "actor":
                state["current_actor_id"] = "foreign"
            elif change == "duplicate":
                session.world_state["npcs"].append(copy.deepcopy(npc))
            else:
                session.world_state["npcs"].remove(npc)
            with self.assertRaises(ValueError):
                session.ensure_combat_state()

    def test_direct_mechanic_rejects_nonparticipant_and_wrong_actor(self):
        session, npc = ready()
        other = session.create_npc_from_ai({"name": "Yolcu", "role": "Traveler", "location": "tavern"})
        before = session.rng.getstate()
        with self.assertRaises(combat_lifecycle.CombatRequestError):
            session.resolve_attack("saldırıyorum", "Kılıç", game.WEAPONS["Kılıç"], other)
        with self.assertRaises(combat_lifecycle.CombatRequestError):
            session.resolve_enemy_attack(npc)
        self.assertEqual(session.rng.getstate(), before)

    def test_hostility_threat_and_model_proposal_are_not_combat_triggers(self):
        session = v1.scene()
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc["hostile"] = True
        for text in ("Merhaba.", "Rakip'e saldırmakla tehdit ediyorum.", "Rakip'e saldırmıyorum.", "Rakip'e saldırsam?"):
            self.assertFalse(combat_lifecycle.is_attack_decision(session, text))
            if session._is_explicitly_negated_attack(text):
                session.execute_intent({"intent": "attack"}, text, npc)
            else:
                with self.assertRaises(combat_lifecycle.CombatRequestError):
                    session.execute_intent({"intent": "attack"}, text, npc)
            self.assertFalse(session.world_state["combat"]["active"])

    def test_closed_identity_is_retained_and_close_is_idempotent(self):
        session, npc = ready()
        identity = session.world_state["combat"]["combat_id"]
        before = session.world_state["campaign_time"]["elapsed_seconds"]
        first = session.end_combat("surrender")
        self.assertEqual(session.end_combat("different"), first)
        self.assertEqual(serialize_session_state(session)["combat"]["combat_id"], identity)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before)
        with self.assertRaises(combat_lifecycle.CombatRequestError):
            session.resolve_enemy_attack(npc)
        with self.assertRaises(combat_lifecycle.CombatRequestError):
            session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], npc)

    def test_round_boundary_and_partial_end_use_only_existing_time(self):
        session, _ = ready()
        identity = session.world_state["combat"]["combat_id"]
        session.advance_combat_turn()
        self.assertEqual(session.world_state["combat"]["round"], 1)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)
        session.advance_combat_turn()
        self.assertEqual(session.world_state["combat"]["round"], 2)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 6)
        self.assertEqual(session.world_state["combat"]["combat_id"], identity)
        session.end_combat("surrender")
        self.assertEqual(session.advance_combat_turn(), (False, None, False))
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_authoritative_npc_relocation_cannot_execute_a_stale_turn(self):
        session, npc = ready()
        npc["location"] = "forest"
        ended = session._combat_end_if_decided()
        self.assertEqual(ended["reason"], "opponents_relocated")
        self.assertFalse(session.world_state["combat"]["active"])
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)

    def test_zero_hp_uses_existing_death_state_and_keeps_combat(self):
        session, _ = ready()
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        session.ensure_death_state()["stable"] = False
        self.assertIsNone(session._combat_end_if_decided())
        self.assertTrue(session.world_state["combat"]["active"])
        self.assertTrue(session._combat_participant_can_act(session.ensure_combat_state(), "player"))

    def test_travel_cannot_teleport_out_of_active_combat(self):
        session, _ = ready()
        before = copy.deepcopy(session.world_state)
        with self.assertRaises(combat_lifecycle.CombatRequestError):
            session.execute_intent({"intent": "travel", "target": "forest"}, "Orman'a gidiyorum.")
        self.assertEqual(session.world_state, before)
        self.assertFalse(game.timed_gameplay.start_travel(session, "forest")["success"])


class CombatLifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await v1.ClockApiTests.asyncSetUp(self)
        self.app.state.ollama_adapter = AuthenticatedOllamaAdapter(ControlledModel())
        self.app.state.ollama_adapter.install_for_engine()
    asyncTearDown = v1.ClockApiTests.asyncTearDown

    def setup_combat(self):
        return ready(self.manager.get(self.sid).game_session)

    def request(self, session, npc, **changes):
        combat = session.world_state["combat"]
        value = {"message": "Rakip'e saldırıyorum.", "target_id": npc["id"],
                 "action_id": str(uuid4()), "combat_id": combat["combat_id"],
                 "combat_round": combat["round"], "combat_turn_index": combat["current_turn_index"]}
        value.update(changes)
        return value

    async def post(self, data, sid=None):
        return await self.http.post(f"/api/game/sessions/{sid or self.sid}/turn", json=data)

    async def assert_rejected_unchanged(self, session, data, status):
        record = self.manager.get(self.sid)
        before = copy.deepcopy((session.world_state, session.messages, record.journal, record.combat_history))
        rng = session.rng.getstate()
        response = await self.post(data)
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual((session.world_state, session.messages, record.journal, record.combat_history), before)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertIsNone(self.manager.get_turn_action(record, data["action_id"]))

    async def test_invalid_stale_and_malformed_requests_do_not_mutate(self):
        session, npc = self.setup_combat()
        other = session.create_npc_from_ai({"name": "Yolcu", "role": "Traveler", "location": "tavern"})
        for changes, status in (({"combat_id": str(uuid4())}, 409), ({"combat_round": 20}, 409),
                                ({"combat_turn_index": 1}, 409), ({"target_id": other["id"]}, 400),
                                ({"target_id": "foreign"}, 400), ({"actor_id": npc["id"]}, 422),
                                ({"combat_round": None}, 422), ({"combat_round": True}, 422),
                                ({"message": "Orman'a gidiyorum."}, 400)):
            await self.assert_rejected_unchanged(session, self.request(session, npc, **changes), status)

    async def test_wrong_actor_and_no_weapon_do_not_roll(self):
        session, npc = self.setup_combat()
        session.advance_combat_turn()
        await self.assert_rejected_unchanged(session, self.request(session, npc), 409)
        session.advance_combat_turn()
        session.world_state["inventory"] = []
        await self.assert_rejected_unchanged(session, self.request(session, npc), 400)

    async def test_valid_miss_is_canonical_and_replay_survives_resume(self):
        session, npc = self.setup_combat()
        identity = session.world_state["combat"]["combat_id"]
        command = self.request(session, npc)
        with patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
            first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()["combat_result"]
        self.assertEqual(result["outcome"], "miss")
        self.assertFalse(result["success"])
        self.assertEqual(result["combat_id"], identity)
        self.assertEqual(result["actor"], "player")
        self.assertEqual(len(self.app.state.ollama_adapter._client.calls), 1)
        self.assertEqual(result["target_hp_before"], result["target_hp_after"])
        self.assertEqual(first.json()["state"]["combat"]["round"], 2)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 6)
        before = copy.deepcopy(session.world_state)
        with patch("game.roll_attack", side_effect=AssertionError("replay must not roll")):
            replay = await self.post(command)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(session.world_state, before)
        conflict = await self.post(dict(command, message="Farklı hamle."))
        self.assertEqual(conflict.status_code, 409)
        restarted = SessionManager(session_factory=v1.scene, campaign_store=CampaignStore(self.store.path))
        sid, restored, _, _, _ = restarted.resume_campaign(self.created["campaign_id"])
        self.assertEqual(restored.game_session.world_state["combat"]["combat_id"], identity)
        self.assertEqual(restored.game_session.world_state["combat"]["round"], 2)
        self.assertEqual(restored.game_session.world_state["campaign_time"]["elapsed_seconds"], 6)
        self.assertEqual(restored.combat_history[0]["result"]["combat_id"], identity)
        self.assertEqual(restarted.get_turn_action(restored, command["action_id"])["response"]["combat_result"], result)
        self.assertNotEqual(sid, self.sid)

    async def test_verified_hit_end_preserves_history_without_extra_time(self):
        session, npc = self.setup_combat()
        identity = session.world_state["combat"]["combat_id"]
        command = self.request(session, npc)
        with patch("game.roll_attack", return_value=20), patch("game.roll_damage", return_value=100):
            response = await self.post(command)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["combat_result"]
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["target_hp_after"], 0)
        self.assertEqual(result["target_status"], "unconscious")
        self.assertEqual(result["combat_id"], identity)
        self.assertFalse(response.json()["state"]["combat"]["active"])
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 0)
        record = self.manager.get(self.sid)
        self.assertEqual(len(record.combat_history), 1)
        with patch("game.roll_attack", side_effect=AssertionError("closed retry must replay")):
            replay = await self.post(command)
        self.assertEqual(replay.json(), response.json())
        await self.assert_rejected_unchanged(session, dict(command, action_id=str(uuid4())), 409)
        self.assertEqual(len(record.combat_history), 1)

    async def test_persistence_failure_rolls_back_result_history_rng_and_time(self):
        session, npc = self.setup_combat()
        command = self.request(session, npc)
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("test")), \
             patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
            await self.assert_rejected_unchanged(session, command, 503)
        calls = self.app.state.ollama_adapter._client.calls
        self.assertEqual(len(calls), 1)
        self.assertNotIn("target_hp_after", json.dumps(calls))

    async def test_model_combat_proposal_cannot_create_a_result_or_advance_combat(self):
        session, npc = self.setup_combat()
        command = self.request(session, npc, message="Düşüncelerimi toparlıyorum.", target_id=None)
        await self.assert_rejected_unchanged(session, command, 400)

    async def test_player_attack_starts_authoritative_combat_with_npc_first(self):
        session = self.manager.get(self.sid).game_session
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=40, max_hp=40, armor_class=20)
        data = {"message": "Rakip'e saldırıyorum.", "target_id": npc["id"], "action_id": str(uuid4())}
        with patch("game.roll_initiative_player", return_value=1), patch("game.roll_initiative", return_value=20), \
             patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
            response = await self.post(data)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["combat_result"]
        self.assertTrue(result["combat_started"])
        self.assertEqual(result["combat_id"], response.json()["state"]["combat"]["combat_id"])
        self.assertTrue(result["enemy_actions"])
        self.assertTrue(all(a["actor"] == npc["id"] for a in result["enemy_actions"]))

    async def test_cross_session_combat_context_is_rejected(self):
        session, npc = self.setup_combat()
        foreign_sid, record = self.manager.create()
        foreign, enemy = ready(record.game_session)
        response = await self.post(self.request(session, npc), foreign_sid)
        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(foreign.world_state["combat"]["combat_id"], session.world_state["combat"]["combat_id"])
        self.assertEqual(foreign.world_state["combat"]["round"], 1)