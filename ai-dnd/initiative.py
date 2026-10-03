"""2024 Initiative audit and membership, inside the existing combat scheduler.

Only trusted engine/feature code supplies groups, awareness or hooks. No HTTP
initiative commands, additional RNG, class features or separate turn ledger.
"""
import copy
from contextlib import contextmanager
from contextvars import ContextVar

from api.core_resolution import roll_d20 as resolve_d20

EVENTS = {"ON_INITIATIVE_ROLL", "AFTER_INITIATIVE_ROLL", "AFTER_INITIATIVE_ORDER_INITIALIZED"}
INCAPACITATING = {"incapacitated", "unconscious", "paralyzed", "stunned", "petrified"}
_starting = ContextVar("initiative_start_owner", default=None)


@contextmanager
def starting(session):
    token = _starting.set(id(session))
    try:
        yield
    finally:
        _starting.reset(token)


@contextmanager
def atomic(session):
    world, character = copy.deepcopy(session.world_state), copy.deepcopy(session.character)
    messages, rng = copy.deepcopy(session.messages), session.rng.getstate()
    try:
        yield
    except Exception:
        session.world_state.clear()
        session.world_state.update(world)
        session.character.clear()
        session.character.update(character)
        session.messages[:] = messages
        session.rng.setstate(rng)
        raise


def data_for(session, actor):
    if actor == "player":
        return session.character
    matches = [n for n in session.world_state.get("npcs", []) if isinstance(n, dict) and n.get("id") == actor]
    if len(matches) != 1 or matches[0].get("location") != session.world_state["location"]:
        raise ValueError("Initiative actor must be one canonical local participant.")
    return matches[0]


def incapacitated(data):
    names = data.get("conditions", [])
    if isinstance(names, dict):
        names = [k for k, v in names.items() if v]
    if not isinstance(names, (list, set, tuple)):
        raise ValueError("Invalid authoritative Initiative conditions.")
    return bool({str(k).lower() for k in names} & INCAPACITATING
                or data.get("combat_status") == "unconscious" or data.get("current_hp", 1) <= 0)


def register_hook(session, event, callback):
    """Feature-owned handlers; registered on a session, never via client input."""
    if event not in EVENTS or not callable(callback):
        raise ValueError("Invalid Initiative hook.")
    if not hasattr(session, "_initiative_hooks"):
        session._initiative_hooks = {}
    session._initiative_hooks.setdefault(event, []).append(callback)


def notify(session, event, context):
    return [fn(session, copy.deepcopy(context))
            for fn in getattr(session, "_initiative_hooks", {}).get(event, ())]


def settings(session, actor, *, notify_features=True):
    data = data_for(session, actor)
    base = data.get("dexterity_mod", 0) if actor == "player" else data.get("initiative_modifier", 0)
    if type(base) is not int:
        raise ValueError("Invalid authoritative Initiative modifier.")
    rules = copy.deepcopy(data.get("initiative_rules", {}))
    if not isinstance(rules, dict):
        raise ValueError("Invalid authoritative Initiative rules.")
    contributions = [rules]
    if notify_features:
        contributions.extend(notify(session, "ON_INITIATIVE_ROLL", {"actor_id": actor}))
    modifiers, advantages, disadvantages = [], [], []
    for contribution in contributions:
        if contribution is None:
            continue
        if not isinstance(contribution, dict) or set(contribution) - {"modifiers", "advantage_sources", "disadvantage_sources"}:
            raise ValueError("Unrecognized Initiative contribution.")
        values = contribution.get("modifiers", [])
        if not isinstance(values, list):
            raise ValueError("Invalid Initiative modifier list.")
        for value in values:
            if (not isinstance(value, dict) or set(value) != {"source", "value"}
                    or not isinstance(value["source"], str) or not value["source"].strip()
                    or type(value["value"]) is not int):
                raise ValueError("Invalid sourced Initiative modifier.")
            modifiers.append(copy.deepcopy(value))
        for key, dest in (("advantage_sources", advantages), ("disadvantage_sources", disadvantages)):
            sources = contribution.get(key, [])
            if not isinstance(sources, list) or any(not isinstance(s, str) or not s.strip() for s in sources):
                raise ValueError("Invalid Initiative roll source.")
            dest.extend(sources)
    if len({m["source"] for m in modifiers}) != len(modifiers):
        raise ValueError("Duplicate Initiative modifier source.")
    surprised = data.get("surprised_at_combat_start", False)
    if type(surprised) is not bool:
        raise ValueError("Surprise must be authoritative boolean state.")
    if surprised:
        disadvantages.append("surprise_2024")
    if incapacitated(data):
        disadvantages.append("incapacitated_2024")
    group = data.get("initiative_group_id")
    block = data.get("stat_block_id")
    if group is not None and (actor == "player" or not isinstance(group, str) or not group.strip()
                              or not isinstance(block, str) or not block.strip()):
        raise ValueError("An explicit identical-monster Initiative group needs stat-block identity.")
    score = data.get("initiative_score")
    if score is not None and type(score) is not int:
        raise ValueError("Invalid monster Initiative score.")
    return {"base_modifier": base, "additional_modifiers": modifiers,
            "advantage_sources": sorted(set(advantages)), "disadvantage_sources": sorted(set(disadvantages)),
            "surprised": surprised, "group_id": group, "stat_block_id": block,
            "stat_block_score": score}


