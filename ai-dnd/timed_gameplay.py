"""Bounded V1 tasks and pedestrian journey stages; no generic quest engine."""

from __future__ import annotations

import re
import math
import copy

import campaign_time as clock
import living_world
from scheduled_events import process_events, pending_events

# Finite local encounters, not monsters, damage, or scheduled world events.
TRAVEL_CATALOG = (
    {"id": "traveler", "text": "Yol ayrımında yön arayan bir yolcuya rastlıyorsun."},
    {"id": "wagon", "text": "Yol kenarında yükünü düzenleyen bir arabacı var."},
    {"id": "crossing", "text": "Dar geçitte karşıdan gelenler yolun açılmasını bekliyor."},
)
DISPOSITIONS = ("sakin", "temkinli", "zorlanıyor")
PACE_MILES_PER_DAY = {"fast": 30, "normal": 24, "slow": 18}
PACE_MILES_PER_HOUR = {"fast": 4, "normal": 3, "slow": 2}
PACE_FEET_PER_MINUTE = {"fast": 400, "normal": 300, "slow": 200}
PACE_ORDER = ("slow", "normal", "fast")


def route_policy(route):
    import local_adventure_catalog as catalog
    return {**catalog.ROUTE_POLICIES.get(route["id"], {}), **route.get("policy", {})}


def effective_pace(world, route, requested, session=None):
    policy = route_policy(route)
    limit = PACE_ORDER.index(policy.get("terrain_max_pace", "fast"))
    if policy.get("good_road", False):
        limit = min(2, limit + 1)
    if session is not None:
        import action_economy
        if action_economy.speed(session, "player") <= session.character.get("speed_ft", 30) / 2:
            limit = 0
    return PACE_ORDER[min(PACE_ORDER.index(requested), limit)]


def stage_metadata(route, durations, returning=False):
    policy = route_policy(route)
    offsets = 0
    result = []
    for index, seconds in enumerate(durations):
        miles = None if returning else route["stage_distances_miles"][index]
        result.append({
            "start": route["origin"] if index == 0 else None,
            "end": route["origin"] if returning else route["destination"] if index == len(durations) - 1 else None,
            "start_mile": None if returning else offsets,
            "end_mile": None if returning else offsets + miles,
            "distance_miles": miles, "duration_seconds": seconds,
            "terrain": policy.get("terrain", "authored_footpath"),
            "weather": policy.get("weather", "unknown"),
            "navigation_risk": policy.get("navigation_risk"),
            "challenge": "navigation" if route["navigation_dc"] is not None else None,
            "interruptions": "existing_scheduled_events_and_travel_catalog",
        })
        offsets += miles or 0
    return result


def pace_effects(world, skill, *, pace=None):
    """Travel-only check modifiers; neither duration nor distance comes from prose."""
    journey = world.get("journey")
    if pace is None:
        if not journey or journey["status"] != "TRAVELLING" or world.get("combat", {}).get("active"):
            return False, False
        pace = journey.get("pace", world.get("flags", {}).get("travel_pace", "normal"))
    return (
        pace == "slow" and skill in {"Perception", "Survival"},
        (pace == "fast" and skill in {"Perception", "Survival", "Stealth"})
        or (pace == "normal" and skill == "Stealth"),
    )


def validate_route(route, origin, destination, locations):
    required = {"id", "origin", "destination", "distance_miles", "duration_seconds",
                "stage_distances_miles", "navigation_dc", "lost_destinations"}
    if not isinstance(route, dict) or not required <= set(route) <= required | {"policy"}:
        raise ValueError("Authored travel route fields are invalid.")
    miles, stages = route["distance_miles"], route["stage_distances_miles"]
    if (not isinstance(route["id"], str) or not 1 <= len(route["id"]) <= 128
            or route["origin"] != origin or route["destination"] != destination
            or origin not in locations or destination not in locations
            or type(miles) not in {int, float} or not math.isfinite(miles) or not 0 < miles <= 864
            or type(route["duration_seconds"]) is not int
            or route["duration_seconds"] != math.ceil(miles * 1200)
            or not isinstance(stages, list) or not 1 <= len(stages) <= 48
            or any(type(s) not in {int, float} or not math.isfinite(s) or not 0 < s <= 18 for s in stages)
            or not math.isclose(sum(stages), miles)
            or route["navigation_dc"] is not None and
               (type(route["navigation_dc"]) is not int or route["navigation_dc"] not in {10, 15, 20, 25, 30})
            or not isinstance(route["lost_destinations"], list)
            or len(route["lost_destinations"]) > 8
            or any(not isinstance(d, str) or d not in locations or d == destination for d in route["lost_destinations"])
            or len(set(route["lost_destinations"])) != len(route["lost_destinations"])):
        raise ValueError("Authored travel route is invalid.")
    policy = route.get("policy", {})
    if (not isinstance(policy, dict) or set(policy) - {"terrain_max_pace", "good_road", "navigation_risk", "terrain", "weather"}
            or policy.get("terrain_max_pace", "fast") not in PACE_ORDER
            or type(policy.get("good_road", False)) is not bool
            or any(not isinstance(policy[k], str) for k in ("navigation_risk", "terrain", "weather") if k in policy)):
        raise ValueError("Authored travel policy is invalid.")
    for alternative in route["lost_destinations"]:
        candidate = locations[origin].get("travel_routes", {}).get(alternative)
        if not isinstance(candidate, dict) or candidate.get("origin") != origin or candidate.get("destination") != alternative:
            raise ValueError("Lost travel must have an explicitly authored alternative route.")


