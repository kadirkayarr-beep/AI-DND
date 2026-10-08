"""Objective evidence. Narration and unbound checks never close a node."""

from __future__ import annotations

from adventure.transitions import transition

SKILL_KINDS = {
    "stealth": "stealth",
    "persuasion": "persuasion",
    "intimidation": "intimidation",
    "investigation": "investigation",
}


def _skill_name(skill):
    if not isinstance(skill, str):
        return ""
    return skill.strip().casefold()


def _dungeon_node(world):
    if not isinstance(world, dict):
        return None
    discovery = world.get("dungeon_discovery")
    if not isinstance(discovery, dict):
        return None
    from adventure.dungeon import HIDEOUT_ID

    state = discovery.get(HIDEOUT_ID)
    if not isinstance(state, dict):
        return None
    node = state.get("node")
    return node if isinstance(node, str) else None


def apply_dynamic_evidence(world, before_world, action_result):
    """Advance dynamic objectives from canonical world evidence only."""
    if not isinstance(world, dict) or not isinstance(action_result, dict):
        return []
    notes = []
    for quest in world.get("quests", []):
        if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
            continue
        if quest.get("status") not in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
            continue
        for evidence in _evidence_from_turn(quest, world, before_world, action_result):
            note = _apply_one(quest, evidence)
            if note is not None:
                notes.append(note)
        _leave_unfinished_threat(quest, before_world, world)
        _reveal_ready(quest)
        _close_if_resolved(world, quest)
    return notes


def _evidence_from_turn(quest, world, before_world, action_result):
    found = []
    turn = world.get("flags", {}).get("turn_index", 0)
    if not isinstance(turn, int):
        turn = 0
    location = world.get("location")
    if before_world.get("location") != location and isinstance(location, str):
        found.extend(_matching(quest, "visit_location", location, "investigation", f"location:{turn}:{location}"))
    before_npcs = {
        npc.get("id"): npc for npc in before_world.get("npcs", []) if isinstance(npc, dict)
    }
    for npc in world.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        previous = before_npcs.get(npc.get("id"))
        if previous is None:
            continue
        defeated = npc.get("combat_status") in {"unconscious", "defeated", "dead"} or npc.get("current_hp", 1) <= 0
        was = previous.get("combat_status") in {"unconscious", "defeated", "dead"} or previous.get("current_hp", 1) <= 0
        if defeated and not was:
            found.extend(_matching(
                quest, "defeat_entity", npc.get("id"), "combat", f"defeat:{turn}:{npc.get('id')}",
            ))
            found.extend(_matching(
                quest, "rescue_person", npc.get("id"), "combat", f"defeat:{turn}:{npc.get('id')}",
            ))
    before_node = _dungeon_node(before_world)
    after_node = _dungeon_node(world)
    if isinstance(after_node, str) and after_node != before_node:
        from adventure.dungeon import HIDEOUT_ID

        found.extend(_matching(
            quest,
            "visit_location",
            f"{HIDEOUT_ID}:{after_node}",
            "investigation",
            f"dungeon:{turn}:{after_node}",
        ))
    if (
        action_result.get("action") == "skill_check"
        and action_result.get("success") is True
        and isinstance(action_result.get("action_id"), str)
    ):
        kind = SKILL_KINDS.get(_skill_name(action_result.get("skill")))
        target = action_result.get("target")
        if not isinstance(target, str):
            target = action_result.get("target_id") or action_result.get("npc_id")
        targets = [target] if isinstance(target, str) else _skill_targets(quest, world, kind)
        if kind is not None:
            types = ("rescue_person", "investigate", "discover_clue")
            if _dungeon_node(world) == "captive" and kind != "stealth":
                types = types + ("defeat_entity",)
            for skill_target in targets:
                for objective_type in types:
                    found.extend(_matching(
                        quest, objective_type, skill_target, kind, action_result["action_id"],
                    ))
    rescued = action_result.get("authoritative_result")
    if isinstance(rescued, dict) and rescued.get("alive") is True and isinstance(rescued.get("location"), str):
        found.extend(_matching(
            quest,
            "rescue_person",
            rescued.get("target"),
            "rescue",
            rescued.get("action_id"),
        ))
    return found


def _skill_targets(quest, world, kind):
    """Bind a real check to the objective only when the player is at its place."""
    if kind == "investigation" and isinstance(world.get("location"), str):
        targets = [world["location"]]
        giver = quest.get("giver_npc_id")
        if isinstance(giver, str):
            targets.append(giver)
        return targets
    if kind in {"persuasion", "intimidation", "stealth"} and _dungeon_node(world) == "captive":
        bindings = quest.get("bindings") if isinstance(quest.get("bindings"), dict) else {}
        bound = bindings.get("target_npc_id")
        if isinstance(bound, str):
            return [bound]
    return []


