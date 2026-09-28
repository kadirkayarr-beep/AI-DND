from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx
import game
from api.main import create_app
from api.ollama_adapter import (
    AuthenticatedOllamaAdapter,
    MODEL_NAME,
    canonical_world_metadata_context,
)
from api.persistence.campaign_store import CampaignStore
from api.schemas import CampaignCreateRequest, TurnRequest
from api.serializers import serialize_session_state
from api.session_manager import SessionManager
from api.world_metadata import (
    WorldMetadataError,
    infer_environment,
    set_session_world_metadata,
    validate_world_metadata,
    world_metadata_for_state,
)
from pydantic import ValidationError


def _location_state(location_id: str, name: str, location_type: str) -> dict:
    return {
        "location": location_id,
        "locations": {
            location_id: {
                "id": location_id,
                "name": name,
                "type": location_type,
            }
        },
    }


class CapturingOllamaClient:
    def __init__(self, content: str = '{"world_updates":{},"narration":"Tamam."}'):
        self.content = content
        self.last_kwargs = None

    def chat(self, *args, **kwargs):
        self.last_kwargs = kwargs
        return {"message": {"content": self.content}}


class WorldMetadataTests(unittest.IsolatedAsyncioTestCase):
    def test_new_session_exposes_supported_defaults(self):
        manager = SessionManager()
        _, record = manager.create()

        state = serialize_session_state(record.game_session)

        self.assertEqual(
            state["world"],
            {
                "environment": "unknown",
                "time_of_day": "day",
                "weather": "clear",
            },
        )
        self.assertEqual(
            world_metadata_for_state(record.game_session.world_state),
            state["world"],
        )

    def test_location_categories_use_server_location_metadata(self):
        cases = (
            ("tavern", "Taverna", "building", "tavern"),
            ("forest", "Orman", "wilderness", "forest"),
            ("old-city", "Eski Şehir", "settlement", "city"),
            ("path-2", "Kuzey Geçidi", "road", "road"),
            ("unmapped", "Adsız Bölge", "structure", "unknown"),
        )
        for location_id, name, location_type, expected in cases:
            with self.subTest(location=location_id):
                self.assertEqual(
                    infer_environment(
                        _location_state(location_id, name, location_type)
                    ),
                    expected,
                )

    def test_unknown_or_missing_world_metadata_has_safe_defaults(self):
        self.assertEqual(
            world_metadata_for_state({}),
            {
                "environment": "unknown",
                "time_of_day": "day",
                "weather": "clear",
            },
        )
        self.assertEqual(
            world_metadata_for_state(
                _location_state("forest", "Orman", "wilderness"),
                {"environment": "unknown", "time_of_day": "night", "weather": "fog"},
            ),
            {"environment": "forest", "time_of_day": "night", "weather": "fog"},
        )

    def test_invalid_metadata_values_and_fields_are_rejected(self):
        invalid_values = (
            {"environment": "volcano", "time_of_day": "day", "weather": "clear"},
            {"environment": "forest", "time_of_day": "midnight", "weather": "clear"},
            {"environment": "forest", "time_of_day": "day", "weather": "hail"},
            {"environment": [], "time_of_day": "day", "weather": "clear"},
            {
                "environment": "forest",
                "time_of_day": "day",
                "weather": "clear",
                "location": "browser-controlled",
            },
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(WorldMetadataError):
                validate_world_metadata(value)

    def test_browser_requests_cannot_set_world_metadata(self):
        with self.assertRaises(ValidationError):
            CampaignCreateRequest.model_validate(
                {
                    "character": {
                        "mode": "custom",
                        "name": "Test",
                        "race": "Elf",
                        "class": "Wizard",
                    },
                    "world": {"environment": "forest"},
                }
            )
        with self.assertRaises(ValidationError):
            TurnRequest.model_validate(
                {"message": "Ormana gidiyorum", "weather": "storm"}
            )

    async def test_api_state_exposes_canonical_world_and_rejects_forged_fields(self):
        manager = SessionManager()
        app = create_app(session_manager=manager, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created = await client.post("/api/game/sessions")
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["session_id"]
            self.assertEqual(
                created.json()["state"]["world"],
                {
                    "environment": "unknown",
                    "time_of_day": "day",
                    "weather": "clear",
                },
            )
            self.assertEqual(
                (await client.get(f"/api/game/sessions/{session_id}/state")).json()["world"],
                created.json()["state"]["world"],
            )
            forged_campaign = await client.post(
                "/api/game/campaigns",
                json={"world": {"environment": "forest"}},
            )
            forged_turn = await client.post(
                f"/api/game/sessions/{session_id}/turn",
                json={"message": "Ormana gidiyorum", "weather": "storm"},
            )

        self.assertEqual(forged_campaign.status_code, 422)
        self.assertEqual(forged_turn.status_code, 422)

    def test_model_receives_dynamic_read_only_metadata_without_committing_output(self):
        session = game.create_session(seed=12)
        session.world_state.update(_location_state("tavern", "Taverna", "building"))
        set_session_world_metadata(
            session,
            {"environment": "unknown", "time_of_day": "evening", "weather": "rain"},
        )
        original_metadata = dict(session.world_metadata)
        client = CapturingOllamaClient(
            '{"world_updates":{"weather":"storm"},"narration":"Dışarıda fırtına kopuyor."}'
        )
        adapter = AuthenticatedOllamaAdapter(client)

        with canonical_world_metadata_context(
            lambda: world_metadata_for_state(
                session.world_state,
                session.world_metadata,
            )
        ):
            adapter.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Narrator rules."},
                    {"role": "user", "content": "What is the weather?"},
                ],
            )
            self.assertIn(
                "environment=tavern; time_of_day=evening; weather=rain",
                client.last_kwargs["messages"][0]["content"],
            )
            session.world_state.update(
                _location_state("forest", "Orman", "wilderness")
            )
            adapter.chat(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": "Narrator rules."}],
            )
            self.assertIn(
                "environment=forest; time_of_day=evening; weather=rain",
                client.last_kwargs["messages"][0]["content"],
            )

        self.assertEqual(session.world_metadata, original_metadata)

    def test_metadata_survives_campaign_save_and_new_manager_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "campaigns.sqlite3"
            store = CampaignStore(database_path)
            manager = SessionManager(campaign_store=store)
            campaign_id, _, record, _ = manager.create_campaign("Metadata test")
            record.game_session.world_state["location"] = "forest"
            record.game_session.world_metadata = {
                "environment": "forest",
                "time_of_day": "evening",
                "weather": "rain",
            }
            manager.save_campaign(campaign_id)

            restarted = SessionManager(campaign_store=CampaignStore(database_path))
            _, resumed, _, _, state = restarted.resume_campaign(campaign_id)

            expected = {
                "environment": "forest",
                "time_of_day": "evening",
                "weather": "rain",
            }
            self.assertEqual(resumed.game_session.world_metadata, expected)
            self.assertEqual(state["world"], expected)

    def test_two_campaigns_keep_world_metadata_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "campaigns.sqlite3"
            store = CampaignStore(database_path)
            manager = SessionManager(campaign_store=store)
            first_id, _, first, _ = manager.create_campaign("First")
            second_id, _, second, _ = manager.create_campaign("Second")
            first.game_session.world_state["location"] = "tavern"
            first.game_session.world_metadata = {
                "environment": "tavern",
                "time_of_day": "evening",
                "weather": "fog",
            }
            second.game_session.world_state["location"] = "forest"
            second.game_session.world_metadata = {
                "environment": "forest",
                "time_of_day": "dawn",
                "weather": "snow",
            }
            manager.save_campaign(first_id)
            manager.save_campaign(second_id)

            restarted = SessionManager(campaign_store=CampaignStore(database_path))
            _, resumed_first, _, _, _ = restarted.resume_campaign(first_id)
            _, resumed_second, _, _, _ = restarted.resume_campaign(second_id)

            self.assertEqual(resumed_first.game_session.world_metadata["weather"], "fog")
            self.assertEqual(resumed_second.game_session.world_metadata["weather"], "snow")
            self.assertEqual(resumed_first.game_session.world_metadata["time_of_day"], "evening")
            self.assertEqual(resumed_second.game_session.world_metadata["time_of_day"], "dawn")

    def test_legacy_campaign_is_backfilled_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "campaigns.sqlite3"
            store = CampaignStore(database_path)
            manager = SessionManager(campaign_store=store)
            campaign_id, _, record, _ = manager.create_campaign("Legacy")
            record.game_session.world_state["location"] = "tavern"
            set_session_world_metadata(record.game_session)
            manager.save_campaign(campaign_id)

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                payload = json.loads(row[0])
                payload.pop("world_metadata")
                connection.execute(
                    "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                    (json.dumps(payload), campaign_id),
                )

            restarted = SessionManager(campaign_store=CampaignStore(database_path))
            _, resumed, _, _, state = restarted.resume_campaign(campaign_id)

            self.assertEqual(
                state["world"],
                {"environment": "tavern", "time_of_day": "day", "weather": "clear"},
            )
            with sqlite3.connect(database_path) as connection:
                migrated_payload = json.loads(
                    connection.execute(
                        "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                        (campaign_id,),
                    ).fetchone()[0]
                )
            self.assertIn("world_metadata", migrated_payload)
            self.assertEqual(
                migrated_payload["world_metadata"],
                resumed.game_session.world_metadata,
            )


if __name__ == "__main__":
    unittest.main()