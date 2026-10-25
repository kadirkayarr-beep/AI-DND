"""Scene truth contract: a real entry, seat and look must agree on one scene.

Phase 1 of the scene-truth plan. Real ASGI/engine and temporary SQLite with a
model client that fails on any unexpected narration call. Nothing here talks to
a live model, and no production campaign or personal save is read.

The measured entry is a real approach/arrival turn; the fixture never teleports
the player inside.
"""
import unittest
import uuid
from unittest.mock import patch

import grounded_action
import living_world
from api.tests import test_campaign_api
from api.tests import test_intent_response_consistency as base

VENUE_NAME = "Kanıt Hanı"


class SceneTruthContractTests(unittest.IsolatedAsyncioTestCase):
    """Reuses the temporary campaign harness of IntentResponseConsistencyTests."""

    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown

    async def send(self, text, *, mode="do", action_id=None, target_id=None):
        """Post one turn and refresh the world reference (restore may replace it)."""
        fields = {
            "message": text,
            "interaction_mode": mode,
            "action_id": action_id or str(uuid.uuid4()),
        }
        if target_id is not None:
            fields["target_id"] = target_id
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=fields)
        self.session = self.manager.get(self.session_id).game_session
        self.world = self.session.world_state
        return response

    def seed_tavern(self, *, locked=False):
        """Create a tavern with a door, a table and a bar in the temporary world.

        Test helper only; it is not a production API. The player stays in the
        starting city and no active/last NPC or entry reference is left behind.
        """
        city = self.world["location"]
        living_world.materialize_scene(
            self.world, city, 0,
            create_npc=self.session.create_npc_from_ai,
            create_feature=self.session.create_local_feature,
        )
        place = grounded_action._create_venue(
            grounded_action._Run(self.session, "synthetic setup"), city,
            name=VENUE_NAME, kind="tavern", noun="han",
            provenance={"kind": "synthetic_verification_setup"},
        )
        door = next(d for d in self.world["doors"] if d["id"] == "venue-door:" + place["id"])
        door.update(open=False, locked=locked, broken=False)
        # Feature creation is current-scene only: seed the room, then go back.
        self.world["location"] = place["id"]
        try:
            for name, kind, description in (
                ("Boş masa", "table", "Kimsenin oturmadığı sade bir masa."),
                ("Bar tezgâhı", "furnishing", "Cilalı uzun bir tezgâh."),
            ):
                feature = self.session.create_local_feature({
                    "location": place["id"], "name": name,
                    "description": description, "kind": kind,
                })
                self.assertIsNotNone(feature, name)
        finally:
            self.world["location"] = city
        scene = self.world.setdefault("scene_state", {})
        scene.pop("entry_target_reference", None)
        scene.pop("active_npc_id", None)
        self.assertEqual(self.world["location"], city)
        return city, place, door

    async def test_real_entry_seat_and_look_agree(self):
        city, place, door = self.seed_tavern()
        approach = await self.send(f"{VENUE_NAME} kapısına yaklaşıyorum")
        self.assertEqual(approach.status_code, 200, approach.text)
        entered = await self.send("İçeri giriyorum")
        self.assertEqual(entered.status_code, 200, entered.text)
        self.assertEqual(self.world["location"], place["id"])
        seated = await self.send("Boş bir masaya oturuyorum")
        self.assertEqual(seated.status_code, 200, seated.text)
        self.assertIsNone(seated.json().get("skill_check_result"))
        position = self.world["scene_state"]["player_position"]
        self.assertEqual((position["location_id"], position["kind"]), (place["id"], "seated"))
        ids = {f["id"] for f in self.world["features"] if f["location"] == place["id"]}
        self.assertIn(position["target_id"], ids)
        observed = await self.send("Çevreyi gözlemliyorum")
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertIn(place["name"], observed.json()["narration"])

    async def enter_tavern(self, **seed):
        city, place, door = self.seed_tavern(**seed)
        await self.send(f"{VENUE_NAME} kapısına yaklaşıyorum")
        entered = await self.send("İçeri giriyorum")
        self.assertEqual(entered.status_code, 200, entered.text)
        return city, place, door, entered

    def venue_features(self, place):
        return [f for f in self.world["features"] if f["location"] == place["id"]]

    async def test_locked_door_never_commits_inside(self):
        city, place, door = self.seed_tavern(locked=True)
        await self.send(f"{VENUE_NAME} kapısına yaklaşıyorum")
        entered = await self.send("İçeri giriyorum")
        self.assertEqual(entered.status_code, 200, entered.text)
        self.assertEqual(self.world["location"], city)
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        self.assertIn("kilitli", entered.json()["narration"])
        self.assertNotIn("içeri giriyorsun", entered.json()["narration"])

    async def test_feature_named_entrance_is_not_a_venue_door(self):
        city, place, door = self.seed_tavern()
        sign = self.session.create_local_feature({
            "location": city, "name": "Giriş levhası",
            "description": "Boyası dökülmüş eski bir levha.", "kind": "furnishing",
        })
        self.assertIsNotNone(sign)
        approach = await self.send("Giriş levhasına yaklaşıyorum")
        self.assertEqual(approach.status_code, 200, approach.text)
        reference = self.world["scene_state"].get("entry_target_reference")
        self.assertIsNone(reference, "a sign is not the venue door")
        self.assertEqual(self.world["location"], city)
        self.assertNotIn("içeri giriyorsun", approach.json()["narration"])

    async def test_expired_entry_reference_does_not_narrate_arrival(self):
        city, place, door = self.seed_tavern()
        await self.send(f"{VENUE_NAME} kapısına yaklaşıyorum")
        # One unrelated turn consumes the one-turn reference.
        await self.send("Çevreme bakıyorum")
        self.assertIsNone(self.world["scene_state"].get("entry_target_reference"))
        stale = await self.send("İçeri giriyorum")
        self.assertEqual(stale.status_code, 200, stale.text)
        inside = self.world["location"] == place["id"]
        if not inside:
            self.assertNotIn(place["name"] + " içine", stale.json()["narration"])
            self.assertNotIn("içeri giriyorsun", stale.json()["narration"])
        else:
            # Entering is allowed only through the one real, visible door.
            self.assertTrue(door["open"])

    async def test_hidden_seat_target_is_not_selected_or_disclosed(self):
        city, place, door, entered = await self.enter_tavern()
        secret = self.session.create_local_feature({
            "location": place["id"], "name": "Gizli kuytu",
            "description": "Perdenin ardındaki saklı bir oturma yeri.", "kind": "seat",
        })
        self.assertIsNotNone(secret)
        secret["hidden"] = True
        result = await self.send("Gizli kuytuya oturuyorum")
        self.assertEqual(result.status_code, 200, result.text)
        position = self.world["scene_state"]["player_position"]
        self.assertNotEqual(position.get("target_id"), secret["id"], result.json()["narration"])
        self.assertNotIn("Gizli kuytu", result.json()["narration"])

    async def test_same_name_tables_require_clarification(self):
        city, place, door, entered = await self.enter_tavern()
        self.assertEqual(self.world["location"], place["id"])
        twin = self.session.create_local_feature({
            "location": place["id"], "name": "Boş masa",
            "description": "Pencere kenarındaki başka bir masa.", "kind": "table",
        })
        if twin is None:
            self.skipTest("fixture could not create a second same-named feature")
        before = dict(self.world["scene_state"]["player_position"])
        result = await self.send("Boş masaya oturuyorum")
        self.assertEqual(result.status_code, 200, result.text)
        after = self.world["scene_state"]["player_position"]
        self.assertEqual(after.get("kind"), before.get("kind"))
        self.assertIn("hangi", result.json()["narration"].lower())

    async def test_investigation_failure_preserves_visible_baseline(self):
        city, place, door, entered = await self.enter_tavern()
        before = sorted(f["id"] for f in self.venue_features(place))
        with patch("game.roll_d20", return_value=2):
            await self.send("Bar tezgâhının altında gizli bir şey var mı diye arıyorum")
        self.assertEqual(self.world["location"], place["id"])
        self.assertEqual(sorted(f["id"] for f in self.venue_features(place)), before)
        observed = await self.send("Çevreyi gözlemliyorum")
        self.assertIn(place["name"], observed.json()["narration"])

    async def test_old_prose_does_not_move_player_or_create_table(self):
        city, place, door, entered = await self.enter_tavern()
        before = sorted(f["id"] for f in self.venue_features(place))
        prose = {"message": {"content": (
            '{"narration": "Hancı seni yeni bir yuvarlak masaya oturttu; masaya yerleştin.",'
            ' "world_updates": {}, "lore_claims": []}'
        )}}
        self.client.allow_narration = True
        with patch.object(self.client, "chat", side_effect=lambda *a, **k: prose):
            await self.send("Çevreyi gözlemliyorum")
        self.assertEqual(self.world["location"], place["id"])
        position = self.world["scene_state"]["player_position"]
        self.assertNotEqual(position.get("kind"), "seated")
        self.assertEqual(sorted(f["id"] for f in self.venue_features(place)), before)
        self.assertFalse(any("yuvarlak" in f["name"].lower() for f in self.venue_features(place)))


if __name__ == "__main__":
    unittest.main()
