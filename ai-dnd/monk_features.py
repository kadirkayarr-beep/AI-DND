"""Monk 1-5 feature rules on the existing owners; it holds rules and one small state record, not a budget or a resource system.

Values only (PHB 2024 PDF 100/101/102 class features, PDF 106 Warrior of the Open Hand).
`character["monk_state"]` = {"focus_spent", "metabolism_spent", "deflect"} is additive, like `hit_dice`: a save without it spent
nothing, and a counter (not a remaining value) makes table growth add points without refilling them.
Everything follows the APPLIED Monk level; a level granted by XP alone changes nothing here.
"""
from __future__ import annotations

import logging
from typing import Any

import character_progression as core
from api.dnd_2024_rules import CharacterCreationError, get_equipment_armor_and_shield
from combat_lifecycle import CombatRequestError, player_incapacitated

logger = logging.getLogger(__name__)

KEY = "monk_state"
SUBCLASS = "open_hand"
PROOF = "worn_armor_v1"
DEFLECT_MODES = ("off", "reduce", "redirect")
_FIELDS = {"focus_spent", "metabolism_spent", "deflect"}
FOCUS_LEVEL = 2
OPEN_HAND_LEVEL = 3
DEFLECT_LEVEL = 3
STUNNING_STRIKE_LEVEL = 5
DEFLECT_DIE = 10
DEFLECT_TYPES = {"bludgeoning", "piercing", "slashing"}
REDIRECT_MELEE_FT = 5
REDIRECT_RANGED_FT = 60
OPEN_HAND_PUSH_FT = 15
OPEN_HAND_TECHNIQUES = ("push", "topple")  # Addle needs Opportunity Attacks against the player, which the engine does not have
_DEFAULT = {"focus_spent": 0, "metabolism_spent": False, "deflect": "reduce"}
# Timed effects kept in the attack owner's `attack_effects`; each ends at the start of the Monk's next turn.
STUN_EFFECT = "stunning_strike_stun"
SLOW_EFFECT = "stunning_strike_slow"
OPENING_EFFECT = "stunning_strike_opening"
_TIMED_EFFECTS = {STUN_EFFECT, SLOW_EFFECT, OPENING_EFFECT}
STRIKE_STEPS = {"martial_arts_strike", "flurry_of_blows", "flurry_strike"}
STEP_KINDS = STRIKE_STEPS | {"patient_defense", "step_of_the_wind", "uncanny_metabolism", "set_deflect_attacks"}


def monk_level(character: Any) -> int | None:
    """The applied Monk level, or None when this is not a verified Monk 1-5 (at 3+ the subclass choice must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Monk":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= OPEN_HAND_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def _cell(level: int, column: str) -> Any:
    try:
        return core.table("Monk")["levels"][str(level)][column]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Invalid Monk table value: {column}.") from error


def martial_arts_die(level: int) -> int:
    value = _cell(level, "martial_arts_die")
    if type(value) is not int or value < 2:
        raise ValueError("Invalid Martial Arts table value.")
    return value


def focus_maximum(level: int) -> int:
    value = _cell(level, "focus_points")
    if value is None:
        return 0
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Focus Points table value.")
    return value


def _movement_cell(level: int) -> int:
    value = _cell(level, "unarmored_movement_ft")
    if value is None:
        return 0
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Unarmored Movement table value.")
    return value


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: the record exists only on a verified Monk, with counts its applied level allows."""
    if KEY not in player:
        return
    level, state = monk_level(player), player[KEY]
    if (level is None or type(state) is not dict or set(state) != _FIELDS
            or type(state["focus_spent"]) is not int or not 0 <= state["focus_spent"] <= focus_maximum(level)
            or type(state["metabolism_spent"]) is not bool or (state["metabolism_spent"] and level < FOCUS_LEVEL)
            or state["deflect"] not in DEFLECT_MODES):
        raise ValueError("Kayıt Monk durum alanı geçersiz.")


def state_of(character: dict[str, Any]) -> dict[str, Any]:
    return {**_DEFAULT, **(character.get(KEY) or {})}


