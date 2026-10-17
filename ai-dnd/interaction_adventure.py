"""Bounded interaction/adventure consumer of the existing Python world owners.

No model, filesystem, RNG, clock advancement or module-global campaign state.
Untrusted envelopes describe intentions, not successful outcomes.
"""
from __future__ import annotations

import copy
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import living_world
import equipment_economy

KEY = "interaction_adventure_v1"
ACTIVE = {"discovered", "offered", "active", "progressing", "reframed"}
TERMINAL = {"succeeded", "failed", "abandoned", "expired"}
MAX_THREADS = 48
MAX_EVENTS = 192


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Route(Contract):
    kind: Literal["visit", "talk", "acquire", "defeat", "fact"]
    target: str = Field(min_length=1, max_length=160)


class Objective(Contract):
    objective_id: str
    description: str = Field(min_length=1, max_length=400)
    optional: bool = False
    hidden: bool = False
    routes: list[Route] = Field(max_length=4)
    status: Literal["active", "completed"] = "active"
    evidence_id: str | None = None


class Thread(Contract):
    thread_id: str
    origin: Literal["player", "local_proposal", "legacy_quest"]
    title: str = Field(min_length=1, max_length=400)
    status: Literal["discovered", "offered", "active", "progressing", "reframed",
                    "succeeded", "failed", "abandoned", "expired"]
    location_id: str
    npc_id: str | None = None
    allegiance_id: str | None = None
    objectives: list[Objective] = Field(min_length=1, max_length=6)
    deadline: int | None = Field(default=None, ge=0)
    created_turn: int = Field(ge=0)
    updated_turn: int = Field(ge=0)
    reframing_evidence: str | None = None


class Commitment(Contract):
    commitment_id: str
    npc_id: str
    quote: str = Field(min_length=1, max_length=400)
    thread_id: str | None = None
    kind: Literal["promise", "conditional", "debt"]
    status: Literal["open", "fulfilled", "broken"] = "open"
    created_turn: int = Field(ge=0)
    updated_turn: int = Field(ge=0)


class ConversationFocus(Contract):
    speaker_id: str = Field(min_length=1, max_length=128)
    scene_id: str = Field(min_length=1, max_length=128)
    subject_id: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1, max_length=64)
    value: str | bool | int | float | None
    turn: int = Field(ge=0)
    action_id: str = Field(min_length=1, max_length=160)
    evidence_id: str = Field(min_length=1, max_length=160)
    epistemic: Literal["owner_verified", "witnessed", "player_claim", "rumor", "belief"]


class PerspectiveEntry(Contract):
    entry_id: str
    kind: Literal["witnessed", "player_claim", "belief", "rumor", "lie"]
    text: str = Field(min_length=1, max_length=400)
    source_id: str
    secret: bool = False


class Event(Contract):
    event_id: str
    kind: str = Field(min_length=1, max_length=64)
    turn: int = Field(ge=0)
    at: int = Field(ge=0)
    location_id: str
    thread_id: str | None = None
    npc_id: str | None = None
    listeners: list[str] = Field(max_length=60)
    private: bool = False
    player_known: bool = True
    summary: str = Field(min_length=1, max_length=400)


class PlanStep(Contract):
    quote: str = Field(min_length=1, max_length=400)
    depends_on: int | None = Field(default=None, ge=0)
    precondition: str = Field(default="", max_length=400)
    interruption: Literal["player_confirmation"] = "player_confirmation"


class Plan(Contract):
    plan_id: str
    goal: str = Field(min_length=1, max_length=400)
    steps: list[PlanStep] = Field(min_length=1, max_length=6)
    cursor: int = Field(ge=0)
    status: Literal["awaiting_confirmation", "paused", "completed", "abandoned"]
    location_id: str


class Novelty(Contract):
    theme: Literal["inquiry", "cooperation", "dispute", "warning", "meeting"]
    conflict: str
    motivation: str
    objective_structure: str
    location_id: str
    antagonist: Literal["none", "local"]
    reward_pattern: Literal["none"]
    resolution_style: str
    turn: int = Field(ge=0)


class State(Contract):
    version: Literal[1] = 1
    conversation_focus: ConversationFocus | None = None
    threads: list[Thread] = Field(default_factory=list, max_length=MAX_THREADS)
    commitments: list[Commitment] = Field(default_factory=list, max_length=64)
    perspectives: dict[str, list[PerspectiveEntry]] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list, max_length=MAX_EVENTS)
    plan: Plan | None = None
    novelty: list[Novelty] = Field(default_factory=list, max_length=16)
    last_generation_turn: int = Field(default=-100, ge=-100)
    last_beat_turn: int = Field(default=-100, ge=-100)


class Candidate(Contract):
    kind: Literal["inquiry", "cooperation", "dispute", "warning", "meeting"]
    impact: Literal["local"]
    npc_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=128)
    routes: list[Route] = Field(min_length=1, max_length=4)
    # IDs only. No invented prose, deadlines, reward, lore or mechanics.
    evidence_id: str | None = None


class Envelope(Contract):
    operation: Literal["none", "goal", "request", "negotiate", "refuse", "delay",
                       "agree", "conditional", "threat", "promise", "information",
                       "reframe", "switch_side", "betray", "abandon", "plan",
                       "continue_plan", "generate"]
    quote: str = Field(default="", max_length=4000)
    thread_id: str | None = None
    evidence_id: str | None = None
    requested_item: str | None = Field(default=None, max_length=160)
    rejected_consideration: str | None = Field(default=None, max_length=400)
    side_id: str | None = None
    privacy: Literal["private", "public", "addressed"] = "addressed"
    steps: list[PlanStep] = Field(default_factory=list, max_length=6)
    routes: list[Route] = Field(default_factory=list, max_length=4)
    candidates: list[Candidate] = Field(default_factory=list, max_length=3)


PROPOSAL_SCHEMA = Envelope.model_json_schema()


def intent_schema(base):
    schema = copy.deepcopy(base)
    envelope = copy.deepcopy(PROPOSAL_SCHEMA)
    schema["$defs"] = envelope.pop("$defs", {})
    schema["properties"]["interaction"] = envelope
    # Optional JSON properties were routinely omitted by the real model, despite
    # prompt guidance. Require the envelope, including an exact player quote.
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "interaction"]))
    envelope["required"] = list(dict.fromkeys([*envelope.get("required", []), "quote"]))
    return schema


