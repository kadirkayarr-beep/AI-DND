"""Pure, bounded Narrative Director memory.

This module deliberately has no engine or persistence dependencies.  It stores
only continuity hints and player utterances; canonical state remains owned by
the engine and is never reconstructed from prose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from typing import Any


NARRATIVE_MEMORY_SCHEMA_VERSION = 1
MAX_RECENT_TURNS = 6
MAX_TEXT = 280
MAX_TOPIC = 120
MAX_ENTITIES = 200
MAX_INTERACTIONS_PER_ENTITY = 20
MAX_LOCATION_FACTS = 12
MAX_THREADS = 40
MAX_FINGERPRINTS = 12
MAX_SERIALIZED_BYTES = 64 * 1024

_SECRET_KEYS = ("OLLAMA_HOST", "OLLAMA_PROXY_TOKEN", "SESSION_SECRET")
_PROMISE_RE = re.compile(
    r"\b(?:i\s+promise|i(?:'ll| will)|promise|"
    r"söz\s+veriyorum|söz|yapacağım|edeceğim|soracağım|"
    r"geri\s+döneceğim|hatırlat(?:acağım|ırım))\b",
    re.IGNORECASE,
)
_FOLLOW_UP_RE = re.compile(
    r"\b(?:later|again|return|follow\s*up|ask|hatırlat|sonra|"
    r"tekrar|geri\s+dön|araştır|öğren)\b",
    re.IGNORECASE,
)
_GENERIC_RE = re.compile(
    r"^(?:hello|hi|hey|merhaba|selam|ok|okay|tamam|teşekkürler|"
    r"thanks|evet|hayır|yes|no)[!. ]*$",
    re.IGNORECASE,
)
_MECHANICAL_RE = re.compile(
    r"\b(?:hp|hit points?|damage|zarar|gold|altın|xp|experience|"
    r"level|seviye|inventory|envanter|item|eşya|quest|görev|"
    r"completed?|tamamlandı|healed?|iyileşti|öldü|dead|death)\b",
    re.IGNORECASE,
)
_THREAD_STOPWORDS = {
    "a", "an", "and", "ask", "again", "i", "ill", "later", "of", "the",
    "to", "will", "you", "about", "it", "bir", "bu", "da", "de", "daha",
    "et", "edeceğim", "edecegim", "mi", "mı", "mu", "mü", "sonra", "söz",
    "veriyorum", "hatırlıyor", "hatirliyor", "musun", "misin", "bunu",
}


def empty_narrative_memory() -> dict[str, Any]:
    """Return a fresh, migration-safe memory envelope."""
    return {
        "schema_version": NARRATIVE_MEMORY_SCHEMA_VERSION,
        "recent_turns": [],
        "story_summary": {
            "current_arc": [],
            "recent_events": [],
            "important_relationships": [],
            "current_location": None,
            "unresolved_threads": [],
            "major_discoveries": [],
            "player_history": [],
        },
        "entity_memory": {"npcs": {}, "locations": {}},
        "npc_interactions": {},
        "location_continuity": {},
        "quest_memory": {},
        "unresolved_threads": [],
        "style_profile": {
            "tone": "immersive high fantasy",
            "description_density": "moderate",
            "dialogue_density": "strong",
            "pace": "variable",
            "darkness": "grounded",
            "humor": "restrained",
            "violence_detail": "restrained",
        },
        "repetition_fingerprint": {
            "recent_openings": [],
            "recent_closings": [],
            "recent_phrases": [],
            "recent_gestures": [],
            "recent_environment_descriptions": [],
        },
    }


def _invalid(error_type: type[Exception], message: str = "Narrative memory is invalid.") -> None:
    raise error_type(message)


def _text(value: Any, limit: int = MAX_TEXT) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _secret_free(value: Any) -> bool:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            strings.extend([str(key)])
            if not _secret_free(child):
                return False
    elif isinstance(value, list):
        for child in value:
            if not _secret_free(child):
                return False
    else:
        return True
    configured = [os.environ[key] for key in _SECRET_KEYS if os.environ.get(key)]
    return not any(secret in text for text in strings for secret in configured)


def validate_narrative_memory(
    value: Any,
    error_type: type[Exception] = ValueError,
) -> dict[str, Any]:
    """Fail closed on malformed, oversized, or secret-bearing memory."""
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        _invalid(error_type)
    expected = set(empty_narrative_memory())
    if set(value) != expected or not _secret_free(value):
        _invalid(error_type)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        _invalid(error_type)
    if len(encoded.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        _invalid(error_type, "Narrative memory is too large.")
    if not isinstance(value["recent_turns"], list) or len(value["recent_turns"]) > MAX_RECENT_TURNS:
        _invalid(error_type)
    for turn in value["recent_turns"]:
        keys = set(turn) if isinstance(turn, dict) else set()
        if keys not in (
            {"player", "narration", "turn_index", "authority"},
            {"player", "narration", "turn_index", "authority", "npc_id"},
        ):
            _invalid(error_type)
        if not _text(turn["player"]) or not _text(turn["narration"]) or type(turn["turn_index"]) is not int:
            _invalid(error_type)
        if "npc_id" in turn and not _text(turn["npc_id"], MAX_TOPIC):
            _invalid(error_type)
        if turn["authority"] != "presentation":
            _invalid(error_type)
    summary = value["story_summary"]
    if (
        not isinstance(summary, dict)
        or set(summary) != {
            "current_arc", "recent_events", "important_relationships",
            "current_location", "unresolved_threads", "major_discoveries",
            "player_history",
        }
    ):
        _invalid(error_type)
    for key in (
        "current_arc", "recent_events", "important_relationships",
        "unresolved_threads", "major_discoveries", "player_history",
    ):
        if not isinstance(summary[key], list) or len(summary[key]) > MAX_THREADS:
            _invalid(error_type)
        for item in summary[key]:
            if not isinstance(item, dict):
                _invalid(error_type)
            if not _text(item.get("text"), MAX_TEXT):
                _invalid(error_type)
            if not _text(item.get("source"), MAX_TOPIC):
                _invalid(error_type)
            if not _text(item.get("authority"), MAX_TOPIC):
                _invalid(error_type)
    if summary["current_location"] is not None and (
        not isinstance(summary["current_location"], dict)
        or not _text(summary["current_location"].get("location_id"), MAX_TOPIC)
        or summary["current_location"].get("authority") != "canonical_reference"
    ):
        _invalid(error_type)
    entities = value["entity_memory"]
    if not isinstance(entities, dict) or set(entities) != {"npcs", "locations"}:
        _invalid(error_type)
    for kind in ("npcs", "locations"):
        records = entities[kind]
        if not isinstance(records, dict) or len(records) > MAX_ENTITIES:
            _invalid(error_type)
        if any(not isinstance(key, str) or not key.strip() for key in records):
            _invalid(error_type)
        for entity_id, record in records.items():
            if not isinstance(record, dict) or record.get("id") != entity_id:
                _invalid(error_type)
            if not _text(record.get("name"), MAX_TOPIC):
                _invalid(error_type)
            if record.get("authority") != "canonical_reference":
                _invalid(error_type)
    for key in ("npc_interactions", "location_continuity"):
        records = value[key]
        if not isinstance(records, dict) or len(records) > MAX_ENTITIES:
            _invalid(error_type)
        for entity_id, entries in records.items():
            if not isinstance(entity_id, str) or not isinstance(entries, list):
                _invalid(error_type)
            if len(entries) > (MAX_INTERACTIONS_PER_ENTITY if key == "npc_interactions" else MAX_LOCATION_FACTS):
                _invalid(error_type)
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("authority") not in {
                    "narrative_continuity", "temporary_narrative_texture",
                }:
                    _invalid(error_type)
                if not _text(entry.get("text"), MAX_TEXT):
                    _invalid(error_type)
    style = value["style_profile"]
    if not isinstance(style, dict) or set(style) != {
        "tone", "description_density", "dialogue_density", "pace",
        "darkness", "humor", "violence_detail",
    } or any(not _text(item, MAX_TOPIC) for item in style.values()):
        _invalid(error_type)
    if not isinstance(value["quest_memory"], dict) or len(value["quest_memory"]) > MAX_ENTITIES:
        _invalid(error_type)
    for quest_id, quest in value["quest_memory"].items():
        if not isinstance(quest_id, str) or not isinstance(quest, dict) or quest.get("quest_id") != quest_id:
            _invalid(error_type)
        if not _text(quest.get("title"), MAX_TOPIC) or quest.get("authority") != "canonical":
            _invalid(error_type)
    threads = value["unresolved_threads"]
    if not isinstance(threads, list) or len(threads) > MAX_THREADS:
        _invalid(error_type)
    for thread in threads:
        if not isinstance(thread, dict) or set(thread) != {
            "thread_id", "related_entity_ids", "summary", "status", "importance",
            "authority", "created_turn", "last_reference_turn",
        }:
            _invalid(error_type)
        if not _text(thread["thread_id"], 128) or not _text(thread["summary"]) or thread["status"] not in {"open", "resolved", "stale"}:
            _invalid(error_type)
        if thread["importance"] not in {"high", "medium"} or thread["authority"] != "narrative_continuity":
            _invalid(error_type)
        if (
            not isinstance(thread["related_entity_ids"], list)
            or any(not isinstance(item, str) for item in thread["related_entity_ids"])
            or type(thread["created_turn"]) is not int
            or type(thread["last_reference_turn"]) is not int
            or thread["created_turn"] < 0
            or thread["last_reference_turn"] < thread["created_turn"]
        ):
            _invalid(error_type)
    fingerprint = value["repetition_fingerprint"]
    if not isinstance(fingerprint, dict) or any(
        not isinstance(fingerprint.get(key), list) or len(fingerprint[key]) > MAX_FINGERPRINTS
        for key in ("recent_openings", "recent_closings", "recent_phrases", "recent_gestures", "recent_environment_descriptions")
    ):
        _invalid(error_type)
    for key in fingerprint:
        if key not in {"recent_openings", "recent_closings", "recent_phrases", "recent_gestures", "recent_environment_descriptions"}:
            _invalid(error_type)
        if any(not _text(item, MAX_TOPIC) for item in fingerprint[key]):
            _invalid(error_type)
    return copy.deepcopy(value)


def _turn_index(world: Any) -> int:
    flags = world.get("flags", {}) if isinstance(world, dict) else {}
    value = flags.get("turn_index", 0) if isinstance(flags, dict) else 0
    return value if type(value) is int and value >= 0 else 0


def _player_visible_npc_name(npc: dict[str, Any]) -> str:
    if npc.get("name_known_to_player", True) is True:
        value = str(npc.get("name", "")).strip()
        if value:
            return value[:MAX_TOPIC]
    return "Yakındaki kişi"


def _player_visible_npc_role(npc: dict[str, Any]) -> str:
    if npc.get("role_known_to_player", True) is True:
        return str(npc.get("role", ""))[:MAX_TOPIC]
    return ""


def _canonical_npcs(world: Any) -> dict[str, dict[str, Any]]:
    npcs = world.get("npcs", []) if isinstance(world, dict) else []
    return {
        npc["id"]: npc for npc in npcs
        if isinstance(npc, dict) and isinstance(npc.get("id"), str) and npc["id"].strip()
    }


def _stable_id(*parts: str) -> str:
    return "thread_" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


def _thread_terms(text: str) -> set[str]:
    """Return deterministic content terms, including light Turkish stems."""
    terms: set[str] = set()
    for word in re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+", text.casefold()):
        if len(word) < 3 or word in _THREAD_STOPWORDS:
            continue
        terms.add(word)
        for suffix in (
            "acağım", "eceğim", "acağını", "eceğini", "mayı", "meyi",
            "ları", "leri", "dan", "den", "dır", "dir", "dır", "dir",
            "ım", "im", "um", "üm", "ı", "i", "u", "ü",
        ):
            if len(word) - len(suffix) >= 4 and word.endswith(suffix):
                terms.add(word[:-len(suffix)])
                break
    return terms


def _thread_intent(text: str) -> bool:
    return bool(_PROMISE_RE.search(text) or _FOLLOW_UP_RE.search(text))


def _summary_record(
    text: str,
    *,
    source: str,
    authority: str,
    turn_index: int,
    **references: Any,
) -> dict[str, Any]:
    return {
        "text": text[:MAX_TEXT],
        "source": source[:MAX_TOPIC],
        "authority": authority[:MAX_TOPIC],
        "turn_index": turn_index,
        **references,
    }


def update_narrative_memory(
    memory: dict[str, Any] | None,
    *,
    player_message: str,
    narration: str,
    action_result: dict[str, Any] | None,
    world_state_before: dict[str, Any],
    world_state_after: dict[str, Any],
    world_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one committed turn to a fresh bounded memory value."""
    base = empty_narrative_memory() if memory is None else copy.deepcopy(memory)
    validate_narrative_memory(base)
    base["repetition_fingerprint"] = copy.deepcopy(
        empty_narrative_memory()["repetition_fingerprint"]
    )
    base["recent_turns"] = [
        {
            **turn,
            "narration": "[presentation omitted from continuity]",
        }
        for turn in base["recent_turns"]
    ]
    if not _text(player_message, 4000) or not _text(narration, 4000):
        raise ValueError("Narrative turn text is invalid.")
    if not isinstance(world_state_before, dict) or not isinstance(world_state_after, dict):
        raise ValueError("Canonical world state is invalid.")
    action = action_result if isinstance(action_result, dict) else {}
    clarification = action.get("status") in {
        "clarification",
        "ambiguous",
        "needs_clarification",
    }
    turn = _turn_index(world_state_after)
    npc_id = action.get("npc_id") or action.get("target_id")
    turn_record = {
        "player": player_message.strip()[:MAX_TEXT],
        "narration": "[presentation omitted from continuity]",
        "turn_index": turn,
        "authority": "presentation",
    }
    if not clarification and isinstance(npc_id, str) and npc_id:
        turn_record["npc_id"] = npc_id
    base["recent_turns"].append(turn_record)
    base["recent_turns"] = base["recent_turns"][-MAX_RECENT_TURNS:]
    for location_id, entries in list(base["location_continuity"].items()):
        base["location_continuity"][location_id] = [
            item
            for item in entries
            if item.get("authority") != "temporary_narrative_texture"
        ][-MAX_LOCATION_FACTS:]

    npcs = _canonical_npcs(world_state_after)
    if not clarification and isinstance(npc_id, str) and npc_id in npcs:
        npc = npcs[npc_id]
        base["entity_memory"]["npcs"][npc_id] = {
            "id": npc_id,
            "name": _player_visible_npc_name(npc),
            "role": _player_visible_npc_role(npc),
            "location_id": str(npc.get("location", ""))[:MAX_TOPIC],
            "authority": "canonical_reference",
        }
        if not _GENERIC_RE.match(player_message.strip()):
            entry = {
                "text": player_message.strip()[:MAX_TEXT],
                "topic": player_message.strip()[:MAX_TOPIC],
                "turn_index": turn,
                "importance": "high" if _PROMISE_RE.search(player_message) else "medium",
                "authority": "narrative_continuity",
                "source": "player_utterance",
            }
            entries = base["npc_interactions"].setdefault(npc_id, [])
            if not any(item["text"] == entry["text"] for item in entries):
                entries.append(entry)
            high = [item for item in entries if item["importance"] == "high"]
            low = [item for item in entries if item["importance"] != "high"]
            base["npc_interactions"][npc_id] = (high + low)[-MAX_INTERACTIONS_PER_ENTITY:]

    location_id = world_state_after.get("location")
    if isinstance(location_id, str) and location_id and location_id != "Henüz belirlenmedi":
        locations = world_state_after.get("locations", {})
        location = locations.get(location_id, {}) if isinstance(locations, dict) else {}
        name = location.get("name") if isinstance(location, dict) else None
        if not isinstance(name, str) or not name.strip():
            name = str(world_metadata.get("location_name", location_id) if isinstance(world_metadata, dict) else location_id)
        base["entity_memory"]["locations"][location_id] = {
            "id": location_id,
            "name": name[:MAX_TOPIC],
            "authority": "canonical_reference",
        }
        continuity = base["location_continuity"].setdefault(location_id, [])
        canonical_text = f"Canonical location: {name}"[:MAX_TEXT]
        if not any(item["text"] == canonical_text for item in continuity):
            continuity.append({
                "text": canonical_text,
                "turn_index": turn,
                "importance": "medium",
                "authority": "narrative_continuity",
                "source": "canonical_location",
            })
        base["location_continuity"][location_id] = continuity[-MAX_LOCATION_FACTS:]
        base["story_summary"]["current_location"] = {
            "location_id": location_id,
            "authority": "canonical_reference",
        }
        base["location_continuity"][location_id] = continuity[:MAX_LOCATION_FACTS]

    if _PROMISE_RE.search(player_message):
        history = base["story_summary"]["player_history"]
        reference = {}
        if not clarification and isinstance(npc_id, str) and npc_id in npcs:
            reference["npc_id"] = npc_id
        history.append(_summary_record(
            player_message,
            source="player_utterance",
            authority="narrative_continuity",
            turn_index=turn,
            **reference,
        ))
        base["story_summary"]["player_history"] = history[-MAX_THREADS:]

    # Quests are copied only from an explicitly canonical source.
    quests = action.get("canonical_quests")
    if isinstance(quests, list):
        for quest in quests:
            if isinstance(quest, dict) and isinstance(quest.get("quest_id"), str) and isinstance(quest.get("title"), str):
                record = copy.deepcopy(quest)
                record["authority"] = "canonical"
                base["quest_memory"][quest["quest_id"]] = record

    # Structured references are accepted only from the action result.  The
    # narrator's prose is deliberately not a source for campaign facts.
    event_references = action.get("event_references")
    if event_references is None:
        event_references = action.get("events")
    if isinstance(event_references, list):
        for event in event_references:
            if not isinstance(event, dict):
                continue
            event_text = event.get("summary") or event.get("text") or event.get("description")
            source = event.get("source")
            if not isinstance(event_text, str) or not event_text.strip() or not isinstance(source, str):
                continue
            npc_ref = event.get("npc_id")
            location_ref = event.get("location_id")
            if isinstance(npc_ref, str) and npc_ref not in npcs:
                continue
            if isinstance(location_ref, str) and location_ref not in base["entity_memory"]["locations"]:
                continue
            references: dict[str, Any] = {}
            if isinstance(npc_ref, str):
                references["npc_id"] = npc_ref
            if isinstance(location_ref, str):
                references["location_id"] = location_ref
            record = _summary_record(
                event_text,
                source=source,
                authority=(
                    "canonical"
                    if event.get("authority") == "canonical"
                    else "narrative_continuity"
                ),
                turn_index=turn,
                **references,
            )
            events = base["story_summary"]["recent_events"]
            if record not in events:
                events.append(record)
            base["story_summary"]["recent_events"] = events[-MAX_THREADS:]

    canonical_events = action.get("canonical_events")
    if isinstance(canonical_events, list):
        for event in canonical_events:
            if (
                isinstance(event, dict)
                and event.get("authority") == "canonical"
                and event.get("event_type") in {"discovery", "major_discovery"}
                and isinstance(event.get("summary"), str)
            ):
                discoveries = base["story_summary"]["major_discoveries"]
                discoveries.append(_summary_record(
                    event["summary"],
                    source="canonical_event",
                    authority="canonical",
                    turn_index=turn,
                    event_type=event["event_type"],
                ))
                base["story_summary"]["major_discoveries"] = discoveries[-MAX_THREADS:]

    if _PROMISE_RE.search(player_message) or _FOLLOW_UP_RE.search(player_message):
        subject = re.sub(r"\s+", " ", player_message.casefold()).strip()[:MAX_TOPIC]
        thread_entity_id = "" if clarification else str(npc_id or "")
        candidate_terms = _thread_terms(player_message)
        existing = None
        for item in base["unresolved_threads"]:
            if item["status"] != "open":
                continue
            if item["related_entity_ids"] != (
                [] if clarification else ([npc_id] if isinstance(npc_id, str) else [])
            ):
                continue
            overlap = candidate_terms & _thread_terms(item["summary"])
            if overlap and _thread_intent(item["summary"]):
                existing = item
                break
        thread_id = _stable_id(thread_entity_id, subject) if existing is None else existing["thread_id"]
        if existing is None:
            base["unresolved_threads"].append({
                "thread_id": thread_id,
                "related_entity_ids": (
                    []
                    if clarification
                    else ([npc_id] if isinstance(npc_id, str) else [])
                ),
                "summary": player_message.strip()[:MAX_TEXT],
                "status": "open",
                "importance": "high" if _PROMISE_RE.search(player_message) else "medium",
                "authority": "narrative_continuity",
                "created_turn": turn,
                "last_reference_turn": turn,
            })
        else:
            existing["last_reference_turn"] = turn
    resolved = action.get("resolved_thread_ids")
    if isinstance(resolved, list):
        for item in base["unresolved_threads"]:
            if item["thread_id"] in resolved:
                item["status"] = "resolved"
    base["unresolved_threads"] = base["unresolved_threads"][-MAX_THREADS:]
    base["story_summary"]["current_arc"] = [
        _summary_record(
            item["thread_id"],
            source="unresolved_thread",
            authority="narrative_continuity",
            turn_index=turn,
            thread_id=item["thread_id"],
        )
        for item in base["unresolved_threads"]
        if item["status"] == "open"
    ][-MAX_THREADS:]

    validate_narrative_memory(base)
    return base


