"""Phase 2: ordinary actions never roll, and a compound move stops honestly.

Real ASGI/engine and temporary SQLite, reusing the Phase 1 tavern fixture.
Covers: (1) ordinary look/walk/enter/seat do not roll a die, (2) a compound
"go in and sit" reaches its first real obstacle and reports only what
happened, (3) a quoted or conditional "sit" is speech, not a command.
"""
import json
import unittest
from unittest.mock import patch

import living_world
from api.tests import test_intent_response_consistency as base
from api.tests import test_scene_truth_contract as phase1

VENUE = phase1.VENUE_NAME
COMPOUND = f"{VENUE}'na gidip içeri girip boş bir masaya oturuyorum"


class SceneCompoundContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown
    send = phase1.SceneTruthContractTests.send
    seed_tavern = phase1.SceneTruthContractTests.seed_tavern
    enter_tavern = phase1.SceneTruthContractTests.enter_tavern
    venue_features = phase1.SceneTruthContractTests.venue_features

    def position(self):
        return self.world["scene_state"]["player_position"]

    async def test_ordinary_look_walk_and_empty_seat_do_not_roll(self):
        city, place, door = self.seed_tavern()
        with patch("game.roll_d20", side_effect=AssertionError("ordinary action rolled a die")):
            for text in ("Çevreme bakıyorum", f"{VENUE} kapısına yaklaşıyorum",
                         "İçeri giriyorum", "Boş bir masaya oturuyorum"):
                response = await self.send(text)
                self.assertEqual(response.status_code, 200, (text, response.text))
                self.assertIsNone(response.json().get("skill_check_result"), text)
        self.assertEqual(self.position()["kind"], "seated")

    async def test_compound_stops_at_locked_entry(self):
        city, place, door = self.seed_tavern(locked=True)
        response = await self.send(COMPOUND)
        self.assertEqual(response.status_code, 200, response.text)
        narration = response.json()["narration"]
        self.assertEqual(self.world["location"], city)
        self.assertTrue(door["locked"])
        self.assertNotEqual(self.position()["kind"], "seated")
        self.assertIn("giremiyorsun", narration)
        self.assertNotIn("oturup", narration)
        self.assertEqual(response.json()["turn_outcome"]["status"], "partial")

    async def test_compound_open_door_completes_entry_and_seat(self):
        city, place, door = self.seed_tavern()
        response = await self.send(COMPOUND)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world["location"], place["id"])
        position = self.position()
        self.assertEqual((position["location_id"], position["kind"]), (place["id"], "seated"))
        ids = {f["id"] for f in self.venue_features(place)}
        self.assertIn(position["target_id"], ids)
        self.assertEqual(response.json()["turn_outcome"]["status"], "completed")

    async def test_compound_keeps_entry_before_missing_seat(self):
        city, place, door = self.seed_tavern()
        # A venue scene is furnished once on first entry; mark it done so the
        # room really has no seat when the player arrives.
        living_world.ensure_scene_record(self.world, place["id"], 0)["materialized"] = True
        self.world["features"] = [
            f for f in self.world["features"]
            if not (f["location"] == place["id"]
                    and f.get("kind") in ("table", "seat", "bench", "furnishing"))
        ]
        response = await self.send(COMPOUND)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world["location"], place["id"], "entry must be kept")
        self.assertNotEqual(self.position()["kind"], "seated")
        narration = response.json()["narration"]
        self.assertIn("oturabileceğin", narration.lower())
        self.assertNotIn("çıkaramadım", narration)
        self.assertEqual(response.json()["turn_outcome"]["status"], "partial")

    def scripted_model(self):
        """Script only the model boundary: a neutral intent and neutral narration."""
        def scripted(*args, **kwargs):
            if "intent" in kwargs["format"]["properties"]:
                packet = {"intent": "narrative", "action": "narrative",
                          "target": {"type": "none", "reference": ""},
                          "completion": "completed", "confidence": 1.0}
            else:
                packet = {"narration": "Masalara göz gezdiriyorsun.",
                          "world_updates": {}, "lore_claims": []}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return patch.object(self.client, "chat", side_effect=scripted)

    async def test_quoted_sit_command_is_speech_not_action(self):
        city, place, door, entered = await self.enter_tavern()
        before = dict(self.position())
        for text in ("Garsona 'masaya otur' diyorum", 'Barmene "otur" diye sesleniyorum'):
            with self.scripted_model():
                response = await self.send(text)
            self.assertEqual(response.status_code, 200, (text, response.text))
            self.assertEqual(self.position()["kind"], before["kind"], text)
            self.assertNotIn("yerleşiyorsun", response.json()["narration"], text)

    async def test_conditional_sit_does_not_seat(self):
        city, place, door, entered = await self.enter_tavern()
        before = dict(self.position())
        with self.scripted_model():
            response = await self.send("Eğer masa boşsa oturacağım")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.position()["kind"], before["kind"])
        self.assertNotIn("yerleşiyorsun", response.json()["narration"])


if __name__ == "__main__":
    unittest.main()
