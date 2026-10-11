"""Small fixed-effect scheduled events, separate from ambient/travel randomness."""

from __future__ import annotations

import copy
import logging

BEHAVIORS = {"NON_INTERRUPTIVE", "INTERRUPTIVE", "OBSERVABLE", "FORCED"}
EXTENSIONS = {"dependencies", "priority", "causal_group", "requires_decision",
              "decision_status", "player_decision", "combat_npc_id",
              "route_destination", "followups", "aftermath_visible"}


def validate_events(events, world):
    if not isinstance(events, list) or len(events) > 256:
        raise ValueError("Scheduled events are invalid.")
    ids = set()
    for event in events:
        required = {"event_id", "window_start", "window_end", "location_id",
                    "prerequisites", "behavior", "status", "effects", "summary",
                    "aftermath", "visibility", "player_observed", "encounter_status",
                    "canonical_result", "player_known_summary"}
        if not isinstance(event, dict) or not required <= set(event) <= required | EXTENSIONS:
            raise ValueError("Scheduled event fields are invalid.")
        if not isinstance(event["event_id"], str) or not event["event_id"] or event["event_id"] in ids:
            raise ValueError("Scheduled event identity is invalid.")
        ids.add(event["event_id"])
        if any(type(event[k]) is not int or event[k] < 0 for k in ("window_start", "window_end")) or event["window_end"] <= event["window_start"]:
            raise ValueError("Scheduled event window is invalid.")
        if event["location_id"] not in world.get("locations", {}):
            raise ValueError("Scheduled event location is not registered.")
        if event["behavior"] not in BEHAVIORS or event["status"] not in {"PENDING", "OCCURRED", "EXPIRED"}:
            raise ValueError("Scheduled event status is invalid.")
        if event["visibility"] not in {"public", "hidden"} or type(event["player_observed"]) is not bool:
            raise ValueError("Scheduled event visibility is invalid.")
        if event["encounter_status"] not in {"UNKNOWN", "AVAILABLE", "OBSERVED", "MISSED"}:
            raise ValueError("Scheduled encounter status is invalid.")
        if not isinstance(event["prerequisites"], dict) or any(
            not isinstance(k, str) or type(v) is not bool for k, v in event["prerequisites"].items()
        ):
            raise ValueError("Scheduled prerequisites are invalid.")
        if any(not isinstance(event[k], str) or len(event[k]) > 1000 for k in ("summary", "aftermath", "player_known_summary")):
            raise ValueError("Scheduled event presentation is invalid.")
        if not isinstance(event["effects"], list):
            raise ValueError("Scheduled effects are invalid.")
        for effect in event["effects"]:
            if not isinstance(effect, dict):
                raise ValueError("Scheduled effect is invalid.")
            if effect.get("kind") == "npc_location":
                if set(effect) != {"kind", "npc_id", "location_id"} or effect["location_id"] not in world.get("locations", {}) or not any(
                    npc.get("id") == effect["npc_id"] for npc in world.get("npcs", [])
                ):
                    raise ValueError("Scheduled NPC movement is invalid.")
            elif effect.get("kind") == "flag":
                if set(effect) != {"kind", "key", "value"} or not isinstance(effect["key"], str) or not effect["key"].startswith("scheduled:") or type(effect["value"]) is not bool:
                    raise ValueError("Scheduled flag effect is invalid.")
            elif effect.get("kind") == "npc_hostility":
                if set(effect) != {"kind", "npc_id", "hostile"} or type(effect["hostile"]) is not bool or not any(
                    npc.get("id") == effect["npc_id"] for npc in world.get("npcs", [])
                ):
                    raise ValueError("Scheduled hostility is invalid.")
            elif effect.get("kind") == "route_block":
                if set(effect) != {"kind", "origin", "destination", "blocked"} or type(effect["blocked"]) is not bool or any(
                    effect[k] not in world.get("locations", {}) for k in ("origin", "destination")
                ):
                    raise ValueError("Scheduled route obstacle is invalid.")
            else:
                raise ValueError("Unsupported scheduled effect.")
        result = event["canonical_result"]
        if event["status"] == "OCCURRED":
            if not isinstance(result, dict) or set(result) != {"resolved_at", "effects_applied"} or type(result["resolved_at"]) is not int or result["resolved_at"] < event["window_start"] or type(result["effects_applied"]) is not int or result["effects_applied"] != len(event["effects"]):
                raise ValueError("Scheduled canonical result is invalid.")
        elif result is not None:
            raise ValueError("Unresolved scheduled event has a canonical result.")
        if event["player_observed"] and event["status"] != "OCCURRED":
            raise ValueError("Observation requires a canonical occurrence.")
        if not event["player_observed"] and event["player_known_summary"]:
            raise ValueError("Unknown event cannot have player knowledge.")
        dependencies = event.get("dependencies", [])
        if not isinstance(dependencies, list) or len(dependencies) > 256 or any(
            not isinstance(d, str) or not d for d in dependencies
        ) or len(set(dependencies)) != len(dependencies):
            raise ValueError("Scheduled dependencies are invalid.")
        if type(event.get("priority", 0)) is not int or not -1000 <= event.get("priority", 0) <= 1000:
            raise ValueError("Scheduled priority is invalid.")
        if not isinstance(event.get("causal_group", ""), str) or len(event.get("causal_group", "")) > 100:
            raise ValueError("Scheduled causal group is invalid.")
        if any(type(event.get(k, False)) is not bool for k in ("requires_decision", "aftermath_visible")):
            raise ValueError("Scheduled decision visibility is invalid.")
        decision = event.get("decision_status", "NONE")
        if decision not in {"NONE", "PENDING", "IN_COMBAT", "RESOLVED"} or (
            decision != "NONE" and (event["status"] != "OCCURRED" or not event["player_observed"])
        ):
            raise ValueError("Scheduled decision state is invalid.")
        if decision != "NONE" and not _decision_required(event):
            raise ValueError("Noninteractive event cannot hold a player decision.")
        if not isinstance(event.get("player_decision", ""), str) or len(event.get("player_decision", "")) > 100:
            raise ValueError("Scheduled player decision is invalid.")
        npc_id = event.get("combat_npc_id")
        if npc_id is not None and not any(n.get("id") == npc_id for n in world.get("npcs", [])):
            raise ValueError("Scheduled combat target is invalid.")
        route = event.get("route_destination")
        if route is not None and route not in world.get("locations", {}):
            raise ValueError("Scheduled travel context is invalid.")
        followups = event.get("followups", [])
        if not isinstance(followups, list) or len(followups) > 16:
            raise ValueError("Scheduled followups are invalid.")
        for definition in followups:
            if not isinstance(definition, dict) or "followups" in definition:
                raise ValueError("Only bounded, nonrecursive followup definitions are allowed.")
            try:
                candidate_world = dict(world, scheduled_events=[])
                register_event(candidate_world, **copy.deepcopy(definition))
            except (TypeError, ValueError):
                raise ValueError("Scheduled followup definition is invalid.") from None


