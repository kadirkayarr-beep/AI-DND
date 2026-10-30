"""W06: a high-importance NPC interaction survives per-entity overflow (priority + recency, deterministic).

Before W06 `update_narrative_memory` built `(high + low)[-20:]`: highs were put first and the LAST 20 kept, so a new high
utterance after 20 medium ones was the first thing sliced away. Collection retention and real context retrieval are asserted
separately; another NPC's lines never enter this NPC's packet.
"""
from __future__ import annotations

import copy
import json
import unittest

from api import narrative_memory
from api.narrative_memory import build_narrative_context, update_narrative_memory

PROMISE = "Yarın sana ışık getireceğim, söz veriyorum."


def world(turn):
    return {
        "location": "loc_inn", "flags": {"turn_index": turn},
        "locations": {"loc_inn": {"id": "loc_inn", "name": "Han"}},
        "npcs": [
            {"id": "npc_a", "name": "Aylin", "role": "Hancı", "location": "loc_inn"},
            {"id": "npc_b", "name": "Berk", "role": "Tüccar", "location": "loc_inn"},
        ],
    }


def say(memory, npc_id, text, turn):
    action = {"action": "talk", "npc_id": npc_id, "status": "resolved"}
    return update_narrative_memory(
        memory, player_message=text, narration="Cevap verdi.", action_result=action,
        world_state_before=world(turn - 1), world_state_after=world(turn))


class OverflowRetentionTests(unittest.TestCase):
    def test_high_memory_survives_entity_overflow(self):
        memory = say(None, "npc_b", "Berk'e gizli bir rakam söylüyorum: SIR-B-7731.", 1)
        for index in range(20):
            memory = say(memory, "npc_a", f"Bugün hava {index} derece soğuk mu?", index + 2)
        memory = say(memory, "npc_a", PROMISE, 30)
        kept = memory["npc_interactions"]["npc_a"]
        action = {"action": "talk", "npc_id": "npc_a", "status": "resolved"}
        packet, _meta = build_narrative_context(
            memory, {"location_id": "loc_inn"}, "Aylin, verdiğim sözü hatırlıyor musun?", action)
        obs = {
            "retained_interactions": kept,
            "new_high_event_id": PROMISE,
            "retained_event_ids": [item["text"] for item in kept],
            "retrieved_promise_id": next((item["text"] for item in
                                          packet["relevant_continuity"]["npc_interactions"].get("npc_a", [])
                                          if item["text"] == PROMISE), None),
            "expected_promise_id": PROMISE,
            "retrieved_other_npc_secret": "SIR-B-7731" in json.dumps(packet, ensure_ascii=False),
            "threads_observed_separately": len(memory["unresolved_threads"]),
        }
        assert len(obs["retained_interactions"]) == 20
        assert obs["new_high_event_id"] in obs["retained_event_ids"]
        assert obs["retrieved_promise_id"] == obs["expected_promise_id"]
        assert obs["retrieved_other_npc_secret"] is False
        self.assertIsInstance(obs["threads_observed_separately"], int)

    def test_retention_is_priority_then_recency_with_stable_ties(self):
        def entry(text, importance, turn):
            return {"text": text, "importance": importance, "turn_index": turn}
        entries = [entry(f"m{i}", "medium", i) for i in range(5)] + [entry("h1", "high", 1), entry("h2", "high", 9)]
        kept = narrative_memory.retain_entity_interactions(entries, 4)
        self.assertEqual([item["text"] for item in kept], ["h1", "h2", "m3", "m4"])
        again = narrative_memory.retain_entity_interactions(copy.deepcopy(entries), 4)
        self.assertEqual(kept, again, "deterministic")
        self.assertEqual(len(narrative_memory.retain_entity_interactions(entries, 100)), 7)
        # more highs than the limit: the most recent highs win, nothing exceeds the limit
        highs = [entry(f"h{i}", "high", i) for i in range(6)]
        self.assertEqual([item["text"] for item in narrative_memory.retain_entity_interactions(highs, 3)], ["h3", "h4", "h5"])


if __name__ == "__main__":
    unittest.main()
