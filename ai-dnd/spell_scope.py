"""Bounded PHB 2024 spell adapter. Existing owners retain all resolutions."""
from __future__ import annotations

import copy
import re

import action_economy as economy
import initiative
import weapon_attack as attacks
from api.core_resolution import resolve_attack_roll
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG

CATALOG = {
    "Fire Bolt": (0, 120, 10, "fire"),
    "Magic Missile": (1, 120, 4, "force"),
    "Cure Wounds": (1, 0, 8, None),
    "Sacred Flame": (0, 60, 8, "radiant"),
}
ALIASES = {"ateş oku": "Fire Bolt", "ates oku": "Fire Bolt",
           "sihirli füze": "Magic Missile", "sihirli fuze": "Magic Missile",
           "yara iyileştirme": "Cure Wounds", "yara iyilestirme": "Cure Wounds",
           "kutsal alev": "Sacred Flame"}


def fail(code, message):
    attacks.fail(code, message)


def initialize(session):
    """Only character creation may grant access and initial resources."""
    character = session.character
    cls = character["class"]
    definition = CLASS_DEFINITIONS[cls]
    if not definition.get("is_spellcaster"):
        session.world_state.pop("spellcasting_v1", None)
        return
    # Wizard selections are a spellbook. Cleric/Druid select two in the existing
    # creation model, whereas the uploaded 2024 feature requires four prepared.
    # Do not manufacture a prepared list or change those class features here.
    session.world_state["spellcasting_v1"] = {
        "version": 1, "class": cls,
        "cantrips": list(character.get("cantrips", [])),
        "prepared": [] if cls in {"Wizard", "Cleric", "Druid"} else list(character.get("spells", [])),
        "slots": copy.deepcopy(definition["spell_slots"]), "slot_turn": None,
    }


def validate(state, character):
    if state is None:
        return
    if (not isinstance(state, dict) or set(state) != {
        "version", "class", "cantrips", "prepared", "slots", "slot_turn"
    } or type(state["version"]) is not int or state["version"] != 1 or state["class"] != character["class"]):
        raise ValueError("Invalid saved spell state.")
    cls = state["class"]
    definition = CLASS_DEFINITIONS[cls]
    if not definition.get("is_spellcaster"):
        raise ValueError("Spell access requires a legitimate class feature.")
    catalog = SPELLS_CATALOG.get(cls, {})
    for field, source, limit in (
        ("cantrips", "cantrips", definition["cantrips_count"]),
        ("prepared", "spells_level_1", 0 if cls in {"Wizard", "Cleric", "Druid"} else definition["spells_count"]),
    ):
        selected = state[field]
        allowed = {s["id"] for s in catalog.get(source, [])}
        if (not isinstance(selected, list) or any(not isinstance(s, str) for s in selected)
                or len(selected) != len(set(selected)) or len(selected) > limit
                or not set(selected).issubset(allowed)):
            raise ValueError("Invalid saved spell access.")
    capacity = definition["spell_slots"]
    if (not isinstance(state["slots"], dict) or set(state["slots"]) != set(capacity)
            or any(type(n) is not int or not 0 <= n <= capacity[k]
                   for k, n in state["slots"].items())):
        raise ValueError("Invalid saved spell slots.")
    marker = state["slot_turn"]
    if marker is not None and (
        not isinstance(marker, list) or len(marker) != 3
        or not isinstance(marker[0], str)
        or any(type(n) is not int or n < 1 for n in marker[1:])
    ):
        raise ValueError("Invalid spell-slot turn marker.")


def restore_slots(session):
    state = session.world_state.get("spellcasting_v1")
    validate(state, session.character)
    if state is not None:
        state["slots"] = copy.deepcopy(CLASS_DEFINITIONS[state["class"]]["spell_slots"])
        # A rest does not authorize a second slot in the same combat turn.


def natural_command(message, target_id):
    """Explicit deterministic proposals only; never choose an implicit target."""
    text = str(message).casefold()
    names = {name.casefold(): name for name in CATALOG} | ALIASES
    selected = [name for alias, name in names.items() if alias in text]
    casting = bool(re.search(r"\b(cast|casting|büyü|buyu|büyüsünü|buyusunu)\b", text))
    if not selected and not casting:
        return None
    # Questions about spells are never player authorization to cast.
    if "?" in text or re.search(r"\b(nedir|what|describe|anlat)\b", text):
        return None
    if re.search(r"\b(not|don't|dont|değil|degil)\b|kullanma|atmıyorum|atmiyorum", text):
        return None
    if len(set(selected)) != 1:
        fail("unsupported_spell", "Name exactly one supported V1 spell.")
    if re.search(r"\b(split|divide|upcast|ritual|reaction|bonus|object|nesne|böl|bol)\b"
                 r"|\b(and|or|then|ve|veya|sonra|distribute|targets|enemies|free|without|slot|slots)\b"
                 r"|[,;]|\b\d+\s*(?:level|seviye)|yüksek|yuksek|harcamadan|hedeflere", text):
        fail("unsupported_spell_mode", "This requested spell mode is outside V1.")
    name = selected[0]
    if target_id is None and name == "Cure Wounds" and re.search(r"\b(self|myself|kendime)\b", text):
        target_id = "player"
    return {"steps": [{"kind": "magic", "ability": name, "target_id": target_id}]}


