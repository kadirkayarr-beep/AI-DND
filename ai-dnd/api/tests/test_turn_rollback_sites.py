"""D-531 stage 3: the four pre-commit refusal sites of play_turn put every turn-owned field back.

Each site is reached by one patched step that first overwrites the session and record fields the turn owns, then
raises. The answer must be the site's own refusal body, and every field must be the pre-turn value again: a site that
forgets one field fails here. Real FastAPI app, real SessionManager, temporary store, fixed town.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import httpx

import api.main as main_module
import refusals
import turn_close
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.serializers import CombatResultSerializationError, SkillCheckResultSerializationError
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import default_town

TOWN_SEED = 8560
ENGINE_TEXT = refusals.text_for("engine_error")


TURN_FILES = (
    "game_parts/turn.py", "game_parts/turn_front.py", "game_parts/places.py",
    "game_parts/living_world_turn.py", "api/routes_turn.py", "api/routes_undo.py",
    "api/routes_economic.py", "api/main.py",
)


def moves_turn_index(node: ast.AST) -> bool:
    """Say whether the node moves a turn_index entry by arithmetic."""
    if isinstance(node, ast.AugAssign):
        targets, arithmetic = [node.target], True
    elif isinstance(node, ast.Assign):
        targets = node.targets
        arithmetic = any(isinstance(inner, ast.BinOp) for inner in ast.walk(node.value))
    else:
        return False
    return arithmetic and any(
        isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
        and target.slice.value == "turn_index" for target in targets)


class TurnRollbackSites(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        with default_town(self, TOWN_SEED):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.record = self.manager.get(self.created["session_id"])
        self.session = self.record.game_session

        def engine_turn(_message, **_kwargs):
            self.session.world_state.setdefault("flags", {})["d531_probe"] = True
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True,
                                      "state_changes": []}}

        self.session.run_player_turn = engine_turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def tamper_then_raise(self, error: Exception):
        """A side effect that overwrites every field the turn owns, then fails the step."""
        def side_effect(*_args, **_kwargs):
            self.session.campaign_lore_state = "TAMPERED_SESSION_LORE"
            self.session.world_metadata = {"tampered": True}
            self.record.journal = {"tampered": True}
            self.record.narrative_memory = {"tampered": True}
            self.record.lore_authority = "TAMPERED_RECORD_LORE"
            raise error
        return side_effect

    async def assert_site(self, target: str, error: Exception, status: int, code: str, message: str):
        lore = self.record.lore_authority
        metadata = copy.deepcopy(self.session.world_metadata)
        journal = copy.deepcopy(self.record.journal)
        memory = copy.deepcopy(self.record.narrative_memory)
        flags = copy.deepcopy(self.session.world_state.get("flags", {}))
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        with patch.object(main_module, target, side_effect=self.tamper_then_raise(error)):
            answer = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn", json=body)
        expected = {"code": code, "message": message, "not_applied": True}
        if code == "engine_error":
            expected["public_message"] = ENGINE_TEXT
        self.assertEqual((answer.status_code, answer.json()["detail"]), (status, expected), answer.text)
        self.assertIs(self.session.campaign_lore_state, lore)
        self.assertEqual(self.session.world_metadata, metadata)
        self.assertEqual(self.record.journal, journal)
        self.assertEqual(self.record.narrative_memory, memory)
        self.assertIs(self.record.lore_authority, lore)
        self.assertEqual(self.session.world_state.get("flags", {}), flags, "the engine's world change was rolled back")
        self.assertTrue(self.record.usable)
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)

    async def test_lore_evidence_site(self):
        await self.assert_site("_stage_engine_lore_state", RuntimeError("lore"), 500, "engine_error",
                               "Campaign lore evidence could not be verified.")

    async def test_narrative_memory_site(self):
        await self.assert_site("update_narrative_memory", RuntimeError("memory"), 500, "narrative_memory_error",
                               "Campaign continuity could not be updated safely.")

    async def test_journal_site(self):
        await self.assert_site("update_campaign_journal", RuntimeError("journal"), 500, "journal_error",
                               "The campaign journal could not be updated safely.")

    async def test_journal_site_skill_check_body(self):
        await self.assert_site("serialize_skill_check_result", SkillCheckResultSerializationError("x"), 500,
                               "engine_error", "The skill-check result could not be verified safely.")

    async def test_journal_site_combat_body(self):
        await self.assert_site("serialize_combat_result", CombatResultSerializationError("x"), 500,
                               "engine_error", "The combat result could not be verified safely.")

    async def test_every_turn_end_increments_once_and_undo_restores_it(self):
        """D-581, D-502: a close moves the index once and adds one pair; Undo restores both."""
        def closing_turn(message: str, **_kwargs: object) -> dict[str, object]:
            turn_close.advance(self.session.world_state)
            turn_close.record_exchange(self.session.messages, message, "The door creaked.")
            result = {"action": "world_interaction", "status": "resolved", "success": True,
                      "state_changes": []}
            return {"narration": "The door creaked.", "action_result": result}

        index_before = self.session.world_state.get("flags", {}).get("turn_index", 0)
        messages_before = copy.deepcopy(self.session.messages)
        action_id = str(uuid.uuid4())
        base = f"/api/game/sessions/{self.created['session_id']}"
        with patch.object(self.session, "run_player_turn", closing_turn):
            answer = await self.http.post(
                f"{base}/turn", json={"message": "I knock.", "action_id": action_id})
        self.assertEqual(answer.status_code, 200, answer.text)
        index_after = self.session.world_state["flags"]["turn_index"]
        self.assertEqual(index_after, index_before + 1)
        self.assertEqual(len(self.session.messages), len(messages_before) + 2)
        undo_body = {"action_id": str(uuid.uuid4()), "target_action_id": action_id}
        undone = await self.http.post(f"{base}/undo", json=undo_body)
        self.assertEqual(undone.status_code, 200, undone.text)
        flags = self.session.world_state.get("flags", {})
        self.assertEqual(flags.get("turn_index", 0), index_before)
        self.assertEqual(self.session.messages, messages_before)

    def test_no_hand_written_turn_index_increment(self) -> None:
        """Check that turn_close.advance alone moves turn_index (D-581, D-502)."""
        root = Path(__file__).resolve().parents[2]
        trees = {name: ast.parse((root / name).read_text(encoding="utf-8")) for name in TURN_FILES}
        found = [f"{name}:{node.lineno}" for name, tree in trees.items()
                 for node in ast.walk(tree) if moves_turn_index(node)]
        self.assertEqual(found, [], "turn_index is moved only by turn_close.advance")

    def test_advance_and_record_exchange(self) -> None:
        self.assertEqual(turn_close.advance({"flags": {"turn_index": 4}}), 5)
        self.assertEqual(turn_close.advance({}), 1)
        messages: list[dict[str, str]] = []
        turn_close.record_exchange(messages, "a", "b")
        pair = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        self.assertEqual(messages, pair)

    async def test_response_site(self):
        await self.assert_site("_turn_outcome", RuntimeError("response"), 500, "engine_error",
                               "The turn response could not be built safely.")


if __name__ == "__main__":
    unittest.main()
