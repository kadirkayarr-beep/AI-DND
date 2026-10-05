"""Package 3 orchestration. Position/time/checks/damage/saves retain their owners."""
import copy
import re

import local_adventure_catalog as catalog
import timed_gameplay
from combat_lifecycle import CombatRequestError

TRAP_STATES = frozenset({"hidden", "detected", "disarmed", "bypassed", "triggered", "neutralized"})


def fail(code, message):
    raise CombatRequestError(code, message, 400)


def validate_state(world):
    state = world.get(catalog.KEY)
    if state is None:
        return
    if (not isinstance(state, dict) or set(state) != set(catalog.initial_state(""))
            or state["catalog_id"] != catalog.CATALOG_ID
            or not isinstance(state["origin"], str) or state["origin"] not in world["locations"]
            or state["origin"] in catalog.LOCATIONS):
        raise ValueError("Local adventure binding is invalid.")
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
    return found


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
    return response


def _timed_reply(session, message, result):
    return _reply(session, message, result.get("direct_response", "Eylemin tamamlandı."),
                  result.get("action", "exploration"), **{k: v for k, v in result.items() if k != "action"})


def _check(session, skill, dc, *, disadvantage=False):
    player = session.character
    check = session.perform_skill_check(
        skill, dc, player["modifiers"], player["proficient_skills"],
        player["proficiency_bonus"], expertise_skills=player.get("expertise_skills", ()),
        disadvantage=disadvantage,
    )
    return dict(check, action="skill_check", outcome="success" if check["resolution"]["outcome"] == "SUCCESS" else "failure",
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
    gate = door(world, identity)
    if identity not in candidates or not gate or operation not in {"open", "close", "unlock", "break"}:
        fail("exploration_door_unknown", "Burada bu kapıya erişemiyorsun.")
    if operation == "open" and gate["locked"]:
        fail("exploration_door_locked", "Kapı kilitli; önce kilidi açmalı veya kapıyı kırmalısın.")
    if operation == "close" and gate["broken"]:
        fail("exploration_door_broken", "Kırılmış kapıyı kapatamazsın.")
    if (operation == "open" and gate["open"] or operation == "close" and not gate["open"]
            or operation == "unlock" and not gate["locked"] or operation == "break" and gate["broken"]):
        return _reply(session, message, "Kapının durumu zaten istediğin gibi.", "door_unchanged")
    lock = catalog.LOCKS[identity]
    advancement = _time(session, lock["attempt_seconds"] if operation in {"unlock", "break"} else lock["handle_seconds"])
    if advancement.get("interrupted"):
        return _reply(session, message, "Kapıyla uğraşırken bir karşılaşma seni durdurdu.", "exploration_interrupted", time_result=advancement)
    check = _check(session, "Sleight of Hand" if operation == "unlock" else "Athletics",
                   lock[operation + "_dc"]) if operation in {"unlock", "break"} else {}
    if check.get("success", True):
        if operation == "unlock":
            gate["locked"] = False
        elif operation == "break":
            gate.update(locked=False, open=True, broken=True)
        else:
            gate["open"] = operation == "open"
    text = f"{gate['name']}: " + ("girişimin sonuç verdi." if check.get("success", True) else "girişimin sonuç vermedi.")
    return _reply(session, message, text, check.pop("action", "door_interaction"), time_result=advancement, **check)


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
    advancement = _time(session, 60)
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


def native_request(message, session=None):
    return isinstance(message, str) and (
        message.strip().startswith(("/explore", "/travel"))
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
        if not route_allowed(world, world["location"], parts[2]) or timed_gameplay.route_stages(world, parts[2]) is None:
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
        return _timed_reply(session, message, timed_gameplay.resolve_task(session, message, None))
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
        advancement = _time(session, 6)
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
    names = [world["locations"][e["to"]]["name"] for e in catalog.EXITS.values()
             if e["from"] == current and visible_exit(world, e)]
    return "Buradan görünen geçitler: " + (", ".join(names) if names else "henüz bilinen bir geçit yok.")


def visible_doors(world):
    if not active(world):
        return world.get("doors", [])
    known = world[catalog.KEY]["discoveries"]
    return [d for d in world.get("doors", []) if d.get("id") != "stone_secret_door" or "stone_secret" in known]


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
                exits.append({"id": identity, "destination": exit["to"], "name": world["locations"][exit["to"]]["name"],
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
    routes = []
    for destination, route in world["locations"].get(current, {}).get("travel_routes", {}).items():
        if isinstance(route, dict):
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
