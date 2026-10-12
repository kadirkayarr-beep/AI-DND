"""Session ids are not credentials. Temporary databases only."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import game
from api.auth import AuthenticationError, bind_principal, reset_principal
from api.persistence.campaign_models import CampaignNotFoundError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager, UnknownSessionError
from api.tests.auth_fixture import PLAYER_A, PLAYER_B, SAME_SUBJECT


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()


def _path(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


class SessionOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = _path(self.directory.name)
        self.store = CampaignStore(self.path)
        self.manager = SessionManager(campaign_store=self.store)

    def _create(self, principal, name: str):
        campaign_id, session_id, record, _ = self.manager.create_campaign(
            name=name, principal=principal,
        )
        return campaign_id, session_id, record

    def test_session_id_without_principal_is_not_access(self):
        _, session_id, _ = self._create(PLAYER_A, "A")
        with self.assertRaises(AuthenticationError):
            self.manager.get(session_id)

    def test_other_player_cannot_use_the_session_id(self):
        campaign_id, session_id, record = self._create(PLAYER_A, "A")
        self.assertEqual(record.owner_issuer, PLAYER_A.issuer)
        self.assertEqual(record.owner_subject, PLAYER_A.subject)
        self.assertIs(self.manager.get(session_id, principal=PLAYER_A), record)
        with self.assertRaises(UnknownSessionError):
            self.manager.get(session_id, principal=PLAYER_B)
        self.assertFalse(record.revoked)
        with self.assertRaises(CampaignNotFoundError):
            self.manager.resume_campaign(campaign_id, principal=PLAYER_B)
        with self.assertRaises(CampaignNotFoundError):
            self.manager.save_campaign(campaign_id, principal=PLAYER_B)
        self.assertFalse(
            self.manager.delete_campaign(campaign_id, principal=PLAYER_B)["deleted"]
        )
        self.assertIs(self.manager.get(session_id, principal=PLAYER_A), record)

    def test_same_subject_different_issuer_cannot_resume(self):
        campaign_id, session_id, _ = self._create(PLAYER_A, "A")
        with self.assertRaises(UnknownSessionError):
            self.manager.get(session_id, principal=SAME_SUBJECT)
        with self.assertRaises(CampaignNotFoundError):
            self.manager.resume_campaign(campaign_id, principal=SAME_SUBJECT)

    def test_delete_revokes_only_the_owner_session(self):
        campaign_id, session_id, record = self._create(PLAYER_A, "A")
        other = SessionManager(campaign_store=CampaignStore(self.path))
        other_sid, stale, *_ = other.resume_campaign(campaign_id, principal=PLAYER_A)
        self.assertTrue(self.manager.delete_campaign(campaign_id, principal=PLAYER_A)["deleted"])
        self.assertTrue(record.revoked)
        with self.assertRaises(UnknownSessionError):
            self.manager.get(session_id, principal=PLAYER_A)
        with self.assertRaises(UnknownSessionError):
            other.get(other_sid, principal=PLAYER_A)
        self.assertTrue(stale.revoked)

    def test_owner_column_change_revokes_the_old_session(self):
        campaign_id, session_id, record = self._create(PLAYER_A, "A")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                """
                UPDATE campaigns
                SET owner_issuer = ?, owner_subject = ?
                WHERE campaign_id = ?
                """,
                (PLAYER_B.issuer, PLAYER_B.subject, campaign_id),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(UnknownSessionError):
            self.manager.get(session_id, principal=PLAYER_A)
        self.assertTrue(record.revoked)
        resumed_id, resumed, *_ = self.manager.resume_campaign(
            campaign_id, principal=PLAYER_B,
        )
        self.assertNotEqual(resumed_id, session_id)
        self.assertEqual(resumed.owner_subject, PLAYER_B.subject)

    def test_ephemeral_session_id_does_not_cross_players(self):
        session_id, _ = self.manager.create(principal=PLAYER_A)
        with self.assertRaises(UnknownSessionError):
            self.manager.get(session_id, principal=PLAYER_B)

    def test_concurrent_players_keep_their_own_campaigns(self):
        errors = []
        created = {}

        def create(principal, name):
            token = bind_principal(principal)
            try:
                campaign_id, session_id, record, _ = self.manager.create_campaign(name=name)
                created[name] = (campaign_id, session_id, record)
            except Exception as error:
                errors.append(error)
            finally:
                reset_principal(token)

        threads = [
            threading.Thread(target=create, args=(PLAYER_A, "A")),
            threading.Thread(target=create, args=(PLAYER_B, "B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        for name, principal in (("A", PLAYER_A), ("B", PLAYER_B)):
            campaign_id, session_id, record = created[name]
            self.assertEqual(record.game_session.world_state.get("campaign_id"), campaign_id)
            self.assertIn(name, self.store.get_campaign(campaign_id, principal=principal).metadata["name"])
            self.assertIs(self.manager.get(session_id, principal=principal), record)
            other = PLAYER_B if principal is PLAYER_A else PLAYER_A
            with self.assertRaises(UnknownSessionError):
                self.manager.get(session_id, principal=other)
