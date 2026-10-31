"""Tests about addressing, doors and clock arithmetic need a street they can name.

New campaigns draw their people, tavern keeper and first hour from a random
campaign id. A test that reads a known person or hour pins the old fixed street
here; test_varied_openings sets ``seeded_street = True`` and checks the real draw.
"""
from unittest.mock import patch

import campaign_time
import living_world


def use_fixed_street(test):
    if getattr(test, "seeded_street", False):
        return
    for target, name, replacement in (
        (living_world, "scene_cast", lambda world, location_id: list(living_world._CITY_PEOPLE[:2])),
        (living_world, "tavern_keeper", lambda world, location_id: living_world._TAVERN_KEEPERS[0]),
        (campaign_time, "seed_start", lambda world, seed: None),
    ):
        patcher = patch.object(target, name, replacement)
        patcher.start()
        test.addCleanup(patcher.stop)
