"""Python Monster Combat decisions around the existing mechanical owners.

DMG 2024 pp. 48, 116-117: contextual fight/flight, personality, relationships.
MM 2024 pp. 8-10: stat-block actions, resources, exact Multiattack.
No model calls, damage/save implementation, new initiative or movement engine.
"""
import copy
import re

import action_economy as economy
import initiative
import weapon_attack as attacks
import monster_capabilities as caps
import monster_perception as perception
from combat_lifecycle import CombatRequestError


def fail(code, message):
    raise CombatRequestError(code, message, 400)


def turn_id(session, actor):
    c = session.world_state["combat"]
    counter = c.get("turn_resources", {}).get(actor, {}).get("attack_turn_counter", 0)
    return f"{c['combat_id']}:{c['round']}:{actor}:{counter}"


def state(session, actor):
    npc = attacks.actor_data(session, actor)
    c = session.world_state["combat"]
    root = session.world_state.setdefault("monster_combat", {})
    if root.get("combat_id") != c["combat_id"]:
        root.clear()
        root.update(combat_id=c["combat_id"], actors={})
    return root["actors"].setdefault(actor, {
        "personality": npc.get("personality", "neutral"),
        "role": npc.get("tactical_role", "basic"),
        "objective": copy.deepcopy(npc.get("combat_objective")),
        "relationships": copy.deepcopy(npc.get("monster_relationships", {})),
        "observations": {}, "last_known": {}, "resources": {},
        "recent": [], "last_turn_result": None, "started_turn": None,
        "last_window_result": None,
    })


def initialize_resources(session, actor, memory, capabilities):
    block = attacks.actor_data(session, actor).get("monster_stat_block", {})
    if memory["role"] == "basic":
        profiles = [c.get("profile", {}) for c in capabilities if c["kind"] == "attack"]
        if any(p.get("kind") == "ranged" for p in profiles):
            memory["role"] = "artillery"
    for cap in capabilities:
        r = memory["resources"].setdefault(cap["capability_id"], {})
        if cap.get("recharge"):
            r.setdefault("available", True)
        if "uses" in cap:
            r.setdefault("remaining", cap["uses"])
    if any(c["action_source"] == "legendary" for c in capabilities):
        limit = block.get("legendary_uses")
        if block.get("in_lair") is True and "lair_legendary_uses" in block:
            limit = block["lair_legendary_uses"]
        caps.number(limit, "Legendary Action uses", 1)
        memory.setdefault("legendary_remaining", limit)


def begin_turn(session, actor):
    if actor == "player":
        return
    capabilities = caps.capabilities(session, actor)
    memory = state(session, actor)
    initialize_resources(session, actor, memory, capabilities)
    identity = turn_id(session, actor)
    if memory["started_turn"] == identity:
        return
    if session.world_state["combat"]["current_actor_id"] != actor:
        fail("out_of_turn", "Recharge requires the monster's start-of-turn boundary.")
    memory["started_turn"] = identity
    memory["recharge_rolls"] = []
    for cap in capabilities:
        r = memory["resources"][cap["capability_id"]]
        if cap.get("recharge") and not r["available"]:
            roll = session.rng.randint(1, 6)
            r["available"] = cap["recharge"][0] <= roll <= cap["recharge"][1]
            memory["recharge_rolls"].append({"capability_id": cap["capability_id"], "roll": roll})
    block = attacks.actor_data(session, actor).get("monster_stat_block", {})
    if "legendary_remaining" in memory:
        memory["legendary_remaining"] = block.get("lair_legendary_uses", block["legendary_uses"]) \
            if block.get("in_lair") is True else block["legendary_uses"]
    memory["legendary_option_uses"] = {}


def restore_resources(session, actor, rest):
    """Rest owner must call explicitly; no per-round or wall-clock restoration."""
    if rest not in {"short_rest", "long_rest"}:
        fail("invalid_rest", "Only authoritative rest boundaries restore abilities.")
    memory = state(session, actor)
    for cap in caps.capabilities(session, actor):
        r = memory["resources"].get(cap["capability_id"], {})
        if cap.get("recharge"):
            r["available"] = True
        if "uses" in cap and (cap["restore"] == rest or rest == "long_rest" and cap["restore"] == "short_rest"):
            r["remaining"] = cap["uses"]


