import unittest

from api.auth import AuthenticationError
from api.auth_diagnostics import enabled_for_request, safe_failure_category
from api.clerk_auth import ClerkAuthenticator, _bearer_token, _require_session_claims


class AuthDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_require_explicit_clerk_opt_in_on_8017(self) -> None:
        self.assertTrue(enabled_for_request("1", "clerk", ("0.0.0.0", 8017)))
        self.assertFalse(enabled_for_request(None, "clerk", ("0.0.0.0", 8017)))
        self.assertFalse(enabled_for_request("1", "clerk", ("0.0.0.0", 8008)))
        self.assertFalse(enabled_for_request("1", "oidc", ("0.0.0.0", 8017)))

    def test_only_allowlisted_constant_categories_are_loggable(self) -> None:
        self.assertEqual(safe_failure_category("issuer_rejected"), "issuer_rejected")
        self.assertEqual(safe_failure_category(None), "unclassified")

    def test_missing_bearer_maps_to_constant_internal_category(self) -> None:
        authenticator = object.__new__(ClerkAuthenticator)
        with self.assertRaises(AuthenticationError) as caught:
            authenticator.authenticate_asgi((), ())
        self.assertEqual(
            caught.exception.diagnostic_category,
            "authorization_header_missing",
        )

    def test_bearer_parse_subcategories_are_constant_and_value_free(self) -> None:
        cases = (
            ([(b"authorization", b"Bearer fake-token-a"), (b"authorization", b"Bearer fake-token-b")], (), "authorization_header_multiple"),
            ([(b"authorization", b"Basic fake-value")], (), "authorization_scheme_rejected"),
            ([(b"authorization", b"Bearer fake token")], (), "bearer_format_rejected"),
            ([(b"x-replit-user-id", b"synthetic-id"), (b"authorization", b"Bearer fake-token")], (), "identity_header_rejected"),
            ([(b"cookie", b"ai_dnd_session=synthetic")], (), "legacy_session_cookie_rejected"),
            ([(b"authorization", b"Bearer fake-token")], (("ai_dnd_session", "synthetic"),), "legacy_session_cookie_rejected"),
        )
        for headers, cookies, expected_category in cases:
            with self.subTest(category=expected_category):
                authenticator = object.__new__(ClerkAuthenticator)
                with self.assertRaises(AuthenticationError) as caught:
                    authenticator.authenticate_asgi(tuple(headers), tuple(cookies))
                self.assertEqual(caught.exception.diagnostic_category, expected_category)
                self.assertEqual(
                    safe_failure_category(caught.exception.diagnostic_category),
                    expected_category,
                )

    def test_verifier_claim_failures_have_constant_categories(self) -> None:
        base = {
            "iss": "expected-issuer",
            "exp": 2000,
            "iat": 1000,
            "nbf": 1000,
            "azp": "expected-party",
            "sid": "synthetic-session",
        }
        cases = (
            ({"iss": "other-issuer"}, "issuer_rejected"),
            ({"azp": "other-party"}, "authorized_party_rejected"),
            ({"exp": 999}, "token_time_rejected"),
            ({"sid": ""}, "session_claim_rejected"),
            ({"sts": "pending"}, "session_status_rejected"),
            ({"aud": "unexpected"}, "audience_rejected"),
        )
        for updates, expected_category in cases:
            claims = {**base, **updates}
            with self.subTest(category=expected_category):
                with self.assertRaises(AuthenticationError) as caught:
                    _require_session_claims(
                        claims,
                        issuer="expected-issuer",
                        authorized_parties=("expected-party",),
                        audience=None,
                        now=1000,
                        clock_skew_seconds=5,
                    )
                self.assertEqual(caught.exception.diagnostic_category, expected_category)


if __name__ == "__main__":
    unittest.main()
