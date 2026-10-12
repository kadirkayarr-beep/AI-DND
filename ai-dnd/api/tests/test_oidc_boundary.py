"""OIDC stays closed unless every server setting is present. No live issuer calls."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

import game
import httpx
from api.auth import (
    OIDC_PRODUCTION_STATUS,
    AuthenticationError,
    FailClosedAuthenticator,
    OidcAuthenticator,
    OidcSettings,
    Principal,
    authenticate,
    oidc_settings_from_environ,
    select_authenticator,
    session_cookie_parameters,
    verify_oidc_token,
)
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


_SECRET = b"local-test-secret"
_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _jwks() -> str:
    return json.dumps({"keys": [{
        "kty": "oct", "kid": "test", "alg": "HS256", "k": _b64(_SECRET),
    }]})


def _settings() -> OidcSettings:
    parsed = oidc_settings_from_environ({
        "AI_DND_OIDC_ISSUER": "https://issuer.test",
        "AI_DND_OIDC_AUDIENCE": "ai-dnd-test",
        "AI_DND_OIDC_CLIENT_ID": "client",
        "AI_DND_OIDC_CLIENT_SECRET": "secret",
        "AI_DND_OIDC_JWKS": _jwks(),
    })
    assert parsed is not None
    return parsed


def _token(payload: dict, *, secret: bytes = _SECRET, kid: str = "test", alg: str = "HS256") -> str:
    header = _b64(json.dumps({"alg": alg, "kid": kid}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(secret, f"{header}.{body}".encode("ascii"), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def _claims(**changes) -> dict:
    payload = {
        "iss": "https://issuer.test",
        "aud": "ai-dnd-test",
        "sub": "player-a",
        "exp": 2_000_000_000,
    }
    payload.update(changes)
    return payload


class OidcBoundaryTests(unittest.TestCase):
    def test_production_oidc_is_not_complete(self):
        self.assertEqual(OIDC_PRODUCTION_STATUS, "BLOCKED: Replit verification required")

    def test_incomplete_configuration_stays_fail_closed(self):
        complete = {
            "AI_DND_OIDC_ISSUER": "https://issuer.test",
            "AI_DND_OIDC_AUDIENCE": "ai-dnd-test",
            "AI_DND_OIDC_CLIENT_ID": "client",
            "AI_DND_OIDC_CLIENT_SECRET": "secret",
            "AI_DND_OIDC_JWKS": _jwks(),
        }
        self.assertIsNone(oidc_settings_from_environ({}))
        for name in complete:
            partial = dict(complete)
            partial[name] = ""
            self.assertIsNone(oidc_settings_from_environ(partial))
            self.assertIsInstance(select_authenticator(partial), FailClosedAuthenticator)

    def test_token_checks_signature_issuer_audience_and_expiry(self):
        settings = _settings()
        verifier = OidcAuthenticator(settings)
        principal = verifier.authenticate(_token(_claims()), now=1_700_000_000)
        self.assertEqual(principal, Principal("https://issuer.test", "player-a"))
        for payload in (
            _claims(iss="https://other.test"),
            _claims(aud="other-audience"),
            _claims(exp=1_600_000_000),
            _claims(sub=""),
        ):
            with self.assertRaises(AuthenticationError):
                verify_oidc_token(_token(payload), settings, now=1_700_000_000)
        tampered = _token(_claims())[:-2] + "aa"
        with self.assertRaises(AuthenticationError):
            verify_oidc_token(tampered, settings, now=1_700_000_000)
        with self.assertRaises(AuthenticationError):
            verify_oidc_token(_token(_claims(), alg="none"), settings, now=1_700_000_000)

    def test_client_headers_are_not_a_token(self):
        with self.assertRaises(AuthenticationError):
            authenticate(OidcAuthenticator(_settings()), {
                "headers": {
                    "Authorization": "Bearer " + _token(_claims()),
                    "X-Replit-User-Id": "player-a",
                },
            })

    def test_loopback_stays_closed_even_when_the_host_string_is_local(self):
        local = {
            "AI_DND_AUTH_MODE": "loopback",
            "AI_DND_LISTEN_HOST": "127.0.0.1",
            "AI_DND_LOOPBACK_ISSUER": "loopback-issuer",
            "AI_DND_LOOPBACK_SUBJECT": "loopback-player",
        }
        self.assertIsInstance(select_authenticator(local, "127.0.0.1"), FailClosedAuthenticator)
        self.assertIsInstance(select_authenticator(local, "0.0.0.0"), FailClosedAuthenticator)
        self.assertIsInstance(select_authenticator(local, "localhost"), FailClosedAuthenticator)
        replit = dict(local, REPL_ID="repl-1")
        self.assertIsInstance(select_authenticator(replit, "127.0.0.1"), FailClosedAuthenticator)
        self.assertIsInstance(
            select_authenticator({"AI_DND_AUTH_MODE": "loopback"}, "127.0.0.1"),
            FailClosedAuthenticator,
        )

    def test_cookie_is_httponly_and_secure_only_on_https(self):
        plain = session_cookie_parameters(False)
        protected = session_cookie_parameters(True)
        self.assertTrue(plain["httponly"])
        self.assertEqual(plain["samesite"], "lax")
        self.assertFalse(plain["secure"])
        self.assertTrue(protected["secure"])


class OidcHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_cookie_session_ignores_spoofed_headers_and_logout_clears_it(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = (Path(directory.name) / "campaigns.sqlite3").resolve()
        if path == _LIVE:
            raise RuntimeError("Refusing to use the live campaign database.")
        manager = SessionManager(campaign_store=CampaignStore(path))
        app = create_app(
            session_manager=manager,
            ollama_adapter=None,
            authenticator=OidcAuthenticator(_settings()),
        )
        token = _token(_claims())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://isolated-testserver",
        ) as client:
            spoofed = await client.get("/api/campaigns", headers={
                "Authorization": "Bearer client-token",
                "X-Replit-User-Id": "player-a",
            })
            self.assertEqual(spoofed.status_code, 401)
            listed = await client.get("/api/campaigns", cookies={"ai_dnd_session": token})
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(listed.json(), [])
            missing_marker = await client.post(
                "/api/campaigns",
                json={},
                cookies={"ai_dnd_session": token},
            )
            self.assertEqual(missing_marker.status_code, 401)
            logout = await client.post("/api/logout", headers={"X-AI-DND-Request": "1"})
            self.assertEqual(logout.status_code, 204)
            self.assertIn("httponly", logout.headers["set-cookie"].lower())
            self.assertIn("secure", logout.headers["set-cookie"].lower())
            self.assertIn("samesite=lax", logout.headers["set-cookie"].lower())