def _matching(quest, objective_type, target, resolution_kind, action_id):
    if not isinstance(target, str) or not isinstance(action_id, str) or not action_id:
        return []
    matched = []
    for objective in quest.get("objectives", []):
        if objective.get("type") != objective_type or objective.get("target") != target:
            continue
        if objective.get("graph_state") != "ACTIVE":
            continue
        allowed = objective.get("resolution_kinds") or []
        if allowed and resolution_kind not in allowed:
            continue
        if not _prerequisites_done(quest, objective):
            continue
        matched.append({
            "quest_id": quest["quest_id"],
            "objective_id": objective["objective_id"],
            "kind": objective_type,
            "target": target,
            "resolution_kind": resolution_kind,
            "action_id": action_id,
        })
    return matched


def _apply_one(quest, evidence):
    if evidence["quest_id"] != quest.get("quest_id"):
        return None
    objective = next(
        (item for item in quest.get("objectives", []) if item.get("objective_id") == evidence["objective_id"]),
        None,
    )
    if objective is None or objective.get("graph_state") != "ACTIVE":
        return None
    if objective.get("target") != evidence.get("target"):
        return None
    if evidence.get("kind") != objective.get("type"):
        return None
    allowed = objective.get("resolution_kinds") or []
    if allowed and evidence.get("resolution_kind") not in allowed:
        return None
    if not isinstance(evidence.get("action_id"), str) or not evidence["action_id"]:
        return None
    if not _prerequisites_done(quest, objective):
        return None
    objective["progress"] = objective["required_count"]
    objective["graph_state"] = "COMPLETE"
    objective["status"] = "completed"
    objective["visibility"] = "known"
    quest.setdefault("timeline", [])
    if len(quest["timeline"]) < 12:
        quest["timeline"].append(objective["description"])
    return {
        "quest_id": quest["quest_id"],
        "objective_id": objective["objective_id"],
        "graph_state": "COMPLETE",
    }


def _leave_unfinished_threat(quest, before_world, world):
    """Leaving the captive room after a rescue, without a defeat, fails only the threat."""
    if _dungeon_node(before_world) != "captive" or _dungeon_node(world) != "exit":
        return
    by_id = {item.get("objective_id"): item for item in quest.get("objectives", [])}
    rescue = by_id.get("rescue")
    threat = by_id.get("threat")
    if not isinstance(rescue, dict) or not isinstance(threat, dict):
        return
    if rescue.get("graph_state") != "COMPLETE" or threat.get("graph_state") != "ACTIVE":
        return
    threat["graph_state"] = "FAILED"
    threat["status"] = "failed"
    threat["visibility"] = "known"


def fail_objective(quest, objective_id):
    objective = next(
        (item for item in quest.get("objectives", []) if item.get("objective_id") == objective_id),
        None,
    )
    if objective is None or objective.get("graph_state") not in {"ACTIVE", "HIDDEN"}:
        return False
    objective["graph_state"] = "FAILED"
    objective["status"] = "failed"
    objective["visibility"] = "known"
    _close_if_resolved({"flags": {"turn_index": quest["updated_turn"]}}, quest)
    return True


def _prerequisites_done(quest, objective):
    by_id = {item["objective_id"]: item for item in quest.get("objectives", [])}
    return all(by_id[item]["graph_state"] == "COMPLETE" for item in objective.get("prerequisites", []) if item in by_id)


def _reveal_ready(quest):
    for objective in quest.get("objectives", []):
        if objective.get("graph_state") != "HIDDEN":
            continue
        if _prerequisites_done(quest, objective):
            objective["graph_state"] = "ACTIVE"
            objective["status"] = "active"
            objective["visibility"] = "known"


def _close_if_resolved(world, quest):
    if quest.get("status") not in {"ACTIVE", "BLOCKED", "DISCOVERED"}:
        return
    states = [item["graph_state"] for item in quest.get("objectives", [])]
    if any(item == "ACTIVE" or item == "HIDDEN" for item in states):
        return
    if not any(item == "COMPLETE" for item in states):
        outcome = "failed"
        state = "FAILED"
    elif any(item == "FAILED" for item in states):
        outcome = "partial_success"
        state = "COMPLETED"
    else:
        outcome = "success"
        state = "COMPLETED"
    turn = world.get("flags", {}).get("turn_index", quest["updated_turn"])
    if not isinstance(turn, int) or turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    closed = transition(quest, state, turn, outcome=outcome)
    quest.clear()
    quest.update(closed)


def public_objectives(quest):
    """Known nodes only. Hidden nodes are omitted, not shown as locked."""
    visible = []
    for objective in quest.get("objectives", []):
        if objective.get("visibility") != "known" or objective.get("graph_state") == "HIDDEN":
            continue
        visible.append({
            "text": objective.get("description"),
            "done": objective.get("graph_state") == "COMPLETE",
        })
    return visible
