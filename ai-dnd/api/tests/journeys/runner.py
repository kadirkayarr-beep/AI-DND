"""The journey runner: one scenario file, played over HTTP against the real app, step by step.

Only the model is scripted (``ScriptedClient``, fed from each step's ``script``); the engine, the
adapter, the save and the turn route are the product's own. After every step the live world is read
(``read_observed``) and compared with the step's ``expect``. Each step then gets one status:

- ``pass``: no mismatch;
- ``known_broken``: marked with note item numbers and really broken (counted, not failed);
- ``marker_stale``: marked known broken but it passed (the marker must go);
- ``new_break``: not marked and broken;
- ``unreached``: not run, because an earlier step was a known break and this step is not
  ``independent``, or because it is a real-chain step and the model is scripted.
"""

from __future__ import annotations

import copy
import json
import os
import time
import unittest
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4
from unittest.mock import patch

import bold_acts
import front_proposal
import game
import local_places
import shop_trade
from api import serializers
from api.tests import test_campaign_api as fixtures
from api.tests.journeys.schema import Scenario, ScenarioError, Step, check_expect

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

Status = Literal["pass", "known_broken", "new_break", "marker_stale", "unreached"]

# ``front_proposal`` (true/false) sets the front-reading flag for the scenario's steps only; local play runs
# with it on, so a step whose script carries a ``front`` reading needs it.
#
# ``campaign_start`` is the new campaign's start (setting, region, starting town), as the create route takes it.
# ``place`` makes a new local place in the starting town and stands the player (and the scenario's people) in
# it: ``kind`` is a local place kind, ``name`` its name, ``scene_kind``/``place_kind`` optional overrides. There is
# no inn among the local place kinds; the product's own inn tests make one the same way (a place with the tavern
# scene kind).
SETUP_KEYS = frozenset({"character", "campaign_start", "place", "npcs", "currency", "inventory", "ammunition",
                        "current_hp", "seed", "front_proposal"})
PLACE_KEYS = frozenset({"kind", "name", "scene_kind", "place_kind"})
SCRIPT_KEYS = frozenset({"intent", "front", "spoken", "narration"})

_DEFAULT_NARRATION = "Etraf sakin; bir süre hiçbir şey değişmiyor."
_DEFAULT_SPOKEN = "Ne istiyorsun?"
_ECONOMIC_MESSAGES = {"prepare": "Teklif hazırla", "confirm": "Teklifi onayla", "cancel": "Teklifi iptal et"}
_COMBAT_MESSAGE = "Savaş eylemi"


@dataclass(frozen=True)
class StepResult:
    index: int
    status: Status
    failures: tuple[str, ...]
    items: tuple[int, ...]
    narration: str
    seconds: float


def _properties(schema: Any) -> Mapping[str, Any]:
    properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    return properties if isinstance(properties, Mapping) else {}


def call_kind(schema: Any) -> str | None:
    """The model call's kind, told apart by its requested schema: ``front``, ``intent``, ``speech``,
    ``steps``, ``narration``, or None for a call no scenario can script."""
    properties = _properties(schema)
    for key, kind in (("front", "front"), ("intent", "intent"), ("spoken_text", "speech"), ("steps", "steps"),
                      ("narration", "narration")):
        if key in properties:
            return kind
    return None


class NarratorInput:
    """The engine's model call for one step, wrapped: every call goes through unchanged, and the messages of
    each narrator call are kept. It sits on ``game.ollama.chat``, in front of whatever answers (the scripted
    model or the real chain), so ``anlaticiya_giden`` reads the same thing under both."""

    def __init__(self, chat: Any):
        self._chat = chat
        self._messages: list[str] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if call_kind(kwargs.get("format")) == "narration":
            self._messages = self._messages if self._messages is not None else []
            self._messages.extend(str(message.get("content", "")) for message in kwargs.get("messages") or []
                                  if isinstance(message, Mapping))
        return self._chat(*args, **kwargs)

    def text(self) -> str | None:
        """Everything the narrator was sent, one message per line; None when no narrator call was made."""
        return None if self._messages is None else "\n".join(self._messages)