def proposal_guidance():
    return (
        "Bu tur serbest interaction niyeti de yorumla. interaction.operation mevcut oyuncu "
        "niyetini ifade eder; başarı, onay, gerçek, eşya aktarımı, süre veya zar sonucu değildir. "
        "quote oyuncu mesajından birebir alıntı olmalı. thread_id ve evidence_id yalnızca "
        "gönderilen context içinden; belirsizse null. Başka NPC'nin bilgisini tahmin etme. "
        "İtem talebinde requested_item yalnızca oyuncunun istediği eşyanın referansıdır. "
        "Oyuncu NPC'den açıkça bir eşya istiyorsa (ör. 'Club'ı bana ver'), operation=request "
        "ve requested_item mesajdaki eşya adı olmalı; bu bir information işlemi değildir. "
        "Bu yorum NPC rızası veya başarılı aktarım değildir; bunları yalnız Python doğrular. "
        "Mevcut bir macera izine devam ediyorsa thread_id seç; yeni hedefte goal seç. "
        "Çok adımlı planın steps alanı yalnızca oyuncunun aynen söylediği adımlardır; bunları "
        "gerçekleştirme. Plan işleminde steps boş olamaz. İlk adım depends_on=null; sonraki "
        "adımlar yalnızca önceki sıfır-tabanlı adım indeksine bağlanabilir. precondition "
        "yalnızca girdide aynen bulunan şarttır; bilinmeyen şartı veya zamanını uydurma. "
        "Tamamlanmayı veya guard shift zamanını uydurma. "
        "generate yalnızca oyuncu iş/macera/fırsat aradığında seçilebilir; generation_allowed "
        "true ise aynı yanıtta en fazla üç LOCAL candidate öner. Mevcut yerel procedural NPC "
        "ve route target kimliklerini kullan; lore figürü, yeni NPC, ödül veya tarih üretme. "
        "Bir tek bilgi sorusunu veya selamı macera üretimine dönüştürme. "
        "steps/candidates çoğu işlemde boş olmalıdır. privacy addressed varsayılandır; "
        "yalnızca açık fısıltıda private, açıkça herkese söylenende public seç. "
        "Konuşmadaki inanç/iddia dünya gerçeği değildir. JSON interaction zarfını da döndür."
    )


def normalize(text):
    return " ".join(str(text).replace("İ", "i").replace("I", "ı").casefold().translate(
        str.maketrans("ıüşöçğ", "iusocg")).split())


def get(world):
    """Read-only defaults. Reads/resume/projection must not create events."""
    return copy.deepcopy(world.get(KEY, State().model_dump()))


def remember_conversation_focus(world, *, speaker_id, scene_id, subject_id,
                                predicate, value, turn, action_id, evidence_id,
                                epistemic="owner_verified"):
    """Store a bounded, structured proposition from an accepted owner result."""
    if not isinstance(action_id, str) or not action_id:
        return False
    focus = ConversationFocus(
        speaker_id=speaker_id, scene_id=scene_id, subject_id=subject_id,
        predicate=predicate, value=value, turn=turn, action_id=action_id,
        evidence_id=evidence_id, epistemic=epistemic,
    )
    world.setdefault(KEY, State().model_dump())["conversation_focus"] = focus.model_dump()
    return True


def current_conversation_focus(world, npc=None):
    raw = get(world).get("conversation_focus")
    if not isinstance(raw, dict):
        return None
    try:
        focus = ConversationFocus.model_validate(raw)
    except ValidationError:
        return None
    flags = world.get("flags", {})
    turn = flags.get("turn_index", 0) if isinstance(flags, dict) else 0
    active_until = flags.get("active_npc_until_turn", -1) if isinstance(flags, dict) else -1
    if (
        focus.scene_id != world.get("location")
        or focus.speaker_id != flags.get("active_npc_id")
        or type(turn) is not int or type(active_until) is not int
        or turn > active_until or turn - focus.turn > 6 or turn < focus.turn
        or focus.epistemic not in {"owner_verified", "witnessed"}
        or (npc is not None and npc.get("id") != focus.speaker_id)
    ):
        return None
    if focus.subject_id.startswith("venue-door:") and focus.predicate == "locked":
        door = next(
            (
                item for item in world.get("doors", [])
                if isinstance(item, dict) and item.get("id") == focus.subject_id
            ),
            None,
        )
        if not isinstance(door, dict) or door.get("locked") is not focus.value:
            return None
    elif focus.subject_id.startswith("npc-profile:"):
        _, npc_id, field = focus.subject_id.split(":", 2)
        owner = next(
            (
                item for item in world.get("npcs", [])
                if isinstance(item, dict) and item.get("id") == npc_id
            ),
            None,
        )
        profile = owner.get("personal_profile") if isinstance(owner, dict) else None
        if (
            not isinstance(profile, dict)
            or not field
            or profile.get(field) != focus.value
            or focus.speaker_id != npc_id
        ):
            return None
    return focus.model_dump()


def is_focus_followup(world, text):
    focus = current_conversation_focus(world)
    if not focus or not isinstance(text, str):
        return False
    normalized = normalize(text)
    terms = re.findall(r"[a-z0-9]+", normalized)
    predicate_terms = {
        "locked": ("kilitli", "kilit"),
    }.get(focus["predicate"], (focus["predicate"],))
    has_reason_question = any(
        term in terms for term in ("neden", "niye", "nicin")
    )
    if not has_reason_question:
        return False
    if focus["subject_id"].startswith("npc-profile:"):
        return len(terms) <= 4 and all(
            term in {"neden", "niye", "nicin", "peki", "ya", "acaba"}
            for term in terms
        )
    focus_subject_location = (
        focus["subject_id"].partition(":")[2]
        if focus["subject_id"].startswith("venue-door:")
        else None
    )
    if focus_subject_location:
        for location_id, location in world.get("locations", {}).items():
            if (
                location_id != focus_subject_location
                and isinstance(location, dict)
                and location.get("scene_kind") == "tavern"
                and isinstance(location.get("name"), str)
                and normalize(location["name"]) in normalized
            ):
                return False
    if any(term in terms for term in predicate_terms):
        return True
    return (
        len(terms) <= 3
        and all(term in {"neden", "niye", "nicin", "peki", "ya", "acaba"} for term in terms)
    )


