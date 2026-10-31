"""The cloud model chain, on fake HTTP only: translation, failure, spending, secrets."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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

    def test_the_call_waits_twenty_seconds_at_most(self):
        timeout = chain_for(FakeCloud())._http.timeout
        self.assertEqual((timeout.connect, timeout.read, timeout.write, timeout.pool), (20, 20, 20, 20))

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

    def test_below_two_dollars_haiku_still_answers(self):
        path = spend_file()
        self.spent(path, input_tokens=19_000_000, output_tokens=199_999)
        self.assertEqual(self.haiku_only(path).chat(CALL, LocalModel())[1], "haiku")

    def test_at_two_dollars_haiku_is_not_called_at_all(self):
        path = spend_file()
        self.spent(path, input_tokens=19_000_000, output_tokens=200_000)
        local = LocalModel()
        self.assertIsNone(self.haiku_only(path).chat(CALL, local)[1])
        self.assertEqual(local.calls, 1)
        self.assertEqual(self.cloud.hosts(), [GOOGLE])

    def test_a_new_month_starts_at_zero(self):
        path = spend_file()
        self.spent(path, month="2026-09", input_tokens=40_000_000)
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


if __name__ == "__main__":
    unittest.main()
