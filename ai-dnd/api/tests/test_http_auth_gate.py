"""Anonymous and cross-player HTTP access. Temporary databases only."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import uuid

import game
import httpx
from api.auth import FailClosedAuthenticator, FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import PLAYER_A, PLAYER_B


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()
_AUTH = {
    "detail": {
        "code": "authentication_required",
        "message": "Kimlik doğrulaması gerekli.",
    },
}
_MISSING_CAMPAIGN = {
    "detail": {
        "code": "campaign_not_found",
        "message": "Bu macera kaydı bulunamadı.",
    },
}
_MISSING_SESSION = {
    "detail": {"code": "unknown_session", "message": "Session not found."},
}


def _path(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


class HttpAuthGateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CampaignStore(_path(self.directory.name))
        self.manager = SessionManager(campaign_store=self.store)
        campaign_id, session_id, record, _ = self.manager.create_campaign(
            name="Owned", principal=PLAYER_A,
        )
        self.campaign_id = campaign_id
        self.session_id = session_id
        self.hp = record.game_session.character["current_hp"]
        self.closed = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=FailClosedAuthenticator(),
        )
        self.owner = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=FixedAuthenticator(PLAYER_A),
        )
        self.other = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=FixedAuthenticator(PLAYER_B),
        )

    def _client(self, app):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://isolated-testserver",
        )

    async def test_public_routes_stay_open_and_protected_routes_require_a_principal(self):
        quest_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        protected = [
            ("POST", "/api/sessions", None),
            ("POST", "/api/game/sessions", None),
            ("GET", f"/api/sessions/{self.session_id}/state", None),
            ("GET", f"/api/game/sessions/{self.session_id}/state", None),
            ("POST", f"/api/sessions/{self.session_id}/turn", {"message": "Bekle."}),
            ("POST", f"/api/game/sessions/{self.session_id}/turn", {"message": "Bekle."}),
            ("POST", f"/api/sessions/{self.session_id}/quests/{quest_id}/accept", None),
            ("POST", f"/api/game/sessions/{self.session_id}/quests/{quest_id}/accept", None),
            ("POST", f"/api/sessions/{self.session_id}/quests/{quest_id}/cancel", None),
            ("POST", f"/api/game/sessions/{self.session_id}/quests/{quest_id}/cancel", None),
            ("POST", f"/api/sessions/{self.session_id}/species-actions", {"action": "dash"}),
            ("POST", f"/api/game/sessions/{self.session_id}/species-actions", {"action": "dash"}),
            (
                "POST",
                f"/api/sessions/{self.session_id}/ambient-events/{event_id}/actions",
                {"action": "ignore"},
            ),
            (
                "POST",
                f"/api/game/sessions/{self.session_id}/ambient-events/{event_id}/actions",
                {"action": "ignore"},
            ),
            ("POST", "/api/campaigns", {}),
            ("POST", "/api/game/campaigns", {}),
            ("GET", "/api/campaigns", None),
            ("GET", "/api/game/campaigns", None),
            ("GET", f"/api/campaigns/{self.campaign_id}", None),
            ("GET", f"/api/game/campaigns/{self.campaign_id}", None),
            ("DELETE", f"/api/campaigns/{self.campaign_id}", None),
            ("DELETE", f"/api/game/campaigns/{self.campaign_id}", None),
            ("POST", f"/api/campaigns/{self.campaign_id}/resume", None),
            ("POST", f"/api/game/campaigns/{self.campaign_id}/resume", None),
            ("POST", f"/api/campaigns/{self.campaign_id}/save", None),
            ("POST", f"/api/game/campaigns/{self.campaign_id}/save", None),
        ]
        public = [
            "/api/health",
            "/api/game/health",
            "/api/character-options",
            "/api/game/character-options",
            "/api/character-creation-catalog",
            "/api/game/character-creation-catalog",
            "/api/campaign-start-options",
            "/api/game/campaign-start-options",
        ]
        async with self._client(self.closed) as client:
            for path in public:
                response = await client.get(path)
                self.assertEqual(response.status_code, 200, path)
            for method, path, body in protected:
                response = await client.request(
                    method,
                    path,
                    json=body,
                    headers={
                        "Authorization": "Bearer client-token",
                        "X-Replit-User-Id": "spoofed",
                        "X-Replit-User-Name": "spoofed",
                    },
                )
                self.assertEqual(response.status_code, 401, path)
                self.assertEqual(response.json(), _AUTH)
        self.assertEqual(
            self.manager.get(self.session_id, principal=PLAYER_A).game_session.character["current_hp"],
            self.hp,
        )
        self.assertTrue(self.store.campaign_exists(self.campaign_id, principal=PLAYER_A))

    async def test_other_player_sees_the_same_not_found_as_a_missing_record(self):
        missing_campaign = str(uuid.uuid4())
        missing_session = str(uuid.uuid4())
        async with self._client(self.other) as other, self._client(self.owner) as owner:
            foreign_campaign = await other.get(f"/api/game/campaigns/{self.campaign_id}")
            absent_campaign = await other.get(f"/api/game/campaigns/{missing_campaign}")
            self.assertEqual(foreign_campaign.status_code, 404)
            self.assertEqual(foreign_campaign.json(), absent_campaign.json())
            self.assertEqual(foreign_campaign.json(), _MISSING_CAMPAIGN)
            foreign_session = await other.get(f"/api/sessions/{self.session_id}/state")
            absent_session = await other.get(f"/api/sessions/{missing_session}/state")
            self.assertEqual(foreign_session.status_code, 404)
            self.assertEqual(foreign_session.json(), absent_session.json())
            self.assertEqual(foreign_session.json(), _MISSING_SESSION)
            own = await owner.get(f"/api/game/campaigns/{self.campaign_id}")
            self.assertEqual(own.status_code, 200, own.text)
