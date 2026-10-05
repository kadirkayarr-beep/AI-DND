"""PHB 2024 turn resources, owned by the existing combat state.

No dice, initiative, persistence, class-feature or spell implementation here.
Only engine code can grant resources and publish perceivable trigger events.
"""
import copy
import re
import weapon_attack
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from combat_lifecycle import CombatRequestError

ACTION_TYPES = frozenset({
    "attack", "dash", "disengage", "dodge", "help", "hide", "influence",
    "magic", "ready", "search", "study", "utilize", "feature",
})
_execution = ContextVar("economy_execution", default=None)


def fail(code, message):
    raise CombatRequestError(code, message, 400)


def actor_data(session, actor):
    combat = session.world_state["combat"]
    if not combat["active"] or actor not in combat["participants"]:
        fail("invalid_combat_actor", "Actor does not belong to active combat.")
    if actor == "player":
        return session.character
    values = [n for n in session.world_state["npcs"] if n.get("id") == actor]
    if len(values) != 1:
        fail("invalid_combat_actor", "Actor is not present.")
    return values[0]


def conditions(session, actor):
    data = actor_data(session, actor)
    names = data.get("conditions", [])
    if isinstance(names, dict):
        names = [name for name, enabled in names.items() if enabled]
    return {str(name).lower() for name in names}


def can_act(session, actor):
    data = actor_data(session, actor)
    status = (session.world_state.get("player_combat_status", "active")
              if actor == "player" else data.get("combat_status", "active"))
    return (data.get("current_hp", 0) > 0 and status == "active"
            and not (actor == "player" and session.world_state.get("death_state", {}).get("dead", False))
            and (actor == "player" or data.get("location") == session.world_state["location"])
            and not conditions(session, actor) & {"incapacitated", "unconscious", "dead", "paralyzed", "stunned", "petrified"})


def speed(session, actor):
    outside_player = actor == "player" and not session.world_state.get("combat", {}).get("active")
    data = session.character if outside_player else actor_data(session, actor)
    active_conditions = weapon_attack.conditions(session, actor, data) if outside_player else conditions(session, actor)
    capable = (data.get("current_hp", 0) > 0 and not active_conditions & {
        "incapacitated", "unconscious", "dead", "paralyzed", "stunned", "petrified"
    }) if outside_player else can_act(session, actor)
    if not capable or active_conditions & {"grappled", "restrained"}:
        return 0
    value = int(data.get("speed_ft", 30 if actor == "player" else 0))
    if actor == "player":
        if (data.get("species_trait_state") or {}).get("large_form_turns_remaining", 0) > 0:
            value += 10
    value -= int(data.get("speed_penalty_ft", 0))
    value -= weapon_attack.slow_penalty(session, actor)
    return max(0, value)


def bonus_rules(session, actor):
    if actor != "player":
        return []
    c = session.character
    s = c.get("species_trait_state") or {}
    rules = []
    if c.get("species", c.get("race")) == "Orc" and s.get("adrenaline_rush_uses_remaining", 0) > 0:
        rules.append("adrenaline_rush")
    if c.get("species", c.get("race")) == "Aasimar" and c.get("level", 1) >= 3 and s.get("celestial_revelation_uses_remaining", 0) > 0:
        rules.append("celestial_revelation")
    if c.get("species", c.get("race")) == "Goliath":
        if c.get("level", 1) >= 5 and s.get("large_form_uses_remaining", 0) > 0:
            rules.append("large_form")
        if c.get("giant_ancestry") == "cloud" and s.get("giant_ancestry_uses_remaining", 0) > 0:
            rules.append("cloud_jaunt")
    return rules


def _initial_resources(session, actor, actions_used):
    return {
        "base_action_spent": actor in actions_used,
        "additional_actions": [], "bonus_action_spent": False,
        "bonus_grants": [], "reaction_spent": False,
        "movement_available": speed(session, actor), "movement_used": 0,
        "dash_count": 0, "ready_movement_grant": 0,
        "ready": None, "opportunity": None, "attack_action": None,
    }


def initialize_actor(session, actor):
    """Membership hook; Initiative does not own or duplicate these resources."""
    combat = session.world_state["combat"]
    if actor not in combat["participants"]:
        fail("invalid_combat_actor", "Resource owner is not a participant.")
    combat.setdefault("turn_resources", {})[actor] = _initial_resources(session, actor, combat["actions_used"])


def ensure(session):
    combat = session.world_state["combat"]
    if not combat["active"]:
        return {}
    if "turn_resources" not in combat:
        # One-time, conservative compatibility with existing v3 saves.
        combat["turn_resources"] = {
            actor: _initial_resources(session, actor, combat["actions_used"])
            for actor in combat["participants"]
        }
        old = (session.character.get("species_trait_state") or {}).get("bonus_action_used_round")
        if old == combat["round"]:
            combat["turn_resources"]["player"]["bonus_action_spent"] = True
    return combat["turn_resources"]


