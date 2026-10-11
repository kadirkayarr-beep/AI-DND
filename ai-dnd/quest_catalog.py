"""Server-owned Quest Outcomes V1 definitions.

The production catalog is intentionally empty.  Tests and owner-approved
installations may inject immutable definitions through ``CATALOG``; clients
never submit quest definitions.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


OBJECTIVE_TYPES = frozenset({"visit_location", "defeat_entity", "acquire_item"})
OFFER_CONDITION_TYPES = frozenset({"location_is", "npc_present"})
QUEST_STATUSES = frozenset({"accepted", "completed", "cancelled"})

# Keep this empty in production.  A tuple also prevents accidental append.
CATALOG: tuple[Mapping[str, Any], ...] = ()


def _text(value: Any, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def validate_catalog(catalog: Any = CATALOG) -> tuple[Mapping[str, Any], ...]:
    """Validate and freeze a server-owned catalog, rejecting client-shaped data."""
    if not isinstance(catalog, (tuple, list)):
        raise ValueError("Quest catalog must be a sequence.")
    seen: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for quest in catalog:
        if not isinstance(quest, Mapping):
            raise ValueError("Quest definition must be an object.")
        required = {"quest_id", "title", "description", "objectives"}
        optional = {"giver_npc_id", "offer_condition", "xp"}
        if not required.issubset(quest) or set(quest) - required - optional:
            raise ValueError("Quest definition fields are invalid.")
        quest_id = quest["quest_id"]
        if not _text(quest_id, 120) or quest_id in seen:
            raise ValueError("Quest identifier is invalid.")
        if not _text(quest["title"], 160) or not _text(quest["description"], 2000):
            raise ValueError("Quest text is invalid.")
        if "giver_npc_id" in quest and quest["giver_npc_id"] is not None and not _text(
            quest["giver_npc_id"], 120
        ):
            raise ValueError("Quest giver is invalid.")
        quest_xp = quest.get("xp")
        if "xp" in quest and (
            type(quest_xp) is not int or quest_xp < 1 or quest_xp > 100_000
        ):
            raise ValueError("Quest experience is invalid.")
        offer_condition = quest.get("offer_condition")
        frozen_condition = None
        if offer_condition is not None:
            if not isinstance(offer_condition, Mapping) or set(offer_condition) != {
                "type",
                "target",
            }:
                raise ValueError("Quest offer condition fields are invalid.")
            condition_type = offer_condition["type"]
            target = offer_condition["target"]
            if (
                not isinstance(condition_type, str)
                or condition_type not in OFFER_CONDITION_TYPES
                or not _text(target, 160)
            ):
                raise ValueError("Quest offer condition is invalid.")
            frozen_condition = MappingProxyType(
                {"type": condition_type, "target": target}
            )
        objectives = quest["objectives"]
        if not isinstance(objectives, (tuple, list)) or not objectives:
            raise ValueError("Quest objectives are invalid.")
        objective_ids: set[str] = set()
        frozen_objectives: list[Mapping[str, Any]] = []
        for objective in objectives:
            if not isinstance(objective, Mapping):
                raise ValueError("Quest objective must be an object.")
            allowed = {"objective_id", "description", "type", "target", "required_count"}
            if set(objective) - allowed or not {"objective_id", "description", "type", "target"} <= set(objective):
                raise ValueError("Quest objective fields are invalid.")
            objective_id = objective["objective_id"]
            if not _text(objective_id, 120) or objective_id in objective_ids:
                raise ValueError("Quest objective identifier is invalid.")
            if not _text(objective["description"], 1000):
                raise ValueError("Quest objective text is invalid.")
            if (
                not isinstance(objective["type"], str)
                or objective["type"] not in OBJECTIVE_TYPES
            ):
                raise ValueError("Quest objective type is unsupported.")
            target = objective["target"]
            if not _text(target, 160):
                raise ValueError("Quest objective target is invalid.")
            if objective["type"] == "acquire_item" and target != "Kılıç":
                raise ValueError("This item objective is not supported.")
            count = objective.get("required_count", 1)
            if type(count) is not int or count < 1 or count > 1000:
                raise ValueError("Quest objective count is invalid.")
            objective_ids.add(objective_id)
            frozen = dict(objective)
            frozen["required_count"] = count
            frozen_objectives.append(MappingProxyType(frozen))
        seen.add(quest_id)
        frozen_quest = {
            "quest_id": quest_id,
            "title": quest["title"],
            "description": quest["description"],
            "giver_npc_id": quest.get("giver_npc_id"),
            "offer_condition": frozen_condition,
            "objectives": tuple(frozen_objectives),
        }
        if "xp" in quest:
            frozen_quest["xp"] = quest_xp
        validated.append(MappingProxyType(frozen_quest))
    return tuple(validated)


def catalog() -> tuple[Mapping[str, Any], ...]:
    return validate_catalog(CATALOG)


def find_quest(quest_id: str) -> Mapping[str, Any] | None:
    return next((quest for quest in catalog() if quest["quest_id"] == quest_id), None)