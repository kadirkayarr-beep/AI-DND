"""Player-safe adventure text. Internal ids stay in the engine record."""

from __future__ import annotations

AFFORDANCE_LABELS = {
    "investigate": "İz ara",
    "discover_clue": "Odayı incele",
    "visit_location": "Oraya git",
    "rescue_person": "Sessizce yaklaş",
    "defeat_entity": "Karşılaş",
}


def affordances(quest):
    if not isinstance(quest, dict) or quest.get("status") not in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
        return []
    labels = []
    for objective in quest.get("objectives", []):
        if objective.get("visibility") != "known" or objective.get("graph_state") != "ACTIVE":
            continue
        label = AFFORDANCE_LABELS.get(objective.get("type"))
        if label and label not in labels:
            labels.append(label)
    return labels


def journal(world, lore_state=None):
    rumors = []
    active = []
    completed = []
    failed = []
    timeline = []
    labels = []
    from adventure.play import dungeon_affordances

    labels.extend(dungeon_affordances(world))
    heard = _heard_rumors(world, lore_state)
    for text in heard:
        rumors.append({"label": "Söylenti", "text": text})
    for quest in world.get("quests", []):
        if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
            continue
        card = {
            "title": quest.get("title"),
            "summary": quest.get("description"),
            "objectives": [
                objective["description"]
                for objective in quest.get("objectives", [])
                if objective.get("visibility") == "known" and objective.get("graph_state") != "HIDDEN"
            ],
        }
        status = quest.get("status")
        if status in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
            if status in {"ACTIVE", "BLOCKED"}:
                active.append(card)
            labels.extend(affordances(quest))
        elif status == "COMPLETED":
            completed.append({**card, "label": "Doğrulandı"})
        elif status in {"FAILED", "ABANDONED"}:
            failed.append(card)
        for objective in quest.get("objectives", []):
            if (
                objective.get("type") == "discover_clue"
                and objective.get("graph_state") == "COMPLETE"
                and objective.get("visibility") == "known"
            ):
                rumors.append({"label": "İpucu", "text": objective.get("description") or ""})
        for line in quest.get("timeline", []):
            if isinstance(line, str):
                timeline.append(line)
    return {
        "rumors": rumors[:6],
        "active": active[:4],
        "completed": completed[:6],
        "failed": failed[:6],
        "timeline": timeline[:12],
        "affordances": labels[:6],
    }


def command_view(quest):
    """Legacy command shape. The stored dynamic row is not rewritten."""
    status = {
        "ACTIVE": "accepted",
        "BLOCKED": "accepted",
        "COMPLETED": "completed",
        "ABANDONED": "cancelled",
        "FAILED": "cancelled",
    }.get(quest.get("status"))
    if status is None:
        raise ValueError("Quest is not available.")
    objectives = []
    for objective in quest.get("objectives", []):
        if objective.get("visibility") != "known" or objective.get("graph_state") == "HIDDEN":
            continue
        objectives.append({
            "objective_id": objective["objective_id"],
            "description": objective["description"],
            "status": {
                "COMPLETE": "completed",
                "FAILED": "cancelled",
            }.get(objective.get("graph_state"), "active"),
            "progress": objective.get("progress", 0),
            "required_count": objective.get("required_count", 1),
        })
    return {
        "quest_id": quest["quest_id"],
        "title": quest["title"],
        "description": quest["description"],
        "status": status,
        "giver_npc_id": quest.get("giver_npc_id"),
        "objectives": objectives,
    }


def _heard_rumors(world, lore_state):
    if lore_state is None:
        return []
    from api.lore_authority.player_knowledge import read_player_knowledge
    from api.lore_authority.registry import LoreRegistry

    projection = read_player_knowledge(lore_state, world, LoreRegistry.empty())
    return [
        item["text"]
        for item in projection.get("adventure_possibilities", [])
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]


def model_packet(world, lore_state=None):
    """Verified player-safe slice. Hidden nodes and unused candidates stay out."""
    from adventure.play import known_place

    visible = journal(world, lore_state)
    packet = {
        "rumors": [item["text"] for item in visible["rumors"]],
        "active": [
            {"title": item["title"], "objectives": item["objectives"]}
            for item in visible["active"]
        ],
        "latest": visible["timeline"][-1] if visible["timeline"] else None,
    }
    place = known_place(world)
    if place is not None:
        packet["place"] = place
    return packet
