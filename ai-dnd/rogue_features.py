"""Rogue 1-5 feature effects on the existing owners; it holds rules, not a budget or a resource system.

Values only (PHB 2024 PDF 128 Sneak Attack, PDF 129 Cunning Action, Steady Aim, Cunning Strike, PDF 130 Withdraw, Uncanny Dodge, PDF 133
Assassin). Every number follows the APPLIED Rogue level; a level granted by XP alone changes nothing here. The only stored fields are
`character["uncanny_dodge_off"]`, a turn marker and Steady Aim inside the player's turn resources, and a Poison entry in `attack_effects`.
"""
from __future__ import annotations

import logging
from typing import Any

import character_progression as core
from combat_lifecycle import CombatRequestError
from weapon_catalog import WEAPONS

logger = logging.getLogger(__name__)

SUBCLASS = "assassin"
SUBCLASS_LEVEL = 3
SNEAK_DIE = 6
UNCANNY_OFF = "uncanny_dodge_off"  # present only when the player turned Uncanny Dodge off, so older saves need nothing
CUNNING_ACTION_LEVEL = 2
STEADY_AIM_LEVEL = 3
CUNNING_STRIKE_LEVEL = 5
UNCANNY_DODGE_LEVEL = 5
CUNNING_STRIKES = {"poison": 1, "trip": 1, "withdraw": 1}  # die cost in d6 (PDF 129, 130)
POISONERS_KIT = "Poisoner's Kit"
POISON_EFFECT = "cunning_poison"
POISON_TURNS = 10  # 1 minute: ten of the Rogue's turns
# Simple weapons, and Martial weapons that have the Finesse or Light property.
CLASS_WEAPONS = ("simple", *sorted({weapon["weapon_id"] for weapon in WEAPONS.values() if weapon["category"] == "martial"
                                    and {"finesse", "light"} & set(weapon["properties"])}))


def rogue_level(character: Any) -> int | None:
    """The applied Rogue level, or None when this is not a verified Rogue 1-5 (at 3+ the Assassin choice must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Rogue":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= SUBCLASS_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def sneak_dice(level: int) -> int:
    try:
        value = core.table("Rogue")["levels"][str(level)]["sneak_attack_dice"]
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid Sneak Attack table value.") from error
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Sneak Attack table value.")
    return value


def carries(session: Any, item: str) -> bool:
    import equipment_economy
    return item in equipment_economy.labels(session.world_state.get("inventory", []))


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: the field exists only on a verified Rogue with the feature applied."""
    if UNCANNY_OFF not in player:
        return
    level = rogue_level(player)
    if level is None or level < UNCANNY_DODGE_LEVEL or player[UNCANNY_OFF] is not True:
        raise ValueError("Kayıt Uncanny Dodge alanı geçersiz.")


def validate_world(player: dict[str, Any], world: Any) -> None:
    """Rogue records inside combat state, read for EVERY class: absent means none of them happened, and only a Rogue sets them.

    Older saves of any class hold none of these fields; a combat shape this module does not recognise is not its to judge.
    """
    level = rogue_level(player)
    world = world if isinstance(world, dict) else {}
    combat = world.get("combat") if isinstance(world.get("combat"), dict) else {}
    turn_resources = combat.get("turn_resources") if isinstance(combat.get("turn_resources"), dict) else {}
    resources = turn_resources.get("player") if isinstance(turn_resources.get("player"), dict) else {}
    if "steady_aim" in resources:
        record = resources["steady_aim"]
        if (level is None or level < STEADY_AIM_LEVEL or type(record) is not dict or set(record) != {"advantage"}
                or type(record["advantage"]) is not bool or combat.get("current_actor_id") != "player" or resources.get("movement_used") != 0):
            raise ValueError("Kayıt Steady Aim alanı geçersiz.")
    if "sneak_attack_turn" in resources:
        marker = resources["sneak_attack_turn"]
        if (level is None or type(marker) is not list or len(marker) != 2 or type(marker[0]) is not int or marker[0] < 1
                or type(marker[1]) is not str or not marker[1]):
            raise ValueError("Kayıt Sneak Attack alanı geçersiz.")
    effects = world.get("attack_effects")
    for effect in effects if isinstance(effects, list) else []:
        if isinstance(effect, dict) and effect.get("kind") == POISON_EFFECT and (
                set(effect) != {"kind", "source_actor", "target_id", "dc", "expires_turn", "expires_boundary"}
                or level is None or level < CUNNING_STRIKE_LEVEL or effect["source_actor"] != "player"
                or type(effect["target_id"]) is not str or not effect["target_id"] or effect["expires_boundary"] != "end"
                or type(effect["dc"]) is not int or effect["dc"] < 1 or type(effect["expires_turn"]) is not int):
            raise ValueError("Kayıt Cunning Strike zehir alanı geçersiz.")


