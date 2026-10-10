"""Dynamic adventure records stored on the existing quest list.

Legacy catalog rows keep their exact field set. This module never adds
template, binding, graph, or reward fields to them.
"""

from __future__ import annotations

import copy
import re

LEGACY_QUEST_FIELDS = frozenset({
    "quest_id",
    "title",
    "description",
    "giver_npc_id",
    "status",
    "objectives",
    "created_turn",
    "accepted_turn",
    "updated_turn",
})

DYNAMIC_QUEST_FIELDS = LEGACY_QUEST_FIELDS | {
    "record_kind",
    "template_id",
    "template_version",
    "binding_version",
    "bindings",
    "opportunity_key",
    "creation_evidence",
    "deadline",
    "threat_band",
    "reward_plan",
    "reward_application_id",
    "outcome",
    "follow_up_key",
    "timeline",
}

STATES = frozenset({
    "AVAILABLE",
    "DISCOVERED",
    "ACTIVE",
    "BLOCKED",
    "COMPLETED",
    "FAILED",
    "ABANDONED",
})

LEGACY_STATE_VIEW = {
    "accepted": "ACTIVE",
    "completed": "COMPLETED",
    "cancelled": "ABANDONED",
}

TERMINAL_OUTCOMES = {
    "COMPLETED": frozenset({"success", "partial_success"}),
    "FAILED": frozenset({"failed", "missed"}),
    "ABANDONED": frozenset({"abandoned"}),
}

BINDING_FIELDS = frozenset({
    "source_npc_id",
    "target_npc_id",
    "location_ids",
    "faction_ids",
    "encounter_recipe_ids",
})

THREAT_BANDS = frozenset({"low", "moderate", "high"})

_TEMPLATE_ID = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
_MARKER = re.compile(r"^[A-Za-z0-9:._-]{1,120}$")


def fail():
    raise ValueError("Kayıt görev durumu geçersiz.")


def empty_bindings():
    return {
        "source_npc_id": None,
        "target_npc_id": None,
        "location_ids": [],
        "faction_ids": [],
        "encounter_recipe_ids": [],
    }


def is_legacy_quest(quest):
    """A legacy row is the exact pre-Phase-8 field set and nothing more."""
    return isinstance(quest, dict) and set(quest) == LEGACY_QUEST_FIELDS


def runtime_state(quest):
    """Read a state label. Legacy status is viewed, never rewritten."""
    if is_legacy_quest(quest):
        viewed = LEGACY_STATE_VIEW.get(quest.get("status"))
        if viewed is None:
            fail()
        return viewed
    if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
        fail()
    state = quest.get("status")
    if state not in STATES:
        fail()
    return state


def new_dynamic_quest(
    *,
    quest_id,
    title,
    description,
    turn,
    template_id,
    template_version,
    binding_version,
    opportunity_key,
    creation_evidence,
    objectives,
    bindings=None,
    giver_npc_id=None,
    threat_band=None,
    reward_plan=None,
):
    """Create one AVAILABLE dynamic row. The player-facing deadline stays unset."""
    record = {
        "quest_id": quest_id,
        "title": title,
        "description": description,
        "giver_npc_id": giver_npc_id,
        "status": "AVAILABLE",
        "objectives": [normalize_objective(item) for item in objectives],
        "created_turn": turn,
        "accepted_turn": None,
        "updated_turn": turn,
        "record_kind": "dynamic",
        "template_id": template_id,
        "template_version": template_version,
        "binding_version": binding_version,
        "bindings": copy.deepcopy(bindings if bindings is not None else empty_bindings()),
        "opportunity_key": opportunity_key,
        "creation_evidence": creation_evidence,
        "deadline": None,
        "threat_band": threat_band,
        "reward_plan": copy.deepcopy(reward_plan) if reward_plan is not None else None,
        "reward_application_id": None,
        "outcome": None,
        "follow_up_key": None,
        "timeline": [],
    }
    validate_dynamic_saved_quest(record, set())
    return record


