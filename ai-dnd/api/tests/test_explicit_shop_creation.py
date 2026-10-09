"""Native shop creation, model boundary, and real campaign transaction tests."""
import copy
from functools import wraps
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

import httpx
import game
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.live_neverwinter_canon_smoke import START_SELECTION

REQUEST = "Bu kampanya için burada küçük bir yerel dükkân ve onu işleten tek bir dükkâncı oluştur."


def protected(world):
    return {key: copy.deepcopy(world.get(key)) for key in (
        "inventory", "gold", "currency", "quests", "quest_offers", "item_rewards",
    )}


class ShopCreationTests(unittest.TestCase):
    def test_python_creates_before_narration_and_rejects_model_world_changes_without_retry(self):
        session = game.create_session(seed=1729)
        session.world_state["location"] = "tavern"
        before = protected(session.world_state)

        # Observe the actual narrator call; its input is already resolved.
        real_ask = game.ask_dungeon_master
        def observe(*args, **kwargs):
            self.assertEqual(len(session.world_state["shops"]), 1)
            self.assertEqual(kwargs["action_result"]["status"], "created")
            self.assertTrue(kwargs["narration_only"])
            return real_ask(*args, **kwargs)
        with patch("game.ask_dungeon_master", side_effect=observe), patch("game.ollama.chat", return_value={"message": {"content": json.dumps({
            "narration": "King Vharion gives you gold.",
            "world_updates": {"create_shops": [{"name": "Forged"}], "create_npcs": [{"name": "Forged"}]},
            "lore_claims": [],
        })}}) as model:
            result = session.run_player_turn(REQUEST)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["action_result"]["status"], "created")
        self.assertEqual(len(session.world_state["shops"]), 1)
        self.assertEqual(len(session.world_state["npcs"]), 1)
        self.assertEqual(result["narration"], result["action_result"]["direct_response"])
        self.assertEqual(protected(session.world_state), before)
        shop, npc = session.world_state["shops"][0], session.world_state["npcs"][0]
        self.assertEqual(shop["shopkeeper_id"], npc["id"])
        self.assertEqual(npc["shop_id"], shop["id"])
        self.assertNotIn("inventory", npc)
        self.assertNotIn("item_offers_cp", shop)
        self.assertEqual(shop["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertLessEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 2)

    def test_capacity_and_unknown_location_fail_without_partial_creation(self):
        for kind in ("shops", "local_shops", "npcs", "local_npcs", "unknown_location"):
            with self.subTest(kind=kind):
                session = game.create_session(seed=1729)
                session.world_state["location"] = "tavern"
                location = session.world_state["location"]
                if kind in {"shops", "local_shops"}:
                    session.world_state["shops"] = [{"id": f"s{i}", "location": location if kind == "local_shops" else "elsewhere"} for i in range(3 if kind == "local_shops" else 12)]
                elif kind in {"npcs", "local_npcs"}:
                    session.world_state["npcs"] = [{"id": f"n{i}", "name": f"Person{i}", "role": "Traveler", "location": location if kind == "local_npcs" else "elsewhere"} for i in range(6 if kind == "local_npcs" else 60)]
                else:
                    session.world_state["location"] = "unknown_unregistered"
                before = copy.deepcopy(session.world_state)
                with patch("game.ollama.chat", side_effect=AssertionError("No model needed")):
                    result = session.run_player_turn(REQUEST)
                self.assertFalse(result["action_result"]["success"])
                for key in ("shops", "npcs", "next_shop_number", "next_npc_number"):
                    self.assertEqual(session.world_state.get(key), before.get(key))


class ShopTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ai-dnd-shop-transaction-")
        self.store = CampaignStore(Path(self.temp.name) / "campaigns.sqlite3")
        self.manager = SessionManager(campaign_store=self.store)
        self.model = Mock()
        self.model.list.return_value = {"models": [{"model": "qwen3:8b"}]}
        self.model.chat.return_value = {"message": {"content": "{}"}}
        adapter = AuthenticatedOllamaAdapter(self.model)
        self.enterContext(adapter.engine_binding())
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(session_manager=self.manager, ollama_adapter=adapter)), base_url="http://testserver")
        response = await self.http.post("/api/game/campaigns", json={"campaign_start": START_SELECTION})
        self.assertEqual(response.status_code, 200, response.text)
        self.created = response.json()
        self.record = self.manager.get(self.created["session_id"])
        self.url = f'/api/game/sessions/{self.created["session_id"]}/turn'

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temp.cleanup()

    async def test_creation_replay_duplicate_resume_and_session_isolation(self):
        other = await self.http.post("/api/game/campaigns", json={"campaign_start": START_SELECTION})
        other_session = self.manager.get(other.json()["session_id"]).game_session
        other_before = copy.deepcopy(other_session.serialize_game_state())
        before = protected(self.record.game_session.world_state)
        body = {"message": REQUEST, "action_id": str(uuid.uuid4())}
        created = await self.http.post(self.url, json=body)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(self.model.chat.call_count, 1)
        replay = await self.http.post(self.url, json=body)
        self.assertEqual(replay.json(), created.json())
        self.assertEqual(self.model.chat.call_count, 1)
        duplicate = await self.http.post(self.url, json={"message": REQUEST, "action_id": str(uuid.uuid4())})
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        world = self.record.game_session.world_state
        self.assertEqual(len(world["shops"]), 1)
        self.assertEqual(len(world["npcs"]), 1)
        self.assertEqual(protected(world), before)
        self.assertEqual(other_session.serialize_game_state(), other_before)
        persisted = copy.deepcopy(world)
        reopened = SessionManager(campaign_store=CampaignStore(self.store.path))
        resumed_id, *_ = reopened.resume_campaign(self.created["campaign_id"])
        resumed = reopened.get(resumed_id)
        self.assertEqual(resumed.game_session.world_state, persisted)
        receipt = reopened.get_turn_action(resumed, body["action_id"])
        self.assertEqual(receipt["response"], created.json())
        adapter = AuthenticatedOllamaAdapter(self.model)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(session_manager=reopened, ollama_adapter=adapter)), base_url="http://testserver") as http:
            replay_after_restart = await http.post(f"/api/game/sessions/{resumed_id}/turn", json=body)
        self.assertEqual(replay_after_restart.status_code, 200, replay_after_restart.text)
        expected = created.json()
        expected["session_id"] = resumed_id
        self.assertEqual(replay_after_restart.json(), expected)
        self.assertEqual(self.model.chat.call_count, 1)
        self.assertEqual(world["shops"][0]["shopkeeper_id"], world["npcs"][0]["id"])
        self.assertEqual(world["npcs"][0]["shop_id"], world["shops"][0]["id"])

    async def test_failed_autosave_restores_complete_state_and_has_no_receipt(self):
        session = self.record.game_session
        engine_before = copy.deepcopy(session.serialize_game_state())
        rng_before = session.rng.getstate()
        history_before = copy.deepcopy(session.recent_dm_narrations)
        journal_before = copy.deepcopy(self.record.journal)
        memory_before = copy.deepcopy(self.record.narrative_memory)
        lore_before = copy.deepcopy(self.record.lore_authority)
        saved_before = self.store.get_campaign(self.created["campaign_id"])
        body = {"message": REQUEST, "action_id": str(uuid.uuid4())}
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("test unavailable")):
            failed = await self.http.post(self.url, json=body)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(session.serialize_game_state(), engine_before)
        self.assertEqual(session.rng.getstate(), rng_before)
        self.assertEqual(session.recent_dm_narrations, history_before)
        self.assertEqual(self.record.journal, journal_before)
        self.assertEqual(self.record.narrative_memory, memory_before)
        self.assertEqual(self.record.lore_authority, lore_before)
        self.assertEqual(self.store.get_campaign(self.created["campaign_id"]).payload, saved_before.payload)
        self.assertIsNone(self.store.get_turn_action(self.created["campaign_id"], body["action_id"]))
        retried = await self.http.post(self.url, json=body)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(len(session.world_state["shops"]), 1)
        self.assertEqual(len(session.world_state["npcs"]), 1)


if __name__ == "__main__":
    unittest.main()
