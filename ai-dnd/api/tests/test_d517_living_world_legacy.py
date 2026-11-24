"""D-517: a new campaign never writes the old save shapes living_world used to repair on load (a feature without an
id, an ambient event without an instance id), so the repair is gone and such a record is refused."""

from __future__ import annotations

import copy
import unittest

import living_world
from api.tests import test_campaign_api
from api.tests.town_seed import fixed_town


class FreshCampaignWritesNoOldShapes(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown

    async def test_a_fixed_town_campaign_has_a_seed_and_complete_records(self):
        start = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                 "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
        with fixed_town(self, 7517):
            created = (await self.http.post("/api/game/campaigns", json={"campaign_start": start})).json()
        record = self.manager.get(created["session_id"])
        world = record.game_session.world_state
        state = living_world.ensure_scene_state(world)
        self.assertTrue(state["campaign_seed"])
        session = record.game_session
        world["locations"][world["location"]]["scene_kind"] = "city"  # so the catalog has candidates here
        self.assertIn("scene_kind", world["locations"][world["location"]])
        living_world.set_ambient_context(
            world, {"environment": "city", "time_of_day": "night", "weather": "storm"}, session.character, "d517-fixed")
        for turn in range(1, 6):  # the live writer, so the loops below check real records
            living_world.select_and_record_ambient_event(world, world["location"], turn)
        state = living_world.ensure_scene_state(world)
        self.assertTrue(state["ambient_event_history"], "HISTORY-EMPTY")
        for item in state["ambient_event_history"]:
            self.assertTrue(item.get("instance_id"))
        for scene in state["scenes"].values():
            event = scene.get("ambient_event")
            if isinstance(event, dict):
                self.assertTrue(event.get("instance_id"))
        if not world.get("features"):  # a fresh start has none: make one through the live writer
            session.create_local_feature({"location": world["location"], "name": "Meşe masa",
                                          "description": "Duvar kenarında duran sağlam bir masa."})
        self.assertTrue(world["features"], "no feature was written")
        for feature in world.get("features", []):
            self.assertTrue(feature.get("id"))
            self.assertFalse(feature["id"].startswith("feature_legacy_"))


class OldShapesAreRefused(unittest.TestCase):
    def world(self):
        return {"location": "a", "locations": {}, "npcs": [], "features": [], "flags": {}}

    def test_a_feature_without_an_id_is_refused(self):
        world = self.world()
        world["features"] = [{"location": "a", "name": "Masa", "description": "x"}]
        with self.assertRaises(ValueError):
            living_world.ensure_scene_state(world)

    def test_an_ambient_history_item_without_an_instance_id_is_refused(self):
        world = self.world()
        state = living_world.ensure_scene_state(world)
        state["ambient_event_history"].append({
            "event_id": "e", "variation_id": "v", "repeat_group": "g", "location_id": "a",
            "turn_index": 1, "last_seen_turn": 1, "count": 1,
        })
        with self.assertRaises(ValueError):
            living_world.ensure_scene_state(copy.deepcopy(world))


if __name__ == "__main__":
    unittest.main()
