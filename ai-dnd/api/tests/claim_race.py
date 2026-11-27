"""Race two turn requests so that the second one reaches its claim late (D-305)."""

from __future__ import annotations

import asyncio
import itertools
import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx


async def racing_claims(
    manager: object,
    post: Callable[[dict, dict], Awaitable[httpx.Response]],
    campaign: dict,
    bodies: list[dict],
) -> list[httpx.Response]:
    """Post every body at once; the second claims late and the first waits for it.

    The first request holds its open claim until the second has been answered,
    or it could finish whole and let the second through (the old CI flake).
    """
    order = itertools.count()
    answered = threading.Barrier(2)
    original = manager.claim_action_intent

    def late_second(record: object, action_id: str, request_hash: str) -> dict:
        if next(order) == 1:
            time.sleep(0.5)
        outcome = original(record, action_id, request_hash)
        answered.wait(timeout=10)
        return outcome

    with patch.object(manager, "claim_action_intent", side_effect=late_second):
        return await asyncio.wait_for(
            asyncio.gather(*(post(campaign, body) for body in bodies)), timeout=20)
