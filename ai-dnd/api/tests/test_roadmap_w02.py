"""W02: the profile test double answers from the CURRENT packet, never from stale global state.

Before W02 `CapturingConversationContextClient` chose the profile fact for a speech packet from `last_profile_field`, left by
whichever earlier request set it, so after an occupation question an origin question was answered with the occupation line.
The contract below drives the double directly with request-local speech packets; it produces no real-model quality claim
(the double declares itself a scripted test double) and keeps topic relevance separate from call-count assertions.
"""
from __future__ import annotations

import json
import unittest

from api.tests.test_campaign_api import CapturingConversationContextClient

PROFILE = {
    "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
    "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
    "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
    "reason_for_being_here": "Kayıp yük kayıtlarını bulmaya geldim.",
}
SPEECH_SCHEMA = {"type": "object", "properties": {"spoken_text": {"type": "string"}, "stage_direction": {"type": "string"}}}
MARKER = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"


def speech_packet(message, focus=None):
    context = {
        "npc_id": "npc_marek", "addressee": {"name": "Marek", "role": "resident"},
        "shareable_profile_facts": [
            {"field": field, "value": value, "evidence_id": f"npc-profile:npc_marek:v1:{field}"}
            for field, value in PROFILE.items()],
        "conversation_focus": focus,
    }
    user = f"{MARKER}{json.dumps(context, ensure_ascii=False)}\nCurrent player message: {message}"
    return {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": user}], "format": SPEECH_SCHEMA}


def answer(client, message, focus=None):
    reply = client.chat(**speech_packet(message, focus))
    return json.loads(reply["message"]["content"])["spoken_text"]


class ProfileDoubleContractTests(unittest.TestCase):
    CASES = (("mesleğin nedir?", "occupation"), ("nereli olduğunu anlatır mısın?", "origin"),
             ("şu an ne yapıyorsun?", "current_activity"), ("neden buraya geldin?", "reason_for_being_here"))

    def test_profile_double_obeys_current_packet(self):
        client = CapturingConversationContextClient()
        client.last_profile_field = "occupation"  # stale state left by an earlier request
        obs = {"response_topic": None, "current_packet_topic": "origin"}
        spoken = answer(client, "Marek, nereli olduğunu anlatır mısın?")
        obs["response_topic"] = next((field for field, value in PROFILE.items() if value in spoken), None)
        obs["stale_last_profile_field_used"] = PROFILE["occupation"] in spoken
        # the same questions in a different order: every answer still follows its own packet
        reordered = [(field, answer(client, f"Marek, {question}")) for question, field in reversed(self.CASES)]
        obs["reordered_questions_keep_topics"] = all(PROFILE[field] in spoken_line for field, spoken_line in reordered)
        obs["fake_result_labeled_real_model"] = client.model_provenance != "scripted_test_double"
        self.assertEqual(obs["response_topic"], obs["current_packet_topic"])
        self.assertIs(obs["stale_last_profile_field_used"], False)
        self.assertIs(obs["reordered_questions_keep_topics"], True)
        self.assertIs(obs["fake_result_labeled_real_model"], False)

    def test_a_question_with_no_matching_topic_gets_no_stale_profile_line(self):
        client = CapturingConversationContextClient()
        client.last_profile_field = "origin"
        spoken = answer(client, "Marek, hava nasıl?")
        self.assertFalse(any(value in spoken for value in PROFILE.values()), "no stale profile fact for an unrelated topic")

    def test_topic_relevance_is_asserted_apart_from_call_counts(self):
        client = CapturingConversationContextClient()
        before = client.chat_calls
        answer(client, "Marek, mesleğin nedir?")
        self.assertEqual(client.chat_calls, before + 1, "call count is its own assertion")
        self.assertIn(PROFILE["occupation"], answer(client, "Marek, mesleğin nedir?"), "topic relevance is its own assertion")


if __name__ == "__main__":
    unittest.main()
