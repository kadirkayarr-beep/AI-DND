"""Coin a turn's reading leaves on the session, planted by a test that stands in for the reading (F_fon G3).

With the front reading on, `front_proposal.begin` starts every turn by clearing the coin fields a reading writes
(`_coin_paid`, `_bribe_held_out`, `_coin_decision`, ...). A test that plants them only before the turn then checks a
turn that never saw them. `planted` sets them before the turn (flag off: no begin runs) and again right after begin
(flag on), so every later purse, card and receipt check runs on the real turn either way. Wrap one turn only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import front_proposal


@contextmanager
def planted(session, **fields):
    def plant(target):
        for name, value in fields.items():
            setattr(target, name, value)

    real_begin = front_proposal.begin

    def begin_then_plant(target, *args, **kwargs):
        real_begin(target, *args, **kwargs)
        plant(target)

    plant(session)
    with patch.object(front_proposal, "begin", side_effect=begin_then_plant):
        yield


def read_as(front):
    """The model reads the line as `front` (a scripted front reading) and fails every other call, as these money
    tests' own model does. Flag on, the coin the reading holds out reaches the engine's owner the way local play
    reaches it; flag off, no reading is asked and nothing else changes."""
    from api.tests.test_front_proposal import FrontClient
    client = FrontClient()
    client.front = front

    def chat(*args, **kwargs):
        if "front" not in ((kwargs.get("format") or {}).get("properties") or {}):
            raise AssertionError("Unexpected model call")
        return client.chat(*args, **kwargs)
    return patch("game.ollama.chat", side_effect=chat)
