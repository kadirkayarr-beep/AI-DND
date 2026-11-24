"""Save version provenance: an ordinary resume keeps the stored engine-save version. Isolated files only.

The explicit migration cases pinned only `save_migration`, an old-save tool no code called; it was removed (temizlik-2, D-510).
"""

from pathlib import Path
import tempfile
import unittest

from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


from api.tests.auth_fixture import TEST_PLAYER


class SaveMigrationTests(unittest.TestCase):
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
