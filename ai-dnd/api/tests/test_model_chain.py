"""The cloud model chain, on fake HTTP only: translation, failure, spending, secrets."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

import game
import interaction_adventure
from api import identity_suggestion, model_chain, ollama_adapter, usage_ledger
from api.auth import FixedAuthenticator
from api.local_model_config import SUPPORTED_LOCAL_MODELS
from api.main import create_app
from api.model_phase import classifier_call
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.tests.auth_fixture import TEST_PLAYER, TestPlayerSessionManager

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


PYDANTIC_SCHEMA = {
    "$defs": {
        "Step": {
            "title": "Step",
            "type": "object",
            "properties": {
                "kind": {"const": "move", "type": "string", "title": "Kind"},
                "note": {"anyOf": [{"type": "string", "maxLength": 40}, {"type": "null"}], "default": None, "title": "Note"},
            },
            "required": ["kind"],
            "additionalProperties": False,
        },
    },
    "title": "Envelope",
    "type": "object",
    "properties": {
        "steps": {"type": "array", "maxItems": 3, "minItems": 0, "items": {"$ref": "#/$defs/Step"}, "default": []},
        "first": {"anyOf": [{"$ref": "#/$defs/Step"}, {"type": "null"}], "default": None},
        "nobody": {"type": "null"},
    },
    "required": ["steps"],
    "additionalProperties": False,
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

    def test_a_gemini_schema_inlines_what_a_pydantic_schema_refers_to(self):
        schema = model_chain.gemini_body(dict(CALL, format=PYDANTIC_SCHEMA))["generationConfig"]["responseSchema"]
        text = json.dumps(schema)
        for word in ("$defs", "$ref", "anyOf", "const", "default", "title", "additionalProperties", '"null"'):
            self.assertNotIn(word, text)
        step = schema["properties"]["steps"]["items"]
        self.assertEqual(step["properties"]["kind"], {"type": "string", "enum": ["move"]})
        self.assertEqual(step["properties"]["note"], {"type": "string", "nullable": True, "maxLength": 40})
        self.assertEqual(schema["properties"]["first"]["type"], "object")
        self.assertTrue(schema["properties"]["first"]["nullable"])
        self.assertEqual(schema["properties"]["nobody"], {"type": "string", "nullable": True})

    def test_a_field_named_like_a_keyword_stays_a_field(self):
        schema = {"type": "object", "properties": {"title": {"type": "string", "title": "Title", "maxLength": 9}}}
        gemini = model_chain.gemini_body(dict(CALL, format=schema))["generationConfig"]["responseSchema"]
        self.assertEqual(gemini["properties"], {"title": {"type": "string", "maxLength": 9}})
        haiku = model_chain.haiku_body(dict(CALL, format=schema))["output_config"]["format"]["schema"]
        self.assertEqual(haiku["properties"], {"title": {"type": "string"}})

    def test_gemini_gets_no_empty_enum_value(self):
        call = dict(CALL, format={"type": "object", "properties": {
            "npc_id": {"type": "string", "enum": [""]},
            "kind": {"type": "string", "enum": ["", "move"]},
        }})
        properties = model_chain.gemini_body(call)["generationConfig"]["responseSchema"]["properties"]
        self.assertEqual(properties["npc_id"], {"type": "string"})
        self.assertEqual(properties["kind"], {"type": "string", "enum": ["move"]})

    def test_a_schema_too_complex_for_haiku_travels_in_the_prompt(self):
        body = model_chain.haiku_body(dict(CALL, format=PYDANTIC_SCHEMA))
        self.assertEqual(body["output_config"], {"effort": "low"})
        self.assertTrue(body["system"].startswith("Kurallar."))
        self.assertIn("JSON", body["system"].removeprefix("Kurallar."))
        self.assertIn('"$ref": "#/$defs/Step"', body["system"])
        for word in ('"default"', '"title"'):
            self.assertNotIn(word, body["system"])

    def test_the_limits_reach_haiku_when_no_compiler_reads_the_schema(self):
        system = model_chain.haiku_body(dict(CALL, format=PYDANTIC_SCHEMA))["system"]
        self.assertIn('"maxItems": 3', system)
        self.assertIn('"maxLength": 40', system)

    def test_a_simple_schema_stays_a_compiled_format_for_haiku(self):
        body = model_chain.haiku_body(CALL)
        self.assertEqual(body["system"], "Kurallar.")
        self.assertIn("format", body["output_config"])

    def test_translating_leaves_the_engine_schema_alone(self):
        before = json.dumps(PYDANTIC_SCHEMA, sort_keys=True)
        model_chain.gemini_body(dict(CALL, format=PYDANTIC_SCHEMA))
        model_chain.haiku_body(dict(CALL, format=PYDANTIC_SCHEMA))
        self.assertEqual(json.dumps(PYDANTIC_SCHEMA, sort_keys=True), before)

    def test_the_real_classifier_schema_keeps_no_keyword_a_provider_refuses(self):
        schema = interaction_adventure.close_proposal_schema(
            interaction_adventure.intent_schema(game.INTENT_SCHEMA, require_conversation=True), {"addressee": None})
        gemini = json.dumps(model_chain.gemini_body(dict(CALL, format=schema))["generationConfig"]["responseSchema"])
        for word in ("$ref", "$defs", "anyOf", "const", '"default"', '"title"'):
            self.assertNotIn(word, gemini)
        self.assertNotIn('""', gemini)
        haiku = model_chain.haiku_body(dict(CALL, format=schema))
        self.assertEqual(haiku["output_config"], {"effort": "low"})
        for word in ('"default"', '"title"'):
            self.assertNotIn(word, haiku["system"])
        self.assertIn('"maxItems": 0', haiku["system"])

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


class Clock:
    def __init__(self):
        self.moment = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.moment

    def advance(self, seconds):
        self.moment += timedelta(seconds=seconds)


GOOGLE = "generativelanguage.googleapis.com"
ANTHROPIC = "api.anthropic.com"


class FakeCloud:
    """Answers by host; a plan is a response, an exception to raise, or a callable giving either."""

    def __init__(self, gemini=None, haiku=None):
        self.plans = {GOOGLE: gemini, ANTHROPIC: haiku}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        plan = self.plans[request.url.host]
        answer = plan() if callable(plan) else plan
        if isinstance(answer, Exception):
            raise answer
        return answer

    def hosts(self):
        return [request.url.host for request in self.requests]


def ok(payload):
    return httpx.Response(200, json=payload)


class LocalModel:
    def __init__(self):
        self.calls = 0
        self.answer = {"message": {"role": "assistant", "content": '{"narration": "yerel"}'}}

    def __call__(self):
        self.calls += 1
        return self.answer


def setUpModule():
    global _TEMP
    _TEMP = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(_TEMP.cleanup)


def spend_file():
    return Path(tempfile.mkdtemp(dir=_TEMP.name)) / "play" / "model-chain-spend.json"


def chain_for(cloud, clock=None, path=None):
    clock = clock or Clock()
    spend = model_chain.HaikuSpend(path or spend_file(), clock)
    providers = [model_chain.gemini(KEY), model_chain.haiku(KEY, spend)]
    return model_chain.ModelChain(providers, transport=httpx.MockTransport(cloud), now=clock)


class TheChain(unittest.TestCase):
    def test_the_first_provider_answers_in_ollama_shape(self):
        local = LocalModel()
        response, answered = chain_for(FakeCloud(gemini=ok(gemini_reply()))).chat(CALL, local)
        self.assertEqual(answered, "gemini")
        self.assertEqual(response.message.content, '{"narration": "Sokak sessiz."}')
        self.assertEqual(response["message"]["content"], '{"narration": "Sokak sessiz."}')
        self.assertEqual(response.message.role, "assistant")
        self.assertEqual(response.done_reason, "stop")
        self.assertEqual((response.prompt_eval_count, response.eval_count), (11, 7))
        self.assertEqual(response.model, "gemini-3.5-flash-lite")
        self.assertEqual(local.calls, 0)

    def test_each_key_travels_only_in_its_header(self):
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
        chain_for(cloud).chat(CALL, LocalModel())
        google, anthropic = cloud.requests
        self.assertEqual(google.headers["x-goog-api-key"], KEY)
        self.assertEqual(anthropic.headers["x-api-key"], KEY)
        self.assertIn("anthropic-version", anthropic.headers)
        for request in cloud.requests:
            self.assertNotIn(KEY, str(request.url))
            self.assertNotIn(KEY, request.content.decode())

    def test_every_failure_moves_to_the_next_provider_in_the_same_call(self):
        failures = {
            "rate limit": httpx.Response(429),
            "server error": httpx.Response(503),
            "refused key": httpx.Response(401),
            "timeout": httpx.ReadTimeout("slow"),
            "no network": httpx.ConnectError("down"),
            "not json at all": httpx.Response(200, text="<html>"),
            "invalid json": ok(gemini_reply('{"narration": "yarım')),
            "json that is not an object": ok(gemini_reply("[1]")),
            "empty object": ok(gemini_reply("{}")),
            "empty reply": ok(gemini_reply("")),
            "no candidate": ok({"promptFeedback": {"blockReason": "SAFETY"}}),
        }
        for name, failure in failures.items():
            with self.subTest(name):
                local = LocalModel()
                cloud = FakeCloud(gemini=failure, haiku=ok(haiku_reply()))
                response, answered = chain_for(cloud).chat(CALL, local)
                self.assertEqual(answered, "haiku")
                self.assertEqual(response.message.content, '{"narration": "Sokak sessiz."}')
                self.assertEqual(cloud.hosts(), [GOOGLE, ANTHROPIC])
                self.assertEqual(local.calls, 0)

    def test_the_local_model_answers_when_every_cloud_provider_fails(self):
        local = LocalModel()
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=httpx.ReadTimeout("slow"))
        response, answered = chain_for(cloud).chat(CALL, local)
        self.assertIsNone(answered)
        self.assertIs(response, local.answer)
        self.assertEqual(local.calls, 1)

    def test_a_local_failure_is_the_callers_as_it_is_today(self):
        def broken():
            raise ConnectionError("ollama down")

        cloud = FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500))
        with self.assertRaises(ConnectionError):
            chain_for(cloud).chat(CALL, broken)

    def test_a_call_without_a_format_accepts_plain_text(self):
        call = dict(CALL, format=None)
        response, answered = chain_for(FakeCloud(gemini=ok(gemini_reply("Sokak sessiz.")))).chat(call, LocalModel())
        self.assertEqual((answered, response.message.content), ("gemini", "Sokak sessiz."))

    def test_a_call_waits_three_seconds_to_connect_and_twenty_for_the_rest(self):
        cloud = FakeCloud(gemini=ok(gemini_reply()))
        chain_for(cloud).chat(CALL, LocalModel())
        timeout = cloud.requests[0].extensions["timeout"]
        self.assertEqual((timeout["connect"], timeout["read"], timeout["write"]), (3, 20, 20))

    def test_the_next_provider_gets_only_what_is_left_of_the_walk(self):
        clock = Clock()

        def hang():
            clock.advance(20)
            return httpx.ReadTimeout("slow")

        cloud = FakeCloud(gemini=hang, haiku=ok(haiku_reply()))
        self.assertEqual(chain_for(cloud, clock).chat(CALL, LocalModel())[1], "haiku")
        timeout = cloud.requests[1].extensions["timeout"]
        self.assertEqual((timeout["connect"], timeout["read"]), (3, 5))

    def test_the_local_model_starts_when_the_walk_runs_out(self):
        clock = Clock()

        def hang():
            clock.advance(25)
            return httpx.ReadTimeout("slow")

        local = LocalModel()
        cloud = FakeCloud(gemini=hang, haiku=ok(haiku_reply()))
        self.assertIsNone(chain_for(cloud, clock).chat(CALL, local)[1])
        self.assertEqual(cloud.hosts(), [GOOGLE])
        self.assertEqual(local.calls, 1)

    def test_a_reply_that_trickles_in_stops_at_the_end_of_the_walk(self):
        clock = Clock()

        def drip():
            for chunk in (b'{"candidates":', b"[]", b"}"):
                clock.advance(13)
                yield chunk

        local = LocalModel()
        cloud = FakeCloud(gemini=lambda: httpx.Response(200, content=drip()), haiku=ok(haiku_reply()))
        self.assertIsNone(chain_for(cloud, clock).chat(CALL, local)[1])
        self.assertEqual(cloud.hosts(), [GOOGLE])
        self.assertEqual(local.calls, 1)

    def test_a_timeout_or_a_lost_connection_rests_the_provider_a_minute(self):
        for name, failure in (("timeout", httpx.ConnectTimeout("slow")), ("read", httpx.ReadTimeout("slow")),
                              ("no network", httpx.ConnectError("down"))):
            with self.subTest(name):
                clock = Clock()
                cloud = FakeCloud(gemini=failure, haiku=ok(haiku_reply()))
                chain = chain_for(cloud, clock)
                chain.chat(CALL, LocalModel())
                clock.advance(59)
                self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
                self.assertEqual(cloud.hosts(), [GOOGLE, ANTHROPIC, ANTHROPIC])
                clock.advance(2)
                cloud.plans[GOOGLE] = ok(gemini_reply())
                self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_dead_network_costs_the_turn_one_wait_not_one_per_call(self):
        clock = Clock()

        def hang():
            clock.advance(20)
            return httpx.ConnectTimeout("slow")

        cloud = FakeCloud(gemini=hang, haiku=ok(haiku_reply()))
        chain = chain_for(cloud, clock)
        for _ in range(3):
            chain.chat(CALL, LocalModel())
        self.assertEqual(cloud.hosts().count(GOOGLE), 1)

    def test_a_rate_limited_provider_rests_for_its_retry_after(self):
        clock = Clock()
        cloud = FakeCloud(gemini=httpx.Response(429, headers={"Retry-After": "30"}), haiku=ok(haiku_reply()))
        chain = chain_for(cloud, clock)
        chain.chat(CALL, LocalModel())
        clock.advance(29)
        cloud.plans[GOOGLE] = ok(gemini_reply())
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
        self.assertEqual(cloud.hosts(), [GOOGLE, ANTHROPIC, ANTHROPIC])
        clock.advance(2)
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_retry_after_date_is_respected(self):
        clock = Clock()
        when = (clock() + timedelta(seconds=120)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        cloud = FakeCloud(gemini=httpx.Response(429, headers={"Retry-After": when}), haiku=ok(haiku_reply()))
        chain = chain_for(cloud, clock)
        chain.chat(CALL, LocalModel())
        clock.advance(119)
        cloud.plans[GOOGLE] = ok(gemini_reply())
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
        clock.advance(2)
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_rate_limit_without_a_usable_header_rests_a_minute(self):
        for header in ({}, {"Retry-After": "soon"}):
            with self.subTest(header):
                clock = Clock()
                cloud = FakeCloud(gemini=httpx.Response(429, headers=header), haiku=ok(haiku_reply()))
                chain = chain_for(cloud, clock)
                chain.chat(CALL, LocalModel())
                clock.advance(59)
                cloud.plans[GOOGLE] = ok(gemini_reply())
                self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
                clock.advance(2)
                self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_daily_quota_error_rests_until_the_quota_resets(self):
        clock = Clock()  # noon UTC, so the 08:00 UTC reset is tomorrow
        quota = {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
        cloud = FakeCloud(gemini=httpx.Response(429, json=quota, headers={"Retry-After": "30"}), haiku=ok(haiku_reply()))
        chain = chain_for(cloud, clock)
        chain.chat(CALL, LocalModel())
        cloud.plans[GOOGLE] = ok(gemini_reply())
        clock.advance(19 * 3600)  # 07:00 UTC
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
        clock.advance(3601)
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_server_error_does_not_rest_the_provider(self):
        cloud = FakeCloud(gemini=httpx.Response(503), haiku=ok(haiku_reply()))
        chain = chain_for(cloud)
        chain.chat(CALL, LocalModel())
        cloud.plans[GOOGLE] = ok(gemini_reply())
        self.assertEqual(chain.chat(CALL, LocalModel())[1], "gemini")

    def test_a_key_reaches_no_log_and_no_error(self):
        def echo():
            return httpx.ReadTimeout(f"failed with {KEY}")

        for name, failure in (("echoing body", httpx.Response(500, text=f"bad key {KEY}")), ("echoing error", echo)):
            with self.subTest(name), self.assertLogs("ai_dnd.api.ollama", "INFO") as logs:
                chain = chain_for(FakeCloud(gemini=failure, haiku=httpx.Response(429, text=KEY)))
                chain.chat(CALL, LocalModel())
                self.assertNotIn(KEY, "\n".join(logs.output))
                self.assertNotIn(KEY, repr(chain))
                self.assertNotIn(KEY, repr(model_chain.gemini(KEY)))

    def test_the_log_names_who_answered_and_who_was_skipped(self):
        with self.assertLogs("ai_dnd.api.ollama", "INFO") as logs:
            chain_for(FakeCloud(gemini=httpx.Response(503), haiku=ok(haiku_reply()))).chat(CALL, LocalModel())
        text = "\n".join(logs.output)
        self.assertIn("provider=gemini", text)
        self.assertIn("reason=http_503", text)
        self.assertIn("provider=haiku", text)


class TheObserver(unittest.TestCase):
    def observed_chain(self, cloud, observer):
        clock = Clock()
        spend = model_chain.HaikuSpend(spend_file(), clock)
        providers = [model_chain.gemini(KEY), model_chain.haiku(KEY, spend)]
        return model_chain.ModelChain(
            providers, transport=httpx.MockTransport(cloud), now=clock, observer=observer,
        )

    def test_observer_sees_skip_then_answer(self):
        seen = []
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
        self.observed_chain(cloud, seen.append).chat(CALL, LocalModel())
        skipped, answered = seen
        self.assertEqual((skipped.provider, skipped.outcome, skipped.reason), ("gemini", "skipped", "http_500"))
        self.assertEqual((skipped.input_tokens, skipped.output_tokens, skipped.thought_tokens), (0, 0, 0))
        self.assertEqual((answered.provider, answered.outcome, answered.reason), ("haiku", "answered", None))
        self.assertEqual((answered.input_tokens, answered.output_tokens, answered.thought_tokens), (1000, 200, 0))
        for attempt in seen:
            self.assertIsInstance(attempt, model_chain.ChainAttempt)
            self.assertGreaterEqual(attempt.seconds, 0.0)

    def test_observer_does_not_change_the_return_value(self):
        def run(observer):
            cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
            response, provider = self.observed_chain(cloud, observer).chat(CALL, LocalModel())
            return response.message.content, provider

        self.assertEqual(run(None), run(lambda attempt: None))
        self.assertEqual(run(None), ('{"narration": "Sokak sessiz."}', "haiku"))

    def test_observer_exception_never_reaches_the_caller(self):
        def broken(attempt):
            raise RuntimeError("observer bug")

        cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
        with self.assertLogs("ai_dnd.api.ollama", "WARNING") as logs:
            response, provider = self.observed_chain(cloud, broken).chat(CALL, LocalModel())
        self.assertEqual(provider, "haiku")
        self.assertEqual(response.message.content, '{"narration": "Sokak sessiz."}')
        self.assertTrue(any("observer" in line for line in logs.output))


class TheReplyShape(unittest.TestCase):
    """A cloud reply leaves shaped as Gemma's grammar would have shaped it, or the next provider is asked."""

    def answer(self, reply, call=CALL):
        return chain_for(FakeCloud(gemini=ok(gemini_reply(reply)), haiku=ok(haiku_reply()))).chat(call, LocalModel())

    def test_a_reply_that_fits_stays_as_it_came(self):
        text = '{ "narration":  "Sokak", "npc": null, "tier": 3, "claims": [] }'
        response, answered = self.answer(text)
        self.assertEqual((answered, response.message.content), ("gemini", text))

    def test_what_the_limits_forbid_is_cut_and_the_provider_keeps_the_turn(self):
        response, answered = self.answer(json.dumps({"narration": "a" * 301, "claims": ["uydurma"]}))
        self.assertEqual(answered, "gemini")
        self.assertEqual(json.loads(response.message.content), {"narration": "a" * 300, "claims": []})

    def test_a_field_the_schema_closes_is_dropped(self):
        response, answered = self.answer('{"narration": "Sokak", "extra": 1}')
        self.assertEqual((answered, json.loads(response.message.content)), ("gemini", {"narration": "Sokak"}))

    def test_a_fenced_reply_is_unwrapped_rather_than_paid_for_twice(self):
        response, answered = self.answer('```json\n{"narration": "Sokak"}\n```')
        self.assertEqual((answered, response.message.content), ("gemini", '{"narration": "Sokak"}'))

    def test_a_reply_that_cannot_be_shaped_moves_to_the_next_provider(self):
        for name, reply in (
            ("missing required field", '{"tier": 3}'),
            ("wrong type", '{"narration": 5}'),
            ("out of range", '{"narration": "Sokak", "tier": 9}'),
            ("a true is not a number", '{"narration": "Sokak", "tier": true}'),
            ("nested wrong type", '{"narration": "Sokak", "npc": {"name": 5}}'),
        ):
            with self.subTest(name):
                self.assertEqual(self.answer(reply)[1], "haiku")

    def test_a_narration_only_reply_loses_the_world_changes_it_may_not_make(self):
        call = dict(CALL, format=game._dm_response_schema_for_turn(narration_only=True))
        updates = {name: [] for name in game.WORLD_UPDATE_SCHEMA["required"]}
        updates["events"] = [{"anything": "invented"}]
        response, answered = self.answer(
            json.dumps({"narration": "Sokak", "world_updates": updates, "lore_claims": ["invented"]}), call)
        self.assertEqual(answered, "gemini")
        reply = json.loads(response.message.content)
        self.assertEqual(reply["world_updates"]["events"], [])
        self.assertEqual(reply["lore_claims"], [])

    def test_a_turn_without_candidates_keeps_its_conversation_reading(self):
        schema = interaction_adventure.close_proposal_schema(
            interaction_adventure.intent_schema(game.INTENT_SCHEMA, require_conversation=True), {"addressee": None})
        proposal = dict(schema["$defs"]["ConversationProposal"], **{"$defs": schema["$defs"]})
        reply = {"addressee_id": "marek", "subject_phrase": "", "subject_role": "unknown", "meaning": "unclear",
                 "topic_relation": "unclear", "candidate_evidence_ids": [""]}
        response, answered = self.answer(json.dumps(reply), dict(CALL, format=proposal))
        self.assertEqual(answered, "gemini")
        shaped = json.loads(response.message.content)
        self.assertIsNone(shaped["addressee_id"])
        self.assertEqual(shaped["candidate_evidence_ids"], [])

    def test_an_id_that_is_not_on_offer_becomes_null_where_null_is_allowed(self):
        schema = {"type": "object", "properties": {
            "addressee_id": {"anyOf": [{"type": "string", "enum": ["marek"]}, {"type": "null"}]},
            "thread": {"anyOf": [{"$ref": "#/$defs/Id"}, {"type": "null"}]},
        }, "$defs": {"Id": {"type": "string", "maxLength": 4}}}
        response, _ = self.answer('{"addressee_id": "kimse", "thread": 7}', dict(CALL, format=schema))
        self.assertEqual(json.loads(response.message.content), {"addressee_id": None, "thread": None})