class ScriptedClient(fixtures.FakeOllamaClient):
    """The model, scripted for one step. It tells the call kinds apart by the requested schema.

    ``front`` (the front reading), ``intent`` (the classifier), ``spoken_text`` (NPC speech),
    ``steps`` (grounded verbs; always answers no steps) and ``narration`` (the narrator). Any other
    request raises ``AssertionError`` and is kept in ``unexpected``, so the runner can fail the step
    even when the engine swallows the error and falls back.
    """

    def __init__(self, script: Mapping[str, Any] | None = None):
        script = dict(script or {})
        unknown = sorted(set(script) - SCRIPT_KEYS)
        if unknown:
            raise ScenarioError(
                f"bilinmeyen script anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(SCRIPT_KEYS))})"
            )
        self.script = script
        self.kinds: list[str] = []
        self.unexpected: list[list[str]] = []

    def chat(self, *args, **kwargs):
        properties = _properties(kwargs.get("format"))
        kind = call_kind(kwargs.get("format"))
        if kind == "front":
            packet = {**self._intent_packet(properties), "front": self._front()}
        elif kind == "intent":
            packet = self._intent_packet(properties)
        elif kind == "speech":
            packet = {"spoken_text": self.script.get("spoken", _DEFAULT_SPOKEN), "stage_direction": ""}
        elif kind == "steps":
            packet = {"steps": []}
        elif kind == "narration":
            packet = {"narration": self.script.get("narration", _DEFAULT_NARRATION),
                      "world_updates": {}, "lore_claims": []}
        else:
            keys = sorted(str(key) for key in properties)
            self.unexpected.append(keys)
            raise AssertionError(f"Senaryoda karşılığı olmayan model çağrısı: {keys}")
        self.kinds.append(kind)
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

    def _intent_packet(self, properties: Mapping[str, Any]) -> dict:
        intent = self.script.get("intent", "narrative")
        packet = {"intent": "narrative", "action": "narrative",
                  "target": {"type": "none", "reference": "", "npc_id": "", "evidence_quote": ""},
                  "completion": "unclear", "confidence": 1.0}
        if isinstance(intent, Mapping):
            packet.update(copy.deepcopy(dict(intent)))
        else:
            packet.update(intent=str(intent), action=str(intent))
        if "narration" in properties and "narration" in self.script and "narration" not in packet:
            packet["narration"] = self.script["narration"]
        return packet

    def _front(self) -> dict:
        return {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none",
                "answer": "none", "inside": False, "kind": "unclear",
                **copy.deepcopy(dict(self.script.get("front") or {}))}


class ModelDriver(Protocol):
    """What answers the model calls of one step. ``real_chain`` says whether real-chain steps run."""

    real_chain: bool

    def bind(self, case: "JourneyCase", step: Step) -> AbstractContextManager[Any]: ...


class ScriptedModel:
    """The default driver: a fresh ``ScriptedClient`` per step and no outside network."""

    real_chain = False

    @contextmanager
    def bind(self, case: "JourneyCase", step: Step) -> Iterator[ScriptedClient]:
        client = ScriptedClient(step.script)
        with (
            patch("socket.socket.connect",
                  side_effect=AssertionError("External network is disabled in journey tests.")),
            patch.object(case.app.state.ollama_adapter, "_client", client),
        ):
            yield client


def apply_setup(case: Any, campaign: Mapping[str, Any], setup: Mapping[str, Any]) -> None:
    """Put the scenario's starting state into the live campaign and save it (dice seeded last)."""
    unknown = sorted(str(key) for key in setup if key not in SETUP_KEYS)
    if unknown:
        raise ScenarioError(
            f"bilinmeyen setup anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(SETUP_KEYS))})"
        )
    if "front_proposal" in setup and not isinstance(setup["front_proposal"], bool):
        raise ScenarioError("setup 'front_proposal' true ya da false olmalı")
    if "campaign_start" in setup and not isinstance(setup["campaign_start"], Mapping):
        raise ScenarioError("setup 'campaign_start' bir nesne olmalı")
    session = case.manager.get(campaign["session_id"]).game_session
    world = session.world_state
    if "place" in setup:
        _stand_in_place(world, setup["place"])
    if "npcs" in setup:
        world["npcs"] = [{"location": world["location"], **copy.deepcopy(npc)} for npc in setup["npcs"]]
    for key in ("currency", "inventory", "ammunition"):
        if key in setup:
            world[key] = copy.deepcopy(setup[key])
    if "current_hp" in setup:
        session.character.update(current_hp=setup["current_hp"])
    if "seed" in setup:
        session.rng.seed(setup["seed"])
    case.manager.save_campaign(campaign["campaign_id"])


def _stand_in_place(world: dict[str, Any], place: Any) -> None:
    """A new local place in the town the player stands in; the player is then inside it."""
    if not isinstance(place, Mapping):
        raise ScenarioError("setup 'place' bir nesne olmalı")
    unknown = sorted(str(key) for key in place if key not in PLACE_KEYS)
    if unknown:
        raise ScenarioError(
            f"bilinmeyen place anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(PLACE_KEYS))})"
        )
    kind, name = place.get("kind"), place.get("name")
    if kind not in local_places.PLACE_KINDS:
        raise ScenarioError(f"setup 'place.kind' bilinen bir yer türü değil: {kind} "
                            f"(izinli: {', '.join(sorted(local_places.PLACE_KINDS))})")
    if not isinstance(name, str) or not name:
        raise ScenarioError("setup 'place.name' boş olmayan bir metin olmalı")
    record = local_places.create_local_place(world, world["location"], kind, name=name)
    if record is None:
        raise ScenarioError(f"setup 'place' kurulamadı: {name}")
    record.update({key: place[key] for key in ("scene_kind", "place_kind") if key in place})
    world["location"] = record["id"]