def save_dc(character: dict[str, Any]) -> int:
    """PDF 101: 8 plus your Wisdom modifier and Proficiency Bonus."""
    return 8 + character.get("wisdom_mod", 0) + character.get("proficiency_bonus", 0)


def _spend_focus(character: dict[str, Any]) -> None:
    state = state_of(character)
    state["focus_spent"] += 1
    character[KEY] = state


def _focus_left(character: dict[str, Any], level: int) -> int:
    return focus_maximum(level) - state_of(character)["focus_spent"]


def rest_recovery(session: Any, kind: str) -> None:
    """PDF 101: a finished Short or Long Rest regains all Focus Points; Uncanny Metabolism returns on a Long Rest. No record, nothing to do."""
    character = session.character
    if KEY not in character:
        return
    state = state_of(character)
    state["focus_spent"] = 0
    if kind == "long_rest":
        state["metabolism_spent"] = False
    character[KEY] = state


def initialize(session: Any, *, known_unarmored: bool) -> None:
    """Creation owner only: the same known-unarmored fact Barbarian's Rage owner records. Never adopted on load."""
    import barbarian_rage
    import equipment_economy
    if session.character.get("class") == "Monk" and known_unarmored and barbarian_rage._format(session) in (4, 5, 6):
        equipment_economy.initialize_unarmored_proof(session)


def unarmored(world: Any) -> bool:
    """Not wearing armor or wielding a Shield. The engine has no route to don either after creation, so the creation proof decides;
    a save without it (older than this slice) is read from what it carries, each time, and never written back."""
    if not isinstance(world, dict):
        return False
    proof = world.get(PROOF)
    if isinstance(proof, dict):
        return proof.get("armor_id") is None
    items = [item.get("name") if isinstance(item, dict) else item for item in world.get("inventory", [])]
    try:
        armor, shield = get_equipment_armor_and_shield([item for item in items if isinstance(item, str)])
    except CharacterCreationError:
        return False
    return armor is None and not shield


def monk_weapon(weapon: dict[str, Any]) -> bool:
    """PDF 100: Simple Melee weapons and Martial Melee weapons that have the Light property."""
    return weapon.get("kind") == "melee" and (weapon.get("category") == "simple"
                                              or (weapon.get("category") == "martial" and "light" in weapon.get("properties", [])))


def movement_bonus_ft(character: Any, world: Any) -> int:
    level = monk_level(character)
    return _movement_cell(level) if level is not None and unarmored(world) else 0


def held_profiles(session: Any, hands: Any = None) -> list[dict[str, Any]]:
    """Weapons really in hand. A save with no hand state, or the default sword it never owned, holds nothing rather than refusing."""
    import weapon_attack as attacks
    hands = hands if hands is not None else session.world_state.get("equipment")
    if not isinstance(hands, dict):
        return []
    owned = {hand: value for hand, value in hands.items() if isinstance(value, str) and session.find_weapon_in_inventory(value)[0]}
    return attacks._held_weapon_profiles(session, "player", session.character, owned)


def martial_arts_ready(session: Any) -> bool:
    data = session.character
    return (monk_level(data) is not None and unarmored(session.world_state)
            and all(monk_weapon(weapon) for weapon in held_profiles(session)))


def default_weapon(session: Any, selected: Any) -> Any:
    """A Monk holding no owned weapon attacks with an Unarmed Strike; anyone else keeps the existing refusal."""
    if monk_level(session.character) is None or (selected and session.find_weapon_in_inventory(selected)[0]):
        return selected
    return "unarmed"


def attack_rules(character: Any, world: Any, weapon: dict[str, Any], held: list[dict[str, Any]]) -> dict[str, Any]:
    """Martial Arts for the existing attack-rule owner: the better of Strength and Dexterity, and the die when it beats the weapon's."""
    level = monk_level(character)
    if (level is None or not (weapon["weapon_id"] == "unarmed" or monk_weapon(weapon)) or not unarmored(world)
            or not all(monk_weapon(each) for each in held)):
        return {}
    better = "dexterity" if character.get("dexterity_mod", 0) >= character.get("strength_mod", 0) else "strength"
    rules: dict[str, Any] = {"ability": better, "dexterous_attacks": True}
    die = martial_arts_die(level)
    if die > weapon["damage_die"]:
        rules.update(damage_die=die, damage_dice=1)
    return rules