def validate_state(world):
    if not isinstance(world.get("flags", {}), dict):
        raise ValueError("Travel flags are invalid.")
    effort = world.get("travel_effort")
    if effort is not None and (
        not isinstance(effort, dict) or set(effort) != {"day", "walking_seconds", "checks"}
        or type(effort["day"]) is not int or effort["day"] < 0
        or type(effort["walking_seconds"]) is not int or not 0 <= effort["walking_seconds"] <= clock.DAY
        or not isinstance(effort["checks"], list)
        or len(effort["checks"]) != max(0, effort["walking_seconds"] // 3600 - 8)
        or any(not isinstance(c, dict) or c.get("ability") != "constitution"
               or c.get("dc") != 11 + index or c.get("outcome") not in {"SUCCESS", "FAILURE"}
               for index, c in enumerate(effort["checks"]))
    ):
        raise ValueError("Daily travel effort is invalid.")
    tracking = world.get("tracking")
    if tracking is not None and (
        not isinstance(tracking, dict)
        or set(tracking) != {"trail_id", "location_id", "status", "confined", "dc", "spent_seconds", "attempts"}
        or not isinstance(tracking["trail_id"], str) or not tracking["trail_id"]
        or tracking["location_id"] not in world.get("locations", {})
        or tracking["status"] not in {"LOST", "REACQUIRED"}
        or type(tracking["confined"]) is not bool or tracking["dc"] not in {10, 15, 20, 25, 30}
        or type(tracking["spent_seconds"]) is not int
        or not 0 <= tracking["spent_seconds"] < (600 if tracking["confined"] else 3600)
        or type(tracking["attempts"]) is not int or not 0 <= tracking["attempts"] <= 2
    ):
        raise ValueError("Tracking state is invalid.")
    pace = world.get("flags", {}).get("travel_pace", "normal")
    if not isinstance(pace, str) or pace not in PACE_MILES_PER_DAY:
        raise ValueError("Travel pace is invalid.")
    for origin, location in world.get("locations", {}).items():
        for destination, route in location.get("travel_routes", {}).items():
            if isinstance(route, dict):
                validate_route(route, origin, destination, world["locations"])
    blocked = world.get("blocked_travel_routes", {})
    if not isinstance(blocked, dict) or len(blocked) > 256 or any(
        origin not in world.get("locations", {}) or not isinstance(routes, dict)
        or len(routes) > 256 or any(
            destination not in world.get("locations", {}) or type(value) is not bool
            for destination, value in routes.items()
        ) for origin, routes in blocked.items()
    ):
        raise ValueError("Travel obstacles are invalid.")
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
        required = {
            "origin", "destination", "stages", "stage_index", "stage_spent_seconds",
            "stage_checked", "status", "encounter", "recent_patterns"
        }
        if not isinstance(journey, dict) or not required <= set(journey) <= required | {"returning", "pace", "distance_miles", "duration_seconds", "route_id", "pace_rules", "stage_metadata", "navigation_outcome"}:
            raise ValueError("Journey fields are invalid.")
        if journey.get("navigation_outcome", "not_required") not in {"not_required", "verified", "lost"}:
            raise ValueError("Journey navigation outcome is invalid.")
        stages = journey["stages"]
        if not isinstance(stages, list) or not 1 <= len(stages) <= 48 or any(type(s) is not int or not 1 <= s <= clock.DAY for s in stages):
            raise ValueError("Journey stages are invalid.")
        metadata = {"pace", "distance_miles", "duration_seconds", "route_id"}
        if metadata & set(journey):
            if (not metadata <= set(journey) or not isinstance(journey["pace"], str)
                    or journey["pace"] not in PACE_MILES_PER_DAY
                    or type(journey["distance_miles"]) not in {int, float}
                    or not math.isfinite(journey["distance_miles"]) or not 0 <= journey["distance_miles"] <= 864
                    or type(journey["duration_seconds"]) is not int
                    or journey["duration_seconds"] != sum(journey["stages"])
                    or not isinstance(journey["route_id"], str) or not journey["route_id"]):
                raise ValueError("Journey distance and pace are invalid.")
        if type(journey.get("returning", False)) is not bool:
            raise ValueError("Journey return state is invalid.")
        if any(not isinstance(journey[k], str) or journey[k] not in world.get("locations", {}) for k in ("origin", "destination")):
            raise ValueError("Journey location is invalid.")
        index = journey["stage_index"]
        if type(index) is not int or not 0 <= index < len(stages):
            raise ValueError("Journey stage index is invalid.")
        if type(journey["stage_spent_seconds"]) is not int or not 0 <= journey["stage_spent_seconds"] <= stages[index] or type(journey["stage_checked"]) is not bool:
            raise ValueError("Journey progress is invalid.")
        if journey["status"] not in {"TRAVELLING", "INTERRUPTED", "STOPPED", "ARRIVED"}:
            raise ValueError("Journey status is invalid.")
        if metadata <= set(journey):
            candidates = [
                route for route in world["locations"][journey["origin"]].get("travel_routes", {}).values()
                if isinstance(route, dict) and route["id"] == journey["route_id"]
            ]
            if len(candidates) != 1:
                raise ValueError("Journey route identity is invalid.")
            route = candidates[0]
            if "stage_metadata" in journey and (
                not isinstance(journey["stage_metadata"], list)
                or journey["stage_metadata"] != stage_metadata(route, journey["stages"], journey.get("returning", False))
            ):
                raise ValueError("Journey stage metadata is invalid.")
            if journey.get("pace_rules") not in {None, "phb2024"}:
                raise ValueError("Journey pace rules are invalid.")
            expected_stages = [
                math.ceil(miles * 3600 / PACE_MILES_PER_HOUR[journey["pace"]])
                if journey.get("pace_rules") == "phb2024"
                else math.ceil(miles * 28800 / PACE_MILES_PER_DAY[journey["pace"]])
                for miles in route["stage_distances_miles"]]
            if journey.get("returning"):
                if (journey["origin"] != journey["destination"]
                        or not 0 < journey["duration_seconds"] <= sum(expected_stages)
                        or not math.isclose(journey["distance_miles"], route["distance_miles"]
                                            * journey["duration_seconds"] / sum(expected_stages))):
                    raise ValueError("Journey retrace progress is invalid.")
            elif (route["destination"] != journey["destination"] or expected_stages != stages
                  or route["distance_miles"] != journey["distance_miles"]):
                raise ValueError("Journey progress does not match its authored route.")
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
    if reason == "travel_stage":
        return advance_walking(session, seconds, observation)
    before_elapsed = session.world_state["campaign_time"]["elapsed_seconds"]
    result = clock.advance(
        session.world_state, seconds, reason,
        f"turn:{session.world_state.get('flags', {}).get('turn_index', 0)}",
        observation=observation,
    )
    import equipment_economy
    equipment_economy.process_supply_days(session, before_elapsed)
    return result


def advance_walking(session, seconds, observation=None):
    """Split at clock/day/hour boundaries; only elapsed movement counts."""
    import weapon_attack
    from api.core_resolution import resolve_saving_throw
    world = session.world_state
    before = clock.public_time(world)
    elapsed, known, saves, death_results = 0, [], [], []
    interrupted = False
    while elapsed < seconds:
        time = world["campaign_time"]
        absolute = time["start_second"] + time["elapsed_seconds"]
        day = absolute // clock.DAY
        effort = world.get("travel_effort")
        if effort is None or effort["day"] != day:
            effort = world["travel_effort"] = {"day": day, "walking_seconds": 0, "checks": []}
        amount = min(seconds - elapsed, clock.DAY - absolute % clock.DAY,
                     3600 - effort["walking_seconds"] % 3600)
        advance = clock.advance(world, amount, "travel_stage",
                               f"turn:{world.get('flags', {}).get('turn_index', 0)}",
                               observation=observation)
        actual = advance["elapsed_seconds"]
        effort["walking_seconds"] += actual
        elapsed += actual
        known.extend(advance["player_known_events"])
        hour = effort["walking_seconds"] // 3600
        if hour > 8 and len(effort["checks"]) < hour - 8:
            player = session.character
            check = resolve_saving_throw(
                roll_fn=lambda: session.rng.randint(1, 20), ability="constitution",
                dc=10 + hour - 8,
                ability_modifier=weapon_attack.saving_bonus(player, "constitution")[0],
                circumstantial_modifier=weapon_attack.saving_bonus(player, "constitution")[1])
            effort["checks"].append(check)
            saves.append(check)
            if check["outcome"] != "SUCCESS":
                fatal = weapon_attack.exhaustion(player) == 5
                deaths = []
                weapon_attack.add_exhaustion(session, "extended_travel", deaths=deaths)
                if fatal:
                    interrupted = True
                    death_results.extend(deaths)
        if absolute % clock.DAY + actual == clock.DAY:
            import equipment_economy
            supply_result = equipment_economy.consume_daily_supplies(session, day=day + 1)
            if supply_result.get("condition_death"):
                interrupted = True
                death_results.extend(supply_result["death_results"])
        interrupted = bool(interrupted or advance.get("interrupted") or weapon_attack.exhaustion(session.character) >= 6)
        if interrupted or not actual:
            break
    return {"before": before, "after": clock.public_time(world),
            "requested_seconds": seconds, "elapsed_seconds": elapsed,
            "player_known_events": known, "interrupted": interrupted,
            "extended_travel_saves": saves, "death_results": death_results}


def reacquire_tracking(session):
    """An already-known authored trail, not navigation to a destination."""
    world = session.world_state
    trail = world.get("tracking")
    if not trail or trail["location_id"] != world["location"]:
        return _result("tracking", "Burada takip ettiğin bilinen bir iz yok.", success=False)
    if trail["status"] == "REACQUIRED" or trail["attempts"] >= 2:
        return _result("tracking", "Bu izin mevcut takip denemesi tamamlandı.")
    required = 600 if trail["confined"] else 3600
    advance = _advance(session, required - trail["spent_seconds"], "tracking")
    trail["spent_seconds"] += advance["elapsed_seconds"]
    if trail["spent_seconds"] < required:
        return _result("tracking", "İzi yeniden araman kesildi; kalan inceleme sürdürülebilir.", advance)
    player = session.character
    check = session.perform_skill_check(
        "Survival", trail["dc"], player["modifiers"], player["proficient_skills"],
        player["proficiency_bonus"], expertise_skills=player.get("expertise_skills", []))
    trail["attempts"] += 1
    trail["spent_seconds"] = 0
    if check["resolution"]["outcome"] == "SUCCESS":
        trail["status"] = "REACQUIRED"
    return _result("skill_check", "İzi yeniden buldun." if trail["status"] == "REACQUIRED"
                   else "İzi henüz bulamadın.", advance,
                   outcome="success" if check["resolution"]["outcome"] == "SUCCESS" else "failure",
                   **check)


def _result(action, text, advancement=None, **extra):
    result = {"action": action, "status": "completed", "success": True,
              "state_changes": ["campaign_time"] if advancement else [],
              "direct_response": text, **extra}
    if advancement is not None:
        result["time_result"] = advancement
        if advancement.get("interrupted"):
            result["status"] = "interrupted"
        known = advancement["player_known_events"]
        if known:
            result["direct_response"] += " " + " ".join(e["summary"] for e in known)
    return result


def _venue_entry_door(world, origin, destination):
    import game
    return game._venue_entry_door(world, origin, destination)


def _blocked_venue_result(door):
    return _result(
        "travel",
        f"{door.get('name', 'Kapı')} kapalı. İçeri geçemezsin.",
        status="blocked",
        success=False,
    )


def route_stages(world, destination, pace=None, session=None):
    origin = world.get("location")
    if destination == origin:
        return []
    if _venue_entry_door(world, origin, destination):
        return None
    import exploration
    if not exploration.route_allowed(world, origin, destination):
        return None
    if world.get("blocked_travel_routes", {}).get(origin, {}).get(destination, False):
        return None
    location = world.get("locations", {}).get(origin, {})
    route = location.get("travel_routes", {}).get(destination)
    if route is not None:
        if isinstance(route, dict):
            validate_route(route, origin, destination, world["locations"])
            pace = pace or world.get("flags", {}).get("travel_pace", "normal")
            if pace not in PACE_MILES_PER_DAY:
                raise ValueError("Travel pace is invalid.")
            pace = effective_pace(world, route, pace, session)
            return [math.ceil(miles * 3600 / PACE_MILES_PER_HOUR[pace])
                    for miles in route["stage_distances_miles"]]
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
    import exploration
    if exploration.active(world):
        exploration._busy(session, journey=True, movement=True)
    if session.ensure_combat_state()["active"]:
        return _result("travel", "Çatışma sırasında bu yolculuğa başlayamazsın.", status="unsupported", success=False)
    venue_door = _venue_entry_door(world, world.get("location"), destination)
    if venue_door:
        return _blocked_venue_result(venue_door)
    stages = route_stages(world, destination, session=session)
    if stages is None:
        if world.get("blocked_travel_routes", {}).get(world.get("location"), {}).get(destination, False):
            return _result("travel", "Bu yol fiziksel olarak kapalı; başka bir kayıtlı rota seçebilirsin.", status="blocked", success=False)
        return _result("travel", "Bu yolun süresi henüz belirlenmiş değil; yolculuk başlamadı.", status="unverified", success=False)
    if not stages:
        journey = world.get("journey")
        if journey and journey["status"] != "ARRIVED":
            return return_travel(session)
        return _result("travel", "Zaten buradasın.")
    previous = world.get("journey")
    navigation = None
    lost = False
    retraced = 0
    start_time = clock.public_time(world)
    return_events = []
    return_requested = 0
    if previous and previous["status"] != "ARRIVED":
        # Rerouting uses the known anchor, never a shortcut from a midpoint.
        returning = return_travel(session)
        if world["journey"]["status"] != "ARRIVED":
            return returning
        back = returning.get("time_result", {})
        retraced = back.get("elapsed_seconds", 0)
        return_events = back.get("player_known_events", [])
        return_requested = back.get("requested_seconds", 0)
    route = world["locations"].get(world.get("location"), {}).get("travel_routes", {}).get(destination)
    chosen_pace = (effective_pace(world, route, world.get("flags", {}).get("travel_pace", "normal"), session)
                   if isinstance(route, dict) else None)
    # Roll only for an authored challenge, once at departure. Existing journeys
    # retain their chosen destination/check through interruptions and reopening.
    if isinstance(route, dict) and route["navigation_dc"] is not None:
        alternatives = [
            alternative for alternative in route["lost_destinations"]
            if route_stages(world, alternative) is not None
        ]
        character = session.character
        advantage, disadvantage = pace_effects(
            world, "Survival", pace=chosen_pace)
        navigation = session.perform_skill_check(
            "Survival", route["navigation_dc"], character["modifiers"],
            character["proficient_skills"], character["proficiency_bonus"],
            advantage=advantage, disadvantage=disadvantage,
            expertise_skills=character.get("expertise_skills", ()),
        )
        if navigation["resolution"]["outcome"] != "SUCCESS":
            if not alternatives:
                return _result(
                    "skill_check", "Yönünü doğrulayamadın; bilinmeyen bir yola sapmadın.",
                    success=False, outcome="failure", **navigation)
            destination = session.rng.choice(alternatives)
            stages = route_stages(world, destination, pace=chosen_pace, session=session)
            lost = True
    recent = world.get("journey", {}).get("recent_patterns", []) if isinstance(world.get("journey"), dict) else []
    world["journey"] = {
        "origin": world["location"], "destination": destination, "stages": stages,
        "stage_index": 0, "stage_spent_seconds": 0, "stage_checked": False,
        "status": "TRAVELLING", "encounter": None, "recent_patterns": list(recent),
        "navigation_outcome": "lost" if lost else "verified" if navigation is not None else "not_required",
    }
    route = world["locations"][world["location"]].get("travel_routes", {}).get(destination)
    if isinstance(route, dict):
        chosen_pace = effective_pace(world, route, chosen_pace, session)
        world["journey"].update(
            pace=chosen_pace,
            distance_miles=route["distance_miles"], duration_seconds=sum(stages), route_id=route["id"],
            pace_rules="phb2024",
            stage_metadata=stage_metadata(route, stages),
        )
    world["active_task"] = None
    result = continue_travel(session)
    if retraced:
        result["time_result"]["elapsed_seconds"] += retraced
        result["time_result"]["requested_seconds"] += return_requested
        result["time_result"]["player_known_events"] = return_events + result["time_result"]["player_known_events"]
        result["time_result"]["before"] = start_time
        result["direct_response"] = "Bildiğin yol ayrımına geri dönüp yeni yolu seçtin. " + result["direct_response"]
    if navigation is not None:
        result.update(navigation, action="skill_check",
                      outcome="failure" if lost else "success", success=not lost)
        if lost:
            result["direct_response"] = "Yönünü karıştırdın; sisli yol ayrımına uzanan patikaya saptın. " + result["direct_response"]
    return result


def return_travel(session):
    """Retrace the actual path, retaining remaining distance if the return is stopped."""
    world = session.world_state
    previous = world["journey"]
    if previous.get("returning"):
        return continue_travel(session)
    spent = sum(previous["stages"][:previous["stage_index"]]) + previous["stage_spent_seconds"]
    origin = previous["origin"]
    if spent == 0:
        previous["status"] = "ARRIVED"
        previous["destination"] = origin
        for key in ("pace", "distance_miles", "duration_seconds", "route_id", "pace_rules"):
            previous.pop(key, None)
        return _result("travel", "Başlangıç noktasındasın.")
    world["journey"] = {
        "origin": origin, "destination": origin,
        "stages": [min(clock.DAY, spent - offset) for offset in range(0, spent, clock.DAY)], "stage_index": 0,
        "stage_spent_seconds": 0, "stage_checked": True, "status": "TRAVELLING",
        "encounter": None, "recent_patterns": list(previous["recent_patterns"]),
        "returning": True,
    }
    if "distance_miles" in previous:
        world["journey"].update(
            pace=previous["pace"], route_id=previous["route_id"],
            distance_miles=previous["distance_miles"] * spent / previous["duration_seconds"],
            duration_seconds=spent,
        )
        if "pace_rules" in previous:
            world["journey"]["pace_rules"] = previous["pace_rules"]
        if "stage_metadata" in previous:
            route = next(r for r in world["locations"][origin]["travel_routes"].values()
                         if isinstance(r, dict) and r["id"] == previous["route_id"])
            world["journey"]["stage_metadata"] = stage_metadata(route, world["journey"]["stages"], True)
    return continue_travel(session)


def continue_travel(session):
    world = session.world_state
    import exploration
    if exploration.active(world):
        exploration._busy(session, journey=True, movement=True)
    journey = world["journey"]
    venue_door = _venue_entry_door(
        world, journey.get("origin"), journey.get("destination")
    )
    if venue_door:
        return _blocked_venue_result(venue_door)
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
        elapsed = advance["elapsed_seconds"]
        journey["stage_spent_seconds"] += elapsed
        if advance.get("interrupted"):
            journey["status"] = "INTERRUPTED"
            return _result("travel", "Yolculukta karar vermen gereken bir durum oluştu.", advance)
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
    journey["stage_spent_seconds"] += advance["elapsed_seconds"] - elapsed
    if advance.get("interrupted"):
        journey["status"] = "INTERRUPTED"
        return _result("travel", "Yolculukta karar vermen gereken bir durum oluştu.", advance)
    if journey["stage_index"] + 1 < len(journey["stages"]):
        journey["stage_index"] += 1
        journey["stage_spent_seconds"] = 0
        journey["stage_checked"] = bool(journey.get("returning"))
        return _result("travel", "Yolun bu kısmını tamamladın. Devam etmek veya durmak sana kalmış.", advance, status="stage_completed", travel_dice=dice)
    destination = journey["destination"]
    venue_door = _venue_entry_door(world, journey.get("origin"), destination)
    if venue_door:
        journey["status"] = "INTERRUPTED"
        return _blocked_venue_result(venue_door)
    if not session.commit_location_change(destination):
        venue_door = _venue_entry_door(world, journey.get("origin"), destination)
        if venue_door:
            journey["status"] = "INTERRUPTED"
            return _blocked_venue_result(venue_door)
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
    active = world.get("active_task")
    if active and not features and "devam" in clock.normalize(text):
        target = next((f for f in world.get("features", []) if f.get("id") == active["target_id"]), target)
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
    task["spent_seconds"] += advancement["elapsed_seconds"]
    if task["spent_seconds"] < task["required_seconds"]:
        return _result("task", "İncelemen henüz tamamlanmadı; araştırmaya devam edebilirsin.",
                       advancement, status="in_progress")
    check = None
    success = True
    import exploration
    policy = exploration.search_policy(world, location, target_id)
    if task["dc"] is not None:
        character = session.character
        if policy and policy["automatic"]:
            success = True
        else:
            check = session.perform_skill_check(
            policy["skill"] if policy else "Investigation", task["dc"], character["modifiers"],
            character["proficient_skills"], character["proficiency_bonus"],
            expertise_skills=character.get("expertise_skills", []),
        )
            success = check["resolution"]["outcome"] == "SUCCESS"
    world["active_task"] = None
    response = target.get("search_result") if success else None
    if not isinstance(response, str) or not response.strip():
        response = "Bu bölgenin incelemesini tamamladın; yeni bir bulgu yok." if success else "İncelemen tamamlandı; aradığını bulamadın."
    result = _result("task", response, advancement, success=success)
    discoveries = exploration.finish_search(world, location, success, target_id)
    if discoveries:
        result["direct_response"] = " ".join(discoveries)
    if check is not None:
        result.update(check, action="skill_check",
                      outcome="success" if success else "failure")
    return result


def resolve_pending(session, normalized):
    """Player chooses; events only identify reality and a canonical combat target."""
    world = session.world_state
    if world.get("player_combat_status") == "unconscious":
        return None
    pending = [e for e in pending_events(world) if e.get("decision_status") == "PENDING"]
    if not pending:
        return None
    selected = [e for e in pending if clock.normalize(e["player_known_summary"]) in normalized]
    event = sorted(selected or pending, key=lambda e: (-e.get("priority", 0), e["event_id"]))[0]
    if "kararim:" in normalized:
        normalized = normalized.split("kararim:", 1)[1]
    session.require_player_can_act()
    if re.search(r"\b(?:istemiyorum|yapmiyorum|gitmiyorum|hayir)\b", normalized):
        return _result("event_decision", "İstemediğin eylem uygulanmadı; karşılaşma için kararın hâlâ bekleniyor.",
                       status="pending_decision", success=False)
    if re.search(r"\b(savas|saldir|dovus)", normalized) and event.get("combat_npc_id"):
        target = next(n for n in world["npcs"] if n["id"] == event["combat_npc_id"])
        if target.get("location") != world.get("location") or target.get("current_hp", 1) <= 0 or target.get("combat_status", "active") != "active":
            return _result("event_decision", "Bu rakip şu anda çatışma için uygun değil; başka bir karar verebilirsin.",
                           status="pending_decision", success=False)
        started = session.start_combat(target)
        event["decision_status"] = "IN_COMBAT"
        return _result("attack", "Çatışmayı seçtin; sıra ve sonuçları çatışma sistemi belirleyecek.", **started)
    returning = "geri don" in normalized
    rerouting = "rota" in normalized or "gidiyorum" in normalized
    continuing = bool(re.search(r"\b(devam|ilerle)", normalized))
    interacting = bool(re.search(r"\b(konus|dinle|etkiles)", normalized))
    stopped = bool(re.search(r"\b(dur|bekle|redded)", normalized))
    if event["behavior"] == "FORCED" and (continuing or interacting or stopped):
        return _result("event_decision", "Bu fiziksel engeli yok sayarak devam edemezsin; geri dönebilir veya doğrulanmış başka bir rota seçebilirsin.",
                       status="pending_decision", success=False)
    if returning or rerouting:
        journey = world.get("journey")
        if returning and (not journey or journey["status"] == "ARRIVED"):
            return _result("event_decision", "Başka bir kayıtlı konuma geçmek için hedefini belirt.",
                           status="pending_decision", success=False)
        # Validate the selected alternative before releasing the encounter.
        if rerouting and not returning:
            candidates = [loc for loc, record in world["locations"].items() if
                          clock.normalize(loc) in normalized or clock.normalize(record.get("name", loc)) in normalized]
            if len(candidates) != 1 or route_stages(world, candidates[0]) is None:
                return _result("event_decision", "Doğrulanmış başka bir rota belirt.", status="pending_decision", success=False)
        event["decision_status"] = "RESOLVED"
        event["player_decision"] = "return" if returning else "reroute"
        return None  # The same explicit player intent takes the existing travel path.
    if continuing or interacting or stopped:
        event["decision_status"] = "RESOLVED"
        event["player_decision"] = "continue" if continuing else "interact" if interacting else "stop"
        return _result("event_decision", "Kararın kaydedildi. Sonraki eylemini sen seçebilirsin.")
    return _result("event_decision", "Bu karşılaşma için kararın bekleniyor. Nasıl ilerlemek istediğini belirt.",
                   status="pending_decision", success=False)


def resolve_input(session, text):
    """Narrow deterministic player-intent grammar before model interpretation."""
    normalized = clock.normalize(text)
    world = session.world_state
    if not session.ensure_combat_state()["active"]:
        decision = resolve_pending(session, normalized)
        if decision is not None:
            return decision
    if "kararim:" in normalized:
        normalized = normalized.split("kararim:", 1)[1]
    if re.search(r"\b(?:istemiyorum|yapmiyorum|beklemiyorum|gitmiyorum|vazgectim|hayir)\b", normalized):
        return None
    journey = world.get("journey")
    movement = re.search(r"\b(devam|duruyorum|dur|geri don|rota|gidiyorum|gitmek|git|yuruyorum|giriyorum|donuyorum|don)", normalized)
    wait = re.search(r"\b(bekliyorum|bekle|uyuyorum|uyu|dinleniyorum|dinlen|kaliyorum)", normalized)
    passive_observation = re.search(r"\b(gozlemliyorum|oturuyorum)\b", normalized)
    task = re.search(r"\b(arastiriyorum|arastir|arastirmaya|inceliyorum|incelemeye|ara)\b", normalized)
    if world.get("active_task") and "devam" in normalized and (not journey or journey["status"] == "ARRIVED"):
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
            return return_travel(session)
    if re.fullmatch(r"geri don(?:uyorum|uyoruz|dum|duk)?[.! ]*", normalized):
        # A bare return may use an explicitly pending destination, but never
        # a model-invented target or an inferred reverse cross-region route.
        destination = world.get("flags", {}).get("pending_destination")
        if destination in world.get("locations", {}):
            return start_travel(session, destination)
        return _result("travel", "Hangi konuma geri dönmek istediğini belirt.",
                       status="clarification", success=False)
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
    result = {"destination": journey["destination"], "status": journey["status"],
            "stage": journey["stage_index"] + 1, "stage_count": len(journey["stages"]),
            "encounter": journey["encounter"]["text"] if journey["encounter"] else None}
    if "distance_miles" in journey:
        spent = sum(journey["stages"][:journey["stage_index"]]) + journey["stage_spent_seconds"]
        result.update(origin=journey["origin"], pace=journey["pace"],
                      distance_miles=journey["distance_miles"], duration_seconds=journey["duration_seconds"],
                      remaining_seconds=journey["duration_seconds"] - spent)
    metadata = journey.get("stage_metadata", [])
    if metadata:
        import exploration
        known = exploration.known_locations(world)
        stage = metadata[journey["stage_index"]]
        result["current_stage"] = {
            "start": stage["start"] if stage["start"] in known else None,
            "end": stage["end"] if stage["end"] in known else None,
            "terrain": stage["terrain"], "weather": stage["weather"],
            "distance_miles": stage["distance_miles"],
            "duration_seconds": stage["duration_seconds"],
            "spent_seconds": journey["stage_spent_seconds"],
            "challenge": "encounter" if journey["encounter"] else
                         "navigation_" + journey["navigation_outcome"]
                         if journey.get("navigation_outcome", "not_required") != "not_required" else None,
        }
    return result


def public_expedition(session, *, snapshot=None):
    world = snapshot["world_state"] if snapshot is not None else session.world_state
    character = session.character if hasattr(session, "character") else snapshot["player"]
    from types import SimpleNamespace
    condition_context = SimpleNamespace(world_state=world)
    import weapon_attack
    effort = world.get("travel_effort", {})
    time = world.get("campaign_time")
    if time and effort.get("day") != (time["start_second"] + time["elapsed_seconds"]) // clock.DAY:
        effort = {}
    tracking = world.get("tracking") or {}
    actions = []
    capable = not world.get("combat", {}).get("active") and not weapon_attack.conditions(
        condition_context, "player", character) & {"dead", "unconscious", "incapacitated"}
    journey = world.get("journey") or {}
    ongoing = journey.get("status", "ARRIVED") != "ARRIVED"
    enabled = world.get("supplies_policy", {}).get("enabled", False)
    if capable and not ongoing and not world.get("active_task"):
        actions.append({"label": "Erzak takibi: " + ("kapat" if enabled else "aç"),
                        "message": "/travel supplies " + ("disabled" if enabled else "enabled")})
        if enabled:
            actions.append({"label": "Bilinen kaynaklardan erzak ara", "message": "/travel forage"})
        for feature in world.get("features", []):
            if (feature.get("location") == world["location"] and not feature.get("hidden", False)
                    and isinstance(feature.get("trail_policy"), dict)):
                actions.append({"label": feature.get("name", "Bilinen izi takip et"),
                                "message": "/travel track " + feature["id"]})
        if (tracking.get("location_id") == world["location"]
                and tracking.get("status") == "LOST" and tracking.get("attempts", 0) < 2):
            actions.append({"label": "İzi yeniden aramayı sürdür", "message": "/travel reacquire"})
        import exploration
        for gate in exploration.visible_doors(world):
            # Legacy doors may have no addressable identity. Keep their saved
            # facts, but never fabricate an unlock command (or a new identity).
            if not isinstance(gate.get("id"), str) or not gate["id"].strip():
                continue
            if gate.get("location") == world["location"] and not gate.get("hidden", False):
                if gate.get("locked"):
                    actions.append({"label": gate["name"] + " · kilidi aç",
                                    "message": "/explore door " + gate["id"] + " unlock"})
    local_tracking = tracking if tracking.get("location_id") == world["location"] else {}
    return {"walking_seconds": effort.get("walking_seconds", 0),
            "hours_beyond_eight": len(effort.get("checks", [])),
             "extended_travel_saves": [
                 {key: copy.deepcopy(check[key]) for key in (
                     "dc", "raw_rolls", "selected_roll", "total", "total_modifier",
                     "modifier_breakdown", "outcome")}
                 for check in effort.get("checks", [])
             ],
            "exhaustion": weapon_attack.exhaustion(character),
            "supplies_enabled": enabled,
            "tracking_status": local_tracking.get("status"),
            "tracking_seconds": local_tracking.get("spent_seconds", 0),
            "tracking_required_seconds": 600 if local_tracking.get("confined") else 3600,
            "actions": actions}