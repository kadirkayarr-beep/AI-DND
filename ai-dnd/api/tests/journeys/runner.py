"""The journey runner: one scenario file, played over HTTP against the real app, step by step.

Only the model is scripted (``ScriptedClient``, fed from each step's ``script``); the engine, the
adapter, the save and the turn route are the product's own. After every step the live world is read
(``read_observed``) and compared with the step's ``expect``. An ``undo`` step takes back the last turn through
the product's undo route; a ``reload`` step reads the campaign back from its save in a fresh session manager
and fails on any observed key where the save and the live game differ. Each step then gets one status:

- ``pass``: no mismatch;
- ``known_broken``: marked with note item numbers and really broken for the marker's own reason (every failure holds
  one of the step's ``broken_because`` substrings); counted, not failed;
- ``marker_stale``: marked known broken but it passed (the marker must go);
- ``new_break``: not marked and broken, or marked but broken for another reason (a failure the marker does not name, a
  server error, an unexpected model call, a reload that differs from the live game: those are never a known break);
- ``unreached``: not run, because an earlier step was a known break and this step is not
  ``independent``, or because it is a real-chain step and the model is scripted.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
import unittest
import httpx
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Protocol
from uuid import uuid4
from unittest.mock import patch

import ambient_event_catalog
import bold_acts
import equipment_economy
import front_proposal
import game
import interaction_adventure
import living_world
import local_places
import shop_trade
import world_threads
from api import serializers
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.journeys.schema import Scenario, ScenarioError, Step, check_expect, check_invariant, check_start_hour

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

Status = Literal["pass", "known_broken", "new_break", "marker_stale", "unreached"]

# ``front_proposal`` (true/false) sets the front-reading flag for the scenario's steps only; local play runs
# with it on, so a step whose script carries a ``front`` reading needs it.
#
# ``campaign_start`` is the new campaign's start (setting, region, starting town), as the create route takes it.
# ``place`` makes a new local place in the starting town and stands the player (and the scenario's people) in
# it: ``kind`` is a local place kind, ``name`` its name, ``scene_kind``/``place_kind`` optional overrides. There is
# no inn among the local place kinds; the product's own inn tests make one the same way (a place with the tavern
# scene kind). ``no_exit`` (true) leaves the place without a way out (no parent, no exit), as the product's own
# flight tests make one.
#
# ``death_mode`` is the new campaign's death mode (``game.DEATH_MODES``). The journeys default to the old NORMAL
# mode, which rewinds a death in a fight; a new campaign in the product dies for real (PERMADEATH).
#
# ``job`` gives one of the scenario's people a town job where the player stands, built the way the product's own job
# tests build one (a seeded thread of the town, rewritten): ``type`` hiring (worked on the spot, paid at the end of
# the day) or errand (a parcel carried to ``recipient`` in a new ``target_kind`` place of the town); ``owner`` the
# person's id; ``status`` offered or accepted (hiring only: an errand is accepted by a step, which puts the parcel in
# hand); ``pay`` in copper; ``line`` what the owner said; ``work_days`` (hiring), ``noun`` (errand).
#
# ``letter`` (with an errand ``job``) is a second errand: a sealed letter (``line`` speaks of the seal) that one of the
# scenario's people (``owner``, whose own place is another place of the town, standing at the job's target place)
# offers there, for ``recipient`` in a
# ``target_kind`` place of the town; a trouble of the town is opened at that place by the product's own opener, so the
# letter, once read, points at something real. It is taken by a step (one town job at a time: after the first is done).
#
# ``ambient_event`` puts one catalog event into the scene the player stands in, written the way the product's own
# scene writers write it: ``event_id`` a catalog id, ``turns_ago`` (0 or more) how long ago it was shown (13 or more:
# its referent has run out, as the click route counts a referent's twelve turns). ``campaign_seed`` (a positive whole
# number) fixes the new campaign's id, and so the campaign seed its town is drawn from (its jobs, places and their
# papers); ``seed`` seeds only the dice. ``start_hour`` (0-23) sets the hour of the day the new campaign's clock
# starts at (after the campaign is made, so the seeded start hour is overwritten). ``xp`` (a whole number, 0 or more)
# is the made character's experience total; it may not reach a level the character does not have yet (no level-up
# hidden in the setup: the scenario earns it in play).
SETUP_KEYS = frozenset({"character", "campaign_start", "place", "npcs", "currency", "inventory", "ammunition",
                        "current_hp", "seed", "front_proposal", "death_mode", "job", "letter", "room",
                        "ambient_event", "campaign_seed", "start_hour", "xp"})
AMBIENT_EVENT_KEYS = frozenset({"event_id", "turns_ago"})
PLACE_KEYS = frozenset({"kind", "name", "scene_kind", "place_kind", "no_exit"})
JOB_KEYS = frozenset({"type", "owner", "status", "pay", "line", "work_days", "noun", "recipient", "target_kind"})
LETTER_KEYS = frozenset({"owner", "pay", "line", "noun", "recipient", "target_kind"})
# An expected ``konum`` naming the setup errand's target place (see ``_with_job_target``).
JOB_TARGET = "$is_hedefi"
# An expected ``konum`` of ``$kurulum_yeri`` is the place the setup stood the player in: a new campaign's town work
# opens places first (Task 18), so the place's number is the engine's, never the scenario's.
SETUP_PLACE = "$kurulum_yeri"
SCRIPT_KEYS = frozenset({"intent", "front", "fronts", "spoken", "narration", "speech", "arrival"})
# ``fronts``: a list of front readings, one for each front-reading call of the step in turn (the last one stays for
# any call after it); a line that walks and then asks reads twice. ``front`` is the same reading for every call.
# A front reading's ``place_id`` (and a setup person's ``location``/``place_role_of``) of ``$yer:KIND`` is the place of
# that scene kind (tavern, temple, ...) in the town the scenario started in: a seeded town's places are numbered by
# the engine, never by the scenario. A kind the town lacks is made (a local place kind) at setup.
TOWN_PLACE = "$yer:"
# ``arrival``: the model's arrival text (a str), or a whole packet ({narration, world_updates, lore_claims}) returned as
# written, so a scenario can try a broken one. A step that scripts none leaves the arrival call to fail (the Python line).
# ``speech``: the speech answer's own optional fields, added to the speech call's answer as written (a broken value
# too, so a scenario can try a missing or broken answer). ``spoken`` stays the spoken line.
SPEECH_SCRIPT_KEYS = frozenset({"coin_answer", "coin_answer_for", "remember_player_line", "asks_for",
                                 "stage_direction"})

_DEFAULT_NARRATION = "Etraf sakin; bir süre hiçbir şey değişmiyor."
_DEFAULT_SPOKEN = "Ne istiyorsun?"
_ECONOMIC_MESSAGES = {"prepare": "Teklif hazırla", "confirm": "Teklifi onayla", "cancel": "Teklifi iptal et"}
_COMBAT_MESSAGE = "Savaş eylemi"
# Step-bound, not state: what the step said, what the narrator and the speech call were sent, whether a stock denial
# was said and the step's counter-attacks. A reload compares everything else.
_NOT_STATE = frozenset({"narration", "anlaticiya_giden", "karsi_saldiri", "konusmaya_giden", "inkar", "ambient", "varis"})
# An enemy's counter-attack in a turn's combat result: a swing that hit or missed (the engine's own exchange text
# says "karşı saldırısı" for exactly these).
_SWINGS = frozenset({"hit", "miss", "critical_hit"})
_ACTIVE_QUEST = frozenset({"ACTIVE", "accepted"})
_HOUR = 3600
_DAY = 24 * _HOUR
# The failure of a real-chain step under the scripted model (it waits for the real chain, not for a fix).
REAL_CHAIN_ONLY = "gerçek zincir adımı; sahte modelde koşulmadı"
# Failures no known-broken marker may stand for (Ruling R19): a server error, a model call no scenario scripts, and a
# reload that read something else back from the save than the live game held.
_ALWAYS_NEW = re.compile(r"^(HTTP 5\d\d\b|beklenmeyen model çağrısı|yenileme:)")


@dataclass(frozen=True)
class StepResult:
    index: int
    status: Status
    failures: tuple[str, ...]
    items: tuple[int, ...]
    narration: str
    seconds: float
    reading: str = ""  # what the model's front reading / classifier answered this step (the report's raw log)
    # What ``varis`` observed after the step ({cagri, kaynak, neden}); the real-chain report lists it for every run.
    varis: Mapping[str, Any] | None = None


def _properties(schema: Any) -> Mapping[str, Any]:
    properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    return properties if isinstance(properties, Mapping) else {}


def call_kind(schema: Any) -> str | None:
    """The model call's kind, told apart by its requested schema: ``arrival`` (looked at first: its schema carries
    ``narration`` too), ``front``, ``intent``, ``speech``, ``steps``, ``narration``, or None for a call no scenario
    can script."""
    properties = _properties(schema)
    for key, kind in (("arrival", "arrival"), ("front", "front"), ("intent", "intent"), ("spoken_text", "speech"), ("steps", "steps"),
                      ("narration", "narration")):
        if key in properties:
            return kind
    return None


class NarratorInput:
    """The engine's model call for one step, wrapped: every call goes through unchanged, and the messages of
    each narrator call are kept, and apart from them the messages of the last speech call. It sits on
    ``game.ollama.chat``, in front of whatever answers (the scripted model or the real chain), so
    ``anlaticiya_giden`` and ``konusmaya_giden`` read the same thing under both."""

    def __init__(self, chat: Any):
        self._chat = chat
        self._messages: list[str] | None = None
        self._speech: list[str] | None = None
        self._readings: list[str] = []
        self._arrivals = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        kind = call_kind(kwargs.get("format"))
        if kind == "narration":
            self._messages = self._messages if self._messages is not None else []
            self._messages.extend(_message_texts(kwargs.get("messages")))
        elif kind == "speech":
            self._speech = _message_texts(kwargs.get("messages"))
        elif kind == "arrival":
            self._arrivals += 1
        reply = self._chat(*args, **kwargs)
        if kind in ("front", "intent"):
            try:
                self._readings.append(str(reply["message"]["content"]))
            except (KeyError, TypeError, IndexError):
                pass
        return reply

    def reading(self) -> str:
        """What the front reading and the classifier answered this step, in call order; "" when neither ran."""
        return " | ".join(self._readings)

    def arrival_calls(self) -> int:
        """How many arrival narration calls were made this step (their messages are not the narrator's input)."""
        return self._arrivals

    def text(self) -> str | None:
        """Everything the narrator was sent, one message per line; None when no narrator call was made."""
        return None if self._messages is None else "\n".join(self._messages)

    def speech_messages(self) -> list[str] | None:
        """Every message text of the step's last speech call (a copy); None when no speech call was made."""
        return None if self._speech is None else list(self._speech)


def _message_texts(messages: Any) -> list[str]:
    return [str(message.get("content", "")) for message in messages or [] if isinstance(message, Mapping)]


class ScriptedClient(fixtures.FakeOllamaClient):
    """The model, scripted for one step. It tells the call kinds apart by the requested schema.

    ``front`` (the front reading), ``intent`` (the classifier), ``spoken_text`` (NPC speech, with the script's
    ``speech`` fields added as written),
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
        speech = script.get("speech", {})
        if not isinstance(speech, Mapping):
            raise ScenarioError(f"script 'speech' bir nesne olmalı, bulunan: {speech!r}")
        unknown = sorted(str(key) for key in speech if key not in SPEECH_SCRIPT_KEYS)
        if unknown:
            raise ScenarioError(f"bilinmeyen script speech anahtarı: {', '.join(unknown)} "
                                f"(izinli: {', '.join(sorted(SPEECH_SCRIPT_KEYS))})")
        self.script = script
        self.front_reads = 0
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
            packet = {"spoken_text": self.script.get("spoken", _DEFAULT_SPOKEN), "stage_direction": "",
                      **copy.deepcopy(dict(self.script.get("speech") or {}))}
        elif kind == "steps":
            packet = {"steps": []}
        elif kind == "narration":
            packet = {"narration": self.script.get("narration", _DEFAULT_NARRATION),
                      "world_updates": {}, "lore_claims": []}
        elif kind == "arrival":
            if "arrival" not in self.script:
                # An unwritten arrival is a model failure (the engine's Python line stands), not an unexpected call.
                self.kinds.append("arrival_unscripted")
                raise RuntimeError("varış yazılmadı")
            written = self.script["arrival"]
            packet = (copy.deepcopy(dict(written)) if isinstance(written, Mapping)
                      else {"narration": written, "world_updates": {}, "lore_claims": []})
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
        readings = self.script.get("fronts")
        if readings:
            reading = readings[min(self.front_reads, len(readings) - 1)]
            self.front_reads += 1
        else:
            reading = self.script.get("front")
        return {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none",
                "answer": "none", "inside": False, "kind": "unclear", **copy.deepcopy(dict(reading or {}))}


class ModelDriver(Protocol):
    """What answers the model calls of one step. ``real_chain`` says whether real-chain steps run."""

    real_chain: bool

    def bind(self, case: "JourneyCase", step: Step) -> AbstractContextManager[Any]: ...


class ScriptedModel:
    """The default driver: a fresh ``ScriptedClient`` per step and no outside network. A front reading's
    ``item_name`` is turned here, from the live bag, into the ``item_id`` the reading names (see ``_bag_id``)."""

    real_chain = False

    @contextmanager
    def bind(self, case: "JourneyCase", step: Step) -> Iterator[ScriptedClient]:
        client = ScriptedClient(_with_town_places(case, _with_price_offer_ids(
            case, _with_live_ids(case, _with_bag_ids(case, step.script)))))
        with (
            patch("socket.socket.connect",
                  side_effect=AssertionError("External network is disabled in journey tests.")),
            patch.object(case.app.state.ollama_adapter, "_client", client),
        ):
            yield client


def _town_place(session: Any, town: str, kind: str) -> str:
    """The first place of the scene or place kind ``kind`` in the town ``town`` (a place whose parent it is); made
    when the town has none: the inn by the product's own inn maker (``game._ensure_local_tavern``, the one a spoken
    "han" reaches), any other kind as a local place kind."""
    world = session.world_state

    def found() -> str | None:
        return next((key for key, record in world.get("locations", {}).items()
                     if isinstance(record, Mapping) and record.get("parent_location_id") == town
                     and kind in (living_world.scene_kind(world, key), record.get("place_kind"))), None)

    if (place := found()) is not None:
        return place
    if kind == "tavern":
        token = game._ACTIVE_SESSION.set(session)
        try:
            record = game._ensure_local_tavern(town)
        finally:
            game._ACTIVE_SESSION.reset(token)
    elif kind in local_places.PLACE_KINDS:
        record = local_places.create_local_place(world, town, kind)
    else:
        raise ScenarioError(f"'{TOWN_PLACE}{kind}': kasabada böyle bir yer yok ve yeri kurulamaz")
    if record is None:
        raise ScenarioError(f"'{TOWN_PLACE}{kind}': yer kurulamadı")
    return record["id"]


def _resolved_place(case: Any, value: Any) -> Any:
    if not (isinstance(value, str) and value.startswith(TOWN_PLACE)):
        return value
    session = case.manager.get(case.last_session_id).game_session
    return _town_place(session, case.setup_town_id, value[len(TOWN_PLACE):])


def _with_town_places(case: Any, script: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The step's script with every front reading's ``$yer:KIND`` place turned into that place of the setup town."""
    readings = [(script or {}).get("front"), *((script or {}).get("fronts") or [])]
    if not any(isinstance(reading, Mapping) and str(reading.get("place_id", "")).startswith(TOWN_PLACE)
               for reading in readings):
        return script

    def fixed(reading: Any) -> Any:
        return {**reading, "place_id": _resolved_place(case, reading["place_id"])} if isinstance(reading, Mapping)             and "place_id" in reading else reading

    out = dict(script)
    if "front" in out:
        out["front"] = fixed(out["front"])
    if "fronts" in out:
        out["fronts"] = [fixed(reading) for reading in out["fronts"]]
    return out


