"""BM Task 7: the journal shows what was really heard (play finding B3).

A thread or rumour counts as heard only when the reply carries its own words (and, when the model named it in
`voiced`, the model's key agrees). A place or an owner's name alone marks nothing. The generic "Söylediklerin
konuşmada duyuldu." line is not copied into the journal any more (owner decision K-BM-4). The journal is saved state:
Undo takes the heard mark and its trail back."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import interaction_adventure
import local_places
import quest_log
import town_knowledge
import world_threads
from api.campaign_journal import empty_campaign_journal, update_campaign_journal
from api.tests import test_front_proposal as fp
from api.tests import test_npc_scene_time as scene_time
from api.tests.test_town_knowledge import person, seeded

GENERIC = "Söylediklerin konuşmada duyuldu."


class HeardMarks(unittest.TestCase):
    """`town_knowledge.note_mention` on a hand-made town."""

    def setUp(self):
        self.world = seeded("bind")
        self.npc = next(person(f"npc_{i}", "Barmen") for i in range(50)
                        if any(item["kind"] == "thread"
                               for item in town_knowledge.public_knowledge(self.world, person(f"npc_{i}", "Barmen"))))
        self.world["npcs"].append(self.npc)
        self.item = next(i for i in town_knowledge.public_knowledge(self.world, self.npc) if i["kind"] == "thread")
        self.place = self.world["locations"][self.item["location_id"]]
        self.thread = world_threads.by_id(self.world, self.item["thread_id"])
        self.key = next(key for key, item in town_knowledge.speech_keys(self.world, self.npc).items()
                        if item["thread_id"] == self.thread["thread_id"])

    def heard_trail(self):
        return [row for row in quest_log.trails(self.world) if row["source"] == "duyulan"]

    def test_the_keys_are_the_numbers_the_prompt_shows(self):
        keys = town_knowledge.speech_keys(self.world, self.npc)
        known = town_knowledge.public_knowledge(self.world, self.npc)
        self.assertEqual(list(keys), [f"k{n}" for n in range(1, len(known) + 1)])
        note = town_knowledge.speech_note(self.world, self.npc)
        for key, item in keys.items():
            self.assertIn(f"{key}: {item['text']}", note)

    def test_place_name_alone_marks_nothing(self):
        town_knowledge.note_mention(self.world, self.npc, f"{self.place['name']} tarafında gerginlik var.")
        self.assertNotEqual(self.thread["status"], "heard")
        self.assertEqual(self.heard_trail(), [])

    def test_owner_name_alone_marks_nothing(self):
        town_knowledge.note_mention(self.world, self.npc, f"{self.thread['owner_name']} ile konuş, o bilir.")
        self.assertNotEqual(self.thread["status"], "heard")

    def test_voiced_and_words_mark_heard(self):
        town_knowledge.note_mention(self.world, self.npc, self.item["text"], voiced=[self.key])
        self.assertEqual(self.thread["status"], "heard")
        self.assertEqual([row["what"] for row in self.heard_trail()], [self.thread["public_line"]])

    def test_voiced_id_without_words_marks_nothing(self):
        town_knowledge.note_mention(self.world, self.npc, "Bugün hava ağır, yolcu.", voiced=[self.key])
        self.assertNotEqual(self.thread["status"], "heard")
        self.assertEqual(self.heard_trail(), [])

    def test_words_without_the_voiced_id_mark_nothing(self):
        town_knowledge.note_mention(self.world, self.npc, self.item["text"], voiced=["none"])
        self.assertNotEqual(self.thread["status"], "heard")
        town_knowledge.note_mention(self.world, self.npc, self.item["text"], voiced=["k99"])
        self.assertNotEqual(self.thread["status"], "heard")

    def test_words_alone_mark_heard_when_the_model_gave_no_keys(self):
        town_knowledge.note_mention(self.world, self.npc, self.item["text"])
        self.assertEqual(self.thread["status"], "heard")

    def test_a_voiced_key_of_another_item_does_not_mark_this_one(self):
        other = next((k for k in town_knowledge.speech_keys(self.world, self.npc) if k != self.key), None)
        if other is None:
            self.skipTest("one listed item")
        town_knowledge.note_mention(self.world, self.npc, self.item["text"], voiced=[other])
        self.assertNotEqual(self.thread["status"], "heard")

    def test_a_place_said_outright_is_still_what_oraya_means(self):
        # The place binding is not the heard mark: it stays.
        import npc_statements
        line = f"Bence {self.place['name']}ne bir uğra."
        npc_statements.record(self.world, self.npc, "İş var mı?", line, turn=None)
        town_knowledge.note_mention(self.world, self.npc, line)
        self.assertEqual(npc_statements.last_said_place(self.world)["location_id"], self.place["id"])


class HeardRumourTrail(unittest.TestCase):
    def test_heard_rumour_trail_shows_claim_and_speaker(self):
        world = seeded("rumour-trail")
        npc = person("npc_77", "Rahip")
        npc["name"] = npc["public_name"] = "Rahip Aldor"
        world["npcs"].append(npc)
        record = local_places.create_local_place(world, "city", "temple", name="Kespur Tapınağı", rumoured=True)
        self.assertIsNotNone(record)
        world["heard_rumours"] = [{"id": "rumour_001", "text": "Kespur Tapınağı: kilitte taze çizikler",
                                   "said_by": npc["id"], "speakers": [npc["id"]], "place_id": record["id"],
                                   "settlement_id": "city", "turn": 3}]
        rows = [row for row in quest_log.trails(world) if row["source"] == "duyulan"]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("kilitte taze çizikler", rows[0]["what"])
        self.assertEqual(rows[0]["who"], "Rahip Aldor")
        self.assertEqual(rows[0]["where"], "Kespur Tapınağı")
        self.assertFalse(rows[0]["followed"])

    def test_a_rumour_without_a_place_is_no_trail(self):
        world = seeded("rumour-none")
        world["heard_rumours"] = [{"id": "rumour_001", "text": "Bir şeyler dönüyor", "said_by": "npc_1",
                                   "speakers": ["npc_1"], "place_id": None, "settlement_id": "city", "turn": 1}]
        self.assertEqual([r for r in quest_log.trails(world) if r["source"] == "duyulan"], [])


class NoGenericLine(unittest.TestCase):
    def test_no_generic_heard_line_in_journal(self):
        before = {"world_state": {"location": "tavern", "locations": {"tavern": {"id": "tavern", "name": "Taverna",
                                                                                   "type": "building"}},
                                  "npcs": [{"id": "n1", "name": "Mara"}], "flags": {"turn_index": 1},
                                  "combat": {"active": False}, "inventory": []}, "player": {"current_hp": 10}}
        after = copy.deepcopy(before)
        after["world_state"]["flags"]["turn_index"] = 2
        state = interaction_adventure.get(after["world_state"])
        npc = after["world_state"]["npcs"][0]
        interaction_adventure._remember_claim(after["world_state"], state, "Dün sana borç verdim.", npc, "addressed")
        after["world_state"][interaction_adventure.KEY] = state
        self.assertTrue(any(e["kind"] == "statement_heard" for e in state["events"]))  # the event itself stays
        journal = update_campaign_journal(empty_campaign_journal(), before, after,
                                          {"action": "dialogue", "status": "resolved"}, {"environment": "tavern"})
        self.assertNotIn(GENERIC, [event["summary"] for event in journal["notable_events"]])

    def test_other_adventure_events_still_reach_the_journal(self):
        before = {"world_state": {"location": "tavern", "locations": {"tavern": {"id": "tavern", "name": "Taverna",
                                                                                   "type": "building"}},
                                  "npcs": [], "flags": {"turn_index": 1}, "combat": {"active": False},
                                  "inventory": []}, "player": {"current_hp": 10}}
        after = copy.deepcopy(before)
        state = interaction_adventure.get(after["world_state"])
        interaction_adventure._event(after["world_state"], state, "town_job", "Bir iş duyuldu.")
        after["world_state"][interaction_adventure.KEY] = state
        journal = update_campaign_journal(empty_campaign_journal(), before, after,
                                          {"action": "dialogue", "status": "resolved"}, {"environment": "tavern"})
        self.assertIn("Bir iş duyuldu.", [event["summary"] for event in journal["notable_events"]])


class VoicedClient(fp.FrontClient):
    """A speech answer that also fills `voiced` the way a model following the schema would."""
    voiced = ["none"]

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        answer = super().chat(*args, **kwargs)
        if "voiced" in (schema.get("properties") or {}):
            packet = json.loads(answer["message"]["content"])
            packet["voiced"] = list(self.voiced)
            answer = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return answer


class SchemaAndUndo(unittest.IsolatedAsyncioTestCase):
    """Real app: the speech schema lists the keys, one turn marks a thread heard, Undo takes it back."""

    asyncSetUp = scene_time.SceneTimeTable.asyncSetUp
    asyncTearDown = scene_time.SceneTimeTable.asyncTearDown
    campaign_with_npc = scene_time.SceneTimeTable.campaign_with_npc
    open_job = fp.FrontTable.open_job
    line = fp.FrontTable.line
    status = fp.FrontTable.status
    say = scene_time.SceneTimeTable.say

    async def begin(self, *, kind="hiring"):
        await fp.FrontTable.begin(self, kind=kind)
        self.client = VoicedClient()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "asks": "rumour", "about_person_id": "none"}
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def speech_schemas(self):
        return [s for s in self.client.schemas if "spoken_text" in (s.get("properties") or {})]

    def heard_trail(self, world):
        return [r["what"] for r in quest_log.trails(world) if r["source"] == "duyulan"]

    async def test_the_speech_schema_lists_the_keys_and_none(self):
        await self.begin()
        await self.say("Burada neler oluyor?")
        voiced = self.speech_schemas()[-1]["properties"]["voiced"]
        keys = list(town_knowledge.speech_keys(self.world, self.npc))
        self.assertEqual(voiced["type"], "array")
        self.assertEqual(voiced["items"]["enum"], [*keys, "none"])
        self.assertEqual(voiced["maxItems"], 3)
        self.assertIn("voiced", self.speech_schemas()[-1]["required"])

    async def test_undo_drops_heard_trail(self):
        await self.begin()
        self.thread["status"] = "open"
        key = next(k for k, item in town_knowledge.speech_keys(self.world, self.npc).items()
                   if item["thread_id"] == self.thread["thread_id"])
        self.client.voiced = [key]
        self.client.narration = self.thread["public_line"]
        self.assertEqual(self.heard_trail(self.world), [])
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": "Burada neler oluyor?", "action_id": action_id,
                                                              "interaction_mode": "say", "target_id": self.npc["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.status(), "heard")
        self.assertEqual(self.heard_trail(self.world), [self.thread["public_line"]])
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        world = self.session.world_state
        self.assertEqual(world_threads.by_id(world, self.thread["thread_id"])["status"], "open")
        self.assertEqual(self.heard_trail(world), [])


if __name__ == "__main__":
    unittest.main()
