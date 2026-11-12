"""Portrait P1, Task 2: OpenRouter image client, strict response validation, bounded retries. No real network."""
import base64
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import httpx

from api import portrait_client as pc
from api.portrait_client import (BACKUP_MODEL, MAX_IMAGE_BYTES, MAX_RETRY_WAIT_SECONDS, OPENROUTER_URL, PRIMARY_MODEL,
                                 TOTAL_DEADLINE_SECONDS, ImageRejected, PortraitClient, PortraitClientError,
                                 client_from_environment, decode_image, image_kind)

KEY = "sk-or-TEST-9f8e7d"
PROMPT = "SECRET-PROMPT-TEXT dwarf fighter"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24


def b64(data):
    return base64.b64encode(data).decode()


def ok_body(value, field="b64_json", usage=None):
    body = {"data": [{field: value}]}
    if usage is not None:
        body["usage"] = usage
    return body


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def reply(status=200, body=None, headers=None, text=None):
    if text is not None:
        return httpx.Response(status, text=text, headers=headers)
    return httpx.Response(status, json=body if body is not None else {}, headers=headers)


class ClientCase(unittest.TestCase):
    def make(self, *responses, monotonic=None):
        self.rec = Recorder(*responses)
        self.waits = []
        kwargs = {"monotonic": monotonic} if monotonic else {}
        self.client = PortraitClient(KEY, transport=httpx.MockTransport(self.rec), sleep=self.waits.append, **kwargs)
        return self.client

    def fails(self, code="portrait_service_failed"):
        with self.assertLogs("ai_dnd.api.portrait", "DEBUG") as logs:
            with self.assertRaises(PortraitClientError) as caught:
                self.client.generate(PROMPT)
        error = caught.exception
        self.assertEqual(error.code, code)
        self.assertEqual(str(error), code)
        self.assert_clean(error, logs.output)
        return error

    def assert_clean(self, error, log_lines):
        blob = " ".join([str(error), repr(error), repr(self.client), *log_lines])
        self.assertNotIn(KEY, blob)
        self.assertNotIn("SECRET-PROMPT", blob)


class Requests(ClientCase):
    def test_request_shape_and_headers(self):
        self.make(reply(200, ok_body("data:image/png;base64," + b64(PNG), "url", {"cost": 0.009})))
        result = self.client.generate("p")
        request = self.rec.requests[0]
        self.assertEqual((request.method, str(request.url)), ("POST", OPENROUTER_URL))
        self.assertEqual(json.loads(request.content),
                         {"model": PRIMARY_MODEL, "prompt": "p", "aspect_ratio": "1:1", "n": 1})
        self.assertEqual(request.headers["Authorization"], "Bearer " + KEY)
        self.assertEqual(request.headers["HTTP-Referer"], "http://localhost")
        self.assertEqual(request.headers["X-Title"], "ai-dnd")
        self.assertEqual((result.kind, result.data, result.model), ("png", PNG, PRIMARY_MODEL))
        self.assertEqual(result.attempts[0].usd, 0.009)
        self.assertEqual(result.attempts[0].outcome, "image")

    def test_cost_missing_or_bad_is_none(self):
        for usage in (None, {"cost": -1}, {"cost": "0.01"}, {"cost": True}):
            self.make(reply(200, ok_body(b64(PNG), usage=usage)))
            self.assertIsNone(self.client.generate("p").attempts[0].usd)

    def test_b64_json_and_data_url_both_accepted(self):
        self.make(reply(200, ok_body(b64(JPEG))))
        self.assertEqual(self.client.generate("p").kind, "jpeg")
        self.make(reply(200, ok_body("data:image/webp;base64," + b64(WEBP), "url")))
        self.assertEqual(self.client.generate("p").kind, "webp")

    def test_client_ignores_proxy_environment(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}):
            self.make(reply(200, ok_body(b64(PNG))))
            self.assertEqual(self.client.generate("p").kind, "png")
        self.assertIs(self.client._http._trust_env, False)
        self.assertFalse(self.client._http.follow_redirects)