def validate(value, world):
    state = State.model_validate(value)
    npcs = {n["id"] for n in world.get("npcs", []) if isinstance(n, dict) and "id" in n}
    locations = set(world.get("locations", {}))
    thread_ids = {t.thread_id for t in state.threads}
    if len(thread_ids) != len(state.threads):
        raise ValueError("Duplicate adventure thread identity.")
    identities = []
    for thread in state.threads:
        identities.extend([thread.thread_id, *(o.objective_id for o in thread.objectives)])
        if thread.location_id not in locations or any(
                actor is not None and actor not in npcs
                for actor in (thread.npc_id, thread.allegiance_id)):
            raise ValueError("Invalid adventure anchor.")
        if thread.updated_turn < thread.created_turn:
            raise ValueError("Invalid adventure transition time.")
        for objective in thread.objectives:
            for route in objective.routes:
                if not route_valid(world, route.model_dump()):
                    raise ValueError("Invalid adventure evidence route.")
    for commitment in state.commitments:
        identities.append(commitment.commitment_id)
        if commitment.npc_id not in npcs or (
                commitment.thread_id is not None and commitment.thread_id not in thread_ids):
            raise ValueError("Invalid commitment anchor.")
    for npc_id, entries in state.perspectives.items():
        if npc_id not in npcs or len(entries) > 24:
            raise ValueError("Invalid NPC perspective.")
        identities.extend(e.entry_id for e in entries)
    for event in state.events:
        identities.append(event.event_id)
        if (event.location_id not in locations or set(event.listeners) - npcs
                or (event.npc_id is not None and event.npc_id not in npcs)
                or (event.thread_id is not None and event.thread_id not in thread_ids)):
            raise ValueError("Invalid adventure event reference.")
        if event.private and set(event.listeners) - {event.npc_id}:
            raise ValueError("Private event leaked listeners.")
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate interaction identity.")
    if state.plan and (state.plan.location_id not in locations
                       or state.plan.cursor > len(state.plan.steps)):
        raise ValueError("Invalid plan progress.")
    if state.plan:
        if ((state.plan.status == "completed" and state.plan.cursor != len(state.plan.steps))
                or (state.plan.status in {"paused", "awaiting_confirmation"}
                    and state.plan.cursor == len(state.plan.steps))):
            raise ValueError("Plan status and cursor disagree.")
        for index, step in enumerate(state.plan.steps):
            if step.depends_on is not None and step.depends_on >= index:
                raise ValueError("Cyclic plan dependency.")


def route_valid(world, route):
    target, kind = route["target"], route["kind"]
    if kind == "visit":
        return target in world.get("locations", {})
    if kind in {"talk", "defeat"}:
        return any(n.get("id") == target for n in world.get("npcs", []))
    if kind == "acquire":
        return target == "Kılıç"  # Existing inventory owner only.
    if kind == "fact":
        return target in known_evidence(world)
    return False


def grounded_goal_routes(world, quote, routes):
    """Only narrow explicit action goals can authorize automatic completion.

    Merely proposing 'talk to X' cannot prove a broader 'is X corrupt?' goal.
    """
    value = normalize(quote)
    patterns = {
        "visit": r"\b(?:gitmek|ulasmak|ziyaret|varmak|go|reach|visit)\b",
        "talk": r"\b(?:konusmak|gorusmek|sormak|talk|speak|meet)\b",
        "acquire": r"\b(?:almak|edinmek|acquire|get|obtain)\b",
        "defeat": r"\b(?:yenmek|alt etmek|defeat)\b",
    }
    accepted = []
    for route in routes:
        kind, target = route["kind"], route["target"]
        if not route_valid(world, route):
            continue
        if kind == "fact":
            # Future fact owners supply predicate-aware goal bindings, not an
            # arbitrary model-selected fact ID meaning "the entire goal is done".
            continue
        names = [target]
        if kind == "visit":
            record = world.get("locations", {}).get(target, {})
            names += [record.get("name", ""), *record.get("aliases", [])]
        elif kind in {"talk", "defeat"}:
            record = next((n for n in world.get("npcs", []) if n.get("id") == target), {})
            names += [record.get("name", ""), *record.get("aliases", [])]
        if re.search(patterns[kind], value) and any(
                normalize(name) and normalize(name) in value for name in names):
            accepted.append(route)
    return accepted


def known_evidence(world):
    # Only accepted player-visible evidence; no hidden NPC/world truth.
    return {
        e["event_id"] for e in get(world)["events"]
        if e["player_known"] and e["kind"] in {"objective_progress", "witnessed_fact"}
    } | {
        item["fact_id"] for item in world.get("player_knowledge", [])
        if isinstance(item, dict) and isinstance(item.get("fact_id"), str)
        and item.get("authority") == "python_engine"
    }


def present_npcs(world):
    return [n for n in world.get("npcs", []) if isinstance(n, dict)
            and n.get("location") == world.get("location")
            and n.get("status", "active") not in {"dead", "unconscious", "defeated"}
            and n.get("current_hp", 1) > 0]


def perspective(world, npc):
    if not isinstance(npc, dict):
        return None
    entries = get(world)["perspectives"].get(npc["id"], [])
    return {
        "npc_id": npc["id"], "name": npc.get("name"), "role": npc.get("role"),
        "personality": npc.get("personality"),
        # Legacy free-form knowledge/memory/secret strings are not verified facts.
        "entries": [copy.deepcopy(e) for e in entries if not e["secret"]],
    }


def record_witness(world, event_id, text, npc_ids):
    """Narrow later-owner interface: require an existing accepted visible event."""
    state = get(world)
    event = next((e for e in state["events"] if e["event_id"] == event_id), None)
    if not event or event["kind"] not in {"objective_progress", "witnessed_fact"}:
        raise ValueError("Witness facts require accepted engine event provenance.")
    if not text or len(text) > 400 or set(npc_ids) - set(event["listeners"]):
        raise ValueError("Unjustified witness knowledge.")
    for npc_id in npc_ids:
        entries = state["perspectives"].setdefault(npc_id, [])
        if any(e["source_id"] == event_id and e["kind"] == "witnessed" for e in entries):
            continue
        entries.append(PerspectiveEntry(
            entry_id=f"perspective:{uuid4().hex}", kind="witnessed",
            text=text, source_id=event_id,
        ).model_dump())
        state["perspectives"][npc_id] = entries[-24:]
    validate(state, {**world, KEY: state})
    world[KEY] = state


def bind_deadline(world, thread_id, scheduled_event_id):
    """Consume a registered schedule boundary; never invent/advance time here."""
    state = get(world)
    thread = _thread(state, thread_id)
    event = next((e for e in world.get("scheduled_events", [])
                  if e.get("event_id") == scheduled_event_id), None)
    if not thread or not event or type(event.get("window_end")) is not int:
        raise ValueError("Deadline needs an existing authoritative schedule.")
    thread["deadline"] = event["window_end"]
    validate(state, {**world, KEY: state})
    world[KEY] = state


