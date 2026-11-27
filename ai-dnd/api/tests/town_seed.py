"""A new Neverwinter campaign seeds its town (work, places, talk) from its id, which is random unless pinned."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from api import session_manager
from api.tests.journeys.schema import ScenarioError


def campaign_seeded(setup: Mapping[str, Any]) -> AbstractContextManager[Any]:
    """The setup's ``campaign_seed`` as the new campaign's id (every other id stays random); untouched without it."""
    if "campaign_seed" not in setup:
        return nullcontext()
    number = setup["campaign_seed"]
    if type(number) is not int or not 0 < number < 10 ** 12:
        raise ScenarioError("setup 'campaign_seed' pozitif bir tam sayı olmalı")
    ids = iter([uuid.UUID(f"00000000-0000-4000-8000-{number:012d}")])
    return patch.object(session_manager, "uuid", SimpleNamespace(uuid4=lambda: next(ids, None) or uuid.uuid4()))


def fixed_town(test: Any, first_seed: int) -> AbstractContextManager[Any]:
    """The next campaign this test creates gets a fixed id: ``first_seed`` for the first, one more for each after.

    Two campaigns of one test cannot share an id, so each creation in a test takes the next seed; the same test
    always sees the same towns in the same order.
    """
    seed = first_seed + getattr(test, "_town_creations", 0)
    test._town_creations = getattr(test, "_town_creations", 0) + 1
    return campaign_seeded({"campaign_seed": seed})


def default_town(test: Any, first_seed: int) -> AbstractContextManager[Any]:
    """``fixed_town`` unless an outer pin is already active (then nothing changes, and no seed is used up).

    A helper that creates a campaign wraps it in this, so a test that pins the town around the helper keeps its own.
    """
    if session_manager.uuid is not uuid:
        return nullcontext()
    return fixed_town(test, first_seed)
