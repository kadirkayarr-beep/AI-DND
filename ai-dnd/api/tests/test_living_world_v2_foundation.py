import copy
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

import living_world
from ambient_event_catalog import EVENT_CATALOG
from api.opening_narrative import initialize_campaign_opening
from api.schemas import CharacterCreateInput


class LivingWorldV2FoundationTests(unittest.TestCase):
    def make_session(self):
        return SimpleNamespace(
            world_state={
                "location": "verified-city",
                "locations": {
                    "verified-city": {
                        "id": "verified-city",
                        "name": "Neverwinter",
                        "type": "city",
                    }
                },
                "npcs": [],
                "features": [],
                "flags": {"turn_index": 0},
            },
            character={
                "name": "Mira",
                "background": "Soldier",
                "origin": "Neverwinter",
                "appearance": "Kısa pelerin",
                "personality": "Dikkatli ve ciddi",
                "backstory": "Nöbet görevini bırakıp yeni bir yol seçti.",
            },
            world_metadata={
                "environment": "city",
                "time_of_day": "night",
                "weather": "storm",
            },
        )

    def test_origin_is_an_optional_custom_identity_field(self):
        request = CharacterCreateInput.model_validate({
            "mode": "custom",
            "name": "Mira",
            "race": "Human",
            "class": "Fighter",
            "origin": "Neverwinter",
        })
        self.assertEqual(request.origin, "Neverwinter")
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({
                "mode": "random",
                "origin": "Neverwinter",
            })
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({
                "mode": "custom",
                "name": "Mira",
                "race": "Human",
                "class": "Fighter",
                "origin": "x" * 241,
            })

    def test_catalog_has_broad_coverage_and_unique_event_ids(self):
        self.assertGreaterEqual(len(EVENT_CATALOG), 50)
        event_ids = [event["event_id"] for event in EVENT_CATALOG]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(
            {event["event_type"] for event in EVENT_CATALOG},
            {"GREEN", "BLUE"},
        )

    def test_opening_uses_authoritative_context_and_survives_reload(self):
        session = self.make_session()
        original_location = session.world_state["location"]
        opening = initialize_campaign_opening(session, "campaign-opening-test")
        self.assertIn("Neverwinter", opening["text"])
        self.assertIn("Kökenin Neverwinter", opening["text"])
        self.assertIn("Fırtına rüzgârı", opening["text"])
        self.assertIn("Nöbet görevini bırakıp yeni bir yol seçti.", opening["text"])
        self.assertEqual(opening["tone"], "gergin")
        self.assertEqual(session.world_state["location"], original_location)
        self.assertEqual(
            len(session.world_state["scene_state"]["ambient_event_history"]),
            1,
        )

        saved_world = copy.deepcopy(session.world_state)
        resumed_projection = living_world.public_scene_projection(saved_world, 0)
        self.assertEqual(resumed_projection["opening"], opening["text"])
        self.assertEqual(
            len(saved_world["scene_state"]["ambient_event_history"]),
            1,
        )

    def test_scene_event_selection_avoids_recent_repeat_groups(self):
        session = self.make_session()
        living_world.set_ambient_context(
            session.world_state,
            session.world_metadata,
            session.character,
            "campaign-repeat-test",
        )
        first = living_world.select_and_record_ambient_event(
            session.world_state,
            "verified-city",
            1,
        )
        second = living_world.select_and_record_ambient_event(
            session.world_state,
            "verified-city",
            2,
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["repeat_group"], second["repeat_group"])
        self.assertEqual(
            session.world_state["scene_state"]["ambient_event_counts"][
                first["event_id"]
            ],
            1,
        )

    def test_materialized_scene_event_is_persistent(self):
        session = self.make_session()
        living_world.set_ambient_context(
            session.world_state,
            session.world_metadata,
            session.character,
            "campaign-materialize-test",
        )

        def create_npc(data):
            npc = {"id": f"npc_{len(session.world_state['npcs']) + 1}", **data}
            session.world_state["npcs"].append(npc)
            return npc

        def create_feature(data):
            feature = {
                "id": f"feature_{len(session.world_state['features']) + 1}",
                **data,
            }
            session.world_state["features"].append(feature)
            return feature

        scene = living_world.materialize_scene(
            session.world_state,
            "verified-city",
            1,
            create_npc=create_npc,
            create_feature=create_feature,
        )
        event = copy.deepcopy(scene["ambient_event"])
        history_length = len(
            session.world_state["scene_state"]["ambient_event_history"]
        )
        resumed_world = copy.deepcopy(session.world_state)
        resumed_scene = living_world.materialize_scene(
            resumed_world,
            "verified-city",
            9,
            create_npc=lambda _data: self.fail("A saved scene must not reroll."),
            create_feature=lambda _data: self.fail("A saved scene must not reroll."),
        )
        self.assertEqual(resumed_scene["ambient_event"], event)
        self.assertEqual(
            len(resumed_world["scene_state"]["ambient_event_history"]),
            history_length,
        )


if __name__ == "__main__":
    unittest.main()