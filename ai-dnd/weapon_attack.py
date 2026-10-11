"""Shared PHB 2024 weapon/Unarmed Strike resolution.

Callers own turns and receipts. This module owns mechanics, not tactical choices.
Spatial facts and feature grants are engine-only data, never narration-derived.
"""
import copy
import re
from math import isfinite
from contextlib import nullcontext
from uuid import uuid4

import action_economy as economy
import initiative
from combat_lifecycle import CombatRequestError
from api.core_resolution import resolve_attack_roll, resolve_saving_throw, resolution_identity, resolution_action_scope
from weapon_catalog import lookup

DAMAGE_TYPES = frozenset("acid bludgeoning cold fire force lightning necrotic piercing poison psychic radiant slashing thunder".split())
MASTERY = frozenset("cleave graze nick push sap slow topple vex".split())
SIZES = ("tiny", "small", "medium", "large", "huge", "gargantuan")
CHOICES = frozenset({
    "mode", "ability", "grip", "mastery", "push_ft", "cleave_target_id",
    "unarmed_option", "shove_option", "target_save_ability", "draw", "unequip", "weapon_instance_id",
})


def fail(code, message):
    raise CombatRequestError(code, message, 400)


def integer(value, name, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        fail("invalid_attack_state", f"Invalid authoritative {name}.")
    return value


def exhaustion(data):
    """PHB2024 condition level; missing legacy fields mean no exhaustion."""
    level = data.get("exhaustion", 0)
    if type(level) is not int or not 0 <= level <= 6:
        fail("invalid_exhaustion", "Tükenmişlik seviyesi geçersiz.")
    return level


def saving_bonus(data, ability):
    modifier = data.get("modifiers", {}).get(ability, data.get(ability + "_mod", 0))
    total = data.get("saving_throw_mods", {}).get(ability, data.get(ability + "_save_bonus", modifier))
    return modifier, total - modifier - 2 * exhaustion(data)


def add_exhaustion(session, cause, *, deaths=None):
    if exhaustion(session.character) == 6:
        return 6
    session.character["exhaustion"] = min(6, exhaustion(session.character) + 1)
    if session.character["exhaustion"] == 6:
        resolution = session._finalize_player_death(cause)
        if deaths is not None:
            deaths.append({"death_resolution": resolution})
    return session.character["exhaustion"]


def actor_data(session, identity):
    if identity == "player":
        return session.character
    values = [n for n in session.world_state.get("npcs", [])
              if isinstance(n, dict) and n.get("id") == identity
              and n.get("location") == session.world_state.get("location")]
    if len(values) != 1:
        fail("invalid_combat_target", "Target must be one canonical local creature.")
    return values[0]


def conditions(session, identity, data):
    names = data.get("conditions", [])
    if isinstance(names, dict):
        names = [name for name, present in names.items() if present]
    result = {str(name).lower() for name in names}
    if data.get("prone"):
        result.add("prone")
    status = (session.world_state.get("player_combat_status", "active")
              if identity == "player" else data.get("combat_status", "active"))
    if status != "active":
        result.add(status)
    if identity == "player" and session.world_state.get("death_state", {}).get("prone"):
        result.add("prone")
    return result


def equipment(session, actor, data):
    state = session.world_state.get("equipment") if actor == "player" else data.get("equipment")
    if not isinstance(state, dict) or set(state) != {"main_hand", "off_hand"}:
        fail("equipment_unknown", "Authoritative hand/equipment state is required.")
    return state


def inventory(session, actor, data):
    return session.world_state.get("inventory", []) if actor == "player" else data.get("inventory", [])


def item_for(session, actor, data, weapon, instance=None):
    for item in inventory(session, actor, data):
        identity = item.get("weapon_id", item.get("name")) if isinstance(item, dict) else item
        candidate = lookup(identity)
        reference = item.get("item_id", candidate["weapon_id"]) if isinstance(item, dict) and candidate else candidate["weapon_id"] if candidate else None
        if candidate and candidate["weapon_id"] == weapon["weapon_id"] and (instance is None or reference == instance):
            return item
    fail("no_weapon", "The requested weapon is not in authoritative inventory.")


def held_identity(session, actor, data, value):
    """Unique owned item IDs distinguish two weapons of the same catalog type."""
    items = inventory(session, actor, data)
    for item in items:
        if isinstance(item, dict) and item.get("item_id") == value:
            return value
    weapon = lookup(value)
    if weapon is not None:
        matches = [
            item for item in items
            if isinstance(item, dict)
            and isinstance(item.get("item_id"), str)
            and (
                item.get("weapon_id") == weapon["weapon_id"]
                or item.get("name") == value
            )
        ]
        if len(matches) == 1:
            return matches[0]["item_id"]
        return weapon["weapon_id"]
    return value


def pair(session, actor, target):
    """Minimal spatial interface; absent distance is an error, never a guess."""
    pairs = session.world_state.get("attack_environment", {}).get("pairs", {})
    value = pairs.get(f"{actor}|{target}", pairs.get(f"{target}|{actor}", {}))
    result = copy.deepcopy(value)
    if "distance_ft" not in result and "player" in (actor, target):
        npc = actor_data(session, target if actor == "player" else actor)
        if "distance_ft" in npc:
            result["distance_ft"] = npc["distance_ft"]
    distance = result.get("distance_ft")
    if type(distance) not in (int, float) or not isfinite(distance) or distance < 0:
        fail("distance_unknown", "Authoritative attack distance is unavailable.")
    # Directional visibility/cover uses an actor→target entry, not its reverse.
    if f"{actor}|{target}" not in pairs:
        result = {"distance_ft": distance}
    return result


def modifiers(values, name):
    if not isinstance(values, list):
        fail("invalid_attack_state", f"{name} must be sourced modifiers.")
    seen, total = set(), 0
    for entry in values:
        source = entry.get("source") if isinstance(entry, dict) else None
        if not isinstance(source, str) or not source or source in seen:
            fail("invalid_attack_state", f"Duplicate/missing {name} source.")
        seen.add(source)
        total += integer(entry.get("value"), name)
    return total


def register_hook(session, event, callback):
    if event not in {"attack_rules", "after_attack", "after_damage", "after_mastery"} or not callable(callback):
        raise ValueError("Invalid engine-only attack feature hook.")
    if not hasattr(session, "_attack_hooks"):
        session._attack_hooks = {}
    session._attack_hooks.setdefault(event, []).append(callback)


def hook(session, event, context):
    outputs = []
    for callback in getattr(session, "_attack_hooks", {}).get(event, []):
        value = callback(session, copy.deepcopy(context))
        if value is not None:
            outputs.append(copy.deepcopy(value))
    return outputs


def rules_for(session, actor, data, weapon):
    rules = copy.deepcopy(data.get("attack_rules", {}))
    for grant in hook(session, "attack_rules", {"actor_id": actor, "weapon_id": weapon["weapon_id"]}):
        if not isinstance(grant, dict) or not grant.get("source"):
            fail("invalid_attack_state", "Feature rules require provenance.")
        for key, value in grant.items():
            if key == "source":
                continue
            if key in {"attack_modifiers", "damage_modifiers", "additional_damage",
                       "advantage_sources", "disadvantage_sources"}:
                rules.setdefault(key, []).extend(value)
            elif key not in rules:
                rules[key] = value
            else:
                fail("invalid_attack_state", "Conflicting authoritative feature overrides.")
    allowed = {"ability", "damage_die", "damage_dice", "damage_modifier",
               "attack_modifiers", "damage_modifiers", "additional_damage",
               "advantage_sources", "disadvantage_sources", "mastery_overrides"}
    if set(rules) - allowed:
        fail("invalid_attack_state", "Unsupported attack feature rule.")
    return rules


def turn_state(session, actor):
    combat = session.world_state["combat"]
    if not combat["active"]:
        fail("combat_required", "Attacks require the authoritative combat owner.")
    return economy.ensure(session)[actor].setdefault("weapon_sequence", {
        "attacks": 0, "light_weapon_ids": [], "light_used": False,
        "cleave_used": False, "loading_origins": [],
    })


def sequence_snapshot(session, actor):
    return session.world_state.get("combat", {}).get("turn_resources", {}).get(actor, {}).get(
        "weapon_sequence", {"attacks": 0, "light_weapon_ids": [], "light_used": False,
                            "cleave_used": False, "loading_origins": []})


def prepare(session, actor, target, weapon_id=None, choice=None, *, origin="action", profile=None):
    choice = copy.deepcopy(choice or {})
    if set(choice) - CHOICES:
        fail("invalid_attack_choice", "Only player choices, never mechanical numbers, are accepted.")
    attacker, defender = actor_data(session, actor), actor_data(session, target)
    combat = session.world_state.get("combat", {})
    if combat.get("combat_id") and not combat["active"]:
        fail("combat_closed", "Combat is closed.")
    if combat["active"]:
        if actor not in combat["participants"] or target not in combat["participants"] or actor == target:
            fail("invalid_combat_target", "Attack identities must be distinct participants.")
        if origin == "action":
            economy.attack_permission(session, actor)
        elif origin in {"continuation", "light", "nick", "cleave"}:
            economy.validate_actor(session, actor, reaction=
                                   economy._execution.get() == (id(session), "monster_capability", actor))
        elif origin == "reaction":
            if economy._execution.get() != (id(session), "reaction", actor):
                fail("invalid_reaction_trigger", "No authorized Reaction context.")
            economy.attack_permission(session, actor)
        else:
            fail("invalid_attack_origin", "Unknown authoritative attack origin.")
    aconditions = conditions(session, actor, attacker)
    tconditions = conditions(session, target, defender)
    if aconditions & {"unconscious", "incapacitated", "paralyzed", "stunned", "dead", "petrified"}:
        fail("actor_cannot_act", "Authoritative conditions prohibit this attack.")
    if "dead" in tconditions:
        fail("invalid_combat_target", "Dead creatures cannot be attacked.")
    spatial = pair(session, actor, target)
    distance = spatial["distance_ft"]
    unarmed = weapon_id == "unarmed"
    if profile is not None:
        weapon = copy.deepcopy(profile)
    elif unarmed:
        weapon = {"weapon_id": "unarmed", "name": "Unarmed Strike", "kind": "melee",
                  "category": None, "properties": [], "mastery": None, "damage_die": 0,
                  "damage_dice": 0, "fixed_damage": 1, "damage_type": "bludgeoning",
                  "magic_attack_bonus": 0, "magic_damage_bonus": 0}
    else:
        weapon = copy.deepcopy(lookup(weapon_id))
        if not weapon:
            fail("no_weapon", "Unknown catalog weapon.")
        hands = copy.deepcopy(equipment(session, actor, attacker))
        requested_instance = choice.get("weapon_instance_id")
        if requested_instance is None and origin in {"light", "nick"}:
            previous = sequence_snapshot(session, actor)["light_weapon_ids"]
            for held_value in hands.values():
                try:
                    candidate = item_for(session, actor, attacker, weapon, held_value)
                except CombatRequestError:
                    continue
                candidate_ref = candidate.get("item_id", weapon["weapon_id"]) if isinstance(candidate, dict) else weapon["weapon_id"]
                if candidate_ref not in previous:
                    requested_instance = candidate_ref
                    break
        item = item_for(session, actor, attacker, weapon, requested_instance)
        weapon["instance_id"] = item.get("item_id", weapon["weapon_id"]) if isinstance(item, dict) else weapon["weapon_id"]
        if isinstance(item, dict):
            for name in ("magic_attack_bonus", "magic_damage_bonus"):
                weapon[name] = integer(item.get(name, 0), name)
        held = [held_identity(session, actor, attacker, value) for value in hands.values()]
        if choice.get("unequip"):
            old = choice["unequip"]
            matches = [hand for hand, value in hands.items() if value == old]
            if len(matches) != 1 or origin not in {"action", "continuation"}:
                fail("invalid_equipment_change", "Unequip needs one held weapon and an Attack Action.")
            hands[matches[0]] = None
            held = [held_identity(session, actor, attacker, value) for value in hands.values()]
        if weapon["instance_id"] not in held:
            if choice.get("draw") and (origin in {"action", "continuation"} or "thrown" in weapon["properties"]):
                free = next((hand for hand, value in hands.items() if value is None), None)
                if free is None:
                    fail("invalid_hands", "No hand is available to draw the weapon.")
                hands[free] = weapon["instance_id"]
            else:
                fail("weapon_not_held", "Requested weapon is not held.")
        grip = choice.get("grip", 2 if "two-handed" in weapon["properties"] else 1)
        if grip not in (1, 2) or (grip == 2 and not ({"two-handed", "versatile"} & set(weapon["properties"]))):
            fail("invalid_grip", "Invalid weapon grip.")
        free_hands = sum(value is None for value in hands.values())
        two_required = "two-handed" in weapon["properties"]
        if (two_required and grip != 2) or (grip == 2 and free_hands < 1):
            fail("invalid_hands", "Two-handed attack needs both hands.")
        if "ammunition" in weapon["properties"] and grip == 1 and free_hands < 1:
            fail("invalid_hands", "A one-handed ammunition weapon requires a free loading hand.")
        weapon["grip"] = grip
        weapon["equipment_after"] = hands
    props = set(weapon["properties"])
    mode = choice.get("mode", weapon["kind"])
    if mode not in {"melee", "ranged", "thrown"} or (
        mode == "thrown" and "thrown" not in props
    ) or (mode == "melee" and weapon["kind"] != "melee") or (
        mode == "ranged" and weapon["kind"] != "ranged"
    ):
        fail("invalid_weapon_mode", "Weapon does not support the requested attack mode.")
    if mode == "melee":
        if distance > (10 if "reach" in props else 5):
            fail("out_of_range", "Target is outside authoritative melee reach.")
    elif distance > weapon["long_range"]:
        fail("out_of_range", "Target is beyond the weapon's long range.")
    covers = spatial.get("cover", [])
    covers = [covers] if isinstance(covers, str) else covers
    if not isinstance(covers, list) or set(covers) - {"none", "half", "three_quarters", "total"}:
        fail("invalid_attack_state", "Unknown authoritative cover.")
    cover = max(covers or ["none"], key=lambda c: {"none": 0, "half": 2, "three_quarters": 5, "total": 99}[c])
    if cover == "total":
        fail("total_cover", "Total Cover prevents direct targeting.")
    rules = rules_for(session, actor, attacker, weapon)
    ability = rules.get("ability", "strength" if weapon["kind"] == "melee" else "dexterity")
    requested_ability = choice.get("ability")
    if requested_ability:
        if requested_ability not in ({"strength", "dexterity"} if "finesse" in props else {ability}):
            fail("invalid_attack_ability", "The weapon/feature does not permit that ability.")
        ability = requested_ability
    if ability not in {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}:
        fail("invalid_attack_state", "Unknown authoritative attack ability.")
    ability_mod = integer(attacker.get(f"{ability}_mod", 0), "ability modifier")
    pb = integer(attacker.get("proficiency_bonus", 0), "proficiency bonus", 0)
    proficiency = attacker.get("weapon_proficiencies", ["longsword"] if actor == "player" else [])
    proficient = unarmed or weapon["weapon_id"] in proficiency or weapon["category"] in proficiency
    attack_modifiers = copy.deepcopy(rules.get("attack_modifiers", []))
    damage_modifiers = copy.deepcopy(rules.get("damage_modifiers", []))
    attack_adjustment = modifiers(attack_modifiers, "attack modifiers")
    damage_adjustment = modifiers(damage_modifiers, "damage modifiers")
    if any(m["source"] in {"ability", "proficiency", "magic_weapon"} for m in attack_modifiers + damage_modifiers):
        fail("invalid_attack_state", "Base sources cannot be applied twice.")
    if profile:
        ability_mod = integer(profile["damage_modifier"], "stat-block damage modifier")
        ability = "stat_block"
        proficient, pb = False, 0
        bonus = integer(profile["attack_bonus"], "stat-block attack bonus") + attack_adjustment
    else:
        bonus = ability_mod + (pb if proficient else 0) + weapon["magic_attack_bonus"] + attack_adjustment
    advantage = list(rules.get("advantage_sources", []))
    disadvantage = list(rules.get("disadvantage_sources", []))
    for names in (advantage, disadvantage):
        if any(not isinstance(source, str) or not source for source in names):
            fail("invalid_attack_state", "Attack advantage sources require provenance.")
    if aconditions & {"blinded", "poisoned", "prone", "restrained"}:
        disadvantage.extend(sorted(aconditions & {"blinded", "poisoned", "prone", "restrained"}))
    if "grappled" in aconditions and attacker.get("grappled_by") != target:
        disadvantage.append("grappled_other_target")
    if tconditions & {"blinded", "restrained", "stunned", "unconscious", "paralyzed"}:
        advantage.extend("target_" + name for name in sorted(tconditions & {"blinded", "restrained", "stunned", "unconscious", "paralyzed"}))
    if "prone" in tconditions:
        (advantage if distance <= 5 else disadvantage).append("target_prone")
    if "invisible" in aconditions:
        advantage.append("invisible_attacker")
    if "invisible" in tconditions:
        disadvantage.append("invisible_target")
    if spatial.get("attacker_sees_target") is False:
        disadvantage.append("unseen_target")
    if spatial.get("target_sees_attacker") is False:
        advantage.append("unseen_attacker")
    # Dodge is owned by #04; #06 only consumes its verified attack modifier.
    defending = combat.get("turn_resources", {}).get(target, {})
    if (defending.get("dodging") is True and economy.can_act(session, target)
            and economy.speed(session, target) > 0 and spatial.get("target_sees_attacker") is True):
        disadvantage.append("target_dodging")
    if "heavy" in props:
        score = "strength" if weapon["kind"] == "melee" else "dexterity"
        if integer(attacker.get(score), "Heavy ability score", 1) < 13:
            disadvantage.append("heavy")
    auto_miss = spatial.get("guessed_location_correct") is False
    underwater = session.world_state.get("attack_environment", {}).get("underwater") is True
    if mode != "melee":
        if distance > weapon["normal_range"]:
            disadvantage.append("long_range")
        if underwater:
            auto_miss |= distance > weapon["normal_range"]
            disadvantage.append("underwater")
        for enemy in combat.get("participants", []):
            if enemy == actor:
                continue
            enemy_data = actor_data(session, enemy)
            same_side = (enemy == "player") == (actor == "player")
            if same_side or conditions(session, enemy, enemy_data) & {
                "incapacitated", "unconscious", "stunned", "paralyzed", "dead", "petrified"
            }:
                continue
            nearby = pair(session, actor, enemy)
            if nearby["distance_ft"] <= 5 and nearby.get("target_sees_attacker", True) and "blinded" not in conditions(session, enemy, enemy_data):
                disadvantage.append("ranged_in_close_combat")
    elif underwater and not unarmed and attacker.get("swim_speed_ft", 0) <= 0 and weapon["damage_type"] != "piercing":
        disadvantage.append("underwater")
    frightened = attacker.get("frightened_until_player_turn")
    if "frightened" in aconditions:
        fear_visible = (attacker.get("frightened_by") == target
                        and spatial.get("attacker_sees_target") is True
                        and "blinded" not in aconditions and "invisible" not in tconditions
                        and not defender.get("hidden", False))
    else:
        # Compatibility for the existing timed species effect only; canonical
        # condition/source facts take precedence whenever present.
        fear_visible = (type(frightened) is int and frightened >
                        (session.character.get("species_trait_state") or {}).get("player_turn_counter", 0))
    if fear_visible and "frightened" not in disadvantage:
        disadvantage.append("frightened")
    for effect in session.world_state.get("attack_effects", []):
        if effect["kind"] == "sap" and effect["target_id"] == actor:
            disadvantage.append("sap")
        if effect["kind"] == "vex" and effect["source_actor"] == actor and effect["target_id"] == target:
            advantage.append("vex")
    mastery = None
    if not unarmed and not profile:
        eligible = weapon["weapon_id"] in attacker.get("weapon_masteries", [])
        mastery = weapon["mastery"] if eligible else None
        requested = choice.get("mastery")
        if requested == "none":
            mastery, requested = None, None
        if requested:
            if requested not in MASTERY or not eligible or (
                requested != mastery and requested not in rules.get("mastery_overrides", [])
            ):
                fail("mastery_unavailable", "Requested mastery is not granted by authoritative features.")
            mastery = requested
    elif choice.get("mastery"):
        fail("mastery_unavailable", "Unarmed/stat-block attacks do not have weapon mastery.")
    sequence = sequence_snapshot(session, actor)
    if origin in {"light", "nick"}:
        if ("light" not in props or sequence["light_used"] or not sequence["light_weapon_ids"]
            or weapon["instance_id"] in sequence["light_weapon_ids"]):
            fail("light_unavailable", "Light requires a different Light weapon and one unused extra attack.")
        if origin == "nick" and mastery != "nick":
            fail("nick_unavailable", "Nick mastery is required.")
        if origin == "light" and economy.ensure(session)[actor]["bonus_action_spent"]:
            fail("bonus_action_spent", "The Bonus Action has already been spent.")
    if origin == "continuation":
        ongoing = economy.ensure(session)[actor].get("attack_action")
        if not ongoing or ongoing["remaining_attacks"] <= 0:
            fail("no_attack_continuation", "No rule-granted Attack Action continuation.")
    loading_key = f"action:{sequence.get('action_index', 0)}" if origin == "action" else origin
    if origin in {"continuation", "nick", "cleave"}:
        loading_key = sequence.get("active_action_key", "action:0")
    if origin == "light":
        loading_key = "bonus"
    if "loading" in props and loading_key in sequence["loading_origins"]:
        fail("loading_limit", "Loading permits one shot per Action/Bonus Action/Reaction.")
    ammunition = None
    if "ammunition" in props:
        ammunition = weapon["ammunition_type"]
        ammo = (session.world_state if actor == "player" else attacker).get("ammunition", {})
        if integer(ammo.get(ammunition, 0), "ammunition", 0) < 1:
            fail("no_ammunition", "Required ammunition is unavailable.")
    unarmed_option = choice.get("unarmed_option", "damage")
    if unarmed_option not in {"damage", "grapple", "shove"} or (not unarmed and unarmed_option != "damage"):
        fail("invalid_unarmed_option", "Unknown Unarmed Strike option.")
    if unarmed and unarmed_option in {"grapple", "shove"}:
        if SIZES.index(defender.get("size", "medium")) > SIZES.index(attacker.get("size", "medium")) + 1:
            fail("invalid_target_size", "Target is more than one size larger.")
        if unarmed_option == "grapple" and not any(value is None for value in equipment(session, actor, attacker).values()):
            fail("invalid_hands", "Grapple requires a free hand.")
        if choice.get("shove_option", "prone") not in {"prone", "push"}:
            fail("invalid_shove_choice", "Choose Prone or a 5-foot push.")
    if choice.get("cleave_target_id"):
        if mastery != "cleave" or mode != "melee" or sequence["cleave_used"]:
            fail("cleave_unavailable", "No unused Cleave mastery trigger.")
        second = choice["cleave_target_id"]
        if second in {actor, target} or second not in combat["participants"]:
            fail("invalid_cleave_target", "Cleave needs a second canonical creature.")
        if pair(session, target, second)["distance_ft"] > 5:
            fail("invalid_cleave_target", "Second target must be within 5 feet of the first.")
        # Validate the complete second attack before committing the first.
        prepare(session, actor, second, weapon_id, {k: v for k, v in choice.items() if k != "cleave_target_id"},
                origin="cleave", profile=profile)
    if choice.get("push_ft") is not None:
        integer(choice["push_ft"], "push choice", 0)
        if choice["push_ft"] > 10 or mastery != "push":
            fail("invalid_push_choice", "Push choice is not supported.")
    die = rules.get("damage_die", weapon["damage_die"])
    count = rules.get("damage_dice", weapon["damage_dice"])
    if "damage_die" in rules or "damage_dice" in rules:
        weapon["fixed_damage"] = None
    integer(die, "damage die", 0)
    integer(count, "damage dice", 0)
    if "damage_modifier" in rules:
        integer(rules["damage_modifier"], "feature damage modifier")
    if count and die < 2:
        fail("invalid_attack_state", "Damage dice require valid sides.")
    damage_sources = set()
    for extra in rules.get("additional_damage", []):
        if not isinstance(extra, dict) or not extra.get("source") or extra.get("damage_type") not in DAMAGE_TYPES:
            fail("invalid_attack_state", "Additional damage needs type and provenance.")
        if extra["source"] in damage_sources:
            fail("invalid_attack_state", "Additional damage sources cannot be repeated.")
        damage_sources.add(extra["source"])
        integer(extra.get("damage_die", 0), "additional damage die", 0)
        integer(extra.get("damage_dice", 0), "additional damage dice", 0)
        integer(extra.get("modifier", 0), "additional damage modifier")
        if extra.get("damage_dice", 0) and extra.get("damage_die", 0) < 2:
            fail("invalid_attack_state", "Invalid additional damage dice.")
    if weapon["damage_type"] not in DAMAGE_TYPES:
        fail("invalid_attack_state", "Unknown canonical damage type.")
    return {"actor_id": actor, "target_id": target, "weapon": weapon, "choice": choice,
            "origin": origin, "mode": mode, "ability": ability, "ability_modifier": ability_mod,
            "proficient": proficient, "proficiency_bonus": pb,
            "attack_bonus": bonus - 2 * exhaustion(attacker), "attack_modifiers": attack_modifiers,
            "damage_adjustment": damage_adjustment, "damage_modifiers": damage_modifiers,
            "advantage_sources": sorted(set(advantage)), "disadvantage_sources": sorted(set(disadvantage)),
            "target_ac_base": integer(defender.get("armor_class"), "target AC", 0),
            "target_ac": defender["armor_class"] + {"none": 0, "half": 2, "three_quarters": 5}[cover],
            "cover": cover, "spatial": spatial, "auto_miss": auto_miss, "mastery": mastery,
            "damage_die": die, "damage_dice": count, "rules": rules,
            "ammunition": ammunition, "loading_key": loading_key, "unarmed": unarmed,
            "unarmed_option": unarmed_option, "target_conditions": sorted(tconditions)}


def preview(session, actor, target, weapon_id, choice=None, *, origin="action"):
    # Existing legacy migration/feature hooks cannot mutate a preview.
    world, character, rng = copy.deepcopy(session.world_state), copy.deepcopy(session.character), session.rng.getstate()
    combat = session.world_state.get("combat", {})
    old_identity = combat.get("combat_id")
    try:
        if not combat.get("active"):
            # A new attack request can open a new encounter; direct resolution
            # still refuses to execute against a closed encounter.
            combat["combat_id"] = None
        return copy.deepcopy(prepare(session, actor, target, weapon_id, choice, origin=origin))
    finally:
        combat["combat_id"] = old_identity
        if session.world_state != world:
            session.world_state.clear()
            session.world_state.update(world)
        if session.character != character:
            session.character.clear()
            session.character.update(character)
        session.rng.setstate(rng)


def mitigate(session, target, damage_type, amount, *, graze=False):
    defender = actor_data(session, target)
    resistances = set(defender.get("resistances", []))
    if target == "player" and defender.get("species") == "Aasimar":
        resistances.update({"radiant", "necrotic"})
    resistance = damage_type in resistances
    vulnerability = damage_type in defender.get("vulnerabilities", [])
    immunity = damage_type in defender.get("immunities", [])
    amount = max(0, amount)
    raw = amount
    if immunity:
        amount = 0
    if resistance:
        amount //= 2
    # Graze cannot be increased by vulnerability or other bonuses (PHB p.214).
    if vulnerability and not graze:
        amount *= 2
    return {"damage_type": damage_type, "raw_damage": raw, "resistance_applied": resistance,
            "vulnerability_applied": vulnerability and not graze, "immunity_applied": immunity,
            "final_damage": max(0, amount)}


def save(session, target, abilities, dc, chosen=None, *, effect_context=None):
    defender = actor_data(session, target)
    ability = chosen or max(abilities, key=lambda a: defender.get(a + "_save_bonus", defender.get(a + "_mod", 0)))
    if ability not in abilities:
        fail("invalid_save_choice", "Invalid target saving throw ability.")
    status = conditions(session, target, defender)
    if ability in {"strength", "dexterity"} and status & {"unconscious", "paralyzed", "stunned"}:
        result = {"ability": ability, "dc": dc, "outcome": "FAILURE", "automatic_failure": True}
    else:
        modifier = integer(defender.get(ability + "_mod", 0), "saving throw modifier")
        total = integer(defender.get(ability + "_save_bonus", modifier), "saving throw bonus")
        dodging = (ability == "dexterity" and economy.ensure(session).get(target, {}).get("dodging")
                   and economy.can_act(session, target) and economy.speed(session, target) > 0)
        if target == "player":
            modifier, adjustment = saving_bonus(defender, ability)
        else:
            adjustment = total - modifier - 2 * exhaustion(defender)
        result = resolve_saving_throw(roll_fn=session.roll_d20, ability=ability, dc=dc,
                                    ability_modifier=modifier, circumstantial_modifier=adjustment,
                                    advantage=bool(dodging))
    block = defender.get("monster_stat_block") or {}
    if (target != "player" and result["outcome"] == "FAILURE" and effect_context
            and session.world_state.get("combat", {}).get("active")
            and any(c.get("kind") == "legendary_resistance" for c in block.get("capabilities", []))):
        import monster_combat
        with initiative.atomic(session):
            economy.monster_event(session, "failed_save", session.world_state["combat"]["current_actor_id"],
                                  target_id=target, severity=effect_context.get("severity", "minor"),
                                  resolution=copy.deepcopy(result))
            decision = monster_combat.window(session, target, "resistance")
            if decision.get("save_override") == "SUCCESS":
                result["outcome"] = "SUCCESS"
                result["legendary_resistance"] = decision["decisions"][0]
    return result


def add_condition(data, name):
    names = data.setdefault("conditions", [])
    if isinstance(names, dict):
        names[name] = True
    elif name not in names:
        names.append(name)
    if name == "prone":
        data["prone"] = True


def push(session, actor, target, distance, *, size_limit="large"):
    if size_limit and SIZES.index(actor_data(session, target).get("size", "medium")) > SIZES.index(size_limit):
        return {"kind": "push", "applied": False, "reason": "target_too_large"}
    spatial = pair(session, actor, target)
    clear = spatial.get("push_clear_ft")
    if type(clear) not in (int, float) or clear < distance:
        return {"kind": "push", "applied": False, "reason": "position_unresolved_or_blocked"}
    # Engine-provided unobstructed straight-away corridor. No inferred geometry.
    new_distance = spatial["distance_ft"] + distance
    pairs = session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
    for key in list(pairs):
        if target in key.split("|"):
            del pairs[key]  # Other distances are now unknown, not silently stale.
    pairs[f"{actor}|{target}"] = {**spatial, "distance_ft": new_distance,
                                 "push_clear_ft": clear - distance}
    if actor == "player":
        actor_data(session, target)["distance_ft"] = new_distance
    elif target == "player":
        actor_data(session, actor)["distance_ft"] = new_distance
    return {"kind": "push", "applied": True, "distance_ft": distance,
            "resulting_distance_ft": new_distance}


def effect(session, kind, actor, target):
    counter = session.world_state["combat"].get("turn_resources", {}).get(actor, {}).get("attack_turn_counter", 0)
    effects = session.world_state.setdefault("attack_effects", [])
    effects[:] = [e for e in effects if not (e["kind"] == kind and e["source_actor"] == actor and e["target_id"] == target)]
    effects.append({"kind": kind, "source_actor": actor, "target_id": target,
                    "expires_turn": counter + 1, "expires_boundary": "end" if kind == "vex" else "begin"})


def boundary(session, actor, event):
    resources = session.world_state.get("combat", {}).get("turn_resources", {})
    counter = resources.get(actor, {}).get("attack_turn_counter", 0)
    if event == "begin":
        counter += 1
        if actor in resources:
            resources[actor]["attack_turn_counter"] = counter
    effects = session.world_state.get("attack_effects", [])
    effects[:] = [e for e in effects if not (e["source_actor"] == actor
                 and e["expires_boundary"] == event and counter >= e["expires_turn"])]


def slow_penalty(session, actor):
    return 10 if any(e["kind"] == "slow" and e["target_id"] == actor
                     for e in session.world_state.get("attack_effects", [])) else 0


def resolve(session, actor, target, weapon_id=None, choice=None, *, origin="action", profile=None):
    # Reuse the existing state/RNG rollback context; HTTP receipts own durability.
    with initiative.atomic(session):
        context = prepare(session, actor, target, weapon_id, choice, origin=origin, profile=profile)
        action_id, _, _ = resolution_identity("weapon_context")
        scope = nullcontext() if action_id else resolution_action_scope(str(uuid4()))
        with scope:
            return _resolve(session, context)


def _resolve(session, c):
    actor, target, weapon = c["actor_id"], c["target_id"], c["weapon"]
    attacker, defender = actor_data(session, actor), actor_data(session, target)
    hp_before = defender["current_hp"]
    resolution, unarmed_save = None, None
    special = c["unarmed"] and c["unarmed_option"] != "damage"
    if special:
        dc = 8 + c["ability_modifier"] + c["proficiency_bonus"]
        unarmed_save = save(session, target, ("strength", "dexterity"), dc, c["choice"].get("target_save_ability"))
        hit = unarmed_save["outcome"] == "FAILURE"
        critical = False
    else:
        resolution = resolve_attack_roll(
            roll_fn=session.roll_attack if actor == "player" else session.roll_d20,
            attack_bonus=c["attack_bonus"], target_ac=c["target_ac"],
            advantage=bool(c["advantage_sources"]), disadvantage=bool(c["disadvantage_sources"]),
            actor_id=actor, target_id=target)
        hit = resolution["outcome"] != "MISS" and not c["auto_miss"]
        critical = bool(hit and (resolution["selected_roll"] == 20 or (
            c["spatial"]["distance_ft"] <= 5 and set(c["target_conditions"]) & {"unconscious", "paralyzed"})))
    graze = not hit and not c["auto_miss"] and c["mastery"] == "graze"
    damage_rolls, components, species_effects, additional_effects = [], [], [], []
    if hit and not special:
        modifier = c["rules"].get("damage_modifier", c["ability_modifier"])
        integer(modifier, "damage modifier")
        if c["origin"] in {"light", "nick", "cleave"}:
            modifier = min(0, modifier)
        fixed = weapon.get("fixed_damage")
        if fixed is not None and not c["unarmed"]:
            modifier = 0  # Blowgun's fixed damage has no ability modifier.
        if fixed is not None:
            raw = max(0, fixed + modifier + weapon["magic_damage_bonus"] + c["damage_adjustment"])
        else:
            die = c["damage_die"]
            if weapon.get("grip") == 2 and "versatile" in weapon["properties"] and c["mode"] == "melee":
                die = weapon["versatile_damage_die"]
            count = c["damage_dice"] * (2 if critical else 1)
            rolls = []
            raw = max(0, session.roll_damage(die, count, modifier + weapon["magic_damage_bonus"] + c["damage_adjustment"], rolls=rolls))
            damage_rolls.append({"source": "weapon", "die": die, "count": count, "rolls": rolls})
        components.append({"damage_type": weapon["damage_type"], "raw_damage": raw})
        for extra in c["rules"].get("additional_damage", []):
            count = extra.get("damage_dice", 0) * (2 if critical and extra.get("critical_doublable", True) else 1)
            rolls = []
            raw = max(0, session.roll_damage(extra.get("damage_die", 0), count, extra.get("modifier", 0), rolls=rolls))
            damage_rolls.append({"source": extra["source"], "die": extra.get("damage_die", 0), "count": count, "rolls": rolls})
            components.append({"damage_type": extra["damage_type"], "raw_damage": raw})
        if actor == "player":
            _, species_effects = session._apply_species_on_hit_effects(defender, critical=critical)
            for entry in species_effects:
                if entry.get("damage"):
                    components.append({"damage_type": entry["damage_type"], "raw_damage": entry["damage"]})
                    if entry.get("raw_rolls"):
                        damage_rolls.append({"source": entry["trait"], "die": entry["damage_die"],
                                             "count": len(entry["raw_rolls"]), "raw_rolls": entry["raw_rolls"],
                                             "modifier": 0, "damage_type": entry["damage_type"]})
    elif graze:
        components.append({"damage_type": weapon["damage_type"], "raw_damage": max(0, c["ability_modifier"])})
    grouped = {}
    for entry in components:
        grouped[entry["damage_type"]] = grouped.get(entry["damage_type"], 0) + entry["raw_damage"]
    raw_grouped = dict(grouped)
    if target == "player":
        reduced, flat_effects = session._reduce_attack_damage_to_player(sum(grouped.values()))
        species_effects.extend(flat_effects)
        remaining_reduction = sum(grouped.values()) - reduced
        for kind in grouped:
            applied = min(grouped[kind], remaining_reduction)
            grouped[kind] -= applied
            remaining_reduction -= applied
    damage_instances = []
    for kind, amount in grouped.items():
        instance = mitigate(session, target, kind, amount, graze=graze)
        instance.update(raw_damage=raw_grouped[kind], pre_resistance_damage=amount,
                        flat_reduction=raw_grouped[kind] - amount)
        damage_instances.append(instance)
    damage = sum(entry["final_damage"] for entry in damage_instances)
    if target == "player":
        hp_result = session._apply_attack_damage_to_player(damage, critical, hit or graze)
        species_effects.extend(hp_result["species_effects"])
        hp_after = session.character["current_hp"]
    else:
        hp_after = session.apply_npc_damage(defender, damage)
        hp_result = {"hp_damage": damage, "death_resolution": None}
    if special and hit:
        if c["unarmed_option"] == "grapple":
            add_condition(defender, "grappled")
            defender["grappled_by"] = actor
            defender["grapple_escape_dc"] = 8 + c["ability_modifier"] + c["proficiency_bonus"]
            hands = equipment(session, actor, attacker)
            free = next(hand for hand, value in hands.items() if value is None)
            hands[free] = f"grapple:{target}"
            additional_effects.append({"kind": "grapple", "applied": True,
                                       "escape_dc": defender["grapple_escape_dc"], "hand": free})
        elif c["choice"].get("shove_option", "prone") == "push":
            additional_effects.append(push(session, actor, target, 5, size_limit=None))
        else:
            add_condition(defender, "prone")
            additional_effects.append({"kind": "shove_prone", "applied": True})
    mastery_result = None
    mastery = c["mastery"]
    if hit and mastery in {"sap", "slow", "vex"}:
        qualifies = mastery == "sap" or damage > 0
        if qualifies:
            effect(session, mastery, actor, target)
        mastery_result = {"kind": mastery, "applied": qualifies}
    elif hit and mastery == "push":
        mastery_result = push(session, actor, target, c["choice"].get("push_ft", 10))
    elif hit and mastery == "topple":
        dc = 8 + c["proficiency_bonus"] + c["ability_modifier"]
        saving = save(session, target, ("constitution",), dc)
        applied = saving["outcome"] == "FAILURE"
        if applied:
            add_condition(defender, "prone")
        mastery_result = {"kind": "topple", "applied": applied, "save": saving}
    elif graze:
        mastery_result = {"kind": "graze", "applied": True}
    if weapon.get("equipment_after") is not None:
        owner = session.world_state if actor == "player" else attacker
        owner["equipment"] = weapon["equipment_after"]
    if c["ammunition"]:
        owner = session.world_state if actor == "player" else attacker
        owner["ammunition"][c["ammunition"]] -= 1
    if "thrown" in weapon["properties"] and c["mode"] != "melee":
        items = inventory(session, actor, attacker)
        items.remove(item_for(session, actor, attacker, weapon, weapon["instance_id"]))
        hands = equipment(session, actor, attacker)
        for hand, value in hands.items():
            if value == weapon["instance_id"] or (lookup(value) and lookup(value)["weapon_id"] == weapon["instance_id"]):
                hands[hand] = None
        session.world_state.setdefault("spent_thrown_weapons", []).append(
            {"weapon_id": weapon["weapon_id"], "actor_id": actor, "target_id": target})
    if attacker.get("hidden") is True:
        attacker["hidden"] = False
        additional_effects.append({"kind": "hidden_location_revealed"})
    effects = session.world_state.get("attack_effects", [])
    if not special:
        effects[:] = [e for e in effects if not (
            (e["kind"] == "sap" and e["target_id"] == actor)
            or (e["kind"] == "vex" and e["source_actor"] == actor and e["target_id"] == target))]
        # A newly granted Vex belongs to this hit, not the previous attack.
        if hit and mastery == "vex" and damage > 0:
            effect(session, "vex", actor, target)
    combat = session.world_state["combat"]
    if combat["active"]:
        sequence = turn_state(session, actor)
        sequence["attacks"] += 1
        if "light" in weapon["properties"] and c["origin"] in {"action", "continuation"}:
            sequence["light_weapon_ids"].append(weapon["instance_id"])
        if c["origin"] in {"light", "nick"}:
            sequence["light_used"] = True
        if "loading" in weapon["properties"]:
            sequence["loading_origins"].append(c["loading_key"])
        if c["origin"] == "action":
            sequence["active_action_key"] = c["loading_key"]
            sequence["action_index"] = sequence.get("action_index", 0) + 1
    result = {
        "action": "attack" if actor == "player" else "enemy_attack", "status": "resolved",
        "success": hit, "outcome": "critical_hit" if critical else "hit" if hit else "miss",
        "actor_id": actor, "actor": actor, "actor_name": attacker.get("name"),
        "target_id": target, "target": target, "target_name": defender.get("name"),
        "combat_id": combat.get("combat_id"), "weapon": "Kılıç" if weapon["weapon_id"] == "longsword" else weapon["name"],
        "weapon_id": weapon["weapon_id"], "attack_type": c["mode"], "attack_origin": c["origin"],
        "ability_used": c["ability"], "ability_modifier": c["ability_modifier"],
        "proficient": c["proficient"], "proficiency_bonus": c["proficiency_bonus"],
        "proficiency_applied": c["proficient"], "attack_bonuses": c["attack_modifiers"],
        "damage_modifiers": c["damage_modifiers"], "attack_bonus": c["attack_bonus"],
        "attack_roll": resolution["selected_roll"] if resolution else None,
        "attack_rolls": resolution["raw_rolls"] if resolution else [],
        "attack_total": resolution["total"] if resolution else None,
        "resolution": resolution or unarmed_save, "unarmed_option": c["unarmed_option"] if c["unarmed"] else None,
        "action_id": (resolution or unarmed_save).get("action_id"),
        "resolution_id": (resolution or unarmed_save).get("resolution_id"),
        "attack_id": (resolution or unarmed_save).get("resolution_id"),
        "advantage_sources": c["advantage_sources"], "disadvantage_sources": c["disadvantage_sources"],
        "disadvantage": bool(c["disadvantage_sources"]) and not c["advantage_sources"],
        "cover_state": c["cover"], "target_ac_base": c["target_ac_base"], "target_ac": c["target_ac"],
        "natural_20": bool(resolution and resolution["selected_roll"] == 20),
        "natural_1": bool(resolution and resolution["selected_roll"] == 1),
        "critical": critical, "hit": hit, "damage": damage, "damage_type": weapon["damage_type"],
        "raw_damage": sum(raw_grouped.values()), "damage_rolls": damage_rolls, "damage_instances": damage_instances,
        "mastery": mastery, "mastery_effect": mastery_result, "additional_effects": additional_effects,
        "ammunition_consumed": {"type": c["ammunition"], "quantity": 1} if c["ammunition"] else None,
        "weapon_instance_id": weapon.get("instance_id"),
        "target_hp_before": hp_before, "target_hp_after": hp_after,
        "target_status": session.world_state.get("player_combat_status", "active") if target == "player" else defender.get("combat_status", "active"),
        "resulting_conditions": sorted(conditions(session, target, defender)),
        "resulting_position": mastery_result if mastery_result and mastery_result["kind"] == "push" else None,
        "species_effects": species_effects, **{k: v for k, v in hp_result.items() if k != "species_effects"},
    }
    for event in ("after_attack", "after_damage", "after_mastery"):
        # Notifications, not unvalidated mutation commands.
        hook(session, event, result)
    import monster_combat
    monster_combat.observe_attack(session, result)
    if hit and c["choice"].get("cleave_target_id"):
        sequence = turn_state(session, actor)
        sequence["cleave_used"] = True
        second_choice = {k: v for k, v in c["choice"].items() if k != "cleave_target_id"}
        result["cleave_attack"] = resolve(session, actor, c["choice"]["cleave_target_id"],
                                         weapon["weapon_id"], second_choice, origin="cleave")
    history = session.world_state.setdefault("attack_results", [])
    history.append(copy.deepcopy(result))
    del history[:-32]
    return result


def _held_weapon_profiles(session, actor, data):
    """Catalog profiles for currently held hands; item_id refs resolve via inventory."""
    hands = equipment(session, actor, data)
    profiles = []
    for value in hands.values():
        if value is None:
            continue
        weapon = lookup(value)
        if weapon is None:
            for item in inventory(session, actor, data):
                if isinstance(item, dict) and item.get("item_id") == value:
                    weapon = lookup(item.get("weapon_id", item.get("name")))
                    break
        if weapon is not None:
            profiles.append(weapon)
    return profiles


def natural_choice(session, text):
    """Choices only; no model-derived stats, grants, distance or hand state."""
    normalized = session._normalize_turkish_typos(text)
    selected = []
    for identity, weapon in __import__("weapon_catalog").WEAPONS.items():
        terms = {identity, weapon["weapon_id"], *weapon["aliases"]}
        if any(re.search(r"(?<!\w)" + re.escape(session._normalize_turkish_typos(term)) + r"(?!\w)", normalized) for term in terms):
            if weapon["weapon_id"] not in selected:
                selected.append(weapon["weapon_id"])
    if len(selected) > 1:
        fail("ambiguous_weapon", "Specify one weapon for each attack.")
    unarmed = bool(re.search(r"yumruk|tekme|unarmed|grapple|kavra|gures|shove|itiyorum", normalized))
    identity = "unarmed" if unarmed else selected[0] if selected else None
    if identity is None:
        held = _held_weapon_profiles(session, "player", getattr(session, "character", {}))
        if not held:
            fail("no_weapon", "Specify an available held weapon or Unarmed Strike.")
        identity = held[0]["weapon_id"]
    choice = {}
    if re.search(r"iki elim|two.hand", normalized):
        choice["grip"] = 2
    if re.search(r"firlat|throw", normalized):
        choice["mode"] = "thrown"
    if re.search(r"dexterity|cevikli|dex\b", normalized):
        choice["ability"] = "dexterity"
    if re.search(r"strength|kuvvet|str\b", normalized):
        choice["ability"] = "strength"
    if re.search(r"ustalik kullanma|mastery kullanma|without mastery", normalized):
        choice["mastery"] = "none"
    if re.search(r"cekip|draw", normalized):
        choice["draw"] = True
    if unarmed and re.search(r"grapple|kavra|gures", normalized):
        choice["unarmed_option"] = "grapple"
    elif unarmed and re.search(r"shove|itiyorum", normalized):
        choice.update(unarmed_option="shove", shove_option="push" if "geri" in normalized else "prone")
    for mastery in MASTERY:
        if re.search(rf"\b{mastery}\b", normalized):
            choice["mastery"] = mastery
    if re.search(r"cekiyorum|draw", normalized):
        choice["draw"] = True
    return identity, choice