def group_signature(config):
    return {k: v for k, v in config.items() if k != "stat_block_score"}


def roll_actor(session, actor, config):
    # Preserve the public legacy rollers and the same session RNG stream. The
    # common D20 resolver, not an Initiative-specific algorithm, selects dice.
    base = config["base_modifier"]
    roller = (lambda: session.roll_initiative_player() - base) if actor == "player" else (
        lambda: session.roll_initiative(base) - base)
    dice = resolve_d20(roller, advantage=bool(config["advantage_sources"]),
                      disadvantage=bool(config["disadvantage_sources"]))
    total = dice["selected_roll"] + base + sum(m["value"] for m in config["additional_modifiers"])
    return {"actor_id": actor, **copy.deepcopy(config), **dice, "final_total": total,
            "source": "PHB_2024_initiative", "mode": "rolled"}


def ordered(totals):
    return sorted(totals, key=lambda actor: (-totals[actor], 0 if actor == "player" else 1, actor))


def roll_members(session, actors, existing_results=None, existing_groups=None):
    # Validate every group and contribution before consuming any Initiative RNG.
    configs = {actor: settings(session, actor) for actor in actors}
    groups = copy.deepcopy(existing_groups or {})
    results = copy.deepcopy(existing_results or {})
    signatures = {}
    for actor, config in configs.items():
        group = config["group_id"]
        if group is None:
            continue
        if group in groups:
            original = results[groups[group][0]]
            signatures[group] = group_signature({k: original[k] for k in config})
        signature = group_signature(config)
        if group in signatures and signatures[group] != signature:
            raise ValueError("Grouped Initiative members must have identical authoritative roll rules.")
        signatures[group] = signature
    effects = []
    for actor in actors:
        config = configs[actor]
        group = config["group_id"]
        if group is not None and groups.get(group):
            result = copy.deepcopy(results[groups[group][0]])
            result.update(actor_id=actor, stat_block_score=config["stat_block_score"])
        else:
            result = roll_actor(session, actor, config)
        results[actor] = result
        if group is not None:
            groups.setdefault(group, []).append(actor)
        for response in notify(session, "AFTER_INITIATIVE_ROLL", {"actor_id": actor, "result": result}):
            if response is not None:
                if not isinstance(response, list):
                    raise ValueError("Post-roll hooks return a list of authoritative ordering effects.")
                effects.extend(response)
    return results, groups, effects


