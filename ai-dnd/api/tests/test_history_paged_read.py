"""D-495: reading a campaign does not fetch its whole story in one `fetchall`.

A long adventure (10 000 story rows here) is read in pages, and the result is
exactly what the one-shot read gave: the same rows in the same order, with the
narration source still on its row. Temporary SQLite only.
"""

from __future__ import annotations

import sqlite3
import unittest
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

from api.tests import test_campaign_api
from api.tests.town_seed import fixed_town

if TYPE_CHECKING:
    from collections.abc import Iterator

ROWS = 10_000
GUARDED = ("campaign_history", "campaign_turn_actions", "campaign_history_sources")
FETCHALL_LOG: list[str] = []
REAL_CONNECT = sqlite3.connect


class SpyCursor:
    """A cursor that notes the statements read with `fetchall`; the rest passes on."""

    def __init__(self, cursor: sqlite3.Cursor, sql: str) -> None:
        """Wrap `cursor`, which ran `sql`."""
        self._cursor = cursor
        self._sql = sql

    def fetchall(self) -> list[sqlite3.Row]:
        """Note the statement, then read everything at once."""
        FETCHALL_LOG.append(self._sql)
        return self._cursor.fetchall()

    def __getattr__(self, name: str) -> object:
        """Pass every other attribute to the real cursor."""
        return getattr(self._cursor, name)

    def __iter__(self) -> Iterator[sqlite3.Row]:
        """Iterate the real cursor."""
        return iter(self._cursor)


class SpyConnection(sqlite3.Connection):
    """A connection whose `execute` hands back a `SpyCursor`."""

    def execute(self, sql: str, *args: object) -> SpyCursor:
        """Run `sql` and wrap its cursor."""
        return SpyCursor(super().execute(sql, *args), str(sql))


def spied_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
    """Open a `SpyConnection` in place of a plain one."""
    return REAL_CONNECT(*args, factory=SpyConnection, **kwargs)


class TestHistoryReadIsPaged(unittest.IsolatedAsyncioTestCase):
    """The story, receipts and sources of a 10 000 row campaign come in pages."""

    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown

    async def test_ten_thousand_story_rows_are_read_in_pages(self) -> None:
        """Same rows, same order, source kept, and no `fetchall` on story tables."""
        with fixed_town(self, 49501):
            body = {"death_mode": "NORMAL"}
            created = (await self.http.post("/api/game/campaigns", json=body)).json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        action_id = str(uuid.uuid4())
        receipt = {"action_id": action_id, "request_hash": "a" * 64,
                   "response": {"action_id": action_id}}
        with record.turn_lock:
            self.manager.autosave_turn(
                record, "ilk", "anlati", narration_source="qwen",
                turn_action_receipt=receipt)
        expected = self.add_rows(campaign_id)
        FETCHALL_LOG.clear()
        with patch.object(sqlite3, "connect", spied_connect):
            stored = self.store.get_campaign(campaign_id)
        got = [(h["player_message"], h["narration"], h["created_at"])
               for h in stored.history]
        if got != expected:
            self.fail("the paged read returned other rows than the stored ones")
        if len(got) <= ROWS or stored.history[0]["narration_source"] != "qwen":
            self.fail("the first row lost its narration source or rows are missing")
        reads = [sql for sql in FETCHALL_LOG if any(n in sql for n in GUARDED)]
        if reads:
            self.fail(f"read with one fetchall: {reads}")

    def add_rows(self, campaign_id: str) -> list[tuple[str, str, str]]:
        """Append `ROWS` story rows by SQL; return every story row in order."""
        db = sqlite3.connect(self.store.path)
        try:
            last = db.execute(
                "SELECT MAX(sequence) FROM campaign_history WHERE campaign_id = ?",
                (campaign_id,)).fetchone()[0]
            db.executemany(
                "INSERT INTO campaign_history (campaign_id, sequence, "
                "player_message, narration, created_at) VALUES (?, ?, ?, ?, ?)",
                [(campaign_id, last + n, f"hamle {n}", f"anlati {n}",
                  "2026-11-26T10:00:00+00:00") for n in range(1, ROWS + 1)])
            db.commit()
            return [tuple(r) for r in db.execute(
                "SELECT player_message, narration, created_at FROM "
                "campaign_history WHERE campaign_id = ? ORDER BY sequence",
                (campaign_id,))]
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
