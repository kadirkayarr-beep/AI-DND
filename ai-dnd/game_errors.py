"""One root for the errors the game raises on purpose.

A caller can catch "a game refusal" without catching every Exception. GameInputError is a refused request (still a
ValueError, so older `except ValueError` callers keep catching it); GameInfrastructureError is a failed dependency
(storage, model, canon stamp) where the request itself may be fine.
"""

from __future__ import annotations


class GameError(Exception):
    """Root of every error the game raises on purpose."""


class GameInputError(GameError, ValueError):
    """The request asked for something the rules refuse."""


class GameInfrastructureError(GameError):
    """A dependency failed; nothing about the request is known to be wrong."""
