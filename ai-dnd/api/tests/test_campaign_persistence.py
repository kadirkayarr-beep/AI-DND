"""Deterministic persistence and restart tests for campaign records."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignNotFoundError,
    CampaignValidationError,
)
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


class CampaignPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.store = CampaignStore(self.database_path)
        self.manager = SessionManager(campaign_store=self.store)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_campaign(self, name="Test campaign"):
        return self.manager.create_campaign(name)

    def test_campaign_save_and_runtime_rng_survive_manager_restart(self):
        campaign_id, original_session_id, record, metadata = self.create_campaign()
        session = record.game_session
        session.character["current_hp"] = session.character["max_hp"] - 3
        session.world_state["location"] = "tavern"
        session.world_state["inventory"].append("Torch")
        session.world_state["npcs"].append(
            {
                "id": "npc_saved",
                "name": "Mira",
                "role": "innkeeper",
                "location": "tavern",
                "memory": [
                    {"speaker": "player", "text": "My name is Arven."},
                    {"speaker": "npc", "text": "I will remember that, Arven."},
                ],
                "current_hp": 8,
                "max_hp": 8,
                "armor_class": 10,
                "combat_status": "active",
            }
        )
        session.world_state["combat"].update(
            {
                "active": True,
                "round": 2,
                "initiative_order": ["player", "npc_saved"],
                "current_turn_index": 1,
                "target_id": "npc_saved",
            }
        )
        session.ensure_combat_state()
        session.rng.random()
        expected_save = copy.deepcopy(session.serialize_game_state())
        expected_rng = session.rng.getstate()

        self.manager.autosave_turn(
            record,
            "Mira'ya adım Arven diyorum.",
            "Mira başıyla selam verir.",
        )

        restarted_manager = SessionManager(
            campaign_store=CampaignStore(self.database_path)
        )
        resumed_session_id, resumed, resumed_metadata, history, _ = (
            restarted_manager.resume_campaign(campaign_id)
        )
        restored = resumed.game_session

        self.assertNotEqual(original_session_id, resumed_session_id)
        self.assertEqual(resumed_metadata["campaign_id"], campaign_id)
        self.assertEqual(restored.serialize_game_state(), expected_save)
        self.assertEqual(restored.rng.getstate(), expected_rng)
        self.assertEqual(restored.character["current_hp"], expected_save["player"]["current_hp"])
        self.assertIn("Torch", restored.world_state["inventory"])
        self.assertEqual(restored.world_state["location"], "tavern")
        self.assertEqual(
            restored.world_state["npcs"][0]["memory"],
            expected_save["world_state"]["npcs"][0]["memory"],
        )
        self.assertEqual(restored.world_state["combat"]["round"], 2)
        self.assertEqual(history[0]["player_message"], "Mira'ya adım Arven diyorum.")
        self.assertEqual(history[0]["narration"], "Mira başıyla selam verir.")
        self.assertEqual(metadata["campaign_id"], campaign_id)

    def test_campaign_ids_are_opaque_and_campaigns_are_isolated(self):
        first_id, _, first_record, _ = self.create_campaign("First")
        second_id, _, second_record, _ = self.create_campaign("Second")
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(__import__("uuid").UUID(first_id).version, 4)
        self.assertEqual(__import__("uuid").UUID(second_id).version, 4)

        first_record.game_session.world_state["inventory"].append("Only first")
        first_record.game_session.character["current_hp"] = 5
        self.manager.save_campaign(first_id)

        restarted = SessionManager(campaign_store=CampaignStore(self.database_path))
        _, first_resumed, _, _, _ = restarted.resume_campaign(first_id)
        _, second_resumed, _, _, _ = restarted.resume_campaign(second_id)
        self.assertIn("Only first", first_resumed.game_session.world_state["inventory"])
        self.assertNotIn("Only first", second_resumed.game_session.world_state["inventory"])
        self.assertEqual(first_resumed.game_session.character["current_hp"], 5)
        self.assertNotEqual(
            first_resumed.game_session.character["current_hp"],
            second_resumed.game_session.character["current_hp"],
        )

    def test_invalid_new_state_does_not_replace_the_last_good_save(self):
        campaign_id, _, record, _ = self.create_campaign()
        before = self.store.get_campaign(campaign_id).payload
        record.game_session.world_state["inventory"].append({"forged": "item"})

        with self.assertRaises(CampaignValidationError):
            self.manager.save_campaign(campaign_id)

        after = self.store.get_campaign(campaign_id).payload
        self.assertEqual(after, before)

    def test_corrupt_campaign_is_rejected_without_affecting_other_campaigns(self):
        good_id, _, _, _ = self.create_campaign("Good")
        corrupt_id, _, _, _ = self.create_campaign("Corrupt")
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                ("{not-json", corrupt_id),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(CampaignCorruptError):
            self.store.get_campaign(corrupt_id)
        self.assertEqual(self.store.get_campaign(good_id).metadata["name"], "Good")

    def test_unsupported_campaign_version_is_rejected(self):
        campaign_id, _, _, _ = self.create_campaign()
        stored = self.store.get_campaign(campaign_id)
        payload = copy.deepcopy(stored.payload)
        payload["version"] = 999
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), campaign_id),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(CampaignCorruptError):
            self.store.get_campaign(campaign_id)

    def test_invalid_ids_cannot_be_used_as_paths(self):
        with self.assertRaises(CampaignNotFoundError):
            self.store.get_campaign("../../saves/adventure.json")

    def test_campaign_list_contains_only_safe_metadata(self):
        campaign_id, _, _, _ = self.create_campaign("Ledger entry")
        listed = self.store.list_campaigns()
        self.assertEqual(listed[0]["campaign_id"], campaign_id)
        self.assertEqual(listed[0]["name"], "Ledger entry")
        self.assertNotIn("payload", listed[0])
        self.assertNotIn("engine_hash", listed[0])
        self.assertNotIn("messages", listed[0])

    def test_configured_secret_is_never_persisted(self):
        secret = "campaign-persistence-secret-sentinel"
        with patch.dict(os.environ, {"OLLAMA_PROXY_TOKEN": secret}):
            session = game.create_session(seed=1)
            session.world_state.setdefault("events", []).append(secret)
            with self.assertRaises(CampaignValidationError):
                self.store.create_campaign(
                    str(uuid.uuid4()),
                    "No secret",
                    session,
                )
        self.assertEqual(self.store.list_campaigns(), [])

    def test_engine_version_mismatch_is_rejected(self):
        campaign_id, _, _, _ = self.create_campaign()
        stored = self.store.get_campaign(campaign_id)
        payload = copy.deepcopy(stored.payload)
        payload["engine_save"]["version"] = 999
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE campaigns SET payload_json = ?, save_version = 999 "
                "WHERE campaign_id = ?",
                (json.dumps(payload), campaign_id),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(CampaignCorruptError):
            self.store.get_campaign(campaign_id)

    def test_resume_updates_last_played_without_rewriting_save_timestamp(self):
        created_at = "2026-09-28T18:00:00+00:00"
        resumed_at = "2026-09-28T19:00:00+00:00"
        with patch(
            "api.persistence.campaign_store._now",
            side_effect=[created_at, resumed_at],
        ):
            campaign_id, _, _, _ = self.create_campaign("Played later")
            restarted = SessionManager(
                campaign_store=CampaignStore(self.database_path)
            )
            _, _, metadata, _, _ = restarted.resume_campaign(campaign_id)

        self.assertEqual(metadata["created_at"], created_at)
        self.assertEqual(metadata["updated_at"], created_at)
        self.assertEqual(metadata["last_played_at"], resumed_at)


if __name__ == "__main__":
    unittest.main()