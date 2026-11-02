"""One local record a turn, beside the route log: calls, tokens, provider, route. Nothing the player said, no key."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import front_proposal
from api import ollama_adapter
from api.tests.test_front_proposal import FrontClient, FrontTable


class Counted(FrontClient):
    """A provider that says what it spent, the way Ollama and the chain's replies do."""

    def chat(self, *args, **kwargs):
        reply = super().chat(*args, **kwargs)
        return {**reply, "prompt_eval_count": 100, "eval_count": 7}


class Records(FrontTable):
    async def counted(self):
        await self.begin()
        self.client = Counted()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def usage_file(self):
        return self.route_file.with_name("routes.usage.jsonl")

    def rows(self):
        return [json.loads(line) for line in self.usage_file().read_text(encoding="utf-8").splitlines()]

    async def test_a_turn_writes_one_record_beside_the_route_log(self):
        await self.counted()
        self.client.front = {"kind": "attempt"}
        await self.line("yerdeki tasi alip duvara firlatiyom")
        row = self.rows()[-1]
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(row["route"], self.routes()[-1]["route"])
        self.assertEqual(row["turn"], self.routes()[-1]["turn"])
        self.assertEqual(row["calls"], self.client.chat_calls)
        self.assertEqual(row["input_tokens"], 100 * self.client.chat_calls)
        self.assertEqual(row["output_tokens"], 7 * self.client.chat_calls)

    async def test_it_says_who_answered(self):
        await self.counted()
        self.client.front = {"kind": "attempt"}
        await self.line("yerdeki tasi alip duvara firlatiyom")
        model = self.app.state.ollama_adapter.model_name
        self.assertEqual([part["provider"] for part in self.rows()[-1]["providers"]], [model])
        self.assertEqual(self.rows()[-1]["providers"][0]["calls"], self.client.chat_calls)

    async def test_it_holds_no_player_words_and_only_its_own_fields(self):
        await self.counted()
        self.client.front = {"kind": "attempt"}
        await self.line("yerdeki Zümrütbaş tasini alip duvara firlatiyom")
        raw = self.usage_file().read_text(encoding="utf-8")
        self.assertNotIn("Zümrütbaş", raw)
        self.assertEqual(set(self.rows()[-1]), {"at", "turn", "route", "calls", "failed", "input_tokens", "output_tokens", "providers"})

    async def test_a_turn_no_model_saw_is_recorded_with_no_calls(self):
        await self.counted()
        self.client.front = {"kind": "bag"}
        await self.line("cantamda ne var", mode="ask_dm")
        self.assertEqual(self.rows()[-1]["calls"], self.client.chat_calls)

    async def test_a_call_that_failed_is_counted_as_failed(self):
        await self.counted()
        self.client.fails = ConnectionError("gone")
        await self.line("etrafa soyle bi goz atayim")
        self.assertGreaterEqual(self.rows()[-1]["failed"], 1)

    async def test_two_turns_are_two_records_and_do_not_add_up(self):
        await self.counted()
        self.client.front = {"kind": "attempt"}
        await self.line("yerdeki tasi alip duvara firlatiyom")
        first = self.client.chat_calls
        await self.line("bir tas daha firlatiyom duvara")
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.rows()[-1]["calls"], self.client.chat_calls - first)

    async def test_no_route_log_set_means_no_record(self):
        await self.counted()
        with patch.dict(os.environ, {"AI_DND_ROUTE_LOG": ""}):
            self.client.front = {"kind": "attempt"}
            await self.line("yerdeki tasi alip duvara firlatiyom")
        self.assertFalse(self.usage_file().exists())


class TheCount(unittest.TestCase):
    def test_a_reply_object_or_a_dict_both_count(self):
        ollama_adapter.begin_turn_usage()
        ollama_adapter.note_usage("gemini", {"prompt_eval_count": 3, "eval_count": 4})

        class Reply:
            prompt_eval_count = 5
            eval_count = None

        ollama_adapter.note_usage("gemini", Reply())
        ollama_adapter.note_usage("haiku", {})
        summary = ollama_adapter.usage_summary()
        self.assertEqual(summary["calls"], 3)
        self.assertEqual(summary["input_tokens"], 8)
        self.assertEqual(summary["output_tokens"], 4)
        self.assertEqual([part["provider"] for part in summary["providers"]], ["gemini", "haiku"])

    def test_local_play_keeps_the_logs_in_the_users_own_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            environ = {"LOCALAPPDATA": folder}
            front_proposal.default_on_for_local_play(environ)
            self.assertEqual(Path(environ[front_proposal.ROUTE_LOG]).parent, Path(folder) / "AI-DND")

    def test_a_path_someone_set_stays(self):
        environ = {front_proposal.ROUTE_LOG: "elsewhere.jsonl"}
        front_proposal.default_on_for_local_play(environ)
        self.assertEqual(environ[front_proposal.ROUTE_LOG], "elsewhere.jsonl")