def available(session, actor, memory, cap, source):
    if cap["action_source"] != source:
        return False
    resources = economy.ensure(session)[actor]
    if source == "action":
        try:
            economy.action_slot(session, actor, cap["kind"] if cap["kind"] in economy.ACTION_TYPES else "feature")
        except CombatRequestError:
            return False
    elif source == "bonus" and resources["bonus_action_spent"]:
        return False
    elif source == "reaction" and resources["reaction_spent"]:
        return False
    r = memory["resources"].get(cap["capability_id"], {})
    if cap.get("recharge") and r.get("available") is not True:
        return False
    if "uses" in cap and r.get("remaining", 0) <= 0:
        return False
    if source == "legendary":
        if memory.get("legendary_remaining", 0) < cap.get("cost", 1):
            return False
        if memory.get("legendary_option_uses", {}).get(cap["capability_id"], 0) >= cap.get("per_turn_limit", 99):
            return False
    data = attacks.actor_data(session, actor)
    conditions = attacks.conditions(session, actor, data)
    if cap.get("requires_bloodied") and data["current_hp"] > data["max_hp"] / 2:
        return False
    if not set(cap.get("requires_conditions", [])).issubset(conditions):
        return False
    if set(cap.get("forbidden_conditions", [])) & conditions:
        return False
    return True


def legal_attack(session, actor, target, cap):
    try:
        # Selection is read-only and uses #06's real legality checks.
        with economy.executing(session, "monster_capability", actor):
            return attacks.prepare(session, actor, target, cap.get("weapon_id"), cap.get("choice"),
                                   profile=cap.get("profile"))
    except CombatRequestError:
        return None


def target_score(session, actor, target, memory):
    data = attacks.actor_data(session, actor)
    score = 60 - min(30, (target["distance_ft"] or 0) / 5)
    intelligence = data.get("intelligence", 0)
    if intelligence >= 8:
        score += min(24, target["threat"] * 2)
    if target["downed"]:
        active_threat = any(not t["downed"] for t in memory.get("perceived_targets", []))
        score -= 55 if active_threat else 20
        if data.get("cruel") is True or memory["role"] == "assassin":
            score += 35
        if (memory["objective"] or {}).get("kind") == "capture":
            score -= 100
    objective = memory["objective"] or {}
    if objective.get("target_id") == target["id"] and objective.get("kind") == "eliminate":
        score += 45
    if memory.get("coordinated_target") == target["id"]:
        score += 12
    observed = memory["observations"].get(target["id"], {})
    if objective.get("kind") == "protect_leader" and observed.get("attacked_id") == objective.get("leader_id"):
        score += 35
    if objective.get("kind") in {"guard_objective", "protect_treasure", "hold_position"}:
        fact = session.world_state.get("monster_perception", {}).get(actor, {}).get(target["id"], {})
        if fact.get("near_objective") is True:
            score += 30
    return score


def morale(session, actor, view, memory):
    data = attacks.actor_data(session, actor)
    bloodied = data["current_hp"] <= data["max_hp"] / 2
    loss = sum(bool(set(a["conditions"]) & {"unconscious", "incapacitated", "paralyzed", "stunned", "dead"})
               for a in view["allies"])
    opponents_lost = any(t["downed"] for t in view["targets"])
    severe = bloodied and ("frightened" in view["conditions"]
                           or bool(view["allies"]) and loss > len(view["allies"]) / 2 and not opponents_lost)
    personality = memory["personality"]
    if personality == "fanatical" or memory["objective"] and memory["objective"].get("kind") == "hold_at_all_costs":
        return 0
    pressure = (60 if severe else 18 if bloodied else 0)
    if personality == "cowardly":
        pressure += 35 if bloodied else 5
    if personality in {"brave", "boastful"}:
        pressure -= 30
    if memory["objective"] and memory["objective"].get("kind") == "escape":
        pressure += 55
    leader = (memory["relationships"] or {}).get("leader_id")
    if leader and any(a["id"] == leader and set(a["conditions"]) & {"unconscious", "dead"} for a in view["allies"]):
        if memory["relationships"].get("leader_response") == "panic":
            pressure += 30
        elif memory["relationships"].get("leader_response") == "frenzy":
            pressure -= 50
    return max(0, pressure)


