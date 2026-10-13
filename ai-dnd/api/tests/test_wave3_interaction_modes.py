from __future__ import annotations



import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.schemas import TurnRequest
from api.serializers import serialize_session_state
from api.session_manager import SessionManager


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Wave 3 deterministic contract test called the model")


class Wave3InteractionModeApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SessionManager()
        self.adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(self.adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=self.adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]
        self.session = self.manager.get(self.session_id).game_session

    async def asyncTearDown(self):
        await self.http.aclose()

    def test_turn_request_accepts_only_supported_modes(self):
        for mode in ("say", "do", "ask_dm", None):
            request = TurnRequest(message="test", interaction_mode=mode)
            self.assertEqual(request.interaction_mode, mode)
        with self.assertRaises(ValidationError):
            TurnRequest(message="test", interaction_mode="chat")

    async def test_ask_dm_ignores_client_npc_target_before_engine_routing(self):
        original_plan = self.session.plan_living_world_turn
        captured = {}

        def capture_plan(message, target_id=None, interaction_mode=None):
            captured["plan_target_id"] = target_id
            captured["plan_mode"] = interaction_mode
            return original_plan(
                message, target_id=target_id, interaction_mode=interaction_mode
            )

        self.session.plan_living_world_turn = capture_plan
        response = await self.http.post(
            f"/api/game/sessions/{self.session_id}/turn",
            json={
                "message": "Envanterimde neler var?",
                "interaction_mode": "ask_dm",
                "target_id": "npc_forged",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Envanter", response.json()["narration"])
        self.assertIsNone(captured["plan_target_id"])
        self.assertEqual(captured["plan_mode"], "ask_dm")


    async def test_say_target_is_validated_by_python_and_returned_as_active_conversation(self):
        world = self.session.world_state
        npc = {
            "id": "npc_wave3_guide",
            "name": "Liora",
            "role": "Yolcu",
            "location": world["location"],
            "tags": [],
            "name_known_to_player": False,
            "role_known_to_player": True,
        }
        world["npcs"].append(npc)
        response = await self.http.post(
            f"/api/game/sessions/{self.session_id}/turn",
            json={
                "message": "Ad\u0131n ne?",
                "interaction_mode": "say",
                "target_id": npc["id"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("Liora", payload["narration"])
        self.assertTrue(npc["name_known_to_player"])
        self.assertTrue(payload["state"]["conversation"]["active"])
        self.assertEqual(payload["state"]["conversation"]["interlocutor"]["id"], npc["id"])
        self.assertEqual(payload["state"]["conversation"]["interlocutor"]["name"], "Liora")



    async def test_speech_modes_do_not_run_attack_prevalidation(self):
        captured = []

        def capture_turn(message, interaction_mode=None, scene_plan=None):
            captured.append((message, interaction_mode))
            return {"action_result": {}, "narration": "Konuşmayı değerlendirdim."}

        with patch.object(self.session, "run_player_turn", capture_turn):
            for mode in ("say", "ask_dm"):
                with self.subTest(mode=mode):
                    response = await self.http.post(
                        f"/api/game/sessions/{self.session_id}/turn",
                        json={"message": "Ona kılıcımla saldırıyorum", "interaction_mode": mode},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(captured[-1], ("Ona kılıcımla saldırıyorum", mode))

    async def test_structured_action_keeps_combat_owner_even_in_speech_mode(self):
        original_plan = self.session.plan_living_world_turn
        captured = {}

        def capture_plan(message, target_id=None, interaction_mode=None):
            captured["plan_mode"] = interaction_mode
            captured["plan_target_id"] = target_id
            return original_plan(message, target_id=target_id, interaction_mode=interaction_mode)

        def capture_turn(message, interaction_mode=None, target_id=None, combat_action=None, scene_plan=None):
            captured.update(run_mode=interaction_mode, run_target_id=target_id, combat_action=combat_action)
            return {"action_result": {}, "narration": "Yapılandırılmış hamle mevcut sahibine iletildi."}

        with patch.object(self.session, "plan_living_world_turn", capture_plan), \
             patch.object(self.session, "run_player_turn", capture_turn):
            response = await self.http.post(
                f"/api/game/sessions/{self.session_id}/turn",
                json={
                    "message": "Hamle", "interaction_mode": "ask_dm", "target_id": "npc_selected",
                    "combat_action": {"steps": [{"kind": "end_turn"}]},
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["plan_mode"], "do")
        self.assertEqual(captured["run_mode"], "do")
        self.assertEqual(captured["plan_target_id"], "npc_selected")
        self.assertEqual(captured["run_target_id"], "npc_selected")
        self.assertEqual(captured["combat_action"]["steps"][0]["kind"], "end_turn")

    async def test_active_combat_rejects_speech_modes_without_effects(self):
        from api.tests.test_combat_lifecycle import ready

        self.session.world_state["location"] = "tavern"
        ready(self.session)
        baseline = self.runtime_snapshot()
        for mode in ("say", "ask_dm"):
            with self.subTest(mode=mode):
                response = await self.http.post(
                    f"/api/game/sessions/{self.session_id}/turn",
                    json={
                        "message": "Ona saldırıyorum", "interaction_mode": mode,
                        "target_id": "npc_forged", "action_id": str(uuid4()),
                    },
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["detail"]["code"], "unsupported_interaction_mode")
                self.assertEqual(self.runtime_snapshot(), baseline)

    def runtime_snapshot(self):
        record = self.manager.get(self.session_id)
        return copy.deepcopy((
            self.session.serialize_game_state(), self.session.rng.getstate(),
            self.session.messages, self.session.world_metadata, record.journal,
            record.narrative_memory, record.combat_history, record.turn_action_receipts,
        ))

    async def test_mode_is_part_of_receipt_identity_and_replay_has_no_effects(self):
        command = {
            "message": "Envanterimde neler var?",
            "interaction_mode": "ask_dm",
            "action_id": str(uuid4()),
        }
        path = f"/api/game/sessions/{self.session_id}/turn"
        accepted = await self.http.post(path, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        baseline = self.runtime_snapshot()
        with patch.object(self.session, "run_player_turn", side_effect=AssertionError("Replay executed mechanics")) as engine, \
             patch.object(self.manager, "autosave_turn", side_effect=AssertionError("Replay replaced a receipt")) as save:
            replayed = await self.http.post(path, json=command)
            self.assertEqual(replayed.status_code, 200, replayed.text)
            self.assertEqual(replayed.json(), accepted.json())
            self.assertEqual(self.runtime_snapshot(), baseline)
            for mode in ("say", "do", None):
                with self.subTest(mode=mode):
                    changed = await self.http.post(path, json={**command, "interaction_mode": mode})
                    self.assertEqual(changed.status_code, 409, changed.text)
                    self.assertEqual(changed.json()["detail"]["code"], "action_id_conflict")
                    self.assertEqual(self.runtime_snapshot(), baseline)
        engine.assert_not_called()
        save.assert_not_called()

    async def test_omitted_mode_keeps_legacy_receipt_hash_and_null_replay(self):
        command = {"message": "Envanterimde neler var?", "action_id": str(uuid4())}
        path = f"/api/game/sessions/{self.session_id}/turn"
        accepted = await self.http.post(path, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        record = self.manager.get(self.session_id)
        expected_hash = hashlib.sha256(json.dumps(
            {"message": command["message"], "target_id": None},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.assertEqual(record.turn_action_receipts[command["action_id"]]["request_hash"], expected_hash)
        baseline = self.runtime_snapshot()
        replayed = await self.http.post(path, json={**command, "interaction_mode": None})
        self.assertEqual(replayed.status_code, 200, replayed.text)
        self.assertEqual(replayed.json(), accepted.json())
        self.assertEqual(self.runtime_snapshot(), baseline)

    def test_conversation_projection_uses_identity_and_visibility_without_learning(self):
        world = self.session.world_state
        npc = {
            "id": "npc_wave3_unknown", "name": "Thalen", "role": "Tüccar",
            "location": world["location"], "tags": [],
            "name_known_to_player": False, "role_known_to_player": True,
        }
        world["npcs"].append(npc)
        world["flags"].update(active_npc_id=npc["id"], active_npc_until_turn=9, turn_index=3)
        before = self.runtime_snapshot()
        state = serialize_session_state(self.session)
        self.assertEqual(state["conversation"], {
            "active": True,
            "interlocutor": {"id": npc["id"], "name": "Bir tüccar", "role": "Tüccar"},
        })
        self.assertEqual(self.runtime_snapshot(), before)
        self.assertEqual(npc["name"], "Thalen")
        self.assertFalse(npc["name_known_to_player"])
        for kind in ("hidden", "unobserved_event"):
            with self.subTest(kind=kind):
                npc["hidden"] = kind == "hidden"
                world["scheduled_events"] = ([{
                    "status": "OCCURRED", "visibility": "hidden", "player_observed": False,
                    "effects": [{"kind": "npc_location", "npc_id": npc["id"]}],
                }] if kind == "unobserved_event" else [])
                before = self.runtime_snapshot()
                state = serialize_session_state(self.session)
                self.assertNotIn(npc["id"], [item["id"] for item in state["npcs"]])
                self.assertEqual(state["conversation"], {"active": False, "interlocutor": None})
                self.assertEqual(self.runtime_snapshot(), before)

if __name__ == "__main__":
    unittest.main()