def validate_saved(combat):
    resources = combat.get("turn_resources")
    if resources is None:
        return  # Known old combat schema; migrated once by ensure.
    if not isinstance(resources, dict) or set(resources) != set(combat["participants"]):
        raise ValueError("Invalid combat turn resource owners.")
    for actor, r in resources.items():
        if not isinstance(r, dict):
            raise ValueError("Invalid turn resources.")
        for name in ("base_action_spent", "bonus_action_spent", "reaction_spent"):
            if type(r.get(name)) is not bool:
                raise ValueError("Invalid resource availability.")
        if r["base_action_spent"] != (actor in combat["actions_used"]):
            raise ValueError("Combat action marker and base action resource disagree.")
        for name in ("movement_available", "movement_used"):
            if type(r.get(name)) is not int or r[name] < 0:
                raise ValueError("Invalid movement resource.")
        for name in ("dash_count", "ready_movement_grant"):
            if type(r.get(name, 0)) is not int or r.get(name, 0) < 0:
                raise ValueError("Invalid movement grant.")
        if r["movement_used"] > r["movement_available"]:
            raise ValueError("Movement is overspent.")
        for name in ("additional_actions", "bonus_grants"):
            if not isinstance(r.get(name), list):
                raise ValueError("Invalid resource grants.")
            for grant in r[name]:
                if (not isinstance(grant, dict) or not isinstance(grant.get("source"), str)
                    or type(grant.get("quantity")) is not int or grant["quantity"] < 1
                    or type(grant.get("remaining")) is not int or not 0 <= grant["remaining"] <= grant["quantity"]
                    or not isinstance(grant.get("restrictions"), dict)
                    or not isinstance(grant.get("allowed_action_types"), list)
                    or not set(grant["allowed_action_types"]).issubset(ACTION_TYPES)
                    or type(grant.get("refresh_each_turn", False)) is not bool):
                    raise ValueError("Invalid restricted action grant.")
        ready = r.get("ready")
        if ready is not None:
            if (not isinstance(ready, dict) or ready.get("trigger", {}).get("event") not in {"actor_moves", "actor_attacks"}
                or ready["trigger"].get("actor_id") not in combat["participants"]
                or ready.get("response", {}).get("kind") not in {"attack", "move", "magic"}):
                raise ValueError("Invalid Ready state.")
            if ready["response"]["kind"] == "magic" and not isinstance(ready.get("spell_metadata"), dict):
                raise ValueError("Readied spell metadata is missing.")
        opportunity = r.get("opportunity")
        if opportunity is not None and (
            not ready or not isinstance(opportunity, dict)
            or opportunity.get("event") != ready["trigger"]["event"]
            or opportunity.get("actor_id") != ready["trigger"]["actor_id"]
            or not isinstance(opportunity.get("id"), str)
        ):
            raise ValueError("Invalid authoritative reaction opportunity.")


def begin_round(session):
    """Reset round-scoped action markers and their base-action projection together.

    Reactions, Ready state and other resources still expire at the actor's turn,
    not at the round boundary.
    """
    combat = session.world_state["combat"]
    resources = ensure(session)
    combat["actions_used"] = []
    for r in resources.values():
        r["base_action_spent"] = False
    session._sync_combat_participant_records(combat)


def begin_turn(session, actor):
    r = ensure(session)[actor]
    weapon_attack.boundary(session, actor, "begin")
    r.pop("weapon_sequence", None)
    r["base_action_spent"] = False
    r["bonus_action_spent"] = False
    r["reaction_spent"] = False
    r["movement_available"] = speed(session, actor)
    r["movement_used"] = 0
    r["dash_count"] = 0
    r["ready_movement_grant"] = 0
    r["ready"] = None
    r["opportunity"] = None
    r["attack_action"] = None
    r.pop("dodging", None)
    r.pop("disengaging", None)
    for name in ("additional_actions", "bonus_grants"):
        r[name] = [g for g in r[name] if g.get("refresh_each_turn")]
        for grant in r[name]:
            grant["remaining"] = grant["quantity"]
    if actor == "player":
        if session.character.get("species_trait_state"):
            session.character["species_trait_state"]["bonus_action_used_round"] = None


def grant(session, actor, source, allowed_action_types, quantity=1, *,
          resource="action", refresh_each_turn=False, restrictions=None):
    """Engine-only compatibility hook. No grant fields exist in HTTP input."""
    if (not source or type(quantity) is not int or quantity < 1
        or resource not in {"action", "bonus"}
        or not allowed_action_types or not set(allowed_action_types).issubset(ACTION_TYPES)):
        fail("invalid_action_grant", "Invalid rule-defined resource grant.")
    if set(restrictions or {}) - {"requires_base_action_spent", "max_attacks"}:
        fail("invalid_action_grant", "This restriction needs an authoritative feature validator.")
    r = ensure(session)[actor]
    r["additional_actions" if resource == "action" else "bonus_grants"].append({
        "source": source, "quantity": quantity, "remaining": quantity,
        "allowed_action_types": list(allowed_action_types),
        "restrictions": copy.deepcopy(restrictions or {}),
        "refresh_each_turn": refresh_each_turn,
    })


