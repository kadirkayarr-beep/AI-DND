"""Opt-in authored room/exit fixture; no geometry, model or parallel position owner."""
import copy

from combat_lifecycle import CombatRequestError

KEY = "authored_dungeon_v1"
FIXTURE = "three_rooms_v1"
ENTRY = "authored_dungeon_entry"
HALL = "authored_dungeon_hall"
VAULT = "authored_dungeon_vault"
ROOMS = {
    ENTRY: {"id": ENTRY, "name": "Taş Eşik", "type": "dungeon",
            "description": "Küçük, yazar tarafından tanımlanmış bir giriş odası."},
    HALL: {"id": HALL, "name": "Sessiz Salon", "type": "dungeon",
           "description": "Girişe dönen geçidi ve kapalı mahzen geçidi bulunan salon."},
    VAULT: {"id": VAULT, "name": "Kapalı Mahzen", "type": "dungeon",
            "description": "Bu fixture'da salon tarafından erişimi kapalı oda."},
}


def definition(origin):
    return {
        "version": 1, "fixture_id": FIXTURE, "origin_location_id": origin,
        "rooms": list(ROOMS),
        "exits": {
            "origin_entry": {"from": origin, "to": ENTRY, "blocked": False},
            "entry_origin": {"from": ENTRY, "to": origin, "blocked": False},
            "entry_hall": {"from": ENTRY, "to": HALL, "blocked": False},
            "hall_entry": {"from": HALL, "to": ENTRY, "blocked": False},
            "hall_vault": {"from": HALL, "to": VAULT, "blocked": True},
            "vault_hall": {"from": VAULT, "to": HALL, "blocked": False},
        },
    }


def validate_state(world):
    """Legacy absence is valid; saved model/client-authored topology is not."""
    if KEY not in world:
        return
    graph = world[KEY]
    if not isinstance(graph, dict):
        raise ValueError("Invalid authored dungeon state.")
    origin = graph.get("origin_location_id")
    locations = world.get("locations", {})
    if (not isinstance(origin, str) or origin not in locations or origin in ROOMS
            or type(graph.get("version")) is not int
            or graph != definition(origin)):
        raise ValueError("Invalid authored dungeon definition.")
    for room, expected in ROOMS.items():
        if locations.get(room) != {**expected, "reality_layer": "PROCEDURAL_LOCAL_FICTION"}:
            raise ValueError("Invalid authored room identity.")
    if any(type(exit["blocked"]) is not bool for exit in graph["exits"].values()):
        raise ValueError("Invalid authored exit state.")


def require_transition(world, destination):
    """Enforce adjacency at the existing location owner, including non-native callers."""
    import exploration
    exploration.require_transition(world, destination)
    current = world.get("location")
    if KEY not in world or (current not in ROOMS and destination not in ROOMS):
        return
    validate_state(world)
    graph = world.get(KEY)
    if graph is None or not any(
        exit["from"] == current and exit["to"] == destination and not exit["blocked"]
        for exit in graph["exits"].values()
    ):
        raise CombatRequestError("dungeon_transition_forbidden", "No open authored exit connects these locations.", 400)


def native_request(message, session=None):
    return isinstance(message, str) and (
        message.strip().casefold().startswith("/dungeon")
        or session is not None and session.world_state.get(KEY)
        and session.world_state.get("location") in ROOMS
        and session._has_travel_language(message)
    )


def _reply(session, message, narration, action, **details):
    session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
    session.messages.extend([{"role": "user", "content": message},
                             {"role": "assistant", "content": narration}])
    return {"messages": session.messages, "narration": narration, "model_calls": 0,
            "action_result": {"action": action, "status": "resolved", "success": True, **details}}


def resolve_command(session, message):
    if not native_request(message):
        if (session.world_state.get(KEY) and session.world_state.get("location") in ROOMS
                and session._has_travel_language(message)):
            raise CombatRequestError("dungeon_exit_required", "Use /dungeon exit <id> for authored room movement.", 400)
        return None
    parts = message.strip().split()
    if parts[:1] != ["/dungeon"] or not (
        parts in (["/dungeon", "enter"], ["/dungeon", "exits"])
        or len(parts) == 3 and parts[1] == "exit"
    ):
        raise CombatRequestError("invalid_dungeon_command", "Use /dungeon enter, /dungeon exits or /dungeon exit <id>.", 400)
    world = session.world_state
    validate_state(world)
    graph = world.get(KEY)
    current = world.get("location")
    if parts[1] == "enter":
        if graph:
            if current != graph["origin_location_id"]:
                raise CombatRequestError("dungeon_entry_unavailable", "Use this room's authored exits.", 400)
        elif current not in world.get("locations", {}) or any(room in world["locations"] for room in ROOMS):
            raise CombatRequestError("dungeon_origin_invalid", "A registered origin and unused room identities are required.", 400)
        destination = ENTRY
    else:
        if graph is None or current not in ROOMS:
            raise CombatRequestError("dungeon_not_entered", "Enter the authored fixture first.", 400)
        if parts[1] == "exits":
            exits = [(identity, exit) for identity, exit in graph["exits"].items() if exit["from"] == current]
            text = "; ".join(
                f"{identity} → {world['locations'][exit['to']]['name']} ({'kapalı' if exit['blocked'] else 'açık'})"
                for identity, exit in exits
            )
            return _reply(session, message, text, "dungeon_exits")
        exit = graph["exits"].get(parts[2])
        if exit is None or exit["from"] != current:
            raise CombatRequestError("dungeon_exit_unknown", "That exit does not belong to this room.", 400)
        if exit["blocked"]:
            raise CombatRequestError("dungeon_exit_blocked", "That authored exit is blocked.", 400)
        destination = exit["to"]
    # Do not teleport out of combat, an interrupted journey or a pending task/decision.
    if (world.get("combat", {}).get("active") or world.get("active_task")
            or (world.get("journey") or {}).get("status", "ARRIVED") != "ARRIVED"
            or any(e.get("decision_status") == "PENDING" for e in world.get("scheduled_events", []))):
        raise CombatRequestError("dungeon_transition_busy", "Resolve current combat, task or travel decisions first.", 400)
    session.require_player_can_act()
    if graph is None:
        world[KEY] = definition(current)
        world["locations"].update({
            identity: {**copy.deepcopy(room), "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
            for identity, room in ROOMS.items()
        })
    session.commit_location_change(destination)
    return _reply(session, message, f"{world['locations'][destination]['name']} konumuna geçtin.",
                  "dungeon_traverse", previous_location=current, new_location=destination,
                  exit_id="origin_entry" if parts[1] == "enter" else parts[2])
