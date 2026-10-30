"""Owner-only local play. Fails closed everywhere but a proven loopback server."""

from __future__ import annotations

import runpy
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import httpx
from api.auth import (
    AuthenticationError,
    FailClosedAuthenticator,
    FixedAuthenticator,
    Principal,
    select_authenticator,
)
from api.local_play import (
    LOCAL_PRINCIPAL,
    LocalPlayAuthenticator,
    LocalPlayRefused,
    bind_loopback_socket,
    local_authenticator_from_environ,
    uvicorn_settings,
)
import api.main as main_module
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()
_LOCAL = {"AI_DND_AUTH_MODE": "local"}
_AUTH_DETAIL = "authentication_required"
_MARKER = {"X-AI-DND-Request": "1"}


def _scope(**overrides: object) -> dict[str, object]:
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "server": ("127.0.0.1", 8008),
        "client": ("127.0.0.1", 50000),
        "headers": [(b"host", b"127.0.0.1:8008")],
    }
    scope.update(overrides)
    return scope


class ModeSelection(unittest.TestCase):
    def test_off_by_default_and_never_implicit(self) -> None:
        for environ in (
            {},
            {"AI_DND_AUTH_MODE": ""},
            {"AI_DND_AUTH_MODE": "oidc"},
            {"AI_DND_AUTH_MODE": "loopback"},
            {"AI_DND_AUTH_MODE": "LOCAL"},
            {"AI_DND_AUTH_MODE": " local"},
            {"AI_DND_AUTH_MODE": "local "},
            {"AI_DND_LOCAL": "1"},
        ):
            for listen_host in (None, "127.0.0.1", "::1"):
                with self.subTest(environ=environ, listen_host=listen_host):
                    self.assertNotIsInstance(
                        select_authenticator(environ, listen_host),
                        LocalPlayAuthenticator,
                    )

    def test_a_mode_string_alone_does_not_open_it(self) -> None:
        # Plain `uvicorn --host 0.0.0.0` reaches create_app with no proven bind.
        self.assertIsInstance(select_authenticator(_LOCAL), FailClosedAuthenticator)

    def test_create_app_alone_stays_closed_under_the_mode(self) -> None:
        with patch.dict("os.environ", _LOCAL):
            application = create_app(ollama_adapter=None)
        self.assertIs(type(application.state.authenticator), FailClosedAuthenticator)

    def test_only_a_loopback_literal_is_accepted(self) -> None:
        for listen_host in ("127.0.0.1", "::1"):
            with self.subTest(listen_host=listen_host):
                self.assertIs(
                    type(select_authenticator(_LOCAL, listen_host)),
                    LocalPlayAuthenticator,
                )
        for listen_host in (
            "0.0.0.0",
            "::",
            "",
            "localhost",
            "192.168.1.10",
            "10.0.0.5",
            "100.64.0.1",
            "127.0.0.1.evil.example",
            "::ffff:192.168.1.10",
            None,
        ):
            with self.subTest(listen_host=listen_host):
                self.assertIs(
                    type(select_authenticator(_LOCAL, listen_host)),
                    FailClosedAuthenticator,
                )

    def test_the_selector_itself_requires_the_mode(self) -> None:
        self.assertIs(
            type(local_authenticator_from_environ({}, "127.0.0.1")),
            FailClosedAuthenticator,
        )

    def test_a_production_configuration_keeps_it_closed(self) -> None:
        for marker in (
            {"REPL_ID": "abc"},
            {"REPLIT_DEPLOYMENT": "1"},
            {"REPLIT_DEV_DOMAIN": "x.replit.dev"},
            {"REPLIT_DOMAINS": "x.replit.app"},
            {"REPLIT_APP_DOMAIN": "x.replit.app"},
            {"NODE_ENV": "production"},
            {"AI_DND_CLERK_ENVIRONMENT": "production"},
        ):
            with self.subTest(marker=marker):
                self.assertIs(
                    type(select_authenticator({**_LOCAL, **marker}, "127.0.0.1")),
                    FailClosedAuthenticator,
                )

    def test_clerk_and_oidc_selection_are_unchanged_by_the_listen_host(self) -> None:
        self.assertIs(
            type(select_authenticator({"AI_DND_AUTH_MODE": "clerk"}, "127.0.0.1")),
            FailClosedAuthenticator,
        )
        self.assertIs(
            type(select_authenticator({"AI_DND_AUTH_MODE": "loopback"}, "127.0.0.1")),
            FailClosedAuthenticator,
        )


