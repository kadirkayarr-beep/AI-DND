"""Shared helpers for tests that run with the front reading (AI_DND_FRONT_PROPOSAL) on or off (G2.1, D-410, D-428).

One home for what several test modules had copied: telling a model call's kind by its schema, the calls a line makes
(flag on, the front reading comes first), a model that answers only the reading, and a watch over the routes the
readings took. It imports only the standard library and ``front_proposal``, so the journey runner and the
campaign API tests can both use it without an import cycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

import front_proposal


unscripted: list[str] = []  # the fake models asked for a reading nobody scripted, in order (D-410)


class UnscriptedReadingError(AssertionError):
    """A fake model was asked for the front reading and has no answer scripted for it (D-410). The engine swallows a
    failed reading (the old chain goes on), so ``forbid_unscripted`` is what makes a test fail on one."""

    def __init__(self, client: str):
        super().__init__(f"{client} was asked for the front reading and has none scripted: answer it "
                         "(test_front_proposal.FrontClient) or expect the fallback")
        unscripted.append(client)


def forbid_unscripted(test: Any) -> None:
    """Fail ``test`` when a fake model was asked for a reading nobody scripted after this call (D-410)."""
    seen = len(unscripted)
    test.addCleanup(lambda: test.assertEqual(unscripted[seen:], [], "a reading was asked of a fake that has none scripted"))


def schema_properties(schema: Any) -> Mapping[str, Any]:
    properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    return properties if isinstance(properties, Mapping) else {}


def call_kind(schema: Any) -> str | None:
    """The model call's kind, told apart by its requested schema: ``arrival`` (looked at first: its schema carries
    ``narration`` too), ``front`` (its schema also carries the classifier's fields, so it is looked at before
    ``intent``), ``intent``, ``speech``, ``steps``, ``narration``, or None for a call no scenario can script."""
    properties = schema_properties(schema)
    for key, kind in (("arrival", "arrival"), ("front", "front"), ("intent", "intent"), ("spoken_text", "speech"),
                      ("steps", "steps"), ("narration", "narration")):
        if key in properties:
            return kind
    return None


def call_kinds(schemas: list[Any]) -> list[str]:
    """Each request's kind by its response schema; a request no kind names is ``other``."""
    return [call_kind(schema) or "other" for schema in schemas]


def with_reading(*kinds: str) -> list[str]:
    """The calls a line makes: with the flag on the front reading comes first (owner rule G1, 2026-11-19: a line
    Python owns spends exactly this one call), then the line's own."""
    return (["front"] if front_proposal.enabled() else []) + list(kinds)


def intent_packet(**overrides: Any) -> dict[str, Any]:
    packet = {
        "intent": "narrative",
        "action": "",
        "target": {"type": "none", "reference": ""},
        "completion": "unclear",
        "confidence": 1.0,
    }
    packet.update(overrides)
    return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


def front_reply(front: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A usable front reading: the classifier's fields plus ``front`` (unclear unless told: a line nobody listed)."""
    body = json.loads(intent_packet()["message"]["content"])
    body["front"] = {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none", "answer": "none",
                     "inside": False, "timing": "now", **(front or {"kind": "unclear"})}
    return {"message": {"content": json.dumps(body, ensure_ascii=False)}}


def reading_only(kinds: list[str]):
    """A model that answers only the front reading (unclear, as for a line naming nobody listed); any other call fails."""
    def chat(**kwargs):
        if "front" not in kwargs["format"]["properties"]:
            raise AssertionError("no model call besides the reading")
        kinds.append("front")
        return front_reply()
    return chat


class RouteWatch:
    """The routes the front readings of a test took (``front_proposal.note``), so a test can demand that every
    reading after its set-up came back usable, not failed, invalid or unusable (D-421)."""

    def __init__(self, test: Any):
        self.routes: list[str] = []
        note = front_proposal.note
        test.enterContext(patch.object(front_proposal, "note", side_effect=lambda session, route, **kw: (
            self.routes.append(route), note(session, route, **kw))[1]))

    def reset(self) -> None:
        """Forget the routes so far: the town's set-up turns read nothing usable."""
        self.routes.clear()

    def unusable(self) -> list[str]:
        return [route for route in self.routes if route.startswith(("fallback", "skipped"))]

    def fell_back(self) -> list[str]:
        """The readings that failed, came back invalid or unusable, or had no front: the old chain read the line."""
        return [route for route in self.routes if route.startswith("fallback")]
