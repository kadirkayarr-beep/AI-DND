"""A new Neverwinter campaign seeds its town (work, places, talk) from its id, which is random unless pinned."""

from __future__ import annotations

import uuid
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from api import session_manager
from api.tests.journeys.runner import _campaign_seeded


def fixed_town(test: Any, first_seed: int) -> AbstractContextManager[Any]:
    """The next campaign this test creates gets a fixed id: ``first_seed`` for the first, one more for each after.

    Two campaigns of one test cannot share an id, so each creation in a test takes the next seed; the same test
    always sees the same towns in the same order.
    """
    seed = first_seed + getattr(test, "_town_creations", 0)
    test._town_creations = getattr(test, "_town_creations", 0) + 1
    return _campaign_seeded({"campaign_seed": seed})


def default_town(test: Any, first_seed: int) -> AbstractContextManager[Any]:
    """``fixed_town`` unless an outer pin is already active (then nothing changes, and no seed is used up).

    A helper that creates a campaign wraps it in this, so a test that pins the town around the helper keeps its own.
    """
    if session_manager.uuid is not uuid:
        return nullcontext()
    return fixed_town(test, first_seed)
