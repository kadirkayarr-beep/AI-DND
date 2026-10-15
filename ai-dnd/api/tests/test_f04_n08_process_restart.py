"""N08 isolated two-OS-process SQLite restart and synthetic context evidence."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"
AI_DND_ROOT = Path(__file__).resolve().parents[2]
if str(AI_DND_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_DND_ROOT))

import httpx
import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_f04_n08_npc_memory import CLAIM


class FakeProvider:
    def __init__(self):
        self.calls = []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls.append(json.loads(json.dumps(
            {"args": args, "kwargs": kwargs}, ensure_ascii=False
        )))
        if len(self.calls) > 2:
            raise AssertionError("More than two provider calls in one process/turn")
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "valid_response": True,
            "narration": "Seni dinliyorum.",
            "lore_claims": [], "world_updates": {},
        }, ensure_ascii=False)))


async def worker(phase: str, root: Path):
    store = CampaignStore(root / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
    manager = SessionManager(
        session_factory=lambda: game.create_session(seed=813), campaign_store=store
    )
    fake = FakeProvider()
    adapter = AuthenticatedOllamaAdapter(fake)
    with adapter.engine_binding():
        if phase == "first":
            app = create_app(
                session_manager=manager, ollama_adapter=adapter,
                authenticator=FixedAuthenticator(TEST_PLAYER),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                created = await client.post("/api/game/campaigns", json={})
                assert created.status_code == 200, created.text
                cid, sid = created.json()["campaign_id"], created.json()["session_id"]
                session = manager.get(sid).game_session
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
                    json={"message": CLAIM,
                          "action_id": "00000000-0000-4000-8000-000000000281"},
                )
                assert first.status_code == 200, first.text
                assert 1 <= len(fake.calls) <= 2
                npc = session.world_state["npcs"][0]
                assert npc["memory"] == [] and npc["knowledge"] == []
                assert npc["relationship"] == "neutral"
                assert store.get_campaign(cid) is not None
                (root / "campaign.json").write_text(json.dumps({"campaign_id": cid}))
                (root / "first.json").write_text(json.dumps({
                    "pid": os.getpid(), "attempts": len(fake.calls),
                    "memory": npc["memory"], "knowledge": npc["knowledge"],
                    "relationship": npc["relationship"],
                }))
        else:
            cid = json.loads((root / "campaign.json").read_text())["campaign_id"]
            sid, record, _, _, _ = manager.resume_campaign(cid, principal=TEST_PLAYER)
            npc = record.game_session.world_state["npcs"][0]
            assert npc["memory"] == [] and npc["knowledge"] == []
            assert npc["relationship"] == "neutral"
            app = create_app(
                session_manager=manager, ollama_adapter=adapter,
                authenticator=FixedAuthenticator(TEST_PLAYER),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                second = await client.post(
                    f"/api/game/sessions/{sid}/turn",
                    json={"message": "Elara, merhaba.",
                          "action_id": "00000000-0000-4000-8000-000000000282"},
                )
            assert second.status_code == 200, second.text
            assert 1 <= len(fake.calls) <= 2
            contexts = []
            for call in fake.calls:
                for message in call["kwargs"].get("messages", []):
                    body = message.get("content", "")
                    prefix = "KOMPAKT WORLD CONTEXT (salt okunur):\n"
                    if message.get("role") != "user" or prefix not in body:
                        continue
                    start = body.index(prefix) + len(prefix)
                    end = body.index("\n\nVERIFIED LORE AUTHORITY", start)
                    contexts.append(json.loads(body[start:end]))
            assert contexts, "Second process did not send real context to fake provider"
            for context in contexts:
                assert context["player_known_events"] == []
                assert context["npcs"][0]["relationship"] == "neutral"
                assert CLAIM not in json.dumps(
                    context["npcs"][0]["verified_npc_memory"], ensure_ascii=False
                )
                continuity = context["narrative_continuity"]["relevant_continuity"]
                matches = [row for row in continuity["recent_turns"]
                           if row.get("player") == CLAIM]
                assert len(matches) == 1
                assert matches[0]["authority"] == "unverified_player_claim"
                assert not continuity["story_summary"]["important_relationships"]
            (root / "second.json").write_text(json.dumps({
                "pid": os.getpid(), "attempts": len(fake.calls),
                "context_count": len(contexts),
                "claim_authority": "unverified_player_claim",
                "memory_before_second": [], "relationship_before_second": "neutral",
            }))


class N08SeparateProcessRestart(unittest.TestCase):
    def test_real_process_exit_and_new_process_resume(self):
        with tempfile.TemporaryDirectory(prefix="n08-process-restart-") as temporary:
            root = Path(temporary)
            for phase in ("first", "second"):
                result = subprocess.run(
                    [sys.executable, "-B", str(Path(__file__).resolve()),
                     "--worker", phase, str(root)],
                    cwd=str(Path(__file__).resolve().parents[2]),
                    capture_output=True, text=True, timeout=45,
                    env={**os.environ, "AI_DND_DISABLE_DEFAULT_APP": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            first = json.loads((root / "first.json").read_text())
            second = json.loads((root / "second.json").read_text())
            self.assertNotEqual(first["pid"], second["pid"])
            self.assertGreaterEqual(second["attempts"], 1)
            self.assertEqual(second["claim_authority"], "unverified_player_claim")
            print("N08_PROCESS_EVIDENCE=" + json.dumps({
                "different_pids": first["pid"] != second["pid"],
                "first_attempts": first["attempts"],
                "second_attempts": second["attempts"],
                "second_contexts": second["context_count"],
                "claim_authority": second["claim_authority"],
            }))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        asyncio.run(worker(sys.argv[2], Path(sys.argv[3])))
    else:
        unittest.main()
