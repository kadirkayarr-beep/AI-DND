"""Offline model-binding ownership checks; no model requests or HTTP acceptance."""

import sys
import unittest
from unittest.mock import MagicMock, patch

import game
import test_regression as legacy
from api.ollama_adapter import AuthenticatedOllamaAdapter


class ModelIsolationTests(unittest.TestCase):
    def test_permanent_install_keeps_existing_production_binding(self):
        target = MagicMock()
        client = MagicMock()
        adapter = AuthenticatedOllamaAdapter(client)
        with patch.object(game, "ollama", target):
            adapter.install_for_engine()
            self.assertIs(game.ollama, target)
            self.assertIs(target.list, client.list)
            self.assertEqual(target.chat, adapter.chat)
            target.chat(model="qwen3:8b", messages=[])
            client.chat.assert_called_once_with(model="qwen3:8b", messages=[])

    def test_nested_scopes_restore_exact_callbacks_after_exception(self):
        target = MagicMock()
        original_list, original_chat = target.list, target.chat
        outer = AuthenticatedOllamaAdapter(MagicMock())
        inner = AuthenticatedOllamaAdapter(MagicMock())
        with patch.object(game, "ollama", target):
            with outer.engine_binding():
                outer_list, outer_chat = target.list, target.chat
                with self.assertRaisesRegex(RuntimeError, "fixture failed"):
                    with inner.engine_binding():
                        self.assertEqual(target.chat, inner.chat)
                        raise RuntimeError("fixture failed")
                self.assertIs(target.list, outer_list)
                self.assertIs(target.chat, outer_chat)
            self.assertIs(target.list, original_list)
            self.assertIs(target.chat, original_chat)

    def test_setup_failure_still_restores_model_callbacks(self):
        adapter = AuthenticatedOllamaAdapter(MagicMock())

        class BrokenFixture(unittest.TestCase):
            def setUp(self):
                self.enterContext(adapter.engine_binding())
                raise RuntimeError("setup failed")

            def runTest(self):
                raise AssertionError("body should not run")

        target = MagicMock()
        original_list, original_chat = target.list, target.chat
        with patch.object(game, "ollama", target):
            result = unittest.TestResult()
            BrokenFixture().run(result)
            self.assertEqual(len(result.errors), 1)
            self.assertIs(target.list, original_list)
            self.assertIs(target.chat, original_chat)

    def test_legacy_mock_is_fresh_and_restores_both_bindings(self):
        previous_mock = legacy.ollama_mock
        previous_module = sys.modules.get("ollama")
        target = MagicMock()
        mocks = []

        @legacy.isolated_model
        def probe():
            model = legacy.ollama_mock
            mocks.append(model)
            self.assertIs(game.ollama, model)
            self.assertIs(sys.modules["ollama"], model)
            self.assertIsNone(model.chat.side_effect)
            self.assertEqual(model.chat.call_count, 0)
            model.chat.side_effect = RuntimeError("unavailable")
            raise RuntimeError("body failed")

        with patch.object(game, "ollama", target):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "body failed"):
                    probe()
                self.assertIs(game.ollama, target)
                self.assertIs(sys.modules.get("ollama"), previous_module)
                self.assertIs(legacy.ollama_mock, previous_mock)
        self.assertIsNot(mocks[0], mocks[1])

    def test_legacy_test_does_not_overwrite_active_api_adapter(self):
        target = MagicMock()
        adapter = AuthenticatedOllamaAdapter(MagicMock())
        with patch.object(game, "ollama", target):
            with adapter.engine_binding():
                active_list, active_chat = target.list, target.chat
                legacy.test_malformed_intent_json()
                self.assertIs(game.ollama, target)
                self.assertIs(target.list, active_list)
                self.assertIs(target.chat, active_chat)


if __name__ == "__main__":
    unittest.main()