def _with_price_offer_ids(case: Any, script: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Resolve an explicit scripted $room:NPC/$goods:NPC selector to the live opaque offer id."""
    intent = (script or {}).get("intent")
    value = intent.get("price_negotiation") if isinstance(intent, Mapping) else None
    offer_id = value.get("offer_id") if isinstance(value, Mapping) else None
    if not isinstance(offer_id, str) or not offer_id.startswith(("$room:", "$goods:")):
        return script
    import money_owner
    kind, npc_id = offer_id[1:].split(":", 1)
    world = case.manager.get(case.last_session_id).game_session.world_state
    found = [row for row in money_owner.price_negotiation_offers(world)
             if row["kind"] == kind and row["npc_id"] == npc_id]
    if len(found) != 1:
        raise ScenarioError("Scripted price negotiation must name exactly one current offer")
    return {**script, "intent": {**intent, "price_negotiation": {**value, "offer_id": found[0]["offer_id"]}}}

def _with_bag_ids(case: Any, script: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The step's script with its front reading's ``item_name`` turned into that reading's ``item_id`` (the step's
    own script is left as written)."""
    front = (script or {}).get("front")
    if not isinstance(front, Mapping) or "item_name" not in front:
        return script
    world = case.manager.get(case.last_session_id).game_session.world_state
    reading = {key: value for key, value in front.items() if key != "item_name"}
    reading["item_id"] = _bag_id(world, front["item_name"])
    return {**script, "front": reading}


def _with_job_target(case: Any, expect: Mapping[str, Any], session_id: str) -> Mapping[str, Any]:
    """An expected ``konum`` of ``$is_hedefi`` is the target place of the setup's errand, read from the live world (a
    town's places are numbered as the campaign's seed made them, so the id is the engine's, never the scenario's)."""
    place = expect.get("konum")
    if isinstance(place, str) and place.startswith(TOWN_PLACE):
        return {**expect, "konum": _resolved_place(case, place)}
    if expect.get("konum") == SETUP_PLACE:
        if getattr(case, "setup_place_id", None) is None:
            raise ScenarioError(f"'{SETUP_PLACE}': kurulumda bir yer (setup 'place') yok")
        return {**expect, "konum": case.setup_place_id}
    if expect.get("konum") != JOB_TARGET:
        return expect
    world = case.manager.get(session_id).game_session.world_state
    thread = world_threads.by_id(world, getattr(case, "setup_job_id", None))
    if thread is None or not thread.get("target_place_id"):
        raise ScenarioError(f"'{JOB_TARGET}': kurulumda hedef yeri olan bir iş yok")
    return {**expect, "konum": thread["target_place_id"]}


def _with_live_ids(case: Any, script: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """A front reading's ``place_id`` ``$iz:N`` turned into the place of the record the N-th trail of the quest log
    points at (1 = the newest), and its ``offer_id`` ``$is:PERSON`` into the one job that person has on offer, both
    read from the live world: a trail's place and a job's id are the engine's, never the scenario's."""
    front = (script or {}).get("front")
    offer = front.get("offer_id") if isinstance(front, Mapping) else None
    if isinstance(offer, str) and offer.startswith("$is:"):  # the one job this person has on offer
        world = case.manager.get(case.last_session_id).game_session.world_state
        found = [t["thread_id"] for t in (world_threads.view(world) or {}).get("threads", [])
                 if t.get("status") == "offered" and t.get("owner_npc_id") == offer[4:]]
        if len(found) != 1:
            raise ScenarioError(f"'{offer}': o kişinin tam bir açık teklifi olmalı ({len(found)} var)")
        front = {**front, "offer_id": found[0]}
        script = {**script, "front": front}
    place = front.get("place_id") if isinstance(front, Mapping) else None
    if not isinstance(place, str) or not place.startswith("$iz:"):
        return script
    import quest_log
    world = case.manager.get(case.last_session_id).game_session.world_state
    rows = quest_log._trail_rows(world)
    number = int(place[4:]) if place[4:].isdigit() else 0
    if not 1 <= number <= len(rows):
        raise ScenarioError(f"'{place}': günlükte o sırada bir iz yok ({len(rows)} iz var)")
    record = world_threads.by_id(world, rows[number - 1]["_to_thread_id"])
    return {**script, "front": {**front, "place_id": record["place_id"]}}


def _bag_id(world: Mapping[str, Any], name: Any) -> str:
    """The ``item_id`` of the first record in the live bag that bears this name; ``none`` when no record does."""
    return next((item["item_id"] for item in world.get("inventory") or []
                 if isinstance(item, Mapping) and item.get("name") == name and isinstance(item.get("item_id"), str)),
                "none")


def apply_setup(case: Any, campaign: Mapping[str, Any], setup: Mapping[str, Any]) -> None:
    """Put the scenario's starting state into the live campaign and save it (dice seeded last). The inventory is
    made into item records with ids (``equipment_economy.materialize``), as the counter hands goods out in play."""
    unknown = sorted(str(key) for key in setup if key not in SETUP_KEYS)
    if unknown:
        raise ScenarioError(
            f"bilinmeyen setup anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(SETUP_KEYS))})"
        )
    if "front_proposal" in setup and not isinstance(setup["front_proposal"], bool):
        raise ScenarioError("setup 'front_proposal' true ya da false olmalı")
    if "campaign_start" in setup and not isinstance(setup["campaign_start"], Mapping):
        raise ScenarioError("setup 'campaign_start' bir nesne olmalı")
    if "start_hour" in setup:
        check_start_hour(setup["start_hour"])
    session = case.manager.get(campaign["session_id"]).game_session
    world = session.world_state
    if "start_hour" in setup:
        world["campaign_time"]["start_second"] = setup["start_hour"] * 3600
    case.setup_place_id = None
    case.setup_town_id = world["location"]
    if "place" in setup:
        _stand_in_place(world, setup["place"])
        case.setup_place_id = world["location"]
    if "npcs" in setup:
        world["npcs"] = [{"location": world["location"], **copy.deepcopy(npc)} for npc in setup["npcs"]]
        for npc in world["npcs"]:
            for key in ("location", "place_role_of"):
                value = npc.get(key)
                if isinstance(value, str) and value.startswith(TOWN_PLACE):
                    npc[key] = _town_place(session, case.setup_town_id, value[len(TOWN_PLACE):])
    for key in ("currency", "inventory", "ammunition"):
        if key in setup:
            world[key] = copy.deepcopy(setup[key])
    if "inventory" in setup:
        equipment_economy.materialize(world)
        _hands_hold_only_the_bag(world)
    if "current_hp" in setup:
        session.character.update(current_hp=setup["current_hp"])
    if "xp" in setup:
        import xp
        total = setup["xp"]
        if type(total) is not int or total < 0 or xp.level_for_xp(total) > session.character.get("level", 1):
            raise ScenarioError("setup 'xp' 0 ya da daha büyük bir tam sayı olmalı ve karakterin seviyesini aşmamalı")
        session.character["xp"] = total
    case.setup_job_id = None
    if "job" in setup:
        case.setup_job_id = _give_job(world, setup["job"])
    if "letter" in setup:
        _give_letter(world, setup["letter"])
    if setup.get("room") is True:  # an inn room already held here for a day (what a confirmed room card leaves)
        import bold_acts
        now = world.get("campaign_time", {}).get("elapsed_seconds", 0)
        world["flags"]["inn_room"] = {"place": world["location"], "until": now + bold_acts._ROOM_DAY}
    if "ambient_event" in setup:
        _place_ambient_event(world, setup["ambient_event"])
    if "seed" in setup:
        session.rng.seed(setup["seed"])
    case.manager.save_campaign(campaign["campaign_id"])


def _place_ambient_event(world: dict[str, Any], spec: Any) -> None:
    """Put one catalog event into the scene the player stands in: the scene's ``ambient_event``, the repetition
    history and count, and (for a BLUE event) the referent, as ``living_world`` writes them. ``turns_ago`` moves
    the referent's last turn to ``turn_index - turns_ago + 12``."""
    if not (isinstance(spec, Mapping) and set(spec) == AMBIENT_EVENT_KEYS):
        raise ScenarioError("setup 'ambient_event' {event_id, turns_ago} nesnesi olmalı")
    turns_ago = spec["turns_ago"]
    if type(turns_ago) is not int or turns_ago < 0:
        raise ScenarioError("setup 'ambient_event' 'turns_ago' 0 ya da daha büyük tam sayı olmalı")
    event = next((item for item in ambient_event_catalog.EVENT_CATALOG if item["event_id"] == spec["event_id"]), None)
    if event is None:
        raise ScenarioError(f"setup 'ambient_event' katalogda olmayan bir olay: {spec['event_id']!r}")
    location = world["location"]
    turn = world.setdefault("flags", {}).setdefault("turn_index", 0)
    scene = living_world.ensure_scene_record(world, location, turn)
    scene["materialized"] = True
    scene["referents"].clear()
    scene.pop("ambient_event", None)  # the opening's own happening (Task 18) gives way to the scenario's
    state = living_world.ensure_scene_state(world)
    count = state["ambient_event_counts"].get(event["event_id"], 0) + 1
    state["ambient_event_counts"][event["event_id"]] = count
    instance = str(uuid4())
    state["ambient_event_history"].append({
        "event_id": event["event_id"], "instance_id": instance, "variation_id": event["variation_id"],
        "repeat_group": event["repeat_group"], "location_id": location, "turn_index": turn,
        "last_seen_turn": turn, "count": count,
    })
    record = {"event_id": event["event_id"], "instance_id": instance, "variation_id": event["variation_id"],
              "event_type": event["event_type"], "repeat_group": event["repeat_group"], "count": count}
    scene["last_beat"] = event["text"]
    if event["event_type"] == "BLUE":
        referent = living_world.create_scene_referent(world, location, turn, description=event["text"],
                                                      aliases=list(event["aliases"]), event_instance_id=instance)
        referent["expires_after_turn"] = turn - turns_ago + 12
        record["referent_id"] = referent["id"]
    scene["ambient_event"] = record


def _hands_hold_only_the_bag(world: dict[str, Any]) -> None:
    """The setup's bag is all the player has: a hand still naming a thing the bag does not hold holds nothing (a
    hand nothing can resolve makes every item transfer out of the player's bag refuse)."""
    hands = world.get("equipment")
    if not isinstance(hands, dict):
        return
    for hand, held in hands.items():
        if held is None:
            continue
        try:
            equipment_economy.canonical_hands(world, "player", {"equipment": {"main_hand": held, "off_hand": None}})
        except equipment_economy.EquipmentError:
            hands[hand] = None


def _give_job(world: dict[str, Any], job: Any) -> str:
    """One town job for one of the scenario's people, where the player stands (see ``SETUP_KEYS``); its thread id."""
    if not isinstance(job, Mapping):
        raise ScenarioError("setup 'job' bir nesne olmalı")
    unknown = sorted(str(key) for key in job if key not in JOB_KEYS)
    if unknown:
        raise ScenarioError(
            f"bilinmeyen job anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(JOB_KEYS))})"
        )
    kind, status, pay, line = job.get("type"), job.get("status"), job.get("pay"), job.get("line")
    if kind not in {"hiring", "errand"}:
        raise ScenarioError(f"setup 'job.type' hiring ya da errand olmalı: {kind}")
    if status not in ({"offered", "accepted"} if kind == "hiring" else {"offered"}):
        raise ScenarioError(f"setup 'job.status' bu iş türünde olamaz: {status}")
    if isinstance(pay, bool) or not isinstance(pay, int) or pay <= 0:
        raise ScenarioError("setup 'job.pay' pozitif bir tam sayı olmalı")
    if not isinstance(line, str) or not line:
        raise ScenarioError("setup 'job.line' boş olmayan bir metin olmalı")
    owner = next((npc for npc in world.get("npcs") or [] if npc.get("id") == job.get("owner")), None)
    if owner is None:
        raise ScenarioError(f"setup 'job.owner' senaryonun kişilerinden biri olmalı: {job.get('owner')}")
    here = world["location"]
    world.pop(world_threads.KEY, None)
    state = world_threads.ensure(world)
    if not state or not state["threads"]:
        raise ScenarioError("setup 'job' kurulamadı: kasabanın iş kaydı yok")
    turn = world["flags"].get("turn_index", 0)
    thread = state["threads"][0]
    thread.update(status="offered", place_id=here, owner_npc_id=owner["id"], owner_name=owner.get("name"),
                  offered_at=0, offered_turn=turn, offer_line=line, owner_line=line, offer_line_turn=turn,
                  expires_at=30 * _DAY)
    if kind == "hiring":
        days = job.get("work_days", 1)
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ScenarioError("setup 'job.work_days' pozitif bir tam sayı olmalı")
        thread.update(type="hiring", template_id="hand_wanted", target_place_id=None, recipient_name=None,
                      terms={"pay": pay, "work_days": days, "pay_basis": "total", "pay_timing": "end_of_day",
                             "deadline_text": f"{days} gün içinde"})
        thread.pop("night_only", None)
    else:
        noun, recipient, target_kind = job.get("noun"), job.get("recipient"), job.get("target_kind")
        if not isinstance(noun, str) or not noun or not isinstance(recipient, str) or not recipient:
            raise ScenarioError("setup 'job.noun' ve 'job.recipient' boş olmayan metinler olmalı")
        settlement = local_places.settlement_of(world, here)
        target = (local_places.create_local_place(world, settlement, target_kind)
                  if target_kind in local_places.PLACE_KINDS else None)
        if target is None:
            raise ScenarioError(f"setup 'job.target_kind' kurulamadı: {target_kind}")
        target["resident_name"] = recipient
        thread.update(type="errand", template_id="courier", target_place_id=target["id"], recipient_name=recipient,
                      item_noun=noun, terms={"pay": pay, "work_days": None, "pay_basis": "per_trip",
                                             "pay_timing": "on_delivery", "deadline_text": "bir gün içinde"})
    state["threads"] = [thread]
    owner["place_role_of"] = here
    world["npc_speech_log"] = {owner["id"]: [{"player": "iş var mı", "npc": line}]}
    if status == "accepted":
        world_threads.accept_hired(world, thread)
    return thread["thread_id"]


def _give_letter(world: dict[str, Any], letter: Any) -> None:
    """A sealed letter offered at the setup job's target place, and a trouble where it is bound (see ``SETUP_KEYS``)."""
    from adventure import dialogue_jobs
    if not isinstance(letter, Mapping):
        raise ScenarioError("setup 'letter' bir nesne olmalı")
    unknown = sorted(str(key) for key in letter if key not in LETTER_KEYS)
    if unknown:
        raise ScenarioError(
            f"bilinmeyen letter anahtarı: {', '.join(unknown)} (izinli: {', '.join(sorted(LETTER_KEYS))})"
        )
    state = world_threads.view(world)
    job = (state or {}).get("threads", [None])[0]
    if not isinstance(job, dict) or job.get("type") != "errand":
        raise ScenarioError("setup 'letter' bir errand 'job' ister")
    pay, line, noun, recipient = letter.get("pay"), letter.get("line"), letter.get("noun"), letter.get("recipient")
    if isinstance(pay, bool) or not isinstance(pay, int) or pay <= 0:
        raise ScenarioError("setup 'letter.pay' pozitif bir tam sayı olmalı")
    if not all(isinstance(value, str) and value for value in (line, noun, recipient)):
        raise ScenarioError("setup 'letter.line', 'letter.noun' ve 'letter.recipient' boş olmayan metinler olmalı")
    owner = next((npc for npc in world.get("npcs") or [] if npc.get("id") == letter.get("owner")), None)
    if owner is None or owner.get("id") == job.get("owner_npc_id"):
        raise ScenarioError(f"setup 'letter.owner' işin sahibi dışında senaryonun kişilerinden biri olmalı: {letter.get('owner')}")
    there = job["target_place_id"]
    settlement = local_places.settlement_of(world, there)
    kind = letter.get("target_kind")
    target = local_places.create_local_place(world, settlement, kind) if kind in local_places.PLACE_KINDS else None
    if target is None or target["id"] in {there, job["place_id"]}:
        raise ScenarioError(f"setup 'letter.target_kind' ayrı bir yer olarak kurulamadı: {kind}")
    target["resident_name"] = recipient
    taken = {there, job["place_id"], target["id"]}
    own = next((record for _, record in sorted(world.get("locations", {}).items()) if isinstance(record, dict)
                and record.get("parent_location_id") == settlement and record.get("place_kind")
                and record["id"] not in taken), None)
    if own is None:
        raise ScenarioError("setup 'letter': mektubun sahibine kasabada ayrı bir yer kalmadı")
    turn = world["flags"].get("turn_index", 0)
    thread = copy.deepcopy(job)
    thread.update(thread_id=f"thread_{state['next_number']:03d}", template_id="sealed_letter", place_id=own["id"],
                  owner_npc_id=owner["id"], owner_name=owner.get("name"), offered_at=0, offered_turn=turn,
                  offer_line=line, owner_line=line, offer_line_turn=turn, target_place_id=target["id"],
                  recipient_name=recipient, item_noun=noun,
                  terms={**job["terms"], "pay": pay})
    if not dialogue_jobs.sealed(thread):
        raise ScenarioError("setup 'letter.line' mührü anmalı (mühürlü mektup)")
    state["next_number"] += 1
    state["threads"].append(thread)
    owner.update(location=there, place_role_of=own["id"])  # their own place is elsewhere; they wait where the job ends
    world.setdefault("npc_speech_log", {})[owner["id"]] = [{"player": "iş var mı", "npc": line}]
    opened = next((found for template in world_threads.catalog()["templates"] if template["type"] == "trouble"
                   for found in (world_threads._open_thread(world, state, template, settlement, create=False,
                                                           now=world_threads._now(world), place=target),) if found), None)
    if opened is None:
        raise ScenarioError("setup 'letter': mektubun gittiği yerde bir dert açılamadı")


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
    if "no_exit" in place and not isinstance(place["no_exit"], bool):
        raise ScenarioError("setup 'place.no_exit' true ya da false olmalı")
    record = local_places.create_local_place(world, world["location"], kind, name=name)
    if record is None:
        raise ScenarioError(f"setup 'place' kurulamadı: {name}")
    record.update({key: place[key] for key in ("scene_kind", "place_kind") if key in place})
    if place.get("no_exit"):
        record.pop("parent_location_id", None)
        record["exit_location_id"] = None
    world["location"] = record["id"]


def read_observed(case: Any, session_id: str) -> dict[str, Any]:
    """What a step can expect, read from the live session (the save copy's public projection for the
    conversation, the card and death; the live world for the rest).

    ``kart`` is the economic card; ``tezgah`` is the counter's offer that a spoken order opens (settled
    only by the counter trade, never by the card); ``kisi_kese`` is every purse but the player's; ``cephane`` is
    the player's ammunition counter (``world.ammunition``, type to count), kept apart from the items: a pack
    label such as "Uzun Yay & 20 Ok" is one item and no arrows. ``hareket`` is the feet of movement the player
    has used in the fight's current turn (None outside a fight or before the turn's resources exist).

    ``kart.kalemler`` names the card's lines as the card shows them (a room card says "Oda (bir gece)", a gift
    "Hediye"). ``xp`` is the player's earned experience; ``saat`` the whole game hours gone since the campaign began;
    ``gorev`` the quest rows still running (``world.quests``, a town errand's row included: count and titles).
    ``karsi_saldiri`` is read from the step's own turn response: the most counter-attacks one enemy made in it, a
    counter-attack being a swing resolved after the player's own (see ``counter_attacks``).
    ``yuva`` is the player's spell slots left, by level (``world.spellcasting_v1.slots``; None without spells).
    ``esya_sayisi`` is every item the player holds, whatever its name (a duplicate shows even under another name).
    ``buyu_olgusu`` names the narrative spell facts saved (``world.spell_effects_v1``, 4C.5), in saved order.

    ``anlatilan`` is what each person keeps of the player's own words (``world.npc_told_v1``: person to the kept
    texts), a state a reload compares. ``konusmaya_giden`` is every message the step's last speech call was sent (None:
    no speech call) and ``inkar`` whether the step's narration holds one of the engine's stock denial or "I do not
    know" lines (``denial_said``); both are the step's own, never compared on reload. ``tezgah`` carries the counter's
    tip (``tip_cp``, 0 without one) and the total it asks for (``total_cp``, unit price and tip)."""
    session = case.manager.get(session_id).game_session
    world = session.world_state
    state = serializers.serialize_session_state(session)
    flags = world.get("flags") if isinstance(world.get("flags"), dict) else {}
    combat = world.get("combat") if isinstance(world.get("combat"), dict) else {}
    offer = state.get("economic_offer")
    currency = world.get("currency") if isinstance(world.get("currency"), dict) else {}
    ammunition = world.get("ammunition") if isinstance(world.get("ammunition"), dict) else {}
    return {
        "kese": currency.get("player"),
        "envanter": _inventory_counts(world.get("inventory") or []),
        "esya_sayisi": sum(_inventory_counts(world.get("inventory") or []).values()),
        "oda": bool(flags.get("inn_room")),
        "kip": copy.deepcopy(state.get("conversation")),
        "savas": bool(combat.get("active")),
        "konum": world.get("location"),
        "hp": session.character.get("current_hp"),
        "kart": None if offer is None else {"max_total_cp": offer.get("max_total_cp"),
                                            "counterparty_label": offer.get("counterparty_label"),
                                            "kalemler": [line.get("label") for line in offer.get("lines") or []]},
        "tezgah": _counter_offer(world),
        "kisi_kese": {str(owner): cp for owner, cp in currency.items() if owner != "player"},
        "cephane": copy.deepcopy(ammunition),
        "hareket": _combat_movement(combat),
        "olu": (state.get("death_state") or {}).get("status"),
        "elinde": _held_name(world),
        "gunluk": _journal(state.get("quest_log")),
        "olay": _scene_event(state.get("scene")),
        "zirh": session.character.get("armor_class"),
        "xp": session.character.get("xp", 0),
        "seviye": session.character.get("level"),
        "saat": (world.get("campaign_time") or {}).get("elapsed_seconds", 0) // _HOUR,
        "gorev": _open_quests(world.get("quests") or []),
        "karsi_saldiri": counter_attacks(getattr(case, "last_combat_result", None)),
        "zar": _dice_card(getattr(case, "last_skill_check", None)),
        "yuva": _spell_slots(world),
        "buyu_olgusu": [fact.get("spell_id") for fact in world.get("spell_effects_v1") or [] if isinstance(fact, dict)],
        "anlatilan": _told(world),
        "narration": getattr(case, "last_narration", ""),
        "anlaticiya_giden": getattr(case, "last_narrator_input", None),
        "konusmaya_giden": getattr(case, "last_speech_input", None),
        "inkar": getattr(case, "last_denial", False),
        "ambient": getattr(case, "last_ambient_result", None),
        "varis": {"cagri": getattr(case, "last_arrival_calls", 0),
                  "kaynak": (getattr(session, "last_arrival_narration", None) or {}).get("source"),
                  "neden": (getattr(session, "last_arrival_narration", None) or {}).get("reason_code")},
    }


def _dice_card(check: Any) -> dict[str, Any] | None:
    """The dice card the player sees for the step's turn (the response's ``skill_check_result``): the skill, the
    outcome (success or failure) and whether the d20 and total are on it; None when the turn showed no dice."""
    if not isinstance(check, Mapping):
        return None
    return {"beceri": check.get("skill"), "sonuc": check.get("outcome"),
            "zar_var": isinstance(check.get("d20"), int) and isinstance(check.get("total"), int)}


def _scene_event(scene: Any) -> dict[str, Any]:
    """The API's scene event as the journey reads it: is there one, and what the API says about clicking it
    (``actionable``: None while the API carries no such field)."""
    event = scene.get("ambient_event") if isinstance(scene, Mapping) else None
    if not isinstance(event, Mapping):
        return {"var": False, "tiklanabilir": None, "neden": None}
    actionable = event.get("actionable") if isinstance(event.get("actionable"), Mapping) else {}
    return {"var": True, "tiklanabilir": actionable.get("can_interact"), "neden": actionable.get("reason")}


def _held_name(world: Mapping[str, Any]) -> str | None:
    """The name of the item in the main hand (``world.equipment.main_hand``); None for an empty hand or a hand
    that points at nothing in the bag."""
    equipment = world.get("equipment")
    held = equipment.get("main_hand") if isinstance(equipment, Mapping) else None
    return next((item.get("name") for item in world.get("inventory") or []
                 if isinstance(item, Mapping) and held is not None and item.get("item_id") == held), None)


def _journal(log: Any) -> dict[str, Any] | None:
    """The API's ``quest_log`` view as the journey reads it (None when the response carries no such field)."""
    if not isinstance(log, Mapping):
        return None
    rows = lambda key: [row for row in log.get(key) or [] if isinstance(row, Mapping)]  # noqa: E731
    return {"sayac": log.get("active_count"),
            "suren": [str(row.get("title")) for row in rows("active")],
            "biten": [f"{row.get('title')} ({row['result']})" if row.get("result") else str(row.get("title"))
                      for row in rows("done")],
            "iz": [{"ne": row.get("what"), "nerede": row.get("where"), "kaynak": row.get("source"),
                    "izlendi": row.get("followed")} for row in rows("trails")]}


def _told(world: Mapping[str, Any]) -> dict[str, list[str]]:
    """Person to the texts they keep of the player's own words (``npc_told_v1``); rows without a text are left out."""
    told = world.get("npc_told_v1")
    if not isinstance(told, Mapping):
        return {}
    return {str(npc): [row["text"] for row in rows if isinstance(row, Mapping) and isinstance(row.get("text"), str)]
            for npc, rows in told.items() if isinstance(rows, list)}


def denial_said(narration: Any) -> bool:
    """Whether the narration holds the spoken part of one of the engine's stock denial lines
    (``game._CLAIM_DENIAL_LINES``) or "I do not know" lines (``interaction_adventure._UNKNOWN_LINES``)."""
    if not isinstance(narration, str) or not narration:
        return False
    lines = (*game._CLAIM_DENIAL_LINES, *interaction_adventure._UNKNOWN_LINES)
    return any(line.split("“", 1)[-1].rstrip("”") in narration for line in lines)


def counter_attacks(combat_result: Any) -> int:
    """The most counter-attacks one enemy made in a turn's combat result (0 without any). ``enemy_actions`` is the
    whole exchange; the singular ``enemy_action`` is the engine's alias of its first entry and counts only alone.

    A counter-attack answers the player's swing, so it is resolved after it. An enemy that won initiative takes its
    turn before the player's blow and its next turn after it, both in one response (D&D 2024 initiative order); the
    first is no counter-attack. The order is the last number of the resolution id within the player's action
    (``<action_id>:attack_roll:<n>``). A swing whose order cannot be compared with the player's counts."""
    if not isinstance(combat_result, Mapping):
        return 0
    enemies = combat_result.get("enemy_actions")
    if not isinstance(enemies, list):
        single = combat_result.get("enemy_action")
        enemies = [single] if isinstance(single, Mapping) else []
    player_order = _resolution_order(combat_result)
    counts: dict[str, int] = {}
    for enemy in enemies:
        if not isinstance(enemy, Mapping) or enemy.get("outcome") not in _SWINGS:
            continue
        order = _resolution_order(enemy)
        if player_order is not None and order is not None and order[0] == player_order[0] \
                and order[1] < player_order[1]:
            continue  # resolved before the player's swing: the enemy's own turn, not an answer to the blow
        actor = str(enemy.get("actor") or enemy.get("actor_name") or "")
        counts[actor] = counts.get(actor, 0) + 1
    return max(counts.values(), default=0)


def _resolution_order(roll: Mapping[str, Any]) -> tuple[str, int] | None:
    """(action id, place in that action) from ``<action_id>:<kind>:<n>``; None when the id says no such thing."""
    action_id, resolution_id = roll.get("action_id"), roll.get("resolution_id")
    if not isinstance(action_id, str) or not isinstance(resolution_id, str) \
            or not resolution_id.startswith(action_id + ":"):
        return None
    number = resolution_id.rsplit(":", 1)[-1]
    return (action_id, int(number)) if number.isdigit() else None


def _spell_slots(world: Mapping[str, Any]) -> dict[str, int] | None:
    """The player's spell slots left, by level (None for a character with no spellcasting)."""
    casting = world.get("spellcasting_v1")
    slots = casting.get("slots") if isinstance(casting, Mapping) else None
    return copy.deepcopy(dict(slots)) if isinstance(slots, Mapping) else None


def _open_quests(quests: Sequence[Any]) -> dict[str, Any]:
    """The quest rows still running (the journal's own rows, a town errand's included), by title."""
    titles = [str(row.get("title")) for row in quests
              if isinstance(row, Mapping) and row.get("status") in _ACTIVE_QUEST]
    return {"aktif": len(titles), "kayit": sorted(titles)}


def _combat_movement(combat: Mapping[str, Any]) -> int | None:
    """The player's movement used this turn, read from the fight's turn resources without making them."""
    if not combat.get("active"):
        return None
    resources = combat.get("turn_resources")
    player = resources.get("player") if isinstance(resources, Mapping) else None
    return player.get("movement_used") if isinstance(player, Mapping) else None


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
    unit = None if quoted is None else quoted["unit_cp"]
    tip = opened.get("tip_cp", 0)
    return {"npc_id": opened.get("npc_id"), "key": opened.get("key"), "unit_cp": unit, "tip_cp": tip,
            "total_cp": unit + tip if type(unit) is int and type(tip) is int else None}


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
    # call), what its last speech call was sent (None: no speech call), whether a stock denial was said, every step's
    # observation, the session played.
    last_narration: str = ""
    last_narrator_input: str | None = None
    last_speech_input: str | None = None
    last_denial: bool = False
    # How many arrival narration calls the last step made (``expect.varis.cagri``).
    last_arrival_calls: int = 0
    # The last turn's combat result as the turn response carried it (None: no turn, or no combat result).
    last_combat_result: Mapping[str, Any] | None = None
    # The last turn's dice card (``skill_check_result``) as the response carried it; None: the turn showed no dice.
    last_skill_check: Mapping[str, Any] | None = None
    last_observations: list[dict[str, Any]]
    last_session_id: str | None = None
    # The action id of the last turn sent, which an ``undo`` step names as the turn to take back.
    last_turn_action_id: str | None = None
    # The last step's ambient click result ({status, reason_code}); None for any other step.
    last_ambient_result: dict[str, Any] | None = None

    async def run_scenario(self, scenario: Scenario, *, model: ModelDriver | None = None) -> list[StepResult]:
        model = model if model is not None else ScriptedModel()
        campaign = await self._journey_campaign(scenario.setup)
        apply_setup(self, campaign, scenario.setup)
        session_id = campaign["session_id"]
        self.last_session_id = session_id
        self.last_narration = ""
        self.last_narrator_input = None
        self.last_speech_input = None
        self.last_denial = False
        self.last_combat_result = None
        self.last_skill_check = None
        self.last_turn_action_id = None
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
                results.append(StepResult(index, "unreached", (REAL_CHAIN_ONLY,), step.known_broken, "", 0.0))
                continue
            started = time.monotonic()
            self.last_arrival_calls = 0
            _forget_arrival_source(self, session_id)
            if step.reload:
                failures, observed = await self._reload(session_id, step, model)
                if not failures:
                    session_id = self.last_session_id
            else:
                self.last_ambient_result = None
                if step.ambient is not None:
                    failures = await self._ambient(session_id, step, model)
                elif step.undo:
                    failures = await self._undo(session_id, step, model)
                else:
                    failures = await self._play(session_id, step, model)
                observed = read_observed(self, session_id)
            self.last_observations.append(observed)
            failures.extend(check_expect(_with_job_target(self, step.expect, session_id), observed))
            if step.sifir_tolerans:
                failures.extend(check_invariant(step.sifir_tolerans, observed))
            journal = observed.get("gunluk")
            if journal is not None and journal["sayac"] != len(journal["suren"]):
                failures.append("gunluk: sayaç ile süren sayısı farklı "
                                f"(sayaç {journal['sayac']}, süren {len(journal['suren'])})")
            status = step_status(step, failures)
            if status == "known_broken":
                blocked_by = index
            results.append(StepResult(index, status, tuple(failures), step.known_broken,
                                      self.last_narration, time.monotonic() - started,
                                      "" if step.undo or step.reload or step.ambient else self.last_reading,
                                      observed.get("varis")))
        return results

    async def _journey_campaign(self, setup: Mapping[str, Any]) -> dict:
        with _campaign_seeded(setup):
            return await self._new_journey_campaign(setup)

    async def _new_journey_campaign(self, setup: Mapping[str, Any]) -> dict:
        if not {"character", "campaign_start", "death_mode"} & set(setup):
            return await self.create_campaign()
        mode = setup.get("death_mode", "NORMAL")
        if mode not in game.DEATH_MODES:
            raise ScenarioError(f"setup 'death_mode' bilinen bir ölüm kipi değil: {mode} "
                                f"(izinli: {', '.join(game.DEATH_MODES)})")
        body: dict[str, Any] = {"death_mode": mode}
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
        self.last_turn_action_id = body["action_id"]
        with model.bind(self, step) as client:
            told = NarratorInput(game.ollama.chat)
            with patch.object(game.ollama, "chat", told):
                response = await self.http.post(f"/api/game/sessions/{session_id}/turn", json=body)
        self.last_narrator_input = told.text()
        self.last_reading = told.reading()
        self.last_arrival_calls = told.arrival_calls()
        spoken_to = told.speech_messages()
        self.last_speech_input = None if spoken_to is None else "\n".join(spoken_to)
        unexpected = getattr(client, "unexpected", None) or []
        failures.extend(f"beklenmeyen model çağrısı: {keys}" for keys in unexpected)
        self.last_combat_result = None
        self.last_skill_check = None
        if response.status_code != 200:
            self.last_narration = ""
            failures.append(f"HTTP {response.status_code}: {response.text[:300]}")
        else:
            self.last_narration = str(response.json().get("narration") or "")
            self.last_combat_result = response.json().get("combat_result")
            self.last_skill_check = response.json().get("skill_check_result")
        self.last_denial = denial_said(self.last_narration)
        return failures

    async def _ambient(self, session_id: str, step: Step, model: ModelDriver) -> list[str]:
        """Click the scene's current ambient event through the product's route (a new action id, which an ``undo``
        step after it names); return the failures the click itself produced. No model call is made."""
        self.last_narrator_input = None
        self.last_speech_input = None
        self.last_denial = False
        self.last_narration = ""
        self.last_combat_result = None
        self.last_skill_check = None
        body = {"action_id": str(uuid4()), "action": step.ambient["action"]}
        with model.bind(self, step) as client:
            world = self.manager.get(session_id).game_session.world_state
            scenes = (world.get("scene_state") or {}).get("scenes") or {}
            event = (scenes.get(world.get("location")) or {}).get("ambient_event")
            if not (isinstance(event, Mapping) and isinstance(event.get("instance_id"), str)):
                return ["ambient: sahnede olay yok"]
            self.last_turn_action_id = body["action_id"]
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/ambient-events/{event['instance_id']}/actions", json=body)
        failures = [f"beklenmeyen model çağrısı: {keys}" for keys in getattr(client, "unexpected", None) or []]
        if response.status_code != 200:
            failures.append(f"HTTP {response.status_code}: {response.text[:300]}")
        else:
            result = response.json().get("result") or {}
            self.last_ambient_result = {"status": result.get("status"), "reason_code": result.get("reason_code")}
        return failures

    async def _undo(self, session_id: str, step: Step, model: ModelDriver) -> list[str]:
        """Take back the last turn sent, through the product's undo route (the route alone decides whether it
        may); return the failures the undo itself produced."""
        self.last_narrator_input = None
        self.last_speech_input = None
        self.last_denial = False
        self.last_narration = ""
        self.last_combat_result = None
        self.last_skill_check = None
        if self.last_turn_action_id is None:
            return ["geri al: geri alınacak tur yok (bu adımdan önce oynanmış tur yok)"]
        body = {"action_id": str(uuid4()), "target_action_id": self.last_turn_action_id}
        with model.bind(self, step) as client:
            response = await self.http.post(f"/api/game/sessions/{session_id}/undo", json=body)
        failures = [f"beklenmeyen model çağrısı: {keys}" for keys in getattr(client, "unexpected", None) or []]
        if response.status_code != 200:
            failures.append(f"HTTP {response.status_code}: {response.text[:300]}")
        else:
            self.last_narration = str(response.json().get("narration") or "")
        return failures

    async def _reload(self, session_id: str, step: Step, model: ModelDriver) -> tuple[list[str], dict[str, Any]]:
        """Read the campaign back from its save in a fresh session manager, as after a restart (nothing from the
        live session carries over), and compare it with the live game key by key. The step observes what came
        back from the save; later HTTP steps use that reopened manager and session."""
        self.last_narrator_input = None
        self.last_speech_input = None
        self.last_denial = False
        self.last_narration = ""
        self.last_combat_result = None
        self.last_skill_check = None
        with model.bind(self, step):
            live = read_observed(self, session_id)
            reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
            fresh = SessionManager(campaign_store=reopened_store)
            reloaded_id, *_ = fresh.resume_campaign(self.manager.get(session_id).campaign_id)
        saved = read_observed(_Reader(fresh), reloaded_id)
        failures = [f"yenileme: {key}: canlı {_show(live[key])}, kayıttan {_show(saved.get(key))}"
                    for key in live if key not in _NOT_STATE and saved.get(key) != live[key]]
        if not failures:
            adapter = self.app.state.ollama_adapter
            headers = dict(self.http.headers)
            base_url = self.http.base_url
            app = create_app(session_manager=fresh, ollama_adapter=adapter,
                             authenticator=FixedAuthenticator(TEST_PLAYER))
            await self.http.aclose()
            self.manager, self.store, self.app = fresh, reopened_store, app
            self.last_session_id = reloaded_id
            self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url=base_url, headers=headers)
        return failures, saved

    def _body(self, session_id: str, step: Step) -> dict[str, Any]:
        body: dict[str, Any] = {"action_id": str(uuid4())}
        if step.say is not None:
            body["message"] = step.say
            if step.konus is not None:
                body.update(interaction_mode="say", target_id=step.konus)
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


@dataclass
class _Reader:
    """What ``read_observed`` needs of a case, for a session manager other than the case's own."""

    manager: SessionManager
    last_narration: str = ""
    last_narrator_input: str | None = None
    last_speech_input: str | None = None
    last_denial: bool = False
    last_arrival_calls: int = 0


def _forget_arrival_source(case: Any, session_id: str) -> None:
    """A step starts with no arrival diagnostic: ``expect.varis.kaynak`` reads only what this step's arrival wrote."""
    case.manager.get(session_id).game_session.last_arrival_narration = None


def _show(value: Any) -> str:
    return "yok" if value is None else str(value)


def _campaign_seeded(setup: Mapping[str, Any]) -> AbstractContextManager[Any]:
    """The setup's ``campaign_seed`` as the new campaign's id (every other id stays random); untouched without it."""
    if "campaign_seed" not in setup:
        return nullcontext()
    number = setup["campaign_seed"]
    if type(number) is not int or not 0 < number < 10 ** 12:
        raise ScenarioError("setup 'campaign_seed' pozitif bir tam sayı olmalı")
    import uuid
    from api import session_manager
    ids = iter([uuid.UUID(f"00000000-0000-4000-8000-{number:012d}")])
    return patch.object(session_manager, "uuid", SimpleNamespace(uuid4=lambda: next(ids, None) or uuid4()))


def _front_setting(setup: Mapping[str, Any]) -> AbstractContextManager[Any]:
    """The front-reading flag as the scenario sets it, restored afterwards; untouched when it says nothing."""
    if "front_proposal" not in setup:
        return nullcontext()
    return patch.dict(os.environ, {front_proposal.FLAG: "1" if setup["front_proposal"] else "0"})


def step_status(step: Step, failures: Sequence[str]) -> Status:
    """A step's status from its failures (see the module docstring)."""
    if not step.known_broken:
        return "new_break" if failures else "pass"
    if not failures:
        return "marker_stale"
    if any(_ALWAYS_NEW.match(failure) for failure in failures):
        return "new_break"
    if step.broken_because and not all(any(cause in failure for cause in step.broken_because)
                                       for failure in failures):
        return "new_break"
    return "known_broken"


def describe_problems(results: Sequence[StepResult]) -> list[str]:
    """One Turkish line per step that must fail the suite (a new break or a stale marker)."""
    lines = []
    for result in results:
        if result.status == "new_break" and result.items:
            lines.append(f"adım {result.index}: YENİ KIRIK (bilinen kırık {list(result.items)} işaretli, ama "
                         "bu hata işaretin nedeni değil): " + "; ".join(result.failures))
        elif result.status == "new_break":
            lines.append(f"adım {result.index}: YENİ KIRIK: " + "; ".join(result.failures))
        elif result.status == "marker_stale":
            lines.append(f"adım {result.index}: geçti ama bilinen kırık işaretli "
                         f"{list(result.items)}; işareti kaldır")
    return lines


def summary_line(results: Mapping[str, Sequence[StepResult]]) -> str:
    """Scenario counts: a scenario with any new break is a new break, else any known break makes it
    known broken, else it passed. Stale markers are counted on their own, and so are the steps that only the real
    chain runs."""
    passed = known = new = 0
    stale = pending = 0
    for steps in results.values():
        statuses = {result.status for result in steps}
        stale += sum(result.status == "marker_stale" for result in steps)
        pending += sum(result.status == "unreached" and result.failures == (REAL_CHAIN_ONLY,) for result in steps)
        if "new_break" in statuses:
            new += 1
        elif "known_broken" in statuses:
            known += 1
        else:
            passed += 1
    line = f"{passed} geçti, {known} bilinen kırık, {new} yeni kırık"
    line += f" ({stale} adımda işaret kaldırılmalı)" if stale else ""
    return line + (f" ({pending} adım yalnız gerçek zincirde)" if pending else "")
