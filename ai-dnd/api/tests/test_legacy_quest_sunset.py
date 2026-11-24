"""Who still writes the legacy quest shape (desloppify: legacy_quest_view_no_sunset).

The legacy view (adventure.LEGACY_QUEST_FIELDS / LEGACY_STATE_VIEW / is_legacy_quest) is not an old-save-only shim:
game.accept_quest writes that shape for quest_catalog.CATALOG rows. The shipped catalog is empty, so a fresh campaign
holds no legacy row; tests that fill the catalog still pin the path, so the view goes only together with it.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import adventure
import quest_catalog
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.town_seed import fixed_town

CATALOG_QUEST = {
    "quest_id": "quest.sunset", "title": "Test", "description": "Test quest", "giver_npc_id": "npc.giver",
    "objectives": [{"objective_id": "visit", "description": "Visit", "type": "visit_location", "target": "forest"}],
}


class LegacyQuestSunset(unittest.TestCase):
    def new_session(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        manager = SessionManager(campaign_store=CampaignStore(Path(directory.name) / "c.sqlite3",
                                                              bound_principal=TEST_PLAYER))
        with fixed_town(self, 12260):
            return manager.create_campaign("Sunset")[2].game_session

    def test_the_shipped_catalog_is_empty_so_a_fresh_campaign_has_no_legacy_row(self):
        self.assertEqual(quest_catalog.CATALOG, ())
        session = self.new_session()
        self.assertFalse(any(adventure.is_legacy_quest(quest) for quest in session.world_state["quests"]))

    def test_a_catalog_quest_is_still_written_in_the_legacy_shape(self):
        session = self.new_session()
        with patch.object(quest_catalog, "CATALOG", (CATALOG_QUEST,)):
            accepted = session.accept_quest("quest.sunset")["quest"]
        self.assertTrue(adventure.is_legacy_quest(accepted))
        self.assertEqual(adventure.runtime_state(accepted), "ACTIVE")


if __name__ == "__main__":
    unittest.main()
