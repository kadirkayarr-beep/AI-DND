"""Campaign ownership is enforced in SQL. Temporary databases only."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid

import game
from api.auth import AuthenticationError, Principal
from api.persistence.campaign_models import CampaignNotFoundError
from api.persistence.campaign_store import CampaignStore
from api.tests.auth_fixture import PLAYER_A, PLAYER_B, SAME_SUBJECT


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()


def _path(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


class CampaignOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = _path(self.directory.name)
        self.store = CampaignStore(self.path)

    def _create(self, principal: Principal, name: str = "Owned"):
        session = game.create_session(seed=1)
        campaign_id = str(uuid.uuid4())
        metadata = self.store.create_campaign(
            campaign_id, name, session, principal=principal,
        )
        return campaign_id, metadata, session

    def test_create_writes_owner_in_the_same_row(self):
        campaign_id, _, _ = self._create(PLAYER_A)
        connection = sqlite3.connect(self.path)
        try:
            row = connection.execute(
                """
                SELECT owner_issuer, owner_subject, ownership_state, payload_json
                FROM campaigns WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0], PLAYER_A.issuer)
        self.assertEqual(row[1], PLAYER_A.subject)
        self.assertEqual(row[2], "owned")
        payload = json.loads(row[3])
        self.assertNotIn("owner_issuer", payload)
        self.assertNotIn("owner_subject", payload.get("engine_save", {}).get("world_state", {}))

    def test_two_players_cannot_read_or_write_each_other(self):
        campaign_id, _, session = self._create(PLAYER_A, "A")
        self.assertEqual(
            [row["campaign_id"] for row in self.store.list_campaigns(principal=PLAYER_A)],
            [campaign_id],
        )
        self.assertEqual(self.store.list_campaigns(principal=PLAYER_B), [])
        self.assertTrue(self.store.campaign_exists(campaign_id, principal=PLAYER_A))
        self.assertFalse(self.store.campaign_exists(campaign_id, principal=PLAYER_B))
        with self.assertRaises(CampaignNotFoundError):
            self.store.get_campaign(campaign_id, principal=PLAYER_B)
        with self.assertRaises(CampaignNotFoundError):
            self.store.save_campaign(campaign_id, session, principal=PLAYER_B)
        self.assertFalse(self.store.delete_campaign(campaign_id, principal=PLAYER_B))
        self.assertTrue(self.store.campaign_exists(campaign_id, principal=PLAYER_A))

    def test_same_subject_different_issuer_is_not_the_owner(self):
        campaign_id, _, _ = self._create(PLAYER_A)
        self.assertEqual(PLAYER_A.subject, SAME_SUBJECT.subject)
        self.assertNotEqual(PLAYER_A.issuer, SAME_SUBJECT.issuer)
        with self.assertRaises(CampaignNotFoundError):
            self.store.get_campaign(campaign_id, principal=SAME_SUBJECT)
        self.assertEqual(self.store.list_campaigns(principal=SAME_SUBJECT), [])

    def test_unowned_campaign_is_invisible_and_not_claimed(self):
        campaign_id = str(uuid.uuid4())
        payload = json.dumps({"engine_save": {"world_state": {"location": "tavern"}}})
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, name, created_at, updated_at, last_played_at,
                    campaign_version, save_version, engine_hash, character_name,
                    character_race, character_class, character_level, location,
                    payload_json, revision, ownership_state
                ) VALUES (?, 'Legacy', 't', 't', 't', 1, 4, 'h', 'Mira', 'Human',
                          'Fighter', 1, 'tavern', ?, 0, 'unowned')
                """,
                (campaign_id, payload),
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(self.store.list_campaigns(principal=PLAYER_A), [])
        with self.assertRaises(CampaignNotFoundError):
            self.store.get_campaign(campaign_id, principal=PLAYER_A)
        self.assertFalse(self.store.delete_campaign(campaign_id, principal=PLAYER_A))
        connection = sqlite3.connect(self.path)
        try:
            row = connection.execute(
                "SELECT owner_issuer, owner_subject, ownership_state, payload_json FROM campaigns"
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNone(row[0])
        self.assertIsNone(row[1])
        self.assertEqual(row[2], "unowned")
        self.assertEqual(row[3], payload)

    def test_missing_principal_fails_closed(self):
        with self.assertRaises(AuthenticationError):
            self.store.list_campaigns()

    def test_concurrent_owners_do_not_swap_rows(self):
        barrier = threading.Barrier(2)
        created: dict[str, str] = {}

        def worker(principal: Principal, label: str):
            barrier.wait()
            campaign_id, _, _ = self._create(principal, label)
            created[label] = campaign_id

        threads = [
            threading.Thread(target=worker, args=(PLAYER_A, "A")),
            threading.Thread(target=worker, args=(PLAYER_B, "B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(
            self.store.get_campaign(created["A"], principal=PLAYER_A).metadata["name"],
            "A",
        )
        self.assertEqual(
            self.store.get_campaign(created["B"], principal=PLAYER_B).metadata["name"],
            "B",
        )
        with self.assertRaises(CampaignNotFoundError):
            self.store.get_campaign(created["A"], principal=PLAYER_B)
