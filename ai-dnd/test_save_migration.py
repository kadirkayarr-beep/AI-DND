"""Explicit save migration and version provenance. Isolated files only."""

import json
from pathlib import Path
import tempfile
import unittest

import game
import save_migration
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


from api.tests.auth_fixture import TEST_PLAYER
def _session():
    session = game.create_session(seed=4)
    session.character["xp"] = 300
    session.character["level"] = 2
    session.world_state["xp_awarded_event_ids"] = ["combat:3:npc_test"]
    return session


class SaveMigrationTests(unittest.TestCase):
    def test_v3_to_v4_keeps_progression_and_does_not_invent_a_feat(self):
        session = _session()
        session._persisted_engine_format = 3
        session.character["cantrips"] = ["Fire Bolt"]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            destination = Path(directory) / "migrated.json"
            session.save_game(source)
            original = source.read_bytes()
            payload = json.loads(original.decode("utf-8"))
            self.assertEqual(payload["version"], 3)
            self.assertNotIn("cantrips", payload["player"])
            self.assertNotIn("origin_feat", payload["player"])
            save_migration.migrate_save_file(source, destination, 4)
            self.assertEqual(source.read_bytes(), original)
            migrated = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(migrated["version"], 4)
            self.assertEqual(migrated["player"]["xp"], 300)
            self.assertEqual(migrated["player"]["level"], 2)
            self.assertEqual(migrated["player"]["cantrips"], [])
            self.assertEqual(migrated["player"]["spells"], [])
            self.assertEqual(migrated["player"]["spell_slots_remaining"], {"1": 0})
            self.assertNotIn("origin_feat", migrated["player"])
            self.assertEqual(
                migrated["world_state"]["xp_awarded_event_ids"],
                ["combat:3:npc_test"],
            )
            self.assertEqual(payload["version"], 3)
            restarted = game.create_session(seed=5)
            restarted.load_game(destination)
            self.assertEqual(restarted._persisted_engine_format, 4)
            self.assertEqual(restarted.character["xp"], 300)
            self.assertEqual(restarted.character["cantrips"], [])
            self.assertIsNone(restarted.character.get("origin_feat"))

    def test_rejected_v5_migration_leaves_the_source_bytes(self):
        session = _session()
        session._persisted_engine_format = 3
        session.character["xp"] = 6500
        session.character["level"] = 1
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            destination = Path(directory) / "rejected.json"
            session.save_game(source)
            original = source.read_bytes()
            with self.assertRaises(ValueError):
                save_migration.migrate_save_file(source, destination, 5)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(destination.exists())
            with self.assertRaises(ValueError):
                save_migration.migrate_save_file(source, source, 4)
            self.assertEqual(source.read_bytes(), original)

            partial = json.loads(original.decode("utf-8"))
            partial["player"]["cantrips"] = ["Fire Bolt"]
            partial_path = Path(directory) / "partial.json"
            partial_path.write_bytes(original)
            partial_path.write_text(json.dumps(partial), encoding="utf-8")
            before = partial_path.read_bytes()
            with self.assertRaises(ValueError):
                save_migration.migrate_save_payload(partial, 4)
            self.assertEqual(partial["player"]["cantrips"], ["Fire Bolt"])
            self.assertEqual(partial["version"], 3)
            self.assertEqual(partial_path.read_bytes(), before)

    def test_consistent_v4_can_migrate_to_v5(self):
        session = _session()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "v4.json"
            destination = Path(directory) / "v5.json"
            session.save_game(source)
            original = source.read_bytes()
            save_migration.migrate_save_file(source, destination, 5)
            self.assertEqual(source.read_bytes(), original)
            migrated = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(migrated["version"], 5)
            self.assertEqual(migrated["player"]["xp"], 300)
            self.assertEqual(migrated["player"]["level"], 2)
            loaded = game.create_session(seed=6)
            loaded.load_game(destination)
            self.assertEqual(loaded._persisted_engine_format, 5)
            resaved = Path(directory) / "again.json"
            loaded.save_game(resaved)
            self.assertEqual(json.loads(resaved.read_text(encoding="utf-8"))["version"], 5)

    def test_ordinary_campaign_resume_keeps_v3_and_v5(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=store)
            campaign_id, _, record, _ = manager.create_campaign("Historical")
            session = record.game_session
            self.assertEqual(session.serialize_game_state()["version"], 4)

            session._persisted_engine_format = 3
            session.character["xp"] = 300
            session.character["cantrips"] = ["Fire Bolt"]
            manager.save_campaign(campaign_id)
            stored = store.get_campaign(campaign_id)
            self.assertEqual(stored.payload["engine_save"]["version"], 3)
            self.assertEqual(stored.payload["engine_save"]["player"]["xp"], 300)
            self.assertNotIn("cantrips", stored.payload["engine_save"]["player"])
            revision = stored.metadata["revision"]
            SessionManager(campaign_store=store).resume_campaign(campaign_id)
            SessionManager(campaign_store=store).resume_campaign(campaign_id)
            after = store.get_campaign(campaign_id)
            self.assertEqual(after.metadata["revision"], revision)
            self.assertEqual(after.payload["engine_save"]["version"], 3)
            self.assertEqual(after.payload["engine_save"]["player"]["xp"], 300)

            session._persisted_engine_format = 5
            session.character["xp"] = 0
            session.character["level"] = 1
            session.character["proficiency_bonus"] = 2
            session.world_state["xp_awarded_event_ids"] = []
            manager.save_campaign(campaign_id)
            stored = store.get_campaign(campaign_id)
            self.assertEqual(stored.payload["engine_save"]["version"], 5)
            revision = stored.metadata["revision"]
            SessionManager(campaign_store=store).resume_campaign(campaign_id)
            after = store.get_campaign(campaign_id)
            self.assertEqual(after.metadata["revision"], revision)
            self.assertEqual(after.payload["engine_save"]["version"], 5)
            self.assertEqual(after.payload["engine_save"]["player"]["cantrips"], ["Fire Bolt"])


if __name__ == "__main__":
    unittest.main()
