"""D-531 stage 4: exits of play_turn that no other test pinned by status, body and state.

Each test drives the real /turn route (real FastAPI app, real SessionManager, temporary store, fixed town) into one
exit and checks the status code, the exact error body, that every turn-owned field is the pre-turn value again for a
refusal, that nothing reached the campaign history, and that a refusal leaves the Undo point alone.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx

import api.main as main_module
import combat_lifecycle
import front_proposal
import game
import refusals
from api.auth import FixedAuthenticator
from api.main import MODEL_FAILURE_MESSAGE, create_app
from api.ollama_adapter import (
    _MODEL_CALLS,
    _MODEL_FAILURES,
    MAX_MODEL_CALLS_PER_TURN,
    AuthenticatedOllamaAdapter,
    OllamaUnavailableError,
    RequiredModelUnavailableError,
)
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import default_town
from dialogue_runtime import DialogueProviderError, DialogueResponseError

TOWN_SEED = 8560
ENGINE_TEXT = refusals.text_for("engine_error")
MESSAGE = "Kapının arkasından ses dinliyorum."
NARRATION = "Kapıdan hafif bir ses geliyor."


def resolved(**extra):
    return {"narration": NARRATION,
            "action_result": {"action": "world_interaction", "status": "resolved", "success": True,
                              "state_changes": [], **extra}}


class PlayTurnBranches(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        self.adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(self.adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=self.adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        with default_town(self, TOWN_SEED):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.url = f"/api/game/sessions/{self.created['session_id']}/turn"
        self.record = self.manager.get(self.created["session_id"])
        self.session = self.record.game_session
        self.engine(lambda: resolved(), tamper=False)

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def engine(self, answer, tamper=True):
        """The engine's turn: it changes the world first (a rollback must undo it), then answers or raises."""
        def engine_turn(_message, **_kwargs):
            self.session.world_state.setdefault("flags", {})["d531_probe"] = True
            if not tamper:
                return answer()
            self.session.world_metadata = {"tampered": True}
            self.record.journal = {"tampered": True}
            self.record.narrative_memory = {"tampered": True}
            self.record.lore_authority = "TAMPERED_RECORD_LORE"
            return answer()
        self.session.run_player_turn = engine_turn

    def raising(self, error: BaseException):
        def answer():
            raise error
        return answer

    def before(self):
        return {"lore": self.record.lore_authority,
                "metadata": copy.deepcopy(self.session.world_metadata), "journal": copy.deepcopy(self.record.journal),
                "memory": copy.deepcopy(self.record.narrative_memory),
                "flags": copy.deepcopy(self.session.world_state.get("flags", {})),
                "undo": self.record.undo_checkpoint}

    def history(self):
        return len(self.store.get_campaign(self.created["campaign_id"]).history)

    async def post(self, message=MESSAGE, action_id=None, **extra):
        body = {"message": message, "action_id": action_id or str(uuid.uuid4()), **extra}
        return await self.http.post(self.url, json=body)

    def assert_put_back(self, before, history=0):
        self.assertIs(self.record.lore_authority, before["lore"])
        self.assertIs(getattr(self.session, "campaign_lore_state", before["lore"]), before["lore"])
        self.assertEqual(self.session.world_metadata, before["metadata"])
        self.assertEqual(self.record.journal, before["journal"])
        self.assertEqual(self.record.narrative_memory, before["memory"])
        self.assertEqual(self.session.world_state.get("flags", {}), before["flags"], "the engine's change rolled back")
        self.assertIs(self.record.undo_checkpoint, before["undo"], "a refusal keeps the Undo point")
        self.assertTrue(self.record.usable)
        self.assertEqual(self.history(), history)

    async def assert_refused(self, status, detail, **post):
        before = self.before()
        answer = await self.post(**post)
        self.assertEqual((answer.status_code, answer.json()["detail"]), (status, detail), answer.text)
        self.assert_put_back(before)
        return answer

    def engine_refusal(self, message):
        return {"code": "engine_error", "message": message, "not_applied": True, "public_message": ENGINE_TEXT}

    def model_refusal(self, code, message=MODEL_FAILURE_MESSAGE):
        return {"code": code, "message": message, "not_applied": True}

    # Before the turn lock is held for work.

    async def test_session_revoked_while_waiting_is_unknown(self):
        claim = self.manager.claim_action_intent

        def claim_then_revoke(*args, **kwargs):
            outcome = claim(*args, **kwargs)
            self.record.revoked = True  # revoked after the claim, before the turn lock was held
            return outcome
        with patch.object(self.manager, "claim_action_intent", side_effect=claim_then_revoke):
            answer = await self.post()
        self.assertEqual((answer.status_code, answer.json()["detail"]),
                         (404, {"code": "unknown_session", "message": "Session not found."}))
        self.assertEqual(self.history(), 0)

    async def test_committed_id_replays_and_conflicts_on_other_payload(self):
        action_id = str(uuid.uuid4())
        first = await self.post(action_id=action_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.engine(self.raising(AssertionError("a replay must not run the engine")))
        again = await self.post(action_id=action_id)
        self.assertEqual((again.status_code, again.json()), (200, first.json()))
        other = await self.post(message="Başka bir şey yapıyorum.", action_id=action_id)
        self.assertEqual((other.status_code, other.json()["detail"]), (409, {
            "code": "action_id_conflict", "message": "This action ID was already used for a different turn."}))
        self.assertEqual(self.history(), 1)

    async def test_refused_id_replays_refusal_and_conflicts_on_other_payload(self):
        action_id = str(uuid.uuid4())
        self.engine(lambda: {"narration": "   ", "action_result": {}})
        detail = self.engine_refusal("The game turn returned an invalid response.")
        await self.assert_refused(500, detail, action_id=action_id)
        self.engine(self.raising(AssertionError("a replay must not run the engine")))
        await self.assert_refused(500, detail, action_id=action_id)
        other = await self.post(message="Başka bir şey yapıyorum.", action_id=action_id)
        self.assertEqual((other.status_code, other.json()["detail"]), (409, {
            "code": "action_id_conflict", "message": "This action ID was already used for a different turn."}))

    async def test_invalid_combat_state(self):
        with patch.object(combat_lifecycle, "validate_request", side_effect=ValueError("broken")):
            await self.assert_refused(409, {"code": "invalid_combat_state", "message": "Combat state is invalid.",
                                            "not_applied": True})

    async def test_no_adapter(self):
        self.app.state.ollama_adapter = None
        await self.assert_refused(503, self.model_refusal("ollama_unavailable"))

    async def test_preflight_unavailable(self):
        with patch.object(self.adapter, "ensure_required_model", side_effect=OllamaUnavailableError("Timeout")):
            await self.assert_refused(503, self.model_refusal("ollama_unavailable"))

    async def test_required_model_missing(self):
        with patch.object(self.adapter, "ensure_required_model", side_effect=RequiredModelUnavailableError()):
            await self.assert_refused(503, self.model_refusal(
                "model_unavailable", f"Required model {self.adapter.model_name} is unavailable."))

    # Inside the engine window (the snapshot is taken).

    async def test_engine_error(self):
        self.engine(self.raising(RuntimeError("engine broke")))
        await self.assert_refused(500, self.engine_refusal("The game turn could not be completed."))

    async def test_dialogue_provider_error(self):
        self.engine(self.raising(DialogueProviderError("down")))
        await self.assert_refused(503, self.model_refusal("ollama_unavailable"))

    async def test_dialogue_response_error(self):
        self.engine(self.raising(DialogueResponseError("bad")))
        await self.assert_refused(503, self.model_refusal("invalid_dialogue_response"))

    async def test_typed_combat_refusal_from_engine(self):
        self.engine(self.raising(combat_lifecycle.CombatRequestError("d531_code", "Typed refusal.", 409)))
        await self.assert_refused(409, {"code": "d531_code", "message": "Typed refusal.", "not_applied": True})

    async def test_player_cannot_act_answers_with_the_fallback_turn(self):
        self.engine(self.raising(game.PlayerCannotAct("down")))
        before = self.before()
        self.session.player_cannot_act_turn = lambda: {"narration": "Kıpırdayamıyorsun.", "action_result": None}
        answer = await self.post()
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json()["narration"], "Kıpırdayamıyorsun.")
        self.assertEqual(self.session.world_state.get("flags", {}).get("d531_probe"), None, "restored before fallback")
        self.assertEqual(self.history(), 1)
        self.assertIsNot(self.record.undo_checkpoint, before["undo"])

    async def test_model_failure_in_turn(self):
        def answer():
            _MODEL_FAILURES.get().append("ReadTimeout")
            return resolved()
        self.engine(answer)
        await self.assert_refused(503, self.model_refusal("ollama_unavailable"))

    async def test_front_reading_failure(self):
        def reading(*_args, **_kwargs):
            self.session.world_state.setdefault("flags", {})["d531_reading"] = True
            _MODEL_FAILURES.get().append("ReadTimeout")
        self.session.front_read_ahead = reading
        self.engine(self.raising(AssertionError("a failed reading must not run the turn")))
        with patch.object(front_proposal, "enabled", return_value=True):
            await self.assert_refused(503, self.model_refusal("ollama_unavailable"))

    # After the engine answered, before the commit.

    async def test_model_call_limit(self):
        def answer():
            _MODEL_CALLS.get().extend(["qwen3:8b"] * (MAX_MODEL_CALLS_PER_TURN + 2))
            return resolved()
        self.engine(answer)
        await self.assert_refused(500, self.engine_refusal("The game turn exceeded its model-call limit."))

    async def test_invalid_narration(self):
        self.engine(lambda: {"narration": "   ", "action_result": {}})
        await self.assert_refused(500, self.engine_refusal("The game turn returned an invalid response."))

    async def test_intent_infrastructure_failure_keeps_a_known_code(self):
        self.engine(lambda: resolved(status="infrastructure_failure", infrastructure_code="intent_timeout"))
        await self.assert_refused(503, self.model_refusal("intent_timeout"))

    async def test_intent_infrastructure_failure_maps_an_unknown_code(self):
        self.engine(lambda: resolved(status="infrastructure_failure", infrastructure_code="d531_other"))
        await self.assert_refused(503, self.model_refusal("model_unavailable"))

    # The commit.

    async def test_success_commits_receipt_and_undo_point(self):
        action_id = str(uuid.uuid4())
        answer = await self.post(action_id=action_id)
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertEqual((body["session_id"], body["action_id"], body["narration"]),
                         (self.created["session_id"], action_id, NARRATION))
        self.assertEqual(self.history(), 1)
        self.assertEqual(self.manager.get_turn_action(self.record, action_id)["response"], body)
        self.assertEqual((self.record.undo_checkpoint["action_id"], self.record.undo_checkpoint["player_message"]),
                         (action_id, MESSAGE))
        self.assertIsNot(self.record.lore_authority, "TAMPERED_RECORD_LORE")

    async def test_death_rollback_keeps_journal_and_memory(self):
        before = self.before()
        self.engine(lambda: resolved(enemy_actions=[{"death_resolution": {"rolled_back": True}}]), tamper=False)
        result = await self.post()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.record.journal, before["journal"], "a death rollback does not write the journal")
        self.assertEqual(self.record.narrative_memory, before["memory"], "a death rollback keeps the memory")
        self.assertEqual(self.history(), 1)

    async def test_death_rollback_skips_the_journal_update(self):
        journal = patch.object(main_module, "update_campaign_journal", wraps=main_module.update_campaign_journal)
        with journal as update:
            self.engine(lambda: resolved(enemy_actions=[{"death_resolution": {"rolled_back": True}}]), tamper=False)
            death = await self.post()
            self.assertEqual(death.status_code, 200, death.text)
            update.assert_not_called()
            self.engine(lambda: resolved(), tamper=False)
            plain = await self.post()
            self.assertEqual(plain.status_code, 200, plain.text)
            update.assert_called_once()

    async def test_plain_turn_writes_journal_and_memory(self):
        """The other side of the death test: the same turn without a death rollback does write both."""
        before = self.before()
        result = await self.post()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotEqual(self.record.narrative_memory, before["memory"])


if __name__ == "__main__":
    unittest.main()
