"""Package 3 orchestration. Position/time/checks/damage/saves retain their owners."""
import copy
import re

import local_adventure_catalog as catalog
import timed_gameplay
from combat_lifecycle import CombatRequestError

TRAP_STATES = frozenset({"hidden", "detected", "disarmed", "bypassed", "triggered", "neutralized"})
KNOWLEDGE_FIELDS = {"known_locations", "search_attempts", "inferences", "investigation_attempts"}


def fail(code, message):
    raise CombatRequestError(code, message, 400)


def validate_state(world):
    state = world.get(catalog.KEY)
    if state is None:
        return
    if (not isinstance(state, dict) or not set(catalog.initial_state("")) <= set(state)
            or set(state) - set(catalog.initial_state("")) - KNOWLEDGE_FIELDS
            or state["catalog_id"] != catalog.CATALOG_ID
            or not isinstance(state["origin"], str) or state["origin"] not in world["locations"]
            or state["origin"] in catalog.LOCATIONS):
        raise ValueError("Local adventure binding is invalid.")
    known = state.get("known_locations", [])
    attempts = state.get("search_attempts", {})
    if (not isinstance(known, list) or any(not isinstance(v, str) or v not in world["locations"] for v in known)
            or len(set(known)) != len(known)
            or not isinstance(attempts, dict)
            or any(k not in catalog.ROOM_IDS or type(v) is not int or not 0 <= v <= 2 for k, v in attempts.items())):
        raise ValueError("Local adventure player knowledge is invalid.")
    inferences = state.get("inferences", [])
    reasoning = state.get("investigation_attempts", {})
    if (not isinstance(state["discoveries"], list)
            or not isinstance(inferences, list)
            or any(not isinstance(v, str) or v not in state["discoveries"] for v in inferences)
            or len(set(inferences)) != len(inferences)
            or not isinstance(reasoning, dict) or any(k not in state["discoveries"]
                or type(v) is not int or not 0 <= v <= 2 for k, v in reasoning.items())):
        raise ValueError("Local adventure clue reasoning is invalid.")
    for field, identities in (("discoveries", catalog.DISCOVERIES), ("interactions", catalog.INTERACTIONS)):
        values = state[field]
        if (not isinstance(values, list) or any(not isinstance(v, str) or v not in identities for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("Local adventure knowledge is invalid.")
    for field, identities, statuses in (
        ("trap_states", catalog.TRAPS, TRAP_STATES),
        ("hazard_states", catalog.HAZARDS, {"active", "neutralized"}),
    ):
        values = state[field]
        if not isinstance(values, dict) or set(values) != set(identities) or any(
            not isinstance(v, str) or v not in statuses for v in values.values()
        ):
            raise ValueError("Local adventure lifecycle is invalid.")
    if any(state["trap_states"][identity] != "hidden" and identity not in state["discoveries"]
           for identity in catalog.TRAPS):
        raise ValueError("A resolved trap must have been discovered.")
    expected_locations = catalog.locations(state["origin"])
    if any(world["locations"].get(k) != value for k, value in expected_locations.items()):
        raise ValueError("Authored locations or routes were altered.")
    if world["locations"][state["origin"]].get("travel_routes", {}).get(catalog.CAMP) != catalog.approach(state["origin"]):
        raise ValueError("Authored approach route was altered.")
    for identity, definition in catalog.DOORS.items():
        doors = [d for d in world.get("doors", []) if d.get("id") == identity]
        if len(doors) != 1:
            raise ValueError("Authored door identity is invalid.")
        door = doors[0]
        if (set(door) != {"id", "name", "location", "description", "locked", "open", "broken"}
                or any(door.get(k) != definition[k] for k in ("name", "location", "description"))
                or any(type(door.get(k)) is not bool for k in ("locked", "open", "broken"))
                or door["locked"] and (door["open"] or door["broken"])
                or door["broken"] and not door["open"]):
            raise ValueError("Authored door state is invalid.")


def active(world):
    return world.get(catalog.KEY) is not None


def known_locations(world):
    """Player knowledge, never the set of registered world possibilities."""
    if not active(world):
        return set(world.get("locations", {}))
    state = world[catalog.KEY]
    known = set(state.get("known_locations", ()))
    known.update({state["origin"], catalog.CAMP, world["location"]})
    # An ordinary path can be known without claiming that its destination was visited.
    if world["location"] == catalog.CAMP:
        known.add(catalog.ENTRY)
    journey = world.get("journey") or {}
    if journey.get("destination") in catalog.LOCATIONS:
        known.add(journey["destination"])
    for exit in catalog.EXITS.values():
        if exit["from"] == world["location"] and visible_exit(world, exit) and not exit_obstacle(world, exit):
            known.add(exit["to"])
    return (set(world["locations"]) - set(catalog.LOCATIONS)) | known


def record_knowledge(world):
    if active(world):
        world[catalog.KEY]["known_locations"] = sorted(known_locations(world) & (set(catalog.LOCATIONS) | {world[catalog.KEY]["origin"]}))


def player_entities(world, entities):
    """Filter local-content references at the server boundary, not in React."""
    known = known_locations(world)
    return [e for e in (entities or []) if not e.get("hidden", False) and (
            e.get("location", e.get("location_id")) not in catalog.LOCATIONS
            or e.get("location", e.get("location_id")) == world["location"]
            and e.get("location", e.get("location_id")) in known
            )]


def door(world, identity):
    return next((d for d in world["doors"] if d.get("id") == identity), None)


def visible_exit(world, definition):
    return not definition.get("discovery_id") or definition["discovery_id"] in world[catalog.KEY]["discoveries"]


def exit_obstacle(world, definition):
    if not visible_exit(world, definition):
        return "secret"
    if definition.get("hazard_id") and world[catalog.KEY]["hazard_states"][definition["hazard_id"]] == "active":
        return "blocked"
    gate = door(world, definition.get("door_id"))
    if gate and not gate["open"]:
        return "locked" if gate["locked"] else "closed"
    return None


def route_allowed(world, origin, destination):
    """Fail closed before clock/RNG changes, including ordinary intent routes."""
    if not active(world) or not ({origin, destination} & set(catalog.LOCATIONS)):
        return True
    return isinstance(world["locations"].get(origin, {}).get("travel_routes", {}).get(destination), dict)


def require_transition(world, destination):
    current = world.get("location")
    if not active(world) or not ({current, destination} & set(catalog.LOCATIONS)) or current == destination:
        return
    validate_state(world)
    exits = [e for e in catalog.EXITS.values() if e["from"] == current and e["to"] == destination]
    for exit in exits:
        if exit_obstacle(world, exit):
            continue
        trap = exit.get("trap_id")
        if trap and world[catalog.KEY]["trap_states"][trap] in {"hidden", "detected"}:
            continue
        return
    journey = world.get("journey")
    if (route_allowed(world, current, destination) and journey
            and journey["destination"] == destination
            and journey["stage_index"] == len(journey["stages"]) - 1
            and journey["stage_spent_seconds"] == journey["stages"][-1]):
        return
    fail("authored_transition_forbidden", "Bu konuma açık bir geçit veya tamamlanmış bir yolculukla ulaşabilirsin.")


def complete_search(world, location, success, target_id=None):
    if not active(world) or not success or target_id not in {None, location}:
        return []
    state = world[catalog.KEY]
    found = []
    for identity, definition in catalog.DISCOVERIES.items():
        if definition["location"] == location and identity not in state["discoveries"]:
            state["discoveries"].append(identity)
            if identity in catalog.TRAPS:
                state["trap_states"][identity] = "detected"
            found.append(definition["text"])
            if identity == "stone_marker" and "stone_secret" not in state["discoveries"]:
                state["discoveries"].append("stone_secret")
    return found


def search_policy(world, location, target_id):
    if not active(world) or location not in catalog.ROOM_IDS or target_id != location:
        return None
    attempts = world[catalog.KEY].get("search_attempts", {}).get(location, 0)
    return {**catalog.SEARCH_POLICIES[location], "automatic": attempts >= 1}


def finish_search(world, location, success, target_id):
    if active(world) and location in catalog.ROOM_IDS and target_id == location:
        attempts = world[catalog.KEY].setdefault("search_attempts", {})
        attempts[location] = min(2, attempts.get(location, 0) + 1)
    return complete_search(world, location, success, target_id)


def notice_passively(session):
    """PHB passive notice; no roll, no remote search, and no state in GETs."""
    world = session.world_state
    if not active(world) or world["location"] not in catalog.ROOM_IDS:
        return []
    import weapon_attack
    if "blinded" in weapon_attack.conditions(session, "player", session.character):
        return []
    player = session.character
    bonus = player["modifiers"]["wisdom"]
    if "Perception" in player["proficient_skills"]:
        bonus += player["proficiency_bonus"] * (2 if "Perception" in player.get("expertise_skills", ()) else 1)
    bonus -= 2 * weapon_attack.exhaustion(player)
    if catalog.LOCATIONS[world["location"]].get("visibility") == "lightly_obscured":
        bonus -= 5
    return complete_search(world, world["location"], 10 + bonus >= catalog.SEARCH_POLICIES[world["location"]]["dc"], world["location"])


def apply_environment(world):
    if active(world) and world.get("location") in catalog.LOCATIONS:
        context = world.get("scene_state", {}).get("ambient_context")
        if isinstance(context, dict):
            context["weather"] = catalog.LOCATIONS[world["location"]]["weather"]


def _busy(session, *, journey=False, task=False, pending=False, movement=False):
    world = session.world_state
    session.require_player_can_act()
    import weapon_attack
    conditions = weapon_attack.conditions(session, "player", session.character)
    if conditions & {
        "incapacitated", "unconscious", "dead", "paralyzed", "stunned", "petrified",
    }:
        fail("exploration_incapacitated", "Şu an bu eylemi yapabilecek durumda değilsin.")
    if movement and conditions & {"grappled", "restrained"}:
        fail("exploration_movement_blocked", "Hareketini engelleyen durum çözülmeden yola çıkamazsın.")
    if world.get("combat", {}).get("active"):
        fail("exploration_combat_active", "Çatışmayı tamamlamadan bu eylemi yapamazsın.")
    if not journey and (world.get("journey") or {}).get("status", "ARRIVED") != "ARRIVED":
        fail("exploration_journey_active", "Önce yolculuğunu tamamla veya başlangıca geri dön.")
    if not task and world.get("active_task"):
        fail("exploration_task_active", "Önce sürdürdüğün araştırmayı tamamla.")
    if not pending and any(e.get("decision_status") in {"PENDING", "IN_COMBAT"} for e in world.get("scheduled_events", [])):
        fail("exploration_decision_pending", "Önce karşılaşma için kararını ver.")


def _reply(session, message, text, action, **result):
    from authored_dungeon import _reply as owned_reply
    response = owned_reply(session, message, text, action)
    response["action_result"].update(result)
    if (getattr(session, "_exploration_narration_available", False)
            and action in {"dungeon_traverse", "environment_interaction"}
            and not (result.get("time_result") or {}).get("interrupted")):
        import game
        packet = game.ask_dungeon_master(
            session.messages, message, return_details=True, narration_only=True,
            action_result={"action": "exploration_resolved", "direct_response": text,
                           "weather": catalog.LOCATIONS.get(session.world_state["location"], {}).get("weather", "unknown")})
        if packet.get("valid_response"):
            response["narration"] = packet["narration"]
            if session.messages and session.messages[-1].get("role") == "assistant":
                session.messages[-1]["content"] = packet["narration"]
    return response


def _timed_reply(session, message, result):
    return _reply(session, message, result.get("direct_response", "Eylemin tamamlandı."),
                  result.get("action", "exploration"), **{k: v for k, v in result.items() if k != "action"})


def _check(session, skill, dc, *, disadvantage=False, tool=None):
    player = session.character
    proficient = list(player["proficient_skills"])
    tool_proficient = tool in player.get("proficient_tools", []) if tool else False
    both = tool_proficient and skill in proficient
    if tool_proficient and skill not in proficient:
        proficient.append(skill)
    check = session.perform_skill_check(
        skill, dc, player["modifiers"], proficient,
        player["proficiency_bonus"], expertise_skills=player.get("expertise_skills", ()),
        disadvantage=disadvantage, advantage=both,
    )
    return dict(check, tool=tool, action="skill_check", outcome="success" if check["resolution"]["outcome"] == "SUCCESS" else "failure",
                success=check["resolution"]["outcome"] == "SUCCESS")


def _time(session, seconds):
    return session.advance_campaign_time(seconds, "exploration")


def _damage(session, definition):
    import weapon_attack
    mitigation = weapon_attack.mitigate(session, "player", definition["damage_type"], definition["damage"])
    # Includes temporary HP, species endurance, massive damage and death policy.
    return session._apply_attack_damage_to_player(mitigation["final_damage"], False, True)


def _trigger(session, identity):
    state = session.world_state[catalog.KEY]
    if state["trap_states"][identity] not in {"hidden", "detected"}:
        return None
    if identity not in state["discoveries"]:
        state["discoveries"].append(identity)
    state["trap_states"][identity] = "triggered"
    return _damage(session, catalog.TRAPS[identity])


def _begin(session, message):
    world = session.world_state
    _busy(session)
    if active(world):
        return _reply(session, message, "Taş patikanın macerası zaten yol haritanda.", "exploration_known")
    origin = world.get("location")
    if origin not in world["locations"] or origin in catalog.LOCATIONS:
        fail("adventure_origin_invalid", "Önce bulunduğun yeri belirlemelisin.")
    if origin in __import__("authored_dungeon").ROOMS:
        fail("adventure_origin_busy", "Yeni patikayı aramadan önce bu zindandan çık.")
    if set(catalog.LOCATIONS) & set(world["locations"]) or any(d.get("id") in catalog.DOORS for d in world["doors"]):
        fail("adventure_identity_collision", "Bu maceranın kayıtları mevcut sahneyle çakışıyor.")
    if catalog.CAMP in world["locations"][origin].get("travel_routes", {}):
        fail("adventure_route_collision", "Bu patikanın kaydı zaten mevcut.")
    world[catalog.KEY] = catalog.initial_state(origin)
    world[catalog.KEY]["known_locations"] = [origin, catalog.CAMP]
    world["locations"].update(catalog.locations(origin))
    world["locations"][origin].setdefault("travel_routes", {})[catalog.CAMP] = catalog.approach(origin)
    world["doors"].extend([
        {"id": identity, **copy.deepcopy(definition), "open": False, "broken": False}
        for identity, definition in catalog.DOORS.items()
    ])
    return _reply(session, message, "Taş patikanın kampına uzanan altı millik yolu öğrendin. Yola çıkmak sana kalmış.",
                  "exploration_begin", catalog_id=catalog.CATALOG_ID)


def _traverse(session, message, identity):
    world = session.world_state
    _busy(session, movement=True)
    exit = catalog.EXITS.get(identity)
    if not exit or exit["from"] != world["location"] or not visible_exit(world, exit):
        fail("exploration_exit_unknown", "Burada böyle bir geçit bilmiyorsun.")
    obstacle = exit_obstacle(world, exit)
    if obstacle:
        fail("exploration_exit_" + obstacle, "Bu geçit " + {"locked": "kilitli.", "closed": "kapalı.", "blocked": "molozla engellenmiş."}[obstacle])
    advancement = _time(session, exit["seconds"])
    if advancement.get("interrupted"):
        return _reply(session, message, "Geçide yaklaşırken bir karşılaşma seni durdurdu.", "exploration_interrupted", time_result=advancement)
    damage = _trigger(session, exit["trap_id"]) if exit.get("trap_id") else None
    if session.character["current_hp"] <= 0:
        return _reply(session, message, "Eşikteki tuzak seni yere düşürdü; geçidi aşamadın.", "trap_triggered", damage_result=damage, time_result=advancement)
    previous = world["location"]
    session.commit_location_change(exit["to"])
    notice_passively(session)
    record_knowledge(world)
    text = f"{world['locations'][exit['to']]['name']} konumuna geçtin."
    if damage:
        text = "Eşikteki tel gerildi ve tuzak tetiklendi. " + text
    return _reply(session, message, text, "dungeon_traverse", previous_location=previous,
                  new_location=exit["to"], exit_id=identity, damage_result=damage, time_result=advancement)


def _door_action(session, message, identity, operation):
    world = session.world_state
    _busy(session)
    candidates = {e.get("door_id") for e in catalog.EXITS.values()
                  if e["from"] == world["location"] and visible_exit(world, e)}
    candidates.update(d["id"] for d in world.get("doors", []) if d.get("id")
                      if d.get("id") not in catalog.DOORS and d.get("location") == world["location"]
                      and not d.get("hidden", False))
    gate = door(world, identity)
    if identity not in candidates or not gate or operation not in {"open", "close", "unlock", "break", "knock"}:
        fail("exploration_door_unknown", "Burada bu kapıya erişemiyorsun.")
    if operation == "knock":
        if gate["locked"]:
            state = "kilitli ve kapalı"
        elif gate.get("open"):
            state = "açık"
        else:
            state = "kapalı"
        text = (f"{gate['name']} üzerine vuruyorsun. Bir süre bekliyorsun; "
                f"içeriden yanıt gelmiyor. Kapı {state}." if gate["locked"] or not gate.get("open")
                else f"{gate['name']} zaten açık; vurmana gerek kalmadan içerisi görünüyor.")
        return _reply(session, message, text, "door_knock")
    if operation == "open" and gate["locked"]:
        fail("exploration_door_locked", "Kapı kilitli; önce kilidi açmalı veya kapıyı kırmalısın.")
    if operation == "close" and gate["broken"]:
        fail("exploration_door_broken", "Kırılmış kapıyı kapatamazsın.")
    if (operation == "open" and gate["open"] or operation == "close" and not gate["open"]
            or operation == "unlock" and not gate["locked"] or operation == "break" and gate["broken"]):
        return _reply(session, message, "Kapının durumu zaten istediğin gibi.", "door_unchanged")
    lock = catalog.LOCKS.get(identity)
    if lock is None:
        policy = gate.get("lock_policy", {"quality": "good", "complexity": "simple"})
        if (not isinstance(policy, dict) or set(policy) != {"quality", "complexity"}
                or policy["quality"] not in {"inferior", "good", "superior"}
                or policy["complexity"] not in {"simple", "complex"}):
            fail("lock_policy_invalid", "Kilit politikası geçersiz.")
        lock = {"unlock_dc": {"inferior": 10, "good": 15, "superior": 20}[policy["quality"]],
                "break_dc": 15, "attempt_seconds": 6 if policy["complexity"] == "simple" else 60,
                "handle_seconds": 6}
        if operation == "unlock":
            import equipment_economy
            if not any(equipment_economy.label(i) == "Thieves' Tools" for i in world["inventory"]):
                fail("thieves_tools_required", "Bu kilit için Hırsız Aletleri gerekiyor.")
    advancement = _time(session, lock["attempt_seconds"] if operation in {"unlock", "break"} else lock["handle_seconds"])
    if advancement.get("interrupted"):
        return _reply(session, message, "Kapıyla uğraşırken bir karşılaşma seni durdurdu.", "exploration_interrupted", time_result=advancement)
    check = _check(session, "Sleight of Hand" if operation == "unlock" else "Athletics",
                   lock[operation + "_dc"], tool="Thieves' Tools" if identity not in catalog.LOCKS
                   and operation == "unlock" else None) if operation in {"unlock", "break"} else {}
    if check.get("success", True):
        if operation == "unlock":
            gate["locked"] = False
        elif operation == "break":
            gate.update(locked=False, open=True, broken=True)
        else:
            gate["open"] = operation == "open"
        record_knowledge(world)
    text = f"{gate['name']}: " + ("girişimin sonuç verdi." if check.get("success", True) else "girişimin sonuç vermedi.")
    return _reply(
        session,
        message,
        text,
        check.pop("action", "door_interaction"),
        time_result=advancement,
        target_id=identity,
        target_type="door",
        **check,
    )


def _obstacle_action(session, message, kind, identity, operation):
    world = session.world_state
    _busy(session)
    definitions = catalog.TRAPS if kind == "trap" else catalog.HAZARDS
    definition = definitions.get(identity)
    state = world[catalog.KEY]
    if not definition or definition["location"] != world["location"]:
        fail("exploration_obstacle_unknown", "Bu engel bulunduğun yerde değil.")
    field = "trap_states" if kind == "trap" else "hazard_states"
    if kind == "trap" and state[field][identity] == "hidden":
        fail("exploration_trap_hidden", "Önce çevreni araştırarak tuzağı bulmalısın.")
    allowed = {"disarm", "bypass", "neutralize"} if kind == "trap" else {"clear", "bypass"}
    if operation not in allowed:
        fail("exploration_operation_invalid", "Bu engel için geçerli bir eylem seç.")
    if state[field][identity] in {"disarmed", "bypassed", "neutralized"}:
        return _reply(session, message, "Bu engeli zaten güvenli hâle getirdin.", "obstacle_unchanged")
    if kind == "trap" and state[field][identity] == "triggered" and operation != "neutralize":
        fail("exploration_trap_spent", "Tuzak zaten tetiklenmiş; kalıntılarını kaldırabilirsin.")
    if kind == "trap" and operation == "neutralize" and state[field][identity] != "triggered":
        fail("exploration_trap_active", "Bu tuzak hâlâ kurulu; önce etkisizleştirmeyi veya geçmeyi dene.")
    advancement = _time(session, catalog.OBSTACLE_SECONDS)
    if advancement.get("interrupted"):
        return _reply(session, message, "Engelle uğraşırken bir karşılaşma seni durdurdu.", "exploration_interrupted", time_result=advancement)
    check = {} if operation == "neutralize" else _check(
        session, "Acrobatics" if operation == "bypass" else "Sleight of Hand" if kind == "trap" else "Athletics", definition["dc"])
    damage = None
    if check.get("success", True):
        state[field][identity] = "bypassed" if operation == "bypass" and kind == "trap" else "disarmed" if operation == "disarm" else "neutralized"
    elif kind == "trap":
        damage = _trigger(session, identity)
    else:
        damage = _damage(session, definition)
    text = definition["name"] + (": güvenle ilerleyebilirsin." if check.get("success", True) else ": denemen başarılı olmadı.")
    return _reply(session, message, text, check.pop("action", "obstacle_interaction"), time_result=advancement, damage_result=damage, **check)


_APOSTROPHE_FOLD = str.maketrans({
    "\u2019": "'",
    "\u2018": "'",
    "\u02bc": "'",
    "\u00b4": "'",
    "`": "'",
})
_EN_AFFIRMATIVE = re.compile(
    r"\s*i\s+(?:am\s+|do\s+)?(?P<verb>breaking|unlocking|break|unlock)"
    r"\s+(?:(?:the|my|a|an)\s+)?$"
)
_EN_KNOCK = re.compile(r"\s*i\s+(?:am\s+)?(?:knocking|knock)(?:\s+on)?\s*$")
_EN_OTHER_OBJECT_TAIL = re.compile(
    r"\s+(?:after|before|while)\s+(?:i\s+)?(?:am\s+|do\s+)?"
    r"(?:unlocking|breaking|opening|unlock|break|open)\s+"
    r"(?:(?:my|the|a|an)\s+)?(?P<object>[a-z0-9']+)"
    r"(?:\s+[a-z0-9']+){0,3}\s*"
)
_TR_BREAK = re.compile(
    r"\s+(?:omzumla\s+zorlayarak\s+)?"
    r"(?:kiriyorum|kirmayi\s+deniyorum|kirmaya\s+calisiyorum)\b"
)
_TR_UNLOCK = re.compile(
    r"\s+(?:kilitli\.\s*)?(?:iceri\s+girebilmek\s+icin\s+)?"
    r"kilid(?:i|ini)\s+ac(?:iyorum|mayi\s+deniyorum|maya\s+calisiyorum)\b"
)
_TR_KNOCK = re.compile(
    r"\s+(?:elimle\s+)?(?:tikliyorum|tiklatiyorum|caliyorum)\b"
)


def _strip_quoted_spans(text):
    for opening, closing in (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")):
        text = re.sub(
            re.escape(opening) + r".*?" + re.escape(closing),
            " ",
            text,
        )
    return text


def _clause_end(text, end):
    sentence_end = len(text)
    for punctuation in ".!?;":
        boundary = text.find(punctuation, end)
        if boundary != -1:
            sentence_end = min(sentence_end, boundary)
    return sentence_end


def _english_operation(prefix):
    if _EN_KNOCK.fullmatch(prefix):
        return "knock"
    match = _EN_AFFIRMATIVE.fullmatch(prefix)
    if match is None:
        return None
    verb = match.group("verb")
    if verb.startswith("break"):
        return "break"
    if verb.startswith("unlock"):
        return "unlock"
    return None


def _tail_keeps_operation(tail, door_id, door_name):
    if re.fullmatch(r"\s*", tail):
        return True
    if _EN_OTHER_OBJECT_TAIL.fullmatch(tail) is None:
        return False
    if door_id and door_id in tail:
        return False
    if door_name and door_name in tail:
        return False
    return True


def _natural_venue_door_action(session, message):
    if not isinstance(message, str) or "?" in message or session is None:
        return None
    import campaign_time
    text = _strip_quoted_spans(campaign_time.normalize(message)).translate(_APOSTROPHE_FOLD)
    world = session.world_state
    candidates = [
        door for door in world.get("doors", [])
        if isinstance(door, dict)
        and isinstance(door.get("id"), str)
        and door["id"].startswith("venue-door:")
        and door.get("location") == world.get("location")
        and not door.get("hidden", False)
    ]
    resolved = set()

    for door in candidates:
        reference_patterns = [
            re.compile(r"(?<![\w:-])" + re.escape(door["id"]) + r"(?![\w:-])")
        ]
        normalized_name = ""
        name = door.get("name")
        if isinstance(name, str) and name.strip():
            normalized_name = campaign_time.normalize(name).strip().translate(_APOSTROPHE_FOLD)
            name_pattern = r"\s+".join(
                re.escape(part) for part in normalized_name.split()
            )
            # Case suffixes attach only after the complete name.
            reference_patterns.append(re.compile(
                r"(?<!\w)" + name_pattern
                + r"(?:n(?:dan|den|da|de|a|e|i|u))?(?!\w)"
            ))
        references = [
            match
            for pattern in reference_patterns
            for match in pattern.finditer(text)
        ]
        if not references:
            continue

        for reference in references:
            # A colon stays inside the clause, so a denial or hypothesis before it
            # still covers the door and the verb.
            clause_start = max(
                text.rfind(".", 0, reference.start()),
                text.rfind("!", 0, reference.start()),
                text.rfind("?", 0, reference.start()),
                text.rfind(";", 0, reference.start()),
            ) + 1
            prefix = text[clause_start:reference.start()]
            operation = _english_operation(prefix)
            if operation is not None:
                sentence_end = _clause_end(text, reference.end())
                tail = text[reference.end():sentence_end]
                keeps_tail = (
                    re.fullmatch(r"\s*", tail)
                    if operation == "knock"
                    else _tail_keeps_operation(tail, door["id"], normalized_name)
                )
                if keeps_tail:
                    resolved.add((door["id"], operation))
            if re.fullmatch(r"\s*", prefix) is None:
                continue
            remainder = text[reference.end():]
            for pattern, operation in (
                (_TR_BREAK, "break"),
                (_TR_UNLOCK, "unlock"),
                (_TR_KNOCK, "knock"),
            ):
                verb = pattern.match(remainder)
                if verb is None:
                    continue
                verb_end = reference.end() + verb.end()
                tail = text[verb_end:_clause_end(text, verb_end)]
                if re.fullmatch(r"\s*", tail):
                    resolved.add((door["id"], operation))

    return next(iter(resolved)) if len(resolved) == 1 else None


def native_request(message, session=None):
    return isinstance(message, str) and (
        message.strip().startswith(("/explore", "/travel"))
        or session is not None and _natural_venue_door_action(session, message) is not None
        or session is not None and active(session.world_state)
        and session.world_state["location"] in catalog.ROOM_IDS
        and (session._has_travel_language(message)
             or bool(re.search(r"\b(?:kap[ıi]|kilit|tuzak|moloz|kald[ıi]raç|door|trap|exit)\w*", message.casefold())))
        and not message.strip().endswith("?")
    )


def resolve_command(session, message):
    if not native_request(message, session):
        return None
    parts = message.strip().split()
    world = session.world_state
    session.require_player_can_act()
    venue_door_action = _natural_venue_door_action(session, message)
    if venue_door_action is not None:
        return _door_action(session, message, *venue_door_action)
    if parts == ["/explore", "begin"]:
        return _begin(session, message)
    if parts == ["/travel", "pace"] or parts == ["/explore", "look"]:
        return _reply(session, message, describe(world), "exploration_observe")
    if len(parts) == 3 and parts[:2] == ["/travel", "pace"]:
        _busy(session)
        if parts[2] not in timed_gameplay.PACE_MILES_PER_DAY:
            fail("travel_pace_invalid", "Hızlı, normal veya yavaş tempoyu seç.")
        world["flags"]["travel_pace"] = parts[2]
        return _reply(session, message, {"fast": "Hızlı", "normal": "Normal", "slow": "Yavaş"}[parts[2]] + " tempoyu seçtin.", "travel_pace")
    if len(parts) == 3 and parts[:2] == ["/travel", "supplies"]:
        _busy(session)
        if parts[2] not in {"enabled", "disabled"}:
            fail("supplies_policy_invalid", "Erzak politikasını açık veya kapalı seç.")
        world["supplies_policy"] = {"enabled": parts[2] == "enabled"}
        return _reply(session, message, "Erzak politikası kaydedildi.", "supplies_policy")
    if parts == ["/travel", "forage"]:
        _busy(session)
        import equipment_economy
        return _timed_reply(session, message, dict(equipment_economy.forage(session), action="foraging"))
    if len(parts) == 3 and parts[:2] == ["/travel", "track"]:
        _busy(session)
        feature = next((f for f in world.get("features", []) if f.get("id") == parts[2]
                        and f.get("location") == world["location"] and not f.get("hidden", False)
                        and isinstance(f.get("trail_policy"), dict)), None)
        if feature is None:
            fail("tracking_trail_unknown", "Burada bilinen bir takip izi yok.")
        policy = feature["trail_policy"]
        if set(policy) != {"confined", "dc"} or type(policy["confined"]) is not bool or policy["dc"] not in {10, 15, 20, 25, 30}:
            fail("tracking_policy_invalid", "İzin takip politikası geçersiz.")
        if (world.get("tracking") or {}).get("trail_id") != parts[2]:
            world["tracking"] = {"trail_id": parts[2], "location_id": world["location"],
                                 "status": "LOST", "spent_seconds": 0, "attempts": 0, **policy}
        return _timed_reply(session, message, timed_gameplay.reacquire_tracking(session))
    if parts == ["/travel", "reacquire"]:
        _busy(session, task=True)
        return _timed_reply(session, message, timed_gameplay.reacquire_tracking(session))
    if len(parts) == 4 and parts[:2] == ["/explore", "door"] and parts[2] not in catalog.DOORS:
        return _door_action(session, message, parts[2], parts[3])
    if not active(world):
        fail("exploration_not_started", "Önce taş patikanın macerasını seç.")
    validate_state(world)
    if len(parts) == 3 and parts[:2] == ["/explore", "decision"]:
        _busy(session, journey=True, task=True, pending=True)
        choices = {"continue": "devam", "talk": "konus", "stop": "dur", "return": "geri don", "fight": "savas"}
        if parts[2] not in choices or not any(e.get("decision_status") == "PENDING" for e in world.get("scheduled_events", [])):
            fail("exploration_decision_invalid", "Bekleyen karşılaşma için geçerli bir karar seç.")
        result = timed_gameplay.resolve_pending(session, choices[parts[2]])
        if result is None and parts[2] == "return":
            result = timed_gameplay.return_travel(session)
        return _timed_reply(session, message, result)
    if len(parts) == 3 and parts[:2] == ["/travel", "go"]:
        _busy(session)
        if parts[2] not in known_locations(world) or not route_allowed(world, world["location"], parts[2]) or timed_gameplay.route_stages(world, parts[2]) is None:
            fail("travel_route_unknown", "Buradan bu konuma bilinen bir rota yok.")
        return _timed_reply(session, message, timed_gameplay.start_travel(session, parts[2]))
    if parts in (["/travel", "continue"], ["/travel", "return"], ["/travel", "stop"]):
        _busy(session, journey=True)
        journey = world.get("journey")
        if not journey or journey["status"] == "ARRIVED":
            fail("travel_not_active", "Şu anda yolda değilsin.")
        if parts[1] == "stop":
            journey["status"] = "STOPPED"
            return _reply(session, message, "Yolculuğu durdurdun.", "travel_stop")
        result = timed_gameplay.return_travel(session) if parts[1] == "return" else timed_gameplay.continue_travel(session)
        return _timed_reply(session, message, result)
    if parts == ["/travel", "scout"]:
        _busy(session, journey=True)
        import weapon_attack
        if "blinded" in weapon_attack.conditions(session, "player", session.character):
            fail("travel_scout_blinded", "Görmeye bağlı yol işaretlerini şu anda inceleyemezsin.")
        journey = world.get("journey")
        if not journey or journey["status"] == "ARRIVED" or "route_id" not in journey:
            fail("travel_scout_unavailable", "Önce bilinen bir patikada yolculuğa başlamalısın.")
        advancement = _time(session, catalog.SCOUTING["seconds"])
        if advancement.get("interrupted"):
            return _reply(session, message, "Bir karşılaşma çevreni gözetlemene engel oldu.", "exploration_interrupted", time_result=advancement)
        obscured = catalog.LOCATIONS.get(world["location"], {}).get("visibility") == "lightly_obscured"
        check = _check(session, "Perception", catalog.SCOUTING["dc"], disadvantage=obscured)
        text = "Durup çevrendeki yol işaretlerini gözden geçirdin." if check["success"] else "Durup baktın, ancak çevrenden bir ipucu çıkaramadın."
        return _reply(session, message, text, check.pop("action"), time_result=advancement, **check)
    if parts == ["/explore", "search"]:
        _busy(session, task=True)
        if "blinded" in __import__("weapon_attack").conditions(session, "player", session.character):
            fail("exploration_search_blinded", "Görmeye bağlı ipuçlarını şu anda inceleyemezsin.")
        return _timed_reply(session, message, timed_gameplay.resolve_task(session, message, None))
    if len(parts) == 3 and parts[:2] == ["/explore", "investigate"]:
        _busy(session)
        identity = parts[2]
        state = world[catalog.KEY]
        if (identity not in state["discoveries"]
                or catalog.DISCOVERIES[identity]["location"] != world["location"]):
            fail("exploration_clue_unknown", "Önce burada görünen bir ipucu bulmalısın.")
        if identity in state.get("inferences", []):
            return _reply(session, message, catalog.INVESTIGATION[identity], "clue_known")
        attempts = state.get("investigation_attempts", {}).get(identity, 0)
        advancement = _time(session, catalog.SEARCH_POLICIES[world["location"]]["seconds"])
        if advancement.get("interrupted"):
            return _reply(session, message, "Bir karşılaşma ipucunu incelemeni durdurdu.", "exploration_interrupted", time_result=advancement)
        check = _check(session, "Investigation", catalog.SEARCH_POLICIES[world["location"]]["dc"]) if not attempts else {}
        state.setdefault("investigation_attempts", {})[identity] = min(2, attempts + 1)
        if check.get("success", True):
            state.setdefault("inferences", []).append(identity)
        text = catalog.INVESTIGATION[identity] if check.get("success", True) else "Görünen ipucunu inceledin; bağlantısını henüz çözemedin."
        return _reply(session, message, text, check.pop("action", "clue_investigation"),
                      time_result=advancement, **check)
    if len(parts) == 3 and parts[:2] == ["/explore", "exit"]:
        return _traverse(session, message, parts[2])
    if len(parts) == 4 and parts[0] == "/explore" and parts[1] in {"door", "trap", "hazard"}:
        return _door_action(session, message, *parts[2:]) if parts[1] == "door" else _obstacle_action(session, message, *parts[1:])
    if len(parts) == 3 and parts[:2] == ["/explore", "interact"]:
        _busy(session)
        definition = catalog.INTERACTIONS.get(parts[2])
        if not definition or definition["location"] != world["location"]:
            fail("exploration_interaction_unknown", "Burada bu nesneye erişemiyorsun.")
        state = world[catalog.KEY]
        advancement = _time(session, catalog.INTERACTION_SECONDS)
        if not advancement.get("interrupted"):
            if parts[2] not in state["interactions"]:
                state["interactions"].append(parts[2])
            state["hazard_states"][definition["hazard_id"]] = "neutralized"
        return _reply(session, message, "Kaldıraç molozları kenara çekti." if not advancement.get("interrupted") else "Bir karşılaşma seni durdurdu.",
                      "environment_interaction", time_result=advancement)
    if parts == ["/explore", "encounter"]:
        _busy(session)
        if world["location"] != catalog.ENTRY:
            fail("exploration_encounter_unavailable", "Burada böyle bir karşılaşma yok.")
        import bounded_encounter
        state = bounded_encounter.binding(session)
        if state and state["location_id"] != world["location"]:
            fail("exploration_encounter_conflict", "Önce daha önce karşılaştığın tehdidi çöz; mevcut karşılaşma sıfırlanmadı.")
        return bounded_encounter.resolve_command(session, bounded_encounter.ENTER, player_message=message)
    # Only imperative, explicit references may select an authored door. Never
    # choose the first door when two are present, or turn a statement into canon.
    if not parts[0].startswith("/"):
        import campaign_time
        import interaction_adventure
        if interaction_adventure.compound_plan(message) is not None:
            return _reply(session, message, "Bu geçit ve nesnelerle sırayla ilgilenelim; önce hangi eylemi seçtiğini belirt.",
                          "exploration_clarification", success=False)
        text = campaign_time.normalize(message)
        if re.search(r"\b(?:degil|istemiyorum|acma|kirma|yapmiyorum|don't|do not)\b", text):
            return _reply(session, message, "İstemediğin eylem uygulanmadı.", "exploration_declined")
        operation = (
            "unlock" if re.search(r"\b(?:kilidi ac\w*|unlock\w*)\b", text) else
            "break" if re.search(r"\b(?:kiriyorum|kir|break\w*)\b", text) else
            "close" if re.search(r"\b(?:kapatiyorum|kapat|close\w*)\b", text) else
            "open" if re.search(r"\b(?:aciyorum|ac|open\w*)\b", text) else None
        )
        candidates = {
            e.get("door_id") for e in catalog.EXITS.values()
            if e["from"] == world["location"] and visible_exit(world, e) and e.get("door_id")
        }
        named = [identity for identity in candidates
                 if identity in message or campaign_time.normalize(catalog.DOORS[identity]["name"]) in text]
        if operation and len(named) == 1:
            return _door_action(session, message, named[0], operation)
        generic = re.fullmatch(
            r"(?:kapiyi|kapi|kilidi) (?:ac|aciyorum|kapat|kapatiyorum|kir|kiriyorum)[.! ]*"
            r"|(?:open|close|break|unlock)(?: the)? (?:door|lock)[.! ]*", text)
        if operation and generic and len(candidates) == 1:
            return _door_action(session, message, next(iter(candidates)), operation)
        return _reply(session, message, "Hangi kapı veya nesneyle ne yapmak istediğini belirt.", "exploration_clarification", success=False)
    fail("exploration_command_ambiguous", "Ne yapmak istediğini ve hangi geçit veya nesneye yöneldiğini belirt.")


def describe(world):
    if not active(world):
        return "Taş patikanın yerel macerasını seçebilirsin."
    current = world["location"]
    names = [e["name"] for e in public_projection(world)["exits"]]
    return "Buradan görünen geçitler: " + (", ".join(names) if names else "henüz bilinen bir geçit yok.")


def visible_doors(world):
    if not active(world):
        return world.get("doors", [])
    local = {e.get("door_id") for e in catalog.EXITS.values()
             if e["from"] == world["location"] and visible_exit(world, e)}
    return [d for d in world.get("doors", []) if not d.get("hidden", False)
            and (d.get("id") not in catalog.DOORS or d.get("id") in local)]


def public_projection(world):
    """Only observable possibilities/actions; never hidden catalog topology."""
    state = world.get(catalog.KEY)
    if not state:
        return None
    current = world["location"]
    ongoing = (world.get("journey") or {}).get("status", "ARRIVED") != "ARRIVED"
    actions = []
    def add(label, message):
        actions.append({"label": label, "message": message})
    exits, obstacles = [], []
    if ongoing:
        add("Durup çevreyi gözetle", "/travel scout")
    if not ongoing:
        add("Çevreyi araştır", "/explore search")
        for identity, exit in catalog.EXITS.items():
            if exit["from"] == current and visible_exit(world, exit):
                known = known_locations(world)
                exits.append({"id": identity, "destination": exit["to"] if exit["to"] in known else None,
                              "name": world["locations"][exit["to"]]["name"] if exit["to"] in known else door(world, exit.get("door_id"))["name"],
                              "state": exit_obstacle(world, exit) or "open", "door_id": exit.get("door_id")})
                if not exit_obstacle(world, exit):
                    add(world["locations"][exit["to"]]["name"] + " yönüne geç", "/explore exit " + identity)
        local_doors = {e.get("door_id") for e in catalog.EXITS.values() if e["from"] == current and visible_exit(world, e)}
        for identity in sorted(local_doors - {None}):
            gate = door(world, identity)
            if gate["locked"]:
                add(gate["name"] + " · kilidi aç", f"/explore door {identity} unlock")
                add(gate["name"] + " · kırmayı dene", f"/explore door {identity} break")
            elif not gate["broken"]:
                add(gate["name"] + (" · kapat" if gate["open"] else " · aç"),
                    f"/explore door {identity} " + ("close" if gate["open"] else "open"))
        for identity, definition in catalog.TRAPS.items():
            status = state["trap_states"][identity]
            if definition["location"] == current and status != "hidden":
                obstacles.append({"id": identity, "name": definition["name"], "state": status})
                if status == "detected":
                    add("Teli etkisizleştir", f"/explore trap {identity} disarm")
                    add("Telin üzerinden güvenle geç", f"/explore trap {identity} bypass")
                elif status == "triggered":
                    add("Tuzak kalıntılarını kaldır", f"/explore trap {identity} neutralize")
        for identity, definition in catalog.HAZARDS.items():
            if definition["location"] == current:
                obstacles.append({"id": identity, "name": definition["name"], "state": state["hazard_states"][identity]})
                if state["hazard_states"][identity] == "active":
                    add("Molozu temizlemeyi dene", f"/explore hazard {identity} clear")
        for identity, definition in catalog.INTERACTIONS.items():
            if definition["location"] == current and identity not in state["interactions"]:
                add("Taş kaldıracı çek", "/explore interact " + identity)
        if current == catalog.ENTRY and world.get("bounded_encounter") is None:
            add("Avluyu incele", "/explore encounter")
        for identity in state["discoveries"]:
            if catalog.DISCOVERIES[identity]["location"] == current and identity not in state.get("inferences", []):
                add(catalog.DISCOVERIES[identity]["name"] + " · ipucunu incele", "/explore investigate " + identity)
    routes = []
    for destination, route in world["locations"].get(current, {}).get("travel_routes", {}).items():
        if isinstance(route, dict) and destination in known_locations(world):
            blocked = world.get("blocked_travel_routes", {}).get(current, {}).get(destination, False)
            durations = timed_gameplay.route_stages(world, destination)
            routes.append({"id": route["id"], "origin": current, "destination": destination,
                           "name": world["locations"][destination]["name"], "distance_miles": route["distance_miles"],
                           "duration_seconds": sum(durations) if durations is not None else None, "blocked": blocked})
            if not ongoing and not blocked:
                add("Yola çık · " + world["locations"][destination]["name"], "/travel go " + destination)
    if world.get("active_task"):
        actions = [{"label": "Araştırmayı sürdür", "message": "/explore search"}]
    if any(e.get("decision_status") in {"PENDING", "IN_COMBAT"} for e in world.get("scheduled_events", [])):
        actions = []
    return {
        "catalog_id": state["catalog_id"], "pace": world.get("flags", {}).get("travel_pace", "normal"),
        "weather": catalog.LOCATIONS.get(current, {}).get("weather", "unknown"),
        "routes": routes, "exits": exits, "obstacles": obstacles,
        "discoveries": [{"id": d, "name": catalog.DISCOVERIES[d]["name"], "text": catalog.DISCOVERIES[d]["text"]}
                        for d in state["discoveries"] if catalog.DISCOVERIES[d]["location"] == current],
        "actions": actions,
    }