def register_event(world, *, event_id, window_start, window_end, location_id,
                   effects=(), summary="", aftermath="", behavior="OBSERVABLE",
                   prerequisites=None, visibility="public", dependencies=(), priority=0,
                   causal_group="", requires_decision=False, combat_npc_id=None,
                   route_destination=None, followups=(), aftermath_visible=None):
    """Server-owned definitions only; intentionally no public scheduling endpoint."""
    event = {
        "event_id": event_id, "window_start": window_start, "window_end": window_end,
        "location_id": location_id, "effects": copy.deepcopy(list(effects)),
        "summary": summary, "aftermath": aftermath, "behavior": behavior,
        "prerequisites": copy.deepcopy(prerequisites or {}), "visibility": visibility,
        "status": "PENDING", "player_observed": False, "encounter_status": "UNKNOWN",
        "canonical_result": None, "player_known_summary": "",
        "dependencies": list(dependencies), "priority": priority,
        "causal_group": causal_group, "requires_decision": requires_decision,
        "decision_status": "NONE", "player_decision": "", "combat_npc_id": combat_npc_id,
        "route_destination": route_destination, "followups": copy.deepcopy(list(followups)),
        "aftermath_visible": visibility == "public" if aftermath_visible is None else aftermath_visible,
    }
    events = world.get("scheduled_events", [])
    validate_events(events + [event], world)
    world.setdefault("scheduled_events", []).append(event)
    return event


def _eligible(event, world):
    return all(world.get("flags", {}).get(key) == value for key, value in event["prerequisites"].items())


def _occur(event, world, at):
    if event["status"] != "PENDING":
        return
    for effect in event["effects"]:
        if effect["kind"] == "flag":
            world.setdefault("flags", {})[effect["key"]] = effect["value"]
        elif effect["kind"] == "npc_location":
            npc = next(n for n in world["npcs"] if n["id"] == effect["npc_id"])
            npc["location"] = effect["location_id"]
        elif effect["kind"] == "npc_hostility":
            npc = next(n for n in world["npcs"] if n["id"] == effect["npc_id"])
            npc["hostile"] = effect["hostile"]
        elif effect["kind"] == "route_block":
            world.setdefault("blocked_travel_routes", {}).setdefault(effect["origin"], {})[
                effect["destination"]
            ] = effect["blocked"]
    event["status"] = "OCCURRED"
    event["canonical_result"] = {"resolved_at": at, "effects_applied": len(event["effects"])}
    for definition in event.get("followups", []):
        definition = copy.deepcopy(definition)
        definition["dependencies"] = list(dict.fromkeys(
            list(definition.get("dependencies", [])) + [event["event_id"]]
        ))
        register_event(world, **definition)


