"""G2.3: the model-call ceiling and the usage record (D-150, D-416, D-417, D-418, D-419, D-494, D-496)."""

from __future__ import annotations

import ast
import json
import os
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

import dialogue_runtime
import front_proposal
import model_phase
from api import model_chain, ollama_adapter, usage_ledger
from api.tests import test_dialogue_runtime as base
from api.tests import test_front_proposal as front_tests
from api.tests.test_model_failure_never_locks import ReadingClient
from api.tests.town_seed import fixed_town
from api.tests.test_model_chain import CALL, FakeCloud, haiku_reply, ok
from api.tests.test_npc_initiative import call_kinds

TESTS = Path(__file__).resolve().parent


class FixedClock:
    def __call__(self):
        return datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


class TestHaikuUnknownUsage(unittest.TestCase):
    """D-150: a Haiku call whose usage never came back counts at the highest possible cost."""

    def counter(self, plan):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "play" / "spend.json"
        spend = model_chain.HaikuSpend(path, FixedClock())
        chain = model_chain.ModelChain([model_chain.haiku("k", spend)], transport=httpx.MockTransport(FakeCloud(haiku=plan)),
                                       now=FixedClock())
        local = {"message": {"role": "assistant", "content": "{}"}}
        chain.chat(CALL, lambda: local)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return saved["input_tokens"], saved["output_tokens"]

    def test_a_timed_out_call_is_counted_at_its_highest_cost(self):
        for name, plan in (("read timeout", httpx.ReadTimeout("slow")), ("dropped", httpx.RemoteProtocolError("cut")),
                           ("not json", httpx.Response(200, text="<html>"))):
            with self.subTest(plan=name):
                counted = self.counter(plan)
                self.assertIsNotNone(counted)
                self.assertEqual(counted[1], CALL["options"]["num_predict"])
                body = model_chain.haiku_body(CALL)
                self.assertGreaterEqual(counted[0], len(json.dumps(body["messages"])) // 4)

    def test_a_reply_without_usage_is_counted_at_its_highest_cost(self):
        reply = haiku_reply()
        reply.pop("usage")
        counted = self.counter(ok(reply))
        self.assertEqual(counted[1], CALL["options"]["num_predict"])
        self.assertGreater(counted[0], 0)

    def test_a_refused_request_is_not_billed(self):
        for name, plan in (("bad request", httpx.Response(400)), ("key refused", httpx.Response(401)),
                           ("unprocessable", httpx.Response(422)), ("rate limit", httpx.Response(429)),
                           ("never connected", httpx.ConnectError("down"))):
            with self.subTest(plan=name):
                self.assertIsNone(self.counter(plan))

    def test_a_reply_with_its_usage_adds_exactly_that(self):
        self.assertEqual(self.counter(ok(haiku_reply())), (haiku_reply()["usage"]["input_tokens"],
                                                           haiku_reply()["usage"]["output_tokens"]))


class TestTheCallCeiling(unittest.TestCase):
    def ask(self, adapter):
        return adapter.chat(model=ollama_adapter.MODEL_NAME, messages=[{"role": "user", "content": "x"}])

    def adapter(self):
        return ollama_adapter.AuthenticatedOllamaAdapter(base.FreeReplyClient())

    def test_a_plain_call_after_a_front_reading_and_an_initiative_is_refused(self):
        """D-416: the extra room is the initiative's own call, not any later call's."""
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            with model_phase.front_call():
                self.ask(adapter)
            with model_phase.initiative_call():
                self.ask(adapter)
            self.assertEqual(len(calls), 2)
            with self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 2)

    def test_a_plain_call_after_a_front_reading_an_initiative_and_a_plain_call_is_refused(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            with model_phase.front_call():
                self.ask(adapter)
            self.ask(adapter)
            with model_phase.initiative_call():
                self.ask(adapter)
            self.assertEqual((len(calls), ollama_adapter.turn_call_cap(calls)), (3, 3))
            with self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)

    def test_the_most_a_turn_may_make_is_three(self):
        self.assertEqual(ollama_adapter.turn_call_cap((), most=True), 3)
        self.assertEqual(ollama_adapter.turn_call_cap(()), ollama_adapter.MAX_MODEL_CALLS_PER_TURN)

    def test_the_third_call_of_the_rest_of_a_line_is_allowed_once(self):
        """D-419 (Kadir S20 a): 'the rest of the line' and a stock answer may take the third call."""
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            with model_phase.front_call():
                self.ask(adapter)
            self.ask(adapter)
            self.assertEqual(ollama_adapter.model_calls_left(), 0)
            self.assertEqual(ollama_adapter.model_calls_left(third=True), 1)
            with ollama_adapter.third_call():
                self.ask(adapter)
                self.assertEqual(ollama_adapter.model_calls_left(third=True), 0)
                with self.assertRaisesRegex(RuntimeError, "budget"):
                    self.ask(adapter)
            self.assertEqual(len(calls), 3)
            self.assertLessEqual(len(calls), ollama_adapter.turn_call_cap(calls))
            with self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(ollama_adapter.model_calls_left(third=True), 0)

    def test_an_ordinary_third_call_is_still_refused_outside_the_marker(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            self.ask(adapter)
            with self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 2)

    def test_the_third_call_and_a_repair_never_make_four(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            self.ask(adapter)
            with ollama_adapter.third_call():
                self.ask(adapter)
            with model_phase.repair_call(), self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 3)


