"""Pins the order and shape of the app's route table (D-531): moving routes out of create_app must not change it.

The golden list is api/tests/main_route_table.json: [path, methods, name, status_code, operation_id, include_in_schema,
repr(response_model), response_model_exclude_unset, repr(dependencies)]; main_openapi_golden.json is the full app.openapi().
A new or changed route is a deliberate edit of that file in the same commit.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("AI_DND_DISABLE_DEFAULT_APP", "1")

from api.main import create_app  # noqa: E402

GOLDEN = Path(__file__).with_name("main_route_table.json")
OPENAPI_GOLDEN = Path(__file__).with_name("main_openapi_golden.json")


class MainRouteTableTest(unittest.TestCase):
    def test_route_table_matches_golden(self) -> None:
        app = create_app(ollama_adapter=None, authenticator=None)
        rows = [
            [r.path, sorted(getattr(r, "methods", None) or []), r.name,
             getattr(r, "status_code", None), getattr(r, "operation_id", None), getattr(r, "include_in_schema", None),
             repr(getattr(r, "response_model", None)), getattr(r, "response_model_exclude_unset", None),
             repr(getattr(r, "dependencies", None))]
            for r in app.routes
        ]
        self.assertEqual(rows, json.loads(GOLDEN.read_text(encoding="utf-8")))

    def test_openapi_matches_golden(self) -> None:
        app = create_app(ollama_adapter=None, authenticator=None)
        actual = json.loads(json.dumps(app.openapi(), sort_keys=True, ensure_ascii=False))
        self.assertEqual(actual, json.loads(OPENAPI_GOLDEN.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
