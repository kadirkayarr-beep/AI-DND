"""The per-turn model-call budget: one repair call may pass the cap after a failed speech check (D-332)."""
import unittest

from api import model_phase, ollama_adapter
from api.tests import test_dialogue_runtime as base


class RepairBudgetTests(unittest.TestCase):
    def ask(self, adapter):
        return adapter.chat(model=ollama_adapter.MODEL_NAME, messages=[{"role": "user", "content": "x"}])

    def adapter(self):
        return ollama_adapter.AuthenticatedOllamaAdapter(base.FreeReplyClient())

    def test_a_repair_may_take_one_call_past_the_cap(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            self.ask(adapter)
            with model_phase.repair_call():
                self.ask(adapter)
            self.assertEqual(len(calls), 3)
            self.assertEqual(ollama_adapter.turn_call_cap(calls), 3)

    def test_a_second_repair_is_refused(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            self.ask(adapter)
            with model_phase.repair_call():
                self.ask(adapter)
            with model_phase.repair_call(), self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 3)

    def test_an_ordinary_third_call_is_still_refused(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            self.ask(adapter)
            with self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 2)
            self.assertEqual(ollama_adapter.turn_call_cap(calls), ollama_adapter.MAX_MODEL_CALLS_PER_TURN)

    def test_initiative_and_repair_never_make_four(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            with model_phase.front_call():
                self.ask(adapter)
            self.ask(adapter)
            with model_phase.initiative_call():
                self.ask(adapter)
            self.assertEqual(len(calls), 3)
            with model_phase.repair_call(), self.assertRaisesRegex(RuntimeError, "budget"):
                self.ask(adapter)
            self.assertEqual(len(calls), 3)

    def test_a_repair_alone_is_an_ordinary_call(self):
        adapter = self.adapter()
        with adapter.capture_model_calls() as calls:
            self.ask(adapter)
            with model_phase.repair_call():
                self.ask(adapter)
            self.assertEqual(len(calls), 2)
            self.assertEqual(ollama_adapter.model_calls_left(), 0)


if __name__ == "__main__":
    unittest.main()
