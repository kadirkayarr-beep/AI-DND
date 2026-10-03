"""Bounded V1 tasks and pedestrian journey stages; no generic quest engine."""

from __future__ import annotations

import re

import campaign_time as clock
import living_world
from scheduled_events import process_events

# Finite local encounters, not monsters, damage, or scheduled world events.
TRAVEL_CATALOG = (
    {"id": "traveler", "text": "Yol ayrımında yön arayan bir yolcuya rastlıyorsun."},
    {"id": "wagon", "text": "Yol kenarında yükünü düzenleyen bir arabacı var."},
    {"id": "crossing", "text": "Dar geçitte karşıdan gelenler yolun açılmasını bekliyor."},
)
DISPOSITIONS = ("sakin", "temkinli", "zorlanıyor")


def validate_state(world):
    task = world.get("active_task")
    if task is not None:
        if not isinstance(task, dict) or set(task) != {"location_id", "target_id", "kind", "required_seconds", "spent_seconds", "dc"}:
            raise ValueError("Active task fields are invalid.")
        if task["location_id"] not in world.get("locations", {}) or task["kind"] != "search":
            raise ValueError("Active task scope is invalid.")
        if type(task["required_seconds"]) is not int or not 1 <= task["required_seconds"] <= clock.DAY:
            raise ValueError("Task duration is invalid.")
        if type(task["spent_seconds"]) is not int or not 0 <= task["spent_seconds"] < task["required_seconds"]:
            raise ValueError("Task progress is invalid.")
        if task["dc"] is not None and (type(task["dc"]) is not int or task["dc"] not in {10, 15, 20, 25, 30}):
            raise ValueError("Task uncertainty is invalid.")
    journey = world.get("journey")
    if journey is not None:
        if not isinstance(journey, dict) or set(journey) != {
            "origin", "destination", "stages", "stage_index", "stage_spent_seconds",
            "stage_checked", "status", "encounter", "recent_patterns"
        }:
            raise ValueError("Journey fields are invalid.")
        if any(journey[k] not in world.get("locations", {}) for k in ("origin", "destination")):
            raise ValueError("Journey location is invalid.")
        stages = journey["stages"]
        if not isinstance(stages, list) or not 1 <= len(stages) <= 48 or any(type(s) is not int or not 1 <= s <= clock.DAY for s in stages):
            raise ValueError("Journey stages are invalid.")
        index = journey["stage_index"]
        if type(index) is not int or not 0 <= index < len(stages):
            raise ValueError("Journey stage index is invalid.")
        if type(journey["stage_spent_seconds"]) is not int or not 0 <= journey["stage_spent_seconds"] <= stages[index] or type(journey["stage_checked"]) is not bool:
            raise ValueError("Journey progress is invalid.")
        if journey["status"] not in {"TRAVELLING", "INTERRUPTED", "STOPPED", "ARRIVED"}:
            raise ValueError("Journey status is invalid.")
        if not isinstance(journey["recent_patterns"], list) or len(journey["recent_patterns"]) > 2 or any(p not in {e["id"] for e in TRAVEL_CATALOG} for p in journey["recent_patterns"]):
            raise ValueError("Journey recent events are invalid.")
        encounter = journey["encounter"]
        if encounter is not None:
            if not isinstance(encounter, dict) or set(encounter) != {"pattern", "text", "disposition", "dice"}:
                raise ValueError("Travel encounter fields are invalid.")
            if encounter["pattern"] not in {e["id"] for e in TRAVEL_CATALOG} or encounter["disposition"] not in DISPOSITIONS or not isinstance(encounter["text"], str):
                raise ValueError("Travel encounter is invalid.")
            dice = encounter["dice"]
            if not isinstance(dice, dict) or set(dice) != {"occurrence", "type", "disposition"} or any(type(v) is not int or not 1 <= v <= 6 for v in dice.values()):
                raise ValueError("Travel dice are invalid.")