def _turn_key(session: Any) -> list[Any]:
    combat = session.world_state["combat"]
    return [combat["round"], combat["current_actor_id"]]


def sneak_used(session: Any) -> bool:
    """Once per turn, any creature's turn: a Reaction attack on an enemy turn may qualify again."""
    combat = session.world_state.get("combat", {})
    marker = combat.get("turn_resources", {}).get("player", {}).get("sneak_attack_turn")
    return bool(combat.get("active")) and marker == _turn_key(session)


def _ally_near(session: Any, target: str) -> bool:
    """A distance nobody knows is never a guess: only a known 5 feet from an able ally counts."""
    import action_economy as economy
    import monster_perception
    import weapon_attack
    for other in session.world_state["combat"]["participants"]:
        if other in ("player", target) or monster_perception.relationship(session, "player", other) != "ally":
            continue
        try:
            if economy.can_act(session, other) and weapon_attack.pair(session, other, target)["distance_ft"] <= 5:
                return True
        except CombatRequestError:
            continue
    return False


def _qualifies(session: Any, c: dict[str, Any]) -> bool:
    if "finesse" not in c["weapon"]["properties"] and c["weapon"]["kind"] != "ranged":
        return False
    if c["disadvantage_sources"]:
        return False
    return bool(c["advantage_sources"]) or _ally_near(session, c["target_id"])


def surprising_target(session: Any, target: str) -> bool:
    """The first round, against a creature later in the order than the turn in progress."""
    combat = session.world_state["combat"]
    order = combat.get("initiative_order", [])
    return combat.get("round") == 1 and target in order and order.index(target) > combat.get("current_turn_index", 0)


def _assassin(character: Any) -> bool:
    level = rogue_level(character)
    return level is not None and level >= SUBCLASS_LEVEL


def initiative_rules(character: Any) -> dict[str, Any]:
    return {"advantage_sources": ["assassinate"]} if _assassin(character) else {}


def attack_advantage(session: Any, target: str) -> list[str]:
    """Feature Advantage for the player's next attack roll."""
    character, sources = session.character, []
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or rogue_level(character) is None:
        return sources
    if combat.get("turn_resources", {}).get("player", {}).get("steady_aim", {}).get("advantage") is True:
        sources.append("steady_aim")
    if _assassin(character) and surprising_target(session, target):
        sources.append("surprising_strikes")
    return sources


def spend_steady_aim(session: Any) -> None:
    record = session.world_state.get("combat", {}).get("turn_resources", {}).get("player", {}).get("steady_aim")
    if record:
        record["advantage"] = False


def _crawling(session: Any) -> bool:
    import action_economy as economy
    return bool(session.character.get("prone") or "prone" in economy.conditions(session, "player"))


def _withdraw_cost(session: Any, distance: int) -> int:
    import spatial_rules
    return spatial_rules.movement_cost(distance, crawling=_crawling(session))


def withdraw_limit(session: Any) -> int:
    import action_economy as economy
    return economy.speed(session, "player") // 2


