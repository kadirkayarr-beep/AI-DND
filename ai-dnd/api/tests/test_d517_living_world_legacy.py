"""D-517: a new campaign never writes the old save shapes living_world used to repair on load (a feature without an
id, an ambient event without an instance id), so the repair is gone and such a record is refused."""

from __future__ import annotations

import copy
import unittest

import living_world
from api.tests import test_campaign_api
from api.tests import test_narration_source_record as narration_record


class FreshCampaignWritesNoOldShapes(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown
    started = narration_record.WriterBoundary.started

    async def test_a_fixed_town_campaign_has_a_seed_and_complete_records(self):
        _campaign_id, record = await self.started(7517)
        world = record.game_session.world_state
        state = living_world.ensure_scene_state(world)
        self.assertTrue(state["campaign_seed"])
        for item in state["ambient_event_history"]:
            self.assertTrue(item.get("instance_id"))
        for scene in state["scenes"].values():
            event = scene.get("ambient_event")
            if isinstance(event, dict):
                self.assertTrue(event.get("instance_id"))
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
