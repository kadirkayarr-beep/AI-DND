"""Synthetic players for tests. These are not production identities."""

from api.auth import FixedAuthenticator, Principal
from api.session_manager import SessionManager

TEST_PLAYER = Principal("test-issuer", "test-player")
PLAYER_A = Principal("test-issuer-a", "player-a")
PLAYER_B = Principal("test-issuer-b", "player-b")
SAME_SUBJECT = Principal("test-issuer-b", "player-a")


def authenticator_for(principal: Principal = TEST_PLAYER) -> FixedAuthenticator:
    return FixedAuthenticator(principal)


class TestPlayerSessionManager(SessionManager):
    """Reads sessions as TEST_PLAYER when a test names no principal (Clerk ownership, 48ccbaa)."""

    __test__ = False

    def get(self, session_id, principal=None):
        return super().get(session_id, principal if principal is not None else TEST_PLAYER)