def _too_large(defender: dict[str, Any]) -> bool:
    """Trip reaches Large or smaller. A size the table does not know is left to the save, as it always was for a creature with none."""
    import weapon_attack
    size = str(defender.get("size", "medium")).lower()
    return size in weapon_attack.SIZES and weapon_attack.SIZES.index(size) > weapon_attack.SIZES.index("large")


def _strike_reason(session: Any, option: str, defender: dict[str, Any] | None) -> str | None:
    if option == "poison" and not carries(session, POISONERS_KIT):
        return "cunning_strike_kit_required"
    if option == "trip" and defender is not None and _too_large(defender):
        return "cunning_strike_target_too_large"
    return None


def _trip_refused_targets(session: Any) -> list[str]:
    """Who Trip would refuse right now, so the public block can say so before the player picks a target."""
    import weapon_attack
    combat = session.world_state.get("combat", {})
    refused = []
    for other in combat.get("participants", []) if combat.get("active") else []:
        try:
            if other != "player" and _too_large(weapon_attack.actor_data(session, other)):
                refused.append(other)
        except CombatRequestError:
            continue
    return refused


def check_choice(session: Any, actor: str, choice: dict[str, Any], defender: dict[str, Any]) -> None:
    """Refuse before any roll: a Cunning Strike the player cannot pay for changes nothing."""
    option, distance = choice.get("cunning_strike"), choice.get("cunning_strike_move_ft")
    if option is None and distance is None:
        return
    level = rogue_level(session.character) if actor == "player" else None
    if level is None or level < CUNNING_STRIKE_LEVEL:
        raise CombatRequestError("cunning_strike_not_available", "Cunning Strike starts at Rogue level 5.", 400)
    if option not in CUNNING_STRIKES or (option == "withdraw") != (distance is not None):
        raise CombatRequestError("invalid_cunning_strike", "Choose Poison, Trip, or Withdraw with a distance.", 400)
    if sneak_used(session):
        raise CombatRequestError("sneak_attack_already_used", "Sneak Attack was already dealt this turn.", 400)
    reason = _strike_reason(session, option, defender)
    if reason:
        raise CombatRequestError(reason, "Cunning Strike is unavailable: " + reason, 400)
    if option == "withdraw" and (type(distance) is not int or distance < 1 or _withdraw_cost(session, distance) > withdraw_limit(session)):
        raise CombatRequestError("cunning_strike_out_of_range", "Withdraw moves up to half your Speed.", 400)


def sneak_attack(session: Any, c: dict[str, Any], critical: bool) -> dict[str, Any] | None:
    """The hit's Sneak Attack, or None. Any Cunning Strike die is forgone here, before the roll; the turn marker is set."""
    level = rogue_level(session.character)
    if level is None or c["actor_id"] != "player" or not session.world_state["combat"]["active"]:
        return None
    if sneak_used(session) or not _qualifies(session, c):
        return None
    session.world_state["combat"]["turn_resources"]["player"]["sneak_attack_turn"] = _turn_key(session)
    option = c["choice"].get("cunning_strike")
    dice = sneak_dice(level) - (CUNNING_STRIKES[option] if option else 0)
    return {"dice": dice, "die": SNEAK_DIE, "count": dice * (2 if critical else 1), "option": option,
            "surprising_strikes": level if _assassin(session.character) and session.world_state["combat"].get("round") == 1 else 0}


def _strike_dc(character: dict[str, Any]) -> int:
    dexterity, bonus = character.get("dexterity_mod"), character.get("proficiency_bonus")
    if type(dexterity) is not int or type(bonus) is not int:
        raise ValueError("Invalid Cunning Strike DC fields.")
    return 8 + dexterity + bonus


def _immune(defender: dict[str, Any], condition: str) -> bool:
    return condition in {str(name).lower() for name in defender.get("condition_immunities", [])}