def validate_actor(session, actor="player", reaction=False):
    if not can_act(session, actor):
        fail("actor_cannot_act", "Authoritative actor condition prevents this action.")
    if not reaction and session.world_state["combat"]["current_actor_id"] != actor:
        fail("out_of_turn", "Actor is not the current participant.")


def action_slot(session, actor, kind, resource="action"):
    validate_actor(session, actor)
    if resource not in {"action", "bonus"}:
        fail("invalid_resource_type", "Unknown Action resource.")
    if kind not in ACTION_TYPES:
        fail("unsupported_action", "Unknown Action family.")
    r = ensure(session)[actor]
    if resource == "action" and not r["base_action_spent"]:
        return None
    if resource == "bonus" and r["bonus_action_spent"]:
        fail("bonus_action_spent", "The Bonus Action was already taken.")
    name = "additional_actions" if resource == "action" else "bonus_grants"
    for g in r[name]:
        if (g["remaining"] > 0 and kind in g["allowed_action_types"]
            and (not g["restrictions"].get("requires_base_action_spent", False) or r["base_action_spent"])):
            return g
    fail("action_unavailable", "No matching rule-defined resource is available.")


def consume_action(session, actor, kind="attack", resource="action"):
    slot = action_slot(session, actor, kind, resource)
    r = ensure(session)[actor]
    if slot is None:
        r["base_action_spent"] = True
        combat = session.world_state["combat"]
        if actor not in combat["actions_used"]:
            combat["actions_used"].append(actor)
    else:
        slot["remaining"] -= 1
    if resource == "bonus":
        r["bonus_action_spent"] = True
    session._sync_combat_participant_records(session.world_state["combat"])


def use_species_bonus(session, ability):
    validate_actor(session)
    r = ensure(session)["player"]
    if ability not in bonus_rules(session, "player") or r["bonus_action_spent"]:
        fail("bonus_action_unavailable", "No available Bonus Action grants this ability.")
    r["bonus_action_spent"] = True


@contextmanager
def executing(session, mode="hold", actor="player"):
    token = _execution.set((id(session), mode, actor))
    try:
        yield
    finally:
        _execution.reset(token)


def holding(session):
    return _execution.get() == (id(session), "hold", "player")


def attack_permission(session, actor):
    if _execution.get() in {(id(session), "reaction", actor), (id(session), "monster_capability", actor)}:
        validate_actor(session, actor, reaction=True)
    else:
        action_slot(session, actor, "attack")


def monster_resource(session, actor, source, kind, capability_id):
    """#04 owns generic slots; #07 owns only stat-block-specific counters."""
    from monster_capabilities import capabilities
    cap = next((c for c in capabilities(session, actor) if c["capability_id"] == capability_id), None)
    if not cap or cap["action_source"] != source:
        fail("capability_unavailable", "No authoritative monster capability grants this resource.")
    if source == "resistance":
        data = actor_data(session, actor)
        if data.get("current_hp", 0) <= 0 or data.get("combat_status") == "dead":
            fail("incapacitated", "A dead monster cannot use Legendary Resistance.")
    else:
        validate_actor(session, actor, reaction=source in {"reaction", "legendary"})
    resources = ensure(session)[actor]
    if source == "action":
        consume_action(session, actor, kind if kind in ACTION_TYPES else "feature")
    elif source == "bonus":
        if resources["bonus_action_spent"]:
            fail("bonus_action_spent", "The Bonus Action was already spent.")
        resources["bonus_action_spent"] = True
    elif source == "reaction":
        if resources["reaction_spent"]:
            fail("reaction_spent", "The Reaction was already spent.")
        resources["reaction_spent"] = True
    elif source not in {"legendary", "resistance"}:
        fail("invalid_resource_type", "Unknown monster action source.")
    if kind == "dodge":
        resources["dodging"] = True
    if kind == "disengage":
        resources["disengaging"] = True
    if kind == "dash":
        resources["dash_count"] += 1
        resources["movement_available"] += speed(session, actor)
    if kind == "multiattack":
        resources["attack_action"] = {"remaining_attacks": len(cap["attack_slots"]) - 1,
                                      "total_attacks": len(cap["attack_slots"]), "action_resource_cost": 1}


def monster_followup_complete(session, actor):
    r = ensure(session)[actor].get("attack_action")
    if not r or r["remaining_attacks"] <= 0:
        fail("no_attack_continuation", "No stat-block attack continuation remains.")
    r["remaining_attacks"] -= 1