def apply_effects(session, combat, effects):
    """Feature code owns eligibility; Initiative validates ordering consequences."""
    for effect in effects:
        if not isinstance(effect, dict) or not isinstance(effect.get("source"), str) or not effect["source"].strip():
            raise ValueError("Ordering effect needs an authoritative feature source.")
        actor = effect.get("actor_id")
        records = {r["id"]: r for r in combat["participant_records"]}
        if actor not in records:
            raise ValueError("Ordering effect actor is not a participant.")
        kind = effect.get("kind")
        if kind == "swap":
            ally = effect.get("ally_id")
            if ally not in records or ally == actor or effect.get("willing") is not True:
                raise ValueError("Initiative swap needs a distinct willing ally.")
            left, right = data_for(session, actor), data_for(session, ally)
            team_left = left.get("combat_side", "party" if actor == "player" else "enemy")
            team_right = right.get("combat_side", "party" if ally == "player" else "enemy")
            if team_left != team_right or incapacitated(left) or incapacitated(right):
                raise ValueError("Initiative swap is unavailable for foes or Incapacitated participants.")
            records[actor]["initiative"], records[ally]["initiative"] = records[ally]["initiative"], records[actor]["initiative"]
        elif kind == "count_adjustment":
            if type(effect.get("value")) is not int:
                raise ValueError("Invalid feature Initiative adjustment.")
            records[actor]["initiative"] += effect["value"]
        else:
            raise ValueError("This ordering effect has no Initiative implementation.")
        combat.setdefault("initiative_effects", []).append(copy.deepcopy(effect))
    combat["initiative_order"] = ordered({r["id"]: r["initiative"] for r in combat["participant_records"]})


def after_order(session, combat, rolled_actors):
    effects = []
    for response in notify(session, "AFTER_INITIATIVE_ORDER_INITIALIZED", {
            "rolled_actor_ids": rolled_actors, "initiative_order": combat["initiative_order"]}):
        if response is not None:
            if not isinstance(response, list):
                raise ValueError("Post-order hooks return authoritative ordering effects.")
            effects.extend(response)
    apply_effects(session, combat, effects)


def initialize(session, actors):
    combat = session.world_state["combat"]
    if (_starting.get() != id(session) or not combat["active"]
            or set(actors) != set(combat["participants"]) or "initiative_results" in combat):
        raise ValueError("Only the established Combat-start lifecycle may initialize Initiative.")
    results, groups, effects = roll_members(session, actors)
    return {"initiative_results": results, "initiative_groups": groups,
            "initiative_effects": [], "effects_to_apply": effects}