def _saving_effect(session: Any, c: dict[str, Any], condition: str, ability: str, dc: int) -> dict[str, Any]:
    import weapon_attack
    target, defender = c["target_id"], weapon_attack.actor_data(session, c["target_id"])
    if defender.get("current_hp", 0) <= 0:
        return {"applied": False, "reason": "target_defeated"}
    if _immune(defender, condition):
        return {"applied": False, "reason": "condition_immunity"}
    if condition in weapon_attack.conditions(session, target, defender):
        return {"applied": False, "reason": "already_" + condition}
    saving = weapon_attack.save(session, target, (ability,), dc, effect_context={"severity": "minor"})
    applied = saving["outcome"] == "FAILURE"
    if applied:
        weapon_attack.add_condition(defender, condition)
    return {"applied": applied, "save": saving}


def _withdraw(session: Any, distance: int) -> dict[str, Any]:
    """The move happens inside the attack on the existing ledger; no allowance outlives the step (as Tactical Shift does)."""
    import action_economy as economy
    economy.ensure(session)["player"]["ready_movement_grant"] += _withdraw_cost(session, distance)
    economy.move(session, "player", distance)
    return {"applied": True, "moved_ft": distance}


def narration(result: dict[str, Any]) -> str:
    """Reads a completed attack result only; the public turn response carries no step results."""
    sneak = result.get("sneak_attack")
    if not sneak:
        return ""
    extra = f" +{sneak['surprising_strikes']}" if sneak["surprising_strikes"] else ""
    text = f"Sneak Attack: {sneak['dice']}d{sneak['die']}{extra}."
    strike = result.get("cunning_strike")
    if not strike:
        return text
    name = strike["option"].capitalize()
    if strike["option"] == "withdraw":
        return f"{text} Cunning Strike ({name}): {strike['moved_ft']} fit uzaklaşırsın."
    condition = {"trip": "Prone", "poison": "Poisoned"}[strike["option"]]
    if strike["applied"]:
        return f"{text} Cunning Strike ({name}): hedef {condition} olur (DC {strike['dc']})."
    return f"{text} Cunning Strike ({name}): etki olmaz (DC {strike['dc']})."


def after_attack(session: Any, c: dict[str, Any], result: dict[str, Any], sneak: dict[str, Any] | None) -> None:
    """The effect occurs immediately after the attack's damage is dealt; the die was already forgone."""
    if sneak is None:
        return
    result["sneak_attack"] = {key: sneak[key] for key in ("dice", "die", "surprising_strikes")}
    option = sneak["option"]
    if option is None:
        return
    dc = _strike_dc(session.character)
    if option == "trip":
        effect = _saving_effect(session, c, "prone", "dexterity", dc)
    elif option == "poison":
        effect = _saving_effect(session, c, "poisoned", "constitution", dc)
        if effect["applied"]:
            turn = session.world_state["combat"]["turn_resources"]["player"].get("attack_turn_counter", 0)
            session.world_state.setdefault("attack_effects", []).append(
                {"kind": POISON_EFFECT, "source_actor": "player", "target_id": c["target_id"], "dc": dc,
                 "expires_turn": turn + POISON_TURNS, "expires_boundary": "end"})
    else:
        effect = _withdraw(session, c["choice"]["cunning_strike_move_ft"])
    result["cunning_strike"] = {"option": option, "cost": CUNNING_STRIKES[option], "dc": dc, **effect}


def _clear_poison(session: Any, effect: dict[str, Any]) -> None:
    for npc in session.world_state.get("npcs", []):
        if isinstance(npc, dict) and npc.get("id") == effect["target_id"]:
            names = npc.get("conditions", [])
            if isinstance(names, dict):
                names.pop("poisoned", None)
            elif "poisoned" in names:
                names.remove("poisoned")


def _poison_effects(session: Any) -> list[dict[str, Any]]:
    return [e for e in session.world_state.get("attack_effects", []) if e.get("kind") == POISON_EFFECT]