def validate_dynamic_saved_quest(quest, quest_ids):
    """Fail closed unless the row is one complete dynamic adventure record."""
    if (
        not isinstance(quest, dict)
        or set(quest) != DYNAMIC_QUEST_FIELDS
        or quest.get("record_kind") != "dynamic"
    ):
        fail()
    _identity(quest, quest_ids)
    _text(quest.get("title"), 160)
    _text(quest.get("description"), 2000)
    _optional_id(quest.get("giver_npc_id"))
    if quest.get("status") not in STATES:
        fail()
    _turns(quest)
    _objectives(quest["objectives"])
    if not isinstance(quest.get("template_id"), str) or _TEMPLATE_ID.fullmatch(quest["template_id"]) is None:
        fail()
    _positive_version(quest.get("template_version"))
    _positive_version(quest.get("binding_version"))
    _bindings(quest.get("bindings"))
    _text(quest.get("opportunity_key"), 200)
    _text(quest.get("creation_evidence"), 200)
    _deadline(quest)
    if quest.get("threat_band") is not None and quest.get("threat_band") not in THREAT_BANDS:
        fail()
    _reward_plan(quest.get("reward_plan"))
    _optional_marker(quest.get("reward_application_id"))
    _outcome(quest)
    _optional_marker(quest.get("follow_up_key"))
    _timeline(quest.get("timeline"))
    quest_ids.add(quest["quest_id"])


def _identity(quest, quest_ids):
    quest_id = quest.get("quest_id")
    if (
        not isinstance(quest_id, str)
        or not quest_id.strip()
        or len(quest_id) > 120
        or quest_id in quest_ids
    ):
        fail()


def _turns(quest):
    for turn_field in ("created_turn", "updated_turn"):
        if type(quest.get(turn_field)) is not int or quest[turn_field] < 0:
            fail()
    if quest["updated_turn"] < quest["created_turn"]:
        fail()
    accepted_turn = quest.get("accepted_turn")
    needs_accept = quest["status"] in {"ACTIVE", "BLOCKED", "COMPLETED"}
    if needs_accept:
        if type(accepted_turn) is not int or accepted_turn < quest["created_turn"]:
            fail()
        return
    if quest["status"] in {"ABANDONED", "FAILED"}:
        if accepted_turn is not None and (
            type(accepted_turn) is not int or accepted_turn < quest["created_turn"]
        ):
            fail()
        return
    if accepted_turn is not None:
        fail()


GRAPH_STATES = frozenset({"HIDDEN", "ACTIVE", "COMPLETE", "FAILED"})
DYNAMIC_OBJECTIVE_TYPES = frozenset({
    "visit_location", "defeat_entity", "acquire_item",
    "rescue_person", "discover_clue", "investigate",
})
RESOLUTION_KINDS = frozenset({
    "combat", "stealth", "persuasion", "intimidation", "bribery",
    "distraction", "alternate_route", "environment", "item_use",
    "rescue", "investigation", "social",
})
OBJECTIVE_FIELDS = frozenset({
    "objective_id", "description", "type", "target", "status",
    "required_count", "progress", "visibility", "prerequisites",
    "resolution_kinds", "graph_state", "optional",
})


def normalize_objective(raw):
    if not isinstance(raw, dict):
        fail()
    item = copy.deepcopy(raw)
    item.setdefault("visibility", "known")
    item.setdefault("prerequisites", [])
    item.setdefault("resolution_kinds", [])
    item.setdefault("optional", False)
    item.setdefault(
        "graph_state",
        "HIDDEN" if item.get("visibility") == "hidden" else "ACTIVE",
    )
    item["status"] = {
        "HIDDEN": "active",
        "ACTIVE": "active",
        "COMPLETE": "completed",
        "FAILED": "failed",
    }.get(item["graph_state"], item.get("status"))
    return item