class Validation(ClientCase):
    def test_non_image_bytes_rejected(self):
        self.make(reply(200, ok_body(b64(b"<html>"))))
        self.fails()
        self.assertEqual(len(self.rec.requests), 1)

    def test_svg_and_html_rejected(self):
        for value in ("data:image/svg+xml;base64," + b64(b"<svg xmlns='x'/>"), "data:text/html;base64," + b64(b"<html>")):
            self.make(reply(200, ok_body(value, "url")))
            self.fails()

    def test_declared_type_must_match_magic_bytes(self):
        self.make(reply(200, ok_body("data:image/png;base64," + b64(JPEG), "url")))
        self.fails()

    def test_strict_base64(self):
        for value in (b64(PNG)[:-1] + "!", b64(PNG)[:8] + "\n" + b64(PNG)[8:], "", 5, None):
            self.make(reply(200, ok_body(value)))
            self.fails()

    def test_oversize_rejected_before_decode(self):
        value = "A" * ((MAX_IMAGE_BYTES * 4) // 3 + 17)
        self.make(reply(200, ok_body(value)))
        with mock.patch.object(base64, "b64decode") as decoder:
            self.fails()
        decoder.assert_not_called()

    def test_oversize_response_body_is_capped(self):
        class Endless(httpx.SyncByteStream):
            def __iter__(self):
                for _ in range(10000):
                    yield b"x" * 65536
        self.make(httpx.Response(200, stream=Endless()))
        self.fails()

    def test_remote_url_never_downloaded(self):
        self.make(reply(200, ok_body("https://evil.example/x.png", "url")))
        self.fails()
        self.assertEqual([r.url.host for r in self.rec.requests], ["openrouter.ai"])

    def test_decode_image_direct(self):
        self.assertEqual(decode_image(b64(PNG)), (PNG, "png"))
        with self.assertRaises(ImageRejected):
            decode_image("data:image/gif;base64," + b64(PNG))
        self.assertIsNone(image_kind(b"RIFF\x00\x00\x00\x00WAVE"))
        self.assertIsNone(image_kind(b""))


class RetriesAndRefusals(ClientCase):
    def test_retry_order_and_limit(self):
        self.make(reply(429, headers={"Retry-After": "999"}), reply(503), reply(503))
        error = self.fails()
        models = [json.loads(r.content)["model"] for r in self.rec.requests]
        self.assertEqual(models, [PRIMARY_MODEL, PRIMARY_MODEL, BACKUP_MODEL])
        self.assertEqual(self.waits[0], MAX_RETRY_WAIT_SECONDS)
        self.assertTrue(all(w <= MAX_RETRY_WAIT_SECONDS for w in self.waits))
        self.assertEqual(len(self.waits), 2)
        self.assertEqual([a.status for a in error.attempts], [429, 503, 503])
        self.assertTrue(all(a.outcome == "failed" for a in error.attempts))

    def test_default_wait_is_two_seconds(self):
        self.make(reply(500), reply(200, ok_body(b64(PNG))))
        self.client.generate("p")
        self.assertEqual(self.waits, [2])

    def test_transport_error_retries(self):
        self.make(httpx.ConnectError("boom " + KEY), reply(200, ok_body(b64(PNG))))
        result = self.client.generate("p")
        self.assertIsNone(result.attempts[0].status)
        self.assertEqual(result.attempts[1].outcome, "image")

    def test_backup_answers_after_two_primary_failures(self):
        self.make(reply(500), reply(500), reply(200, ok_body(b64(PNG))))
        result = self.client.generate("p")
        self.assertEqual(result.model, BACKUP_MODEL)
        self.assertEqual(len(result.attempts), 3)

    def test_auth_error_stops_at_once(self):
        for status in (401, 403):
            self.make(reply(status, text="invalid key " + KEY))
            self.fails()
            self.assertEqual(len(self.rec.requests), 1)

    def test_content_refusal_stops_at_once(self):
        for status in (400, 403, 422):
            self.make(reply(status, {"error": {"message": "Content policy violation"}}))
            error = self.fails("portrait_service_refused")
            self.assertEqual(len(self.rec.requests), 1)
            self.assertEqual(error.attempts[0].outcome, "refused")

    def test_other_400_is_failed_not_refused(self):
        self.make(reply(400, {"error": {"message": "bad aspect ratio"}}))
        self.fails()
        self.assertEqual(len(self.rec.requests), 1)

    def test_redirect_not_followed(self):
        self.make(reply(302, headers={"Location": "https://evil.example/"}))
        self.fails()
        self.assertEqual(len(self.rec.requests), 1)

    def test_deadline_stops_retries(self):
        clock = iter([0.0, 0.0, TOTAL_DEADLINE_SECONDS + 1, TOTAL_DEADLINE_SECONDS + 1, TOTAL_DEADLINE_SECONDS + 1])
        self.make(reply(503), reply(200, ok_body(b64(PNG))), monotonic=lambda: next(clock))
        self.fails()
        self.assertEqual(len(self.rec.requests), 1)


class KeyHandling(ClientCase):
    def test_key_never_in_repr_or_logs(self):
        self.make(reply(200, ok_body(b64(PNG))))
        self.assertNotIn(KEY, repr(self.client))
        self.assertNotIn(KEY, str(self.client))
        self.make(reply(500, text=KEY), reply(500, text=KEY), reply(500, text=KEY))
        error = self.fails()
        self.assertNotIn(KEY, repr(error.attempts))

    def test_client_from_environment(self):
        with mock.patch.dict(os.environ, {pc.KEY_ENV: ""}):
            self.assertIsNone(client_from_environment())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(pc.KEY_ENV, None)
            self.assertIsNone(client_from_environment())
        with mock.patch.dict(os.environ, {pc.KEY_ENV: KEY}), \
                mock.patch("builtins.open", side_effect=AssertionError("file read")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("file read")):
            client = client_from_environment()
        self.assertIsInstance(client, PortraitClient)
        self.assertNotIn(KEY, repr(client))


if __name__ == "__main__":
    unittest.main()