def monster_routes(session, actor, kind):
    """Small endpoint-facts adapter, not pathfinding or a geometry engine.

    An existing/campaign positioning producer must supply known, clear routes.
    Route facts never come from a client or narration.
    """
    from monster_perception import relationship
    resources = ensure(session)[actor]
    routes = session.world_state.get("monster_routes", {}).get(actor, [])
    legal = []
    if not isinstance(routes, list) or len(routes) > 32:
        fail("invalid_movement_routes", "Routes must be a bounded canonical list.")
    for route in routes:
        if not isinstance(route, dict) or route.get("known") is not True or route.get("clear") is not True:
            continue
        if not isinstance(route.get("route_id"), str) or not isinstance(route.get("destination"), str):
            continue
        distance = route.get("distance_ft")
        if type(distance) is not int or distance <= 0:
            continue
        mode = route.get("mode", "walk")
        if mode != "walk":
            continue  # A special-movement owner must supply its validated adapter.
        multiplier = 1 + int("prone" in conditions(session, actor)) + int(route.get("difficult_terrain") is True)
        limit = movement_limit(session, actor) + (speed(session, actor) if kind == "dash" else 0)
        if speed(session, actor) <= 0 or resources["movement_used"] + distance * multiplier > limit:
            continue
        distances = route.get("target_distances")
        starts = route.get("start_distances")
        if (not isinstance(distances, dict) or not distances
                or not isinstance(starts, dict) or set(starts) != set(distances)):
            continue
        # An omitted hostile is not evidence of a safe crossing. Require its
        # canonical start/end facts; do not infer geometry or create an OA owner.
        required = {
            target for target in session.world_state["combat"]["participants"]
            if target != actor and relationship(session, actor, target) == "enemy"
        }
        if not required.issubset(distances):
            continue
        if "frightened" in conditions(session, actor):
            fear = actor_data(session, actor).get("frightened_by")
            if (fear not in starts or type(starts[fear]) not in (float, int)
                    or type(distances[fear]) not in (float, int) or distances[fear] < starts[fear]):
                continue  # No source/distance evidence means no legal native route.
        valid = True
        for target, new_distance in distances.items():
            if target not in session.world_state["combat"]["participants"] or target == actor:
                valid = False
                break
            if type(new_distance) not in (float, int) or not 0 <= new_distance < 100000:
                valid = False
                break
            try:
                old = weapon_attack.pair(session, actor, target)["distance_ft"]
            except CombatRequestError:
                valid = False
                break
            if starts[target] != old:
                valid = False
                break
            if abs(new_distance - old) > distance:
                valid = False
                break
            if (old <= 5 < new_distance and relationship(session, actor, target) == "enemy"
                    and not ensure(session)[target]["reaction_spent"] and kind != "disengage"):
                valid = False  # Missing OA resolver is not permission to escape freely.
                break
        if valid:
            legal.append(copy.deepcopy(route))
    return legal


def resolve_monster_route(session, actor, route_id, kind):
    route = next((r for r in monster_routes(session, actor, kind) if r["route_id"] == route_id), None)
    if route is None:
        fail("movement_unavailable", "The authoritative route is unavailable.")
    # Dash has already been consumed/added by #04; avoid adding it a second time.
    multiplier = 1 + int("prone" in conditions(session, actor)) + int(route.get("difficult_terrain") is True)
    r = ensure(session)[actor]
    cost = route["distance_ft"] * multiplier
    if cost > movement_limit(session, actor) - r["movement_used"]:
        fail("movement_unavailable", "Movement exceeds the legal budget.")
    r["movement_used"] += cost
    r["movement_available"] = max(r["movement_available"], r["movement_used"])
    pairs = session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
    for key in list(pairs):
        if actor in key.split("|"):
            del pairs[key]  # Endpoint facts replace, never retain stale geometry.
    for target, distance in route["target_distances"].items():
        pairs[f"{actor}|{target}"] = {"distance_ft": distance}
        if target == "player":
            actor_data(session, actor)["distance_ft"] = distance
    actor_data(session, actor)["position"] = route["destination"]
    import bounded_encounter
    bounded_encounter.refresh(session)
    publish_event(session, "actor_moves", actor)
    return {"kind": "move", "distance_ft": route["distance_ft"], "movement_cost_ft": cost,
            "destination": route["destination"], "movement_intent": route.get("movement_intent", "REPOSITION")}


def target(session, identity):
    combat = session.world_state["combat"]
    values = [n for n in session.active_npcs() if n.get("id") == identity]
    if (len(values) != 1 or identity not in combat["participants"]
        or values[0].get("combat_status", "active") not in {"active", "unconscious"}):
        fail("invalid_combat_target", "Select a targetable local combat participant.")
    return values[0]


def move(session, actor, distance):
    validate_actor(session, actor)
    if type(distance) is not int or distance < 1:
        fail("invalid_movement", "Movement needs a positive integer distance in feet.")
    r = ensure(session)[actor]
    multiplier = 2 if actor_data(session, actor).get("prone") or "prone" in conditions(session, actor) else 1
    cost = distance * multiplier
    if speed(session, actor) <= 0 or cost > movement_limit(session, actor) - r["movement_used"]:
        fail("movement_unavailable", "Movement exceeds the current legal budget.")
    r["movement_used"] += cost
    r["movement_available"] = max(r["movement_used"], movement_limit(session, actor))
    import bounded_encounter
    bounded_encounter.unlocated_move(session, actor)
    publish_event(session, "actor_moves", actor)
    return {"kind": "move", "distance_ft": distance, "movement_cost_ft": cost}


