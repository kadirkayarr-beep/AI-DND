from __future__ import annotations

import copy
import os
import unittest
import uuid
from unittest.mock import patch

from api.tests import test_campaign_api
from api.tests.test_campaign_api import create_city_with_locked_tavern


class ConditionTargetIndependenceHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.enterContext(patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "0"}))

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def fixture(self, *, lysa_open=False, add_lysara=False, duplicate_lysa=False):
        city_id, _, session, turn_url, lysa_id, lysa_door = (
            await create_city_with_locked_tavern(self)
        )
        lysa = session.world_state["locations"][lysa_id]
        lysa.update({"name": "Lysa Hanı", "scene_kind": "tavern", "type": "inn"})
        lysa_door.update({
            "name": "Lysa Hanı Kapısı",
            "description": "Lysa Hanı Kapısı",
            "open": lysa_open,
            "locked": not lysa_open,
            "broken": False,
        })

        def add_sibling(place_id: str, name: str, *, open_: bool, locked: bool):
            place = copy.deepcopy(lysa)
            place.update({
                "id": place_id,
                "name": name,
                "parent_location_id": city_id,
                "exit_location_id": city_id,
            })
            session.world_state["locations"][place_id] = place
            door = copy.deepcopy(lysa_door)
            door.update({
                "id": f"venue-door:{place_id}",
                "name": f"{name} Kapısı",
                "description": f"{name} Kapısı",
                "location": city_id,
                "open": open_,
                "locked": locked,
                "broken": False,
            })
            session.world_state["doors"].append(door)
            return door

        alysa_door = add_sibling(
            "diagnostic:alysa", "Alysa Hanı", open_=True, locked=False
        )
        lysara_door = (
            add_sibling("diagnostic:lysara", "Lysara Hanı", open_=False, locked=True)
            if add_lysara else None
        )
        duplicate_door = (
            add_sibling("diagnostic:lysa-copy", "Lysa Hanı", open_=True, locked=False)
            if duplicate_lysa else None
        )
        return {
            "city_id": city_id,
            "session": session,
            "turn_url": turn_url,
            "lysa_door": lysa_door,
            "alysa_door": alysa_door,
            "lysara_door": lysara_door,
            "duplicate_door": duplicate_door,
        }

    async def turn(self, fixture, message):
        return await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            fixture["turn_url"],
            test_campaign_api.FakeOllamaClient(),
            {
                "message": message,
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )

    async def approach(self, fixture, venue):
        response = await self.turn(
            fixture, f"{venue} Hanı Kapısına yaklaşıyorum."
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["turn_outcome"].get("target_name"),
            f"{venue} Hanı Kapısı",
            response.json(),
        )
        return response

    def door_state(self, fixture):
        return {
            item["id"]: {
                key: item.get(key) for key in ("open", "locked", "broken")
            }
            for item in fixture["session"].world_state["doors"]
            if item.get("id") in {
                fixture["lysa_door"]["id"],
                fixture["alysa_door"]["id"],
                (fixture["lysara_door"] or {}).get("id"),
                (fixture["duplicate_door"] or {}).get("id"),
            }
        }

    async def test_false_lysa_condition_never_uses_open_alysa_focus(self):
        fixture = await self.fixture()
        await self.approach(fixture, "Alysa")
        before_location = fixture["session"].world_state["location"]
        before_doors = self.door_state(fixture)
        response = await self.turn(
            fixture,
            "Eğer Lysa Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "condition_unmet", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertEqual(payload["state"]["location"], before_location)
        self.assertEqual(self.door_state(fixture), before_doors)
        self.assertIn("Koşulun gerçekleşmiyor", payload.get("narration", ""))
        self.assertNotIn("Alysa Hanı Kapısı kilidi açık", payload.get("narration", ""))

    async def test_false_condition_with_lysa_focus_keeps_action_bound_to_alysa(self):
        fixture = await self.fixture()
        await self.approach(fixture, "Lysa")
        before_doors = self.door_state(fixture)
        response = await self.turn(
            fixture,
            "Eğer Lysa Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "condition_unmet", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertEqual(self.door_state(fixture), before_doors)

    async def test_true_lysa_condition_keeps_distinct_alysa_action_target(self):
        fixture = await self.fixture(lysa_open=True)
        await self.approach(fixture, "Lysa")
        response = await self.turn(
            fixture,
            "Eğer Lysa Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "completed", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertIn("Alysa Hanı Kapısı", payload.get("narration", ""))

    async def test_generic_condition_keeps_current_focus_fallback(self):
        fixture = await self.fixture()
        await self.approach(fixture, "Alysa")
        response = await self.turn(
            fixture,
            "Eğer kapı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "completed", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)

    async def test_unrecognized_explicit_condition_name_is_unknown(self):
        fixture = await self.fixture()
        await self.approach(fixture, "Alysa")
        before = self.door_state(fixture)
        response = await self.turn(
            fixture,
            "Eğer Zehra Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "condition_unknown", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertEqual(self.door_state(fixture), before)

    async def test_ambiguous_registered_condition_name_is_unknown(self):
        fixture = await self.fixture(duplicate_lysa=True)
        await self.approach(fixture, "Alysa")
        before = self.door_state(fixture)
        response = await self.turn(
            fixture,
            "Eğer Lysa Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "condition_unknown", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertEqual(self.door_state(fixture), before)

    async def test_similar_registered_name_binds_lysara_not_current_alysa_focus(self):
        fixture = await self.fixture(add_lysara=True)
        await self.approach(fixture, "Alysa")
        before = self.door_state(fixture)
        response = await self.turn(
            fixture,
            "Eğer Lysara Hanı Kapısı açıksa Alysa Hanı Kapısı kilidini inceliyorum.",
        )
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("status"), "condition_unmet", payload)
        self.assertEqual(payload["turn_outcome"].get("target_name"), "Alysa Hanı Kapısı", payload)
        self.assertEqual(self.door_state(fixture), before)
