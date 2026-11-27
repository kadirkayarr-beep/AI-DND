"""A test that reaches a real Ollama server fails loudly instead of using whatever model the machine has (D-292).

On a machine with a live local Ollama, a game turn that nobody patched (``game.ollama.chat``) really calls the model
and then fails on the model's own words (D-223). Importing this module makes every real network transport of the
process refuse a request to the Ollama host, so such a test errors at once and names the cause. Fakes are untouched:
``ASGITransport`` and ``MockTransport`` are other classes.
"""

from __future__ import annotations

import os
import unittest
from typing import Any
from urllib.parse import urlsplit
from unittest.mock import patch

import httpx
import ollama

OLLAMA_PORT = 11434


class RealOllamaCall(RuntimeError):
    """A test sent a request to the Ollama host; it must patch ``game.ollama.chat`` or use a fake model."""


def _is_ollama(request: httpx.Request) -> bool:
    host = urlsplit(os.environ.get("OLLAMA_HOST", "")).netloc
    return request.url.port == OLLAMA_PORT or bool(host) and request.url.netloc.decode() == host


def _refuse(real: Any) -> Any:
    def guarded(self: Any, request: httpx.Request) -> Any:
        if _is_ollama(request):
            raise RealOllamaCall(f"a test called the real Ollama at {request.url}; patch game.ollama.chat")
        return real(self, request)
    return guarded


def _refuse_async(real: Any) -> Any:
    async def guarded(self: Any, request: httpx.Request) -> Any:
        if _is_ollama(request):
            raise RealOllamaCall(f"a test called the real Ollama at {request.url}; patch game.ollama.chat")
        return await real(self, request)
    return guarded


patch.object(httpx.HTTPTransport, "handle_request", _refuse(httpx.HTTPTransport.handle_request)).start()
patch.object(httpx.AsyncHTTPTransport, "handle_async_request",
             _refuse_async(httpx.AsyncHTTPTransport.handle_async_request)).start()


class RealOllamaIsRefused(unittest.TestCase):
    def test_the_ollama_client_on_the_default_port_raises_at_once(self) -> None:
        with self.assertRaises(RealOllamaCall):
            ollama.Client(host=f"http://127.0.0.1:{OLLAMA_PORT}").list()

    def test_the_host_the_environment_names_raises_too(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://models.example:8080"}):
            with self.assertRaises(RealOllamaCall):
                ollama.Client(host="http://models.example:8080").list()

    def test_another_host_is_left_alone(self) -> None:
        request = httpx.Request("GET", "http://other.example:8080/")
        self.assertFalse(_is_ollama(request))


if __name__ == "__main__":
    unittest.main()