def turn_boundary(session: Any, actor: str, event: str, counter: int) -> None:
    """Called by the existing turn-boundary owner, before it expires effects."""
    import weapon_attack
    if event != "end":
        return
    if actor == "player":
        session.world_state.get("combat", {}).get("turn_resources", {}).get("player", {}).pop("steady_aim", None)
    for effect in _poison_effects(session):
        ended = False
        if effect["target_id"] == actor and any(npc.get("id") == actor and npc.get("location") == session.world_state.get("location")
                                                for npc in session.world_state.get("npcs", []) if isinstance(npc, dict)):
            ended = weapon_attack.save(session, actor, ("constitution",), effect["dc"], effect_context={"severity": "minor"})["outcome"] == "SUCCESS"
        if ended or (actor == "player" and counter >= effect["expires_turn"]):
            _clear_poison(session, effect)
            session.world_state["attack_effects"].remove(effect)


def combat_ended(session: Any) -> None:
    """Poison lasts at most this combat: its turn owner is gone. Called before the effects list is cleared."""
    for effect in _poison_effects(session):
        _clear_poison(session, effect)


def uncanny_dodge(session: Any, c: dict[str, Any], hit: bool, damage: int) -> tuple[int, list[dict[str, Any]]]:
    """Halve one hit before Resistance; a Reaction held by Ready or turned off is kept."""
    import action_economy as economy
    import weapon_attack
    character = session.character
    level = rogue_level(character)
    combat = session.world_state.get("combat", {})
    if (level is None or level < UNCANNY_DODGE_LEVEL or UNCANNY_OFF in character or not hit or damage <= 0
            or not combat.get("active") or (c["unarmed"] and c["unarmed_option"] != "damage")
            or not economy.can_act(session, "player")):
        return damage, []
    resources = economy.ensure(session)["player"]
    attacker = weapon_attack.actor_data(session, c["actor_id"])
    attacker_conditions = weapon_attack.conditions(session, c["actor_id"], attacker)
    seen = (c["spatial"].get("target_sees_attacker") is True
            or (c["spatial"].get("target_sees_attacker") is not False and "invisible" not in attacker_conditions
                and not attacker.get("hidden")))
    if resources["reaction_spent"] or resources["ready"] or not seen or "blinded" in weapon_attack.conditions(session, "player", character):
        return damage, []
    resources["reaction_spent"] = True
    return damage // 2, [{"kind": "uncanny_dodge", "damage_before": damage, "damage_after": damage // 2}]


def _turn_reason(session: Any, prefix: str, minimum: int) -> str | None:
    from combat_lifecycle import player_incapacitated
    level = rogue_level(session.character)
    if level is None or level < minimum:
        return f"{prefix}_not_available"
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or combat.get("current_actor_id") != "player":
        return f"{prefix}_current_combat_turn_required"
    if player_incapacitated(session.character, session.world_state):
        return f"{prefix}_incapacitated"
    resources = combat.get("turn_resources", {}).get("player", {})
    if resources.get("opportunity"):
        return "reaction_pending"  # pure projection, no ensure() mutation
    return "bonus_action_spent" if resources.get("bonus_action_spent") else None


def _steady_aim_reason(session: Any) -> str | None:
    reason = _turn_reason(session, "steady_aim", STEADY_AIM_LEVEL)
    if reason:
        return reason
    return "steady_aim_moved" if session.world_state["combat"].get("turn_resources", {}).get("player", {}).get("movement_used") else None


def cunning_action(session: Any, option: Any) -> dict[str, Any]:
    from initiative import atomic
    import action_economy as economy
    with atomic(session):
        reason = _turn_reason(session, "cunning_action", CUNNING_ACTION_LEVEL)
        if reason:
            raise CombatRequestError(reason, "Cunning Action is unavailable: " + reason, 400)
        economy.consume_feature_bonus(session)
        resources = economy.ensure(session)["player"]
        if option == "disengage":
            resources["disengaging"] = True
            return {"option": option}
        added = economy.speed(session, "player")
        resources["dash_count"] = resources.get("dash_count", 0) + 1
        resources["movement_available"] = max(resources["movement_used"], economy.movement_limit(session, "player"))
        return {"option": option, "movement_added_ft": added}


