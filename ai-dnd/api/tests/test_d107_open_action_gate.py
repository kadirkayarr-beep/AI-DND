"""D-107 (Codex YÜK-02): while a campaign has an open (unresolved) action, no other game write may overtake it.

The turn and level-up routes refuse a different action id against the stored intents. Undo, quest accept/cancel,
species actions, spell preparation and ambient events must refuse the same way, before any engine work, so an old
move that is retried later never runs on a world that changed after it was accepted. Stored receipts still replay.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import fixed_town

OK_TURN = {"narration": "Kapıdan hafif bir ses geliyor.",
           "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}


class OpenActionGateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.clients = []
        self.calls = []
        self.manager, self.http, self.session_id = await self.boot(self.store, create=True)

    async def boot(self, store, create=False):
        manager = SessionManager(campaign_store=store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        app = create_app(session_manager=manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.clients.append(http)
        if create:
            with fixed_town(self, 10700):
                created = await http.post("/api/game/campaigns", json={})
            self.assertEqual(created.status_code, 200, created.text)
            self.campaign_id = created.json()["campaign_id"]
            session_id = created.json()["session_id"]
        else:
            session_id, *_ = manager.resume_campaign(self.campaign_id)
        manager.get(session_id).game_session.run_player_turn = self.counted_turn
        return manager, http, session_id

    def counted_turn(self, _message, **_kwargs):
        self.calls.append(True)
        return dict(OK_TURN)

    async def asyncTearDown(self):
        for http in self.clients:
            await http.aclose()
        self.temporary_directory.cleanup()

    def body(self, text="Kapının arkasından ses dinliyorum."):
        return {"message": text, "action_id": str(uuid.uuid4())}

    def turn(self, body):
        return self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)

    async def leave_open_by_outage(self, body):
        """The intent is recorded, then storage fails before any effect: the action stays open, nothing applied."""
        with patch.object(self.manager, "assert_current", side_effect=CampaignStorageError("disk")):
            failed = await self.turn(body)
        self.assertEqual(failed.status_code, 503, failed.text)
        unresolved = await self.http.get(f"/api/game/sessions/{self.session_id}/actions/unresolved")
        self.assertEqual(unresolved.json()["unresolved"]["action_id"], body["action_id"])

    async def restart(self):
        self.manager, self.http, self.session_id = await self.boot(
            CampaignStore(self.store.path, bound_principal=TEST_PLAYER))

    def assert_blocked_by(self, response, open_id):
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "unresolved_action")
        self.assertEqual(detail["unresolved_action_id"], open_id)

    async def test_undo_cannot_overtake_an_open_turn(self):
        done = self.body()
        self.assertEqual((await self.turn(done)).status_code, 200)
        pending = self.body("Başka bir hamle.")
        await self.leave_open_by_outage(pending)
        session = self.manager.get(self.session_id).game_session
        before = session.serialize_game_state()
        undo = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                    json={"action_id": str(uuid.uuid4()), "target_action_id": done["action_id"]})
        self.assert_blocked_by(undo, pending["action_id"])
        self.assertEqual(session.serialize_game_state(), before, "the refused undo changed nothing")
        # The open move still applies exactly once with its own id; then nothing is open any more.
        self.assertEqual((await self.turn(pending)).status_code, 200)
        self.assertEqual(len(self.calls), 2)

    async def test_quest_accept_and_cancel_cannot_overtake_an_open_turn_after_a_restart(self):
        pending = self.body()
        await self.leave_open_by_outage(pending)
        await self.restart()
        session = self.manager.get(self.session_id).game_session
        for command in ("accept", "cancel"):
            with patch.object(session, f"{command}_quest", side_effect=ValueError("the engine ran")) as engine:
                refused = await self.http.post(f"/api/game/sessions/{self.session_id}/quests/any-quest/{command}")
            self.assert_blocked_by(refused, pending["action_id"])
            engine.assert_not_called()

    async def test_species_action_cannot_overtake_an_open_turn_after_a_restart_but_its_receipt_still_replays(self):
        session = self.manager.get(self.session_id).game_session
        session.character.update({"species": "Aasimar", "race": "Aasimar", "level": 3, "proficiency_bonus": 2,
                                  "current_hp": 1, "max_hp": 20, "charisma_mod": 1})
        session.initialize_species_trait_state()
        url = f"/api/game/sessions/{self.session_id}/species-actions"
        applied_id = str(uuid.uuid4())
        with patch.object(session.rng, "randint", return_value=1):
            first = await self.http.post(url, json={"action": "healing_hands", "action_id": applied_id})
        self.assertEqual(first.status_code, 200, first.text)
        pending = self.body()
        await self.leave_open_by_outage(pending)
        await self.restart()
        url = f"/api/game/sessions/{self.session_id}/species-actions"
        session = self.manager.get(self.session_id).game_session
        with patch.object(session, "resolve_species_trait_action", side_effect=AssertionError("the engine ran")) as engine:
            refused = await self.http.post(url, json={"action": "long_rest", "action_id": str(uuid.uuid4())})
            replay = await self.http.post(url, json={"action": "healing_hands", "action_id": applied_id})
        self.assert_blocked_by(refused, pending["action_id"])
        self.assertEqual((replay.status_code, replay.json()["action_id"]), (200, applied_id))
        engine.assert_not_called()

    async def test_spell_preparation_cannot_overtake_an_open_turn_after_a_restart(self):
        import spell_preparation
        pending = self.body()
        await self.leave_open_by_outage(pending)
        await self.restart()
        with patch.object(spell_preparation, "view", side_effect=ValueError("the engine ran")) as engine:
            refused = await self.http.post(f"/api/game/sessions/{self.session_id}/spellcasting/prepare",
                                           json={"prepared": [], "action_id": str(uuid.uuid4())})
        self.assert_blocked_by(refused, pending["action_id"])
        engine.assert_not_called()

    async def test_ambient_event_cannot_overtake_an_open_turn_after_a_restart(self):
        pending = self.body()
        await self.leave_open_by_outage(pending)
        await self.restart()
        session = self.manager.get(self.session_id).game_session
        with patch.object(session, "resolve_ambient_event_action", side_effect=ValueError("the engine ran")) as engine:
            refused = await self.http.post(
                f"/api/game/sessions/{self.session_id}/ambient-events/{uuid.uuid4()}/actions",
                json={"action": "observe", "action_id": str(uuid.uuid4())})
        self.assert_blocked_by(refused, pending["action_id"])
        engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
