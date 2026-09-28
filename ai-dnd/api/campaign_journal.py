"""Canonical, API-owned journal projection over frozen engine save data."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import uuid
from typing import Any


JOURNAL_SCHEMA_VERSION = 1
MAX_LOCATIONS = 500
MAX_NPCS = 500
MAX_EVENTS = 200
MAX_QUESTS = 100
MAX_OBJECTIVES_PER_QUEST = 100

_ENVIRONMENTS = {
    "tavern", "forest", "city", "village", "road", "wilderness",
    "dungeon", "cave", "castle", "temple", "ruins", "unknown",
}
_EVENT_TYPES = {
    "location_discovered",
    "npc_met",
    "combat_started",
    "combat_ended",
    "enemy_defeated",
    "player_unconscious",
    "item_gained",
    "item_lost",
}
_QUEST_STATUSES = {"active", "completed", "failed", "cancelled"}
_OBJECTIVE_STATUSES = {"active", "completed", "failed", "cancelled"}


def empty_campaign_journal() -> dict[str, Any]:
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "discovered_locations": [],
        "known_npcs": [],
        "notable_events": [],
        "quests": [],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_uuid4(value: Any) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


def _valid_text(value: Any, maximum: int, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def validate_campaign_journal(
    value: Any,
    error_type: type[Exception] = ValueError,
) -> None:
    """Reject malformed or client-shaped journal data before it is persisted."""

    def invalid() -> None:
        raise error_type("Campaign journal is invalid.")

    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema_version",
            "discovered_locations",
            "known_npcs",
            "notable_events",
            "quests",
        }
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != JOURNAL_SCHEMA_VERSION
    ):
        invalid()

    locations = value["discovered_locations"]
    npcs = value["known_npcs"]
    events = value["notable_events"]
    quests = value["quests"]
    if (
        not isinstance(locations, list)
        or len(locations) > MAX_LOCATIONS
        or not isinstance(npcs, list)
        or len(npcs) > MAX_NPCS
        or not isinstance(events, list)
        or len(events) > MAX_EVENTS
        or not isinstance(quests, list)
        or len(quests) > MAX_QUESTS
    ):
        invalid()

    location_ids: set[str] = set()
    for entry in locations:
        if (
            not isinstance(entry, dict)
            or set(entry) != {
                "location_id",
                "name",
                "environment",
                "first_discovered_at",
                "last_visited_at",
                "first_discovered_turn",
                "last_visited_turn",
                "visit_count",
            }
        ):
            invalid()
        location_id = entry.get("location_id")
        if (
            not _valid_text(location_id, 160)
            or location_id in location_ids
            or not _valid_text(entry.get("name"), 160)
            or not isinstance(entry.get("environment"), str)
            or entry["environment"] not in _ENVIRONMENTS
            or not _valid_timestamp(entry.get("first_discovered_at"))
            or not _valid_timestamp(entry.get("last_visited_at"))
            or type(entry.get("first_discovered_turn")) is not int
            or entry["first_discovered_turn"] < 0
            or type(entry.get("last_visited_turn")) is not int
            or entry["last_visited_turn"] < entry["first_discovered_turn"]
            or type(entry.get("visit_count")) is not int
            or entry["visit_count"] < 1
        ):
            invalid()
        location_ids.add(location_id)

    npc_ids: set[str] = set()
    for entry in npcs:
        if (
            not isinstance(entry, dict)
            or set(entry) != {
                "npc_id",
                "name",
                "role",
                "first_met_at",
                "last_seen_at",
                "first_met_turn",
                "last_seen_turn",
                "last_known_location_id",
                "last_known_location",
            }
        ):
            invalid()
        npc_id = entry.get("npc_id")
        if (
            not _valid_text(npc_id, 160)
            or npc_id in npc_ids
            or not _valid_text(entry.get("name"), 160)
            or not _valid_text(entry.get("role"), 160, nullable=True)
            or not _valid_timestamp(entry.get("first_met_at"))
            or not _valid_timestamp(entry.get("last_seen_at"))
            or type(entry.get("first_met_turn")) is not int
            or entry["first_met_turn"] < 0
            or type(entry.get("last_seen_turn")) is not int
            or entry["last_seen_turn"] < entry["first_met_turn"]
            or not _valid_text(entry.get("last_known_location_id"), 160, nullable=True)
            or not _valid_text(entry.get("last_known_location"), 160, nullable=True)
            or (
                (entry["last_known_location_id"] is None)
                != (entry["last_known_location"] is None)
            )
        ):
            invalid()
        npc_ids.add(npc_id)

    event_ids: set[str] = set()
    for entry in events:
        if (
            not isinstance(entry, dict)
            or set(entry) != {
                "event_id",
                "event_type",
                "created_at",
                "turn_index",
                "summary",
                "location_id",
                "location_name",
                "related_npc_id",
                "related_item",
            }
        ):
            invalid()
        event_id = entry.get("event_id")
        if (
            not _valid_uuid4(event_id)
            or event_id in event_ids
            or not isinstance(entry.get("event_type"), str)
            or entry.get("event_type") not in _EVENT_TYPES
            or not _valid_timestamp(entry.get("created_at"))
            or type(entry.get("turn_index")) is not int
            or entry["turn_index"] < 0
            or not _valid_text(entry.get("summary"), 240)
            or not _valid_text(entry.get("location_id"), 160, nullable=True)
            or not _valid_text(entry.get("location_name"), 160, nullable=True)
            or (
                (entry["location_id"] is None)
                != (entry["location_name"] is None)
            )
            or not _valid_text(entry.get("related_npc_id"), 160, nullable=True)
            or not _valid_text(entry.get("related_item"), 160, nullable=True)
            or (
                entry["related_npc_id"] is not None
                and entry["related_npc_id"] not in npc_ids
            )
        ):
            invalid()
        event_ids.add(event_id)

    quest_ids: set[str] = set()
    for quest in quests:
        if (
            not isinstance(quest, dict)
            or set(quest) != {
                "quest_id",
                "title",
                "description",
                "status",
                "giver_npc_id",
                "objectives",
                "created_at",
                "updated_at",
                "completed_at",
            }
        ):
            invalid()
        quest_id = quest.get("quest_id")
        objectives = quest.get("objectives")
        if (
            not _valid_uuid4(quest_id)
            or quest_id in quest_ids
            or not _valid_text(quest.get("title"), 160)
            or not _valid_text(quest.get("description"), 2000)
            or not isinstance(quest.get("status"), str)
            or quest.get("status") not in _QUEST_STATUSES
            or not _valid_text(quest.get("giver_npc_id"), 160, nullable=True)
            or (
                quest["giver_npc_id"] is not None
                and quest["giver_npc_id"] not in npc_ids
            )
            or not isinstance(objectives, list)
            or len(objectives) > MAX_OBJECTIVES_PER_QUEST
            or not _valid_timestamp(quest.get("created_at"))
            or not _valid_timestamp(quest.get("updated_at"))
            or (
                quest.get("completed_at") is not None
                and not _valid_timestamp(quest.get("completed_at"))
            )
        ):
            invalid()
        objective_ids: set[str] = set()
        for objective in objectives:
            if (
                not isinstance(objective, dict)
                or set(objective) != {"objective_id", "description", "status"}
                or not _valid_uuid4(objective.get("objective_id"))
                or objective["objective_id"] in objective_ids
                or not _valid_text(objective.get("description"), 1000)
                or not isinstance(objective.get("status"), str)
                or objective.get("status") not in _OBJECTIVE_STATUSES
            ):
                invalid()
            objective_ids.add(objective["objective_id"])
        quest_ids.add(quest_id)


def _location_record(
    world_state: dict[str, Any],
    location_id: Any,
) -> dict[str, Any] | None:
    locations = world_state.get("locations")
    if (
        not isinstance(location_id, str)
        or location_id == "Henüz belirlenmedi"
        or not isinstance(locations, dict)
        or not isinstance(locations.get(location_id), dict)
    ):
        return None
    record = locations[location_id]
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return {"location_id": location_id, "name": name.strip()}


def _turn_index(world_state: dict[str, Any]) -> int:
    flags = world_state.get("flags")
    value = flags.get("turn_index", 0) if isinstance(flags, dict) else 0
    return value if type(value) is int and value >= 0 else 0


def _add_event(
    journal: dict[str, Any],
    *,
    event_type: str,
    summary: str,
    created_at: str,
    turn_index: int,
    location: dict[str, str] | None = None,
    related_npc_id: str | None = None,
    related_item: str | None = None,
) -> None:
    journal["notable_events"].append({
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "created_at": created_at,
        "turn_index": turn_index,
        "summary": summary,
        "location_id": location["location_id"] if location else None,
        "location_name": location["name"] if location else None,
        "related_npc_id": related_npc_id,
        "related_item": related_item,
    })
    if len(journal["notable_events"]) > MAX_EVENTS:
        del journal["notable_events"][:-MAX_EVENTS]


def _record_location(
    journal: dict[str, Any],
    world_state: dict[str, Any],
    world_metadata: dict[str, Any] | None,
    *,
    visited_at: str,
    turn_index: int,
) -> tuple[dict[str, str] | None, bool]:
    location = _location_record(world_state, world_state.get("location"))
    if location is None:
        return None, False

    existing = next(
        (
            item
            for item in journal["discovered_locations"]
            if item["location_id"] == location["location_id"]
        ),
        None,
    )
    if existing is not None:
        existing["last_visited_at"] = visited_at
        existing["last_visited_turn"] = turn_index
        existing["visit_count"] += 1
        return location, False

    environment = (
        world_metadata.get("environment")
        if isinstance(world_metadata, dict)
        else None
    )
    if environment not in _ENVIRONMENTS:
        environment = "unknown"
    journal["discovered_locations"].append({
        **location,
        "environment": environment,
        "first_discovered_at": visited_at,
        "last_visited_at": visited_at,
        "first_discovered_turn": turn_index,
        "last_visited_turn": turn_index,
        "visit_count": 1,
    })
    return location, True


def create_initial_campaign_journal(
    world_state: dict[str, Any],
    world_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Record a starting place only when the engine already established one."""
    journal = empty_campaign_journal()
    now = _now()
    turn_index = _turn_index(world_state)
    location, discovered = _record_location(
        journal,
        world_state,
        world_metadata,
        visited_at=now,
        turn_index=turn_index,
    )
    if discovered and location is not None:
        _add_event(
            journal,
            event_type="location_discovered",
            summary=f"{location['name']} keşfedildi.",
            created_at=now,
            turn_index=turn_index,
            location=location,
        )
    validate_campaign_journal(journal)
    return journal


