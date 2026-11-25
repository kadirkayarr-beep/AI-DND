"""Direct tests for the pure helpers of api.ollama_adapter: prompt layout, history summary, usage counting."""
import contextvars
import unittest

import httpx
import ollama

from api import ollama_adapter as adapter


class ContextWindowTests(unittest.TestCase):
    def test_fixed_model_window_and_default(self):
        self.assertEqual(adapter.local_context_window("gemma4-12b-dm"), 12288)
        self.assertEqual(adapter.local_context_window("any-other"), adapter.CONTEXT_WINDOW_TOKENS)


class PromptLayoutTests(unittest.TestCase):
    def setUp(self):
        self.engine = "Kurallar." + f"\n\n{adapter._METADATA_HEADER}\nsaat: 9"
        self.messages = [{"role": "system", "content": self.engine}, {"role": "user", "content": "Kapıyı açıyorum."}]

    def test_no_system_text_is_returned_unchanged(self):
        messages = [{"role": "user", "content": "x"}]
        self.assertEqual(adapter._cache_friendly(messages, style=True, metadata_at_end=True), messages)

    def test_metadata_moves_to_the_end_of_the_last_user_message(self):
        out = adapter._cache_friendly(self.messages, style=False, metadata_at_end=True)
        self.assertEqual(out[0]["content"], "Kurallar.")
        self.assertEqual(out[1]["content"], f"Kapıyı açıyorum.\n\n{adapter._METADATA_HEADER}\nsaat: 9")
        self.assertEqual(self.messages[0]["content"], self.engine, "the caller's messages are not changed")

    def test_style_rules_follow_the_engine_text(self):
        out = adapter._cache_friendly(self.messages, style=True, metadata_at_end=False)
        self.assertEqual(out[0]["content"],
                         f"{self.engine}\n\n{adapter.LOCAL_STYLE_RULES}\n\n{adapter.LOCAL_DM_EXAMPLE}")
        self.assertEqual(out[1], self.messages[1])

    def test_cloud_style_is_added_to_the_first_system_text_only(self):
        prepared = {"model": "m", "messages": self.messages}
        out = adapter._with_cloud_style(prepared)
        self.assertTrue(out["messages"][0]["content"].endswith(f"\n\n{adapter.CLOUD_STYLE_RULES}"))
        self.assertEqual(out["messages"][1], self.messages[1])
        self.assertEqual(adapter._with_cloud_style({"messages": []}), {"messages": []})


class HistorySummaryTests(unittest.TestCase):
    def test_summary_keeps_the_first_sentence_of_each_line(self):
        line = adapter._history_summary(["- Kapı açıldı. İçerisi karanlık.", "- Bir ses geldi! Sonra sustu."])
        self.assertEqual(line, "- (Daha eski 2 anlatımın özeti: Kapı açıldı. / Bir ses geldi!)")

    def test_summary_is_capped(self):
        line = adapter._history_summary([f"- {'uzun cümle ' * 20}." for _ in range(20)])
        self.assertEqual(len(line), adapter._HISTORY_SUMMARY_MAX_CHARS)
        self.assertTrue(line.endswith("…)"))


class UsageTests(unittest.TestCase):
    def test_usage_summary_counts_answered_calls_by_provider(self):
        def turn():
            adapter.begin_turn_usage()
            adapter.note_usage("local", {"prompt_eval_count": 100, "eval_count": 20})
            adapter.note_usage("gemini", {"prompt_eval_count": 50, "eval_count": "x"})
            adapter.note_usage("local", None, failed=True)
            return adapter.usage_summary()

        summary = contextvars.copy_context().run(turn)
        self.assertEqual(summary["calls"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual((summary["input_tokens"], summary["output_tokens"]), (150, 20))
        self.assertEqual([p["provider"] for p in summary["providers"]], ["local", "gemini"])

    def test_outage_is_transport_or_provider_5xx_only(self):
        self.assertTrue(adapter._provider_outage(OSError("refused")))
        self.assertTrue(adapter._provider_outage(httpx.ConnectTimeout("slow")))
        self.assertTrue(adapter._provider_outage(ollama.ResponseError("busy", 503)))
        self.assertFalse(adapter._provider_outage(ollama.ResponseError("bad", 400)))
        self.assertFalse(adapter._provider_outage(ValueError("parse")))


if __name__ == "__main__":
    unittest.main()
