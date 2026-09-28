"""In-memory registry for opaque, isolated game sessions."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import game


class UnknownSessionError(LookupError):
    """Raised when an API request refers to a session that is not registered."""


@dataclass
class ManagedSession:
    game_session: Any
    turn_lock: threading.Lock = field(default_factory=threading.Lock)


class SessionManager:
    """Owns session objects; callers receive records, never client-controlled state."""

    def __init__(self, session_factory: Callable[[], Any] | None = None):
        self._session_factory = session_factory or game.create_session
        self._sessions: dict[str, ManagedSession] = {}
        self._registry_lock = threading.RLock()

    def create(self) -> tuple[str, ManagedSession]:
        session = self._session_factory()
        with self._registry_lock:
            session_id = str(uuid.uuid4())
            while session_id in self._sessions:
                session_id = str(uuid.uuid4())
            record = ManagedSession(game_session=session)
            self._sessions[session_id] = record
        return session_id, record

    def get(self, session_id: str) -> ManagedSession:
        with self._registry_lock:
            record = self._sessions.get(session_id)
        if record is None:
            raise UnknownSessionError(session_id)
        return record