def steady_aim(session: Any) -> dict[str, Any]:
    from initiative import atomic
    import action_economy as economy
    with atomic(session):
        reason = _steady_aim_reason(session)
        if reason:
            raise CombatRequestError(reason, "Steady Aim is unavailable: " + reason, 400)
        economy.consume_feature_bonus(session)
        resources = economy.ensure(session)["player"]
        resources["steady_aim"] = {"advantage": True}
        resources["movement_available"] = resources["movement_used"]
        return {"active": True}


def set_uncanny_dodge(session: Any, enabled: Any) -> dict[str, Any]:
    level = rogue_level(session.character)
    if level is None or level < UNCANNY_DODGE_LEVEL:
        raise CombatRequestError("uncanny_dodge_not_available", "Uncanny Dodge starts at Rogue level 5.", 400)
    if enabled:
        session.character.pop(UNCANNY_OFF, None)
    else:
        session.character[UNCANNY_OFF] = True
    return {"enabled": bool(enabled)}


def native_command(command: Any) -> bool:
    """One exact typed step; Hide is not offered."""
    if type(command) is not dict or set(command) != {"steps"} or type(command["steps"]) is not list or len(command["steps"]) != 1:
        return False
    step = {key: value for key, value in command["steps"][0].items() if value is not None} if type(command["steps"][0]) is dict else None
    if step is None:
        return False
    if step.get("kind") == "cunning_action":
        return step.get("resource") == "bonus" and step.get("cunning_option") in ("dash", "disengage") and set(step) == {"kind", "resource", "cunning_option"}
    if step.get("kind") == "steady_aim":
        return step.get("resource") == "bonus" and set(step) == {"kind", "resource"}
    return (step.get("kind") == "uncanny_dodge" and type(step.get("uncanny_dodge_enabled")) is bool
            and set(step) - {"resource"} == {"kind", "uncanny_dodge_enabled"} and step.get("resource", "action") == "action")


def step_choice(step: dict[str, Any]) -> dict[str, Any]:
    """The Cunning Strike fields of a public attack step, as attack choices."""
    return {name: step[name] for name in ("cunning_strike", "cunning_strike_move_ft") if step.get(name) is not None}


def _availability(reason: str | None) -> dict[str, Any]:
    return {"available": reason is None, "reason": reason}


def projection(session: Any) -> dict[str, Any] | None:
    """The public block. Invalid saved state hides the controls and leaves a log line; any other fault is a real error."""
    import action_economy as economy
    character = session.character
    try:
        level = rogue_level(character)
        if level is None:
            return None
        validate_saved(character)
        combat = session.world_state.get("combat", {})
        in_combat = bool(combat.get("active"))
        resources = combat.get("turn_resources", {}).get("player", {})
        action_reason = _turn_reason(session, "cunning_action", CUNNING_ACTION_LEVEL)
        strike = None
        if level >= CUNNING_STRIKE_LEVEL:
            strike = {"dc": _strike_dc(character), "withdraw_max_ft": withdraw_limit(session) if in_combat else 0,
                      "trip_refused_targets": _trip_refused_targets(session),
                      "options": [{"id": option, "cost": cost, **_availability(_strike_reason(session, option, None))}
                                  for option, cost in CUNNING_STRIKES.items()]}
        return {
            "subclass": character.get("subclass_id"),
            "sneak_attack": {"dice": sneak_dice(level), "die": SNEAK_DIE, "used_this_turn": sneak_used(session)},
            "cunning_action": None if level < CUNNING_ACTION_LEVEL else {"dash": _availability(action_reason), "disengage": _availability(action_reason)},
            "steady_aim": None if level < STEADY_AIM_LEVEL else {**_availability(_steady_aim_reason(session)), "active": "steady_aim" in resources},
            "cunning_strike": strike,
            "uncanny_dodge": None if level < UNCANNY_DODGE_LEVEL else {
                "enabled": UNCANNY_OFF not in character,
                "reaction_available": not (in_combat and (resources.get("reaction_spent") or not economy.can_act(session, "player")))},
        }
    except ValueError as error:
        logger.warning("Rogue controls hidden: %s", error)
        return None