def _fail(code: str, message: str | None = None) -> None:
    raise CombatRequestError(code, message or code, 400)


def _turn_id(session: Any) -> list[int]:
    combat = session.world_state["combat"]
    return [combat.get("round"), combat.get("current_turn_index")]


def _stunning_reason(session: Any, level: int | None) -> str | None:
    import weapon_attack as attacks
    if level is None or level < STUNNING_STRIKE_LEVEL:
        return "stunning_strike_not_available"
    if _focus_left(session.character, level) < 1:
        return "focus_points_exhausted"
    if attacks.sequence_snapshot(session, "player").get("stunning_strike_turn") == _turn_id(session):
        return "stunning_strike_used_this_turn"
    return None


def check_attack_choice(session: Any, actor: str, choice: dict[str, Any], weapon: dict[str, Any], origin: str, special: bool) -> None:
    """Both choices are declared with the attack, before the roll; nothing is spent unless it hits."""
    wanted, technique = choice.get("stunning_strike"), choice.get("open_hand_technique")
    if wanted is None and technique is None:
        return
    level = monk_level(session.character) if actor == "player" else None
    if wanted is not None:
        if type(wanted) is not bool:
            _fail("invalid_attack_choice", "Stunning Strike requires an explicit boolean.")
        if wanted:
            reason = _stunning_reason(session, level)
            if reason:
                _fail(reason)
            if special or not (weapon["weapon_id"] == "unarmed" or monk_weapon(weapon)):
                _fail("stunning_strike_weapon_required", "Stunning Strike needs a hit with a Monk weapon or an Unarmed Strike.")
    if technique is not None:
        if level is None or level < OPEN_HAND_LEVEL:
            _fail("open_hand_technique_not_available")
        if origin != "flurry":
            _fail("open_hand_technique_flurry_only", "Open Hand Technique applies to an attack granted by Flurry of Blows.")
        if technique not in OPEN_HAND_TECHNIQUES:
            _fail("invalid_attack_choice", "Unknown Open Hand Technique.")


def _stunning_strike(session: Any, target: str, defender: dict[str, Any]) -> dict[str, Any]:
    import weapon_attack as attacks
    character = session.character
    _spend_focus(character)
    attacks.turn_state(session, "player")["stunning_strike_turn"] = _turn_id(session)
    save = attacks.save(session, target, ("constitution",), save_dc(character), effect_context={"source": "Stunning Strike", "severity": "harmful"})
    if save["outcome"] == "FAILURE":
        added = "stunned" not in attacks.conditions(session, target, defender)
        attacks.add_condition(defender, "stunned")
        attacks.effect(session, STUN_EFFECT, "player", target)
        session.world_state["attack_effects"][-1]["condition_added"] = added
        return {"kind": "stunning_strike", "outcome": "stunned", "save": save}
    attacks.effect(session, SLOW_EFFECT, "player", target)
    attacks.effect(session, OPENING_EFFECT, "player", target)
    return {"kind": "stunning_strike", "outcome": "resisted", "save": save}


def _open_hand(session: Any, technique: str, target: str, defender: dict[str, Any]) -> dict[str, Any]:
    """PDF 106. The text names no DC of its own; the Monk's Focus save DC (PDF 101) is the reading used here."""
    import weapon_attack as attacks
    ability = "strength" if technique == "push" else "dexterity"
    save = attacks.save(session, target, (ability,), save_dc(session.character), effect_context={"source": "Open Hand Technique", "severity": "minor"})
    result: dict[str, Any] = {"kind": "open_hand_technique", "technique": technique, "save": save, "applied": False}
    if save["outcome"] != "FAILURE":
        return result
    if technique == "topple":
        attacks.add_condition(defender, "prone")
        result["applied"] = True
    else:
        result["push"] = attacks.push(session, "player", target, OPEN_HAND_PUSH_FT, size_limit=None)
        result["applied"] = result["push"]["applied"]
    return result


