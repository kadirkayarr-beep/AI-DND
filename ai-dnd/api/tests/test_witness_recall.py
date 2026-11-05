"""Transient witnessed-source IDs cannot authorize unrelated speech or claims."""
import copy
import unittest

import witness_recall as recall


class WitnessSources(unittest.TestCase):
    def setUp(self):
        self.npc = {"id": "kalila", "name": "Kalila", "location": "town"}
        self.deed = {"kind": "arson", "text": "Atölye içinde ateş yaktı", "turn": 1,
                     "witnesses": ["kalila"], "heard": [], "told": []}
        self.world = {"location": "town", "npcs": [self.npc], "flags": {"deeds": [self.deed]}}

    def proposal(self):
        return {"scope": "witnessed_deed", "source_id": recall.candidates(self.world, self.npc)[0]["source_id"],
                "evidence_quote": "Ne yaptım hatırlıyor musun?"}

    def answer(self, proposal, about="memory"):
        return recall.answer(self.world, self.npc, "Ne yaptım hatırlıyor musun?", proposal, about=about)

    def test_valid_selection_returns_only_the_engine_source_and_never_mutates_it(self):
        before = copy.deepcopy(self.world)
        self.assertEqual(self.answer(self.proposal()), self.deed["text"])
        self.assertEqual(self.world, before)

    def test_nonwitness_claim_hearsay_and_unsupported_kinds_are_not_candidates(self):
        for change in ({"witnesses": [], "told": ["kalila"]}, {"witnesses": [], "heard": ["kalila"]},
                       {"witnesses": ["other"]}, {"kind": "claim"}, {"kind": "unknown"},
                       {"text": None}, {"text": ""}, {"witnesses": "kalila"}):
            with self.subTest(change=change):
                self.world["flags"]["deeds"] = [{**self.deed, **change}]
                self.assertEqual(recall.candidates(self.world, self.npc), [])

    def test_missing_foreign_and_changed_source_ids_fail_closed(self):
        proposal = self.proposal()
        for raw in (None, {}, {**proposal, "source_id": True}, {**proposal, "source_id": "foreign"},
                    {**proposal, "evidence_quote": "another request"}, {**proposal, "scope": "own_words"},
                    {**proposal, "extra": "authority"}):
            with self.subTest(raw=raw):
                self.assertIsNone(self.answer(raw))
        self.deed["text"] = "Başka bir olay"
        self.assertIsNone(self.answer(proposal))

    def test_npc_words_and_own_words_never_use_witness_authority(self):
        for about in ("npc_words", "own_words", "unknown"):
            self.assertIsNone(self.answer(self.proposal(), about))

    def test_addressed_npc_must_be_here_and_candidate_ids_are_speaker_bound(self):
        proposal = self.proposal()
        other = {**self.npc, "id": "other"}
        self.world["npcs"].append(other)
        self.deed["witnesses"].append("other")
        self.assertNotEqual(recall.candidates(self.world, other)[0]["source_id"], proposal["source_id"])
        self.assertIsNone(recall.answer(self.world, other, proposal["evidence_quote"], proposal, about="memory"))
        self.npc["location"] = "elsewhere"
        self.assertEqual(recall.candidates(self.world, self.npc), [])

    def test_at_most_eight_recent_sources_are_offered_without_changing_the_ledger(self):
        self.world["flags"]["deeds"] = [{**self.deed, "text": f"Olay {i}"} for i in range(12)]
        before = copy.deepcopy(self.world)
        rows = recall.candidates(self.world, self.npc)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]["text"], "Olay 11")
        self.assertEqual(len({row["source_id"] for row in rows}), 8)
        self.assertEqual(self.world, before)