def dash(session, actor="player", resource="action"):
    if resource == "bonus" and actor == "player" and "adrenaline_rush" in bonus_rules(session, actor):
        before = ensure(session)[actor]["movement_available"]
        try:
            result = session.resolve_species_trait_action("adrenaline_rush")
        except ValueError as error:
            fail("invalid_species_action", str(error))
        return {"kind": "dash", "resource": "bonus", "source": "adrenaline_rush",
                "movement_added_ft": ensure(session)[actor]["movement_available"] - before,
                "feature_result": result}
    action_slot(session, actor, "dash", resource)
    added = speed(session, actor)
    consume_action(session, actor, "dash", resource)
    r = ensure(session)[actor]
    r["dash_count"] = r.get("dash_count", 0) + 1
    r["movement_available"] = max(r["movement_used"], movement_limit(session, actor))
    return {"kind": "dash", "movement_added_ft": added, "resource": resource}


def prepare_ready(session, actor, trigger, response):
    action_slot(session, actor, "ready")
    if (not isinstance(trigger, dict) or set(trigger) != {"event", "actor_id"}
        or trigger["event"] not in {"actor_moves", "actor_attacks"}
        or trigger["actor_id"] not in session.world_state["combat"]["participants"]):
        fail("invalid_ready_trigger", "Ready needs one supported perceivable combat event.")
    actor_data(session, trigger["actor_id"])
    if not isinstance(response, dict):
        fail("invalid_ready_response", "Ready needs one Action or movement response.")
    if response.get("kind") == "attack" and set(response) == {"kind", "target_id"}:
        target(session, response["target_id"])
        if not session.find_weapon_in_inventory("Kılıç")[0]:
            fail("no_weapon", "No configured weapon is available.")
    elif response.get("kind") == "move" and set(response) == {"kind", "distance_ft"}:
        cost = response["distance_ft"] if type(response["distance_ft"]) is int else 0
        if actor_data(session, actor).get("prone") or "prone" in conditions(session, actor):
            cost *= 2
        if type(response["distance_ft"]) is not int or not 0 < cost <= speed(session, actor):
            fail("invalid_ready_response", "Readied movement cannot exceed Speed.")
    else:
        fail("invalid_ready_response", "This Ready response has no configured mechanic.")
    consume_action(session, actor, "ready")
    r = ensure(session)[actor]
    r["ready"] = {"trigger": copy.deepcopy(trigger), "response": copy.deepcopy(response),
                  "spell_metadata": None}
    r["opportunity"] = None
    return {"kind": "ready", "ready": copy.deepcopy(r["ready"])}


def prepare_spell_hook(session, actor, trigger, spell_metadata):
    """Future spell engine hook; no spell casting or concentration resolution."""
    action_slot(session, actor, "ready")
    if (not isinstance(spell_metadata, dict) or not spell_metadata.get("spell_id")
        or spell_metadata.get("casting_action") != "action"
        or not isinstance(trigger, dict) or set(trigger) != {"event", "actor_id"}
        or trigger["event"] not in {"actor_moves", "actor_attacks"}
        or trigger["actor_id"] not in session.world_state["combat"]["participants"]):
        fail("invalid_ready_spell_metadata", "A future spell engine must supply authoritative Action-based metadata.")
    consume_action(session, actor, "ready")
    ensure(session)[actor]["ready"] = {
        "trigger": copy.deepcopy(trigger), "response": {"kind": "magic"},
        "spell_metadata": copy.deepcopy(spell_metadata),
    }


def publish_event(session, event, actor):
    """Only called after an actual Python-resolved action, never from HTTP."""
    if not session.world_state["combat"]["active"]:
        return
    for owner, r in ensure(session).items():
        ready = r["ready"]
        if (ready and not r["reaction_spent"] and can_act(session, owner)
            and ready["trigger"] == {"event": event, "actor_id": actor}):
            r["opportunity"] = {"id": str(uuid4()), "event": event, "actor_id": actor}
    monster_event(session, event, actor)


def monster_event(session, kind, actor, **verified):
    """Mechanic owners publish actual boundaries/effects, never HTTP fields."""
    combat = session.world_state["combat"]
    if not combat["active"]:
        return []
    allowed = {"actor_moves", "actor_attacks", "after_turn", "failed_save", "incoming_hit"}
    if kind not in allowed or actor not in combat["participants"]:
        fail("invalid_monster_event", "Invalid authoritative monster trigger.")
    counter = combat.get("monster_event_counter", 0) + 1
    combat["monster_event_counter"] = counter
    combat["monster_event"] = {"event_id": f"{combat['combat_id']}:{counter}",
                             "kind": kind, "actor_id": actor, **copy.deepcopy(verified)}
    if kind == "failed_save":
        return []  # Saving-throw owner queries the affected creature explicitly.
    import monster_combat
    outcomes = monster_combat.after_event(session)
    if outcomes:
        queue = session.world_state.setdefault("monster_interrupt_results", [])
        queue.extend(copy.deepcopy(outcomes))
        if len(queue) > 4096:
            fail("too_many_monster_interrupts", "The bounded interrupt result buffer is full.")
    return outcomes


