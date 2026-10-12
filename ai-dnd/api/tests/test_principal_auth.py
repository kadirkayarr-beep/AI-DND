"""Isolated principal authentication. No campaigns, HTTP app, or model calls."""
import unittest

from api.auth import (
    AuthenticationError,
    FailClosedAuthenticator,
    Principal,
    authenticate,
)


class BoundPrincipal(FailClosedAuthenticator):
    """Test double. The player is chosen here, never from request data."""

    def __init__(self, principal: Principal):
        self._principal = principal

    def authenticate(self) -> Principal:
        return self._principal


def untrusted_claim(subject: str) -> dict[str, object]:
    return {
        "headers": {
            "X-Replit-User-Id": subject,
            "X-Replit-User-Name": subject,
            "Authorization": "Bearer client-supplied-token",
        },
        "body": {"user_id": subject, "issuer": "https://client.example", "subject": subject},
    }


class PrincipalAuthTests(unittest.TestCase):
    def setUp(self):
        self.player_a = Principal("test-issuer-a", "player-a")
        self.player_b = Principal("test-issuer-b", "player-b")
        self.same_subject_other_issuer = Principal("test-issuer-b", "player-a")

    def test_missing_authenticator_fails_closed_and_ignores_client_identity(self):
        with self.assertRaises(AuthenticationError):
            authenticate(None, untrusted_claim("player-a"))

    def test_default_authenticator_fails_closed(self):
        with self.assertRaises(AuthenticationError):
            authenticate(FailClosedAuthenticator(), untrusted_claim("player-a"))

    def test_two_synthetic_players_stay_distinct_despite_client_claims(self):
        as_a = BoundPrincipal(self.player_a)
        as_b = BoundPrincipal(self.player_b)
        self.assertEqual(authenticate(as_a, untrusted_claim("player-b")), self.player_a)
        self.assertEqual(authenticate(as_b, untrusted_claim("player-a")), self.player_b)
        self.assertNotEqual(self.player_a, self.player_b)

    def test_same_subject_with_different_issuer_is_a_different_principal(self):
        self.assertEqual(self.player_a.subject, self.same_subject_other_issuer.subject)
        self.assertNotEqual(self.player_a, self.same_subject_other_issuer)
        resolved = authenticate(
            BoundPrincipal(self.same_subject_other_issuer),
            untrusted_claim(self.player_a.subject),
        )
        self.assertEqual(resolved, self.same_subject_other_issuer)
        self.assertNotEqual(resolved, self.player_a)

    def test_non_principal_result_fails_closed(self):
        class ReportsClientDict(FailClosedAuthenticator):
            def authenticate(self):
                return {"issuer": "test-issuer-a", "subject": "player-a"}

        with self.assertRaises(AuthenticationError):
            authenticate(ReportsClientDict(), untrusted_claim("player-a"))

    def test_invalid_identity_parts_are_rejected(self):
        for issuer, subject in (
            ("", "player-a"),
            ("test-issuer-a", ""),
            (" test-issuer-a", "player-a"),
            ("test-issuer-a", "player-a "),
            ("test-issuer-a", None),
        ):
            with self.assertRaises(ValueError):
                Principal(issuer, subject)