class BindRefusal(unittest.TestCase):
    def test_a_non_loopback_bind_is_refused_before_any_socket_exists(self) -> None:
        for host in ("0.0.0.0", "::", "192.168.1.10", "localhost", "", "127.0.0.1 "):
            with self.subTest(host=host), patch("api.local_play.socket.socket") as opened:
                with self.assertRaises(LocalPlayRefused):
                    bind_loopback_socket(host, 8008)
                opened.assert_not_called()

    def test_the_reported_socket_address_decides_not_the_requested_one(self) -> None:
        fake = patch("api.local_play.socket.socket").start()
        self.addCleanup(patch.stopall)
        fake.return_value.getsockname.return_value = ("0.0.0.0", 8008)
        with self.assertRaises(LocalPlayRefused):
            bind_loopback_socket("127.0.0.1", 8008)
        fake.return_value.close.assert_called_once()

    def bind_with_platform(self, platform: str) -> Any:
        opened = patch("api.local_play.socket.socket").start()
        self.addCleanup(patch.stopall)
        opened.return_value.getsockname.return_value = ("127.0.0.1", 8008)
        with (
            patch("api.local_play.sys.platform", platform),
            patch("api.local_play.socket.SOL_SOCKET", 65535, create=True),
            patch("api.local_play.socket.SO_EXCLUSIVEADDRUSE", -5, create=True),
        ):
            bind_loopback_socket("127.0.0.1", 8008)
        return opened.return_value

    def test_windows_claims_the_port_exclusively_before_it_binds(self) -> None:
        listener = self.bind_with_platform("win32")
        names = [call[0] for call in listener.method_calls]
        self.assertLess(names.index("setsockopt"), names.index("bind"))
        listener.setsockopt.assert_called_once_with(65535, -5, 1)

    def test_other_systems_keep_the_default_exclusive_bind(self) -> None:
        self.bind_with_platform("linux").setsockopt.assert_not_called()

    def test_a_refused_exclusive_claim_closes_the_socket(self) -> None:
        opened = patch("api.local_play.socket.socket").start()
        self.addCleanup(patch.stopall)
        opened.return_value.setsockopt.side_effect = OSError("refused")
        with (
            patch("api.local_play.sys.platform", "win32"),
            patch("api.local_play.socket.SO_EXCLUSIVEADDRUSE", -5, create=True),
        ):
            with self.assertRaises(OSError):
                bind_loopback_socket("127.0.0.1", 8008)
        opened.return_value.close.assert_called_once()

    def test_uvicorn_keeps_the_real_peer_and_ignores_proxy_headers(self) -> None:
        settings = uvicorn_settings()
        self.assertIs(settings["proxy_headers"], False)
        self.assertEqual(settings["forwarded_allow_ips"], "")
        self.assertEqual(settings["workers"], 1)
        self.assertIs(settings["reload"], False)

    def test_refused_when_the_mode_is_not_set(self) -> None:
        from api.local_play import prepare_listener

        with patch("api.local_play.bind_loopback_socket") as bind:
            with self.assertRaises(LocalPlayRefused):
                prepare_listener({}, "127.0.0.1", 8008)
            bind.assert_not_called()

    def test_refused_under_a_production_configuration_before_binding(self) -> None:
        from api.local_play import prepare_listener

        with patch("api.local_play.bind_loopback_socket") as bind:
            with self.assertRaises(LocalPlayRefused):
                prepare_listener({**_LOCAL, "REPL_ID": "abc"}, "127.0.0.1", 8008)
            bind.assert_not_called()

    def test_a_legal_listener_returns_the_local_authenticator_for_its_bound_address(self) -> None:
        from api.local_play import prepare_listener

        fake_socket = unittest.mock.Mock(spec=socket.socket)
        fake_socket.getsockname.return_value = ("127.0.0.1", 8008)
        with patch("api.local_play.bind_loopback_socket", return_value=fake_socket):
            listener, authenticator = prepare_listener(_LOCAL, "127.0.0.1", 8008)
        self.assertIs(listener, fake_socket)
        self.assertIs(type(authenticator), LocalPlayAuthenticator)


