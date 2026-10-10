"""Player text inside generator context is data, not instruction."""

from __future__ import annotations

import copy
import re

MAX_PLAYER_TEXT = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FENCE = re.compile(r"<<+|>>+")


def sanitize(text):
    if not isinstance(text, str):
        return ""
    cleaned = _FENCE.sub(" ", _CONTROL.sub(" ", text)).strip()
    return cleaned[:MAX_PLAYER_TEXT]


def attach(envelope, player_text):
    """Return the generator packet. The envelope is frozen before text joins."""
    return {
        "envelope": copy.deepcopy(envelope),
        "player_text": "<<PLAYER_TEXT_UNTRUSTED>>" + sanitize(player_text) + "<<END_PLAYER_TEXT>>",
    }
