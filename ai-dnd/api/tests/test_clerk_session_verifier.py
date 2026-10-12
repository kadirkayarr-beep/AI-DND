"""Offline Clerk session-token checks. No HTTP app and no campaign database."""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from api.auth import AuthenticationError, Principal
from api.clerk_auth import CLERK_HTTP_INTEGRATION, ClerkSessionVerifier


ISSUER = "https://example.clerk.accounts.dev"
PARTY = "http://localhost:5173"
SUBJECT = "user_synthetic"
SESSION = "sess_synthetic"
NOW = 1_700_000_000


def _pem(key: rsa.RSAPrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "azp": PARTY,
        "sid": SESSION,
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + 60,
    }
    claims.update(overrides)
    return claims


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _sign(
    private: rsa.RSAPrivateKey,
    claims: dict[str, object],
    header: dict[str, object] | None = None,
) -> str:
    token_header = {"alg": "RS256", "typ": "JWT", "kid": "test-key"}
    if header is not None:
        token_header.update(header)
    signing = _b64(json.dumps(token_header, separators=(",", ":")).encode()) + "." + _b64(
        json.dumps(claims, separators=(",", ":")).encode()
    )
    signature = private.sign(signing.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return signing + "." + _b64(signature)


class ClerkSessionVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = _pem(cls.private)
        cls.other_pem = _pem(cls.other)

    def verifier(self, **overrides: object) -> ClerkSessionVerifier:
        arguments: dict[str, object] = {
            "issuer": ISSUER,
            "authorized_parties": (PARTY, "https://play.example"),
            "public_keys": {"test-key": self.pem},
        }
        arguments.update(overrides)
        return ClerkSessionVerifier(**arguments)  # type: ignore[arg-type]

    def token(self, claims: dict[str, object] | None = None, header: dict[str, object] | None = None) -> str:
        return _sign(self.private, _claims() if claims is None else claims, header)

    def test_pinned_pyjwt_skips_issuer_unless_the_caller_supplies_one(self) -> None:
        self.assertEqual(jwt.__version__, "2.15.1")
        token = self.token(_claims(iss="https://attacker.example"))
        accepted = jwt.decode(
            token,
            self.pem,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False, "verify_nbf": False, "verify_iat": False},
        )
        self.assertEqual(accepted["iss"], "https://attacker.example")
        with self.assertRaises(jwt.InvalidIssuerError):
            jwt.decode(
                token,
                self.pem,
                algorithms=["RS256"],
                issuer=ISSUER,
                options={"verify_aud": False, "verify_exp": False, "verify_nbf": False, "verify_iat": False},
            )

    def test_valid_session_token_returns_only_the_configured_principal(self) -> None:
        self.assertEqual(
            CLERK_HTTP_INTEGRATION,
            "BLOCKED: Clerk bearer mode is wired and is not a production release",
        )
        with patch("socket.create_connection", side_effect=AssertionError("network")), patch(
            "socket.getaddrinfo", side_effect=AssertionError("network")
        ):
            principal = self.verifier().verify(self.token(), now=NOW)
        self.assertEqual(principal, Principal(ISSUER, SUBJECT))
        self.assertIs(type(principal), Principal)

    def test_signature_key_and_algorithm_failures(self) -> None:
        verifier = self.verifier()
        signed_by_other = _sign(self.other, _claims())
        with self.assertRaises(AuthenticationError):
            verifier.verify(signed_by_other, now=NOW)
        tampered = self.token()[:-2] + ("A" if self.token()[-2] != "A" else "B") + self.token()[-1]
        with self.assertRaises(AuthenticationError):
            verifier.verify(tampered, now=NOW)
        hs256 = jwt.encode(
            _claims(),
            "not-the-rsa-key-and-not-a-public-key",
            algorithm="HS256",
            headers={"kid": "test-key"},
        )
        with self.assertRaises(AuthenticationError):
            verifier.verify(hs256, now=NOW)
        unsigned = _b64(b'{"alg":"none","typ":"JWT","kid":"test-key"}') + "." + _b64(b"{}") + "."
        with self.assertRaises(AuthenticationError):
            verifier.verify(unsigned, now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(header={"alg": "RS384"}), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(header={"kid": "other-key"}), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(header={"kid": None}), now=NOW)

    def test_header_must_be_a_jwt_and_must_not_name_a_key_location(self) -> None:
        verifier = self.verifier()
        for header in (
            {"typ": "at+jwt"},
            {"typ": None},
            {"jku": "https://evil.example/jwks.json"},
            {"jwk": {"kty": "RSA"}},
            {"x5u": "https://evil.example/cert"},
            {"crit": ["b64"]},
        ):
            with self.subTest(header=header):
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self.token(header=header), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify("not-a-token", now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify("@@@.@@@.@@@", now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify("", now=NOW)

    def test_issuer_subject_and_session_claims(self) -> None:
        verifier = self.verifier()
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iss="https://other.clerk.accounts.dev")), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iss=ISSUER.upper())), now=NOW)
        for subject in ("", " user", "user ", "user\n", None, 12):
            with self.subTest(subject=subject):
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self.token(_claims(sub=subject)), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(sid="")), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token({key: value for key, value in _claims().items() if key != "sid"}), now=NOW)

    def test_expiry_nbf_and_iat_use_the_supplied_clock(self) -> None:
        verifier = self.verifier()
        self.assertEqual(
            verifier.verify(self.token(_claims(iat=NOW - 60, nbf=NOW - 60, exp=NOW - 4)), now=NOW).subject,
            SUBJECT,
        )
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iat=NOW - 60, nbf=NOW - 60, exp=NOW - 5)), now=NOW)
        self.assertEqual(
            verifier.verify(self.token(_claims(nbf=NOW + 5, exp=NOW + 60)), now=NOW).subject,
            SUBJECT,
        )
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(nbf=NOW + 6, exp=NOW + 60)), now=NOW)
        self.assertEqual(
            verifier.verify(self.token(_claims(iat=NOW + 5, nbf=NOW, exp=NOW + 60)), now=NOW).subject,
            SUBJECT,
        )
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iat=NOW + 6, nbf=NOW, exp=NOW + 60)), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(exp=True)), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iat=NOW + 0.5)), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(exp=NOW + 24 * 60 * 60 + 1)), now=NOW)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(nbf=NOW + 61, exp=NOW + 120)), now=NOW)

    def test_zero_skew_rejects_the_boundary_pyjwt_treats_as_expired(self) -> None:
        verifier = self.verifier(clock_skew_seconds=0)
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(_claims(iat=NOW - 60, nbf=NOW - 60, exp=NOW)), now=NOW)
        self.assertEqual(
            verifier.verify(self.token(_claims(iat=NOW - 60, nbf=NOW - 60, exp=NOW + 1)), now=NOW).subject,
            SUBJECT,
        )

    def test_azp_must_be_present_and_approved(self) -> None:
        verifier = self.verifier()
        self.assertEqual(
            verifier.verify(self.token(_claims(azp="https://play.example")), now=NOW).subject,
            SUBJECT,
        )
        for azp in (None, "", "http://evil.example", "http://localhost:5173/", "http://localhost:5173/app"):
            with self.subTest(azp=azp):
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self.token(_claims(azp=azp)), now=NOW)
        claims = {key: value for key, value in _claims().items() if key != "azp"}
        with self.assertRaises(AuthenticationError):
            verifier.verify(self.token(claims), now=NOW)

    def test_audience_is_optional_until_configured(self) -> None:
        self.assertEqual(self.verifier().verify(self.token(), now=NOW).subject, SUBJECT)
        with self.assertRaises(AuthenticationError):
            self.verifier().verify(self.token(_claims(aud="clerk-frontend")), now=NOW)
        configured = self.verifier(audience="clerk-frontend")
        with self.assertRaises(AuthenticationError):
            configured.verify(self.token(), now=NOW)
        with self.assertRaises(AuthenticationError):
            configured.verify(self.token(_claims(aud="other-api")), now=NOW)
        with self.assertRaises(AuthenticationError):
            configured.verify(self.token(_claims(aud=["clerk-frontend", "other-api"])), now=NOW)
        self.assertEqual(
            configured.verify(self.token(_claims(aud="clerk-frontend")), now=NOW).subject,
            SUBJECT,
        )

    def test_missing_or_unsafe_configuration_fails_closed(self) -> None:
        for arguments in (
            {"issuer": "http://example.clerk.accounts.dev"},
            {"issuer": ISSUER + "/"},
            {"issuer": "https://user:secret@example.clerk.accounts.dev"},
            {"authorized_parties": ()},
            {"authorized_parties": ("not a url",)},
            {"public_keys": {}},
            {"clock_skew_seconds": 61},
            {"clock_skew_seconds": -1},
            {"clock_skew_seconds": True},
            {"audience": ""},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(AuthenticationError):
                    self.verifier(**arguments)
        small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        with self.assertRaises(AuthenticationError):
            self.verifier(public_keys={"test-key": _pem(small)})
        with self.assertRaises(AuthenticationError):
            ClerkSessionVerifier.from_mapping({"issuer": ISSUER})
        with self.assertRaises(AuthenticationError):
            ClerkSessionVerifier.from_mapping({
                "issuer": ISSUER,
                "authorized_parties": [PARTY],
                "public_keys": {"test-key": self.pem},
                "jwks_url": "https://example.clerk.accounts.dev/.well-known/jwks.json",
            })

    def test_mapping_configuration_verifies_without_reading_the_process_environment(self) -> None:
        verifier = ClerkSessionVerifier.from_mapping({
            "issuer": ISSUER,
            "authorized_parties": [PARTY],
            "public_keys": {"test-key": self.pem},
            "clock_skew_seconds": 5,
        })
        self.assertEqual(verifier.verify(self.token(), now=NOW), Principal(ISSUER, SUBJECT))

    def test_session_status_rejects_pending_and_other_explicit_values(self) -> None:
        verifier = self.verifier()
        self.assertEqual(verifier.verify(self.token(), now=NOW).subject, SUBJECT)
        self.assertEqual(verifier.verify(self.token(_claims(sts="active")), now=NOW).subject, SUBJECT)
        for status in ("pending", "revoked", "expired", "ACTIVE", "", None, 1, True, ["active"]):
            with self.subTest(status=status):
                with self.assertRaises(AuthenticationError):
                    verifier.verify(self.token(_claims(sts=status)), now=NOW)

    def test_kid_selects_only_an_injected_key(self) -> None:
        verifier = self.verifier(public_keys={"test-key": self.pem, "other-key": self.other_pem})
        self.assertEqual(verifier.verify(self.token(), now=NOW).subject, SUBJECT)
        swapped = _sign(self.other, _claims(), {"kid": "test-key"})
        with self.assertRaises(AuthenticationError):
            verifier.verify(swapped, now=NOW)
        matching = _sign(self.other, _claims(), {"kid": "other-key"})
        self.assertEqual(verifier.verify(matching, now=NOW).subject, SUBJECT)


if __name__ == "__main__":
    unittest.main()
