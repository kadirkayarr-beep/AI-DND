"""Resolution-boundary regressions for the AI-freedom first slice.

The slice lets the model resolve a described person (or propose a local one)
when Python's own name/alias resolution found nobody. That deferral must only
apply to dialogue-shaped input whose sole-NPC fallback was deliberately
postponed. It must not:

* turn a movement/door action into a conversation with the only visible person,
* turn an in-combat non-attack statement into an NPC clarification,
* spend a model call on a world-subject question Python already answers.

All scenes are controlled fiction; the model is a local mock.
"""

import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.tests import test_campaign_api as campaign_api
from api.tests import test_campaign_time as v1


def _intent_packet(**overrides):
    packet = {
        "intent": "narrative",
        "action": "",
        "target": {"type": "none", "reference": ""},
        "completion": "unclear",
        "confidence": 1.0,
    }
    packet.update(overrides)
    return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class EngineResolutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=11)
        self.session.world_state["location"] = "tavern"
        self.person = {
            "id": "npc_ilvara_boundary", "name": "Ilvara", "role": "kâtip",
            "location": "tavern", "personality": "", "appearance": "Mürekkep lekeli eldivenli",
            "relationship": "neutral", "knowledge": [], "memory": [],
        }
        self.session.world_state["npcs"] = [self.person]

    def test_greeting_the_only_visible_person_still_reaches_them(self):
        def fake_chat(**kwargs):
            packet = _intent_packet(intent="dialogue", action="dialogue")
            body = json.loads(packet["message"]["content"])
            if "narration" in kwargs["format"]["properties"]:
                body["narration"] = "Kâtip başını kaldırıp selamını alıyor."
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat):
            result = self.session.run_player_turn("Merhaba!", interaction_mode="say")
        self.assertEqual(result["action_result"].get("npc_id"), self.person["id"])

    def test_described_person_is_still_resolved_by_validated_model_choice(self):
        other = dict(self.person, id="npc_kord_boundary", name="Kord", role="hamal",
                     appearance="Omzunda halat taşıyan iri biri")
        self.session.world_state["npcs"].append(other)

        def fake_chat(**kwargs):
            body = json.loads(_intent_packet(
                intent="dialogue", action="dialogue",
                target={"type": "npc", "reference": "halatlı kişi",
                        "npc_id": other["id"], "evidence_quote": "halat taşıyan kişiye"},
            )["message"]["content"])
            if "narration" in kwargs["format"]["properties"]:
                body["narration"] = "Hamal yükünü indirip sana dönüyor."
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat):
            result = self.session.run_player_turn(
                "Omzunda halat taşıyan kişiye selam veriyorum.", interaction_mode="do"
            )
        self.assertEqual(result["action_result"].get("npc_id"), other["id"])
        self.assertEqual(len(self.session.world_state["npcs"]), 2)


def _scene_person(city_id):
    return {
        "id": "npc_ilvara_http_boundary", "name": "Ilvara", "role": "kâtip",
        "location": city_id, "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "combat_status": "active", "current_hp": 10, "status": "active",
    }


class HttpResolutionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    # Existing harness borrowed read-only; no test from that class is re-run here.
    asyncSetUp = campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_api.CampaignApiTests.asyncTearDown
    post_scene_turn = campaign_api.CampaignApiTests.post_scene_turn

    async def test_door_actions_beside_one_person_do_not_become_dialogue(self):
        # Opening itself is covered by the existing door lifecycle test; this
        # guards the routing boundary for other physical door phrasings.
        for phrase in ("Hanın kapısını açıyorum.", "Kapıyı aralıyorum."):
            with self.subTest(phrase=phrase):
                city_id, _, session, turn_url, _, door = (
                    await campaign_api.create_city_with_locked_tavern(self))
                person = _scene_person(city_id)
                session.world_state.setdefault("npcs", []).append(person)
                door["locked"] = False
                client = campaign_api.CapturingConversationContextClient()
                response = await self.post_scene_turn(turn_url, client, {
                    "message": phrase, "action_id": str(uuid4()),
                })
                self.assertEqual(response.status_code, 200, response.text[:300])
                outcome = response.json()["turn_outcome"]
                self.assertNotEqual(outcome.get("action"), "dialogue", outcome)
                self.assertIsNone(
                    session.world_state["flags"].get("active_npc_id"),
                    "A door action must not silently make the bystander the addressee.",
                )

    async def test_world_subject_question_to_present_person_spends_no_model_call(self):
        city_id, _, session, turn_url, _, _ = (
            await campaign_api.create_city_with_locked_tavern(self))
        session.world_state.setdefault("npcs", []).append(_scene_person(city_id))
        client = campaign_api.CapturingConversationContextClient()
        batches_before = len(client.message_batches)
        response = await self.post_scene_turn(turn_url, client, {
            "message": "Ilvara, Neverwinter'ı neden gizlice bir ejderha yönetiyor?",
            "action_id": str(uuid4()),
        })
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertEqual(len(client.message_batches), batches_before,
                         "Python-owned unverified lore must not reach the model.")
        self.assertNotIn("ejderha", response.json()["narration"].casefold())


class _NoIntentModel(v1.NoModel):
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return _intent_packet(intent="attack",
                              target={"type": "npc", "reference": "Rakip"})


class CombatResolutionBoundaryApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await v1.ClockApiTests.asyncSetUp(self)
        self.app.state.ollama_adapter = AuthenticatedOllamaAdapter(_NoIntentModel())
        self.enterContext(self.app.state.ollama_adapter.engine_binding())

    asyncTearDown = v1.ClockApiTests.asyncTearDown

    async def test_in_combat_non_attack_statement_is_not_an_npc_clarification(self):
        session = self.manager.get(self.sid).game_session
        rival = session.create_npc_from_ai(
            {"name": "Rakip", "role": "Guard", "location": "tavern"})
        rival.update(current_hp=40, max_hp=40, armor_class=20, hostile=True,
                     distance_ft=5, attack_damage_type="bludgeoning")
        session.world_state.setdefault("monster_perception", {})[rival["id"]] = {
            "player": {"visible": True}}
        if not session.find_weapon_in_inventory("Kılıç")[0]:
            session.world_state["inventory"].append({"name": "Kılıç"})
        with patch("game.roll_initiative_player", return_value=20), \
             patch("game.roll_initiative", return_value=1):
            session.start_combat(rival)
        self.assertGreaterEqual(len(session.active_npcs()), 2)
        combat = session.world_state["combat"]
        data = {
            "message": "Bir an durup nefesimi düzenliyorum.", "target_id": None,
            "action_id": str(uuid4()), "combat_id": combat["combat_id"],
            "combat_round": combat["round"],
            "combat_turn_index": combat["current_turn_index"],
        }
        record = self.manager.get(self.sid)
        before = copy.deepcopy((session.world_state, session.messages,
                                record.journal, record.combat_history))
        response = await self.http.post(
            f"/api/game/sessions/{self.sid}/turn", json=data)
        self.assertEqual(response.status_code, 400, response.text[:300])
        self.assertEqual((session.world_state, session.messages,
                          record.journal, record.combat_history), before)


if __name__ == "__main__":
    unittest.main()
