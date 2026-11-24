"""SessionManager.create_campaign refuses a bad death mode with a CampaignError (desloppify: inconsistent_error_contract).

It raised a bare ValueError while every other campaign refusal is a CampaignError subclass. The new error keeps
ValueError as a second base, so any caller that caught ValueError still catches it.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from api.persistence.campaign_models import CampaignError, InvalidDeathModeError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.town_seed import fixed_town


class CreateCampaignDeathModeError(unittest.TestCase):
    def test_a_bad_death_mode_is_a_campaign_error_and_still_a_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=store)
            with fixed_town(self, 16301), self.assertRaises(InvalidDeathModeError) as raised:
                manager.create_campaign("Bad mode", death_mode="BOGUS")
            self.assertIsInstance(raised.exception, CampaignError)
            self.assertIsInstance(raised.exception, ValueError)
            self.assertEqual(str(raised.exception), "Campaign death mode is invalid.")
            self.assertEqual(store.list_campaigns(principal=TEST_PLAYER), [], "nothing is created")


if __name__ == "__main__":
    unittest.main()
