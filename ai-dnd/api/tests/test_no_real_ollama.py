"""A test that reaches a real Ollama server fails loudly instead of using whatever model the machine has (D-292).

On a machine with a live local Ollama, a game turn that nobody patched (``game.ollama.chat``) really calls the model
and then fails on the model's own words (D-223). Importing this module makes every real network transport of the
process refuse a request to the Ollama host, so such a test errors at once and names the cause. Fakes are untouched:
``ASGITransport`` and ``MockTransport`` are other classes.
"""

from __future__ import annotations

import os
import unittest
from typing import TYPE_CHECKING
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import ollama

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

OLLAMA_PORT = 11434


class RealOllamaCallError(RuntimeError):
    """A test sent a request to the Ollama host; it must patch ``game.ollama.chat`` or use a fake model."""


def _is_ollama(request: httpx.Request) -> bool:
    host = urlsplit(os.environ.get("OLLAMA_HOST", "")).netloc
    return request.url.port == OLLAMA_PORT or (bool(host) and request.url.netloc.decode() == host)


def _refuse(
    real: Callable[[httpx.HTTPTransport, httpx.Request], httpx.Response],
) -> Callable[[httpx.HTTPTransport, httpx.Request], httpx.Response]:
    def guarded(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        if _is_ollama(request):
            message = f"a test called the real Ollama at {request.url}; patch game.ollama.chat"
            raise RealOllamaCallError(message)
        return real(self, request)
    return guarded


def _refuse_async(
    real: Callable[[httpx.AsyncHTTPTransport, httpx.Request], Awaitable[httpx.Response]],
) -> Callable[[httpx.AsyncHTTPTransport, httpx.Request], Awaitable[httpx.Response]]:
    async def guarded(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        if _is_ollama(request):
            message = f"a test called the real Ollama at {request.url}; patch game.ollama.chat"
            raise RealOllamaCallError(message)
        return await real(self, request)
    return guarded


# ``setattr``, not ``patch.object(...).start()``: another module's ``patch.stopall()`` would undo a started patch and
# leave the rest of the process unguarded. Once only, so a re-import never wraps the guard twice.
for _transport, _method, _wrap in (
    (httpx.HTTPTransport, "handle_request", _refuse),
    (httpx.AsyncHTTPTransport, "handle_async_request", _refuse_async),
):
    _real = getattr(_transport, _method)
    if _real.__name__ != "guarded":
        setattr(_transport, _method, _wrap(_real))

class RealOllamaIsRefusedTests(unittest.TestCase):
    def test_the_ollama_client_on_the_default_port_raises_at_once(self) -> None:
        with self.assertRaises(RealOllamaCallError):
            ollama.Client(host=f"http://127.0.0.1:{OLLAMA_PORT}").list()

    def test_the_host_the_environment_names_raises_too(self) -> None:
        with (
            patch.dict(os.environ, {"OLLAMA_HOST": "http://models.example:8080"}),
            self.assertRaises(RealOllamaCallError),
        ):
            ollama.Client(host="http://models.example:8080").list()

    def test_the_guard_survives_a_patch_stopall_from_another_module(self) -> None:
        patch.stopall()
        with self.assertRaises(RealOllamaCallError):
            ollama.Client(host=f"http://127.0.0.1:{OLLAMA_PORT}").list()

    def test_another_host_is_left_alone(self) -> None:
        request = httpx.Request("GET", "http://other.example:8080/")
        self.assertFalse(_is_ollama(request))


if __name__ == "__main__":
    unittest.main()
