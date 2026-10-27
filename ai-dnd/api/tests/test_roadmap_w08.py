"""W08: compaction keeps every critical source resolvable, never turns a note into a fact, and retrieval respects who may know.

`memory_archive.compact_memory` moves old per-NPC interactions out of the active short context into a source-traced archive
(the original entry is kept whole and resolves by a stable source id; a summary is labelled as a summary and never as an event).
`retrieve_memory` answers from active + archive within a token budget, resolves Turkish names with case suffixes, pronouns
through an explicit last-referent and explicit aliases, and hides a secret from an observer who may not know it.
Measured quantities (bytes before/after, archive bytes, estimated context tokens, elapsed time) are reported separately.
"""
from __future__ import annotations

import copy
import json
import unittest

import memory_archive
import npc_statements
from api.narrative_memory import update_narrative_memory

PROMISE = "Yarın sana ışık getireceğim, söz veriyorum."
SECRET_LINE = "Berk'e gizli kasa şifresini söylüyorum: SIR-B-7731."


def world(turn):
    return {
        "location": "loc_inn", "flags": {"turn_index": turn},
        "locations": {"loc_inn": {"id": "loc_inn", "name": "Han"}},
        "npcs": [{"id": "npc_a", "name": "Aylin", "role": "Hancı", "location": "loc_inn"},
                 {"id": "npc_b", "name": "Berk", "role": "Tüccar", "location": "loc_inn"}],
    }


def say(memory, npc_id, text, turn):
    action = {"action": "talk", "npc_id": npc_id, "status": "resolved"}
    return update_narrative_memory(memory, player_message=text, narration="Cevap verdi.", action_result=action,
                                   world_state_before=world(turn - 1), world_state_after=world(turn))


def build_memory():
    memory = say(None, "npc_a", PROMISE, 1)
    for index in range(18):
        memory = say(memory, "npc_a", f"Bugün hava {index} derece soğuk mu?", index + 2)
    memory = say(memory, "npc_b", SECRET_LINE, 25)
    memory["npc_interactions"]["npc_b"][-1]["visibility"] = {"secret": True, "known_to": ["npc_b"]}
    # a manual player note: descriptive, never a world fact
    memory["npc_interactions"]["npc_a"].append({
        "text": "Not: Aylin'in gizli bir kardeşi olabilir.", "topic": "not", "turn_index": 26, "importance": "high",
        "authority": "narrative_continuity", "source": "player_note"})
    return memory


POLICY = {"active_limit": 5, "keep_importance": "high"}
KNOWLEDGE = {"observer_id": "player", "aliases": {"npc_a": ["hancı", "han sahibi"]}, "last_npc_id": "npc_a"}


