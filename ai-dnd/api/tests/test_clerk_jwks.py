"""Offline Clerk JWKS cache tests. Transport and DNS are injected."""

from __future__ import annotations

import base64
import json
import ssl
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa

from api.auth import AuthenticationError, Principal
from api.clerk_auth import CLERK_HTTP_INTEGRATION, ClerkSessionVerifier
from api.clerk_jwks import (
    JwksRequest,
    JwksResponse,
    JwksTransportError,
    PinnedHttpsJwksTransport,
    connect_pinned,
    keys_from_jwks,
    parse_http_jwks_message,
    pinned_public_ip,
)
from api.clerk_jwks import ClerkJwksCache
from api.tests.test_clerk_session_verifier import ISSUER, NOW, PARTY, SUBJECT, _claims, _sign


OTHER_ISSUER = "https://other.clerk.accounts.dev"
PINNED_IP = "8.8.8.8"
JWKS_URL = ISSUER + "/.well-known/jwks.json"


def _b64_int(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwk(private: rsa.RSAPrivateKey, kid: str, **overrides: object) -> dict[str, object]:
    numbers = private.public_key().public_numbers()
    entry: dict[str, object] = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64_int(numbers.n),
        "e": _b64_int(numbers.e),
    }
    entry.update(overrides)
    return entry


def _document(*entries: dict[str, object]) -> bytes:
    return json.dumps({"keys": list(entries)}, separators=(",", ":")).encode("utf-8")


def _public_resolver(_hostname: str) -> tuple[str, ...]:
    return (PINNED_IP,)


class CountingTransport:
    def __init__(self, responses: list[object], delay: float = 0) -> None:
        self._responses = list(responses)
        self._sticky: object | None = None
        self.delay = delay
        self.calls: list[JwksRequest] = []
        self._lock = threading.Lock()

    def fetch(self, request: JwksRequest) -> JwksResponse:
        with self._lock:
            self.calls.append(request)
            if self._responses:
                item = self._responses.pop(0)
                if not self._responses:
                    self._sticky = item
            else:
                item = self._sticky
        if self.delay:
            time.sleep(self.delay)
        if isinstance(item, BaseException):
            raise item
        if not isinstance(item, JwksResponse):
            raise AssertionError("missing JWKS response")
        return item


class ClerkJwksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def _cache(
        self,
        transport: CountingTransport,
        *,
        issuer: str = ISSUER,
        environment: str = "development",
        ttl: int = 30,
        interval: int = 10,
        resolver: object = _public_resolver,
        **overrides: object,
    ) -> ClerkJwksCache:
        arguments: dict[str, object] = {
            "issuer": issuer,
            "environment": environment,
            "transport": transport,
            "resolver": resolver,
            "cache_ttl_seconds": ttl,
            "refresh_interval_seconds": interval,
            "connect_timeout_seconds": 1.0,
            "read_timeout_seconds": 1.0,
        }
        arguments.update(overrides)
        return ClerkJwksCache(**arguments)  # type: ignore[arg-type]

    def _verifier(self, cache: ClerkJwksCache, *, issuer: str = ISSUER, environment: str = "development") -> ClerkSessionVerifier:
        return ClerkSessionVerifier(
            issuer=issuer,
            authorized_parties=(PARTY,),
            jwks=cache,
            environment=environment,
        )

    def _token(self, claims: dict[str, object] | None = None, header: dict[str, object] | None = None, private: rsa.RSAPrivateKey | None = None) -> str:
        return _sign(self.private if private is None else private, _claims() if claims is None else claims, header)

    def test_initial_fetch_cache_hit_and_derived_url(self) -> None:
        self.assertEqual(
            CLERK_HTTP_INTEGRATION,
            "BLOCKED: Clerk bearer mode is wired and is not a production release",
        )
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body)])
        with patch("socket.getaddrinfo", side_effect=AssertionError("dns")):
            verifier = self._verifier(self._cache(transport))
            first = verifier.verify(self._token(), now=NOW)
            second = verifier.verify(self._token(), now=NOW + 9)
        self.assertEqual(first, Principal(ISSUER, SUBJECT))
        self.assertEqual(second, Principal(ISSUER, SUBJECT))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0].url, JWKS_URL)
        self.assertEqual(transport.calls[0].pinned_ip, PINNED_IP)
        self.assertEqual(transport.calls[0].hostname, "example.clerk.accounts.dev")

    def test_cache_expiry_drops_keys_and_backs_off_during_an_outage(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([
            JwksResponse(200, body),
            TimeoutError("timeout"),
            JwksResponse(200, body),
        ])
        verifier = self._verifier(self._cache(transport, ttl=10, interval=10))
        self.assertEqual(verifier.verify(self._token(), now=NOW).subject, SUBJECT)
        self.assertEqual(verifier.verify(self._token(), now=NOW + 9).subject, SUBJECT)
        self.assertEqual(len(transport.calls), 1)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(), now=NOW + 10)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(), now=NOW + 15)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(verifier.verify(self._token(), now=NOW + 20).subject, SUBJECT)
        self.assertEqual(len(transport.calls), 3)

    def test_rotation_is_one_refresh_per_interval(self) -> None:
        first = _document(_jwk(self.private, "test-key"))
        rotated = _document(_jwk(self.private, "test-key"), _jwk(self.other, "next-key"))
        transport = CountingTransport([JwksResponse(200, first), JwksResponse(200, rotated)])
        verifier = self._verifier(self._cache(transport, ttl=30, interval=10))
        self.assertEqual(verifier.verify(self._token(), now=NOW).subject, SUBJECT)
        rotated_token = self._token(header={"kid": "next-key"}, private=self.other)
        for _ in range(20):
            with self.assertRaises(AuthenticationError):
                verifier.verify(rotated_token, now=NOW)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(verifier.verify(rotated_token, now=NOW + 10).subject, SUBJECT)
        for _ in range(10):
            with self.assertRaises(AuthenticationError):
                verifier.verify(self._token(header={"kid": "later-key"}), now=NOW + 10)
        self.assertEqual(len(transport.calls), 2)

    def test_bad_rotation_response_keeps_unexpired_keys(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body), JwksResponse(200, b"{")])
        verifier = self._verifier(self._cache(transport, ttl=30, interval=10))
        self.assertEqual(verifier.verify(self._token(), now=NOW).subject, SUBJECT)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(header={"kid": "next-key"}), now=NOW + 10)
        self.assertEqual(verifier.verify(self._token(), now=NOW + 10).subject, SUBJECT)
        self.assertEqual(len(transport.calls), 2)

    def test_invalid_signature_and_expired_token_do_not_refresh(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body)])
        verifier = self._verifier(self._cache(transport))
        forged = self._token(private=self.other)
        expired = self._token(_claims(iat=NOW - 60, nbf=NOW - 60, exp=NOW - 10))
        for _ in range(5):
            with self.assertRaises(AuthenticationError):
                verifier.verify(forged, now=NOW)
            with self.assertRaises(AuthenticationError):
                verifier.verify(expired, now=NOW)
        self.assertEqual(len(transport.calls), 1)

    def test_pending_and_invalid_status_do_not_return_a_principal(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body)])
        verifier = self._verifier(self._cache(transport))
        self.assertEqual(verifier.verify(self._token(_claims(sts="active")), now=NOW).subject, SUBJECT)
        for status in ("pending", "revoked", "ended"):
            with self.subTest(status=status):
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self._token(_claims(sts=status)), now=NOW)
        self.assertEqual(len(transport.calls), 1)

    def test_wrong_issuer_and_cross_instance_key_do_not_bind(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body)])
        cache = self._cache(transport)
        verifier = self._verifier(cache)
        foreign = self._token(_claims(iss=OTHER_ISSUER))
        with self.assertRaises(AuthenticationError):
            verifier.verify(foreign, now=NOW)
        substituted = self._token(private=self.other)
        with self.assertRaises(AuthenticationError):
            verifier.verify(substituted, now=NOW)
        self.assertEqual(len(transport.calls), 1)
        with self.assertRaises(AuthenticationError):
            self._verifier(cache, issuer=OTHER_ISSUER)
        with self.assertRaises(AuthenticationError):
            self._verifier(cache, environment="production")
        with self.assertRaises(AuthenticationError):
            ClerkSessionVerifier(
                issuer=ISSUER,
                authorized_parties=(PARTY,),
                public_keys={"test-key": "ignored"},
                jwks=cache,
                environment="development",
            )

    def test_malformed_jwks_and_bad_rsa_metadata_are_rejected(self) -> None:
        small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        valid = _jwk(self.private, "test-key")
        bodies: list[bytes] = [
            b"{",
            b"[]",
            b'{"keys":[]}',
            _document(valid, valid),
            _document(_jwk(small, "test-key")),
            _document({**valid, "alg": "HS256"}),
            _document({**valid, "kty": "oct", "k": "secret"}),
            _document({**valid, "use": "enc"}),
            _document({**valid, "key_ops": ["sign"]}),
            _document({**valid, "key_ops": ["verify", "sign"]}),
            _document({key: value for key, value in valid.items() if key != "alg"}),
            _document({key: value for key, value in valid.items() if key != "kid"}),
            _document({**valid, "d": "AQAB"}),
            _document(*[_jwk(self.private, f"key-{index}") for index in range(9)]),
        ]
        for body in bodies:
            with self.subTest(body=body[:48]):
                transport = CountingTransport([JwksResponse(200, body)])
                verifier = self._verifier(self._cache(transport))
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self._token(), now=NOW)
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self._token(), now=NOW)
                self.assertEqual(len(transport.calls), 1)

    def test_redirect_ssrf_timeout_and_oversized_responses_do_not_fetch_again(self) -> None:
        transport = CountingTransport([
            JwksResponse(302, b"", "https://169.254.169.254/latest"),
        ])
        verifier = self._verifier(self._cache(transport, max_response_bytes=1024))
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(), now=NOW)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0].url, JWKS_URL)
        self.assertNotIn("169.254.169.254", transport.calls[0].url)

        private = CountingTransport([JwksResponse(200, _document(_jwk(self.private, "test-key")))])
        private_verifier = self._verifier(self._cache(private, resolver=lambda _hostname: ("10.0.0.1", "8.8.8.8")))
        with self.assertRaises(AuthenticationError):
            private_verifier.verify(self._token(), now=NOW)
        self.assertEqual(private.calls, [])

        refused = CountingTransport([OSError("down"), JwksResponse(200, _document(_jwk(self.private, "test-key")))])
        refused_verifier = self._verifier(self._cache(refused, ttl=10, interval=10))
        with self.assertRaises(AuthenticationError):
            refused_verifier.verify(self._token(), now=NOW)
        with self.assertRaises(AuthenticationError):
            refused_verifier.verify(self._token(), now=NOW + 5)
        self.assertEqual(len(refused.calls), 1)

        oversized = CountingTransport([JwksResponse(200, b"{" + b"x" * 2048)])
        oversized_verifier = self._verifier(self._cache(oversized, max_response_bytes=1024))
        with self.assertRaises(AuthenticationError):
            oversized_verifier.verify(self._token(), now=NOW)
        self.assertEqual(len(oversized.calls), 1)

    def test_token_header_urls_and_blocked_issuers_never_reach_transport(self) -> None:
        transport = CountingTransport([JwksResponse(200, _document(_jwk(self.private, "test-key")))])
        verifier = self._verifier(self._cache(transport))
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(header={"jku": "https://evil.example/jwks.json"}), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(header={"jwk": {"kty": "RSA"}}), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(header={"x5u": "https://evil.example/cert"}), now=NOW)
        self.assertEqual(transport.calls, [])
        for issuer in (
            "https://127.0.0.1",
            "https://169.254.169.254",
            "https://metadata.google.internal",
            "https://example.clerk.accounts.dev.internal",
            "http://example.clerk.accounts.dev",
            "https://user:secret@example.clerk.accounts.dev",
            ISSUER + "/.well-known/jwks.json",
        ):
            with self.subTest(issuer=issuer):
                with self.assertRaises(AuthenticationError):
                    self._cache(transport, issuer=issuer, resolver=lambda _hostname: (_ for _ in ()).throw(AssertionError("dns")))

    def test_concurrent_verification_shares_one_refresh(self) -> None:
        body = _document(_jwk(self.private, "test-key"))
        transport = CountingTransport([JwksResponse(200, body)], delay=0.05)
        verifier = self._verifier(self._cache(transport))
        errors: list[BaseException] = []

        def verify_once() -> None:
            try:
                if verifier.verify(self._token(), now=NOW) != Principal(ISSUER, SUBJECT):
                    raise AssertionError("principal")
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=verify_once) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(transport.calls), 1)

    def test_configuration_rejects_a_mismatched_or_unsafe_jwks_url(self) -> None:
        transport = CountingTransport([])

        def refuse(_request: JwksRequest) -> JwksResponse:
            raise AssertionError("network")

        transport.fetch = refuse  # type: ignore[method-assign]
        with self.assertRaises(AuthenticationError):
            ClerkJwksCache.from_mapping(
                {
                    "issuer": ISSUER,
                    "environment": "production",
                    "jwks_url": "https://evil.example/jwks.json",
                },
                transport=transport,
            )
        cache = ClerkJwksCache.from_mapping(
            {
                "issuer": ISSUER,
                "environment": "production",
                "jwks_url": JWKS_URL,
            },
            transport=transport,
            resolver=_public_resolver,
        )
        self.assertEqual(cache.environment, "production")
        self.assertEqual(cache.jwks_url, JWKS_URL)
        for config in (
            {"issuer": ISSUER, "environment": "production", "secret_key": "sk_test"},
            {"issuer": ISSUER, "environment": "production", "issuers": [ISSUER, OTHER_ISSUER]},
            {"issuer": ISSUER, "environment": "staging"},
            {"issuer": ISSUER, "environment": "production", "cache_ttl_seconds": 10, "refresh_interval_seconds": 11},
            {"issuer": ISSUER, "environment": "production", "max_keys": 9},
        ):
            with self.subTest(config=sorted(config)):
                with self.assertRaises(AuthenticationError):
                    ClerkJwksCache.from_mapping(config, transport=transport, resolver=_public_resolver)

    def test_public_address_selection_rejects_private_and_mixed_answers(self) -> None:
        self.assertEqual(pinned_public_ip(("8.8.8.8",)), "8.8.8.8")
        self.assertEqual(pinned_public_ip(("::ffff:8.8.8.8",)), "8.8.8.8")
        for answers in (
            ("10.0.0.1",),
            ("8.8.8.8", "10.0.0.1"),
            ("169.254.169.254",),
            ("127.0.0.1",),
            (),
        ):
            with self.subTest(answers=answers):
                with self.assertRaises(AuthenticationError):
                    pinned_public_ip(answers)

    def test_https_transport_pins_ip_and_does_not_follow_redirects(self) -> None:
        opens: list[tuple[str, str]] = []
        payload = (
            b"HTTP/1.1 302 Found\r\n"
            b"Location: https://169.254.169.254/latest\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )

        class MemoryStream:
            def __init__(self) -> None:
                self.written = b""
                self._payload = payload

            def write(self, data: bytes) -> None:
                self.written += data

            def read(self, limit: int) -> bytes:
                chunk = self._payload[:limit]
                self._payload = self._payload[limit:]
                return chunk

            def close(self) -> None:
                return None

            def settimeout(self, _value: float) -> None:
                return None

        stream = MemoryStream()

        def opener(ip: str, hostname: str, _timeout: float) -> MemoryStream:
            opens.append((ip, hostname))
            return stream

        transport = PinnedHttpsJwksTransport(opener=opener)
        response = transport.fetch(JwksRequest(
            url=JWKS_URL,
            hostname="example.clerk.accounts.dev",
            pinned_ip=PINNED_IP,
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            max_bytes=1024,
        ))
        self.assertEqual(opens, [(PINNED_IP, "example.clerk.accounts.dev")])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "https://169.254.169.254/latest")
        self.assertTrue(stream.written.startswith(b"GET /.well-known/jwks.json HTTP/1.1\r\n"))
        self.assertIn(b"Host: example.clerk.accounts.dev\r\n", stream.written)
        self.assertNotIn(b"169.254.169.254", stream.written)
        with self.assertRaises(AuthenticationError):
            transport.fetch(JwksRequest(
                url="https://evil.example/jwks.json",
                hostname="evil.example",
                pinned_ip=PINNED_IP,
                connect_timeout_seconds=1,
                read_timeout_seconds=1,
                max_bytes=1024,
            ))
        with self.assertRaises(AuthenticationError):
            transport.fetch(JwksRequest(
                url=JWKS_URL,
                hostname="example.clerk.accounts.dev",
                pinned_ip="127.0.0.1",
                connect_timeout_seconds=1,
                read_timeout_seconds=1,
                max_bytes=1024,
            ))
        self.assertEqual(len(opens), 1)

    def test_response_parser_rejects_chunked_and_oversized_bodies(self) -> None:
        message = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
        )
        parsed = parse_http_jwks_message(message, 1024)
        self.assertEqual(parsed.body, b"{}")
        with self.assertRaises(AuthenticationError):
            parse_http_jwks_message(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
                1024,
            )
        with self.assertRaises(AuthenticationError):
            parse_http_jwks_message(
                b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n" + b"123456",
                1024,
            )
        with self.assertRaises(AuthenticationError):
            keys_from_jwks(b"", max_keys=8)

    def test_tls_connector_uses_the_pinned_address_and_default_verification(self) -> None:
        seen: dict[str, object] = {}

        class FakeSocket:
            def close(self) -> None:
                seen["closed"] = True

        def connect(address: tuple[str, int], timeout: float) -> FakeSocket:
            seen["address"] = address
            seen["timeout"] = timeout
            return FakeSocket()

        def wrap(self: ssl.SSLContext, sock: object, server_hostname: str | None = None, **_kwargs: object) -> FakeSocket:
            seen["sni"] = server_hostname
            seen["check_hostname"] = self.check_hostname
            seen["verify_mode"] = self.verify_mode
            return FakeSocket()

        with patch("socket.create_connection", connect), patch.object(ssl.SSLContext, "wrap_socket", wrap):
            connect_pinned(PINNED_IP, "example.clerk.accounts.dev", 1.5)
        self.assertEqual(seen["address"], (PINNED_IP, 443))
        self.assertEqual(seen["timeout"], 1.5)
        self.assertEqual(seen["sni"], "example.clerk.accounts.dev")
        self.assertIs(seen["check_hostname"], True)
        self.assertEqual(seen["verify_mode"], ssl.CERT_REQUIRED)
        with patch("socket.create_connection", side_effect=AssertionError("socket")), self.assertRaises(AuthenticationError):
            connect_pinned("10.1.2.3", "example.clerk.accounts.dev", 1.0)

    def test_transport_errors_stay_authentication_failures(self) -> None:
        transport = CountingTransport([JwksTransportError("timed out")])
        verifier = self._verifier(self._cache(transport))
        with self.assertRaises(AuthenticationError):
            verifier.verify(self._token(), now=NOW)
        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