def read_observed(case: Any, session_id: str) -> dict[str, Any]:
    """What a step can expect, read from the live session (the save copy's public projection for the
    conversation, the card and death; the live world for the rest).

    ``kart`` is the economic card; ``tezgah`` is the counter's offer that a spoken order opens (settled
    only by the counter trade, never by the card); ``kisi_kese`` is every purse but the player's."""
    session = case.manager.get(session_id).game_session
    world = session.world_state
    state = serializers.serialize_session_state(session)
    flags = world.get("flags") if isinstance(world.get("flags"), dict) else {}
    combat = world.get("combat") if isinstance(world.get("combat"), dict) else {}
    offer = state.get("economic_offer")
    currency = world.get("currency") if isinstance(world.get("currency"), dict) else {}
    return {
        "kese": currency.get("player"),
        "envanter": _inventory_counts(world.get("inventory") or []),
        "oda": bool(flags.get("inn_room")),
        "kip": copy.deepcopy(state.get("conversation")),
        "savas": bool(combat.get("active")),
        "konum": world.get("location"),
        "hp": session.character.get("current_hp"),
        "kart": None if offer is None else {"max_total_cp": offer.get("max_total_cp"),
                                            "counterparty_label": offer.get("counterparty_label")},
        "tezgah": _counter_offer(world),
        "kisi_kese": {str(owner): cp for owner, cp in currency.items() if owner != "player"},
        "olu": (state.get("death_state") or {}).get("status"),
        "narration": getattr(case, "last_narration", ""),
        "anlaticiya_giden": getattr(case, "last_narrator_input", None),
    }


def _counter_offer(world: dict[str, Any]) -> dict[str, Any] | None:
    """The counter's offer while it still stands (the product's own test: same person, no trade settled since,
    within its turns), with the unit price the counter quotes now; None otherwise."""
    opened = (world.get("flags") or {}).get("counter_offer_v1")
    if not isinstance(opened, dict):
        return None
    npc = next((npc for npc in world.get("npcs") or []
                if isinstance(npc, dict) and npc.get("id") == opened.get("npc_id")), None)
    if bold_acts.offer_still_open(world, npc) is None:
        return None
    quoted = shop_trade.quote(world, str(opened.get("npc_id")), str(opened.get("key")), 1)
    return {"npc_id": opened.get("npc_id"), "key": opened.get("key"),
            "unit_cp": None if quoted is None else quoted["unit_cp"]}


def _inventory_counts(inventory: Sequence[Any]) -> dict[str, int]:
    """Name to count. Items are separate records (no stacks), so each one counts once."""
    counts: dict[str, int] = {}
    for item in inventory:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str):
            counts[name] = counts.get(name, 0) + 1
    return counts


