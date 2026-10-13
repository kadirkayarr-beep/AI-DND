"""One offline regression for rejected narration and transient campaign memory."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

# This module is run alone so the default application cannot open its startup
# campaign store during api.main import.
os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import httpx

import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER


UNSUPPORTED_NARRATION = (
    "Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor."
)
PLAYER_MESSAGE = "Hancı'ya selam veriyorum"


class FakeOllamaClient:
    def __init__(self):
        self.list_calls = 0
        self.chat_calls = []

    def list(self):
        self.list_calls += 1
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.chat_calls.append((args, kwargs))
        return SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "valid_response": True,
                        "narration": UNSUPPORTED_NARRATION,
                        "lore_claims": [],
                        "world_updates": {},
                    },
                    ensure_ascii=False,
                )
            )
        )


class TransientNarrationMemoryAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_narration_falls_back_without_poisoning_transient_memory(self):
        manager = SessionManager(
            session_factory=lambda: game.create_session(seed=42),
        )
        session_id, record = manager.create(principal=TEST_PLAYER)
        session = record.game_session
        session.character["name"] = "Tester"
        session.character["current_hp"] = 10
        session.character["max_hp"] = 10
        session.lore_authority_context = game._empty_lore_authority_context()
        session.recent_dm_narrations = []
        session.world_state["location"] = "l_tavern"
        session.world_state["locations"] = {
            "l_tavern": {"id": "l_tavern", "name": "Eski Han", "type": "tavern"}
        }
        npc = {
            "id": "npc_barkeep",
            "name": "Hancı",
            "role": "Barkeep",
            "location": "l_tavern",
            "relationship": "neutral",
            "memory": [],
            "knowledge": [],
        }
        session.world_state["npcs"] = [npc]
        session.world_state.setdefault("flags", {})["active_npc_id"] = npc["id"]

        self.assertIsNone(record.campaign_id)
        self.assertIsNone(manager._campaign_store)
        npc_before = json.dumps(npc, ensure_ascii=False, sort_keys=True)
        memory_before = json.dumps(
            record.narrative_memory, ensure_ascii=False, sort_keys=True
        )
        journal_before = json.dumps(record.journal, ensure_ascii=False, sort_keys=True)

        fake_client = FakeOllamaClient()
        adapter = AuthenticatedOllamaAdapter(fake_client)
        with adapter.engine_binding():
            app = create_app(
                session_manager=manager,
                ollama_adapter=adapter,
                authenticator=FixedAuthenticator(TEST_PLAYER),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                response = await client.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"message": PLAYER_MESSAGE},
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotEqual(payload["narration"], UNSUPPORTED_NARRATION)
        self.assertEqual(len(fake_client.chat_calls), 1)
        self.assertEqual(fake_client.list_calls, 1)
        self.assertEqual(session.last_narration_safety["reason_code"],
                         "CANONICAL_RELATIONSHIP_CONTRADICTION")
        self.assertEqual(session.last_narration_safety["handling"], "python_fallback")

        npc_after = json.dumps(npc, ensure_ascii=False, sort_keys=True)
        memory_after = json.dumps(
            record.narrative_memory, ensure_ascii=False, sort_keys=True
        )
        journal_after = json.dumps(record.journal, ensure_ascii=False, sort_keys=True)
        for marker in ("tamamen güveniyor", "en iyi dostu"):
            self.assertNotIn(marker, npc_after.casefold())
            self.assertNotIn(marker, memory_after.casefold())
            self.assertNotIn(marker, journal_after.casefold())
        self.assertEqual(npc["relationship"], "neutral")
        self.assertEqual(npc["knowledge"], [])
        self.assertIn(PLAYER_MESSAGE, memory_after)
        self.assertIn("[presentation omitted from continuity]", memory_after)
        self.assertNotEqual(memory_before, memory_after)
        self.assertNotEqual(npc_before, npc_after)
        recent_turn = record.narrative_memory["recent_turns"][-1]
        self.assertEqual(recent_turn["player"], PLAYER_MESSAGE)
        self.assertEqual(
            recent_turn["narration"], "[presentation omitted from continuity]"
        )
        # Journal changes are permitted only from engine state/action evidence;
        # the journal updater receives no narration argument.
        self.assertIsInstance(record.journal.get("notable_events"), list)
        print(
            "F04_NARRATION_MEMORY_EVIDENCE="
            + json.dumps(
                {
                    "npc_memory_count_before": len(json.loads(npc_before)["memory"]),
                    "npc_memory_count_after": len(npc["memory"]),
                    "npc_knowledge_before": json.loads(npc_before)["knowledge"],
                    "npc_knowledge_after": npc["knowledge"],
                    "relationship_before": json.loads(npc_before)["relationship"],
                    "relationship_after": npc["relationship"],
                    "narrative_recent_turns_before": len(
                        json.loads(memory_before)["recent_turns"]
                    ),
                    "narrative_recent_turns_after": len(
                        record.narrative_memory["recent_turns"]
                    ),
                    "journal_notable_event_count_before": len(
                        json.loads(journal_before)["notable_events"]
                    ),
                    "journal_notable_event_count_after": len(
                        record.journal["notable_events"]
                    ),
                    "journal_event_types_after": [
                        event.get("event_type")
                        for event in record.journal["notable_events"]
                    ],
                    "model_chat_calls": len(fake_client.chat_calls),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    async def test_rejected_narration_stays_noncanonical_after_campaign_restart(self):
        safe_next_narration = "Hancı selamını duyunca başıyla karşılık verir."

        class SequencedFakeOllamaClient:
            def __init__(self):
                self.chat_calls = []
                self.responses = [UNSUPPORTED_NARRATION, safe_next_narration]

            def list(self):
                return {"models": [{"model": "qwen3:8b"}]}

            def chat(self, *args, **kwargs):
                self.chat_calls.append(
                    json.loads(json.dumps({"args": args, "kwargs": kwargs}, ensure_ascii=False))
                )
                if len(self.chat_calls) > len(self.responses):
                    raise AssertionError("Unexpected narration retry or extra model call.")
                narration = self.responses[len(self.chat_calls) - 1]
                return SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "valid_response": True,
                                "narration": narration,
                                "lore_claims": [],
                                "world_updates": {},
                            },
                            ensure_ascii=False,
                        )
                    )
                )

        def serialized(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)

        def assert_claim_absent(test_case, *values):
            combined = serialized(values).casefold()
            test_case.assertNotIn(UNSUPPORTED_NARRATION.casefold(), combined)

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "campaigns.sqlite3"
            store = CampaignStore(database_path, bound_principal=TEST_PLAYER)
            manager = SessionManager(
                session_factory=lambda: game.create_session(seed=42),
                campaign_store=store,
            )
            fake_client = SequencedFakeOllamaClient()
            adapter = AuthenticatedOllamaAdapter(fake_client)

            with adapter.engine_binding():
                app = create_app(
                    session_manager=manager,
                    ollama_adapter=adapter,
                    authenticator=FixedAuthenticator(TEST_PLAYER),
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://testserver",
                ) as client:
                    created = await client.post("/api/game/campaigns", json={})
                    self.assertEqual(created.status_code, 200, created.text)
                    campaign_id = created.json()["campaign_id"]
                    session_id = created.json()["session_id"]
                    record = manager.get(session_id)
                    session = record.game_session

                    session.lore_authority_context = game._empty_lore_authority_context()
                    session.recent_dm_narrations = []
                    session.world_state["location"] = "l_tavern"
                    session.world_state["locations"] = {
                        "l_tavern": {
                            "id": "l_tavern",
                            "name": "Eski Han",
                            "type": "tavern",
                        }
                    }
                    npc = {
                        "id": "npc_barkeep",
                        "name": "Hancı",
                        "role": "Barkeep",
                        "location": "l_tavern",
                        "relationship": "neutral",
                        "memory": [],
                        "knowledge": [],
                    }
                    session.world_state["npcs"] = [npc]
                    session.world_state.setdefault("flags", {})["active_npc_id"] = npc["id"]

                    engine_results = []
                    real_run_turn = session.run_player_turn

                    @wraps(real_run_turn)
                    def capture_real_turn(*args, **kwargs):
                        result = real_run_turn(*args, **kwargs)
                        engine_results.append(result)
                        return result

                    session.run_player_turn = capture_real_turn
                    initial_turn_index = session.world_state["flags"].get("turn_index", 0)
                    first_response = await client.post(
                        f"/api/game/sessions/{session_id}/turn",
                        json={
                            "message": PLAYER_MESSAGE,
                            "action_id": "00000000-0000-4000-8000-000000000008",
                        },
                    )
                    self.assertEqual(first_response.status_code, 200, first_response.text)
                    first_payload = first_response.json()
                    self.assertEqual(len(engine_results), 1)
                    self.assertIsInstance(engine_results[0].get("action_result"), dict)
                    first_action = engine_results[0]["action_result"]
                    self.assertEqual(
                        (
                            first_action.get("action"),
                            first_action.get("status"),
                            first_action.get("success"),
                            first_action.get("npc_id"),
                        ),
                        ("dialogue", "answered_smalltalk", True, npc["id"]),
                    )
                    self.assertEqual(
                        session.world_state["flags"]["turn_index"],
                        initial_turn_index + 1,
                    )
                    self.assertEqual(len(fake_client.chat_calls), 1)
                    self.assertNotEqual(first_payload["narration"], UNSUPPORTED_NARRATION)
                    first_safety = session.last_narration_safety
                    self.assertEqual(
                        first_safety["reason_code"],
                        "CANONICAL_RELATIONSHIP_CONTRADICTION",
                    )
                    self.assertIn(
                        first_safety["handling"],
                        {"python_fallback", "repaired"},
                    )
                    if first_safety["handling"] == "python_fallback":
                        self.assertIn(
                            "[presentation omitted from continuity]",
                            serialized(record.narrative_memory),
                        )
                    self.assertEqual(npc["relationship"], "neutral")
                    self.assertEqual(npc["knowledge"], [])

                    saved = store.get_campaign(campaign_id)
                    self.assertIsNotNone(saved)
                    self.assertTrue(
                        any(
                            item.get("player_message") == PLAYER_MESSAGE
                            for item in saved.history
                        )
                    )
                    self.assertEqual(saved.payload["journal"], record.journal)
                    assert_claim_absent(
                        self,
                        saved.history,
                        saved.payload,
                        session.messages,
                        session.world_state,
                        record.narrative_memory,
                        record.journal,
                    )

                    reopened_store = CampaignStore(
                        database_path,
                        bound_principal=TEST_PLAYER,
                    )
                    resumed_manager = SessionManager(
                        session_factory=lambda: game.create_session(seed=42),
                        campaign_store=reopened_store,
                    )
                    resumed_id, resumed_record, _, _, _ = (
                        resumed_manager.resume_campaign(
                            campaign_id,
                            principal=TEST_PLAYER,
                        )
                    )
                    resumed_app = create_app(
                        session_manager=resumed_manager,
                        ollama_adapter=adapter,
                        authenticator=FixedAuthenticator(TEST_PLAYER),
                    )
                    self.assertEqual(len(fake_client.chat_calls), 1)
                    self.assertIn(PLAYER_MESSAGE, serialized(resumed_record.narrative_memory))
                    assert_claim_absent(
                        self,
                        resumed_record.game_session.messages,
                        resumed_record.game_session.world_state,
                        resumed_record.narrative_memory,
                        resumed_record.journal,
                    )
                    resumed_npc = resumed_record.game_session.world_state["npcs"][0]
                    self.assertEqual(resumed_npc["relationship"], "neutral")
                    self.assertEqual(resumed_npc["knowledge"], [])

                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=resumed_app),
                        base_url="http://testserver",
                    ) as resumed_client:
                        second_response = await resumed_client.post(
                            f"/api/game/sessions/{resumed_id}/turn",
                            json={
                                "message": "Hancı'ya tekrar selam veriyorum.",
                                "action_id": "00000000-0000-4000-8000-000000000009",
                            },
                        )
                    self.assertEqual(
                        second_response.status_code, 200, second_response.text
                    )
                    self.assertEqual(len(fake_client.chat_calls), 2)
                    self.assertNotEqual(
                        second_response.json()["narration"],
                        UNSUPPORTED_NARRATION,
                    )
                    self.assertNotIn(
                        UNSUPPORTED_NARRATION.casefold(),
                        serialized(fake_client.chat_calls[1]).casefold(),
                    )
                    final_saved = reopened_store.get_campaign(campaign_id)
                    assert_claim_absent(
                        self,
                        final_saved.history,
                        final_saved.payload,
                        resumed_record.game_session.messages,
                        resumed_record.game_session.world_state,
                        resumed_record.narrative_memory,
                        resumed_record.journal,
                    )
                    for journal in (
                        saved.payload["journal"],
                        final_saved.payload["journal"],
                    ):
                        self.assertIn(
                            npc["id"],
                            {item["npc_id"] for item in journal["known_npcs"]},
                        )
                        self.assertEqual(
                            sum(
                                event["event_type"] == "npc_met"
                                and event["related_npc_id"] == npc["id"]
                                for event in journal["notable_events"]
                            ),
                            1,
                        )
                    for marker in ("tamamen güveniyor", "en iyi dostu ilan ediyor"):
                        for value in (
                            resumed_npc["memory"],
                            resumed_npc["knowledge"],
                            resumed_record.narrative_memory,
                            final_saved.payload["journal"],
                            fake_client.chat_calls[1],
                        ):
                            self.assertNotIn(
                                marker.casefold(),
                                serialized(value).casefold(),
                            )