def public(world):
    state = get(world)
    threads = copy.deepcopy(state["threads"])
    for thread in threads:
        thread["objectives"] = [o for o in thread["objectives"] if not o["hidden"]]
    return {
        "threads": threads, "commitments": copy.deepcopy(state["commitments"]),
        "plan": copy.deepcopy(state["plan"]),
        "recent_events": [copy.deepcopy(e) for e in state["events"][-12:]
                          if e["player_known"]],
    }


def generation_eligible(world):
    state = get(world)
    turn = world.get("flags", {}).get("turn_index", 0)
    return (not world.get("combat", {}).get("active")
            and len(state["threads"]) < MAX_THREADS
            and sum(t["status"] in ACTIVE for t in state["threads"]) < 3
            and turn - state["last_generation_turn"] >= 5
            and bool(present_npcs(world)))


def context(world, npc):
    state = get(world)
    threads = public(world)["threads"]
    if npc:
        heard = {entry["text"] for entry in state["perspectives"].get(npc["id"], [])
                 if entry["kind"] == "player_claim"}
        visible = {e["thread_id"] for e in state["events"] if npc["id"] in e["listeners"]}
        threads = [
            {key: t[key] for key in ("thread_id", "title", "origin", "location_id", "npc_id")}
            for t in threads if t["npc_id"] == npc["id"] or t["thread_id"] in visible
            or t["title"] in heard
        ]
    addressee = perspective(world, npc)
    if isinstance(addressee, dict) and isinstance(npc, dict):
        addressee = copy.deepcopy(addressee)
        addressee["name"] = living_world.public_npc_name(npc)
        addressee["role"] = living_world.public_npc_role(npc)
    return {
        "location_id": world.get("location"),
        "actors": [
            {
                "npc_id": n["id"],
                "name": living_world.public_npc_name(n),
                "role": living_world.public_npc_role(n),
            }
            for n in present_npcs(world)
        ],
        "addressee": addressee,
        "conversation_focus": current_conversation_focus(world, npc),
        "threads": threads,
        "commitments": [
            {key: c[key] for key in ("commitment_id", "npc_id", "quote", "kind", "thread_id")}
            for c in state["commitments"] if npc and c["npc_id"] == npc["id"]
        ],
        "evidence_ids": sorted(
            known_evidence(world) if not npc else
            known_evidence(world) & {e["source_id"] for e in state["perspectives"].get(npc["id"], [])
                                     if e["kind"] == "witnessed" and not e["secret"]}
        ),
        "generation_allowed": generation_eligible(world),
        "recent_categories": state["novelty"] if not npc else [],
        "time": world.get("campaign_time", {}).get("elapsed_seconds", 0),
    }


def compound_plan(text):
    """Source-bound intentions, never actions. Only complete first-person clauses.

    Quoted speech is opaque; separators and verb suffixes inside it cannot turn
    a quotation or a noun list into a plan. Conditions remain unevaluated.
    """
    if not isinstance(text, str):
        return None
    masked = re.sub(r'"[^"]*"|“[^”]*”', lambda m: " " * len(m[0]), text)
    boundaries = list(re.finditer(r"[,;\n]+|\b(?:sonra|ardından|ardindan|ve|then)\b", masked, re.I))
    if not boundaries:
        return None
    action = re.compile(
        r"\b[a-z]{2,}(?:eyim|ayim|elim|alim|ecegim|acagim|iyorum|uyorum)\b[.! ]*$"
    )
    condition = re.compile(r"[a-z]{3,}(?:ince|inca|unca|unce|sam|sem|sa|se)$")
    steps, start, pending = [], 0, None
    for boundary in [*boundaries, None]:
        end = boundary.start() if boundary else len(text)
        clause = text[start:end].strip()
        visible = masked[start:end]
        if not clause:
            start = boundary.end() if boundary else end
            continue
        conditions = [m for m in re.finditer(r"\w+", visible)
                      if condition.fullmatch(normalize(m[0]))]
        if action.search(normalize(visible)):
            quote = text[pending if pending is not None else start:end].strip()
            # Offsets are in the original source, never accent-folded text.
            precondition = text[start:start + conditions[0].end()].strip() if conditions else ""
            if pending is not None:
                precondition = text[pending:start].strip(" ,;\n")
            steps.append({"quote": quote, "depends_on": len(steps) - 1 if steps else None,
                          "precondition": precondition})
            pending = None
        elif conditions and not visible[conditions[-1].end():].strip(" ."):
            pending = start if pending is None else pending
        else:
            return None
        start = boundary.end() if boundary else end
    if pending is not None or len(steps) < 2:
        return None
    # Do not truncate oversized plans: the existing strict envelope rejects them.
    return {"operation": "plan", "quote": text, "steps": steps, "privacy": "private"}


def hint(text, npc=None):
    """Coarse routing hints only; the generic model envelope carries semantics."""
    if compound_plan(text) is not None:
        return "plan"
    value = normalize(text)
    categories = (
        ("plan", r"\b(?:planim|planliyorum|once .+ sonra|eger .+ sonra|after .+ then|if .+ then)\b"),
        ("continue_plan", r"\b(?:plana devam|siradaki adim|continue (?:the )?plan)\b"),
        ("goal", r"\b(?:hedefim|amacim|arastirmak istiyorum|ogrenmek istiyorum|my goal|i want to (?:find out|investigate))\b"),
        ("negotiate", r"\b(?:altin istemiyorum|para istemiyorum|pazarlik|karsiliginda|kilicini|kilici ver|give me (?:your|the) sword|don't want the gold)\b"),
        ("switch_side", r"\b(?:taraf (?:degistir|degistiriyorum)|onlara katil|haydutlara yardim|help the bandits|work with the bandits|change sides)\b"),
        ("reframe", r"\b(?:hedefi degistir|yeniden cerceve|reframe)\b"),
        ("abandon", r"\b(?:vazgec|birakiyorum|terk ediyorum|abandon)\b"),
        ("refuse", r"\b(?:reddediyorum|guvenmiyorum|kabul etmiyorum|don't trust|refuse)\b"),
        ("promise", r"\b(?:soz veriyorum|soz ver|yemin|i promise|i'll help)\b"),
        ("conditional", r"\b(?:yardim ederim ama|yalnizca .+ olursa|only if|but first)\b"),
        ("delay", r"\b(?:sonra konusalim|daha sonra|not now|later)\b"),
        ("generate", r"\b(?:is (?:var mi|ariyorum)|bir is|yardima ihtiyacin|macera (?:ariyorum|istiyorum)|looking for work)\b"),
    )
    for operation, pattern in categories:
        if re.search(pattern, value):
            return operation
    if npc and re.search(r"\b(?:fisilda|fisildiyorum|whisper|sembol|symbol|ne biliyorsun|what do you know)\b", value):
        return "information"
    return None


