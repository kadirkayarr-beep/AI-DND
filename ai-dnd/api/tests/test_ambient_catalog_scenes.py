"""Dilim 3, Task 13: street happenings are not offered inside the inn (table test, data only)."""
from __future__ import annotations

import unittest

from ambient_event_catalog import EVENT_CATALOG, select_ambient_event

TAVERN_OK = {
    "building_candle", "building_stair", "city_advice", "city_slammed_door", "city_small_argument",
    "city_tavern_chair", "city_tavern_cook", "city_tavern_server", "city_tavern_song",
    "city_tavern_spill", "city_tavern_story",
    "evt021", "evt022", "evt023", "evt024", "evt025", "evt026", "evt027", "evt028", "evt029",
    "evt030", "evt031", "evt032", "evt034", "evt035", "evt036", "evt037", "evt038", "evt039", "evt040",
}


class AmbientCatalogScenesTests(unittest.TestCase):
    def test_tavern_scene_kind_is_exactly_the_indoor_set(self):
        self.assertEqual({e["event_id"] for e in EVENT_CATALOG if "tavern" in e["kinds"]}, TAVERN_OK)

    def test_inn_scene_never_picks_a_street_event_over_200_seeds(self):
        for seed in range(200):
            for tod in ("day", "evening", "night"):
                event = select_ambient_event(
                    scene_kind="tavern", location_id="inn", turn_index=seed,
                    context={"time_of_day": tod}, history=[], campaign_seed=f"s{seed}",
                )
                if event is not None:
                    self.assertIn(event["event_id"], TAVERN_OK)


if __name__ == "__main__":
    unittest.main()
