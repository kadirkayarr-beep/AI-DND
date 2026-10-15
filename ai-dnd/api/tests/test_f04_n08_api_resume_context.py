"""N08 persisted campaign and next-provider-context regression; offline ASGI only."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

# Do not initialize the default application or its persistent campaign store.
os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"

import httpx
import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_f04_n08_npc_memory import CLAIM


class CaptureFakeClient:
    def __init__(self):
        self.chat_calls = []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.chat_calls.append(json.loads(json.dumps(
            {"args": args, "kwargs": kwargs}, ensure_ascii=False
        )))
        if len(self.chat_calls) > 4:
            raise AssertionError("Exceeded two provider attempts per turn")
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "valid_response": True,
            "narration": "Seni dinliyorum.",
            "lore_claims": [],
            "world_updates": {},
        }, ensure_ascii=False)))


class N08ApiPersistenceContext(unittest.IsolatedAsyncioTestCase):
    async def test_claim_not_verified_after_sqlite_resume_and_next_provider_context(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "n08.sqlite3"
            store = CampaignStore(db, bound_principal=TEST_PLAYER)
            manager = SessionManager(
                session_factory=lambda: game.create_session(seed=813),
                campaign_store=store,
            )
            fake = CaptureFakeClient()
            adapter = AuthenticatedOllamaAdapter(fake)
            with adapter.engine_binding():
                app = create_app(
                    session_manager=manager, ollama_adapter=adapter,
                    authenticator=FixedAuthenticator(TEST_PLAYER),
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://testserver",
                ) as client:
                    created = await client.post("/api/game/campaigns", json={})
                    self.assertEqual(created.status_code, 200, created.text)
                    cid = created.json()["campaign_id"]
                    sid = created.json()["session_id"]
                    record = manager.get(sid)
                    session = record.game_session
                    session.lore_authority_context = game._empty_lore_authority_context()
                    session.world_state["location"] = "l_tavern"
                    session.world_state["locations"] = {
                        "l_tavern": {"id": "l_tavern", "name": "Eski Han", "type": "tavern"}
                    }
                    session.world_state["npcs"] = [{
                        "id": "npc_001", "name": "Elara", "role": "Barkeep",
                        "location": "l_tavern", "relationship": "neutral",
                        "memory": [], "knowledge": [],
                    }]
                    session.world_state.setdefault("flags", {})["active_npc_id"] = "npc_001"
                    first = await client.post(
                        f"/api/game/sessions/{sid}/turn",
                        json={"message": CLAIM, "action_id": "00000000-0000-4000-8000-000000000181"},
                    )
                    self.assertEqual(first.status_code, 200, first.text)
                    first_attempts = len(fake.chat_calls)
                    self.assertGreaterEqual(first_attempts, 1)
                    self.assertLessEqual(first_attempts, 2)
                    self.assertEqual(session.world_state["npcs"][0]["memory"], [])
                    saved = store.get_campaign(cid)
                    self.assertIsNotNone(saved)

                reopened = CampaignStore(db, bound_principal=TEST_PLAYER)
                resumed = SessionManager(
                    session_factory=lambda: game.create_session(seed=813),
                    campaign_store=reopened,
                )
                new_sid, new_record, _, _, _ = resumed.resume_campaign(
                    cid, principal=TEST_PLAYER,
                )
                resumed_npc = new_record.game_session.world_state["npcs"][0]
                self.assertEqual(resumed_npc["memory"], [])
                self.assertEqual(resumed_npc["relationship"], "neutral")
                self.assertEqual(resumed_npc["knowledge"], [])
                resumed_app = create_app(
                    session_manager=resumed, ollama_adapter=adapter,
                    authenticator=FixedAuthenticator(TEST_PLAYER),
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=resumed_app),
                    base_url="http://testserver",
                ) as client:
                    second = await client.post(
                        f"/api/game/sessions/{new_sid}/turn",
                        json={"message": "Elara, merhaba.", "action_id": "00000000-0000-4000-8000-000000000182"},
                    )
                self.assertEqual(second.status_code, 200, second.text)
                second_attempts = len(fake.chat_calls) - first_attempts
                self.assertGreaterEqual(second_attempts, 1)
                self.assertLessEqual(second_attempts, 2)
                second_calls = fake.chat_calls[first_attempts:]
                user_prompts = [m["content"] for call in second_calls
                                for m in call["kwargs"].get("messages", [])
                                if m.get("role") == "user"]
                context_prompts = [p for p in user_prompts if "KOMPAKT WORLD CONTEXT" in p]
                self.assertTrue(context_prompts, "No real second-turn model context captured")
                prefix = "KOMPAKT WORLD CONTEXT (salt okunur):\n"
                for prompt in context_prompts:
                    begin = prompt.index(prefix) + len(prefix)
                    end = prompt.index("\n\nVERIFIED LORE AUTHORITY", begin)
                    context = json.loads(prompt[begin:end])
                    memory = context["npcs"][0]["verified_npc_memory"]
                    self.assertNotIn(CLAIM, json.dumps(memory, ensure_ascii=False))
                    self.assertEqual(context["npcs"][0]["relationship"], "neutral")
                    self.assertEqual(context["player_known_events"], [])
                    recent = context["narrative_continuity"]["relevant_continuity"]["recent_turns"]
                    claims = [item for item in recent if item.get("player") == CLAIM]
                    self.assertEqual(len(claims), 1)
                    self.assertEqual(claims[0]["authority"], "unverified_player_claim")
                self.assertEqual(resumed_npc["relationship"], "neutral")


if __name__ == "__main__":
    unittest.main()
