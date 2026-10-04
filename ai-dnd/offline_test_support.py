"""Scoped model ownership for legacy offline script entry points."""

from functools import wraps
import sys
from unittest.mock import MagicMock, patch


DEFAULT_CONTENT = (
    '{"intent":"narrative","action":"test",'
    '"target":{"type":"none","reference":""},'
    '"completion":"unclear","confidence":0.5}'
)


def offline_model(engine, content=DEFAULT_CONTENT):
    """Give each invocation a fresh mock and restore both bindings on exit.

    Import the engine normally before using this decorator. Collection must
    never seed the engine's permanent model reference with an offline mock.
    The module binding covers terminal paths that import ollama again.
    """
    def decorate(test):
        @wraps(test)
        def run(*args, **kwargs):
            model = MagicMock()
            model.chat.return_value = {"message": {"content": content}}
            with patch.object(engine, "ollama", model), \
                 patch.dict(sys.modules, {"ollama": model}):
                return test(*args, **kwargs)
        return run
    return decorate