class TheSpendCap(unittest.TestCase):
    def haiku_only(self, path, clock=None, reply=None):
        self.cloud = FakeCloud(gemini=httpx.Response(503), haiku=reply or ok(haiku_reply()))
        return chain_for(self.cloud, clock, path)

    def spent(self, path, month="2026-10", input_tokens=0, output_tokens=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"month": month, "input_tokens": input_tokens, "output_tokens": output_tokens}))

    def test_haiku_tokens_are_counted_in_a_file_without_the_key(self):
        path = spend_file()
        chain = self.haiku_only(path)
        chain.chat(CALL, LocalModel())
        chain.chat(CALL, LocalModel())
        saved = json.loads(path.read_text())
        self.assertEqual(saved, {"month": "2026-10", "input_tokens": 2000, "output_tokens": 400})
        self.assertNotIn(KEY, path.read_text())

    def test_gemini_is_not_counted(self):
        path = spend_file()
        chain_for(FakeCloud(gemini=ok(gemini_reply())), path=path).chat(CALL, LocalModel())
        self.assertFalse(path.exists())

    def test_a_reply_the_game_cannot_use_is_still_paid_for(self):
        path = spend_file()
        self.haiku_only(path, reply=ok(haiku_reply("yarım"))).chat(CALL, LocalModel())
        self.assertEqual(json.loads(path.read_text())["input_tokens"], 1000)

    def test_below_four_dollars_haiku_answers(self):
        path = spend_file()
        self.spent(path, input_tokens=39_000_000, output_tokens=199_999)
        self.assertEqual(self.haiku_only(path).chat(CALL, LocalModel())[1], "haiku")

    def test_past_four_dollars_haiku_still_answers_because_the_cap_was_lifted(self):
        path = spend_file()
        self.spent(path, input_tokens=39_000_000, output_tokens=200_000)
        self.assertEqual(self.haiku_only(path).chat(CALL, LocalModel())[1], "haiku")
        self.assertEqual(json.loads(path.read_text())["input_tokens"], 39_001_000)

    def test_a_new_month_starts_at_zero(self):
        path = spend_file()
        self.spent(path, month="2026-09", input_tokens=80_000_000)
        self.assertEqual(self.haiku_only(path).chat(CALL, LocalModel())[1], "haiku")
        self.assertEqual(json.loads(path.read_text()), {"month": "2026-10", "input_tokens": 1000, "output_tokens": 200})

    def test_a_spend_file_that_cannot_be_read_stops_haiku(self):
        for content in ("not json", "[]", '{"month": "2026-10", "input_tokens": "many", "output_tokens": 0}'):
            with self.subTest(content):
                path = spend_file()
                path.parent.mkdir(parents=True)
                path.write_text(content)
                self.assertIsNone(self.haiku_only(path).chat(CALL, LocalModel())[1])
                self.assertEqual(self.cloud.hosts(), [GOOGLE])
                self.assertEqual(path.read_text(), content)

    def test_a_count_that_cannot_be_saved_stops_haiku_for_this_run(self):
        path = spend_file()
        chain = self.haiku_only(path)
        with patch.object(model_chain.os, "replace", side_effect=OSError("disk")):
            self.assertEqual(chain.chat(CALL, LocalModel())[1], "haiku")
        self.assertIsNone(chain.chat(CALL, LocalModel())[1])
        self.assertEqual(self.cloud.hosts(), [GOOGLE, ANTHROPIC, GOOGLE])