def pending_reaction(session):
    if not session.world_state.get("combat", {}).get("active"):
        return False
    return bool(ensure(session)["player"]["opportunity"])


def react(session, opportunity_id, actor="player"):
    validate_actor(session, actor, reaction=True)
    r = ensure(session)[actor]
    if (r["reaction_spent"] or not r["ready"] or not r["opportunity"]
        or r["opportunity"]["id"] != opportunity_id):
        fail("invalid_reaction_trigger", "No matching authoritative reaction opportunity.")
    response = r["ready"]["response"]
    if response["kind"] == "magic":
        fail("spell_mechanic_unavailable", "Spell resolution is outside this lock.")
    if response["kind"] == "attack":
        npc = target(session, response["target_id"])
        weapon, data = session.find_weapon_in_inventory(session.world_state.get("equipment", {}).get("main_hand"))
        if not weapon:
            fail("no_weapon", "No configured weapon is available.")
        with executing(session, "reaction", actor):
            result = session.resolve_attack("Saldırıyorum.", weapon, data, npc, origin="reaction")
    else:
        distance = response["distance_ft"]
        cost = distance * (2 if actor_data(session, actor).get("prone") or "prone" in conditions(session, actor) else 1)
        if cost > speed(session, actor) or speed(session, actor) == 0:
            fail("movement_unavailable", "Readied movement is no longer legal.")
        # Same ledger, restricted one-response movement grant, no leftover grant.
        r["ready_movement_grant"] = r.get("ready_movement_grant", 0) + cost
        r["movement_used"] += cost
        r["movement_available"] = max(r["movement_used"], movement_limit(session, actor))
        import bounded_encounter
        bounded_encounter.unlocated_move(session, actor)
        result = {"kind": "move", "distance_ft": distance, "movement_cost_ft": cost}
    r["reaction_spent"] = True
    r["ready"] = None
    r["opportunity"] = None
    session._combat_end_if_decided()
    return {"kind": "react", "response": result}


def projection(session):
    if not session.world_state["combat"]["active"]:
        return None
    rows = {}
    for actor, r in ensure(session).items():
        able = can_act(session, actor)
        current = session.world_state["combat"]["current_actor_id"] == actor
        rows[actor] = {
            **copy.deepcopy(r), "speed_ft": speed(session, actor),
            "action_available": able and current and (not r["base_action_spent"] or any(g["remaining"] for g in r["additional_actions"])),
            "bonus_action_available": able and current and not r["bonus_action_spent"] and bool(bonus_rules(session, actor) or any(g["remaining"] for g in r["bonus_grants"])),
            "bonus_rules": bonus_rules(session, actor),
            "reaction_available": able and not r["reaction_spent"],
            "effective_movement_available": movement_limit(session, actor),
            "movement_remaining": max(0, movement_limit(session, actor) - r["movement_used"]) if able and speed(session, actor) else 0,
            "legal_actions": [],
        }
        for kind in sorted(ACTION_TYPES):
            reason = None
            try:
                action_slot(session, actor, kind)
                if kind not in {"attack", "dash", "ready"}:
                    reason = "Action-specific mechanic not connected by this lock."
            except CombatRequestError as error:
                reason = str(error)
            rows[actor]["legal_actions"].append({"kind": kind, "legal": reason is None, "reason": reason})
    return {"actors": rows}


def movement_limit(session, actor):
    r = ensure(session)[actor]
    return speed(session, actor) * (1 + r.get("dash_count", 0)) + r.get("ready_movement_grant", 0)


def attack_step(session, identity, continuation=False, *, weapon_id=None, choice=None, origin=None):
    validate_actor(session)
    r = ensure(session)["player"]
    ongoing = r.get("attack_action")
    origin = origin or ("continuation" if continuation else "action")
    extra = origin in {"light", "nick"}
    if continuation:
        if not ongoing or ongoing["remaining_attacks"] <= 0:
            fail("no_attack_continuation", "No rule-granted attack remains inside this Attack Action.")
    elif not extra:
        slot = action_slot(session, "player", "attack")
        limit = (slot["restrictions"].get("max_attacks", 1) if slot else
                 actor_data(session, "player").get("attacks_per_action", 1))
        if type(limit) is not int or limit < 1:
            fail("invalid_attack_allowance", "Invalid server-defined attacks-per-Action.")
    npc = target(session, identity)
    selected = weapon_id or session.world_state.get("equipment", {}).get("main_hand")
    weapon, data = session.find_weapon_in_inventory(selected)
    if any(isinstance(item, dict) and item.get("item_id") == selected for item in session.world_state["inventory"]):
        choice = {**(choice or {}), "weapon_instance_id": selected}
    if weapon_id == "unarmed":
        weapon, data = "unarmed", None
    if not weapon:
        fail("no_weapon", "No configured weapon is available.")
    result = session.resolve_attack("Saldırıyorum.", weapon, data, npc,
                                   attack_choice=choice, origin=origin)
    if continuation:
        ongoing["remaining_attacks"] -= 1
    elif extra:
        if origin == "light":
            # The Light rule grants this Bonus Action; #04 remains its owner.
            r["bonus_action_spent"] = True
    else:
        consume_action(session, "player", "attack")
        r["attack_action"] = {"remaining_attacks": limit - 1, "total_attacks": limit,
                              "action_resource_cost": 1}
    session._combat_end_if_decided()
    publish_event(session, "actor_attacks", "player")
    return {"kind": "attack", "continuation": continuation, "result": result,
            "action_resource_cost": 0 if continuation or extra else 1}