def candidates(session, actor, memory, capabilities, view, source="action", event=None):
    results = []
    memory["perceived_targets"] = view["targets"]  # transient, removed before persistence
    pressure = morale(session, actor, view, memory)
    data = attacks.actor_data(session, actor)
    by_id = {c["capability_id"]: c for c in capabilities}
    leader = (memory["relationships"] or {}).get("leader_id")
    memory["coordinated_target"] = perception.communicate(session, actor, leader, view) if leader else None
    for cap in capabilities:
        if not available(session, actor, memory, cap, source):
            continue
        if source == "reaction" and (not event or cap["trigger"] != event["kind"]):
            continue
        if cap["kind"] in {"attack", "multiattack"}:
            berserk = data.get("monster_stat_block", {}).get("behavior_constraint")
            possible_targets = view["targets"] + view["allies"] if berserk == "nearest_creature" else view["targets"]
            for target in possible_targets:
                if "charmed" in view["conditions"] and data.get("charmed_by") == target["id"]:
                    continue
                if "dead" in target["conditions"]:
                    continue
                if cap.get("target_restriction") == "trigger_actor" and (not event or target["id"] != event["actor_id"]):
                    continue
                combinations = caps.sequences(cap, capabilities) if cap["kind"] == "multiattack" else [[cap["capability_id"]]]
                for seq in combinations:
                    if any(not legal_attack(session, actor, target["id"], by_id[a]) for a in seq):
                        continue
                    score = target_score(session, actor, target, memory) + 12 * (len(seq) - 1)
                    score += sum(min(12, (by_id[a].get("profile", {}).get("damage_die", 0) + 1)
                                     * by_id[a].get("profile", {}).get("damage_dice", 0) / 6)
                                 for a in seq)
                    damage_types = [by_id[a].get("profile", {}).get("damage_type") for a in seq]
                    if data.get("intelligence", 0) >= 8:
                        score -= 18 * sum(target["beliefs"].get(t) in {"suspected_resistant", "known_immune"} for t in damage_types)
                    if berserk == "nearest_creature":
                        nearest = min(t["distance_ft"] for t in possible_targets if t["distance_ft"] is not None)
                        if target["distance_ft"] != nearest:
                            continue
                        score += 100
                    results.append({"capability_id": cap["capability_id"], "target_ids": [target["id"]],
                                    "attack_sequence": seq, "score": score, "reason_code": "ENGAGE_THREAT"})
            continue
        if cap["kind"] == "dodge":
            results.append({"capability_id": cap["capability_id"], "target_ids": [],
                            "score": 8 + min(30, pressure / 3), "reason_code": "DEFEND_POSITION"})
        elif cap["kind"] in {"dash", "disengage"}:
            for route in economy.monster_routes(session, actor, cap["kind"]):
                movement = route.get("movement_intent", "REPOSITION")
                score = pressure + 15 if movement == "RETREAT" else 35
                if memory["role"] == "artillery" and movement == "MAINTAIN_RANGE":
                    score += 30
                if movement in {"PROTECT_LEADER", "GUARD_OBJECTIVE"} and memory["objective"]:
                    score += 35
                if movement == "CLOSE_DISTANCE" and not any(
                    legal_attack(session, actor, t["id"], c) for t in view["targets"]
                    for c in capabilities if c["kind"] == "attack"
                ):
                    score += 30
                results.append({"capability_id": cap["capability_id"], "target_ids": [],
                                "route_id": route["route_id"], "movement_intent": movement,
                                "destination": route["destination"], "score": score,
                                "reason_code": "ESCAPE_MORALE" if movement == "RETREAT" else "TACTICAL_POSITION"})
        elif cap["kind"] == "influence":
            if data.get("intelligence", 0) >= 4 and data.get("languages") and pressure >= 45:
                for proposal in ("PARLEY_PROPOSED", "SURRENDER_PROPOSED"):
                    results.append({"capability_id": cap["capability_id"], "target_ids": [],
                                    "proposal": proposal, "score": pressure, "reason_code": "SEEK_TERMS"})
        else:
            adapter = caps.executor(session, cap["kind"])
            if adapter is None:
                continue
            # Owner supplies bounded legal options, geometry and spell availability.
            intents = adapter[0](session, actor, copy.deepcopy(cap), copy.deepcopy(view))
            if not isinstance(intents, list) or len(intents) > 64:
                fail("invalid_owner_options", "Owner options must be bounded.")
            for intent in intents:
                if not isinstance(intent, dict) or "score" in intent:
                    fail("invalid_owner_options", "Owner provides legality, never tactical scores.")
                targets = intent.get("target_ids", [])
                known = {t["id"] for t in view["targets"] + view["allies"]} | {actor}
                if not set(targets).issubset(known):
                    continue
                if cap["kind"] == "spell" and intent.get("spell_id") not in cap["spell_ids"]:
                    continue
                score = 50
                if cap.get("powerful") and targets:
                    score += 35
                if intent.get("harmful", cap.get("harmful", cap["kind"] in {"special", "spell"})):
                    if "charmed" in view["conditions"] and data.get("charmed_by") in targets:
                        continue
                    allies = {t["id"] for t in view["allies"]} | {actor}
                    score -= 45 * len(set(targets) & allies)
                if intent.get("movement_intent") == "RETREAT":
                    score = pressure + 15
                if intent.get("movement_intent") == "CLOSE_DISTANCE" and not any(
                    legal_attack(session, actor, t["id"], c) for t in view["targets"]
                    for c in capabilities if c["kind"] == "attack"
                ):
                    score += 25
                if intent.get("movement_intent") in {"PROTECT_LEADER", "GUARD_OBJECTIVE"} and memory["objective"]:
                    score += 25
                results.append({**copy.deepcopy(intent), "capability_id": cap["capability_id"],
                                "score": score, "reason_code": "USE_POWERFUL_ABILITY" if cap.get("powerful") else "TACTICAL_POSITION"})
    memory.pop("perceived_targets", None)
    memory.pop("coordinated_target", None)
    if results and memory["recent"]:
        last = memory["recent"][-1]
        for candidate in results:
            if (candidate["capability_id"] == last["capability_id"]
                    and candidate.get("target_ids", []) == last["target_ids"]):
                candidate["score"] -= 2
    return results