class TheSetting(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(dir=_TEMP.name))
        self.database = self.home / "play" / "game.sqlite3"
        self.saved = patch.dict(os.environ, {
            "USERPROFILE": str(self.home), "LOCALAPPDATA": str(self.home / "appdata"), "AI_DND_CAMPAIGN_DB": str(self.database),
        })
        self.saved.start()
        self.addCleanup(self.saved.stop)
        for name in ("AI_DND_MODEL_CHAIN", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(name, None)

    def keys(self, gemini="gemini-file-key", haiku="haiku-file-key"):
        if gemini:
            (self.home / ".aidnd-gemini-key").write_text(gemini, encoding="utf-8-sig")
        if haiku:
            (self.home / ".aidnd-anthropic-key").write_text(f"{haiku}\n", encoding="utf-8")

    def test_no_setting_means_no_chain_and_no_key_is_read(self):
        self.keys()
        with patch.object(model_chain, "_read_key") as read, self.assertNoLogs("ai_dnd.api.ollama", "INFO"):
            self.assertIsNone(model_chain.from_environment())
        read.assert_not_called()

    def test_the_setting_gives_the_order_and_the_local_model_ends_it(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        self.assertEqual(model_chain.from_environment().provider_names(), ["gemini", "haiku"])
        os.environ["AI_DND_MODEL_CHAIN"] = "haiku, gemini"
        self.assertEqual(model_chain.from_environment().provider_names(), ["haiku", "gemini"])
        os.environ["AI_DND_MODEL_CHAIN"] = "gemma,gemini"
        self.assertIsNone(model_chain.from_environment())

    def test_a_missing_key_skips_that_provider_quietly(self):
        self.keys(gemini=None)
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        self.assertEqual(model_chain.from_environment().provider_names(), ["haiku"])

    def test_no_key_at_all_means_no_chain(self):
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        self.assertIsNone(model_chain.from_environment())

    def test_a_key_in_the_environment_turns_nothing_on(self):
        os.environ.update(AI_DND_MODEL_CHAIN="gemini,haiku", GEMINI_API_KEY="g-env", ANTHROPIC_API_KEY="a-env")
        self.assertIsNone(model_chain.from_environment())

    def test_deleting_a_key_file_turns_that_provider_off_whatever_the_environment_holds(self):
        self.keys(haiku=None)
        os.environ.update(AI_DND_MODEL_CHAIN="gemini,haiku", ANTHROPIC_API_KEY="a-env")
        self.assertEqual(model_chain.from_environment().provider_names(), ["gemini"])

    def test_an_unreadable_key_file_leaves_that_provider_off(self):
        self.keys(haiku=None)
        (self.home / ".aidnd-anthropic-key").write_bytes("haiku-file-key".encode("utf-16"))
        os.environ.update(AI_DND_MODEL_CHAIN="gemini,haiku", ANTHROPIC_API_KEY="a-env")
        self.assertEqual(model_chain.from_environment().provider_names(), ["gemini"])

    def test_an_unknown_name_is_left_out(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,gpt"
        self.assertEqual(model_chain.from_environment().provider_names(), ["gemini"])

    def test_every_save_folder_shares_one_spend_file_because_the_cap_is_per_key(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "haiku,gemma"
        paths = []
        for folder in ("one", "two"):
            os.environ["AI_DND_CAMPAIGN_DB"] = str(self.home / folder / "game.sqlite3")
            paths.append(model_chain.from_environment()._providers[0].spend._path)
        self.assertEqual(paths, [self.home / "appdata" / "AI-DND" / "model-chain-spend.json"] * 2)

    def test_a_haiku_with_heavy_spend_is_still_on_because_the_cap_was_lifted(self):
        self.keys()
        spend = self.home / "appdata" / "AI-DND" / "model-chain-spend.json"
        spend.parent.mkdir(parents=True)
        month = datetime.now().astimezone().strftime("%Y-%m")
        spend.write_text(json.dumps({"month": month, "input_tokens": 50_000_000, "output_tokens": 0}))
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        self.assertEqual(model_chain.from_environment().provider_names(), ["gemini", "haiku"])

    def test_from_environment_records_to_the_usage_path(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        expected = self.home / "appdata" / "AI-DND" / "model-usage.jsonl"
        self.assertEqual(model_chain._usage_path(), expected)
        chain = model_chain.from_environment()
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
        chain._http = httpx.Client(transport=httpx.MockTransport(cloud), trust_env=False)
        _, provider = chain.chat(CALL, LocalModel())
        self.assertEqual(provider, "haiku")
        text = expected.read_text(encoding="utf-8")
        rows = [json.loads(line) for line in text.splitlines()]
        self.assertEqual([(row["provider"], row["outcome"]) for row in rows],
                         [("gemini", "skipped"), ("haiku", "answered")])
        self.assertEqual((rows[1]["input"], rows[1]["output"]), (1000, 200))
        self.assertNotIn("file-key", text)

    def test_haiku_spend_still_counts_the_same_with_the_ledger_wired_in(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        folder = self.home / "appdata" / "AI-DND"
        spend = folder / "model-chain-spend.json"
        chain = model_chain.from_environment()
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply()))
        chain._http = httpx.Client(transport=httpx.MockTransport(cloud), trust_env=False)
        chain.chat(CALL, LocalModel())
        chain.chat(CALL, LocalModel())
        saved = json.loads(spend.read_text(encoding="utf-8"))
        self.assertEqual(saved, {"month": datetime.now().astimezone().strftime("%Y-%m"),
                                 "input_tokens": 2000, "output_tokens": 400})
        self.assertEqual(sorted(path.name for path in folder.iterdir() if path.suffix in {".json", ".jsonl"}),
                         ["model-chain-spend.json", "model-usage.jsonl"])
        usage = [json.loads(line) for line in (folder / "model-usage.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(row["input"] for row in usage if row["provider"] == "haiku"), 2000)

    def test_the_local_play_adapter_gets_a_ledger_on_the_same_path_and_a_plain_one_does_not(self):
        self.keys()
        os.environ.update(AI_DND_MODEL_CHAIN="gemini,haiku,gemma", OLLAMA_HOST="http://127.0.0.1:11434",
                          OLLAMA_PROXY_TOKEN="loopback")
        with_cloud = AuthenticatedOllamaAdapter.from_environment(use_cloud=True)
        self.assertEqual(with_cloud.usage_ledger._path, self.home / "appdata" / "AI-DND" / "model-usage.jsonl")
        self.assertIsNone(AuthenticatedOllamaAdapter.from_environment().usage_ledger)

    def test_the_status_line_names_providers_and_no_secret(self):
        self.keys()
        os.environ["AI_DND_MODEL_CHAIN"] = "gemini,haiku,gemma"
        with self.assertLogs("ai_dnd.api.ollama", "INFO") as logs:
            model_chain.from_environment()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("gemini,haiku,local", logs.output[0])
        self.assertNotIn("file-key", logs.output[0])


class TheCharacterNote(unittest.TestCase):
    def setUp(self):
        self.local = EngineStub()
        self.local.chat = lambda **call: {"message": {"role": "assistant", "content": "Yerel not."}}
        patcher = patch.object(identity_suggestion, "_local_client", return_value=self.local)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_note_comes_from_the_first_cloud_provider(self):
        cloud = FakeCloud(gemini=ok(gemini_reply("Sessiz bir arşivci.")))
        self.assertEqual(identity_suggestion.chain_provider(chain_for(cloud))("Alan: Kişilik."), "Sessiz bir arşivci.")
        sent = json.loads(cloud.requests[0].content)
        self.assertEqual(sent["generationConfig"]["maxOutputTokens"], 200)
        self.assertEqual(sent["contents"][0]["parts"][0]["text"], "Alan: Kişilik.")

    def test_the_local_model_keeps_its_own_short_note_limit(self):
        seen = []
        self.local.chat = lambda **call: seen.append(call) or {"message": {"role": "assistant", "content": "Yerel not."}}
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500))
        identity_suggestion.chain_provider(chain_for(cloud))("Alan: Kişilik.")
        self.assertEqual(seen[0]["options"]["num_predict"], 60)

    def test_a_note_cut_short_is_not_a_note(self):
        cloud = FakeCloud(gemini=ok(gemini_reply("Sessiz bir", finish="MAX_TOKENS")), haiku=ok(haiku_reply("Bütün bir not.")))
        self.assertEqual(identity_suggestion.chain_provider(chain_for(cloud))("Alan: Kişilik."), "Bütün bir not.")

    def test_the_local_model_writes_the_note_when_the_cloud_fails(self):
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500))
        self.assertEqual(identity_suggestion.chain_provider(chain_for(cloud))("Alan: Kişilik."), "Yerel not.")

    def test_the_app_routes_notes_through_the_chain_only_when_it_is_on(self):
        adapter = AuthenticatedOllamaAdapter(EngineStub(), model_name="gemma4:e4b")
        off = create_app(session_manager=TestPlayerSessionManager(), ollama_adapter=adapter,
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        self.assertIs(off.state.identity_suggestions._provider, identity_suggestion.local_ollama_provider)
        adapter = AuthenticatedOllamaAdapter(EngineStub(), model_name="gemma4:e4b", chain=chain_for(FakeCloud()))
        on = create_app(session_manager=TestPlayerSessionManager(), ollama_adapter=adapter,
                        authenticator=FixedAuthenticator(TEST_PLAYER))
        self.assertIsNot(on.state.identity_suggestions._provider, identity_suggestion.local_ollama_provider)


class EngineStub:
    def __init__(self):
        self.calls = []

    def list(self):
        return {"models": [{"model": "gemma4:e4b"}]}

    def chat(self, *args, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"role": "assistant", "content": '{"narration": "yerel"}'}, "done_reason": "stop"}


class TheAdapter(unittest.TestCase):
    def adapter(self, cloud):
        stub = EngineStub()
        adapter = AuthenticatedOllamaAdapter(stub, model_name="gemma4:e4b")
        adapter._chain = chain_for(cloud)
        return adapter, stub

    def engine_call(self, adapter):
        return adapter.chat(model=ollama_adapter.MODEL_NAME, messages=list(CALL["messages"]), format=SCHEMA,
                            think=False, options={"temperature": 0.3, "num_predict": 400})

    def test_with_no_setting_the_adapter_has_no_chain(self):
        os.environ.pop("AI_DND_MODEL_CHAIN", None)
        self.assertIsNone(AuthenticatedOllamaAdapter(EngineStub())._chain)

    def test_a_setting_left_in_a_window_turns_on_nothing_outside_local_play(self):
        home = Path(tempfile.mkdtemp(dir=_TEMP.name))
        (home / ".aidnd-gemini-key").write_text("gemini-file-key", encoding="utf-8")
        with patch.dict(os.environ, {
            "USERPROFILE": str(home), "AI_DND_MODEL_CHAIN": "gemini,gemma", "AI_DND_AUTH_MODE": "local",
            "OLLAMA_HOST": "http://127.0.0.1:11434", "OLLAMA_PROXY_TOKEN": "loopback",
        }):
            self.assertIsNone(AuthenticatedOllamaAdapter(EngineStub())._chain)
            self.assertIsNone(AuthenticatedOllamaAdapter.from_environment()._chain)
            self.assertEqual(AuthenticatedOllamaAdapter.from_environment(use_cloud=True).model_chain,
                             ["gemini-3.5-flash-lite", "gemma4:e4b"])

    def test_the_cloud_reply_reaches_the_engine_through_the_old_contract(self):
        adapter, stub = self.adapter(FakeCloud(gemini=ok(gemini_reply())))
        response = self.engine_call(adapter)
        self.assertEqual(game.ollama_response_content(response), '{"narration": "Sokak sessiz."}')
        self.assertFalse(game.ollama_reply_was_cut(response))
        self.assertEqual(stub.calls, [])

    def test_gemma_keeps_its_current_options_when_it_answers_last(self):
        adapter, stub = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)))
        response = self.engine_call(adapter)
        self.assertEqual(game.ollama_response_content(response), '{"narration": "yerel"}')
        plain_adapter = AuthenticatedOllamaAdapter(EngineStub(), model_name="gemma4:e4b")
        plain_adapter._chain = None
        self.engine_call(plain_adapter)
        self.assertEqual(stub.calls, plain_adapter._client.calls)
        self.assertEqual(stub.calls[0]["options"], {"num_ctx": 8192, "temperature": 0.3, "num_predict": 400})
        self.assertIs(stub.calls[0]["think"], False)

    def test_falling_through_costs_one_counted_call(self):
        adapter, _ = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)))
        with adapter.capture_model_calls() as calls, adapter.capture_model_failures() as failures:
            self.engine_call(adapter)
        self.assertEqual(calls, ["gemma4:e4b"])
        self.assertEqual(failures, [])

    def test_the_turn_records_which_provider_answered_each_call(self):
        cloud = FakeCloud(gemini=ok(gemini_reply()), haiku=ok(haiku_reply()))
        adapter, _ = self.adapter(cloud)
        with adapter.capture_model_calls() as calls:
            self.engine_call(adapter)
            cloud.plans[GOOGLE] = httpx.Response(500)
            self.engine_call(adapter)
        self.assertEqual(calls, ["gemini", "haiku"])

    def test_the_call_cap_still_holds_with_the_chain_on(self):
        adapter, _ = self.adapter(FakeCloud(gemini=ok(gemini_reply())))
        with adapter.capture_model_calls():
            self.engine_call(adapter)
            self.engine_call(adapter)
            with self.assertRaises(RuntimeError):
                self.engine_call(adapter)

    def test_the_world_metadata_rule_still_shapes_the_prompt_sent_to_the_cloud(self):
        cloud = FakeCloud(gemini=ok(gemini_reply()))
        adapter, _ = self.adapter(cloud)
        metadata = {"environment": "city", "time_of_day": "evening", "weather": "clear"}
        with ollama_adapter.canonical_world_metadata_context(lambda: metadata):
            self.engine_call(adapter)
        self.assertIn("time_of_day=evening", json.loads(cloud.requests[0].content)["systemInstruction"]["parts"][0]["text"])

    def test_a_local_failure_stays_the_adapters_sanitized_error(self):
        adapter, stub = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)))
        stub.chat = lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("down"))
        with adapter.capture_model_failures() as failures, self.assertRaisesRegex(RuntimeError, "Ollama request failed"):
            self.engine_call(adapter)
        self.assertEqual(failures, ["ConnectionError"])

    def test_a_classifier_that_reaches_a_failed_local_model_leaves_the_turn_alive(self):
        adapter, stub = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)))
        stub.chat = lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))
        with adapter.capture_model_failures() as failures, self.assertRaises(RuntimeError), classifier_call():
            self.engine_call(adapter)
        self.assertEqual(failures, [])

    def test_with_no_chain_a_classifier_failure_stays_as_it_was(self):
        stub = EngineStub()
        stub.chat = lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))
        adapter = AuthenticatedOllamaAdapter(stub, model_name="gemma4:e4b")
        with adapter.capture_model_failures() as failures, self.assertRaises(RuntimeError), classifier_call():
            self.engine_call(adapter)
        self.assertEqual(failures, ["ReadTimeout"])

    def test_a_stopped_ollama_blocks_nothing_while_a_cloud_provider_can_answer(self):
        adapter, stub = self.adapter(FakeCloud(gemini=ok(gemini_reply())))
        stub.list = lambda: (_ for _ in ()).throw(ConnectionError("ollama down"))
        adapter.ensure_required_model()
        self.assertEqual(game.ollama_response_content(self.engine_call(adapter)), '{"narration": "Sokak sessiz."}')

    def test_a_missing_local_model_blocks_nothing_while_a_cloud_provider_can_answer(self):
        adapter, stub = self.adapter(FakeCloud(gemini=ok(gemini_reply())))
        stub.list = lambda: {"models": []}
        adapter.ensure_required_model()

    def test_the_preflight_still_refuses_when_no_cloud_provider_can_answer(self):
        clock = Clock()
        cloud = FakeCloud(gemini=httpx.Response(429), haiku=httpx.Response(429))
        stub = EngineStub()
        stub.list = lambda: (_ for _ in ()).throw(ConnectionError("ollama down"))
        adapter = AuthenticatedOllamaAdapter(stub, model_name="gemma4:e4b", chain=chain_for(cloud, clock))
        adapter._chain.chat(CALL, LocalModel())
        with self.assertRaises(ollama_adapter.OllamaUnavailableError):
            adapter.ensure_required_model()

    def test_the_model_chain_lists_cloud_names_then_the_local_model(self):
        adapter, _ = self.adapter(FakeCloud())
        self.assertEqual(adapter.model_chain, ["gemini-3.5-flash-lite", "claude-haiku-5-5", "gemma4:e4b"])
        adapter._chain = None
        self.assertIsNone(adapter.model_chain)