def natural_command(session, message, selected_target=None):
    """Small extension of existing intent routing, not a second model parser."""
    if not session.world_state.get("combat", {}).get("active"):
        return None
    text = session._normalize_turkish_typos(message)
    opportunity = ensure(session)["player"]["opportunity"]
    if opportunity and re.search(r"reaksiyon.*(?:kullan|ver)|use.*reaction", text):
        return {"steps": [{"kind": "react", "opportunity_id": opportunity["id"]}]}
    if opportunity and re.search(r"reaksiyon.*(?:atla|vazgec)|decline.*reaction", text):
        return {"steps": [{"kind": "decline_reaction", "opportunity_id": opportunity["id"]}]}
    if text in {"turumu bitiriyorum", "turumu bitir", "end turn", "sirami bitiriyorum"}:
        return {"steps": [{"kind": "end_turn"}]}
    if re.search(r"\b(?:nick|bonus|ekstra|extra)\b", text) and (
        session._has_explicit_attack_verb(text) or "attack" in text
    ):
        weapon, choice = weapon_attack.natural_choice(session, message)
        origin = "nick" if "nick" in text else "light"
        return {"steps": [{"kind": "attack", "target_id": selected_target or session.world_state["combat"]["target_id"],
                           "weapon_id": weapon, "attack_choice": choice, "attack_origin": origin}]}
    if "ready" in text or "hazir bekliyorum" in text:
        found = session.resolve_npc_reference(message)
        identity = selected_target or (found["npc"]["id"] if found["status"] == "found" else None)
        event = "actor_attacks" if re.search(r"saldirirsa|attacks", text) else (
            "actor_moves" if re.search(r"hareket ederse|moves", text) else None)
        if identity and event and re.search(r"saldiracagim|\battack\b", text):
            return {"steps": [{"kind": "ready", "trigger": {"event": event, "actor_id": identity},
                               "response": {"kind": "attack", "target_id": identity}}]}
        distance = re.search(r"\b(\d+)\s*(?:feet|ft|fit)\b", text)
        if identity and event and distance and re.search(r"hareket|cekil|move|ilerl|geri|yuru", text):
            return {"steps": [{"kind": "ready", "trigger": {"event": event, "actor_id": identity},
                               "response": {"kind": "move", "distance_ft": int(distance[1])}}]}
        fail("ready_needs_trigger", "Ready needs one supported perceivable trigger and one configured response.")
    for unavailable in ACTION_TYPES - {"attack", "dash", "ready", "feature"}:
        if re.search(rf"\b{unavailable}\b", text):
            return {"steps": [{"kind": unavailable}]}
    steps = []
    for part in re.split(r"\b(?:sonra|ardindan|then)\b|[,;]", text):
        distance = re.search(r"\b(\d+)\s*(?:feet|ft|fit)\b", part)
        if distance and re.search(r"hareket|cekil|move|step|ilerl|geri|yuru", part):
            steps.append({"kind": "move", "distance_ft": int(distance[1])})
        elif "dash" in part or "depar" in part:
            steps.append({"kind": "dash", "resource": "bonus" if "bonus" in part else "action"})
        elif re.search(r"adrenalin|adrenaline", part):
            steps.append({"kind": "species", "ability": "adrenaline_rush"})
        elif session._has_explicit_attack_verb(part) and not session._is_explicitly_negated_attack(part):
            if not steps and not re.search(r"sonra|ardindan|then", text):
                continue  # Preserve existing single-attack compatibility.
            identity = selected_target
            if identity is None:
                found = session.resolve_npc_reference(message)
                if found["status"] == "found":
                    identity = found["npc"]["id"]
            steps.append({"kind": "attack", "target_id": identity})
        elif part.strip() and (steps or re.search(r"sonra|ardindan|then", text)):
            fail("unsupported_action_sequence", "This compound instruction needs a configured action.")
    return {"steps": steps} if steps else None


def execute(session, command, action_id=None, session_id=None):
    before_world = copy.deepcopy(session.world_state)
    before_character = copy.deepcopy(session.character)
    before_messages = copy.deepcopy(session.messages)
    before_rng = session.rng.getstate()
    try:
        return _execute(session, command, action_id, session_id)
    except Exception:
        session.world_state.clear()
        session.world_state.update(before_world)
        session.character.clear()
        session.character.update(before_character)
        session.messages[:] = before_messages
        session.rng.setstate(before_rng)
        raise