def _local(event, world, *, travelling=False):
    if travelling:
        journey = world.get("journey") or {}
        return event.get("route_destination") == journey.get("destination") and event.get("route_destination") is not None
    return event["location_id"] == world.get("location") and event.get("route_destination") is None


def _decision_required(event):
    return event["behavior"] == "FORCED" or (
        event["behavior"] == "INTERRUPTIVE" and event.get("requires_decision", False)
    )


def pending_events(world):
    return [e for e in world.get("scheduled_events", []) if e.get("decision_status") in {"PENDING", "IN_COMBAT"}]


def public_pending(world):
    if world.get("player_combat_status") == "unconscious":
        return []
    return [{
        "summary": e["player_known_summary"], "forced": e["behavior"] == "FORCED",
        "in_combat": e.get("decision_status") == "IN_COMBAT",
        "can_fight": any(
            n.get("id") == e.get("combat_npc_id") and n.get("location") == world.get("location")
            and n.get("current_hp", 1) > 0 and n.get("combat_status", "active") == "active"
            for n in world.get("npcs", [])
        ),
    } for e in pending_events(world) if e["player_observed"]]


def combat_finished(world):
    for event in pending_events(world):
        if event.get("decision_status") == "IN_COMBAT":
            event["decision_status"] = "PENDING"


def _blocked_dependencies(events):
    """Bounded Kahn pass: retain cycles/descendants unchanged and report IDs privately."""
    by_id = {e["event_id"]: e for e in events}
    remaining = set(by_id)
    visited = set()
    while remaining:
        ready = {identity for identity in remaining if all(
            dep in visited for dep in by_id[identity].get("dependencies", [])
        )}
        if not ready:
            break
        visited.update(ready)
        remaining.difference_update(ready)
    return remaining


def _observe(event, now, known, *, decision=False):
    active = event["window_start"] <= now < event["window_end"]
    text = event["summary"] if active or decision else event["aftermath"]
    if not text and not decision:
        return
    if event["player_observed"] and event["player_known_summary"] == text and not decision:
        return
    event["player_observed"] = True
    event["player_known_summary"] = text or "Yoluna devam etmeden önce bir karar vermen gerekiyor."
    event["encounter_status"] = "OBSERVED" if active or decision else "MISSED"
    if decision:
        event["decision_status"] = "PENDING"
    known.append(public_event(event, now))