def validate_saved(combat):
    results = combat.get("initiative_results")
    if results is None:
        if any(k in combat for k in ("initiative_groups", "initiative_effects")):
            raise ValueError("Partial Initiative audit state.")
        return  # Existing saves preserve their old totals; never fabricate dice.
    if not isinstance(results, dict) or set(results) != set(combat["participants"]):
        raise ValueError("Invalid Initiative result owners.")
    for actor, result in results.items():
        if not isinstance(result, dict) or result.get("actor_id") != actor:
            raise ValueError("Invalid Initiative actor result.")
        if result.get("mode") == "legacy_preserved":
            if (type(result.get("final_total")) is not int or result.get("raw_rolls") != []
                    or result.get("group_id") is not None):
                raise ValueError("Invalid preserved legacy Initiative total.")
            continue
        for name in ("advantage_sources", "disadvantage_sources"):
            values = result.get(name)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError("Invalid Initiative source audit.")
        if (type(result.get("surprised")) is not bool
                or result.get("source") != "PHB_2024_initiative" or result.get("roll_type") != "d20"):
            raise ValueError("Invalid Initiative source/context.")
        raw = result.get("raw_rolls")
        if (not isinstance(raw, list) or len(raw) not in (1, 2)
                or any(type(v) is not int or not 1 <= v <= 20 for v in raw)):
            raise ValueError("Invalid canonical Initiative dice.")
        adv, dis = result.get("advantage"), result.get("disadvantage")
        if type(adv) is not bool or type(dis) is not bool or len(raw) != (2 if adv != dis else 1):
            raise ValueError("Invalid Initiative Advantage/Disadvantage.")
        if adv != bool(result["advantage_sources"]) or dis != bool(result["disadvantage_sources"]):
            raise ValueError("Initiative roll and its sources disagree.")
        selected = max(raw) if adv and not dis else min(raw) if dis and not adv else raw[0]
        base, modifiers = result.get("base_modifier"), result.get("additional_modifiers")
        if (type(base) is not int or not isinstance(modifiers, list)
                or any(not isinstance(m, dict) or not isinstance(m.get("source"), str)
                       or not m["source"] or type(m.get("value")) is not int for m in modifiers)):
            raise ValueError("Invalid Initiative modifier breakdown.")
        if (type(result.get("selected_roll")) is not int or result["selected_roll"] != selected
                or type(result.get("final_total")) is not int
                or result["final_total"] != selected + base + sum(m["value"] for m in modifiers)
                or result.get("advantage_cancelled") is not (adv and dis)
                or result.get("mode") != "rolled"):
            raise ValueError("Initiative audit total is inconsistent.")
    groups = combat.get("initiative_groups")
    if not isinstance(groups, dict):
        raise ValueError("Invalid Initiative groups.")
    grouped = []
    for group, members in groups.items():
        if (not isinstance(group, str) or not group or not isinstance(members, list) or not members
                or any(not isinstance(a, str) or not a for a in members)
                or len(set(members)) != len(members) or not set(members).issubset(results)):
            raise ValueError("Invalid Initiative group membership.")
        grouped.extend(members)
        first = results[members[0]]
        for actor in members:
            r = results[actor]
            if (r.get("group_id") != group or r.get("stat_block_id") != first.get("stat_block_id")
                    or r["raw_rolls"] != first["raw_rolls"] or r["final_total"] != first["final_total"]):
                raise ValueError("Shared Initiative group results differ.")
    if len(grouped) != len(set(grouped)) or set(grouped) != {a for a, r in results.items() if r.get("group_id") is not None}:
        raise ValueError("Duplicate or missing Initiative group assignments.")
    totals = {actor: r["final_total"] for actor, r in results.items()}
    effects = combat.get("initiative_effects")
    if not isinstance(effects, list):
        raise ValueError("Invalid Initiative effect history.")
    for effect in effects:
        if not isinstance(effect, dict) or not isinstance(effect.get("source"), str) or not effect["source"]:
            raise ValueError("Invalid Initiative effect history.")
        actor = effect.get("actor_id")
        if not isinstance(actor, str) or not actor:
            raise ValueError("Invalid Initiative effect actor.")
        if effect.get("kind") == "swap":
            ally = effect.get("ally_id")
            if not isinstance(ally, str) or ally == actor or effect.get("willing") is not True:
                raise ValueError("Invalid Initiative swap history.")
            if actor in totals and ally in totals:
                totals[actor], totals[ally] = totals[ally], totals[actor]
        elif effect.get("kind") == "count_adjustment" and type(effect.get("value")) is int:
            if actor in totals:
                totals[actor] += effect["value"]
        else:
            raise ValueError("Invalid persisted Initiative ordering effect.")
    if any(r["initiative"] != totals[r["id"]] for r in combat["participant_records"]):
        raise ValueError("Initiative count and audited effects disagree.")
    if combat["initiative_order"] != ordered(totals):
        raise ValueError("Canonical Initiative order disagrees with audited counts.")