def immersive_unknown(npc=None):
    if npc:
        return f'{living_world.public_npc_name(npc)} başını hafifçe sallıyor. “Bunu kendi gözlerimle görmedim.”'
    return "Şu ana kadar gördüklerin bu düşünceyi doğrulamıyor. Nasıl ilerlemek istediğin sana kalmış."


def safe_narration(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 2400:
        return False
    return not re.search(
        r"\b(?:python|qwen|backend|frontend|server|sunucu|canonical|kanonik|veritabani|"
        r"database|model|yapay zeka|unsupported|desteklenmiyor|insufficient data|"
        r"access to (?:data|information)|bilgiye erisim|veriye erisim)\b",
        normalize(text),
    )


def outcome_consistent(result, text):
    """Interaction records intent, not these deferred physical/social outcomes."""
    if not safe_narration(text):
        return False
    value = normalize(text)
    if re.search(
        r"(?:\b(?:gorev|hedef|quest|objective)\b.{0,45}\b(?:tamamland\w*|completed|succeeded)\b"
        r"|\b(?:kilic|esya|item|sword)\b.{0,55}\b(?:artik senin|sana ver\w*|senin oldu|now yours)\b)",
        value,
    ):
        return False
    if result.get("npc_consent") is False and re.search(
        r"\b(?:kabul ediyor|kabul etti|onayliyor|onayladi|accepts|agrees)\b", value
    ):
        return False
    if result.get("operation") in {"plan", "continue_plan"} and re.search(
        r"\b(?:bekliyorsun|giriyorsun|suzuluyorsun|ariyorsun|you (?:enter|wait|search|sneak))\b",
        value,
    ):
        return False
    return True


def _event(world, state, kind, summary, npc=None, thread=None, privacy="addressed",
           player_known=True):
    listeners = ([n["id"] for n in present_npcs(world)] if privacy == "public"
                 else [npc["id"]] if npc else [])
    event = Event(
        event_id=f"interaction:{uuid4().hex}", kind=kind,
        turn=world.get("flags", {}).get("turn_index", 0),
        at=world.get("campaign_time", {}).get("elapsed_seconds", 0),
        location_id=world["location"], npc_id=npc["id"] if npc else None,
        thread_id=thread["thread_id"] if thread else None,
        listeners=listeners, private=privacy == "private",
        player_known=player_known, summary=summary[:400],
    ).model_dump()
    state["events"] = [*state["events"], event][-MAX_EVENTS:]
    return event


def _result(operation, status, text, **fields):
    return {"action": "interaction", "operation": operation, "status": status,
            "success": status in {"recorded", "resolved", "offered", "reframed"},
            "direct_response": text, "state_changes": [], **fields}


def _thread(state, identity):
    return next((t for t in state["threads"] if t["thread_id"] == identity), None)


def _new_thread(world, state, quote, npc=None, *, origin="player", routes=()):
    turn = world.get("flags", {}).get("turn_index", 0)
    thread = Thread(
        thread_id=f"thread:{uuid4().hex}", origin=origin, title=quote[:400],
        status="offered" if origin == "local_proposal" else "active",
        location_id=world["location"], npc_id=npc["id"] if npc else None,
        created_turn=turn, updated_turn=turn,
        objectives=[Objective(
            objective_id=f"objective:{uuid4().hex}", description=quote[:400],
            routes=[Route.model_validate(r) for r in routes],
        )],
    ).model_dump()
    state["threads"].append(thread)
    _event(world, state, "thread_created", quote, npc, thread)
    return thread


def _remember_claim(world, state, quote, npc, privacy):
    event = _event(world, state, "statement_heard", "Söylediklerin konuşmada duyuldu.",
                   npc, privacy=privacy)
    for listener in event["listeners"]:
        entries = state["perspectives"].setdefault(listener, [])
        entry = PerspectiveEntry(entry_id=f"perspective:{uuid4().hex}",
                                 kind="player_claim", text=quote[:400],
                                 source_id=event["event_id"]).model_dump()
        state["perspectives"][listener] = [*entries, entry][-24:]
    return event


def authorize_item_transfer(world, npc, item):
    """Record the NPC's bounded decision, never a model/social-roll outcome."""
    expected = {"operation": "receive", "recipient": "player"}
    if npc.get("item_consents", {}).get(item["item_id"]) == expected:
        return
    if npc.get("item_release_policy", {}).get(item["item_id"]) != expected:
        from equipment_economy import fail
        fail("npc_consent_required")
    state = get(world)
    _event(world, state, "item_consent",
           f'{item["item_id"]}: receive → player', npc)
    validate(state, world)
    world[KEY] = state
    npc.setdefault("item_consents", {})[item["item_id"]] = dict(expected)
    del npc["item_release_policy"][item["item_id"]]


def record_item_dialogue(world, npc, quote):
    state = get(world)
    _remember_claim(world, state, quote, npc, "addressed")
    validate(state, world)
    world[KEY] = state
    return f'{living_world.public_npc_name(npc)} sözlerini duydu.'


def item_request(world, npc, reference):
    """Ownership and explicit existing consent inspection; no social-roll grant."""
    if not npc or not reference:
        return {"owned": False, "transfer_possible": False, "reason": "item_unresolved"}
    inventory = npc.get("inventory")
    # Equipment fallback/defaults are not inventory ownership evidence.
    owned = isinstance(inventory, list) and any(
        normalize(reference) in {normalize(i.get("item_id", "")),
                                normalize(i.get("name", "")),
                                normalize(i.get("weapon_id", ""))}
        if isinstance(i, dict) else normalize(reference) == normalize(i)
        for i in inventory
    )
    consented = owned and any(
        isinstance(i, dict) and normalize(reference) in {
            normalize(i["item_id"]), normalize(i["name"]), normalize(i.get("weapon_id", ""))}
        and npc.get("item_consents", {}).get(i["item_id"]) == {
            "operation": "receive", "recipient": "player"}
        for i in inventory
    )
    return {"owned": bool(owned), "transfer_possible": bool(consented),
            "reason": None if consented else "npc_consent_required" if owned else "not_owned"}


def resolve(session, player_input, raw, npc=None, fallback_operation=None):
    """Validate a proposed intention and commit only bounded Python transitions."""
    world = session.world_state
    try:
        if isinstance(raw, dict) and isinstance(raw.get("candidates"), list):
            if len(raw["candidates"]) > 3:
                raise ValueError("Too many creative proposals.")
            cleaned = []
            for candidate in raw["candidates"]:
                try:
                    cleaned.append(Candidate.model_validate(candidate).model_dump())
                except (ValidationError, TypeError):
                    continue
            raw = {**raw, "candidates": cleaned}
        envelope = Envelope.model_validate(raw)
    except (ValueError, TypeError):
        return _result("unknown", "proposal_rejected", immersive_unknown(npc),
                       reason_code="invalid_interaction_proposal")
    data = envelope.model_dump()
    operation = data["operation"]
    if operation == "none":
        return _result(operation, "no_effect", immersive_unknown(npc))
    quote = data["quote"]
    # Keep Unicode/original phrasing; accent folding is for routing only.
    if not quote or quote not in player_input:
        return _result(operation, "proposal_rejected", immersive_unknown(npc),
                       reason_code="ungrounded_player_intent")
    if fallback_operation and operation != fallback_operation and operation not in {
            "request", "negotiate", "conditional", "promise", "information", "plan"}:
        return _result(operation, "proposal_rejected", immersive_unknown(npc),
                       reason_code="mismatched_player_intent")
    if data["privacy"] == "public" and not re.search(
            r"\b(?:herkese|herkesin|yuksek sesle|public|everyone|aloud)\b", normalize(player_input)):
        data["privacy"] = "addressed"
    if re.search(r"\b(?:fisild\w*|whisper\w*)\b", normalize(player_input)):
        data["privacy"] = "private"
    if world.get("location") not in world.get("locations", {}):
        return _result(operation, "no_effect", "Önce maceranın başlayacağı yeri seçmelisin.")
    if world.get("combat", {}).get("active"):
        return _result(operation, "blocked", "Önündeki çatışma dikkatini bütünüyle istiyor.")
    state = get(world)
    thread = _thread(state, data["thread_id"])
    if data["thread_id"] and thread is None:
        return _result(operation, "proposal_rejected", immersive_unknown(npc),
                       reason_code="unknown_thread")
    if len(state["threads"]) >= MAX_THREADS and operation in {"goal", "generate"}:
        return _result(operation, "no_effect", "Önce yarım kalan işlerinden birine dönmek isteyebilirsin.")
    before = copy.deepcopy(state)
    result = None
    if operation == "goal":
        existing = next((t for t in state["threads"] if t["title"] == quote[:400]
                         and t["origin"] == "player"), None)
        if any(not route_valid(world, r) for r in data["routes"]):
            return _result(operation, "proposal_rejected", immersive_unknown(npc),
                           reason_code="invalid_objective_route")
        thread = existing or _new_thread(
            world, state, quote, npc,
            routes=grounded_goal_routes(world, quote, data["routes"]),
        )
        result = _result(operation, "recorded", "Bu sorunun peşini bırakmamaya karar veriyorsun.",
                         thread_id=thread["thread_id"])
    elif operation in {"promise", "conditional"}:
        if not npc or len(state["commitments"]) >= 64:
            return _result(operation, "no_effect", "Sözünü kime yönelttiğin henüz belli değil.")
        existing = next((c for c in state["commitments"] if c["npc_id"] == npc["id"]
                         and c["quote"] == quote[:400] and c["status"] == "open"), None)
        if not existing:
            commitment = Commitment(
                commitment_id=f"commitment:{uuid4().hex}", npc_id=npc["id"],
                quote=quote[:400], thread_id=data["thread_id"],
                kind="conditional" if operation == "conditional" else "promise",
                created_turn=world["flags"]["turn_index"],
                updated_turn=world["flags"]["turn_index"],
            ).model_dump()
            state["commitments"].append(commitment)
            _event(world, state, "commitment_made", "Aranızda bir söz kaldı.", npc, thread,
                   data["privacy"])
        result = _result(operation, "recorded", f'{living_world.public_npc_name(npc)} sözlerini dikkatle dinliyor. Henüz bir şey yerine getirilmiş değil.')
    elif operation in {"negotiate", "request", "threat"}:
        inspected = item_request(world, npc, data["requested_item"])
        if operation == "request" and inspected["owned"]:
            import equipment_economy
            import shlex
            transfer = equipment_economy.execute(
                session, f'/item request {shlex.quote(data["requested_item"])} {npc["id"]}',
                advance_turn=False,
            )
            if transfer["action_result"]["success"]:
                # resolve() returns an action result, not the command turn envelope.
                # Keep the existing turn/narration/persistence owners in control.
                return _result(
                    operation, "resolved", transfer["narration"],
                    npc_id=npc["id"], npc_consent=True,
                    item_validation={"owned": True, "transfer_possible": True, "reason": None},
                    state_changes=transfer["action_result"]["state_changes"],
                )
        text = (f'{living_world.public_npc_name(npc)} elindekini bırakmıyor. “Önce ne istediğimizi açıkça konuşalım.”'
                if npc else "Teklifini kime yönelttiğini açıkça belirtmen gerekiyor.")
        result = _result(operation, "pending", text, requested_item=data["requested_item"],
                         rejected_consideration=data["rejected_consideration"],
                         item_validation=inspected, npc_consent=False)
        if npc:
            _event(world, state, "negotiation", "Aranızda bir teklif konuşuldu; değiş tokuş yapılmadı.",
                   npc, thread, data["privacy"])
    elif operation == "information":
        entries = perspective(world, npc)
        entry = next((e for e in (entries or {}).get("entries", [])
                      if e["entry_id"] == data["evidence_id"]), None)
        text = immersive_unknown(npc)
        if entry:
            prefix = {"belief": "Bana kalırsa", "rumor": "Duyduğuma göre",
                      "lie": "Sana söyleyebileceğim şu", "player_claim": "Senin söylediğin",
                      "witnessed": "Gördüğüm şu"}[entry["kind"]]
            text = f'{living_world.public_npc_name(npc)}: “{prefix}: {entry["text"]}”'
        result = _result(operation, "answered", text)
        if npc:
            _remember_claim(world, state, quote, npc, data["privacy"])
    elif operation in {"refuse", "delay", "abandon", "agree", "switch_side", "betray", "reframe"}:
        if thread and thread["status"] in TERMINAL:
            return _result(operation, "no_effect", "Bu iş artık geride kaldı; yeni bir amaç seçebilirsin.")
        if operation == "reframe":
            if not thread or data["evidence_id"] not in known_evidence(world):
                return _result(operation, "no_effect", "Bu düşünceni destekleyen yeni bir iz henüz bulmadın.")
            thread["title"] = quote[:400]
            thread["status"] = "reframed"
            thread["reframing_evidence"] = data["evidence_id"]
            if data["routes"]:
                if any(not route_valid(world, r) for r in data["routes"]):
                    return _result(operation, "proposal_rejected", immersive_unknown(npc))
                # Keep existing legitimate routes; a missed clue need not dead-end.
                for objective in thread["objectives"]:
                    for route in grounded_goal_routes(world, quote, data["routes"]):
                        if route not in objective["routes"] and len(objective["routes"]) < 4:
                            objective["routes"].append(route)
        elif operation in {"switch_side", "betray"}:
            side = next((n for n in present_npcs(world) if n["id"] == data["side_id"]), None)
            if not thread or not side or not any(
                    normalize(alias) in normalize(player_input)
                    for alias in [side.get("name", ""), *side.get("aliases", [])] if alias):
                return _result(operation, "no_effect", "Kimin yanında durmak istediğini açıkça belirt.")
            thread["allegiance_id"] = side["id"]
            thread["status"] = "reframed"
            if operation == "betray":
                for commitment in state["commitments"]:
                    if commitment["thread_id"] == thread["thread_id"] and commitment["status"] == "open":
                        commitment["status"] = "broken"
                        commitment["updated_turn"] = world["flags"]["turn_index"]
        elif thread and operation in {"refuse", "abandon"}:
            thread["status"] = "abandoned"
            for commitment in state["commitments"]:
                if commitment["thread_id"] == thread["thread_id"] and commitment["status"] == "open":
                    commitment["status"] = "broken"
                    commitment["updated_turn"] = world["flags"]["turn_index"]
        elif thread and operation == "agree":
            thread["status"] = "active"
        if thread:
            thread["updated_turn"] = world["flags"]["turn_index"]
        if operation == "abandon" and state["plan"]:
            state["plan"]["status"] = "abandoned"
        _event(world, state, operation, quote, npc, thread, data["privacy"])
        result = _result(operation, "reframed" if operation == "reframe" else "recorded",
                         "Kararını açıkça ortaya koyuyorsun. Sonraki adımın hâlâ sana ait.")
    elif operation == "plan":
        steps = data["steps"]
        reason = "plan_empty_steps" if not steps else None
        for index, step in enumerate(steps):
            if step["quote"] not in player_input:
                reason = "plan_ungrounded_step"
            elif step["precondition"] and step["precondition"] not in player_input:
                reason = "plan_ungrounded_condition"
            elif step["depends_on"] is not None and step["depends_on"] >= index:
                reason = "plan_invalid_dependency"
            if reason:
                break
        if reason:
            return _result(operation, "proposal_rejected", "Planındaki adımları biraz daha açık anlat.",
                           reason_code=reason)
        state["plan"] = Plan(plan_id=f"plan:{uuid4().hex}", goal=quote[:400],
                             steps=steps, cursor=0, status="awaiting_confirmation",
                             location_id=world["location"]).model_dump()
        _event(world, state, "plan_recorded", "Adımlarını düşündün; henüz yola koyulmadın.")
        result = _result(operation, "recorded",
                         f'İlk adımın: {steps[0]["quote"]}. Bunu denemek için hamleni söyle; diğer adımlar bekleyebilir.')
    elif operation == "continue_plan":
        plan = state["plan"]
        if not plan or plan["status"] in {"completed", "abandoned"}:
            return _result(operation, "no_effect", "Devam edeceğin bir plan henüz yok.")
        step = plan["steps"][plan["cursor"]]
        plan["status"] = "awaiting_confirmation"
        result = _result(operation, "pending", f'Sıradaki adımın: {step["quote"]}. Denemek istediğinde kendi hamleni söyle.')
    elif operation == "generate":
        if generation_eligible(world):
            for candidate in data["candidates"]:
                accepted = accept_candidate(world, state, candidate)
                if accepted:
                    thread = accepted
                    break
        if thread:
            result = _result(operation, "offered", thread["title"], thread_id=thread["thread_id"])
        else:
            result = _result(operation, "no_effect", "Şimdilik yeni bir iş çıkmıyor; sohbet olağan akışında sürüyor.")
    if result is None:
        result = _result(operation, "no_effect", immersive_unknown(npc))
    if npc and operation != "information":
        _remember_claim(world, state, quote, npc, data["privacy"])
    if state != before:
        validate(state, {**world, KEY: state})
        world[KEY] = state
        result["state_changes"] = [f"world.{KEY}"]
    return result


def accept_candidate(world, state, candidate):
    npc = next((n for n in present_npcs(world) if n["id"] == candidate["npc_id"]), None)
    local_ids = {n["id"] for n in present_npcs(world)}
    if (not npc or npc.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
            or candidate["location_id"] != world["location"]
            or any(not route_valid(world, r) for r in candidate["routes"])
            or any(r["kind"] not in {"talk", "visit"}
                   or (r["kind"] == "talk" and r["target"] not in local_ids)
                   or (r["kind"] == "visit" and r["target"] != world["location"])
                   for r in candidate["routes"])
            or candidate["impact"] != "local"
            or (candidate["evidence_id"] is not None
                and candidate["evidence_id"] not in known_evidence(world))):
        return None
    kind = candidate["kind"]
    # Novelty truth is derived from accepted structure, not model-supplied tags.
    novelty = Novelty(
        theme=kind, conflict=kind, motivation=kind,
        objective_structure="|".join(sorted({r["kind"] for r in candidate["routes"]})),
        location_id=world["location"], antagonist="none", reward_pattern="none",
        resolution_style="|".join(sorted({r["kind"] for r in candidate["routes"]})),
        turn=world["flags"]["turn_index"],
    ).model_dump()
    if any(old["theme"] == novelty["theme"]
           and old["objective_structure"] == novelty["objective_structure"]
           and old["location_id"] == novelty["location_id"] for old in state["novelty"][-8:]):
        return None
    titles = {
        "inquiry": f'{living_world.public_npc_name(npc)} ile cevap bekleyen bir sorunun peşine düşebilirsin.',
        "cooperation": f'{living_world.public_npc_name(npc)} birlikte hareket etme olasılığını konuşmak istiyor.',
        "dispute": f'{living_world.public_npc_name(npc)} farklı görüşleri sakin biçimde ele almayı teklif ediyor.',
        "warning": f'{living_world.public_npc_name(npc)} temkinli davranmanı öneriyor; ayrıntıları kendisine sorabilirsin.',
        "meeting": f'{living_world.public_npc_name(npc)} burada seninle görüşmek istiyor.',
    }
    thread = _new_thread(world, state, titles[kind], npc, origin="local_proposal",
                         routes=candidate["routes"])
    state["novelty"] = [*state["novelty"], novelty][-16:]
    state["last_generation_turn"] = world["flags"]["turn_index"]
    return thread


def _newly_acquired(world, before_world, target):
    """Use the existing equipment owner's labels for legacy and instance items."""
    after = equipment_economy.labels(world.get("inventory", []))
    before = equipment_economy.labels(before_world.get("inventory", []))
    return after.count(target) > before.count(target)


_VERIFIED_OUT_OF_COMBAT = frozenset({"unconscious", "defeated", "dead"})


def _defeated(npc):
    """A defeat goal follows Python's verified out-of-combat status.

    Current combat_status wins. Old saves that only stored the legacy status
    field still count. Zero HP does not invent a defeat while a status says
    the NPC is active.
    """
    if not isinstance(npc, dict):
        return False
    combat_status = npc.get("combat_status")
    if isinstance(combat_status, str):
        return combat_status in _VERIFIED_OUT_OF_COMBAT
    legacy_status = npc.get("status")
    if isinstance(legacy_status, str):
        return legacy_status in _VERIFIED_OUT_OF_COMBAT
    current_hp = npc.get("current_hp", 1)
    return type(current_hp) is int and current_hp <= 0


def _newly_defeated(world, before_world, target):
    before = next((n for n in before_world.get("npcs", [])
                   if n.get("id") == target), None)
    after = next((n for n in world.get("npcs", [])
                  if n.get("id") == target), None)
    return before is not None and after is not None and not _defeated(before) and _defeated(after)


def consume(session, action_result, before_world, player_input=""):
    """Consume resolved evidence/time once, inside the existing turn transaction."""
    world = session.world_state
    if KEY not in world:
        return
    state = get(world)
    turn = world["flags"]["turn_index"]
    now = world.get("campaign_time", {}).get("elapsed_seconds", 0)
    old_now = before_world.get("campaign_time", {}).get("elapsed_seconds", now)
    before = copy.deepcopy(state)
    for thread in state["threads"]:
        if thread["status"] not in ACTIVE:
            continue
        if thread["deadline"] is not None and old_now < thread["deadline"] <= now:
            thread.update(status="expired", updated_turn=turn)
            _event(world, state, "thread_expired", "Bu fırsatın zamanı geçti.",
                   thread=thread, player_known=thread["location_id"] == world["location"])
            continue
        if thread["status"] == "offered":
            continue
        for objective in thread["objectives"]:
            if objective["status"] == "completed":
                continue
            for route in objective["routes"]:
                kind, target = route["kind"], route["target"]
                matched = (
                    (kind == "visit" and action_result.get("action") == "travel"
                     and action_result.get("status") == "completed"
                     and before_world.get("location") != world["location"]
                     and target == world["location"])
                    or (kind == "talk" and action_result.get("action") == "dialogue"
                        and action_result.get("npc_id") == target
                        and action_result.get("success") is True)
                    or (kind == "acquire" and _newly_acquired(world, before_world, target))
                    or (kind == "defeat" and _newly_defeated(world, before_world, target))
                    or (kind == "fact" and target in known_evidence(world)
                        and target not in known_evidence(before_world))
                )
                if matched:
                    objective["status"] = "completed"
                    event = _event(world, state, "objective_progress",
                                   "İzlediğin yolda somut bir adım attın.", thread=thread)
                    objective["evidence_id"] = event["event_id"]
                    thread.update(status="progressing", updated_turn=turn)
                    break
        required = [o for o in thread["objectives"] if not o["optional"]]
        if required and all(o["status"] == "completed" for o in required):
            thread.update(status="succeeded", updated_turn=turn)
            _event(world, state, "thread_succeeded", "Bu işin sonuna geldin.", thread=thread)
            for commitment in state["commitments"]:
                if (commitment["thread_id"] == thread["thread_id"] and commitment["kind"] == "promise"
                        and commitment["status"] == "open"
                        and grounded_goal_routes(world, commitment["quote"],
                                                 [r for o in thread["objectives"] for r in o["routes"]])):
                    commitment.update(status="fulfilled", updated_turn=turn)
    plan = state["plan"]
    if plan and plan["status"] not in {"abandoned", "completed"}:
        if (world.get("combat", {}).get("active") or world["location"] != plan["location_id"]
                or action_result.get("success") is False
                or plan["steps"][plan["cursor"]]["precondition"]):
            # Free-form conditions have no predicate owner here. Never mark
            # them satisfied merely because the subsequent action succeeded.
            plan["status"] = "paused"
        elif (plan["steps"][plan["cursor"]]["quote"] == player_input
              and action_result.get("success") is True
              and action_result.get("status") in {"completed", "resolved"}
              and action_result.get("action") not in {"interaction", "narrative"}):
            plan["cursor"] += 1
            plan["status"] = ("completed" if plan["cursor"] == len(plan["steps"])
                              else "awaiting_confirmation")
    if state != before:
        validate(state, {**world, KEY: state})
        world[KEY] = state
        action_result.setdefault("state_changes", []).append(f"world.{KEY}")


def initiative_beat(world):
    """A selective local reminder, not an NPC simulation or model conversation."""
    if KEY not in world or world.get("combat", {}).get("active"):
        return None
    state = get(world)
    turn = world["flags"]["turn_index"]
    if turn - state["last_beat_turn"] < 5:
        return None
    npc_ids = {n["id"] for n in present_npcs(world)}
    candidate = next((c for c in state["commitments"]
                      if c["npc_id"] in npc_ids and c["status"] in {"open", "broken"}
                      and turn - c["updated_turn"] >= 5), None)
    if not candidate:
        return None
    npc = next(n for n in present_npcs(world) if n["id"] == candidate["npc_id"])
    known_broken = candidate["status"] == "broken" and any(
        e["kind"] in {"betray", "abandon", "refuse"} and e["thread_id"] == candidate["thread_id"]
        and npc["id"] in e["listeners"] for e in state["events"]
    )
    summary = (f'{living_world.public_npc_name(npc)} aranızda kalan sözü unutmamış.' if known_broken
               else f'{living_world.public_npc_name(npc)} verdiğin sözü hatırlatıyor.')
    event = _event(world, state, "callback", summary, npc)
    state["last_beat_turn"] = turn
    world[KEY] = state
    return event