def after_hit(session: Any, context: dict[str, Any], defender: dict[str, Any]) -> list[dict[str, Any]]:
    """What a hit declared. A target the hit already took out makes no save and costs nothing."""
    if context["actor_id"] != "player" or defender.get("current_hp", 0) <= 0:
        return []
    results = []
    choice, target = context["choice"], context["target_id"]
    if choice.get("stunning_strike"):
        results.append(_stunning_strike(session, target, defender))
    if choice.get("open_hand_technique"):
        results.append(_open_hand(session, choice["open_hand_technique"], target, defender))
    return results


def _remove_condition(session: Any, identity: str, name: str) -> None:
    for npc in session.world_state.get("npcs", []):
        if isinstance(npc, dict) and npc.get("id") == identity:
            names = npc.get("conditions")
            if isinstance(names, dict):
                names.pop(name, None)
            elif isinstance(names, list) and name in names:
                names.remove(name)


def effect_ended(session: Any, effect: dict[str, Any]) -> None:
    """The attack owner removed a timed effect: a stun this strike added ends with it, one the target already had does not."""
    if effect.get("kind") == STUN_EFFECT and effect.get("condition_added") is True:
        _remove_condition(session, effect["target_id"], "stunned")


def validate_saved_effects(world: dict[str, Any], character: dict[str, Any]) -> None:
    """Timed effects exist only on an applied level-5 Monk in combat, with the exact expiry the strike wrote."""
    combat = world.get("combat", {})
    effects = world.get("attack_effects", [])
    if not isinstance(effects, list):
        return  # the attack owner refuses this shape
    for entry in effects:
        if not isinstance(entry, dict) or entry.get("kind") not in _TIMED_EFFECTS:
            continue
        level = monk_level(character)
        counter = combat.get("turn_resources", {}).get("player", {}).get("attack_turn_counter", 0)
        fields = {"kind", "source_actor", "target_id", "expires_turn", "expires_boundary"}
        if entry["kind"] == STUN_EFFECT:
            fields = fields | {"condition_added"}
        if (level is None or level < STUNNING_STRIKE_LEVEL or not combat.get("active") or set(entry) != fields
                or entry["source_actor"] != "player" or entry["expires_boundary"] != "begin"
                or type(counter) is not int or type(entry["expires_turn"]) is not int or entry["expires_turn"] != counter + 1
                or type(entry["target_id"]) is not str
                or (entry["kind"] == STUN_EFFECT and type(entry["condition_added"]) is not bool)):
            raise ValueError("Invalid saved Stunning Strike effect.")


def deflect_attacks(session: Any, context: dict[str, Any], damage: int, grouped: dict[str, int]) -> tuple[int, dict[str, Any] | None]:
    """A Reaction reduces the attack's total, before typed mitigation. Taken unless the setting is off or a readied Reaction is held."""
    import action_economy as economy
    character = session.character
    level = monk_level(character)
    if (context["actor_id"] == "player" or level is None or level < DEFLECT_LEVEL or damage <= 0
            or state_of(character)["deflect"] == "off" or not set(grouped) & DEFLECT_TYPES
            or not session.world_state.get("combat", {}).get("active")):
        return damage, None
    resources = economy.ensure(session).get("player")
    if not resources or resources["reaction_spent"] or resources.get("ready") or not economy.can_act(session, "player"):
        return damage, None
    roll = session.rng.randint(1, DEFLECT_DIE)
    reduction = max(0, roll + character.get("dexterity_mod", 0) + level)
    resources["reaction_spent"] = True
    return max(0, damage - reduction), {"kind": "deflect_attacks", "roll": roll, "reduction": reduction}


