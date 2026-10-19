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
import npc_statements
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

    def test_described_person_dialogue_counts_intent_and_narration_calls(self):
        other = dict(self.person, id="npc_kord_call_count", name="Kord", role="hamal",
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

        with patch("game.ollama.chat", side_effect=fake_chat) as model:
            result = self.session.run_player_turn(
                "Omzunda halat taşıyan kişiye selam veriyorum.", interaction_mode="do"
            )
        self.assertEqual(result["action_result"].get("npc_id"), other["id"])
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(model.call_count, 2)
        self.assertEqual(telemetry["total_model_calls"], model.call_count, telemetry)
        self.assertEqual(telemetry["intent_model_calls"], 1, telemetry)
        self.assertEqual(telemetry["narration_model_calls"], 1, telemetry)
        self.assertIn("sana dönüyor", result["narration"])

    def test_described_person_promise_commits_and_narrates_within_budget(self):
        other = dict(self.person, id="npc_kord_promise", name="Kord", role="hamal",
                     appearance="Omzunda halat taşıyan iri biri")
        self.session.world_state["npcs"].append(other)
        message = "Omzunda halat taşıyan kişiye selam veriyorum. Sana söz veriyorum."

        def fake_chat(**kwargs):
            properties = kwargs["format"]["properties"]
            body = json.loads(_intent_packet(
                intent="dialogue", action="dialogue",
                target={"type": "npc", "reference": "halatlı kişi",
                        "npc_id": other["id"], "evidence_quote": "halat taşıyan kişiye"},
            )["message"]["content"])
            if "interaction" in properties:
                body["interaction"] = {
                    "operation": "promise", "quote": "Sana söz veriyorum.",
                    "privacy": "addressed",
                }
            if "narration" in properties:
                body["narration"] = "Kord sözünü duyunca dikkatle sana dönüyor."
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat) as model:
            result = self.session.run_player_turn(message, interaction_mode="do")
        action = result["action_result"]
        self.assertEqual(action.get("operation"), "promise", action)
        self.assertEqual(action.get("status"), "recorded", action)
        self.assertEqual(action.get("npc_id"), other["id"], action)
        commitments = self.session.world_state[game.interaction_adventure.KEY]["commitments"]
        self.assertEqual(len(commitments), 1)
        self.assertEqual(commitments[0]["npc_id"], other["id"])
        self.assertEqual(commitments[0]["quote"], "Sana söz veriyorum.")
        self.assertTrue(result["narration"].strip())
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(model.call_count, 2)
        self.assertEqual(telemetry["total_model_calls"], model.call_count, telemetry)


class ClaimAndBudgetBoundaryTests(unittest.TestCase):
    """Unverified past claims and the documented two-call turn budget."""

    def setUp(self):
        self.session = game.create_session(seed=17)
        self.session.world_state["location"] = "tavern"
        self.session.world_state["npcs"] = []
        self.session.world_state["flags"] = {
            "last_npc_id": None, "active_npc_id": None,
            "active_npc_until_turn": -1, "turn_index": 0,
        }

    def _person(self, **fields):
        person = {"relationship": "neutral", "memory": [], "knowledge": [],
                  "personality": "", "appearance": ""}
        person.update(fields)
        self.session.world_state["npcs"].append(person)
        return person

    def test_claim_about_named_absent_person_is_answered_by_python_without_model(self):
        # Alone, and with a visible bystander the model could otherwise pick.
        for bystander in (False, True):
            with self.subTest(bystander=bystander):
                self.setUp()
                if bystander:
                    self._person(id="npc_bystander_claim", name="Oswin", role="hamal",
                                 location="tavern", appearance="İri biri")
                self._assert_absent_claim_is_python_owned()

    def _assert_absent_claim_is_python_owned(self):
        tamsin = self._person(id="npc_tamsin_claim", name="Tamsin", role="kayıkçı",
                              location="forest")
        before = copy.deepcopy(self.session.world_state)
        with patch("game.ollama.chat", side_effect=AssertionError("no model call")) as model:
            result = self.session.run_player_turn("Tamsin bana gümüş pusuladan bahsetmişti.")
        action = result["action_result"]
        self.assertEqual(model.call_count, 0)
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
        self.assertEqual(action.get("status"), "unverified")
        self.assertFalse(action.get("success"))
        self.assertEqual(action.get("state_changes"), [])
        self.assertEqual(tamsin["memory"], [])
        self.assertEqual(tamsin["knowledge"], [])
        self.assertEqual(self.session.world_state["location"], before["location"])
        self.assertEqual([n["id"] for n in self.session.world_state["npcs"]],
                         [n["id"] for n in before["npcs"]])
        self.assertNotIn("pusula", result["narration"].casefold())

    def test_claim_about_described_present_person_still_lets_model_find_them(self):
        dwarf = self._person(id="npc_scarf_claim", name="Bruna", role="cüce tüccar",
                             location="tavern", appearance="Kırmızı atkılı kısa boylu cüce")
        self._person(id="npc_other_claim", name="Oswin", role="hamal",
                     location="tavern", appearance="Omzunda halat taşıyan iri biri")
        before_npcs = copy.deepcopy(self.session.world_state["npcs"])
        calls = []

        claim = "Kırmızı atkılıyla dün nehir hakkında konuşmuştuk, bana nehri anlatmıştı."

        def fake_chat(**kwargs):
            calls.append(sorted(kwargs["format"]["properties"]))
            body = json.loads(_intent_packet(
                intent="dialogue", action="dialogue",
                target={"type": "npc", "reference": "kırmızı atkılı",
                        "npc_id": dwarf["id"], "evidence_quote": "Kırmızı atkılı"},
            )["message"]["content"])
            if "narration" in kwargs["format"]["properties"]:
                body["narration"] = "Cüce kaşlarını çatıyor."
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat):
            result = self.session.run_player_turn(claim)
        action = result["action_result"]
        self.assertTrue(calls, "A described claimant may still be interpreted by the model.")
        self.assertEqual(action.get("npc_id"), dwarf["id"], action)
        self.assertEqual(action.get("status"), "unverified", action)
        self.assertFalse(action.get("success"))
        after = {n["id"]: n for n in self.session.world_state["npcs"]}
        self.assertEqual(len(after), len(before_npcs))
        for npc in before_npcs:
            self.assertEqual(after[npc["id"]]["knowledge"], npc["knowledge"])
        # The player's claim must not become the NPC's own recorded words.
        self.assertNotEqual(
            npc_statements.claim_support(
                self.session.world_state, after[dwarf["id"]], claim)["status"],
            "supported",
        )

    def test_unresolved_description_keeps_the_two_call_budget_and_reports_it(self):
        self._person(id="npc_budget_a", name="Bruna", role="cüce tüccar",
                     location="tavern", appearance="Kısa boylu cüce")
        self._person(id="npc_budget_b", name="Oswin", role="hamal",
                     location="tavern", appearance="İri biri")

        def fake_chat(**kwargs):
            body = json.loads(_intent_packet(intent="dialogue", action="dialogue")
                              ["message"]["content"])
            if "narration" in kwargs["format"]["properties"]:
                body.update(valid_response=True, narration="Kimse karşılık vermiyor.",
                            lore_claims=[], world_updates={})
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat) as model:
            result = self.session.run_player_turn(
                "Mavi pelerinli kişiye selam veriyorum.", interaction_mode="do")
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertLessEqual(model.call_count, 2)
        self.assertEqual(telemetry["total_model_calls"], model.call_count, telemetry)


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
