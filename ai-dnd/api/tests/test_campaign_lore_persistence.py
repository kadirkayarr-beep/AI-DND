from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.lore_authority import BindingStatus, CampaignLoreState
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


def bound_lore_state() -> CampaignLoreState:
    return CampaignLoreState.from_mapping(
        {
            "binding_status": "BOUND",
            "setting_profile": "FORGOTTEN_REALMS",
            "world_id": "world:toril",
            "epoch_id": "epoch:current",
            "region_id": "region:faerun",
            "current_location_entity_id": "city:waterdeep",
            "player_known_fact_ids": ["fact:waterdeep-known"],
            "npc_known_fact_ids": {
                "npc_001": ["fact:waterdeep-npc-known"],
            },
            "campaign_overrides": [],
            "procedural_entity_refs": ["location_001"],
            "lore_discoveries": ["fact:waterdeep-known"],
        }
    )


class CampaignLorePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.store = CampaignStore(self.database_path)
        self.manager = SessionManager(campaign_store=self.store)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_new_campaign_persists_lore_state_outside_engine_save(self):
        campaign_id, _, record, _ = self.manager.create_campaign("Lore test")
        stored = self.store.get_campaign(campaign_id)

        self.assertEqual(
            record.lore_authority.binding_status,
            BindingStatus.LEGACY_UNBOUND,
        )
        self.assertIn("lore_authority", stored.payload)
        self.assertNotIn("lore_authority", stored.payload["engine_save"])
        self.assertEqual(
            stored.payload["lore_authority"]["binding_status"],
            "LEGACY_UNBOUND",
        )

    def test_lore_references_survive_save_and_campaign_resume(self):
        campaign_id, _, record, _ = self.manager.create_campaign("Lore test")
        record.lore_authority = bound_lore_state()
        self.manager.save_campaign(campaign_id)

        restarted_manager = SessionManager(
            campaign_store=CampaignStore(self.database_path)
        )
        _, resumed_record, _, _, _ = restarted_manager.resume_campaign(campaign_id)

        self.assertEqual(
            resumed_record.lore_authority.to_dict(),
            record.lore_authority.to_dict(),
        )
        self.assertNotIn(
            "lore_authority",
            self.store.get_campaign(campaign_id).payload["engine_save"],
        )

    def test_direct_save_preserves_existing_lore_when_argument_is_omitted(self):
        campaign_id, _, record, _ = self.manager.create_campaign("Lore test")
        record.lore_authority = bound_lore_state()
        self.manager.save_campaign(campaign_id)

        self.store.save_campaign(campaign_id, record.game_session)

        self.assertEqual(
            self.store.get_campaign(campaign_id).payload["lore_authority"],
            record.lore_authority.to_dict(),
        )

    def test_legacy_payload_migrates_to_unbound_without_remapping_engine_state(self):
        campaign_id, _, record, _ = self.manager.create_campaign("Legacy test")
        original_engine_save = record.game_session.serialize_game_state()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("lore_authority")
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), campaign_id),
            )

        restarted_manager = SessionManager(
            campaign_store=CampaignStore(self.database_path)
        )
        _, resumed_record, _, _, _ = restarted_manager.resume_campaign(campaign_id)
        migrated = CampaignStore(self.database_path).get_campaign(campaign_id)

        self.assertEqual(
            resumed_record.lore_authority.binding_status,
            BindingStatus.LEGACY_UNBOUND,
        )
        self.assertEqual(migrated.payload["lore_authority"]["binding_status"], "LEGACY_UNBOUND")
        self.assertEqual(
            resumed_record.game_session.serialize_game_state(),
            original_engine_save,
        )

    def test_malformed_lore_state_is_rejected_as_corrupt_campaign(self):
        campaign_id, _, _, _ = self.manager.create_campaign("Corrupt test")
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            payload = json.loads(row[0])
            payload["lore_authority"] = {
                "binding_status": "BOUND",
                "setting_profile": None,
                "world_id": None,
                "epoch_id": None,
                "region_id": None,
                "current_location_entity_id": None,
                "player_known_fact_ids": [],
                "npc_known_fact_ids": {},
                "campaign_overrides": [],
                "procedural_entity_refs": [],
                "lore_discoveries": [],
            }
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), campaign_id),
            )

        with self.assertRaises(CampaignCorruptError):
            self.store.get_campaign(campaign_id)


if __name__ == "__main__":
    unittest.main()