class Launcher(unittest.TestCase):
    def test_module_execution_uses_the_importable_module(self) -> None:
        # Under -m this file is __main__, and a class defined there is not the
        # class the middleware compares against: the mode would stay closed.
        with patch("api.local_play.main", return_value=0) as entry:
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_module("api.local_play", run_name="__main__")
        self.assertEqual(stopped.exception.code, 0)
        entry.assert_called_once_with()

    def test_main_serves_the_bound_socket_with_the_local_authenticator(self) -> None:
        import api.local_play as local_play

        listener = unittest.mock.Mock(spec=socket.socket)
        authenticator = LocalPlayAuthenticator("127.0.0.1")
        with (
            patch.dict("os.environ", _LOCAL),
            patch.object(local_play, "prepare_listener", return_value=(listener, authenticator)),
            patch("uvicorn.Server") as server,
            patch("uvicorn.Config") as config,
            patch("api.main.create_app") as create,
        ):
            self.assertEqual(local_play.main(["--port", "8008"]), 0)
        create.assert_called_once_with(authenticator=authenticator)
        self.assertIs(type(create.call_args.kwargs["authenticator"]), main_module.LocalPlayAuthenticator)
        config.assert_called_once_with(create.return_value, **uvicorn_settings())
        server.return_value.run.assert_called_once_with(sockets=[listener])

    def test_main_returns_an_error_and_serves_nothing_when_refused(self) -> None:
        import api.local_play as local_play

        with patch.dict("os.environ", {}, clear=True), patch("uvicorn.Server") as server:
            self.assertEqual(local_play.main(["--host", "0.0.0.0"]), 2)
        server.assert_not_called()