class CompactionTests(unittest.TestCase):
    def test_compaction_preserves_source_and_visibility(self):
        memory = build_memory()
        ledger = {"location": "loc_inn", "flags": {"turn_index": 30}, "npcs": [{"id": "npc_a", "name": "Aylin"}]}
        npc = ledger["npcs"][0]
        npc_statements.record(ledger, npc, "Beni hana götür.", "Aylin: “Seni hana götüreceğim.”", turn=3)
        promise_id = npc_statements.open_commitments(ledger, npc_id="npc_a")[0]["id"]
        npc_statements.transition_commitment(ledger, promise_id, "fulfilled", "event:inn_reached")
        frozen = copy.deepcopy(memory)
        critical = [memory_archive.source_id_of("npc_a", memory["npc_interactions"]["npc_a"][0]),
                    memory_archive.source_id_of("npc_b", memory["npc_interactions"]["npc_b"][-1])]
        result = memory_archive.compact_memory(memory, POLICY)
        note_entry = next(e for e in memory["npc_interactions"]["npc_a"] if e.get("source") == "player_note")
        note_id = memory_archive.source_id_of("npc_a", note_entry)
        observer_b = memory_archive.retrieve_memory(
            {"text": "Berk'e ne söylemiştim?", "npc_id": "npc_b"}, {"observer_id": "npc_b"}, 400, compacted=result)
        observer_player = memory_archive.retrieve_memory(
            {"text": "Berk'e ne söylemiştim?", "npc_id": "npc_b"}, KNOWLEDGE, 400, compacted=result)
        closed = next(c for c in npc_statements.view(ledger)["commitments"] if c["id"] == promise_id)
        obs = {
            "critical_source_ids_before": critical,
            "resolvable_source_ids_after": [sid for sid in critical + [note_id] if memory_archive.resolve_source(result, sid)],
            "note_became_fact": memory_archive.resolve_source(result, note_id)["authority"] != "player_note",
            "retrieved_secret_for_wrong_observer": any("SIR-B-7731" in json.dumps(item, ensure_ascii=False)
                                                        for item in observer_player["items"]),
            "closed_promise_reason_preserved": closed.get("closed_by_event_id") == "event:inn_reached"
                                               and closed["history"][0]["status"] == "open",
        }
        assert set(obs["critical_source_ids_before"]) <= set(obs["resolvable_source_ids_after"])
        assert obs["note_became_fact"] is False
        assert obs["retrieved_secret_for_wrong_observer"] is False
        assert obs["closed_promise_reason_preserved"] is True
        self.assertEqual(memory, frozen, "compaction never mutates its input")
        self.assertLessEqual(len(result["active"]["npc_interactions"]["npc_a"]), POLICY["active_limit"] + 2)
        self.assertTrue(any("SIR-B-7731" in json.dumps(item, ensure_ascii=False) for item in observer_b["items"]),
                        "the observer who may know the secret still retrieves it")
        self.assertEqual(memory_archive.resolve_source(result, note_id)["authority"], "player_note")
        self.assertEqual(result["metrics"]["entries_before"], result["metrics"]["entries_active"] + result["metrics"]["entries_archived"],
                         "nothing is lost: every entry is active or archived")

    def test_high_importance_stays_active_and_summaries_are_not_events(self):
        result = memory_archive.compact_memory(build_memory(), POLICY)
        active_texts = [e["text"] for e in result["active"]["npc_interactions"]["npc_a"]]
        self.assertIn(PROMISE, active_texts, "a high-importance promise is never archived out of the active context")
        for record in result["archive"]:
            self.assertEqual(record["summary_authority"], "summary")
            self.assertNotEqual(record["summary_authority"], "event")
            self.assertTrue(record["source_id"].startswith("mem:"))

    def test_retrieval_resolves_turkish_names_pronouns_and_aliases_within_budget(self):
        result = memory_archive.compact_memory(build_memory(), POLICY)
        by_name = memory_archive.retrieve_memory({"text": "Aylin'e verdiğim sözü hatırlıyor musun?"}, KNOWLEDGE, 400, compacted=result)
        by_pronoun = memory_archive.retrieve_memory({"text": "Ona verdiğim sözü hatırlıyor mu?"}, KNOWLEDGE, 400, compacted=result)
        by_alias = memory_archive.retrieve_memory({"text": "Han sahibine ne söz vermiştim?"}, KNOWLEDGE, 400, compacted=result)
        for packet in (by_name, by_pronoun, by_alias):
            self.assertEqual(packet["npc_id"], "npc_a")
            self.assertTrue(any(PROMISE in item["text"] for item in packet["items"]))
        tiny = memory_archive.retrieve_memory({"text": "Aylin'e verdiğim sözü hatırlıyor musun?"}, KNOWLEDGE, 20, compacted=result)
        self.assertLessEqual(tiny["used_tokens"], 20)
        self.assertGreater(tiny["dropped"], 0)
        self.assertEqual({"bytes_before", "bytes_after", "archive_bytes", "context_tokens", "elapsed_ms"} - set(result["metrics"]), set())


if __name__ == "__main__":
    unittest.main()