class LocalEngine:
    """A local client that takes a moment and reports token counts, like Ollama does."""

    def chat(self, *args, **kwargs):
        time.sleep(0.03)
        return {"message": {"role": "assistant", "content": '{"narration": "yerel"}'},
                "done_reason": "stop", "prompt_eval_count": 11, "eval_count": 7}

    def list(self):
        return {"models": [{"model": "gemma4:e4b"}]}


class RaisingLedger:
    def record(self, *args, **kwargs):
        raise RuntimeError("ledger bug")

    def warning(self):
        raise RuntimeError("ledger bug")


class TheUsageLedgerWiring(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp(dir=_TEMP.name)) / "model-usage.jsonl"
        self.ledger = usage_ledger.UsageLedger(self.path)

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def adapter(self, cloud, client=None):
        clock = Clock()
        providers = [model_chain.gemini(KEY), model_chain.haiku(KEY, model_chain.HaikuSpend(spend_file(), clock))]
        chain = model_chain.ModelChain(providers, transport=httpx.MockTransport(cloud), now=clock,
                                       observer=model_chain.ledger_observer(self.ledger))
        adapter = AuthenticatedOllamaAdapter(client or LocalEngine(), model_name="gemma4:e4b", chain=chain)
        adapter.usage_ledger = self.ledger
        return adapter

    def engine_call(self, adapter):
        return adapter.chat(model=ollama_adapter.MODEL_NAME, messages=list(CALL["messages"]), format=SCHEMA,
                            think=False, options={"temperature": 0.3, "num_predict": 400})

    def test_cloud_attempts_are_recorded_with_seconds_and_tokens(self):
        adapter = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=ok(haiku_reply())))
        self.engine_call(adapter)
        skipped, answered = self.rows()
        self.assertEqual((skipped["provider"], skipped["outcome"]), ("gemini", "skipped"))
        self.assertEqual((skipped["input"], skipped["output"], skipped["thought"]), (0, 0, 0))
        self.assertEqual((answered["provider"], answered["outcome"]), ("haiku", "answered"))
        self.assertEqual((answered["input"], answered["output"]), (1000, 200))
        for row in (skipped, answered):
            self.assertIsInstance(row["seconds"], float)
            self.assertGreaterEqual(row["seconds"], 0.0)
        self.assertEqual(self.ledger.today()["haiku"]["calls"], 1)

    def test_a_cloud_answer_gets_no_second_line_from_the_adapter(self):
        self.engine_call(self.adapter(FakeCloud(gemini=ok(gemini_reply()))))
        self.assertEqual([row["provider"] for row in self.rows()], ["gemini"])

    def test_gemma_answer_is_timed_by_the_adapter(self):
        self.engine_call(self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500))))
        self.assertEqual([(row["provider"], row["outcome"]) for row in self.rows()],
                         [("gemini", "skipped"), ("haiku", "skipped"), ("gemma", "answered")])
        gemma = self.rows()[-1]
        self.assertGreater(gemma["seconds"], 0.0)
        self.assertEqual((gemma["input"], gemma["output"], gemma["thought"]), (11, 7, 0))

    def test_gemma_alone_without_a_chain_is_still_timed(self):
        adapter = AuthenticatedOllamaAdapter(LocalEngine(), model_name="gemma4:e4b")
        adapter.usage_ledger = self.ledger
        self.engine_call(adapter)
        (gemma,) = self.rows()
        self.assertEqual((gemma["provider"], gemma["outcome"], gemma["input"], gemma["output"]),
                         ("gemma", "answered", 11, 7))
        self.assertGreater(gemma["seconds"], 0.0)

    def test_a_failed_local_call_writes_nothing_and_stays_the_adapters_error(self):
        engine = LocalEngine()
        engine.chat = lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("down"))
        adapter = self.adapter(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)), engine)
        with self.assertRaisesRegex(RuntimeError, "Ollama request failed"):
            self.engine_call(adapter)
        self.assertEqual([row["provider"] for row in self.rows()], ["gemini", "haiku"])

    def test_ledger_failure_does_not_fail_the_turn(self):
        cloud = FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500))
        expected = game.ollama_response_content(self.engine_call(self.adapter(cloud)))
        broken = self.adapter(cloud)
        broken.usage_ledger = RaisingLedger()
        with self.assertLogs("ai_dnd.api.ollama", "WARNING") as logs:
            answer = game.ollama_response_content(self.engine_call(broken))
        self.assertEqual(answer, expected)
        self.assertTrue(any("ledger" in line.lower() for line in logs.output))
        # A ledger that cannot write at all (its folder is a file) also leaves the answer alone.
        blocked = self.adapter(cloud)
        blocked.usage_ledger = usage_ledger.UsageLedger(self.path / "nope" / "model-usage.jsonl")
        with self.assertLogs("ai_dnd.api.ollama", "WARNING"):
            self.assertEqual(game.ollama_response_content(self.engine_call(blocked)), expected)

    def test_spend_warning_reads_the_ledger_and_is_none_without_one(self):
        adapter = self.adapter(FakeCloud())
        self.assertIsNone(adapter.spend_warning())
        self.ledger.record("haiku", input_tokens=30_000_000, output_tokens=0)
        self.assertIn("3.00 USD", adapter.spend_warning())
        adapter.usage_ledger = None
        self.assertIsNone(adapter.spend_warning())
        adapter.usage_ledger = RaisingLedger()
        with self.assertLogs("ai_dnd.api.ollama", "WARNING"):
            self.assertIsNone(adapter.spend_warning())