class TestTheLiveSmokes(unittest.TestCase):
    """D-417: the live smoke scripts read the adapter's ceiling; none keeps its own copy of two."""

    OWN = ("live_phase7_lore_smoke.py", "live_neverwinter_canon_smoke.py", "playable_living_world_v1_review.py")

    @staticmethod
    def tree(name):
        return ast.parse((TESTS / name).read_text(encoding="utf-8"))

    @staticmethod
    def imported(tree, module):
        return {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == module
                for alias in node.names}

    def test_no_live_script_keeps_a_local_two_call_limit(self):
        for name in self.OWN:
            with self.subTest(script=name):
                tree = self.tree(name)
                limits = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "MAX_MODEL_CALLS_PER_TURN"
                                  for target in node.targets)]
                self.assertTrue(limits, "the script still names its limit")
                for node in limits:
                    self.assertNotIsInstance(node.value, ast.Constant, "the limit must come from the adapter")
                self.assertIn("turn_call_cap", self.imported(tree, "api.ollama_adapter"))

    def test_the_playable_smoke_takes_its_limit_from_the_review_that_reads_the_adapter(self):
        tree = self.tree("live_playable_living_world_v1_smoke.py")
        names = {target.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name)}
        self.assertNotIn("MAX_MODEL_CALLS_PER_TURN", names)
        self.assertIn("MAX_MODEL_CALLS_PER_TURN", self.imported(tree, "api.tests.playable_living_world_v1_review"))

    def test_every_script_limit_is_the_adapters_ceiling(self):
        from api.tests import live_neverwinter_canon_smoke, live_phase7_lore_smoke, live_playable_living_world_v1_smoke
        from api.tests import playable_living_world_v1_review
        for module in (live_neverwinter_canon_smoke, live_phase7_lore_smoke, live_playable_living_world_v1_smoke,
                       playable_living_world_v1_review):
            self.assertEqual(module.MAX_MODEL_CALLS_PER_TURN, ollama_adapter.turn_call_cap((), most=True), module)

    def test_the_long_incident_smoke_reads_the_canon_script_limit(self):
        text = (TESTS / "live_incident_long_smoke.py").read_text(encoding="utf-8")
        self.assertNotIn("MAX_MODEL_CALLS_PER_TURN = ", text)
        self.assertIn("canon.MAX_MODEL_CALLS_PER_TURN", text)


class TestTheLocalLock(unittest.TestCase):
    def test_a_busy_local_model_falls_back_after_a_bounded_wait(self):
        """D-494: a held local lock ends the second call with a timeout, never a wait without end."""
        client = base.FreeReplyClient()
        adapter = ollama_adapter.AuthenticatedOllamaAdapter(client)
        held = threading.Event()
        release = threading.Event()

        def hold():
            with ollama_adapter._LOCAL_CALL_LOCK:
                held.set()
                release.wait(10)

        worker = threading.Thread(target=hold, daemon=True)
        worker.start()
        self.assertTrue(held.wait(5))
        try:
            with patch.object(ollama_adapter, "LOCAL_LOCK_WAIT_SECONDS", 0.2), \
                    adapter.capture_model_failures() as failures, \
                    self.assertRaisesRegex(RuntimeError, "Ollama request failed"):
                adapter.chat(model=ollama_adapter.MODEL_NAME, messages=[{"role": "user", "content": "x"}])
            self.assertEqual(client.calls, 0, "the busy model was never called")
            self.assertEqual(list(failures), ["TimeoutError"])
        finally:
            release.set()
            worker.join(5)
        self.assertTrue(ollama_adapter._LOCAL_CALL_LOCK.acquire(timeout=1), "the lock is free again")
        ollama_adapter._LOCAL_CALL_LOCK.release()

    def test_a_free_lock_answers_and_is_released(self):
        client = base.FreeReplyClient()
        adapter = ollama_adapter.AuthenticatedOllamaAdapter(client)
        adapter.chat(model=ollama_adapter.MODEL_NAME, messages=[{"role": "user", "content": "x"}])
        self.assertEqual(client.calls, 1)
        self.assertTrue(ollama_adapter._LOCAL_CALL_LOCK.acquire(timeout=1))
        ollama_adapter._LOCAL_CALL_LOCK.release()