def redirect(session: Any, context: dict[str, Any], record: dict[str, Any] | None, remaining: int, damage_type: str) -> list[dict[str, Any]]:
    """Reduced to 0 on the redirect setting: 1 Focus Point, the attacker as the one offered creature, a Dexterity save or two dice."""
    import weapon_attack as attacks
    character = session.character
    level = monk_level(character)
    spatial = context["spatial"]
    reach = REDIRECT_MELEE_FT if context["mode"] == "melee" else REDIRECT_RANGED_FT
    if (record is None or remaining > 0 or state_of(character)["deflect"] != "redirect" or level is None
            or _focus_left(character, level) < 1 or spatial["distance_ft"] > reach or spatial.get("target_sees_attacker") is False):
        return []
    attacker_id = context["actor_id"]
    attacker = attacks.actor_data(session, attacker_id)
    _spend_focus(character)
    save = attacks.save(session, attacker_id, ("dexterity",), save_dc(character), effect_context={"source": "Deflect Attacks", "severity": "harmful"})
    result = {"kind": "deflect_redirect", "target_id": attacker_id, "save": save, "damage": 0, "damage_type": damage_type}
    if save["outcome"] == "FAILURE":
        rolls: list[int] = []
        raw = session.roll_damage(martial_arts_die(level), 2, character.get("dexterity_mod", 0), rolls=rolls)
        instance = attacks.mitigate(session, attacker_id, damage_type, max(0, raw))
        session.apply_npc_damage(attacker, instance["final_damage"])
        result.update(damage=instance["final_damage"], rolls=rolls)
    return [result]


def _turn_reason(session: Any, prefix: str) -> str | None:
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or combat.get("current_actor_id") != "player":
        return f"{prefix}_current_combat_turn_required"
    if player_incapacitated(session.character, session.world_state):
        return f"{prefix}_incapacitated"
    if combat.get("turn_resources", {}).get("player", {}).get("opportunity"):
        return "reaction_pending"
    return None


def _bonus_spent(session: Any) -> bool:
    return bool(session.world_state["combat"].get("turn_resources", {}).get("player", {}).get("bonus_action_spent"))


def _strike_reason(session: Any) -> str | None:
    if monk_level(session.character) is None:
        return "martial_arts_not_available"
    reason = _turn_reason(session, "martial_arts_strike")
    if reason:
        return reason
    if not martial_arts_ready(session):
        return "martial_arts_conditions_not_met"
    return "bonus_action_spent" if _bonus_spent(session) else None


def _focus_reason(session: Any, prefix: str, *, cost: int) -> str | None:
    level = monk_level(session.character)
    if level is None or level < FOCUS_LEVEL:
        return "focus_not_available"
    reason = _turn_reason(session, prefix)
    if reason:
        return reason
    if _bonus_spent(session):
        return "bonus_action_spent"
    return "focus_points_exhausted" if _focus_left(session.character, level) < cost else None


def _flurry_reason(session: Any) -> str | None:
    """PDF 101: a Focus feature, so the Martial Arts conditions gate its die and Dexterity, never the strikes themselves."""
    return _focus_reason(session, "flurry_of_blows", cost=1)


def _metabolism_reason(session: Any) -> str | None:
    """The engine rolls Initiative without a pause, so the choice stays open through the first round, on your own turn."""
    level = monk_level(session.character)
    if level is None or level < FOCUS_LEVEL:
        return "uncanny_metabolism_not_available"
    reason = _turn_reason(session, "uncanny_metabolism")
    if reason:
        return reason
    if session.world_state["combat"].get("round") != 1:
        return "uncanny_metabolism_initiative_only"
    return "uncanny_metabolism_used" if state_of(session.character)["metabolism_spent"] else None


def _flurry_grant(session: Any) -> dict[str, Any] | None:
    import action_economy as economy
    grants = economy.ensure(session).get("player", {}).get("bonus_grants", [])
    return next((grant for grant in grants if grant.get("source") == "flurry_of_blows" and grant.get("remaining", 0) > 0), None)


def _strike(session: Any, target_id: Any, choice: dict[str, Any], origin: str) -> dict[str, Any]:
    import action_economy as economy
    npc = economy.target(session, target_id)
    result = session.resolve_attack("Saldırıyorum.", "unarmed", None, npc, attack_choice=choice, origin=origin)
    session._combat_end_if_decided()
    economy.publish_event(session, "actor_attacks", "player")
    return result