class TheHttpSurface(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.adapter = AuthenticatedOllamaAdapter(EngineStub(), model_name="gemma4:e4b")
        self.enterContext(self.adapter.engine_binding())
        self.manager = TestPlayerSessionManager()
        app = create_app(session_manager=self.manager, ollama_adapter=self.adapter,
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.addAsyncCleanup(self.http.aclose)

    async def test_health_stays_as_it_was_with_no_chain(self):
        health = await self.http.get("/api/game/health")
        self.assertEqual(health.json(), {"status": "ok", "engine": "AI-DND", "model": "gemma4:e4b"})

    async def test_health_shows_the_chain_without_calling_the_cloud_local(self):
        self.adapter._chain = chain_for(FakeCloud())
        for path in ("/api/game/health", "/api/health"):
            health = (await self.http.get(path)).json()
            self.assertEqual(health["model"], "gemma4:e4b")
            self.assertEqual(health["model_chain"], ["gemini-3.5-flash-lite", "claude-haiku-5-5", "gemma4:e4b"])
            self.assertNotIn(KEY, json.dumps(health))

    async def test_no_cloud_model_joins_the_local_allow_list(self):
        self.assertFalse({"gemini-3.5-flash-lite", "claude-haiku-5-5"} & set(SUPPORTED_LOCAL_MODELS))

    async def turn(self, narrate):
        created = (await self.http.post("/api/sessions")).json()
        self.manager.get(created["session_id"]).game_session.run_player_turn = narrate
        return await self.http.post(f"/api/sessions/{created['session_id']}/turn", json={"message": "Bekle"})

    async def test_the_turn_log_names_the_provider_that_answered(self):
        self.adapter._chain = chain_for(FakeCloud(gemini=ok(gemini_reply())))

        def narrate(message):
            game.ollama.chat(model=ollama_adapter.MODEL_NAME, messages=list(CALL["messages"]), format=SCHEMA, think=False, options={})
            return {"action_result": {"action": "wait", "status": "resolved"}, "narration": "Bekliyorsun."}

        with self.assertLogs("ai_dnd.api", "INFO") as logs:
            response = await self.turn(narrate)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Turn providers (answered=gemini)", "\n".join(logs.output))

    async def test_a_failed_classifier_on_the_chain_path_still_gives_the_player_a_turn(self):
        self.adapter._chain = chain_for(FakeCloud(gemini=httpx.Response(500), haiku=httpx.Response(500)))
        self.adapter._client.chat = lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))

        def narrate(message):
            self.assertEqual(game.parse_player_intent(message), {"intent": "unknown"})
            return {"action_result": {"action": "wait", "status": "resolved"}, "narration": "Bekliyorsun."}

        response = await self.turn(narrate)
        self.assertEqual(response.status_code, 200, response.text)

    async def test_no_provider_line_with_no_chain(self):
        narrate = lambda message: {"action_result": {"action": "wait", "status": "resolved"}, "narration": "Bekliyorsun."}
        with self.assertLogs("ai_dnd.api", "INFO") as logs:
            await self.turn(narrate)
        self.assertNotIn("Turn providers", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
