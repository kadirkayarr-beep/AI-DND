import httpx
import re
import tempfile
import unittest
from pathlib import Path

from api.lore_authority import (
    EXTRACTED_PACK,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    REVIEWED_PACK,
    BindingStatus,
    ReviewStatus,
)
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


class CampaignStartPackTests(unittest.TestCase):
    def test_extraction_is_gated_and_only_reviewed_records_publish(self):
        extracted = (
            *EXTRACTED_PACK.entities,
            *EXTRACTED_PACK.edges,
            *EXTRACTED_PACK.facts,
        )
        reviewed = (
            *REVIEWED_PACK.entities,
            *REVIEWED_PACK.edges,
            *REVIEWED_PACK.facts,
        )
        self.assertEqual(len(EXTRACTED_PACK.entities), 14)
        self.assertEqual(len(EXTRACTED_PACK.edges), 7)
        self.assertEqual(len(EXTRACTED_PACK.facts), 20)
        self.assertTrue(
            all(item.review_status is ReviewStatus.UNREVIEWED_EXTRACTED for item in extracted)
        )
        self.assertTrue(
            all(item.review_status is ReviewStatus.VERIFIED_CANON for item in reviewed)
        )
        self.assertEqual(
            (PRODUCTION_REGISTRY.entity_count, PRODUCTION_REGISTRY.edge_count,
             PRODUCTION_REGISTRY.fact_count),
            (14, 7, 20),
        )
        self.assertTrue(
            all(fact.visibility.value != "DM_SECRET" for fact in REVIEWED_PACK.facts)
        )

    def test_only_catalogued_verified_location_is_startable(self):
        options = PRODUCTION_START_CATALOG.to_response()["settings"]
        self.assertEqual(len(options), 1)
        setting = options[0]
        self.assertEqual(setting["setting_id"], "forgotten_realms")
        self.assertEqual(len(setting["regions"]), 1)
        region = setting["regions"][0]
        self.assertEqual(region["region_id"], "fr:region:the_north")
        self.assertEqual(
            region["starting_locations"],
            [{"entity_id": "fr:city:neverwinter", "name": "Neverwinter"}],
        )

    def test_source_inventory_preserves_expected_hash_metadata_and_page_citations(self):
        expected_sources = {
            "SOURCE_FR_HEROES_2025": (
                "Forgotten_Realms_-_Heroes_of_Faerun_1790680112925.pdf",
                "569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528",
            ),
            "SOURCE_FR_ADVENTURES_2025": (
                "Forgotten_Realms_-_Adventures_in_Faerûn_1790680112924.pdf",
                "65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848",
            ),
        }
        sources = {source.source_id: source for source in EXTRACTED_PACK.sources}
        self.assertEqual(set(sources), set(expected_sources))
        for source_id, (filename, digest) in expected_sources.items():
            source = sources[source_id]
            self.assertIn(f"file={filename}; SHA-256={digest}", source.notes)

        records = (
            *EXTRACTED_PACK.entities,
            *EXTRACTED_PACK.edges,
            *EXTRACTED_PACK.facts,
        )
        self.assertTrue(all(item.source_id in expected_sources for item in records))
        self.assertTrue(
            all(re.match(r"^PDF p\.\d+ — ", item.source_reference) for item in records)
        )


class CampaignStartApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3"
        , bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=None,
            authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def test_selected_city_is_engine_start_and_persists_after_resume(self):
        options_response = await self.http.get("/api/game/campaign-start-options")
        self.assertEqual(options_response.status_code, 200)
        setting = options_response.json()["settings"][0]
        region = setting["regions"][0]
        location = region["starting_locations"][0]
        campaign_start = {
            "setting_id": setting["setting_id"],
            "region_pack_id": region["region_pack_id"],
            "region_id": region["region_id"],
            "starting_location_id": location["entity_id"],
        }

        valid_character = {
            "mode": "custom",
            "name": "Mira",
            "species": "Human",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            "fighting_style": "Defense",
            "languages": ["Common", "Orc", "Goblin"],
            "background_equipment_option": "A",
            "equipment_package": "A",
        }
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "First steps in Neverwinter",
                "character": valid_character,
                "campaign_start": campaign_start,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        self.assertEqual(created["state"]["location"], "fr:city:neverwinter")
        self.assertEqual(
            created["state"]["locations"]["fr:city:neverwinter"]["name"],
            "Neverwinter",
        )
        restarted_manager = SessionManager(campaign_store=self.store)
        _, resumed, _, _, _ = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        session = resumed.game_session
        self.assertEqual(session.world_state["location"], "fr:city:neverwinter")
        self.assertEqual(session.location_display_name(), "Neverwinter")
        self.assertEqual(
            session.resolve_location_reference("Neverwinter"),
            "fr:city:neverwinter",
        )
        self.assertEqual(session.world_metadata["environment"], "city")
        self.assertIs(resumed.lore_authority.binding_status, BindingStatus.BOUND)
        self.assertEqual(
            resumed.lore_authority.region_pack_id,
            "fr:pack:the_north:neverwinter:v1",
        )
        self.assertEqual(
            resumed.lore_authority.starting_location_entity_id,
            "fr:city:neverwinter",
        )
        self.assertIn(
            "fr:city:neverwinter",
            session.world_state["locations"],
        )

    async def test_invalid_campaign_start_is_rejected_before_creation(self):
        options_response = await self.http.get("/api/game/campaign-start-options")
        option = options_response.json()["settings"][0]["regions"][0]
        valid_character = {
            "mode": "custom",
            "name": "Mira",
            "species": "Human",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            "fighting_style": "Defense",
            "languages": ["Common", "Orc", "Goblin"],
            "background_equipment_option": "A",
            "equipment_package": "A",
        }
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": valid_character,
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": option["region_pack_id"],
                    "region_id": "fr:region:sword_coast",
                    "starting_location_id": "fr:city:neverwinter",
                },
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "invalid_campaign_start",
        )
        self.assertEqual(self.store.list_campaigns(), [])
