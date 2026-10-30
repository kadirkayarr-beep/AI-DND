"""W07: a promise has an identity; a restatement is not a new debt; a closed promise keeps its history and reason.

Before W07 every spoken restatement of "seni hana götüreceğim" created another open commitment (only the immediately
consecutive identical statement was skipped), and a promise could only be closed as "fulfilled" with a free-text note.
Identity is speaker + recipient + scope (kind, objects, destination) + origin event; while a commitment is open a restatement
with the same scope is recorded on it, a different scope is a genuinely new promise, and 1000 distinct promises are all kept.
"""
from __future__ import annotations

import unittest

import npc_statements

NPC = {"id": "npc_marek", "name": "Marek", "location": "loc_city"}


def world():
    return {"location": "loc_city", "flags": {"turn_index": 1}, "npcs": [NPC],
            "locations": {"loc_city": {"id": "loc_city", "name": "Şehir"}}}


def say(w, player, npc_line, turn):
    return npc_statements.record(w, NPC, player, f"Marek: “{npc_line}”", turn=turn)


def open_ids(w):
    return [c["id"] for c in npc_statements.open_commitments(w, npc_id="npc_marek")]


class CommitmentIdentityTests(unittest.TestCase):
    def test_commitment_dedup_preserves_genuinely_new_promise(self):
        w = world()
        say(w, "Beni hana götür.", "Evet, seni hana götüreceğim.", 3)
        first_ids = open_ids(w)
        say(w, "Hani beni hana götürecektin?", "Evet, seni hana götüreceğim.", 5)
        say(w, "Peki ne zaman?", "Seni hana götüreceğim dedim ya.", 6)
        restated_ids = open_ids(w)
        say(w, "Bana bir şey ver.", "Sana bir fener getireceğim.", 7)
        new_ids = open_ids(w)
        original = first_ids[0]
        npc_statements.transition_commitment(w, original, "fulfilled", "event:walked_to_inn")
        closed = next(c for c in npc_statements.view(w)["commitments"] if c["id"] == original)
        obs = {
            "same_promise_restatement_count": len(restated_ids),
            "genuinely_new_promise_count": len(new_ids),
            "closed_promise_reason_event_id": closed.get("closed_by_event_id"),
            "expected_closure_event_id": "event:walked_to_inn",
            "closure_erased_history": not closed.get("history") or closed["history"][0].get("status") != "open",
        }
        assert obs["same_promise_restatement_count"] == 1
        assert obs["genuinely_new_promise_count"] == 2
        assert obs["closed_promise_reason_event_id"] == obs["expected_closure_event_id"]
        assert obs["closure_erased_history"] is False
        self.assertEqual(closed["status"], "fulfilled")
        self.assertEqual([item["status"] for item in closed["history"]], ["open", "fulfilled"])
        self.assertGreaterEqual(closed["restatements"], 2, "restatements are recorded on the promise, not lost")

    def test_every_status_keeps_its_reason_and_closed_is_final(self):
        w = world()
        for index, status in enumerate(("fulfilled", "broken", "cancelled", "closed")):
            say(w, f"Bana nesne{'abcd'[index] * 3} ver.", f"Sana nesne{'abcd'[index] * 3} vereceğim.", 10 + index)
        ids = open_ids(w)
        self.assertEqual(len(ids), 4)
        for commitment_id, status in zip(ids, ("fulfilled", "broken", "cancelled", "closed")):
            npc_statements.transition_commitment(w, commitment_id, status, f"event:{status}")
        by_id = {c["id"]: c for c in npc_statements.view(w)["commitments"]}
        for commitment_id, status in zip(ids, ("fulfilled", "broken", "cancelled", "closed")):
            self.assertEqual((by_id[commitment_id]["status"], by_id[commitment_id]["closed_by_event_id"]), (status, f"event:{status}"))
        with self.assertRaises(ValueError):
            npc_statements.transition_commitment(w, ids[0], "broken", "event:later")
        with self.assertRaises(ValueError):
            npc_statements.transition_commitment(w, ids[1], "not_a_status", "event:x")
        with self.assertRaises(ValueError):
            npc_statements.transition_commitment(w, "commit_9999", "closed", "event:x")
        self.assertEqual(npc_statements.open_commitments(w, npc_id="npc_marek"), [])

    def test_different_promises_of_one_kind_are_not_merged(self):
        # review finding: same kind (and same place kind) with different content is a different promise
        w = world()
        say(w, "Bana bir şey göster.", "Sana kılıcı göstereceğim.", 1)
        say(w, "Bir şey daha göster.", "Sana haritayı göstereceğim.", 2)
        self.assertEqual(len(open_ids(w)), 2)
        say(w, "Kılıcı unutma.", "Sana kılıcı göstereceğim.", 3)
        self.assertEqual(len(open_ids(w)), 2, "a true restatement still merges")
        # inflection does not split one promise in two
        say(w, "Fener?", "Sana fener getireceğim.", 4)
        say(w, "Feneri?", "Sana feneri getireceğim.", 5)
        self.assertEqual(len(open_ids(w)), 3)

    def test_fulfil_does_not_overwrite_a_closed_promises_reason(self):
        w = world()
        say(w, "Beni hana götür.", "Seni hana götüreceğim.", 1)
        commitment_id = open_ids(w)[0]
        npc_statements.transition_commitment(w, commitment_id, "broken", "event:left_town")
        npc_statements.fulfil(w, commitment_id, "walked_with_player")
        closed = next(c for c in npc_statements.view(w)["commitments"] if c["id"] == commitment_id)
        self.assertEqual((closed["status"], closed["closed_by_event_id"]), ("broken", "event:left_town"))
        self.assertNotIn("fulfilled_by", closed)

    def test_a_promise_made_again_after_closing_is_new(self):
        w = world()
        say(w, "Beni hana götür.", "Seni hana götüreceğim.", 1)
        npc_statements.transition_commitment(w, open_ids(w)[0], "fulfilled", "event:done")
        say(w, "Yine hana götür.", "Seni hana götüreceğim.", 9)
        self.assertEqual(len(open_ids(w)), 1)
        self.assertEqual(len(npc_statements.view(w)["commitments"]), 2)

    def test_many_restatements_stay_bounded_and_many_distinct_promises_survive(self):
        w = world()
        for turn in range(1000):
            say(w, f"Hani götürecektin {turn}?", "Seni hana götüreceğim.", 100 + turn)
        self.assertEqual(len(open_ids(w)), 1)
        commitment = npc_statements.view(w)["commitments"][0]
        self.assertGreaterEqual(commitment["restatements"], 999)
        self.assertLessEqual(len(commitment.get("restated_turns", [])), 5)
        distinct = world()

        def token(number):
            letters = ""
            for _ in range(3):
                letters += "bcdfghjklmnprstvyz"[number % 18]
                number //= 18
            return f"nesne{letters}"
        for number in range(500):
            say(distinct, f"Bana {token(number)} ver.", f"Sana {token(number)} vereceğim.", 1 + number)
        self.assertEqual(len(open_ids(distinct)), 500)


if __name__ == "__main__":
    unittest.main()