def _execute(session, command, action_id=None, session_id=None):
    """Structured/NL commands share the same mechanics and receipt transaction."""
    from api.core_resolution import resolution_action_scope
    steps = command.get("steps", [])
    if not 1 <= len(steps) <= 8:
        fail("invalid_action_sequence", "Provide between one and eight action steps.")
    session.ensure_combat_state()
    ensure(session)
    results = []
    combat_id = session.world_state["combat"].get("combat_id")
    with resolution_action_scope(action_id or str(uuid4()), session_id):
        for step in steps:
            kind = step["kind"]
            if step.get("resource", "action") == "bonus" and kind not in {"dash", "attack"}:
                fail("invalid_resource_type", "This action has no configured Bonus Action rule.")
            if pending_reaction(session) and kind not in {"react", "decline_reaction"}:
                fail("reaction_pending", "Resolve or decline the authoritative reaction opportunity.")
            if kind == "react":
                results.append(react(session, step.get("opportunity_id")))
                results[-1]["enemy_actions"] = []
                if session.world_state["combat"]["active"] and session.world_state["combat"]["current_actor_id"] != "player":
                    session.advance_combat_turn()
                    results[-1]["enemy_actions"] = session._resolve_enemy_turns_until_player()
            elif kind == "decline_reaction":
                r = ensure(session)["player"]
                if not r["opportunity"] or r["opportunity"]["id"] != step.get("opportunity_id"):
                    fail("invalid_reaction_trigger", "No matching reaction opportunity.")
                r["opportunity"] = None
                results.append({"kind": kind, "enemy_actions": []})
                if session.world_state["combat"]["current_actor_id"] != "player":
                    session.advance_combat_turn()
                    results[-1]["enemy_actions"] = session._resolve_enemy_turns_until_player()
            elif kind == "move":
                results.append(move(session, "player", step.get("distance_ft")))
            elif kind == "dash":
                results.append(dash(session, resource=step.get("resource", "action")))
            elif kind == "ready":
                results.append(prepare_ready(session, "player", step.get("trigger"), step.get("response")))
            elif kind in {"attack", "continue_attack"}:
                results.append(attack_step(
                    session, step.get("target_id"), kind == "continue_attack",
                    weapon_id=step.get("weapon_id"), choice=step.get("attack_choice"),
                    origin=step.get("attack_origin", "light" if step.get("resource") == "bonus" else None),
                ))
            elif kind == "species":
                with executing(session):
                    try:
                        result = session.resolve_species_trait_action(step.get("ability"), form=step.get("form"))
                    except ValueError as error:
                        fail("invalid_species_action", str(error))
                    results.append({"kind": kind, "result": result})
            elif kind == "magic":
                import spell_scope
                if not step.get("ability"):
                    fail("unsupported_action", "Action-specific mechanic is not configured.")
                if any(step.get(field) is not None for field in (
                    "form", "weapon_id", "attack_choice", "attack_origin", "distance_ft",
                    "trigger", "response", "opportunity_id",
                )):
                    fail("unsupported_spell_mode", "Magic accepts only an ability name and one creature target.")
                results.append({"kind": kind, "result": spell_scope.cast(
                    session, step.get("ability"), step.get("target_id"),
                )})
            elif kind == "end_turn":
                if (not session.world_state["combat"]["active"]
                    or session.world_state["combat"]["current_actor_id"] != "player"
                    or session.character.get("current_hp", 0) <= 0):
                    fail("out_of_turn", "End Turn cannot skip another actor or a scheduled death save.")
                effects = session._finish_species_player_turn()
                session.advance_combat_turn()
                enemies = session._resolve_enemy_turns_until_player()
                results.append({"kind": kind, "species_effects": effects, "enemy_actions": enemies})
            else:
                fail("unsupported_action", "Action-specific mechanic is not configured.")
    if session.world_state["combat"]["active"]:
        session._sync_combat_participant_records(session.world_state["combat"])
    session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
    narration_parts = []
    for step in results:
        if step["kind"] == "magic":
            narration_parts.append(spell_scope.narration(step["result"]))
        elif step["kind"] in {"end_turn", "react", "decline_reaction"}:
            narration_parts.append(session._combat_narration({
                "outcome": step["kind"],
                "enemy_actions": step["enemy_actions"],
                "combat": {
                    "player_combat_status": session.world_state["player_combat_status"],
                    "player_current_hp": session.character["current_hp"],
                    "player_max_hp": session.character["max_hp"],
                },
            }))
    return {
        "messages": session.messages,
        "narration": " ".join(narration_parts) or "Python doğrulamasıyla hamle çözüldü.",
        "action_result": {"action": "action_economy", "status": "resolved", "success": True,
                          "combat_id": combat_id, "economy_steps": results},
        "action_economy_result": {"combat_id": combat_id, "steps": results, "state": projection(session)},
        "model_calls": 0,
    }