def travel_dice(rng, recent):
    occurrence = rng.randint(1, 6)
    dice = {"occurrence": occurrence, "type": None, "disposition": None}
    if occurrence > 2:
        return None, dice
    candidates = [e for e in TRAVEL_CATALOG if not recent or e["id"] != recent[-1]]
    kind = rng.randint(1, 6)
    disposition = rng.randint(1, 6)
    chosen = candidates[(kind - 1) % len(candidates)]
    return {
        "pattern": chosen["id"], "text": chosen["text"],
        "disposition": DISPOSITIONS[(disposition - 1) // 2],
        "dice": {"occurrence": occurrence, "type": kind, "disposition": disposition},
    }, {"occurrence": occurrence, "type": kind, "disposition": disposition}


def _advance(session, seconds, reason, observation=None):
    return clock.advance(
        session.world_state, seconds, reason,
        f"turn:{session.world_state.get('flags', {}).get('turn_index', 0)}",
        observation=observation,
    )


def _result(action, text, advancement=None, **extra):
    result = {"action": action, "status": "completed", "success": True,
              "state_changes": ["campaign_time"] if advancement else [],
              "direct_response": text, **extra}
    if advancement is not None:
        result["time_result"] = advancement
        known = advancement["player_known_events"]
        if known:
            result["direct_response"] += " " + " ".join(e["summary"] for e in known)
    return result


def route_stages(world, destination):
    origin = world.get("location")
    if destination == origin:
        return []
    location = world.get("locations", {}).get(origin, {})
    route = location.get("travel_routes", {}).get(destination)
    if route is not None:
        if not isinstance(route, list) or not 1 <= len(route) <= 48 or any(type(s) is not int or not 1 <= s <= clock.DAY for s in route):
            raise ValueError("Server travel route duration is invalid.")
        return list(route)
    target = world.get("locations", {}).get(destination, {})
    # Explicit V1 local pedestrian convention, never an estimate from Qwen.
    # Cross-region trips require server-defined travel_routes.
    if location.get("region_id") == target.get("region_id") and (
        location.get("region_id") is not None
        or (location.get("reality_layer") == target.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION")
    ):
        return [300]
    origin_anchor = living_world.location_anchor_id(world, origin)
    target_anchor = living_world.location_anchor_id(world, destination)
    if origin_anchor and origin_anchor == target_anchor:
        return [300]
    if target.get("parent_location_id") == origin or location.get("parent_location_id") == destination:
        return [300]
    return None


def start_travel(session, destination):
    world = session.world_state
    if session.ensure_combat_state()["active"]:
        return _result("travel", "Çatışma sırasında bu yolculuğa başlayamazsın.", status="unsupported", success=False)
    stages = route_stages(world, destination)
    if stages is None:
        return _result("travel", "Bu yolun süresi henüz belirlenmiş değil; yolculuk başlamadı.", status="unverified", success=False)
    if not stages:
        journey = world.get("journey")
        if journey and journey["status"] != "ARRIVED":
            spent = sum(journey["stages"][:journey["stage_index"]]) + journey["stage_spent_seconds"]
            advancement = _advance(session, spent, "travel_return")
            journey["status"] = "ARRIVED"
            journey["destination"] = destination
            return _result("travel", "Geldiğin yoldan geri döndün.", advancement)
        return _result("travel", "Zaten buradasın.")
    previous = world.get("journey")
    retraced = 0
    start_time = clock.public_time(world)
    if previous and previous["status"] != "ARRIVED":
        # Rerouting uses known routes from the last registered anchor, not an
        # invented shortcut from a midpoint whose geography is not modeled.
        retraced = sum(previous["stages"][:previous["stage_index"]]) + previous["stage_spent_seconds"]
        _advance(session, retraced, "travel_reroute_return")
    recent = world.get("journey", {}).get("recent_patterns", []) if isinstance(world.get("journey"), dict) else []
    world["journey"] = {
        "origin": world["location"], "destination": destination, "stages": stages,
        "stage_index": 0, "stage_spent_seconds": 0, "stage_checked": False,
        "status": "TRAVELLING", "encounter": None, "recent_patterns": list(recent),
    }
    world["active_task"] = None
    result = continue_travel(session)
    if retraced:
        result["time_result"]["elapsed_seconds"] += retraced
        result["time_result"]["before"] = start_time
        result["direct_response"] = "Bildiğin yol ayrımına geri dönüp yeni yolu seçtin. " + result["direct_response"]
    return result


def continue_travel(session):
    world = session.world_state
    journey = world["journey"]
    journey["status"] = "TRAVELLING"
    journey["encounter"] = None
    seconds = journey["stages"][journey["stage_index"]]
    elapsed = 0
    dice = None
    before = clock.public_time(world)
    known_events = []
    if not journey["stage_checked"]:
        midpoint = seconds // 2
        elapsed = max(0, midpoint - journey["stage_spent_seconds"])
        advance = _advance(session, elapsed, "travel_stage")
        known_events.extend(advance["player_known_events"])
        journey["stage_spent_seconds"] += elapsed
        journey["stage_checked"] = True
        encounter, dice = travel_dice(session.rng, journey["recent_patterns"])
        if encounter:
            journey["encounter"] = encounter
            journey["status"] = "INTERRUPTED"
            journey["recent_patterns"] = (journey["recent_patterns"] + [encounter["pattern"]])[-2:]
            return _result("travel", encounter["text"] + " Devam edebilir, durabilir veya başka bir yol seçebilirsin.",
                           advance, status="interrupted", travel_dice=dice)
    remaining = seconds - journey["stage_spent_seconds"]
    advance = _advance(session, remaining, "travel_stage")
    advance["before"] = before
    advance["player_known_events"] = known_events + advance["player_known_events"]
    advance["elapsed_seconds"] += elapsed
    journey["stage_spent_seconds"] = seconds
    if journey["stage_index"] + 1 < len(journey["stages"]):
        journey["stage_index"] += 1
        journey["stage_spent_seconds"] = 0
        journey["stage_checked"] = False
        return _result("travel", "Yolun bu kısmını tamamladın. Devam etmek veya durmak sana kalmış.", advance, status="stage_completed", travel_dice=dice)
    destination = journey["destination"]
    session.commit_location_change(destination)
    journey["status"] = "ARRIVED"
    now = world["campaign_time"]["elapsed_seconds"]
    known = process_events(world, now, now, observation={"kind": "arrival", "location_id": destination})
    advance["player_known_events"].extend(known)
    world.setdefault("flags", {})["pending_destination"] = None
    return _result("travel", f"{session.location_display_name(destination)} konumuna vardın.", advance,
                   new_location=destination, travel_dice=dice)


def resolve_task(session, text, budget):
    world = session.world_state
    location = world["location"]
    features = session._scene_feature_match(text, location)
    if len(features) > 1:
        return _result("task", "Hangi yeri araştırmak istediğini belirt.", status="clarification", success=False)
    target = features[0] if features else world["locations"].get(location, {})
    target_id = target.get("id", location)
    task = world.get("active_task")
    if task is None or task["target_id"] != target_id or task["location_id"] != location:
        # A finite pass over one registered scene/feature, not every freeform action.
        required = target.get("search_duration_seconds", 360)
        dc = target.get("search_dc")
        task = {"location_id": location, "target_id": target_id, "kind": "search",
                "required_seconds": required, "spent_seconds": 0, "dc": dc}
        candidate = dict(world, active_task=task)
        validate_state(candidate)
        world["active_task"] = task
    duration = min(budget if budget is not None else task["required_seconds"], task["required_seconds"] - task["spent_seconds"])
    advancement = _advance(session, duration, "active_task")
    task["spent_seconds"] += duration
    if task["spent_seconds"] < task["required_seconds"]:
        return _result("task", "İncelemen henüz tamamlanmadı; araştırmaya devam edebilirsin.",
                       advancement, status="in_progress")
    check = None
    success = True
    if task["dc"] is not None:
        character = session.character
        check = session.perform_skill_check(
            "Investigation", task["dc"], character["modifiers"],
            character["proficient_skills"], character["proficiency_bonus"],
            expertise_skills=character.get("expertise_skills", []),
        )
        success = check["resolution"]["outcome"] == "SUCCESS"
    world["active_task"] = None
    response = target.get("search_result") if success else None
    if not isinstance(response, str) or not response.strip():
        response = "Bu bölgenin incelemesini tamamladın; yeni bir bulgu yok." if success else "İncelemen tamamlandı; aradığını bulamadın."
    result = _result("task", response, advancement, success=success)
    if check is not None:
        result.update(check, action="skill_check",
                      outcome="success" if success else "failure")
    return result


def resolve_input(session, text):
    """Narrow deterministic player-intent grammar before model interpretation."""
    normalized = clock.normalize(text)
    if re.search(r"\b(?:istemiyorum|yapmiyorum|beklemiyorum|gitmiyorum|vazgectim|hayir)\b", normalized):
        return None
    world = session.world_state
    journey = world.get("journey")
    movement = re.search(r"\b(devam|duruyorum|dur|geri don|rota|gidiyorum|gitmek|git|yuruyorum|giriyorum|donuyorum|don)", normalized)
    wait = re.search(r"\b(bekliyorum|bekle|uyuyorum|uyu|dinleniyorum|dinlen)", normalized)
    passive_observation = re.search(r"\b(gozlemliyorum|oturuyorum)\b", normalized)
    task = re.search(r"\b(arastiriyorum|arastir|arastirmaya|inceliyorum|incelemeye|ara)\b", normalized)
    if world.get("active_task") and "devam" in normalized and not journey:
        task = True
    if not (movement or wait or task or passive_observation):
        return None
    if session.ensure_combat_state()["active"]:
        return None
    session.require_player_can_act()
    if journey and journey["status"] != "ARRIVED" and movement:
        if re.search(r"\b(devam|ilerle)", normalized):
            return continue_travel(session)
        if re.search(r"\b(dur|duruyorum)", normalized):
            journey["status"] = "STOPPED"
            return _result("travel", "Yolculuğu durdurdun.", status="stopped")
        if "geri don" in normalized:
            spent = sum(journey["stages"][:journey["stage_index"]]) + journey["stage_spent_seconds"]
            origin = journey["origin"]
            advancement = _advance(session, spent, "travel_return")
            session.commit_location_change(origin)
            journey["status"] = "ARRIVED"
            journey["destination"] = origin
            return _result("travel", "Geldiğin yoldan geri döndün.", advancement)
    if movement and not wait and not task:
        candidates = [loc for loc in world.get("locations", {}) if (
            clock.normalize(loc) in normalized
            or clock.normalize(world["locations"][loc].get("name", loc)) in normalized
        )]
        if len(candidates) == 1:
            return start_travel(session, candidates[0])
        return None
    duration = clock.requested_duration(text)
    if wait or passive_observation:
        if "sabaha kadar" in normalized:
            duration = clock.until_morning(world)
        if duration is None:
            return None  # Existing atmosphere-only wait remains unchanged.
        if "uyu" in normalized and duration >= 8 * 3600:
            rest = session.resolve_species_trait_action("long_rest", elapsed_seconds=duration)
            return _result("rest", rest["message"], rest["effects"]["time_result"])
        if "dinlen" in normalized:
            if duration < 3600:
                return _result("rest", "Kısa dinlenme için en az bir saat gerekir.", status="clarification", success=False)
            kind = "long_rest" if duration >= 8 * 3600 else "short_rest"
            rest = session.resolve_species_trait_action(kind, elapsed_seconds=duration)
            return _result("rest", rest["message"], rest["effects"]["time_result"])
        observation = {"kind": "observe", "location_id": world["location"]} if passive_observation and not (
            journey and journey["status"] != "ARRIVED"
        ) else None
        advancement = _advance(session, duration, "sleep" if "uyu" in normalized else "explicit_wait", observation)
        return _result("wait", "Belirttiğin süre geçti.", advancement)
    if task and (duration is not None or world.get("active_task")):
        if journey and journey["status"] != "ARRIVED":
            return _result("task", "Bu yeri incelemek için önce yolculuğunu tamamlamalı veya geri dönmelisin.",
                           status="unavailable", success=False)
        return resolve_task(session, text, duration)
    return None


def public_journey(world):
    journey = world.get("journey")
    if not journey or journey["status"] == "ARRIVED":
        return None
    return {"destination": journey["destination"], "status": journey["status"],
            "stage": journey["stage_index"] + 1, "stage_count": len(journey["stages"]),
            "encounter": journey["encounter"]["text"] if journey["encounter"] else None}