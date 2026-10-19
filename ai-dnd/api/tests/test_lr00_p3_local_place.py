"""LR00-P3 pilot: a local place the player heads for becomes real and stays.

Covers OH1-05 (creation -> record -> reference -> interaction), OH1-09
(same records after a fresh manager/resume) and the P1 guards (negation,
condition, question never move). Deterministic layer only; the live layer is
api/tests/live_lr00_probe.py scenario "p3".
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import httpx

import game
import local_places
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.auth import FixedAuthenticator
from api.tests.test_campaign_api import FakeOllamaClient


class LocalPlacePilotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": "fr:city:neverwinter",
        }})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_id = created.json()["campaign_id"]
        self.session_id = created.json()["session_id"]
        self.session = self.manager.get(self.session_id).game_session
        self.turn_url = f"/api/game/sessions/{self.session_id}/turn"
        self.city = "fr:city:neverwinter"

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def turn(self, message):
        response = await self.http.post(
            self.turn_url, json={"message": message, "action_id": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def world(self):
        return self.session.world_state

    def places(self):
        return [r for r in self.world()["locations"].values()
                if isinstance(r, dict) and r.get("place_kind")]

    async def test_going_to_an_archive_creates_one_place_person_detail_and_matter(self):
        body = await self.turn("Marek'in bahsettiği arşive gidiyorum.")
        places = self.places()
        self.assertEqual(len(places), 1)
        place = places[0]
        self.assertEqual(place["place_kind"], "archive")
        self.assertEqual(place["parent_location_id"], self.city)
        self.assertEqual(place["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(self.world()["location"], place["id"])
        person = local_places.resident_of(self.world(), place["id"])
        self.assertIsNotNone(person)
        self.assertIn(place["name"], person["personal_profile"]["occupation"])
        self.assertTrue(person["personal_profile"]["immediate_goal"])
        detail = local_places.feature_of(self.world(), place["id"], "Tozlu raflar")
        self.assertIsNotNone(detail)
        self.assertTrue(place["local_issue"])
        # The local matter is not a quest, reward or commitment.
        self.assertEqual(self.world().get("quests", []), [])
        self.assertIn(place["name"], body["narration"])
        self.assertNotIn("iz göremiyorsun", body["narration"])

    async def test_leaving_and_returning_reuses_the_same_records(self):
        await self.turn("Arşive gidiyorum.")
        place = self.places()[0]
        person = copy.deepcopy(local_places.resident_of(self.world(), place["id"]))
        def people_here():
            return [n["id"] for n in self.world()["npcs"] if n.get("location") == place["id"]]

        npcs_at_place = people_here()
        await self.turn("Buradan çıkıp sokağa dönüyorum.")
        self.assertEqual(self.world()["location"], self.city)
        again = await self.turn("Arşive geri gidiyorum.")
        self.assertEqual(self.world()["location"], place["id"])
        self.assertEqual(len(self.places()), 1)
        self.assertEqual(people_here(), npcs_at_place)
        self.assertEqual(local_places.resident_of(self.world(), place["id"])["id"], person["id"])
        self.assertIn("Yeniden", again["narration"])
        here = await self.turn("Arşive gidiyorum.")
        self.assertIn("Zaten", here["narration"])

    async def test_negated_conditional_and_question_forms_do_not_move(self):
        for message in (
            "Arşive gitmiyorum, burada bekleyeceğim.",
            "Eğer kapı açıksa arşive giderim.",
            "Arşive nasıl giderim?",
        ):
            with self.subTest(message=message):
                self.assertIsNone(local_places.is_local_place_visit(message))

    async def test_place_survives_a_fresh_manager_resume(self):
        await self.turn("Demirciye uğruyorum.")
        place = self.places()[0]
        person_id = local_places.resident_of(self.world(), place["id"])["id"]
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app), base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            world = reopened_manager.get(resumed.json()["session_id"]).game_session.world_state
            self.assertEqual(world["location"], place["id"])
            self.assertEqual(world["locations"][place["id"]]["name"], place["name"])
            self.assertEqual(local_places.resident_of(world, place["id"])["id"], person_id)

    def test_turkish_consonant_softening_still_names_the_place(self):
        for message, kind in (
            ("Tapınağa gidiyorum.", "temple"),
            ("Mezarlığa doğru yürüyorum.", "graveyard"),
            ("Demirciye uğruyorum.", "smithy"),
            ("Limana iniyorum, iskeleye gidiyorum.", "harbor"),
        ):
            with self.subTest(message=message):
                self.assertEqual(local_places.is_local_place_visit(message), kind)

    def test_different_campaign_seeds_name_places_differently(self):
        names = set()
        for seed in ("seed-a", "seed-b", "seed-c", "seed-d"):
            world = {"scene_state": {"campaign_seed": seed}, "locations": {
                "fr:city:neverwinter": {"id": "fr:city:neverwinter", "type": "city", "scene_kind": "city"},
            }, "npcs": []}
            names.add(local_places.create_local_place(world, "fr:city:neverwinter", "archive")["name"])
        self.assertGreater(len(names), 1)


if __name__ == "__main__":
    unittest.main()