def process_events(world, old, now, *, observation=None, resolution=None,
                   allow_interrupt=False, travelling=False):
    """Bulk chronological resolution. Never modifies the campaign clock itself.

    Default V1 events still commit at window close or real local observation.
    Only explicitly decision-bearing, directly relevant events can stop an action.
    """
    events = world.get("scheduled_events", [])
    validate_events(events, world)
    unconscious = world.get("player_combat_status") == "unconscious"
    if unconscious:
        # World events still progress, but an unconscious player cannot observe
        # them or stop gameplay to make a decision (including an existing one).
        observation = None
        allow_interrupt = False
    known = []
    limit = now
    cursor = old
    existing = [e for e in pending_events(world) if e.get("decision_status") == "PENDING"]
    if allow_interrupt and existing:
        limit = old
    processed = set()
    # The queue is capped at 256, including followups. No recursive event execution.
    for _ in range(256):
        blocked = _blocked_dependencies(events)
        diagnostics = ([{"code": "dependency_cycle_or_missing", "event_ids": sorted(blocked)}] if blocked else [])
        if diagnostics != world.get("scheduled_event_diagnostics", []) and diagnostics:
            logging.getLogger(__name__).warning("Scheduled event dependency cycle/missing reference; blocked_count=%s", len(blocked))
        world["scheduled_event_diagnostics"] = diagnostics
        by_id = {e["event_id"]: e for e in events}
        candidates = []
        for event in events:
            identity = event["event_id"]
            if identity in processed or identity in blocked or event["status"] != "PENDING":
                continue
            if not _in_player_horizon(event, world):
                continue
            dependencies = [by_id[d] for d in event.get("dependencies", [])]
            if any(d["status"] == "PENDING" for d in dependencies):
                continue
            dep_time = max([d["canonical_result"]["resolved_at"] for d in dependencies if d["canonical_result"]] + [0])
            at = max(event["window_end"], dep_time, cursor)
            decision = (allow_interrupt and _local(event, world, travelling=travelling)
                        and event["visibility"] == "public" and _decision_required(event)
                        and _eligible(event, world)
                        and all(d["status"] == "OCCURRED" for d in dependencies))
            if decision:
                encounter_at = max(old, cursor, dep_time, event["window_start"])
                if encounter_at < event["window_end"]:
                    at = encounter_at
                else:
                    decision = False
            # Endpoint observation is an actual encounter, not a retrospective stop.
            observed = (observation and observation.get("kind") in {"look", "observe", "arrival"}
                        and observation.get("location_id") == event["location_id"]
                        and _local(event, world) and event["visibility"] == "public"
                        and event["window_start"] <= limit < event["window_end"])
            if observed and not decision:
                at = max(limit, dep_time)
            if at <= limit:
                candidates.append((at, -event.get("priority", 0), event.get("causal_group", ""),
                                   event["location_id"], identity, event, decision, observed))
        if not candidates:
            break
        at, _, _, _, identity, event, decision, observed = min(candidates, key=lambda c: c[:5])
        processed.add(identity)
        cursor = at
        dependencies_ok = all(by_id[d]["status"] == "OCCURRED" for d in event.get("dependencies", []))
        if dependencies_ok and _eligible(event, world):
            _occur(event, world, at)
            if decision or observed:
                _observe(event, at, known, decision=decision or _decision_required(event))
            else:
                event["encounter_status"] = "MISSED"
            if decision:
                limit = at
                # Independent events at this same point still resolve; nothing
                # after the actual stop point can run.
        elif at >= event["window_end"]:
            event["status"] = "EXPIRED"
            event["encounter_status"] = "MISSED"
    _mark_missed_outside_horizon(events, world, limit)
    # Observation of already-resolved events/aftermath does not reapply effects.
    for event in sorted(events, key=lambda e: (-e.get("priority", 0), e["location_id"], e["event_id"])):
        active = event["window_start"] <= limit < event["window_end"]
        local = (observation and observation.get("kind") in {"look", "observe", "arrival"}
                 and observation.get("location_id") == event["location_id"] and _local(event, world))
        if event["status"] == "PENDING" and active and _eligible(event, world):
            event["encounter_status"] = "AVAILABLE"
        elif event["status"] == "OCCURRED" and local and event.get("decision_status", "NONE") == "NONE" and (
            (active and event["visibility"] == "public")
            or (not active and event.get("aftermath_visible", event["visibility"] == "public"))
        ):
            _observe(event, limit, known, decision=active and _decision_required(event))
    if resolution is not None:
        resolution.update(stop_at=limit, interrupted=not unconscious and bool(
            [e for e in pending_events(world) if e.get("decision_status") == "PENDING"]
        ), diagnostics=copy.deepcopy(world.get("scheduled_event_diagnostics", [])))
    return known


def public_event(event, now):
    return {
        "summary": event["player_known_summary"],
        "window_start": event["window_start"], "window_end": event["window_end"],
        "status": event["status"],
    }


def _mark_missed_outside_horizon(events, world, limit):
    """Record that a due encounter was not faced, without simulating it.

    Full occurrence, effects, narration, and player knowledge stay inside the
    horizon. The deadline only closes the encounter lifecycle.
    """
    for event in events:
        if event["status"] != "PENDING" or event.get("decision_status") not in {None, "NONE"}:
            continue
        if _in_player_horizon(event, world) or event["window_end"] > limit:
            continue
        if event["encounter_status"] in {"UNKNOWN", "AVAILABLE"}:
            event["encounter_status"] = "MISSED"


def _in_player_horizon(event, world):
    """V1 only advances the current settlement, its children, and the active road."""
    here = world.get("location")
    location_id = event.get("location_id")
    if location_id == here:
        return True
    record = world.get("locations", {}).get(location_id)
    if isinstance(record, dict) and record.get("parent_location_id") == here:
        return True
    journey = world.get("journey") or {}
    destination = event.get("route_destination")
    return bool(destination and destination == journey.get("destination"))


def public_events(world):
    now = world.get("campaign_time", {}).get("elapsed_seconds", 0)
    return [public_event(e, now) for e in world.get("scheduled_events", []) if e["player_observed"]]


def visible_npcs(world):
    """Never expose remote locations changed by an unseen scheduled occurrence."""
    hidden = {
        effect["npc_id"]
        for event in world.get("scheduled_events", [])
        if event["status"] == "OCCURRED" and not event["player_observed"]
        for effect in event["effects"] if effect["kind"] == "npc_location"
    }
    return [npc for npc in world.get("npcs", []) if npc.get("id") not in hidden or (
        npc.get("location") == world.get("location")
        and not any(
            e["visibility"] == "hidden" and e["status"] == "OCCURRED" and not e["player_observed"]
            and any(f.get("npc_id") == npc.get("id") for f in e["effects"])
            for e in world.get("scheduled_events", [])
        )
    )]