def choose(session, candidates, memory, *, deterministic=False):
    if not candidates:
        return None, []
    best = max(c["score"] for c in candidates)
    viable = [c for c in candidates if c["score"] >= best - 8]
    viable.sort(key=lambda c: (c["capability_id"], str(c.get("target_ids")), str(c.get("attack_sequence")), str(c.get("proposal"))))
    if len(viable) == 1 or deterministic:
        return viable[0], []
    # Only near-equivalent choices; avoid superficial randomness and poor tactics.
    weights = [max(1, int(c["score"] - best + 10)) for c in viable]
    roll = session.rng.randint(1, sum(weights))
    position = roll
    for candidate, weight in zip(viable, weights):
        position -= weight
        if position <= 0:
            return candidate, [{"purpose": "decision", "roll": roll, "range": [1, sum(weights)]}]
    raise RuntimeError("Weighted decision failed.")


def spend_specific(memory, cap):
    r = memory["resources"][cap["capability_id"]]
    if cap.get("recharge"):
        r["available"] = False
    if "uses" in cap:
        r["remaining"] -= 1
    if cap["action_source"] == "legendary":
        memory["legendary_remaining"] -= cap.get("cost", 1)
        used = memory.setdefault("legendary_option_uses", {})
        used[cap["capability_id"]] = used.get(cap["capability_id"], 0) + 1


