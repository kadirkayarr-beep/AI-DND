"""Phase 6: one action id commits once; replay and conflict never repeat an effect.

Real ASGI/engine and temporary SQLite. This pins existing turn-lock, receipt and
campaign-store behaviour so later mutation owners cannot break it quietly. Cases
already covered elsewhere are not duplicated: pre-commit save failure restore
(`test_campaign_api`, fail_once save) and narrator failure fallback
(`test_f04_frozen_narrator_faults`).
"""
import asyncio
import unittest
import uuid
from contextlib import closing
from unittest.mock import patch

from api.tests import test_intent_response_consistency as base
from api.tests import test_scene_truth_contract as phase1

VENUE = phase1.VENUE_NAME


class SceneTransactionContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown
    send = phase1.SceneTruthContractTests.send
    seed_tavern = phase1.SceneTruthContractTests.seed_tavern

    def history_count(self, campaign_id=None):
        with closing(self.store._connect()) as db:
            return db.execute(
                "SELECT COUNT(*) FROM campaign_history WHERE campaign_id = ?",
                (campaign_id or self.campaign_id,),
            ).fetchone()[0]

    async def at_the_door(self):
        city, place, door = self.seed_tavern()
        await self.send(f"{VENUE} kapısına yaklaşıyorum")
        return city, place

    async def test_replayed_action_id_commits_once_and_returns_same_receipt(self):
        city, place = await self.at_the_door()
        rows_before = self.history_count()
        action_id = str(uuid.uuid4())
        first = await self.send("İçeri giriyorum", action_id=action_id)
        self.assertEqual(first.status_code, 200, first.text)
        rows_after_first = self.history_count()
        self.assertEqual(rows_after_first, rows_before + 1)
        position = dict(self.world["scene_state"]["player_position"])
        with patch("game.roll_d20", side_effect=AssertionError("replay rolled a die")):
            second = await self.send("İçeri giriyorum", action_id=action_id)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["action_id"], first.json()["action_id"])
        self.assertEqual(second.json()["narration"], first.json()["narration"])
        self.assertEqual(self.history_count(), rows_after_first, "replay must not save a second turn")
        self.assertEqual(self.world["location"], place["id"])
        self.assertEqual(self.world["scene_state"]["player_position"], position)

    async def test_same_action_id_different_body_conflicts_without_effect(self):
        city, place = await self.at_the_door()
        action_id = str(uuid.uuid4())
        first = await self.send("İçeri giriyorum", action_id=action_id)
        self.assertEqual(first.status_code, 200, first.text)
        rows = self.history_count()
        state_after_first = dict(self.world["scene_state"]["player_position"])
        clash = await self.send("Boş bir masaya oturuyorum", action_id=action_id)
        self.assertEqual(clash.status_code, 409, clash.text)
        self.assertEqual(clash.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual(self.history_count(), rows)
        self.assertEqual(self.world["scene_state"]["player_position"], state_after_first)

    async def test_concurrent_same_action_id_commits_once(self):
        city, place = await self.at_the_door()
        rows_before = self.history_count()
        action_id = str(uuid.uuid4())
        results = await asyncio.gather(
            self.send("İçeri giriyorum", action_id=action_id),
            self.send("İçeri giriyorum", action_id=action_id),
        )
        codes = sorted(r.status_code for r in results)
        self.assertTrue(all(code in (200, 409) for code in codes), codes)
        self.assertIn(200, codes)
        self.assertEqual(self.history_count(), rows_before + 1, "two requests, one committed turn")
        self.assertEqual(self.world["location"], place["id"])
        winners = [r.json() for r in results if r.status_code == 200]
        self.assertEqual({w["action_id"] for w in winners}, {action_id})
        self.assertEqual(len({w["narration"] for w in winners}), 1)

    async def test_other_campaign_history_is_untouched_by_a_turn(self):
        other = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": "fr:city:neverwinter",
        }})
        self.assertEqual(other.status_code, 200, other.text)
        other_id = other.json()["campaign_id"]
        other_rows = self.history_count(other_id)
        mine = self.history_count()
        response = await self.send("Çevreme bakıyorum")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.history_count(), mine + 1)
        self.assertEqual(self.history_count(other_id), other_rows)