def build_narrative_context(
    memory: dict[str, Any],
    canonical_context: dict[str, Any],
    player_message: str,
    action_result: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a bounded, ID-grounded context packet for a narrator.

    This is intentionally deterministic.  Names are only a convenience for
    selecting a unique entity; IDs are the sole identity used in the packet.
    """
    validate_narrative_memory(memory)
    if not isinstance(canonical_context, dict) or not isinstance(player_message, str):
        raise ValueError("Narrative context inputs are invalid.")
    action = action_result if isinstance(action_result, dict) else {}
    text = player_message.casefold()
    entities = memory["entity_memory"]
    npc_records = entities["npcs"]
    location_records = entities["locations"]
    explicit_ids: set[str] = set()
    for value in (action.get("npc_id"), action.get("target_id"), action.get("location_id")):
        if isinstance(value, str) and value in {**npc_records, **location_records}:
            explicit_ids.add(value)
    for entity_id in {**npc_records, **location_records}:
        if re.search(rf"(?<![\w-]){re.escape(entity_id.casefold())}(?![\w-])", text):
            explicit_ids.add(entity_id)

    mentions: dict[str, list[str]] = {}
    for kind, records in (("npc", npc_records), ("location", location_records)):
        for entity_id, record in records.items():
            name = str(record.get("name", "")).strip().casefold()
            if name and re.search(rf"(?<!\w){re.escape(name)}(?:['’]?[a-zçğıöşü]+)?(?!\w)", text):
                mentions.setdefault(name, []).append(entity_id)
    ambiguities = [
        {"display_name": name, "entity_ids": sorted(ids)}
        for name, ids in sorted(mentions.items())
        if len(ids) > 1
    ]
    for name, ids in mentions.items():
        if len(ids) == 1:
            explicit_ids.add(ids[0])

    current_location = canonical_context.get("location_id") or canonical_context.get("location", {}).get("id")
    if isinstance(current_location, str) and current_location in location_records:
        explicit_ids.add(current_location)
    selected_npcs = sorted(entity_id for entity_id in explicit_ids if entity_id in npc_records)
    selected_locations = sorted(entity_id for entity_id in explicit_ids if entity_id in location_records)
    referenced_threads = [
        thread for thread in memory["unresolved_threads"]
        if (
            any(entity_id in explicit_ids for entity_id in thread["related_entity_ids"])
            or (
                thread["status"] == "open"
                and not thread["related_entity_ids"]
                and _thread_terms(thread["summary"]) & _thread_terms(player_message)
            )
        )
    ]
    referenced_threads.sort(
        key=lambda item: (
            0 if item["importance"] == "high" else 1,
            item["created_turn"],
            item["thread_id"],
        )
    )
    relevant_interactions = {
        entity_id: memory["npc_interactions"].get(entity_id, [])
        for entity_id in selected_npcs
        if entity_id in memory["npc_interactions"]
    }
    relevant_locations = {
        entity_id: [
            item for item in memory["location_continuity"].get(entity_id, [])
            if item.get("authority") != "temporary_narrative_texture"
        ]
        for entity_id in selected_locations
        if entity_id in memory["location_continuity"]
    }
    target_npc_id = None
    if isinstance(canonical_context.get("current_npc_target"), dict):
        target_npc_id = canonical_context["current_npc_target"].get("id")
    if not target_npc_id and isinstance(action, dict):
        target_npc_id = action.get("npc_id") or action.get("target_id")

    filtered_recent_turns = []
    if target_npc_id:
        other_npc_utterances = set()
        for other_id, interactions in memory.get("npc_interactions", {}).items():
            if other_id != target_npc_id and isinstance(interactions, list):
                for item in interactions:
                    if isinstance(item, dict) and item.get("text"):
                        other_npc_utterances.add(item["text"].strip())
        for turn_item in memory["recent_turns"][-MAX_RECENT_TURNS:]:
            if turn_item.get("npc_id") and turn_item.get("npc_id") != target_npc_id:
                continue
            if turn_item.get("player") and turn_item["player"].strip() in other_npc_utterances:
                continue
            filtered_recent_turns.append(turn_item)
    else:
        filtered_recent_turns = memory["recent_turns"][-MAX_RECENT_TURNS:]

    packet: dict[str, Any] = {
        "authority_boundary": {
            "canonical_state": "authoritative; must not be contradicted",
            "narrative_continuity": "descriptive only; never mechanical authority",
            "temporary_texture": (
                "presentation only; do not promote to facts, entities, "
                "interactive objects, quests, or mechanics"
            ),
        },
        "canonical": copy.deepcopy(canonical_context),
        "player_action": player_message[:MAX_TEXT],
        "action_result": copy.deepcopy(action),
        "relevant_continuity": {
            "recent_turns": [
                {
                    "player": turn["player"],
                    "turn_index": turn["turn_index"],
                    "authority": "unverified_player_claim",
                }
                for turn in filtered_recent_turns
            ],
            "story_summary": memory["story_summary"],
            "npcs": {entity_id: npc_records[entity_id] for entity_id in selected_npcs},
            "npc_interactions": relevant_interactions,
            "locations": {entity_id: location_records[entity_id] for entity_id in selected_locations},
            "location_continuity": relevant_locations,
            "unresolved_threads": referenced_threads,
            "style_profile": memory["style_profile"],
            "repetition_fingerprint": memory["repetition_fingerprint"],
        },
    }
    packet, final_size = _fit_context_packet(packet)
    estimated_tokens = (final_size + 1) // 2
    reserved_prompt_tokens = 8192
    estimated_total_tokens = estimated_tokens + reserved_prompt_tokens
    max_estimated_total_tokens = 32768
    model_context_window_tokens = 40960
    # Conservative UTF-8-byte estimate for Turkish/Qwen prompts; this is not
    # a tokenizer count.  Keep both the product budget and observed window
    # assertions explicit so future packet changes fail closed.
    assert estimated_total_tokens <= max_estimated_total_tokens
    assert estimated_total_tokens <= model_context_window_tokens
    diagnostics = {
        "scene_type": _scene_type(action),
        "estimated_tokens": estimated_tokens,
        "packet_characters": final_size,
        "model_context_window_tokens": model_context_window_tokens,
        "reserved_prompt_tokens": reserved_prompt_tokens,
        "estimated_total_tokens": estimated_total_tokens,
        "max_estimated_total_tokens": max_estimated_total_tokens,
        "selected_counts": {
            "recent_turns": len(packet["relevant_continuity"].get("recent_turns", [])),
            "npcs": len(packet["relevant_continuity"].get("npcs", {})),
            "npc_interactions": sum(len(items) for items in packet["relevant_continuity"].get("npc_interactions", {}).values()),
            "locations": len(packet["relevant_continuity"].get("locations", {})),
            "location_continuity": sum(len(items) for items in packet["relevant_continuity"].get("location_continuity", {}).values()),
            "threads": len(packet["relevant_continuity"].get("unresolved_threads", [])),
        },
        "ambiguities": ambiguities,
    }
    return packet, diagnostics


def _scene_type(action: dict[str, Any]) -> str:
    if action.get("action") == "attack":
        return "combat"
    if action.get("action") == "travel":
        return "travel"
    if action.get("action") in {"query", "inventory", "status"}:
        return "direct_query"
    if action.get("action") == "skill_check":
        return "skill_check"
    if action.get("action") == "dialogue" or action.get("npc_id"):
        return "conversation"
    return "exploration"


def _fit_context_packet(packet: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Drop lower-priority continuity deterministically, never canonical state."""
    def encoded() -> str:
        return json.dumps(packet, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    continuity = packet["relevant_continuity"]
    reductions = (
        ("repetition_fingerprint", {}),
        ("style_profile", {}),
        ("story_summary", {}),
        ("location_continuity", {}),
        ("npc_interactions", {}),
        ("unresolved_threads", []),
        ("recent_turns", []),
    )
    for key, empty in reductions:
        if len(encoded().encode("utf-8")) <= 4800:
            break
        continuity[key] = empty
    if len(encoded().encode("utf-8")) > 4800:
        # Canonical data remains first-class, but oversized free text is
        # clipped rather than allowing an unbounded model prompt.
        packet["canonical"] = _clip_value(packet["canonical"], 1800)
        packet["action_result"] = _clip_value(packet["action_result"], 600)
    if len(encoded().encode("utf-8")) > 4800:
        packet["canonical"] = {"canonical_context_truncated": True}
    value = encoded()
    return packet, len(value.encode("utf-8"))


def _clip_value(value: Any, budget: int) -> Any:
    if budget <= 0:
        return "[truncated]"
    if isinstance(value, str):
        return value[:budget]
    if isinstance(value, list):
        result = []
        for item in value:
            candidate = _clip_value(item, max(32, budget // max(1, len(value))))
            result.append(candidate)
        return result
    if isinstance(value, dict):
        result = {}
        remaining = budget
        for key, item in value.items():
            if remaining <= 0:
                break
            clipped = _clip_value(item, max(32, remaining // 2))
            result[key] = clipped
            remaining -= len(str(clipped))
        return result
    return value