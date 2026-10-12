"""Clerk bearer HTTP gate. Synthetic tokens, mocked JWKS, temporary SQLite."""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import httpx
from api.auth import FailClosedAuthenticator, FixedAuthenticator, Principal, select_authenticator
from api.clerk_auth import (
    CLERK_HTTP_INTEGRATION,
    CLERK_LOGOUT_REVOCATION,
    ClerkAuthenticator,
    ClerkSessionVerifier,
)
from api.clerk_jwks import ClerkJwksCache, JwksResponse
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.test_clerk_jwks import (
    PINNED_IP,
    CountingTransport,
    _document,
    _jwk,
    _public_resolver,
)
from api.tests.test_clerk_session_verifier import ISSUER, PARTY, _claims, _sign
from cryptography.hazmat.primitives.asymmetric import rsa


OTHER_ISSUER = "https://other.clerk.accounts.dev"
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


def _database(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


def _clerk_environ(**overrides: str) -> dict[str, str]:
    values = {
        "AI_DND_AUTH_MODE": "clerk",
        "AI_DND_CLERK_ISSUER": ISSUER,
        "AI_DND_CLERK_AUTHORIZED_PARTIES": PARTY,
        "AI_DND_CLERK_ENVIRONMENT": "development",
        "AI_DND_OIDC_ISSUER": "https://issuer.test",
        "AI_DND_OIDC_AUDIENCE": "ai-dnd-test",
        "AI_DND_OIDC_CLIENT_ID": "client",
        "AI_DND_OIDC_CLIENT_SECRET": "secret",
        "AI_DND_OIDC_JWKS": '{"keys":[{"kty":"oct","kid":"test","k":"aaaa"}]}',
    }
    values.update(overrides)
    return values


class ClerkConfigurationTests(unittest.TestCase):
    def test_clerk_mode_fails_closed_without_installing_a_fixed_player(self) -> None:
        self.assertIn("BLOCKED", CLERK_HTTP_INTEGRATION)
        self.assertIn("BLOCKED", CLERK_LOGOUT_REVOCATION)
        self.assertIn("does not revoke", CLERK_LOGOUT_REVOCATION)
        with patch("sqlite3.connect", side_effect=AssertionError("database")), patch(
            "socket.create_connection", side_effect=AssertionError("network")
        ):
            selected = select_authenticator(_clerk_environ())
            self.assertIsInstance(selected, ClerkAuthenticator)
            self.assertNotIsInstance(selected, FixedAuthenticator)
            self.assertEqual(selected.issuer, ISSUER)
            self.assertEqual(selected.environment, "development")
            for overrides in (
                {"AI_DND_CLERK_ISSUER": ""},
                {"AI_DND_CLERK_SECRET_KEY": "sk_test"},
                {"AI_DND_CLERK_JWKS_URL": "https://evil.example/jwks.json"},
                {"AI_DND_AUTH_MODE": "loopback"},
                {"AI_DND_AUTH_MODE": "developer"},
            ):
                with self.subTest(overrides=overrides):
                    authenticator = select_authenticator(_clerk_environ(**overrides))
                    self.assertIsInstance(authenticator, FailClosedAuthenticator)
                    self.assertNotIsInstance(authenticator, FixedAuthenticator)


class ClerkHttpTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CampaignStore(_database(self.directory.name))
        self.store.bound_principal = Principal(ISSUER, "bound-user")
        self.manager = SessionManager(campaign_store=self.store)
        self.transport = CountingTransport([JwksResponse(200, _document(_jwk(self.private, "test-key")))])
        self.other_transport = CountingTransport([
            JwksResponse(200, _document(_jwk(self.other, "test-key"))),
        ])
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=self._authenticator(self.transport, ISSUER, self.private),
        )
        self.other_app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=self._authenticator(self.other_transport, OTHER_ISSUER, self.other),
        )
        self.token_a = self._token(self.private, "user_a", ISSUER)
        self.token_b = self._token(self.private, "user_b", ISSUER)
        self.token_same_subject = self._token(self.other, "user_a", OTHER_ISSUER)

    def _authenticator(
        self,
        transport: CountingTransport,
        issuer: str,
        _private: rsa.RSAPrivateKey,
    ) -> ClerkAuthenticator:
        cache = ClerkJwksCache(
            issuer=issuer,
            environment="development",
            transport=transport,
            resolver=_public_resolver,
            cache_ttl_seconds=300,
            refresh_interval_seconds=60,
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
        )
        verifier = ClerkSessionVerifier(
            issuer=issuer,
            authorized_parties=(PARTY,),
            jwks=cache,
            environment="development",
        )
        return ClerkAuthenticator(verifier)

    def _token(self, private: rsa.RSAPrivateKey, subject: str, issuer: str, **claims: object) -> str:
        now = int(time.time())
        payload = _claims(
            iss=issuer,
            sub=subject,
            sid=f"sess_{subject}_{issuer[-3:]}",
            iat=now,
            nbf=now,
            exp=now + 60,
        )
        payload.update(claims)
        return _sign(private, payload)

    def _client(self, app: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://isolated-testserver",
        )

    def _bearer(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def test_anonymous_requests_are_401_and_do_not_mutate(self) -> None:
        created = self.manager.create_campaign("Owned", principal=Principal(ISSUER, "user_a"))
        campaign_id, session_id, record, _metadata = created
        hp = record.game_session.character["current_hp"]
        async with self._client(self.app) as client:
            for path in ("/api/health", "/api/game/health", "/api/character-options"):
                opened = await client.get(path)
                self.assertEqual(opened.status_code, 200, path)
            anonymous = [
                ("GET", "/api/campaigns", None),
                ("GET", "/api/game/campaigns", None),
                ("POST", "/api/campaigns", {}),
                ("POST", "/api/game/campaigns", {}),
                ("GET", f"/api/campaigns/{campaign_id}", None),
                ("GET", f"/api/game/campaigns/{campaign_id}", None),
                ("DELETE", f"/api/campaigns/{campaign_id}", None),
                ("DELETE", f"/api/game/campaigns/{campaign_id}", None),
                ("POST", f"/api/campaigns/{campaign_id}/save", None),
                ("POST", f"/api/game/campaigns/{campaign_id}/save", None),
                ("POST", f"/api/sessions/{session_id}/turn", {"message": "Bekle."}),
                ("POST", f"/api/game/sessions/{session_id}/turn", {"message": "Bekle."}),
            ]
            for method, path, body in anonymous:
                response = await client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401, path)
                self.assertEqual(response.json(), _AUTH)
            query = await client.get("/api/campaigns", params={"access_token": self.token_a})
            self.assertEqual(query.status_code, 401)
            cookie = await client.get(
                "/api/campaigns",
                cookies={"ai_dnd_session": self.token_a},
            )
            self.assertEqual(cookie.status_code, 401)
            spoofed = await client.get(
                "/api/game/campaigns",
                headers={
                    "Authorization": f"Bearer {self.token_a}",
                    "X-Replit-User-Id": "user_a",
                },
            )
            self.assertEqual(spoofed.status_code, 401)
            both = await client.get(
                "/api/campaigns",
                headers=self._bearer(self.token_a),
                cookies={"ai_dnd_session": "legacy"},
            )
            self.assertEqual(both.status_code, 401)
            pending = await client.get(
                "/api/campaigns",
                headers=self._bearer(self._token(self.private, "user_a", ISSUER, sts="pending")),
            )
            self.assertEqual(pending.status_code, 401)
            malformed = await client.post(
                f"/api/sessions/{session_id}/turn",
                json={"message": "Bekle."},
                headers={"Authorization": "Bearer not-a-token"},
            )
            self.assertEqual(malformed.status_code, 401)
        reloaded = self.manager.get(session_id, principal=Principal(ISSUER, "user_a"))
        self.assertEqual(reloaded.game_session.character["current_hp"], hp)
        self.assertTrue(self.store.campaign_exists(campaign_id, principal=Principal(ISSUER, "user_a")))
        self.assertEqual(self.store.list_campaigns(principal=Principal(ISSUER, "bound-user")), [])

    async def test_two_users_are_isolated_on_both_route_aliases(self) -> None:
        async with self._client(self.app) as client, self._client(self.other_app) as other_client:
            created_a = await client.post("/api/campaigns", json={"name": "A"}, headers=self._bearer(self.token_a))
            created_b = await client.post(
                "/api/game/campaigns",
                json={"name": "B"},
                headers=self._bearer(self.token_b),
            )
            self.assertEqual(created_a.status_code, 200, created_a.text)
            self.assertEqual(created_b.status_code, 200, created_b.text)
            campaign_a = created_a.json()["campaign_id"]
            campaign_b = created_b.json()["campaign_id"]
            session_a = created_a.json()["session_id"]
            listed = await asyncio.gather(
                client.get("/api/campaigns", headers=self._bearer(self.token_a)),
                client.get("/api/game/campaigns", headers=self._bearer(self.token_b)),
                client.get(f"/api/sessions/{session_a}/state", headers=self._bearer(self.token_b)),
                client.get(f"/api/game/sessions/{session_a}/state", headers=self._bearer(self.token_a)),
            )
            self.assertEqual(listed[0].status_code, 200)
            self.assertEqual([item["campaign_id"] for item in listed[0].json()], [campaign_a])
            self.assertEqual(listed[1].status_code, 200)
            self.assertEqual([item["campaign_id"] for item in listed[1].json()], [campaign_b])
            self.assertEqual(listed[2].status_code, 404)
            self.assertEqual(listed[2].json(), _MISSING_SESSION)
            self.assertEqual(listed[3].status_code, 200)
            foreign_campaign = await client.get(
                f"/api/game/campaigns/{campaign_a}",
                headers=self._bearer(self.token_b),
            )
            missing_campaign = await client.get(
                "/api/game/campaigns/00000000-0000-4000-8000-000000000099",
                headers=self._bearer(self.token_b),
            )
            self.assertEqual(foreign_campaign.status_code, 404)
            self.assertEqual(foreign_campaign.json(), missing_campaign.json())
            self.assertEqual(foreign_campaign.json(), _MISSING_CAMPAIGN)
            same_subject = await other_client.get(
                f"/api/campaigns/{campaign_a}",
                headers=self._bearer(self.token_same_subject),
            )
            self.assertEqual(same_subject.status_code, 404)
            self.assertEqual(same_subject.json(), _MISSING_CAMPAIGN)
            hp = self.manager.get(session_a, principal=Principal(ISSUER, "user_a")).game_session.character["current_hp"]
            for method, path, body in (
                ("POST", f"/api/sessions/{session_a}/turn", {"message": "Bekle."}),
                ("POST", f"/api/game/sessions/{session_a}/turn", {"message": "Bekle."}),
                ("POST", f"/api/campaigns/{campaign_a}/save", None),
                ("POST", f"/api/game/campaigns/{campaign_a}/save", None),
            ):
                response = await client.request(method, path, json=body, headers=self._bearer(self.token_b))
                self.assertEqual(response.status_code, 404, path)
            for path in (f"/api/campaigns/{campaign_a}", f"/api/game/campaigns/{campaign_a}"):
                deleted = await client.delete(path, headers=self._bearer(self.token_b))
                self.assertEqual(deleted.status_code, 200, path)
                self.assertEqual(deleted.json()["deleted"], False)
            self.assertEqual(
                self.manager.get(session_a, principal=Principal(ISSUER, "user_a")).game_session.character["current_hp"],
                hp,
            )
            self.assertTrue(self.store.campaign_exists(campaign_a, principal=Principal(ISSUER, "user_a")))
            self.assertFalse(self.store.campaign_exists(campaign_a, principal=Principal(ISSUER, "user_b")))
            self.assertFalse(self.store.campaign_exists(campaign_a, principal=Principal(OTHER_ISSUER, "user_a")))
            self.assertEqual(self.store.list_campaigns(principal=Principal(ISSUER, "bound-user")), [])

    async def test_logout_does_not_revoke_a_bearer_token(self) -> None:
        async with self._client(self.app) as client:
            created = await client.post("/api/campaigns", json={}, headers=self._bearer(self.token_a))
            self.assertEqual(created.status_code, 200, created.text)
            logout = await client.post("/api/logout", headers={"X-AI-DND-Request": "1"})
            self.assertEqual(logout.status_code, 204)
            again = await client.get("/api/campaigns", headers=self._bearer(self.token_a))
            self.assertEqual(again.status_code, 200)
            self.assertEqual(len(again.json()), 1)

    async def test_concurrent_requests_share_one_jwks_fetch_without_blocking_the_loop(self) -> None:
        transport = CountingTransport(
            [JwksResponse(200, _document(_jwk(self.private, "test-key")))],
            delay=0.4,
        )
        app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=self._authenticator(transport, ISSUER, self.private),
        )
        async with self._client(app) as client:
            started = time.monotonic()
            tasks = [
                asyncio.create_task(client.get("/api/campaigns", headers=self._bearer(self.token_a))),
                asyncio.create_task(client.get("/api/game/campaigns", headers=self._bearer(self.token_b))),
            ]
            await asyncio.sleep(0.05)
            health = await client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertLess(time.monotonic() - started, 0.25)
            responses = await asyncio.gather(*tasks)
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0].pinned_ip, PINNED_IP)


if __name__ == "__main__":
    unittest.main()