def join(session, actor_ids):
    """Trusted lifecycle entry point, not a client-supplied membership command."""
    import action_economy
    with atomic(session):
        combat = session.ensure_combat_state()
        if not combat["active"]:
            raise ValueError("Initiative cannot independently start combat.")
        if not isinstance(actor_ids, list) or not actor_ids or len(set(actor_ids)) != len(actor_ids):
            raise ValueError("Joining actors need unique canonical IDs.")
        fresh = [a for a in actor_ids if a not in combat["participants"]]
        if not fresh:
            return []
        for actor in fresh:
            if actor == "player":
                raise ValueError("Player membership is owned by Combat lifecycle.")
            data = data_for(session, actor)
            if data.get("combat_status", "active") not in {"active", "unconscious"}:
                raise ValueError("Inactive combatant cannot join Initiative.")
        current = combat["current_actor_id"]
        if "initiative_results" not in combat:
            if any(type(r["initiative"]) is not int for r in combat["participant_records"]):
                raise ValueError("Legacy encounter has no authoritative totals for newcomer insertion.")
            combat.update(initiative_results={
                r["id"]: {"actor_id": r["id"], "final_total": r["initiative"],
                          "mode": "legacy_preserved", "raw_rolls": [], "group_id": None}
                for r in combat["participant_records"]
            }, initiative_groups={}, initiative_effects=[])
        results, groups, effects = roll_members(session, fresh, combat["initiative_results"], combat["initiative_groups"])
        combat["initiative_results"], combat["initiative_groups"] = results, groups
        for actor in fresh:
            combat["participants"].append(actor)
            combat["participant_records"].append(session._combat_record_for_actor(actor, results[actor]["final_total"]))
        apply_effects(session, combat, effects)
        after_order(session, combat, fresh)
        combat["current_turn_index"] = combat["initiative_order"].index(current)
        for actor in fresh:
            if combat["initiative_order"].index(actor) < combat["current_turn_index"]:
                combat["actions_used"].append(actor)  # Wait until next round; never replay passed turns.
            action_economy.initialize_actor(session, actor)
        session._sync_combat_participant_records(combat)
        session._validate_combat_v3_payload(combat)
        return fresh


def leave(session, actor):
    """Remove one legitimate leaver without rerolling or moving other actors."""
    with atomic(session):
        combat = session.ensure_combat_state()
        if not combat["active"] or actor not in combat["participants"]:
            return False
        if actor == "player":
            if not session.ensure_death_state()["dead"]:
                raise ValueError("Initiative cannot remove a living player.")
            session._combat_end_if_decided()
            return True
        if len(combat["participants"]) == 2:
            # Death/lifecycle decides whether to end or retain the player's
            # death-resolution boundary when the last opponent leaves.
            if session._combat_end_if_decided(excluded_participant_ids=(actor,)):
                return True
        current = combat["current_actor_id"]
        old_order = list(combat["initiative_order"])
        if "initiative_results" in combat:
            # Preserve historical swap consequences when one partner leaves.
            counts = {r["id"]: r["initiative"] for r in combat["participant_records"]}
            combat["initiative_effects"] = [
                {"kind": "count_adjustment", "source": "preserved_order_on_departure",
                 "actor_id": a, "value": counts[a] - r["final_total"],
                 "prior_effects": copy.deepcopy(combat["initiative_effects"])}
                for a, r in combat["initiative_results"].items() if a != actor and counts[a] != r["final_total"]]
            del combat["initiative_results"][actor]
            groups = combat["initiative_groups"]
            for group in list(groups):
                groups[group] = [a for a in groups[group] if a != actor]
                if not groups[group]:
                    del groups[group]
        for key in ("participants", "initiative_order", "actions_used"):
            combat[key] = [a for a in combat[key] if a != actor]
        combat["participant_records"] = [r for r in combat["participant_records"] if r["id"] != actor]
        combat.get("turn_resources", {}).pop(actor, None)
        for r in combat.get("turn_resources", {}).values():
            if r.get("ready") and (r["ready"]["trigger"]["actor_id"] == actor or r["ready"]["response"].get("target_id") == actor):
                r["ready"], r["opportunity"] = None, None
        if combat["target_id"] == actor:
            combat["target_id"] = next((a for a in combat["initiative_order"] if a != "player"), None)
        if current != actor:
            combat["current_turn_index"] = combat["initiative_order"].index(current)
        else:
            remaining_this_round = old_order[old_order.index(actor) + 1:]
            session._sync_combat_participant_records(combat)
            successor = next((a for a in remaining_this_round if a not in combat["actions_used"]
                              and session._combat_participant_can_act(combat, a)), None)
            if successor is not None:
                session._begin_combat_actor_turn(successor)
            else:
                # Delegate round wrap, clock and resource reset to the scheduler.
                predecessor = combat["initiative_order"][-1]
                combat["current_actor_id"] = predecessor
                combat["current_turn_index"] = len(combat["initiative_order"]) - 1
                session.advance_combat_turn()
        session._sync_combat_participant_records(combat)
        session._validate_combat_v3_payload(combat)
        return True