def _martial_arts_strike(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    import action_economy as economy
    reason = _strike_reason(session)
    if reason:
        _fail(reason)
    economy.consume_feature_bonus(session)
    return {"attack": _strike(session, step.get("target_id"), step_choice(step), "martial_arts")}


def _flurry(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    import action_economy as economy
    reason = _flurry_reason(session)
    if reason:
        _fail(reason)
    _spend_focus(session.character)
    economy.consume_feature_bonus(session)
    economy.grant(session, "player", "flurry_of_blows", ["attack"], resource="bonus")
    attack = _strike(session, step.get("target_id"), step_choice(step), "flurry")
    return {"attack": attack, "strikes_remaining": 1}


def _flurry_strike(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    reason = _turn_reason(session, "flurry_strike")
    grant = _flurry_grant(session)
    if grant is None:
        _fail("flurry_strike_unavailable", "Flurry of Blows has no Unarmed Strike left this turn.")
    if reason:
        _fail(reason)
    grant["remaining"] -= 1
    return {"attack": _strike(session, step.get("target_id"), step_choice(step), "flurry"), "strikes_remaining": grant["remaining"]}


def _patient_defense(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    import action_economy as economy
    paid = step.get("spend_focus") is True
    reason = _focus_reason(session, "patient_defense", cost=1 if paid else 0)
    if reason:
        _fail(reason)
    if paid:
        _spend_focus(session.character)
    economy.consume_feature_bonus(session)
    resources = economy.ensure(session)["player"]
    resources["disengaging"] = True
    if paid:
        resources["dodging"] = True
    return {"disengage": True, "dodge": paid}


def _step_of_the_wind(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    """Dash on the existing movement ledger. `economy.dash` would spend an Orc's Adrenaline Rush for a Bonus Action Dash."""
    import action_economy as economy
    paid = step.get("spend_focus") is True
    reason = _focus_reason(session, "step_of_the_wind", cost=1 if paid else 0)
    if reason:
        _fail(reason)
    if paid:
        _spend_focus(session.character)
    economy.consume_feature_bonus(session)
    resources = economy.ensure(session)["player"]
    added = economy.speed(session, "player")
    resources["dash_count"] = resources.get("dash_count", 0) + 1
    resources["movement_available"] = max(resources["movement_used"], economy.movement_limit(session, "player"))
    if paid:
        resources["disengaging"] = True
    return {"movement_added_ft": added, "disengage": paid}


def _uncanny_metabolism(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    reason = _metabolism_reason(session)
    if reason:
        _fail(reason)
    character = session.character
    level = monk_level(character)
    roll = session.rng.randint(1, martial_arts_die(level))
    healing = session.heal_player(level + roll)
    state = state_of(character)
    state.update(focus_spent=0, metabolism_spent=True)
    character[KEY] = state
    return {"roll": roll, "healing": healing, "heal_source": "class_feature", "current_hp": character["current_hp"]}


def _set_deflect(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    level = monk_level(session.character)
    if level is None or level < DEFLECT_LEVEL:
        _fail("deflect_attacks_not_available")
    state = state_of(session.character)
    state["deflect"] = step["deflect_mode"]
    session.character[KEY] = state
    return {"deflect_mode": state["deflect"]}


def step_choice(step: dict[str, Any]) -> dict[str, Any]:
    """The Monk fields of a typed step, as attack choices. Absent stays absent, so other classes send the attack owner nothing new."""
    return {key: step[key] for key in ("stunning_strike", "open_hand_technique") if step.get(key) is not None}


def run_step(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    """Rollback belongs to `action_economy.execute`, the only caller."""
    handlers = {"martial_arts_strike": _martial_arts_strike, "flurry_of_blows": _flurry, "flurry_strike": _flurry_strike,
                "patient_defense": _patient_defense, "step_of_the_wind": _step_of_the_wind,
                "uncanny_metabolism": _uncanny_metabolism, "set_deflect_attacks": _set_deflect}
    return handlers[step["kind"]](session, step)


_STEP_FIELDS = {"martial_arts_strike": {"target_id", "stunning_strike", "open_hand_technique"},
                "flurry_of_blows": {"target_id", "stunning_strike", "open_hand_technique"},
                "flurry_strike": {"target_id", "stunning_strike", "open_hand_technique"},
                "patient_defense": {"spend_focus"}, "step_of_the_wind": {"spend_focus"},
                "uncanny_metabolism": set(), "set_deflect_attacks": {"deflect_mode"}}


def _step_shape_ok(step: Any) -> bool:
    kind = step.get("kind") if type(step) is dict else None
    # A parsed public step carries the default action resource; these steps say what they spend by their kind.
    if kind not in _STEP_FIELDS or set(step) - {"kind", "resource"} - _STEP_FIELDS[kind] or step.get("resource", "action") != "action":
        return False
    if kind in STRIKE_STEPS and (type(step.get("target_id")) is not str
                                 or ("open_hand_technique" in step and step["open_hand_technique"] not in OPEN_HAND_TECHNIQUES)
                                 or ("stunning_strike" in step and type(step["stunning_strike"]) is not bool)):
        return False
    if "spend_focus" in step and type(step["spend_focus"]) is not bool:
        return False
    return kind != "set_deflect_attacks" or step.get("deflect_mode") in DEFLECT_MODES


def native_command(command: Any) -> bool:
    """Exactly one typed Monk step; Flurry's second strike is its own command, so a refusal never leaves half a sequence."""
    steps = command.get("steps") if type(command) is dict else None
    return type(steps) is list and len(steps) == 1 and _step_shape_ok(steps[0])


def narration(session: Any, step: dict[str, Any]) -> str:
    result, kind = step["result"], step["kind"]
    if kind in STRIKE_STEPS:
        return session._combat_narration(result["attack"])
    if kind == "patient_defense":
        return "Bonus eylem ile Sabırlı Savunma: Disengage" + (" ve Dodge." if result["dodge"] else ".")
    if kind == "step_of_the_wind":
        return f"Bonus eylem ile Rüzgâr Adımı: bu tur {result['movement_added_ft']} fit daha hareket edebilirsin."
    if kind == "uncanny_metabolism":
        return f"Uncanny Metabolism: Focus Points yenilenir, {result['healing']} can puanı kazanırsın."
    return f"Deflect Attacks ayarı: {result['deflect_mode']}."


def _available(reason: str | None) -> dict[str, Any]:
    return {"available": reason is None, "reason": reason}


def disclosure(level: int) -> dict[str, list[str]]:
    die = martial_arts_die(level)
    supported = [
        f"Martial Arts: 1d{die} in place of the normal damage when larger, Dexterity for attack, damage and the Grapple or Shove DC, and a Bonus Action Unarmed Strike, while unarmed or wielding only Monk weapons and known to be unarmored",
        "Unarmored Defense: 10 + DEX + WIS is the creation Armor Class, on the same owner as Barbarian's formula, and follows a Wisdom modifier rise at level 4",
        "Monk weapon proficiency: Simple weapons and Martial weapons with the Light property, read at each attack",
    ]
    pending = [
        "Unarmored state: there is no general armor owner; the creation fact decides, and a save without it counts as unarmored only if it carries no armor or Shield",
        "Attack rolls use the better of Strength and Dexterity unless Strength is requested; the Martial Arts die replaces a smaller weapon die automatically",
        "Monk equipment packages are the existing catalog lists, not yet the PHB packages; the Artisan's Tools or Musical Instrument choice is not offered",
        "Weapon Mastery does not exist for the Monk; other Monk subclasses and higher-level features remain unsupported",
    ]
    if level >= FOCUS_LEVEL:
        supported.extend([
            f"Focus Points: {focus_maximum(level)} points, all back on a finished Short or Long Rest; save DC 8 + WIS + Proficiency Bonus",
            "Flurry of Blows: 1 Focus Point and the Bonus Action for two Unarmed Strikes, each its own step",
            "Patient Defense: Disengage as a Bonus Action (records the state only, no effect yet), or 1 Focus Point to add Dodge",
            "Step of the Wind: Dash as a Bonus Action, or 1 Focus Point to add Disengage (records the state only, no effect yet)",
            f"Unarmored Movement: +{_movement_cell(level)} ft Speed while known to be unarmored",
            "Uncanny Metabolism: all Focus Points and the Martial Arts die + Monk level Hit Points, once per Long Rest",
        ])
        pending.extend([
            "Disengage has no separate effect: the engine has no Opportunity Attacks against the player's movement",
            "Dodge gives Disadvantage only when the engine knows the player sees the attacker (existing Dodge owner)",
            "Step of the Wind: doubled jump distance has no effect, the engine has no jump owner",
            "Uncanny Metabolism: Initiative is rolled without a pause, so the choice stays open on your own turn in the first round instead of at the roll",
        ])
    if level >= DEFLECT_LEVEL:
        supported.extend([
            "Deflect Attacks: when a melee or ranged weapon attack roll hits for Bludgeoning, Piercing or Slashing, a Reaction reduces the total by 1d10 + DEX + Monk level; a setting chooses off, reduce or redirect",
            "Deflect Attacks redirect: on the redirect setting, an attack reduced to 0 spends 1 Focus Point; the attacker makes a Dexterity save or takes two Martial Arts dice + DEX",
            "Selected Warrior of the Open Hand: Open Hand Technique Push or Topple, declared with a Flurry of Blows attack",
        ])
        pending.extend([
            "Deflect Attacks is decided by the setting at the hit, with no prompt, so it takes the first eligible hit each round; a held Ready keeps its Reaction",
            "Deflect Attacks redirect targets only the attacker, never another creature",
            "Deflect Attacks reduces the damage before Resistance and other typed reductions; the text does not fix the order, so this is the reading used",
            "Open Hand Technique: Addle is not offered, the engine has no Opportunity Attacks to stop; Push needs a known clear line; the text names no DC, so the Focus save DC is the reading used",
        ])
    if level >= 4:
        supported.append("Selected level4 ordinary Ability Score Improvement supported, Dexterity included; a choice that moves the Dexterity modifier is refused only when the Armor Class total cannot be tied to its creation armor")
        pending.extend(["Slow Fall: no effect, the engine has no fall damage owner",
                        "Other feats remain unsupported"])
    if level >= STUNNING_STRIKE_LEVEL:
        supported.extend([
            "Extra Attack: two attacks instead of one when taking the Attack action on your own turn (shared allowance owner)",
            "Stunning Strike: once per turn on a hit with a Monk weapon or Unarmed Strike, 1 Focus Point and a Constitution save; Stunned on a failure, or halved Speed and Advantage on the next attack roll on a success, until the start of your next turn",
        ])
        pending.append("Stunning Strike is declared with the attack, before the roll, and costs nothing on a miss; it cannot be decided after seeing the hit; the panel offers it on the Attack action only, not on Flurry or the Bonus Action strike")
    return {"supported": supported, "pending": pending}


def projection(session: Any) -> dict[str, Any] | None:
    """The public block. Invalid saved state hides the controls, as Rage does, and leaves a log line; any other fault is a real error."""
    character = session.character
    try:
        level = monk_level(character)
        if level is None:
            return None
        validate_saved(character)
        state = state_of(character)
        maximum = focus_maximum(level)
        focus = level >= FOCUS_LEVEL
        grant = _flurry_grant(session) if session.world_state.get("combat", {}).get("active") else None
        return {
            "martial_arts_die": martial_arts_die(level),
            "martial_arts_ready": martial_arts_ready(session),
            "movement_bonus_ft": movement_bonus_ft(character, session.world_state),
            "save_dc": save_dc(character),
            "focus": {"points_remaining": maximum - state["focus_spent"], "max_points": maximum} if focus else None,
            "martial_arts_strike": _available(_strike_reason(session)),
            "flurry_of_blows": _available(_flurry_reason(session)) if focus else None,
            "flurry_strikes_remaining": grant["remaining"] if grant else 0,
            "patient_defense": _available(_focus_reason(session, "patient_defense", cost=0)) if focus else None,
            "step_of_the_wind": _available(_focus_reason(session, "step_of_the_wind", cost=0)) if focus else None,
            "uncanny_metabolism": _available(_metabolism_reason(session)) if focus else None,
            "stunning_strike": _available(_stunning_reason(session, level) if session.world_state.get("combat", {}).get("active") else "stunning_strike_combat_required") if level >= STUNNING_STRIKE_LEVEL else None,
            "deflect_mode": state["deflect"] if level >= DEFLECT_LEVEL else None,
            "open_hand_techniques": list(OPEN_HAND_TECHNIQUES) if level >= OPEN_HAND_LEVEL else [],
        }
    except ValueError as error:
        logger.warning("Monk controls hidden: %s", error)
        return None
