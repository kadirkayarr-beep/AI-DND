"""E02 empty player projection and the save-load boundary.

Player turn responses and stored receipts must omit a hidden table-absence
cause and a persona secret that remain on the engine world.
"""

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

import httpx

import equipment_economy
import game
import incidents.projection as projection
import relationships
import scheduled_events
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.serializers import serialize_session_state
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_incident_models import _incident


class _SilentModel:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("This projection test must not call a model.")


def _public(session):
    state = serialize_session_state(session)
    return {key: state[key] for key in ("quests", "campaign_adventures")}


class IncidentProjectionTests(unittest.TestCase):
    def test_projection_is_empty_and_quest_surfaces_do_not_change(self):
        session = game.create_session(seed=7)
        before = _public(session)
        session.world_state["incidents"] = {"inc.one": _incident()}
        self.assertEqual(projection.scene_annotation(session.world_state), [])
        after = _public(session)
        self.assertEqual(after, before)
        self.assertNotIn("inc.one", repr(after))
        self.assertEqual(session.world_state["quests"], [])

    def test_engine_save_accepts_valid_and_refuses_corrupt_incidents(self):
        session = game.create_session(seed=8)
        session.world_state["incidents"] = {"inc.one": _incident()}
        payload = session.serialize_game_state()
        game._validate_save_payload(payload)
        for broken in ([], {"inc.one": _incident(lifecycle="PROPOSED")},
                       {"inc.x": _incident()}):
            corrupt = copy.deepcopy(payload)
            corrupt["world_state"]["incidents"] = broken
            with self.assertRaises(ValueError):
                game._validate_save_payload(corrupt)


class HiddenCauseProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3",
            bound_principal=TEST_PLAYER,
        )
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(_SilentModel())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def test_trace_projection_excludes_hidden_cause_and_persona_secrets(self):
        created_response = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        world = session.world_state
        here = "tavern"
        world["location"] = here
        self.assertIn(here, world["locations"])
        table = {
            "id": "feature_table", "name": "Kil masa", "location": here,
            "kind": "table", "description": "Sağlam bir masa.",
        }
        world.setdefault("features", []).append(table)
        secret = "GIZLI_KISI_SIRRI"
        world.setdefault("npcs", []).append({
            "id": "barmen", "name": "Barmen", "role": "han sahibi",
            "location": here, "inventory": [], "current_hp": 8, "max_hp": 8,
            "alive": True, "hostile": False,
            "personal_profile": {"secret_motive": secret},
        })
        marked = equipment_economy.execute(
            session, f'/item mark {table["id"]} "eski iz"')
        self.assertTrue(marked["action_result"]["success"], marked["narration"])
        event = scheduled_events.arm_table_absence(world, here)
        self.assertIsNotNone(event)
        cause = f"witnessed:{event['event_id']}"
        relationships.note(world, "barmen", 0, cause)
        action_id = str(uuid.uuid4())
        response = await self.http.post(
            f"/api/game/sessions/{session_id}/turn",
            json={"message": "/item list", "action_id": action_id},
        )
        self.assertEqual(response.status_code, 200, response.text)
        hidden = (secret, "table_absence", cause)
        for token in hidden:
            self.assertNotIn(token, response.text)
        payload = response.json()
        self.assertEqual(payload["action_id"], action_id)
        outcome = payload.get("turn_outcome") or {}
        self.assertNotEqual(outcome.get("action"), "table_absence")
        self.assertNotEqual(outcome.get("kind"), "table_absence")
        receipt = self.manager.get_turn_action(record, action_id)
        self.assertEqual(receipt["response"]["action_id"], action_id)
        stored = json.dumps(receipt["response"], ensure_ascii=False)
        for token in hidden:
            self.assertNotIn(token, stored)
        self.assertIn(secret, json.dumps(world["npcs"], ensure_ascii=False))
        self.assertIn(cause, json.dumps(relationships.read(world), ensure_ascii=False))
        self.assertTrue(any(
            effect.get("kind") == "table_absence"
            for item in world.get("scheduled_events", [])
            for effect in item.get("effects", [])
        ))


if __name__ == "__main__":
    unittest.main()
