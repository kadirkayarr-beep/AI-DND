"""D-152 (ORTA-11): abandoned transient sessions and their successful replies stay bounded in process memory.

Transient (non-campaign) sessions live only in the SessionManager. Before the fix nothing ever dropped them, and every
successful turn kept its whole reply forever. Bounds under test:

* One owner keeps at most MAX_TRANSIENT_SESSIONS_PER_OWNER transient sessions; creating one more drops that owner's
  least recently used one (a dropped session answers "unknown session", like any unknown id). Another owner's
  sessions, campaign sessions and a session whose turn is running are never dropped.
* A transient session keeps at most MAX_TRANSIENT_TURN_RECEIPTS whole replies. An older reply is dropped but its
  action id stays reserved with its request hash: it is still "applied", can never be refused or run again, and a
  retry gets a refusal instead of a second run.

No campaign is started and nothing is written to disk.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.session_manager as session_manager_module
from api.main import create_app
from api.persistence.campaign_models import CampaignStaleError
from api.session_manager import ManagedSession, UnknownSessionError
from api.tests.auth_fixture import PLAYER_A, PLAYER_B, TEST_PLAYER, TestPlayerSessionManager, authenticator_for


def _receipt(action_id: str) -> dict:
    return {"action_id": action_id, "request_hash": "b" * 64, "response": {"narration": "x" * 1000}}


class TransientSessionCapTests(unittest.TestCase):
    def setUp(self):
        self.manager = TestPlayerSessionManager()
        cap = patch.object(session_manager_module, "MAX_TRANSIENT_SESSIONS_PER_OWNER", 3)
        cap.start()
        self.addCleanup(cap.stop)

    def _owned_transient_ids(self, principal):
        return [
            sid for sid, record in self.manager._sessions.items()
            if record.campaign_id is None and self.manager._owned_by(record, principal)
        ]

    def test_new_session_past_the_cap_drops_the_owners_least_recently_used_one(self):
        first, first_record = self.manager.create(PLAYER_A)
        second, _ = self.manager.create(PLAYER_A)
        third, _ = self.manager.create(PLAYER_A)
        self.manager.get(first, PLAYER_A)  # first is now the most recently used
        fourth, _ = self.manager.create(PLAYER_A)
        self.assertEqual(sorted(self._owned_transient_ids(PLAYER_A)), sorted([first, third, fourth]))
        with self.assertRaises(UnknownSessionError):
            self.manager.get(second, PLAYER_A)
        self.assertIs(self.manager.get(first, PLAYER_A), first_record)

    def test_dropped_record_is_revoked_so_a_late_turn_cannot_save_into_it(self):
        _, oldest = self.manager.create(PLAYER_A)
        for _ in range(3):
            self.manager.create(PLAYER_A)
        self.assertTrue(oldest.revoked)

    def test_many_creations_stay_within_the_cap(self):
        for _ in range(20):
            self.manager.create(PLAYER_A)
        self.assertEqual(len(self._owned_transient_ids(PLAYER_A)), 3)

    def test_another_owners_sessions_are_never_dropped(self):
        b_ids = [self.manager.create(PLAYER_B)[0] for _ in range(3)]
        for _ in range(10):
            self.manager.create(PLAYER_A)
        self.assertEqual(sorted(self._owned_transient_ids(PLAYER_B)), sorted(b_ids))

    def test_campaign_sessions_are_not_counted_or_dropped(self):
        campaign_record = ManagedSession(
            game_session=object(), campaign_id=str(uuid.uuid4()),
            owner_issuer=PLAYER_A.issuer, owner_subject=PLAYER_A.subject,
        )
        self.manager._sessions["campaign-session"] = campaign_record
        for _ in range(10):
            self.manager.create(PLAYER_A)
        self.assertIs(self.manager._sessions.get("campaign-session"), campaign_record)
        self.assertFalse(campaign_record.revoked)

    def test_a_session_with_a_running_turn_is_not_dropped(self):
        busy, busy_record = self.manager.create(PLAYER_A)
        with busy_record.turn_lock:
            for _ in range(5):
                self.manager.create(PLAYER_A)
            self.assertIn(busy, self.manager._sessions)
            self.assertFalse(busy_record.revoked)

    def test_the_new_session_is_never_the_one_dropped(self):
        """Every older session mid-turn: the cap waits for one to finish; the id just handed out stays usable."""
        busy = [self.manager.create(PLAYER_A)[1] for _ in range(3)]
        for record in busy:
            record.turn_lock.acquire()
        try:
            new_id, new_record = self.manager.create(PLAYER_A)
            self.assertFalse(new_record.revoked)
            self.assertIs(self.manager.get(new_id, PLAYER_A), new_record)
        finally:
            for record in busy:
                record.turn_lock.release()


class TransientReceiptCapTests(unittest.TestCase):
    def setUp(self):
        self.manager = TestPlayerSessionManager()
        cap = patch.object(session_manager_module, "MAX_TRANSIENT_TURN_RECEIPTS", 3)
        cap.start()
        self.addCleanup(cap.stop)
        _, self.record = self.manager.create(PLAYER_A)
        self.ids = [str(uuid.uuid4()) for _ in range(5)]
        for action_id in self.ids:
            self.manager.autosave_turn(self.record, "p", "n", turn_action_receipt=_receipt(action_id))

    def test_only_the_newest_whole_replies_are_kept(self):
        whole = [r for r in self.record.turn_action_receipts.values() if "response" in r]
        self.assertEqual(len(whole), 3)
        for action_id in self.ids[-3:]:
            self.assertEqual(self.manager.get_turn_action(self.record, action_id), _receipt(action_id))

    def test_an_old_id_is_still_applied_and_never_runs_again(self):
        old = self.ids[0]
        self.assertEqual(self.manager.action_state(self.record, old), "applied")
        with self.assertRaises(CampaignStaleError):
            self.manager.get_turn_action(self.record, old)

    def test_an_old_id_can_never_be_refused_or_abandoned(self):
        old = self.ids[1]
        self.assertFalse(self.manager.record_refused_action(
            self.record, old, "a" * 64, 409, {"code": "x", "message": "x", "not_applied": True},
        ))
        self.assertEqual(self.manager.abandon_action(self.record, old), {"state": "applied"})
        self.assertNotIn(old, self.record.refused_actions)

    def test_a_dropped_reply_keeps_only_its_hash(self):
        kept = self.record.turn_action_receipts[self.ids[0]]
        self.assertNotIn("response", kept)
        self.assertEqual(kept["request_hash"], "b" * 64)


class DroppedReplyOverHttpTests(unittest.TestCase):
    """The status and abandon routes say "applied" with no reply for an old id; only a retried turn is refused (409)."""

    def setUp(self):
        cap = patch.object(session_manager_module, "MAX_TRANSIENT_TURN_RECEIPTS", 1)
        cap.start()
        self.addCleanup(cap.stop)
        self.manager = TestPlayerSessionManager()
        self.client = TestClient(
            create_app(session_manager=self.manager, ollama_adapter=None, authenticator=authenticator_for(TEST_PLAYER)),
            raise_server_exceptions=False,
        )
        self.session_id, self.record = self.manager.create(TEST_PLAYER)
        self.old, newer = str(uuid.uuid4()), str(uuid.uuid4())
        for action_id in (self.old, newer):
            self.manager.autosave_turn(self.record, "p", "n", turn_action_receipt=_receipt(action_id))
        self.assertNotIn("response", self.record.turn_action_receipts[self.old])

    def test_status_of_an_old_id_is_applied_without_a_reply(self):
        status = self.client.get(f"/api/game/sessions/{self.session_id}/actions/{self.old}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["state"], "applied", status.text)
        self.assertIsNone(status.json()["response"], status.text)

    def test_abandon_of_an_old_id_is_applied_and_closes_nothing(self):
        closed = self.client.post(f"/api/game/sessions/{self.session_id}/actions/{self.old}/abandon")
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(closed.json()["state"], "applied", closed.text)
        self.assertIsNone(closed.json()["response"], closed.text)
        self.assertNotIn(self.old, self.record.refused_actions)

    def test_a_retried_turn_with_an_old_id_is_refused_not_run(self):
        before = len(self.record.game_session.messages)
        retry = self.client.post(f"/api/game/sessions/{self.session_id}/turn",
                                 json={"message": "I look around.", "action_id": self.old})
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["detail"]["code"], "campaign_stale", retry.text)
        self.assertEqual(len(self.record.game_session.messages), before)


if __name__ == "__main__":
    unittest.main()