class JourneyCase(unittest.IsolatedAsyncioTestCase):
    """The real app on a temporary campaign store, as in the campaign API tests."""

    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    # Set by run_scenario: the last step's narration and what its narrator calls were sent (None: no narrator
    # call), every step's observation, the session played.
    last_narration: str = ""
    last_narrator_input: str | None = None
    last_observations: list[dict[str, Any]]
    last_session_id: str | None = None

    async def run_scenario(self, scenario: Scenario, *, model: ModelDriver | None = None) -> list[StepResult]:
        model = model if model is not None else ScriptedModel()
        campaign = await self._journey_campaign(scenario.setup)
        apply_setup(self, campaign, scenario.setup)
        session_id = campaign["session_id"]
        self.last_session_id = session_id
        self.last_narration = ""
        self.last_narrator_input = None
        self.last_observations = []
        with _front_setting(scenario.setup):
            return await self._run_steps(scenario, session_id, model)

    async def _run_steps(self, scenario: Scenario, session_id: str, model: ModelDriver) -> list[StepResult]:
        results: list[StepResult] = []
        blocked_by: int | None = None
        for index, step in enumerate(scenario.steps, start=1):
            if blocked_by is not None and not step.independent:
                results.append(StepResult(index, "unreached",
                                          (f"adım {blocked_by} bilinen kırık; bu adım koşulmadı",),
                                          step.known_broken, "", 0.0))
                continue
            if step.real_chain and not model.real_chain:
                results.append(StepResult(index, "unreached",
                                          ("gerçek zincir adımı; sahte modelde koşulmadı",),
                                          step.known_broken, "", 0.0))
                continue
            started = time.monotonic()
            failures = await self._play(session_id, step, model)
            observed = read_observed(self, session_id)
            self.last_observations.append(observed)
            failures.extend(check_expect(step.expect, observed))
            status = _status(step, failures)
            if status == "known_broken":
                blocked_by = index
            results.append(StepResult(index, status, tuple(failures), step.known_broken,
                                      self.last_narration, time.monotonic() - started))
        return results

    async def _journey_campaign(self, setup: Mapping[str, Any]) -> dict:
        if "character" not in setup and "campaign_start" not in setup:
            return await self.create_campaign()
        body: dict[str, Any] = {"death_mode": "NORMAL"}
        for key in ("character", "campaign_start"):
            if key in setup:
                body[key] = setup[key]
        response = await self.http.post("/api/game/campaigns", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def _play(self, session_id: str, step: Step, model: ModelDriver) -> list[str]:
        """Send the step's one action; return the failures the action itself produced."""
        failures: list[str] = []
        body = self._body(session_id, step)
        with model.bind(self, step) as client:
            told = NarratorInput(game.ollama.chat)
            with patch.object(game.ollama, "chat", told):
                response = await self.http.post(f"/api/game/sessions/{session_id}/turn", json=body)
        self.last_narrator_input = told.text()
        unexpected = getattr(client, "unexpected", None) or []
        failures.extend(f"beklenmeyen model çağrısı: {keys}" for keys in unexpected)
        if response.status_code != 200:
            self.last_narration = ""
            failures.append(f"HTTP {response.status_code}: {response.text[:300]}")
        else:
            self.last_narration = str(response.json().get("narration") or "")
        return failures

    def _body(self, session_id: str, step: Step) -> dict[str, Any]:
        body: dict[str, Any] = {"action_id": str(uuid4())}
        if step.say is not None:
            body["message"] = step.say
        elif step.command is not None:
            body["message"] = step.command
        elif step.economic_action is not None:
            action = copy.deepcopy(step.economic_action)
            kind = action.get("kind")
            if kind in {"confirm", "cancel"} and "offer_id" not in action:
                card = serializers.serialize_session_state(
                    self.manager.get(session_id).game_session).get("economic_offer") or {}
                action["offer_id"] = card.get("offer_id")
                if kind == "confirm" and "confirmation_digest" not in action:
                    action["confirmation_digest"] = card.get("confirmation_digest")
            body.update(message=_ECONOMIC_MESSAGES.get(kind, "Teklif"), economic_action=action)
        else:
            body.update(message=_COMBAT_MESSAGE, combat_action=copy.deepcopy(step.combat_action))
        combat = self.manager.get(session_id).game_session.world_state.get("combat") or {}
        if combat.get("active") and step.economic_action is None:
            body.update(combat_id=combat.get("combat_id"), combat_round=combat.get("round"),
                        combat_turn_index=combat.get("current_turn_index"))
        return body


def _front_setting(setup: Mapping[str, Any]) -> AbstractContextManager[Any]:
    """The front-reading flag as the scenario sets it, restored afterwards; untouched when it says nothing."""
    if "front_proposal" not in setup:
        return nullcontext()
    return patch.dict(os.environ, {front_proposal.FLAG: "1" if setup["front_proposal"] else "0"})


def _status(step: Step, failures: Sequence[str]) -> Status:
    if step.known_broken:
        return "known_broken" if failures else "marker_stale"
    return "new_break" if failures else "pass"


def describe_problems(results: Sequence[StepResult]) -> list[str]:
    """One Turkish line per step that must fail the suite (a new break or a stale marker)."""
    lines = []
    for result in results:
        if result.status == "new_break":
            lines.append(f"adım {result.index}: YENİ KIRIK: " + "; ".join(result.failures))
        elif result.status == "marker_stale":
            lines.append(f"adım {result.index}: geçti ama bilinen kırık işaretli "
                         f"{list(result.items)}; işareti kaldır")
    return lines


def summary_line(results: Mapping[str, Sequence[StepResult]]) -> str:
    """Scenario counts: a scenario with any new break is a new break, else any known break makes it
    known broken, else it passed. Stale markers are counted on their own."""
    passed = known = new = 0
    stale = 0
    for steps in results.values():
        statuses = {result.status for result in steps}
        stale += sum(result.status == "marker_stale" for result in steps)
        if "new_break" in statuses:
            new += 1
        elif "known_broken" in statuses:
            known += 1
        else:
            passed += 1
    line = f"{passed} geçti, {known} bilinen kırık, {new} yeni kırık"
    return line + (f" ({stale} adımda işaret kaldırılmalı)" if stale else "")