def execute(session, actor, selected, capabilities, memory, view, source, event=None):
    cap = next(c for c in capabilities if c["capability_id"] == selected["capability_id"])
    # Revalidate without RNG. A stale capability does not consume any resource.
    newly_legal = candidates(session, actor, memory, capabilities, view, source, event)
    signature = lambda c: {k: v for k, v in c.items() if k not in {"score", "reason_code"}}
    if not any(signature(c) == signature(selected) for c in newly_legal):
        selected, _ = choose(session, newly_legal, memory, deterministic=True)
        if selected is None:
            return [], {"decision_type": "NO_ACTION", "reason_code": "STALE_OPTIONS"}
        cap = next(c for c in capabilities if c["capability_id"] == selected["capability_id"])
    economy.monster_resource(session, actor, source, cap["kind"], cap["capability_id"])
    outcomes = []
    if cap["kind"] in {"attack", "multiattack"}:
        by_id = {c["capability_id"]: c for c in capabilities}
        for index, identity in enumerate(selected["attack_sequence"]):
            target = selected["target_ids"][0]
            if "dead" in attacks.conditions(session, target, attacks.actor_data(session, target)):
                break
            attack = by_id[identity]
            with economy.executing(session, "monster_capability", actor):
                result = attacks.resolve(session, actor, target, attack.get("weapon_id"), attack.get("choice"),
                                         profile=attack.get("profile"), origin="action" if index == 0 else "continuation")
            if index:
                economy.monster_followup_complete(session, actor)
            outcomes.append(result)
    elif cap["kind"] == "influence":
        proposals = memory.setdefault("proposals", [])
        proposal = {"proposal_id": turn_id(session, actor) + ":" + selected["proposal"],
                    "type": selected["proposal"], "status": "pending", "actor_id": actor}
        proposals.append(proposal)
        del proposals[:-8]
        outcomes.append(public_result(session, actor, selected["proposal"].lower()))
    elif cap["kind"] == "dodge":
        outcomes.append(public_result(session, actor, "dodge"))
    elif cap["kind"] in {"dash", "disengage"}:
        movement = economy.resolve_monster_route(session, actor, selected["route_id"], cap["kind"])
        outcome = "flee_declared" if selected["movement_intent"] == "RETREAT" else cap["kind"]
        result = public_result(session, actor, outcome)
        result["target_name"] = movement["destination"]
        outcomes.append(result)
    else:
        adapter = caps.executor(session, cap["kind"])
        result = adapter[1](session, actor, copy.deepcopy(cap), copy.deepcopy(selected))
        if not isinstance(result, dict) or result.get("status") not in {"resolved", "handoff"}:
            fail("invalid_owner_result", "A mechanic owner must return a verified result.")
        if result["status"] == "handoff":
            # No spell/movement/effect results or resources are fabricated.
            fail("owner_not_implemented", "The chosen mechanic cannot yet be resolved.")
        outcomes.append(result)
    spend_specific(memory, cap)
    metadata = {k: copy.deepcopy(v) for k, v in selected.items() if k != "score"}
    decision_type = "FLEE_DECLARED" if selected.get("movement_intent") == "RETREAT" else selected.get("proposal", cap["kind"].upper())
    metadata.update(decision_type=decision_type, action_source=source,
                    resource_used=cap["capability_id"] if cap.get("recharge") or "uses" in cap else source)
    return outcomes, metadata


def window(session, actor, source):
    """Read a mechanic-owner-issued event, never a client-provided trigger."""
    if source not in {"reaction", "legendary", "resistance"}:
        fail("invalid_window", "Not a monster interrupt window.")
    with initiative.atomic(session):
        combat = session.world_state["combat"]
        event = combat.get("monster_event")
        if not combat["active"] or actor not in combat["participants"] or not event:
            fail("invalid_window", "No current canonical monster event.")
        memory = state(session, actor)
        key = f"{event['event_id']}:{actor}:{source}"
        previous = memory["last_window_result"]
        if previous and previous["window_id"] == key:
            return copy.deepcopy(previous)
        if source == "legendary" and (event["kind"] != "after_turn" or event["actor_id"] == actor):
            fail("invalid_window", "Legendary Actions occur only after another creature's turn.")
        if source == "resistance" and (event["kind"] != "failed_save" or event.get("target_id") != actor):
            fail("invalid_window", "Legendary Resistance needs this monster's actual failed save.")
        capabilities = caps.capabilities(session, actor)
        initialize_resources(session, actor, memory, capabilities)
        result = {"window_id": key, "outcomes": [], "decisions": []}
        passive_resistance = source == "resistance" and attacks.actor_data(session, actor).get("current_hp", 0) > 0
        if economy.can_act(session, actor) or passive_resistance:
            view = perception.snapshot(session, actor, memory)
            if source == "resistance":
                # Severity is an effect-owner label, not an AI-created save outcome.
                options = [c for c in capabilities if c["kind"] == "legendary_resistance"
                           and available(session, actor, memory, c, source)]
                severe = event.get("severity") in {"incapacitation", "paralysis", "banishment", "lethal"}
                if severe and options:
                    cap = options[0]
                    economy.monster_resource(session, actor, source, cap["kind"], cap["capability_id"])
                    spend_specific(memory, cap)
                    result["decisions"] = [{"decision_type": "LEGENDARY_RESISTANCE_USED",
                                           "capability_id": cap["capability_id"], "reason_code": "AVOID_SEVERE_EFFECT"}]
                    # Save owner must apply this verified decision to its pending save.
                    result["save_override"] = "SUCCESS"
            else:
                options = candidates(session, actor, memory, capabilities, view, source, event)
                selected, rng = choose(session, options, memory)
                if selected:
                    outcomes, metadata = execute(session, actor, selected, capabilities, memory, view, source, event)
                    metadata["rng"] = rng
                    result["outcomes"] = outcomes
                    result["decisions"] = [metadata]
        memory["last_window_result"] = copy.deepcopy(result)
        return result