def narration(result):
    if result["spell_id"] == "Cure Wounds":
        return f"Cure Wounds ile {result['healing']} canın yenilenir."
    if not result["hit"]:
        return f"{result['spell_id']} hedefe hasar vermez."
    return f"{result['spell_id']} hedefe {result['damage']} hasar verir."


def explicit_request(message, command=None):
    if command and any(step.get("kind") == "magic" for step in command.get("steps", [])):
        return True
    text = str(message).casefold()
    if "?" in text or re.search(r"\b(nedir|describe|what|anlat)\b", text):
        return False
    return bool(re.search(r"\b(cast|casting|büyüsünü|buyusunu)\b", text)
                or (any(name.casefold() in text for name in CATALOG)
                    and "?" not in text and not re.search(r"\b(nedir|describe|what|anlat)\b", text)))


def cast(session, spell_id, target_id, slot_level=None):
    with initiative.atomic(session):
        return _cast(session, spell_id, target_id, slot_level)


def _cast(session, spell_id, target_id, slot_level):
    session.require_player_can_act()
    if spell_id not in CATALOG:
        fail("unsupported_spell", "Spell mechanics are outside the bounded V1 catalog.")
    state = session.world_state.get("spellcasting_v1")
    validate(state, session.character)
    level, maximum_range, sides, damage_type = CATALOG[spell_id]
    if state is None or spell_id not in state["prepared" if level else "cantrips"]:
        fail("spell_not_available", "This spell is not available/prepared through this caster's feature.")
    if slot_level is not None and (type(slot_level) is not int or slot_level != level):
        fail("unsupported_spell_mode", "V1 does not support upcasting.")
    character = session.character
    character_level = character["level"]
    if level and character_level != 1:
        fail("unsupported_spell_progression", "Only sourced level-one slot progression is supported.")
    pb = character["proficiency_bonus"]
    if type(character_level) is not int or not 1 <= character_level <= 20 or pb != 2 + (character_level - 1) // 4:
        fail("unsupported_spell_progression", "Authoritative level/proficiency state is inconsistent.")
    ability = CLASS_DEFINITIONS[character["class"]]["spellcasting_ability"]
    score = character.get(ability)
    if type(score) is not int:
        fail("invalid_spell_state", "Authoritative spellcasting ability is missing.")
    modifier = (score - 10) // 2
    combat = session.world_state.get("combat", {})
    if not combat.get("active"):
        fail("unsupported_spell_mode", "V1 spells use an existing active combat turn.")
    economy.action_slot(session, "player", "magic")
    hands = attacks.equipment(session, "player", character)
    actor_conditions = attacks.conditions(session, "player", character)
    if not any(value is None for value in hands.values()) or actor_conditions & {"silenced", "silence", "cannot_speak", "petrified"}:
        fail("spell_components_unavailable", "Required V/S components are unavailable.")
    if not isinstance(target_id, str) or not target_id:
        fail("spell_target_required", "Choose an explicit canonical creature target.")
    if spell_id == "Cure Wounds":
        if target_id != "player":
            fail("unsupported_spell_mode", "Only player self-healing has an existing healing owner.")
        target = character
        target_conditions = actor_conditions
        spatial = {"distance_ft": 0}
    else:
        if target_id == "player" or target_id not in combat["participants"]:
            fail("invalid_spell_target", "Choose a participating canonical NPC creature.")
        target = attacks.actor_data(session, target_id)
        target_conditions = attacks.conditions(session, target_id, target)
        if "dead" in target_conditions:
            fail("invalid_spell_target", "Dead creatures are not supported targets.")
        block = target.get("monster_stat_block") or {}
        if (target_conditions & {"petrified"} or target.get("concentration")
                or target.get("active_spell_effects")
                or set(block.get("traits", {})) - {"training"}):
            fail("unsupported_spell_target_mode", "This target requires a deferred spell/defense owner.")
        traits = character.get("species_trait_state") or {}
        if traits.get("celestial_revelation_turns_remaining"):
            fail("unsupported_spell_damage_mode", "Active species spell-damage riders are deferred.")
        spatial = attacks.pair(session, "player", target_id)
        if spatial["distance_ft"] > maximum_range:
            fail("spell_out_of_range", "Target is outside the sourced spell range.")
        if spatial.get("attacker_sees_target") is not True:
            fail("spell_visibility_unknown", "V1 requires an explicitly visible target.")
        if spatial.get("cover", "none") == "total" or spatial.get("clear_path") is False:
            fail("spell_path_blocked", "The target has no clear spell path.")
    if spell_id == "Fire Bolt":
        # Restricted modes are rejected, not resolved with missing advantage rules.
        traits = character.get("species_trait_state") or {}
        if actor_conditions or target_conditions or traits.get("giant_ancestry_armed") or traits.get("celestial_revelation_turns_remaining"):
            fail("unsupported_spell_attack_mode", "Condition/rider-modified spell attacks are deferred.")
        if economy.ensure(session).get(target_id, {}).get("dodging") or session.world_state.get("attack_effects"):
            fail("unsupported_spell_attack_mode", "Tracked attack modifiers require their spell-compatible owner.")
        for npc_id in combat["participants"]:
            if npc_id == "player":
                continue
            npc = attacks.actor_data(session, npc_id)
            if attacks.conditions(session, npc_id, npc) & {"dead", "unconscious", "incapacitated"}:
                continue
            if attacks.pair(session, "player", npc_id)["distance_ft"] <= 5:
                fail("unsupported_spell_attack_mode", "Close-hostile ranged spell modes are deferred.")
        cover = spatial.get("cover", "none")
        if cover not in {"none", "half", "three_quarters"} or type(target.get("armor_class")) is not int:
            fail("invalid_spell_target", "Target AC/cover is not authoritative.")
    if spell_id == "Sacred Flame":
        if target_conditions & {"restrained"}:
            fail("unsupported_spell_save_mode", "Modified Dexterity save modes are deferred.")
        # Never accept the save owner's legacy zero fallback without source evidence.
        bonus = target.get("dexterity_save_bonus", target.get("dexterity_mod"))
        if type(bonus) is not int:
            block = target.get("monster_stat_block", {})
            sourced = block.get("ability_modifiers", {}).get("dexterity")
            if sourced != 0 or type(sourced) is not int or block.get("saving_throws"):
                fail("spell_save_modifier_unknown", "Authoritative target Dexterity save is required.")
    marker = [combat["combat_id"], combat["round"],
              economy.ensure(session)["player"]["attack_turn_counter"]]
    if level:
        if state["slots"].get("1", 0) < 1:
            fail("spell_slot_unavailable", "No level-one spell slot remains.")
        if state["slot_turn"] == marker:
            fail("spell_slot_turn_limit", "Only one spell slot may be expended on this turn.")
    # No canonical cast starts until every supported-mode prerequisite passes.
    economy.consume_action(session, "player", "magic")
    if level:
        state["slots"]["1"] -= 1
        state["slot_turn"] = marker
    result = {"spell_id": spell_id, "target_id": target_id, "slot_level": level,
              "spell_attack_modifier": modifier + pb, "spell_save_dc": 8 + modifier + pb,
              "damage": 0, "healing": 0, "resolution": None}
    if spell_id == "Cure Wounds":
        before = character["current_hp"]
        amount = max(0, session.roll_damage(8, 2, modifier))
        session.heal_player(amount)
        result.update(healing=character["current_hp"] - before, rolled_healing=amount)
    else:
        dice = 1 + sum(character_level >= threshold for threshold in (5, 11, 17))
        critical = False
        hits = True
        if spell_id == "Fire Bolt":
            resolution = resolve_attack_roll(
                roll_fn=session.roll_d20, attack_bonus=modifier + pb,
                target_ac=target["armor_class"] + {"none": 0, "half": 2, "three_quarters": 5}[cover],
                actor_id="player", target_id=target_id,
            )
            result["resolution"] = resolution
            hits = resolution["outcome"] != "MISS"
            critical = resolution["outcome"] == "CRITICAL_HIT"
        elif spell_id == "Sacred Flame":
            resolution = attacks.save(session, target_id, ["dexterity"], 8 + modifier + pb,
                                      effect_context={"source": "Sacred Flame", "severity": "harmful"})
            result["resolution"] = resolution
            hits = resolution["outcome"] == "FAILURE"
        if hits:
            if spell_id == "Magic Missile":
                # One recipient, simultaneous darts; mitigate each damage instance.
                darts = [session.roll_damage(4, 1, 1) for _ in range(3)]
                damage = sum(attacks.mitigate(session, target_id, "force", n)["final_damage"] for n in darts)
                result["darts"] = darts
            else:
                raw = session.roll_damage(sides, dice * (2 if critical else 1), 0)
                damage = attacks.mitigate(session, target_id, damage_type, raw)["final_damage"]
                result["raw_damage"] = raw
            before = target["current_hp"]
            session.apply_npc_damage(target, damage)
            result.update(damage=damage, hp_before=before, hp_after=target["current_hp"])
            session._combat_end_if_decided()
        result["hit"] = hits
    return result