"""The flag-on talk reading writes the focus Python can verify (G2.2, D-413, D-414).

A line read as talk to a person is answered by that person's speech, so no old word owner wrote the conversation
focus. These tests run with the front reading on and off: on, the reading says speak_to and Python writes the focus
(the profile fact the answer repeats, the locked inn it knows); off, the classifier's envelope and the owner's own line
write it, as before."""

from __future__ import annotations

import json
import unittest
import uuid

import front_proposal
import local_dialogue
from api.tests import test_campaign_api as fixtures


class PersonReadingClient(fixtures.CapturingConversationContextClient):
    """Flag on, the front reading takes every line as words said to ``person_id``, as local play's model reads a talk."""

    def __init__(self, person_id):
        super().__init__()
        self.person_id = person_id

    def chat(self, *args, **kwargs):
        if "front" not in (kwargs.get("format") or {}).get("properties", {}):
            return super().chat(*args, **kwargs)
        self.chat_calls += 1
        self.kinds.append("front")
        front = {"kind": "speak_to", "person_id": self.person_id, "place_id": "none", "offer_id": "none",
                 "thing_id": "none", "answer": "none", "inside": False, "timing": "now"}
        return {"message": {"content": json.dumps({
            "intent": "dialogue", "action": "dialogue", "target": {"type": "none", "reference": ""},
            "completion": "unclear", "confidence": 0.9, "front": front})}}


class FreeTalkFocusTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    post_scene_turn = fixtures.CampaignApiTests.post_scene_turn

    async def test_free_person_line_answers_purpose(self):
        # D-413: a free line (no chosen person, no mode) that names Marek and asks why he is here must be answered from
        # his verified reason_for_being_here and write that focus, flag on (the front reading says speak_to) and off
        # (the classifier's conversation envelope says personal_purpose).
        reading = front_proposal.enabled()
        city_id, _, session, turn_url, _, _ = await fixtures.create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_free_line",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)

        client = PersonReadingClient(marek["id"])
        envelope = {"conversation": {
            "addressee_id": marek["id"], "subject_phrase": "Marek", "subject_role": "addressee",
            "meaning": "personal_purpose", "topic_relation": "new",
            "candidate_evidence_ids": [f"npc-profile:{marek['id']}:v1:reason_for_being_here"]}}
        client.conversation_replies = [{"narration": purpose}] if reading else [{**envelope, "narration": purpose}]

        response = await self.post_scene_turn(
            turn_url, client,
            {"message": "Marek, seni bu şehre getiren şeyi anlat", "action_id": str(uuid.uuid4())})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(purpose, response.json()["narration"])
        focus = session.world_state["interaction_adventure_v1"]["conversation_focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["speaker_id"], marek["id"])
        self.assertEqual(focus["predicate"], "reason_for_being_here")
        if reading:
            self.assertEqual(client.kinds[:1], ["front"])

    async def test_inn_question_gives_locked_inn_answer(self):
        # D-414: "Buralarda han var mı Marek?" with the inn's door locked: the person's answer is the locked inn, and
        # Python writes the locked-door focus (owner_verified, `venue-door:<han>`), flag on (plain talk, answered by
        # speech) and off (the owner's own line), so "neden kilitli?" can follow.
        reading = front_proposal.enabled()
        city_id, _, session, turn_url, _, door = await fixtures.create_city_with_locked_tavern(self)
        marek = {"id": "npc_marek_inn", "name": "Marek", "role": "keeper", "location": city_id, "personality": "",
                 "appearance": "", "relationship": "neutral", "knowledge": [], "memory": [], "combat_status": "active",
                 "current_hp": 12, "status": "active"}
        session.world_state.setdefault("npcs", []).append(marek)
        client = PersonReadingClient(marek["id"])
        client.conversation_replies = [{"narration": "Han var ama kapısı kilitli; şimdilik kimseyi almıyorlar."}]

        response = await self.post_scene_turn(
            turn_url, client, {"message": "Buralarda han var mı Marek?", "action_id": str(uuid.uuid4())})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("kilitli", response.json()["narration"].casefold())
        focus = session.world_state.get("interaction_adventure_v1", {}).get("conversation_focus")
        self.assertIsInstance(focus, dict)
        self.assertEqual(focus["speaker_id"], marek["id"])
        self.assertEqual(focus["subject_id"], door["id"])
        self.assertEqual(focus["predicate"], "locked")
        self.assertEqual(focus["epistemic"], "owner_verified")
        if reading:
            self.assertEqual(client.kinds[:1], ["front"])