def after_event(session):
    event = session.world_state["combat"].get("monster_event", {})
    source = "legendary" if event.get("kind") == "after_turn" else "reaction"
    outcomes = []
    for actor in list(session.world_state["combat"]["participants"]):
        if actor == "player":
            continue
        if source == "legendary" and actor == event.get("actor_id"):
            continue
        if not any(c["action_source"] == source for c in caps.capabilities(session, actor)):
            continue
        outcomes.extend(window(session, actor, source)["outcomes"])
    return outcomes


def public_result(session, actor, outcome):
    data = attacks.actor_data(session, actor)
    return {"action": "monster_" + outcome, "status": "resolved", "success": True,
            "outcome": outcome, "actor": actor, "actor_name": data.get("name"),
            "damage": 0, "target_name": None}


def run_turn(session, actor, *, expected_turn_id=None, commit=None):
    """Child decisions are part of the existing parent turn receipt/transaction.

    The single last result is a turn-completion checkpoint, not a parallel receipt
    store. HTTP retries and older turns replay through existing campaign receipts.
    """
    previous = session.world_state.get("monster_combat", {}).get("actors", {}).get(actor, {}).get("last_turn_result")
    if expected_turn_id is not None and previous and previous["turn_id"] == expected_turn_id:
        return copy.deepcopy(previous)
    with initiative.atomic(session):
        memory = state(session, actor)
        previous = memory["last_turn_result"]
        identity = turn_id(session, actor)
        if previous and previous["turn_id"] == (expected_turn_id or identity):
            return copy.deepcopy(previous)
        if expected_turn_id is not None and expected_turn_id != identity:
            fail("stale_monster_turn", "Monster intent belongs to a different turn.")
        combat = session.world_state["combat"]
        if not combat["active"] or combat["current_actor_id"] != actor or actor == "player":
            fail("out_of_turn", "Only the current monster may take this turn.")
        capabilities = caps.capabilities(session, actor)
        initialize_resources(session, actor, memory, capabilities)
        if not economy.can_act(session, actor):
            result = {"turn_id": identity, "actor_id": actor, "combat_id": combat["combat_id"],
                      "round": combat["round"], "decision_type": "NO_ACTION", "outcomes": [], "decisions": []}
        else:
            view = perception.snapshot(session, actor, memory)
            outcomes, decisions = [], []
            for source in ("action", "bonus"):
                if not session.world_state["combat"]["active"] or not economy.can_act(session, actor):
                    break
                view = perception.snapshot(session, actor, memory)
                options = candidates(session, actor, memory, capabilities, view, source)
                selection_rng = session.rng.getstate()
                selected, rng = choose(session, options, memory)
                if selected is None:
                    continue
                try:
                    with initiative.atomic(session):
                        actual, metadata = execute(session, actor, selected, capabilities, memory, view, source)
                except CombatRequestError as error:
                    if error.code not in {"loading_limit", "no_attack_continuation", "out_of_range",
                                          "no_ammunition", "invalid_combat_target"}:
                        raise
                    session.rng.setstate(selection_rng)
                    memory = state(session, actor)
                    view = perception.snapshot(session, actor, memory)
                    newly_legal = [c for c in candidates(session, actor, memory, capabilities, view, source)
                                   if c["capability_id"] != selected["capability_id"]]
                    fallback, _ = choose(session, newly_legal, memory, deterministic=True)
                    if fallback is None:
                        actual, metadata = [], {"decision_type": "NO_ACTION", "reason_code": "INVALID_OPTIONS"}
                    else:
                        actual, metadata = execute(session, actor, fallback, capabilities, memory, view, source)
                    metadata["rejected_capability"] = selected["capability_id"]
                    metadata["rejection_code"] = error.code
                    rng = []
                metadata.update(rng=rng, decision_id=identity + ":" + source,
                                behavior_profile={"personality": memory["personality"], "role": memory["role"]},
                                objective=copy.deepcopy(memory["objective"]))
                outcomes.extend(actual)
                decisions.append(metadata)
                memory["recent"].append({"capability_id": metadata.get("capability_id"),
                                         "target_ids": metadata.get("target_ids", [])})
                del memory["recent"][:-4]
            result = {"turn_id": identity, "actor_id": actor, "combat_id": combat["combat_id"],
                      "round": combat["round"], "decision_type": "MONSTER_TURN",
                      "outcomes": outcomes, "decisions": decisions,
                      "recharge_rolls": copy.deepcopy(memory.get("recharge_rolls", []))}
        memory["last_turn_result"] = copy.deepcopy(result)
        if commit is not None:
            commit()  # Same persistence owner; its failure restores this entire child.
        return result