def _snapshot_maps(world_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = world_state.get("npcs")
    if not isinstance(value, list):
        return {}
    return {
        item["id"]: item
        for item in value
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    }


def _has_new_memory(before_npc: dict[str, Any], after_npc: dict[str, Any]) -> bool:
    before = before_npc.get("memory", [])
    after = after_npc.get("memory", [])
    return isinstance(before, list) and isinstance(after, list) and before != after


def _active_npc_ids(world_state: dict[str, Any], location_id: str) -> set[str]:
    result: set[str] = set()
    for npc in _snapshot_maps(world_state).values():
        if npc.get("location") != location_id:
            continue
        if npc.get("combat_status", "active") != "active":
            continue
        hp = npc.get("current_hp", 1)
        if type(hp) in (int, float) and hp <= 0:
            continue
        result.add(npc["id"])
    return result


def update_campaign_journal(
    journal_value: dict[str, Any],
    before_save: dict[str, Any],
    after_save: dict[str, Any],
    action_result: dict[str, Any] | None,
    world_metadata: dict[str, Any] | None,
    *,
    presence_location_id: str | None = None,
) -> dict[str, Any]:
    """Derive journal changes only from canonical before/after engine state."""
    validate_campaign_journal(journal_value)
    journal = deepcopy(journal_value)
    before_world = before_save.get("world_state", {})
    after_world = after_save.get("world_state", {})
    if not isinstance(before_world, dict) or not isinstance(after_world, dict):
        return journal
    action = action_result if isinstance(action_result, dict) else {}
    now = _now()
    turn_index = _turn_index(after_world)
    before_location_id = before_world.get("location")
    current_location_id = after_world.get("location")
    current_location = _location_record(after_world, current_location_id)

    if current_location_id != before_location_id and current_location is not None:
        location, discovered = _record_location(
            journal,
            after_world,
            world_metadata,
            visited_at=now,
            turn_index=turn_index,
        )
        if discovered and location is not None:
            _add_event(
                journal,
                event_type="location_discovered",
                summary=f"{location['name']} keşfedildi.",
                created_at=now,
                turn_index=turn_index,
                location=location,
            )

    before_npcs = _snapshot_maps(before_world)
    after_npcs = _snapshot_maps(after_world)
    encountered_ids: set[str] = set()
    for key in ("npc_id", "target_id", "target"):
        npc_id = action.get(key)
        if isinstance(npc_id, str) and npc_id in after_npcs:
            encountered_ids.add(npc_id)
    for npc_id, after_npc in after_npcs.items():
        before_npc = before_npcs.get(npc_id)
        if before_npc is not None and _has_new_memory(before_npc, after_npc):
            encountered_ids.add(npc_id)
    if (
        action.get("action") == "query"
        and action.get("query_type") == "presence"
        and presence_location_id == current_location_id
        and isinstance(current_location_id, str)
    ):
        encountered_ids.update(_active_npc_ids(after_world, current_location_id))

    known_by_id = {
        entry["npc_id"]: entry
        for entry in journal["known_npcs"]
    }
    for npc_id in encountered_ids:
        npc = after_npcs.get(npc_id)
        if (
            npc is None
            or npc.get("location") != current_location_id
            or not _valid_text(npc.get("name"), 160)
        ):
            continue
        location = _location_record(after_world, current_location_id)
        role = npc.get("role")
        if not isinstance(role, str) or not role.strip():
            role = None
        existing = known_by_id.get(npc_id)
        if existing is None:
            entry = {
                "npc_id": npc_id,
                "name": npc["name"].strip(),
                "role": role.strip() if role is not None else None,
                "first_met_at": now,
                "last_seen_at": now,
                "first_met_turn": turn_index,
                "last_seen_turn": turn_index,
                "last_known_location_id": (
                    location["location_id"] if location else None
                ),
                "last_known_location": location["name"] if location else None,
            }
            journal["known_npcs"].append(entry)
            known_by_id[npc_id] = entry
            if len(journal["known_npcs"]) > MAX_NPCS:
                journal["known_npcs"] = journal["known_npcs"][-MAX_NPCS:]
                known_by_id = {
                    item["npc_id"]: item
                    for item in journal["known_npcs"]
                }
            if npc_id in known_by_id:
                _add_event(
                    journal,
                    event_type="npc_met",
                    summary=f"{entry['name']} ile karşılaşıldı.",
                    created_at=now,
                    turn_index=turn_index,
                    location=location,
                    related_npc_id=npc_id,
                )
        else:
            existing["last_seen_at"] = now
            existing["last_seen_turn"] = turn_index
            existing["last_known_location_id"] = (
                location["location_id"] if location else None
            )
            existing["last_known_location"] = location["name"] if location else None

    before_combat = before_world.get("combat", {})
    after_combat = after_world.get("combat", {})
    was_in_combat = (
        isinstance(before_combat, dict) and before_combat.get("active") is True
    )
    is_in_combat = (
        isinstance(after_combat, dict) and after_combat.get("active") is True
    )
    if not was_in_combat and is_in_combat:
        _add_event(
            journal,
            event_type="combat_started",
            summary="Çatışma başladı.",
            created_at=now,
            turn_index=turn_index,
            location=current_location,
        )
    elif was_in_combat and not is_in_combat:
        _add_event(
            journal,
            event_type="combat_ended",
            summary="Çatışma sona erdi.",
            created_at=now,
            turn_index=turn_index,
            location=current_location,
        )

    for npc_id, before_npc in before_npcs.items():
        after_npc = after_npcs.get(npc_id)
        if after_npc is None:
            continue
        before_hp = before_npc.get("current_hp")
        after_hp = after_npc.get("current_hp")
        was_active = before_npc.get("combat_status", "active") == "active"
        is_defeated = (
            after_npc.get("combat_status") in {"defeated", "dead", "unconscious"}
            or (type(after_hp) in (int, float) and after_hp <= 0)
        )
        if was_active and is_defeated and npc_id in known_by_id:
            npc_record = known_by_id[npc_id]
            _add_event(
                journal,
                event_type="enemy_defeated",
                summary=f"{npc_record['name']} çatışmada yenildi.",
                created_at=now,
                turn_index=turn_index,
                location=current_location,
                related_npc_id=npc_id,
            )

    before_player = before_save.get("player", {})
    after_player = after_save.get("player", {})
    before_hp = before_player.get("current_hp") if isinstance(before_player, dict) else None
    after_hp = after_player.get("current_hp") if isinstance(after_player, dict) else None
    before_player_status = before_world.get("player_combat_status")
    after_player_status = after_world.get("player_combat_status")
    if (
        before_player_status != "unconscious"
        and after_player_status == "unconscious"
    ) or (
        type(before_hp) in (int, float)
        and before_hp > 0
        and type(after_hp) in (int, float)
        and after_hp <= 0
    ):
        _add_event(
            journal,
            event_type="player_unconscious",
            summary="Karakter bilincini kaybetti.",
            created_at=now,
            turn_index=turn_index,
            location=current_location,
        )

    before_items = before_world.get("inventory", [])
    after_items = after_world.get("inventory", [])
    if isinstance(before_items, list) and isinstance(after_items, list):
        before_counts = Counter(item for item in before_items if isinstance(item, str))
        after_counts = Counter(item for item in after_items if isinstance(item, str))
        for item in sorted(set(before_counts) | set(after_counts), key=str.casefold):
            if not _valid_text(item, 160):
                continue
            if after_counts[item] > before_counts[item]:
                _add_event(
                    journal,
                    event_type="item_gained",
                    summary=f"Envantere {item} eklendi.",
                    created_at=now,
                    turn_index=turn_index,
                    location=current_location,
                    related_item=item,
                )
            elif after_counts[item] < before_counts[item]:
                _add_event(
                    journal,
                    event_type="item_lost",
                    summary=f"Envanterden {item} çıkarıldı.",
                    created_at=now,
                    turn_index=turn_index,
                    location=current_location,
                    related_item=item,
                )

    validate_campaign_journal(journal)
    return journal