"""Small fixed-effect scheduled events, separate from ambient/travel randomness."""

from __future__ import annotations

import copy

BEHAVIORS = {"NON_INTERRUPTIVE", "INTERRUPTIVE", "OBSERVABLE"}


def validate_events(events, world):
    if not isinstance(events, list) or len(events) > 256:
        raise ValueError("Scheduled events are invalid.")
    ids = set()
    for event in events:
        required = {"event_id", "window_start", "window_end", "location_id",
                    "prerequisites", "behavior", "status", "effects", "summary",
                    "aftermath", "visibility", "player_observed", "encounter_status",
                    "canonical_result", "player_known_summary"}
        if not isinstance(event, dict) or set(event) != required:
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
                if set(effect) != {"kind", "key", "value"} or not str(effect["key"]).startswith("scheduled:") or type(effect["value"]) is not bool:
                    raise ValueError("Scheduled flag effect is invalid.")
            else:
                raise ValueError("Unsupported scheduled effect.")
        result = event["canonical_result"]
        if event["status"] == "OCCURRED":
            if not isinstance(result, dict) or set(result) != {"resolved_at", "effects_applied"} or type(result["resolved_at"]) is not int or result["effects_applied"] != len(event["effects"]):
                raise ValueError("Scheduled canonical result is invalid.")
        elif result is not None:
            raise ValueError("Unresolved scheduled event has a canonical result.")
        if event["player_observed"] and event["status"] != "OCCURRED":
            raise ValueError("Observation requires a canonical occurrence.")
        if not event["player_observed"] and event["player_known_summary"]:
            raise ValueError("Unknown event cannot have player knowledge.")


def register_event(world, *, event_id, window_start, window_end, location_id,
                   effects=(), summary="", aftermath="", behavior="OBSERVABLE",
                   prerequisites=None, visibility="public"):
    """Server-owned definitions only; intentionally no public scheduling endpoint."""
    event = {
        "event_id": event_id, "window_start": window_start, "window_end": window_end,
        "location_id": location_id, "effects": copy.deepcopy(list(effects)),
        "summary": summary, "aftermath": aftermath, "behavior": behavior,
        "prerequisites": copy.deepcopy(prerequisites or {}), "visibility": visibility,
        "status": "PENDING", "player_observed": False, "encounter_status": "UNKNOWN",
        "canonical_result": None, "player_known_summary": "",
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
    event["status"] = "OCCURRED"
    event["canonical_result"] = {"resolved_at": at, "effects_applied": len(event["effects"])}


def process_events(world, old, now, *, observation=None):
    """No retroactive interruptions. At window close, resolve unseen world effects.

    An explicit, local observation can establish occurrence inside the window.
    Otherwise occurrence is committed at window end, not a fabricated random instant.
    """
    events = world.get("scheduled_events", [])
    validate_events(events, world)
    known = []
    for event in sorted(events, key=lambda e: (e["window_end"], e["event_id"])):
        local = (
            observation is not None
            and observation.get("location_id") == event["location_id"] == world.get("location")
            and observation.get("kind") in {"look", "observe", "arrival"}
            and event["visibility"] == "public"
        )
        active = event["window_start"] <= now < event["window_end"]
        if event["status"] == "PENDING" and now >= event["window_end"]:
            if _eligible(event, world):
                _occur(event, world, event["window_end"])
            else:
                event["status"] = "EXPIRED"
            if not event["player_observed"]:
                event["encounter_status"] = "MISSED"
        elif event["status"] == "PENDING" and active:
            if _eligible(event, world):
                event["encounter_status"] = "AVAILABLE"
                if local:
                    _occur(event, world, now)
        if local and event["status"] == "OCCURRED":
            text = event["summary"] if active else event["aftermath"]
            if text:
                event["player_observed"] = True
                event["player_known_summary"] = text
                event["encounter_status"] = "OBSERVED"
                known.append(public_event(event, now))
    return known


def public_event(event, now):
    return {
        "summary": event["player_known_summary"],
        "window_start": event["window_start"], "window_end": event["window_end"],
        "status": event["status"],
    }


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