class RequestGate(unittest.TestCase):
    def setUp(self) -> None:
        self.authenticator = LocalPlayAuthenticator("127.0.0.1")

    def _refused(self, **overrides: object) -> None:
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate_asgi(_scope(**overrides))

    def test_a_loopback_request_gets_the_fixed_principal(self) -> None:
        self.assertEqual(self.authenticator.authenticate_asgi(_scope()), LOCAL_PRINCIPAL)
        for host in (b"localhost:8008", b"localhost", b"127.0.0.1", b"[::1]", b"[::1]:8008"):
            with self.subTest(host=host):
                self.assertEqual(
                    self.authenticator.authenticate_asgi(_scope(headers=[(b"host", host)])),
                    LOCAL_PRINCIPAL,
                )

    def test_the_principal_is_fixed_not_a_clerk_or_oidc_identity(self) -> None:
        self.assertEqual(LOCAL_PRINCIPAL, Principal("urn:ai-dnd:local-play", "owner"))

    def test_no_request_context_means_no_principal(self) -> None:
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate()

    def test_a_non_loopback_client_is_refused(self) -> None:
        for client in (("192.168.1.20", 5), ("8.8.8.8", 5), ("::ffff:10.0.0.1", 5), ("testclient", 5), None, ()):
            with self.subTest(client=client):
                self._refused(client=client)

    def test_a_mapped_loopback_client_is_loopback(self) -> None:
        self.assertEqual(
            self.authenticator.authenticate_asgi(_scope(client=("::ffff:127.0.0.1", 5))),
            LOCAL_PRINCIPAL,
        )

    def test_a_request_on_another_local_address_is_refused(self) -> None:
        for server in (("192.168.1.10", 8008), ("0.0.0.0", 8008), ("::1", 8008), None):
            with self.subTest(server=server):
                self._refused(server=server)

    def test_a_forged_host_is_refused(self) -> None:
        for host in (
            b"evil.example",
            b"evil.example:8008",
            b"127.0.0.1.evil.example",
            b"localhost.evil.example",
            b"127.0.0.2",
            b"foo.localhost",
            b"127.0.0.1@evil.example",
            b"192.168.1.10:8008",
            b"127.0.0.1:port",
            b"127.0.0.1:",
            b"",
        ):
            with self.subTest(host=host):
                self._refused(headers=[(b"host", host)])

    def test_a_missing_or_repeated_host_is_refused(self) -> None:
        self._refused(headers=[])
        self._refused(headers=[(b"host", b"127.0.0.1"), (b"host", b"localhost")])

    def test_a_forwarded_request_is_refused(self) -> None:
        for name in (
            b"forwarded",
            b"x-forwarded-for",
            b"x-forwarded-host",
            b"x-forwarded-proto",
            b"x-real-ip",
            b"cf-connecting-ip",
            b"true-client-ip",
        ):
            with self.subTest(name=name):
                self._refused(headers=[(b"host", b"127.0.0.1:8008"), (name, b"127.0.0.1")])

    def test_a_cross_site_browser_request_is_refused(self) -> None:
        for extra in (
            (b"origin", b"https://evil.example"),
            (b"origin", b"http://127.0.0.1.evil.example:22785"),
            (b"origin", b"https://127.0.0.1:22785"),
            (b"origin", b"null"),
            (b"sec-fetch-site", b"cross-site"),
            (b"sec-fetch-site", b"same-site"),
        ):
            with self.subTest(extra=extra):
                self._refused(headers=[(b"host", b"127.0.0.1:8008"), extra])

    def test_the_local_vite_origin_is_accepted(self) -> None:
        for origin in (b"http://127.0.0.1:22785", b"http://localhost:22785", b"http://[::1]:22785"):
            with self.subTest(origin=origin):
                principal = self.authenticator.authenticate_asgi(
                    _scope(
                        method="POST",
                        headers=[
                            (b"host", b"127.0.0.1:8008"),
                            (b"origin", origin),
                            (b"sec-fetch-site", b"same-origin"),
                            (b"x-ai-dnd-request", b"1"),
                        ],
                    )
                )
                self.assertEqual(principal, LOCAL_PRINCIPAL)

    def test_a_write_needs_the_request_marker(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self._refused(method=method)

    def test_a_malformed_scope_is_refused_not_raised_through(self) -> None:
        self._refused(headers=None)
        self._refused(headers=[(b"host", "127.0.0.1")])
        self._refused(server=())
        with self.assertRaises(AuthenticationError):
            self.authenticator.authenticate_asgi({"type": "http"})


class HttpBoundary(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = (Path(self.directory.name) / "campaigns.sqlite3").resolve()
        self.assertNotEqual(path, _LIVE)
        self.store = CampaignStore(path)
        self.manager = SessionManager(campaign_store=self.store)
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=LocalPlayAuthenticator("127.0.0.1"),
        )

    def _client(
        self,
        app: object | None = None,
        *,
        peer: tuple[str, int] = ("127.0.0.1", 50000),
        base_url: str = "http://127.0.0.1:8008",
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app or self.app, client=peer),
            base_url=base_url,
        )

    async def test_the_owner_can_play_without_a_token(self) -> None:
        async with self._client() as client:
            created = await client.post("/api/campaigns", json={"name": "Yerel"}, headers=_MARKER)
            self.assertEqual(created.status_code, 200, created.text)
            listed = await client.get("/api/game/campaigns")
        self.assertEqual(
            [item["campaign_id"] for item in listed.json()],
            [created.json()["campaign_id"]],
        )
        self.assertTrue(
            self.store.campaign_exists(created.json()["campaign_id"], principal=LOCAL_PRINCIPAL)
        )

    async def test_a_forged_host_is_401_on_private_and_public_paths(self) -> None:
        async with self._client(base_url="http://evil.example:8008") as client:
            for path in ("/api/campaigns", "/api/health", "/api/character-creation-catalog", "/openapi.json"):
                response = await client.get(path)
                self.assertEqual(response.status_code, 401, path)
                self.assertEqual(response.json()["detail"]["code"], _AUTH_DETAIL)

    async def test_a_forged_host_header_on_a_loopback_url_is_401(self) -> None:
        async with self._client() as client:
            response = await client.get("/api/campaigns", headers={"Host": "evil.example"})
        self.assertEqual(response.status_code, 401)

    async def test_a_lan_client_is_401_and_cannot_write(self) -> None:
        async with self._client(peer=("192.168.1.20", 50000)) as client:
            response = await client.post("/api/campaigns", json={"name": "LAN"}, headers=_MARKER)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.store.list_campaigns(principal=LOCAL_PRINCIPAL), [])

    async def test_a_lan_server_address_is_401_even_from_loopback_peer(self) -> None:
        async with self._client(base_url="http://192.168.1.10:8008") as client:
            response = await client.get("/api/campaigns", headers={"Host": "127.0.0.1:8008"})
        self.assertEqual(response.status_code, 401)

    async def test_a_browser_csrf_write_is_401(self) -> None:
        async with self._client() as client:
            no_marker = await client.post("/api/campaigns", json={"name": "CSRF"})
            evil_origin = await client.post(
                "/api/campaigns",
                json={"name": "CSRF"},
                headers={**_MARKER, "Origin": "https://evil.example"},
            )
        self.assertEqual(no_marker.status_code, 401)
        self.assertEqual(evil_origin.status_code, 401)
        self.assertEqual(self.store.list_campaigns(principal=LOCAL_PRINCIPAL), [])

    async def test_client_supplied_identity_never_changes_the_owner(self) -> None:
        async with self._client() as client:
            created = await client.post(
                "/api/campaigns",
                json={"name": "Yerel"},
                headers={
                    **_MARKER,
                    "Authorization": "Bearer forged",
                    "X-Replit-User-Id": "someone-else",
                    "X-Forwarded-User": "someone-else",
                },
                cookies={"ai_dnd_session": "forged"},
            )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(
            self.store.campaign_exists(created.json()["campaign_id"], principal=LOCAL_PRINCIPAL)
        )
        self.assertFalse(
            self.store.campaign_exists(
                created.json()["campaign_id"],
                principal=Principal("urn:ai-dnd:local-play", "someone-else"),
            )
        )

    async def test_campaign_ownership_is_not_bypassed_in_either_direction(self) -> None:
        clerk_user = Principal("https://clerk.example", "user_a")
        campaign_a, session_a, record, _metadata = self.manager.create_campaign(
            "Clerk",
            principal=clerk_user,
        )
        hp = record.game_session.character["current_hp"]
        clerk_app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=FixedAuthenticator(clerk_user),
        )
        async with self._client() as local, self._client(clerk_app) as clerk:
            self.assertEqual((await local.get("/api/campaigns")).json(), [])
            for method, path, body in (
                ("GET", f"/api/campaigns/{campaign_a}", None),
                ("GET", f"/api/sessions/{session_a}/state", None),
                ("POST", f"/api/campaigns/{campaign_a}/save", None),
                ("POST", f"/api/sessions/{session_a}/turn", {"message": "Bekle."}),
            ):
                response = await local.request(method, path, json=body, headers=_MARKER)
                self.assertEqual(response.status_code, 404, path)
            deleted = await local.delete(f"/api/campaigns/{campaign_a}", headers=_MARKER)
            self.assertEqual(deleted.json()["deleted"], False)

            own = await local.post("/api/campaigns", json={"name": "Yerel"}, headers=_MARKER)
            self.assertEqual(own.status_code, 200, own.text)
            own_id = own.json()["campaign_id"]
            self.assertEqual((await clerk.get(f"/api/campaigns/{own_id}")).status_code, 404)
            self.assertEqual(
                [item["campaign_id"] for item in (await clerk.get("/api/campaigns")).json()],
                [campaign_a],
            )
        self.assertTrue(self.store.campaign_exists(campaign_a, principal=clerk_user))
        self.assertFalse(self.store.campaign_exists(campaign_a, principal=LOCAL_PRINCIPAL))
        self.assertEqual(
            self.manager.get(session_a, principal=clerk_user).game_session.character["current_hp"],
            hp,
        )


if __name__ == "__main__":
    unittest.main()
