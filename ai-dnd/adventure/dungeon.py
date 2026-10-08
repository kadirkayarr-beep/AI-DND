"""A small dungeon graph. Mechanics stay with their existing owners."""

from __future__ import annotations

import copy

HIDEOUT_ID = "bandit_hideout_v1"

HIDEOUT = {
    "dungeon_id": HIDEOUT_ID,
    "entry": "entrance",
    "exit": "exit",
    "nodes": {
        "entrance": {"title": "Saklı giriş", "encounter_recipe_id": None},
        "fork": {"title": "Çatal koridor", "encounter_recipe_id": None},
        "guarded": {"title": "Nöbet odası", "encounter_recipe_id": "dungeon_room"},
        "hidden_route": {"title": "Dar geçit", "encounter_recipe_id": None},
        "captive": {"title": "Tutsak odası", "encounter_recipe_id": "dungeon_room"},
        "exit": {"title": "Dışarı", "encounter_recipe_id": None},
    },
    "edges": [
        {"edge_id": "in_fork", "source": "entrance", "destination": "fork", "hidden": False, "door": None, "hazard": None},
        {"edge_id": "fork_guard", "source": "fork", "destination": "guarded", "hidden": False, "door": "barred", "hazard": None},
        {"edge_id": "fork_hidden", "source": "fork", "destination": "hidden_route", "hidden": True, "door": None, "hazard": None},
        {"edge_id": "guard_captive", "source": "guarded", "destination": "captive", "hidden": False, "door": None, "hazard": "loose_beam"},
        {"edge_id": "hidden_captive", "source": "hidden_route", "destination": "captive", "hidden": False, "door": None, "hazard": None},
        {"edge_id": "captive_exit", "source": "captive", "destination": "exit", "hidden": False, "door": None, "hazard": None},
    ],
}


def empty_discovery(campaign_id):
    return {
        "dungeon_id": HIDEOUT_ID,
        "campaign_id": campaign_id,
        "node": "entrance",
        "discovered_nodes": ["entrance"],
        "discovered_edges": [],
        "opened_doors": [],
    }


def ensure(world, campaign_id):
    dungeons = world.setdefault("dungeon_discovery", {})
    if not isinstance(dungeons, dict):
        world["dungeon_discovery"] = {}
        dungeons = world["dungeon_discovery"]
    current = dungeons.get(HIDEOUT_ID)
    if not isinstance(current, dict) or current.get("campaign_id") != campaign_id:
        dungeons[HIDEOUT_ID] = empty_discovery(campaign_id)
    return dungeons[HIDEOUT_ID]


def visible_exits(world, campaign_id):
    state = ensure(world, campaign_id)
    exits = []
    for edge in HIDEOUT["edges"]:
        if edge["source"] != state["node"]:
            continue
        if edge["hidden"] and edge["edge_id"] not in state["discovered_edges"]:
            continue
        exits.append({
            "title": HIDEOUT["nodes"][edge["destination"]]["title"],
            "door": edge["door"] if edge["edge_id"] not in state["opened_doors"] else None,
            "hazard": edge["hazard"],
        })
    return exits


def move(world, campaign_id, destination):
    state = ensure(world, campaign_id)
    edge = next(
        (
            item for item in HIDEOUT["edges"]
            if item["source"] == state["node"] and item["destination"] == destination
        ),
        None,
    )
    if edge is None:
        raise ValueError("Bu geçit yok.")
    if edge["hidden"] and edge["edge_id"] not in state["discovered_edges"]:
        raise ValueError("Bu geçit yok.")
    if edge["door"] and edge["edge_id"] not in state["opened_doors"]:
        raise ValueError("Kapı kapalı.")
    state["node"] = destination
    if destination not in state["discovered_nodes"]:
        state["discovered_nodes"].append(destination)
    if edge["edge_id"] not in state["discovered_edges"]:
        state["discovered_edges"].append(edge["edge_id"])
    return copy.deepcopy(state)


def reveal_hidden(world, campaign_id, edge_id):
    state = ensure(world, campaign_id)
    edge = next((item for item in HIDEOUT["edges"] if item["edge_id"] == edge_id), None)
    if edge is None or not edge["hidden"] or edge["source"] != state["node"]:
        raise ValueError("Gizli geçit bulunamadı.")
    if edge_id not in state["discovered_edges"]:
        state["discovered_edges"].append(edge_id)
    return copy.deepcopy(state)


def open_door(world, campaign_id, edge_id):
    state = ensure(world, campaign_id)
    edge = next((item for item in HIDEOUT["edges"] if item["edge_id"] == edge_id), None)
    if edge is None or edge["door"] is None or edge["source"] != state["node"]:
        raise ValueError("Kapı yok.")
    if edge_id not in state["opened_doors"]:
        state["opened_doors"].append(edge_id)
    return copy.deepcopy(state)
