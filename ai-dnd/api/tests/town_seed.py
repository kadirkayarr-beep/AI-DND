"""A new Neverwinter campaign seeds its town (work, places, talk) from its id, which is random unless pinned."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from api.tests.journeys.runner import _campaign_seeded


def fixed_town(test: Any, first_seed: int) -> AbstractContextManager[Any]:
    """The next campaign this test creates gets a fixed id: ``first_seed`` for the first, one more for each after.

    Two campaigns of one test cannot share an id, so each creation in a test takes the next seed; the same test
    always sees the same towns in the same order.
    """
    seed = first_seed + getattr(test, "_town_creations", 0)
    test._town_creations = getattr(test, "_town_creations", 0) + 1
    return _campaign_seeded({"campaign_seed": seed})
