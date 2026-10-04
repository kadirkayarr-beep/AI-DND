"""Validated, engine-owned capabilities. No monster names drive AI behavior.

MM 2024 pp. 8-10: exact Multiattack, limited usage and legendary timing.
Mechanic executors belong to their existing owners, not to the decision layer.
"""
import copy
import itertools

import weapon_attack
from combat_lifecycle import CombatRequestError

KINDS = frozenset({
    "attack", "multiattack", "special", "spell", "movement", "dash", "disengage",
    "dodge", "help", "hide", "search", "study", "influence", "ready", "utilize",
    "legendary_resistance",
})
SOURCES = frozenset({"action", "bonus", "reaction", "legendary", "resistance"})


def invalid(message):
    raise CombatRequestError("invalid_monster_capability", message, 400)


def number(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        invalid("Invalid authoritative " + name)
    return value


def capabilities(session, actor):
    """Read canonical data only; never accept a client/model action description."""
    npc = weapon_attack.actor_data(session, actor)
    block = npc.get("monster_stat_block")
    if block is None:
        # Existing Python NPC mechanics are not a Monster Manual import.
        result = []
        if npc.get("weapon_id"):
            result.append({"capability_id": "legacy_attack", "kind": "attack",
                           "action_source": "action", "weapon_id": npc["weapon_id"],
                           "source_stat_block": "legacy_python_npc"})
        elif all(k in npc for k in ("attack_bonus", "damage_die", "damage_dice", "damage_modifier")):
            dtype = npc.get("attack_damage_type", npc.get("damage_type"))
            if dtype in weapon_attack.DAMAGE_TYPES:
                result.append({"capability_id": "legacy_attack", "kind": "attack",
                               "action_source": "action", "source_stat_block": "legacy_python_npc",
                               "profile": {"weapon_id": "legacy_attack", "name": "Stat-block attack",
                                           "kind": "melee", "category": None, "properties": [], "mastery": None,
                                           "attack_bonus": npc["attack_bonus"], "damage_die": npc["damage_die"],
                                           "damage_dice": npc["damage_dice"], "damage_modifier": npc["damage_modifier"],
                                           "damage_type": dtype, "magic_attack_bonus": 0, "magic_damage_bonus": 0}})
    else:
        if not isinstance(block, dict) or not isinstance(block.get("source"), str) or not block["source"]:
            invalid("Stat block requires authoritative provenance.")
        result = copy.deepcopy(block.get("capabilities"))
        if not isinstance(result, list) or len(result) > 64:
            invalid("Invalid capability list.")
        seen = set()
        for cap in result:
            if (not isinstance(cap, dict) or not isinstance(cap.get("capability_id"), str)
                    or not cap["capability_id"] or cap["capability_id"] in seen
                    or cap.get("kind") not in KINDS or cap.get("action_source") not in SOURCES):
                invalid("Invalid or duplicate capability.")
            seen.add(cap["capability_id"])
            cap["source_stat_block"] = block["source"]
            if cap["kind"] == "attack" and bool(cap.get("profile")) == bool(cap.get("weapon_id")):
                invalid("Attack requires exactly one authoritative profile/weapon.")
            if cap.get("recharge") is not None:
                r = cap["recharge"]
                if not isinstance(r, list) or len(r) != 2:
                    invalid("Recharge needs its exact d6 range.")
                if not 1 <= number(r[0], "Recharge minimum", 1) <= number(r[1], "Recharge maximum", 1) <= 6:
                    invalid("Invalid Recharge range.")
            if "uses" in cap:
                number(cap["uses"], "limited uses", 1)
                if cap.get("restore") not in {"long_rest", "short_rest", "never"}:
                    invalid("Limited uses require an explicit restoration rule.")
            if cap["action_source"] == "legendary":
                number(cap.get("cost", 1), "Legendary Action cost", 1)
            if cap["action_source"] == "reaction" and not isinstance(cap.get("trigger"), str):
                invalid("Reaction requires an exact trigger.")
            if cap["kind"] == "spell" and not isinstance(cap.get("spell_ids"), list):
                invalid("Spell capability requires its listed spells.")
        for cap in result:
            if cap["kind"] == "multiattack":
                sequences(cap, result)
    # General PHB creature actions do not grant a monster-specific capability.
    existing = {c["capability_id"] for c in result}
    for kind in ("dodge", "dash", "disengage", "search", "influence"):
        identity = "general_" + kind
        if identity not in existing:
            result.append({"capability_id": identity, "kind": kind, "action_source": "action",
                           "source_stat_block": "PHB_2024_general_actions"})
    return result


def sequences(cap, caps):
    """Explicit slots enumerate only combinations actually permitted by the block."""
    slots = cap.get("attack_slots")
    attacks = {c["capability_id"] for c in caps if c["kind"] == "attack"}
    if (not isinstance(slots, list) or not 1 <= len(slots) <= 16
            or any(not isinstance(slot, list) or not slot or len(slot) > 8
                   or not set(slot).issubset(attacks) for slot in slots)):
        invalid("Multiattack requires exact, bounded stat-block attack slots.")
    combinations = 1
    for slot in slots:
        combinations *= len(slot)
    if combinations > 256:
        invalid("Multiattack candidate expansion exceeds the bounded interface.")
    allowed = cap.get("allowed_sequences")
    if allowed is not None:
        if (not isinstance(allowed, list) or len(allowed) > 256
                or any(len(seq) != len(slots) or any(a not in slots[i] for i, a in enumerate(seq))
                       for seq in allowed)):
            invalid("Invalid restricted Multiattack combinations.")
        return [list(seq) for seq in allowed]
    return [list(seq) for seq in itertools.product(*slots)]


def register_executor(session, kind, *, legal, resolve):
    """Engine-only adapters for movement, perception, spells and special effects."""
    if kind not in KINDS or not callable(legal) or not callable(resolve):
        invalid("Invalid owner integration.")
    if not hasattr(session, "_monster_executors"):
        session._monster_executors = {}
    session._monster_executors[kind] = (legal, resolve)


def executor(session, kind):
    return getattr(session, "_monster_executors", {}).get(kind)