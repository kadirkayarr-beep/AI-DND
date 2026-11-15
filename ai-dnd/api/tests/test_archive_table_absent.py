"""D-077: the file under an already open store has no `campaign_turn_actions_archive` table (an older file put in
its place while the server runs). The adventure still loads and the next save still lands, as for the narration
source table; a committed action id is still refused, and nothing creates the table. Temporary SQLite only.
"""

from __future__ import annotations

import sqlite3
import unittest
import uuid

from api.persistence.campaign_models import CampaignValidationError
from api.tests import test_campaign_api
from api.tests import test_narration_source_record as narration_record
from api.tests.test_narration_source_record import tables
from api.tests.town_seed import fixed_town

ARCHIVE = "campaign_turn_actions_archive"


def drop_archive_table(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"DROP TABLE {ARCHIVE}")
        connection.commit()
    finally:
        connection.close()


def history_rows(path, campaign_id):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT sequence, player_message, narration FROM campaign_history WHERE campaign_id = ? ORDER BY sequence",
            (campaign_id,)).fetchall()
    finally:
        connection.close()


def receipt_ids(path, campaign_id):
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute(
            "SELECT action_id FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY rowid", (campaign_id,))]
    finally:
        connection.close()


class FileWithoutTheArchiveTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown
    started = narration_record.WriterBoundary.started
    receipt = narration_record.WriterBoundary.receipt

    async def test_the_adventure_loads_without_the_archive(self):
        campaign_id, record = await self.started(7701)
        with record.turn_lock:
            self.manager.autosave_turn(record, "ilk", "anlatı", turn_action_receipt=self.receipt())
        drop_archive_table(self.store.path)
        stored = self.store.get_campaign(campaign_id)
        self.assertEqual([(row["player_message"], row["narration"]) for row in stored.history],
                         [(message, narration) for _, message, narration in history_rows(self.store.path, campaign_id)])
        self.assertEqual(stored.history[-1]["player_message"], "ilk")
        detail = await self.http.get(f"/api/game/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(len(detail.json()["history"]), len(stored.history))
        # Reading wrote nothing: the table is still absent.
        self.assertNotIn(ARCHIVE, tables(self.store.path))

    async def test_a_save_with_a_receipt_still_lands_and_leaves_the_table_absent(self):
        campaign_id, record = await self.started(7702)
        drop_archive_table(self.store.path)
        before = history_rows(self.store.path, campaign_id)
        receipt = self.receipt()
        with record.turn_lock:
            self.manager.autosave_turn(record, "sonraki", "anlatı", turn_action_receipt=receipt)
        after = history_rows(self.store.path, campaign_id)
        self.assertEqual(after[:-1], before)
        self.assertEqual(after[-1][1:], ("sonraki", "anlatı"))
        self.assertEqual(receipt_ids(self.store.path, campaign_id)[-1], receipt["action_id"])
        self.assertNotIn(ARCHIVE, tables(self.store.path))

    async def test_a_committed_action_id_is_still_refused(self):
        campaign_id, record = await self.started(7703)
        drop_archive_table(self.store.path)
        receipt = self.receipt()
        with record.turn_lock:
            self.manager.autosave_turn(record, "ilk", "anlatı", turn_action_receipt=receipt)
        before = history_rows(self.store.path, campaign_id)
        receipts = receipt_ids(self.store.path, campaign_id)
        revision = self.store.get_campaign(campaign_id).metadata["revision"]
        with record.turn_lock, self.assertRaises(CampaignValidationError):
            self.manager.autosave_turn(record, "ikinci", "anlatı", turn_action_receipt=self.receipt(receipt["action_id"]))
        self.assertEqual(history_rows(self.store.path, campaign_id), before)
        self.assertEqual(receipt_ids(self.store.path, campaign_id), receipts)
        self.assertEqual(self.store.get_campaign(campaign_id).metadata["revision"], revision)
        self.assertNotIn(ARCHIVE, tables(self.store.path))

    async def test_the_http_turn_path_still_plays_without_the_archive(self):
        # The real turn route claims the intent, reads the action and its state before and after the save.
        # The deterministic city search of test_campaign_api: no model is called on this turn.
        start = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                 "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
        with fixed_town(self, 7704):
            created = (await self.http.post("/api/game/campaigns", json={"campaign_start": start})).json()
        session_id, campaign_id = created["session_id"], created["campaign_id"]
        drop_archive_table(self.store.path)
        before = len(history_rows(self.store.path, campaign_id))
        action_id = str(uuid.uuid4())
        body = {"message": "Yakınlarda bir taverna arıyorum.", "action_id": action_id}
        turn = await self.http.post(f"/api/game/sessions/{session_id}/turn", json=body)
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual(len(history_rows(self.store.path, campaign_id)), before + 1)
        self.assertEqual(receipt_ids(self.store.path, campaign_id)[-1], action_id)
        # The same id again is a replay of the stored reply, not a second turn.
        replay = await self.http.post(f"/api/game/sessions/{session_id}/turn", json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(len(history_rows(self.store.path, campaign_id)), before + 1)
        state = await self.http.get(f"/api/game/sessions/{session_id}/actions/{action_id}")
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["state"], "applied")
        unknown = await self.http.get(f"/api/game/sessions/{session_id}/actions/{uuid.uuid4()}")
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertEqual(unknown.json()["state"], "unknown")
        open_action = await self.http.get(f"/api/game/sessions/{session_id}/actions/unresolved")
        self.assertEqual(open_action.status_code, 200, open_action.text)
        self.assertIsNone(open_action.json()["unresolved"])
        self.assertNotIn(ARCHIVE, tables(self.store.path))

    async def test_a_refusal_is_still_recorded_without_the_archive(self):
        campaign_id, record = await self.started(7705)
        drop_archive_table(self.store.path)
        refused = self.receipt()
        self.assertTrue(self.store.record_refused_action(
            campaign_id, refused["action_id"], refused["request_hash"], 409, {"code": "x", "message": "x"}))
        self.assertEqual(self.store.action_state(campaign_id, refused["action_id"]), "not_applied")
        self.assertIsNone(self.store.get_turn_action(campaign_id, refused["action_id"]))
        self.assertNotIn(ARCHIVE, tables(self.store.path))


if __name__ == "__main__":
    unittest.main()