def _objectives(objectives):
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 8:
        fail()
    seen = set()
    for objective in objectives:
        if not isinstance(objective, dict):
            fail()
        objective.setdefault("optional", False)
        if set(objective) != OBJECTIVE_FIELDS or type(objective.get("optional")) is not bool:
            fail()
        _text(objective.get("objective_id"), 120)
        if objective["objective_id"] in seen:
            fail()
        seen.add(objective["objective_id"])
        _text(objective.get("description"), 1000)
        _text(objective.get("target"), 160)
        if objective.get("type") not in DYNAMIC_OBJECTIVE_TYPES:
            fail()
        if objective["type"] == "acquire_item" and objective["target"] != "Kılıç":
            fail()
        if objective.get("visibility") not in {"hidden", "known"}:
            fail()
        if objective.get("graph_state") not in GRAPH_STATES:
            fail()
        expected = {
            "HIDDEN": ("active", "hidden"),
            "ACTIVE": ("active", "known"),
            "COMPLETE": ("completed", "known"),
            "FAILED": ("failed", "known"),
        }[objective["graph_state"]]
        if (objective.get("status"), objective.get("visibility")) != expected:
            fail()
        prerequisites = objective.get("prerequisites")
        if (
            not isinstance(prerequisites, list)
            or len(prerequisites) > 4
            or any(not isinstance(item, str) for item in prerequisites)
        ):
            fail()
        kinds = objective.get("resolution_kinds")
        if (
            not isinstance(kinds, list)
            or len(kinds) > 6
            or any(item not in RESOLUTION_KINDS for item in kinds)
        ):
            fail()
        if (
            type(objective.get("required_count")) is not int
            or not 1 <= objective["required_count"] <= 1000
        ):
            fail()
        if (
            type(objective.get("progress")) is not int
            or not 0 <= objective["progress"] <= objective["required_count"]
        ):
            fail()
        if (
            objective["graph_state"] == "COMPLETE"
            and objective["progress"] != objective["required_count"]
        ):
            fail()
    known = {item["objective_id"] for item in objectives}
    for objective in objectives:
        if any(item not in known or item == objective["objective_id"] for item in objective["prerequisites"]):
            fail()
    if _has_cycle(objectives):
        fail()


def _has_cycle(objectives):
    edges = {item["objective_id"]: list(item["prerequisites"]) for item in objectives}
    visiting = set()
    visited = set()

    def walk(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(walk(child) for child in edges.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(walk(node) for node in edges)


def _reward_plan(plan):
    if plan is None:
        return
    if not isinstance(plan, dict) or not plan or set(plan) - {"success", "partial_success", "failed"}:
        fail()
    for branch in plan.values():
        if not isinstance(branch, dict) or set(branch) - {"xp", "gold", "faction", "item"}:
            fail()
        item = branch.get("item")
        if item is not None:
            from weapon_catalog import lookup

            found = lookup(item) if isinstance(item, str) else None
            if found is None or found.get("weapon_id") != item:
                fail()
        for key in ("xp", "gold"):
            if key in branch and (type(branch[key]) is not int or not 0 <= branch[key] <= 100000):
                fail()
        faction = branch.get("faction")
        if faction is None:
            continue
        if (
            not isinstance(faction, dict)
            or set(faction) != {"id", "standing"}
            or not isinstance(faction.get("id"), str)
            or not faction["id"].strip()
            or len(faction["id"]) > 120
            or type(faction.get("standing")) is not int
            or not -5 <= faction["standing"] <= 5
        ):
            fail()


def _bindings(bindings):
    if not isinstance(bindings, dict) or set(bindings) != BINDING_FIELDS:
        fail()
    _optional_id(bindings.get("source_npc_id"))
    _optional_id(bindings.get("target_npc_id"))
    for key in ("location_ids", "faction_ids", "encounter_recipe_ids"):
        values = bindings.get(key)
        if (
            not isinstance(values, list)
            or len(values) > 8
            or len(values) != len(set(values))
            or any(not isinstance(item, str) or not item.strip() or len(item) > 120 for item in values)
        ):
            fail()


def _deadline(quest):
    deadline = quest.get("deadline")
    if quest["status"] == "AVAILABLE":
        if deadline is not None:
            fail()
        return
    if deadline is not None and (
        not isinstance(deadline, str) or not deadline.strip() or len(deadline) > 120
    ):
        fail()


def _outcome(quest):
    outcome = quest.get("outcome")
    allowed = TERMINAL_OUTCOMES.get(quest["status"])
    if allowed is None:
        if outcome is not None:
            fail()
        return
    if outcome not in allowed:
        fail()


def _positive_version(value):
    if type(value) is not int or not 1 <= value <= 1000:
        fail()


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail()


def _optional_id(value):
    if value is None:
        return
    _text(value, 120)


def _timeline(value):
    if (
        not isinstance(value, list)
        or len(value) > 12
        or any(not isinstance(item, str) or not item.strip() or len(item) > 200 for item in value)
    ):
        fail()


def _optional_marker(value):
    if value is None:
        return
    if not isinstance(value, str) or _MARKER.fullmatch(value) is None:
        fail()
