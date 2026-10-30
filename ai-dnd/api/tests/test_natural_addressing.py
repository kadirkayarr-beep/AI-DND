"""A typed line with people around reaches the most plausible person.

The real UI sends no target by default. These turns run the real HTTP path on a
new Neverwinter campaign with two people in the scene, as a player would.
"""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import living_world
from api.tests import test_campaign_api

START = {"campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}}
WALL = ("birden fazla kişi", "Hangisini", "seçemedim", "Kiminle konuşmak")


class TownClient:
    """Answers every call the way a quiet local model would."""

    SPOKEN = "Pek bir şey bilmiyorum, kusura bakma."

    def __init__(self):
        self.calls = 0
        self.kinds = []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format", {}) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "spoken_text" in properties:
            self.kinds.append("speech")
            return {"message": {"content": json.dumps(
                {"spoken_text": self.SPOKEN, "stage_direction": ""}, ensure_ascii=False,
            )}}
        if "intent" not in properties:
            self.kinds.append("narration")
            return {"message": {"content": json.dumps({
                "narration": "Bir an durup çevrene kulak veriyorsun.",
                "world_updates": {}, "lore_claims": [],
            }, ensure_ascii=False)}}
        self.kinds.append("intent")
        return {"message": {"content": json.dumps({
            "intent": "narrative", "action": "narrative",
            "target": {"type": "none", "reference": ""},
            "completion": "intended", "confidence": 1.0,
            "interaction": {
                "operation": "none", "quote": "", "thread_id": None, "evidence_id": None,
                "requested_item": None, "steps": [], "candidates": [],
                "conversation": {
                    "addressee_id": "npc_unknown", "subject_phrase": "",
                    "subject_role": "unknown", "meaning": "other",
                    "topic_relation": "new", "candidate_evidence_ids": [],
                },
            },
        }, ensure_ascii=False)}}


class TownCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = TownClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        created = await self.http.post("/api/game/campaigns", json=START)
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]
        self.world["campaign_time"]["elapsed_seconds"] = 4 * 3600  # 13:00, an ordinary afternoon
        await self.say("Etrafa bakıyorum.")
        self.assertEqual(len(self.people), 2, self.people)

    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    @property
    def people(self):
        return [n for n in self.world["npcs"] if n.get("location") == self.world["location"]]

    @property
    def guard(self):
        return next(n for n in self.people if "uhaf" in str(n.get("role")))

    @property
    def other(self):
        return next(n for n in self.people if "uhaf" not in str(n.get("role")))

    async def say(self, text):
        response = await self.http.post(
            f"/api/game/sessions/{self.session_id}/turn",
            json={"message": text, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_no_wall(self, data):
        for word in WALL:
            self.assertNotIn(word, data["narration"])

    @property
    def flags(self):
        return self.world["flags"]


class AddressGoesToThePlausiblePerson(TownCase):
    async def test_approaching_someone_nearby_picks_a_person(self):
        data = await self.say("Yakınımdaki birine yaklaşıyorum.")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        self.assertEqual(self.other.get("distance_ft"), 5)

    async def test_approach_and_greeting_in_one_line(self):
        data = await self.say("Yakınımdaki birine yaklaşıyorum. Selamlar, ismin nedir?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        self.assertIn(self.other["name"], data["narration"])

    async def test_a_question_with_no_target_reaches_the_nearest_non_guard(self):
        data = await self.say("Burada ne iş yapıyorsun?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])

    async def test_a_question_keeps_the_current_conversation_partner(self):
        await self.say("Muhafıza selam veriyorum.")
        self.assertEqual(self.flags["active_npc_id"], self.guard["id"])
        data = await self.say("Buralarda koruma arayan bir soylu biliyor musun?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.guard["id"])

    async def test_a_question_after_the_talk_lapsed_goes_to_the_last_person_addressed(self):
        await self.say("Muhafıza selam veriyorum.")
        self.flags["active_npc_id"] = None
        self.flags["active_npc_until_turn"] = -1
        data = await self.say("Buralarda koruma arayan bir soylu biliyor musun?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["last_npc_id"], self.guard["id"])

    async def test_a_word_for_the_guard_goes_to_the_guard(self):
        data = await self.say("Nöbetçiye bu sokakta bir sorun olup olmadığını soruyorum.")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.guard["id"])

    async def test_two_people_sharing_a_label_are_no_wall(self):
        twin = copy.deepcopy(self.other)
        twin.update(id="npc_twin", name="Ilva", memory=[], personal_profile=None)
        self.world["npcs"].append(twin)
        data = await self.say("Yakındaki kişiye yolu soruyorum.")
        self.assert_no_wall(data)
        self.assertIn(self.flags["active_npc_id"], {self.other["id"], twin["id"]})

    async def test_only_guards_here_still_answer(self):
        self.other["location"] = "elsewhere"
        data = await self.say("Burada ne iş yapıyorsun?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.guard["id"])

    async def test_an_attack_with_two_people_is_not_aimed_for_the_player(self):
        await self.http.post(
            f"/api/game/sessions/{self.session_id}/turn",
            json={"message": "Saldırıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertFalse(self.world["combat"].get("active"))


class WorldQuestionsReachThePerson(TownCase):
    async def test_asking_about_an_inn_is_answered_by_a_person(self):
        data = await self.say("Bu çevrede bir han var mı?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        inn = next(r for r in self.world["locations"].values() if r.get("scene_kind") == "tavern")
        self.assertIn(inn["name"], data["narration"])
        self.assertIn("“", data["narration"])

    async def test_asking_the_street_for_work_reaches_a_person(self):
        data = await self.say("Burada nerede iş bulabilirim?")
        self.assert_no_wall(data)
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        self.assertIn("speech", self.client.kinds)

    async def test_why_was_the_door_locked_is_a_question_to_someone(self):
        before = copy.deepcopy(self.world["doors"])
        data = await self.say("Kapı niye kilitliydi?")
        self.assert_no_wall(data)
        self.assertNotIn("açıp kapatabileceğin", data["narration"])
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        self.assertEqual(self.world["doors"], before)

    async def test_nobody_here_means_the_player_searches_for_the_inn(self):
        for npc in self.people:
            npc["location"] = "elsewhere"
        data = await self.say("Bu çevrede bir han var mı?")
        self.assertIn("Hanı", data["narration"])


    async def test_a_question_without_a_mark_is_still_a_question(self):
        data = await self.say("Bu çevrede bir han var mı")
        self.assertEqual(self.flags["active_npc_id"], self.other["id"])
        self.assertIn("“", data["narration"])

    async def test_a_named_inn_is_kept_under_its_real_name(self):
        await self.say("Bu çevrede bir han var mı?")
        inn = next(r for r in self.world["locations"].values() if r.get("scene_kind") == "tavern")
        references = self.world["npc_statements"]["references"]
        self.assertEqual([r["location_id"] for r in references], [inn["id"]])
        self.assertEqual(references[0]["name"], inn["name"])


if __name__ == "__main__":
    unittest.main()