def observe_attack(session, result):
    """Only participants who perceived the actual actor/target learn an event."""
    if not session.world_state.get("combat", {}).get("active"):
        return
    for actor in session.world_state["combat"]["participants"]:
        if actor == "player":
            continue
        memory = state(session, actor)
        view = perception.snapshot(session, actor, memory)
        known = {t["id"] for t in view["targets"] + view["allies"]} | {actor}
        attacker, target = result["actor_id"], result["target_id"]
        if attacker not in known or target not in known:
            continue
        entry = memory["observations"].setdefault(attacker, {"threat": 0, "beliefs": {}})
        entry["attacked_id"] = target
        if result.get("hit") and result.get("damage", 0) > 0:
            entry["threat"] = min(12, entry["threat"] + 2)
        if actor == attacker:
            for damage in result.get("damage_instances", []):
                if damage.get("resistance_applied") or damage.get("immunity_applied"):
                    observed = memory["observations"].setdefault(target, {"threat": 0, "beliefs": {}})
                    observed["beliefs"][damage["damage_type"]] = "suspected_resistant"


def proposal_response(session, actor, proposal_id, accept):
    """Player interaction owner calls this; never infer acceptance from prose."""
    if type(accept) is not bool:
        fail("invalid_proposal_response", "An explicit player decision is required.")
    memory = state(session, actor)
    proposal = next((p for p in memory.get("proposals", []) if p["proposal_id"] == proposal_id), None)
    if not proposal:
        fail("unknown_proposal", "Proposal does not exist.")
    if proposal["status"] == "pending":
        proposal["status"] = "accepted" if accept else "rejected"
    # Combat Lifecycle/social owner owns ending; this never closes an encounter.
    return copy.deepcopy(proposal)


def player_response(session, text, target_id=None):
    """Narrow Turkish choice routing, not model-generated player acceptance."""
    if not session.world_state.get("combat", {}).get("active"):
        return None
    if not isinstance(text, str) or "?" in text:
        return None
    normalized = session._normalize_turkish_typos(text)
    if not re.search(r"teslim|ateskes|parley|muzakere|konusma teklifi", normalized):
        return None
    accepted = bool(re.search(r"\bkabul ediyorum\b|\bteslimiyeti kabul\b|\bateskes yapalim\b", normalized))
    rejected = bool(re.search(r"\bredd(?:ediyorum|et)\b|\bkabul etmiyorum\b|\bhayir\b", normalized))
    if rejected:
        accepted = False
    if not accepted and not rejected:
        return None  # A question or ambiguous phrasing is not a player decision.
    economy.validate_actor(session, "player")
    root = session.world_state.get("monster_combat", {}).get("actors", {})
    pending = [(actor, p) for actor, memory in root.items()
               for p in memory.get("proposals", []) if p["status"] == "pending"
               and (target_id is None or actor == target_id)]
    if len(pending) != 1:
        fail("ambiguous_proposal", "Choose one pending surrender/parley proposal.")
    actor, proposal = pending[0]
    outcome = proposal_response(session, actor, proposal["proposal_id"], accepted)
    combat = session.world_state["combat"]
    combat_id = combat["combat_id"]
    if accepted:
        enemies = [a for a in combat["participants"] if a != "player"
                   and perception.relationship(session, a, "player") == "enemy"]
        if all(any(p["status"] == "accepted" for p in root.get(a, {}).get("proposals", [])) for a in enemies):
            session.end_combat("parley_accepted")
    return {"messages": session.messages, "model_calls": 0,
            "narration": "Teklifi kabul ettin." if accepted else "Teklifi reddettin; çatışma sürüyor.",
            "action_result": {"action": "monster_proposal_response", "status": "resolved",
                              "success": True, "combat_id": combat_id,
                              "outcome": outcome["status"]}}