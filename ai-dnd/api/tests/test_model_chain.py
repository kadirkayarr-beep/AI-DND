"""The cloud model chain, on fake HTTP only: translation, failure, spending, secrets."""

from __future__ import annotations

import json
import unittest

import httpx

from api import model_chain

KEY = "test-key-not-real-7f3a"
SCHEMA = {
    "type": "object",
    "properties": {
        "narration": {"type": "string", "maxLength": 300},
        "npc": {
            "type": ["object", "null"],
            "properties": {"name": {"type": ["string", "null"]}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "tier": {"type": "integer", "minimum": 1, "maximum": 5},
        "claims": {"type": "array", "maxItems": 0, "items": {"type": "string", "minLength": 1}},
    },
    "required": ["narration"],
    "additionalProperties": False,
}
CALL = {
    "model": "gemma4:e4b",
    "messages": [{"role": "system", "content": "Kurallar."}, {"role": "user", "content": "Etrafa bakıyorum."}],
    "format": SCHEMA,
    "think": False,
    "options": {"num_ctx": 8192, "temperature": 0.35, "num_predict": 700, "repeat_penalty": 1.15},
}


def gemini_reply(text='{"narration": "Sokak sessiz."}', finish="STOP", parts=None):
    return {
        "candidates": [{"content": {"parts": parts or [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7},
    }


def haiku_reply(text='{"narration": "Sokak sessiz."}', stop="end_turn", content=None):
    return {
        "content": [{"type": "text", "text": text}] if content is None else content,
        "stop_reason": stop,
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }


class TheTranslation(unittest.TestCase):
    def test_a_gemini_request_carries_the_prompt_the_schema_and_no_thinking(self):
        body = model_chain.gemini_body(CALL)
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "Kurallar."}]})
        self.assertEqual(body["contents"], [{"role": "user", "parts": [{"text": "Etrafa bakıyorum."}]}])
        config = body["generationConfig"]
        self.assertEqual(config["temperature"], 0.35)
        self.assertEqual(config["maxOutputTokens"], 700)
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "minimal"})

    def test_a_gemini_schema_has_no_additional_properties_and_no_type_lists(self):
        schema = model_chain.gemini_body(CALL)["generationConfig"]["responseSchema"]
        self.assertNotIn("additionalProperties", json.dumps(schema))
        self.assertEqual(schema["properties"]["npc"]["type"], "object")
        self.assertTrue(schema["properties"]["npc"]["nullable"])
        self.assertEqual(schema["properties"]["npc"]["properties"]["name"], {"type": "string", "nullable": True})
        self.assertEqual(schema["properties"]["claims"]["maxItems"], 0)
        self.assertEqual(SCHEMA["additionalProperties"], False)

    def test_a_haiku_request_turns_thinking_off_at_low_effort(self):
        body = model_chain.haiku_body(CALL)
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["output_config"]["effort"], "low")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(body["system"], "Kurallar.")
        self.assertEqual(body["messages"], [{"role": "user", "content": "Etrafa bakıyorum."}])
        self.assertEqual(body["max_tokens"], 700)

    def test_haiku_gets_no_temperature_because_it_refuses_non_default_values(self):
        self.assertNotIn("temperature", model_chain.haiku_body(CALL))

    def test_a_haiku_schema_closes_every_object_and_keeps_only_what_it_accepts(self):
        schema = model_chain.haiku_body(CALL)["output_config"]["format"]["schema"]
        self.assertIs(schema["additionalProperties"], False)
        self.assertIs(schema["properties"]["npc"]["additionalProperties"], False)
        text = json.dumps(schema)
        for word in ("maxLength", "minLength", "minimum", "maximum", "maxItems"):
            self.assertNotIn(word, text)

    def test_nothing_but_the_prompt_leaves_for_a_provider(self):
        call = dict(CALL, keep_alive="5m", session_id="private", options={"num_predict": 10, "gm_only": "secret"})
        for body in (model_chain.gemini_body(call), model_chain.haiku_body(call)):
            text = json.dumps(body)
            for word in ("private", "secret", "gm_only", "keep_alive", "num_ctx", "gemma4"):
                self.assertNotIn(word, text)

    def test_a_call_without_a_system_message_sends_none(self):
        call = dict(CALL, messages=[{"role": "user", "content": "Selam"}], format=None, options={})
        self.assertNotIn("systemInstruction", model_chain.gemini_body(call))
        self.assertNotIn("responseSchema", model_chain.gemini_body(call)["generationConfig"])
        self.assertNotIn("system", model_chain.haiku_body(call))
        self.assertEqual(model_chain.haiku_body(call)["output_config"], {"effort": "low"})

    def test_gemini_thought_parts_never_reach_the_game(self):
        reply = model_chain.gemini_read(gemini_reply(parts=[{"text": "düşünce", "thought": True}, {"text": "{}"}]))
        self.assertEqual(reply.text, "{}")

    def test_a_cut_reply_reads_as_ollama_length(self):
        self.assertEqual(model_chain.gemini_read(gemini_reply(finish="MAX_TOKENS")).done_reason, "length")
        self.assertEqual(model_chain.haiku_read(haiku_reply(stop="max_tokens")).done_reason, "length")
        self.assertEqual(model_chain.haiku_read(haiku_reply()).done_reason, "stop")

    def test_a_haiku_refusal_reads_as_empty(self):
        self.assertEqual(model_chain.haiku_read(haiku_reply(stop="refusal")).text, "")

    def test_a_gemini_reply_with_no_candidate_reads_as_empty(self):
        self.assertEqual(model_chain.gemini_read({"promptFeedback": {"blockReason": "SAFETY"}}).text, "")


if __name__ == "__main__":
    unittest.main()
