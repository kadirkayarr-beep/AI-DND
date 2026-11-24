"""An unexpected fault while checking a failed save still answers UNKNOWN, but is no longer silent.

desloppify autosave_check_returns_none_on_any_error: campaign_save_landed and _commit_already_durable turned every
exception into None. None (unknown, nobody guesses) stays the answer, so rollback and receipts behave as before; a
known campaign failure stays quiet, any other exception is logged with its traceback.
"""
from __future__ import annotations
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from api import main
from api.persistence.campaign_models import CampaignStorageError
from api.session_manager import SessionManager


class SaveLandedUnknownIsLogged(unittest.TestCase):
    def check(self, error):
        manager = SessionManager()
        store = MagicMock()
        store.get_campaign.side_effect = error
        record = SimpleNamespace(campaign_id="campaign-1")
        with patch.object(manager, "_require_campaign_store", return_value=store), \
                patch.object(manager, "_sealed_principal", return_value=None):
            answer = manager.campaign_save_landed(record, ("campaign-1", 3))
        store.get_campaign.assert_called_once()
        return answer

    def test_an_unexpected_fault_answers_unknown_and_is_logged(self):
        with self.assertLogs("ai_dnd.api.session_manager", "ERROR") as logged:
            self.assertIsNone(self.check(RuntimeError("disk on fire")))
        self.assertTrue(any("save landed" in line for line in logged.output), logged.output)

    def test_a_campaign_failure_answers_unknown_quietly(self):
        with self.assertNoLogs("ai_dnd.api.session_manager", "ERROR"):
            self.assertIsNone(self.check(CampaignStorageError("storage down")))


class CommitAlreadyDurableUnknownIsLogged(unittest.TestCase):
    def check(self, error):
        manager = MagicMock()
        manager.get_turn_action.side_effect = error
        answer = main._commit_already_durable(manager, object(), "action-1", "a" * 64, {})
        manager.get_turn_action.assert_called_once()
        return answer

    def test_an_unexpected_fault_answers_unknown_and_is_logged(self):
        with self.assertLogs("ai_dnd.api", "ERROR") as logged:
            self.assertIsNone(self.check(RuntimeError("disk on fire")))
        self.assertTrue(any("receipt" in line for line in logged.output), logged.output)

    def test_a_campaign_failure_answers_unknown_quietly(self):
        with self.assertNoLogs("ai_dnd.api", "ERROR"):
            self.assertIsNone(self.check(CampaignStorageError("storage down")))


if __name__ == "__main__":
    unittest.main()
