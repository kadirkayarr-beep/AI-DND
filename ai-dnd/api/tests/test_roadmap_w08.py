"""W08: a closed NPC promise keeps the event that closed it and its open history.

The compaction/retrieval cases of this file pinned only `memory_archive`, which was never wired into play and was removed
(temizlik-2, D-509); the live npc_statements commitment case stays.
"""
from __future__ import annotations

import unittest

import npc_statements


class CompactionTests(unittest.TestCase):
    def test_closed_promise_keeps_its_reason(self):
        ledger = {"location": "loc_inn", "flags": {"turn_index": 30}, "npcs": [{"id": "npc_a", "name": "Aylin"}]}
        npc = ledger["npcs"][0]
        npc_statements.record(ledger, npc, "Beni hana götür.", "Aylin: “Seni hana götüreceğim.”", turn=3)
        promise_id = npc_statements.open_commitments(ledger, npc_id="npc_a")[0]["id"]
        npc_statements.transition_commitment(ledger, promise_id, "fulfilled", "event:inn_reached")
        closed = next(c for c in npc_statements.view(ledger)["commitments"] if c["id"] == promise_id)
        assert closed.get("closed_by_event_id") == "event:inn_reached" and closed["history"][0]["status"] == "open"


if __name__ == "__main__":
    unittest.main()