class TestTheHealthWarning(unittest.TestCase):
    def test_two_health_reads_in_a_row_read_the_ledger_file_once(self):
        """D-496: the spend warning is kept for a few seconds."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        ledger = usage_ledger.UsageLedger(Path(folder.name) / "usage.jsonl")
        ledger.record("haiku", input_tokens=10, output_tokens=10)
        adapter = ollama_adapter.AuthenticatedOllamaAdapter(base.FreeReplyClient())
        adapter.usage_ledger = ledger
        clock = [100.0]
        adapter._now = lambda: clock[0]
        with patch.object(usage_ledger.UsageLedger, "_read_day", autospec=True,
                          side_effect=usage_ledger.UsageLedger._read_day) as read:
            first = adapter.spend_warning()
            second = adapter.spend_warning()
            self.assertEqual((read.call_count, second), (1, first))
            clock[0] += ollama_adapter.SPEND_WARNING_CACHE_SECONDS + 1
            adapter.spend_warning()
            self.assertEqual(read.call_count, 2)


class TestThreeCallTelemetry(unittest.IsolatedAsyncioTestCase):
    """D-418: a turn of a front reading, a narration and an initiative says three calls in its telemetry."""

    asyncSetUp = base.DialogueRuntimeTests.asyncSetUp
    asyncTearDown = base.DialogueRuntimeTests.asyncTearDown
    setup_free = base.DialogueRuntimeTests.setup_free
    send = base.DialogueRuntimeTests.send

    async def test_a_three_call_turn_reports_three(self):
        self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}))
        await self.setup_free()
        self.npc["dialogue_observation"] = {"id": "injury:test", "kind": "visible_injury", "visible": True,
                                            "location_id": self.world["location"], "turn_index": 0}
        seen = []
        real = dialogue_runtime.observe_turn

        def spy(session, before, old_hp, result, player_text, action_id):
            real(session, before, old_hp, result, player_text, action_id)
            evidence = result.get("_engine_event_evidence") or {}
            seen.append((result.get("model_calls"), (evidence.get("telemetry") or {}).get("total_model_calls")))

        with patch.object(dialogue_runtime, "observe_turn", spy):
            reply = await self.send("Çevreyi gözlemliyorum.", mode="do", action_id=str(uuid.uuid4()))
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(call_kinds(self.reply.batches), ["front", "narration", "initiative"])
        self.assertEqual(self.reply.calls, 3)
        self.assertTrue(seen, "the turn reached the dialogue observer")
        self.assertEqual(seen[-1][1], 3, seen)
        self.assertEqual(seen[-1][0], 3, seen)


class TestTheRefusedTurn(unittest.IsolatedAsyncioTestCase):
    """D-405 and D-408: a lost provider in the turn's own reading refuses the line and changes nothing; every refused
    line still leaves a row in the play measurement files."""

    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    routes = front_tests.FrontTable.routes
    line = front_tests.FrontTable.line
    LINE = "etrafa şöyle bir göz atayım"

    async def begin(self):
        with fixed_town(self, 2701):
            await front_tests.FrontTable.begin(self)
        self.client = ReadingClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def everything(self):
        stored = self.store.get_campaign(self.manager.get(self.session_id).campaign_id)
        return (len(stored.history), stored.payload["engine_save"]), self.session.serialize_game_state(),             self.session.rng.getstate()

    def usage(self):
        path = self.route_file.with_name(f"{self.route_file.stem}.usage{self.route_file.suffix}")
        return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]

    async def test_a_lost_provider_in_the_turns_own_reading_refuses_the_line_and_changes_nothing(self):
        await self.begin()
        ahead = []
        self.session.front_read_ahead = lambda *_args, **_kwargs: ahead.append(1)  # nothing is read ahead
        before = self.everything()
        self.client.fails = ConnectionError("gone")
        failed = await self.http.post(self.turn_url, json={"message": self.LINE, "action_id": str(uuid.uuid4())})
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "ollama_unavailable")
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        self.assertEqual(ahead, [1], "the reading was not run ahead")
        self.assertEqual(self.client.kinds.count("front"), 1, "the turn's own step read it")
        self.assertEqual(self.everything(), before, "state, history and dice are as before")

    async def test_a_refused_line_leaves_a_refused_row_in_both_measurement_files(self):
        await self.begin()
        self.client.fails = ConnectionError("gone")
        failed = await self.http.post(self.turn_url, json={"message": self.LINE, "action_id": str(uuid.uuid4())})
        self.assertEqual(failed.status_code, 503, failed.text)
        route = self.routes()[-1]
        self.assertEqual((route["status"], route["owner"], route["model_calls"]), ("refused", None, 0))
        self.assertTrue(route["route"].startswith("skipped:"), "a refused line is no free line in the model share")
        usage = self.usage()[-1]
        self.assertEqual(usage["outcome"], "refused")
        self.assertEqual((usage["calls"], usage["failed"]), (0, 1))
        self.assertEqual(front_proposal.share(self.routes())["free_lines"], 0)

    async def test_an_answered_line_writes_no_refused_outcome(self):
        await self.begin()
        await self.line(self.LINE)
        self.assertNotIn("outcome", self.usage()[-1])
        self.assertNotEqual(self.routes()[-1]["status"], "refused")


if __name__ == "__main__":
    unittest.main()
