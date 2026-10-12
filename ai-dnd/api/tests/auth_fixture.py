"""Synthetic players for tests. These are not production identities."""

from api.auth import FixedAuthenticator, Principal

TEST_PLAYER = Principal("test-issuer", "test-player")
PLAYER_A = Principal("test-issuer-a", "player-a")
PLAYER_B = Principal("test-issuer-b", "player-b")
SAME_SUBJECT = Principal("test-issuer-b", "player-a")


def authenticator_for(principal: Principal = TEST_PLAYER) -> FixedAuthenticator:
    return FixedAuthenticator(principal)
