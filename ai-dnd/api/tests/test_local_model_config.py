"""Direct unit tests for api.local_model_config: explicit local model selection, never a download."""

import os
import unittest
from unittest import mock

from api import local_model_config as config


class ValidateTests(unittest.TestCase):
    def test_every_supported_model_validates_to_itself(self):
        for name in config.SUPPORTED_LOCAL_MODELS:
            with self.subTest(model=name):
                self.assertEqual(config.validate_local_model(name), name)

    def test_unsupported_value_is_refused_without_echoing_it(self):
        with self.assertRaises(ValueError) as caught:
            config.validate_local_model("secret-config-value")
        self.assertNotIn("secret-config-value", str(caught.exception))

    def test_defaults_and_fallback_are_supported_models(self):
        self.assertIn(config.DEFAULT_LOCAL_MODEL, config.SUPPORTED_LOCAL_MODELS)
        self.assertIn(config.PRODUCTION_LOCAL_MODEL, config.SUPPORTED_LOCAL_MODELS)
        for source, fallback in config.LOCAL_FALLBACK_MODELS.items():
            self.assertIn(source, config.SUPPORTED_LOCAL_MODELS)
            self.assertIn(fallback, config.SUPPORTED_LOCAL_MODELS)
        self.assertEqual(list(config.LOCAL_FALLBACK_MODELS), [config.PRODUCTION_LOCAL_MODEL])


class SelectedModelTests(unittest.TestCase):
    def test_unset_environment_selects_the_production_model(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_DND_OLLAMA_MODEL", None)
            self.assertEqual(config.selected_local_model(), config.PRODUCTION_LOCAL_MODEL)

    def test_environment_choice_is_used_and_checked(self):
        with mock.patch.dict(os.environ, {"AI_DND_OLLAMA_MODEL": "qwen3:8b"}):
            self.assertEqual(config.selected_local_model(), "qwen3:8b")
        with mock.patch.dict(os.environ, {"AI_DND_OLLAMA_MODEL": "gpt-9000"}):
            with self.assertRaises(ValueError):
                config.selected_local_model()


if __name__ == "__main__":
    unittest.main()
