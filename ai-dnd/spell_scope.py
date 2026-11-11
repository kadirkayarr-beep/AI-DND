"""Bounded PHB 2024 spell adapter. Existing owners retain all resolutions."""
from __future__ import annotations

import copy
import re

import action_economy as economy
import barbarian_rage
import initiative
import spatial_rules
import weapon_attack as attacks
from api.core_resolution import resolve_attack_roll
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG, proficiency_bonus_for_level

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


def harmful(spell_id):
    """A spell that deals damage (its catalog damage type): the surrendered-foe question asks about it (D-036)."""
    entry = CATALOG.get(spell_id) if isinstance(spell_id, str) else None
    return entry is not None and entry[3] is not None


def fail(code, message):
    attacks.fail(code, message)


_V1_KEYS = frozenset({"version", "class", "cantrips", "prepared", "slots", "slot_turn"})
_V2_KEYS = _V1_KEYS | {"spellbook", "prepare_window"}  # 4C.2: state version 2
PREPARING = frozenset({"Wizard", "Cleric"})  # prepare from a window (4C.2); Druid keeps the version-1 rule (no prepared list)
WINDOW_REASONS = frozenset({"creation", "long_rest", "migration", "level_up"})  # level_up: a Wizard/Cleric level step (4C.3)


def clock_second(world):
    """The campaign second; a world without a clock yet is at 0, where the clock starts (campaign_time.initialize)."""
    return world.get("campaign_time", {}).get("elapsed_seconds", 0)


def _book_from(character):
    """The Wizard's creation selections, kept only where the spellbook may hold them (unique, Wizard level-1 list)."""
    allowed = {s["id"] for s in SPELLS_CATALOG["Wizard"]["spells_level_1"]}
    book = []
    for spell in character.get("spells") or []:
        if isinstance(spell, str) and spell in allowed and spell not in book:
            book.append(spell)
    return book


def prepare_limit(character):
    """How many level-1+ spells a preparing class may hold: the applied level's row of its `classes/` table (4C.3)."""
    import character_progression
    return character_progression.capacity(character)["prepared_spells"]


def initialize(session):
    """Only character creation may grant access and initial resources."""
    session.world_state.pop("sorcery_points_v1", None)
    character = session.character
    cls = character["class"]
    definition = CLASS_DEFINITIONS[cls]
    if not definition.get("is_spellcaster"):
        session.world_state.pop("spellcasting_v1", None)
        return
    # Wizard selections are a spellbook. Cleric/Druid select two in the existing
    # creation model, whereas the uploaded 2024 feature requires four prepared.
    # Do not manufacture a prepared list or change those class features here:
    # Wizard and Cleric prepare in the window creation opens (4C.2).
    session.world_state["spellcasting_v1"] = {
        "version": 2, "class": cls,
        "cantrips": list(character.get("cantrips", [])),
        "prepared": [] if cls in {"Wizard", "Cleric", "Druid"} else list(character.get("spells", [])),
        "slots": copy.deepcopy(definition["spell_slots"]), "slot_turn": None,
        "spellbook": _book_from(character) if cls == "Wizard" else None,
        "prepare_window": ({"opened_second": clock_second(session.world_state), "reason": "creation"}
                           if cls in PREPARING else None),
    }


def upgrade(world, character):
    """Version 1 -> 2 in place for a preparing class (old Wizard/Cleric saves). Idempotent; never chooses a spell.

    Other classes keep a version-1 state byte for byte: for them version 2 adds nothing (no spellbook, no window), and
    old campaigns must resume to exactly the state they saved. A Wizard's spellbook is built from the creation selections
    already saved in `character["spells"]`; a Wizard or Cleric gets a migration window at the current second (none during
    an active fight, which would close it)."""
    state = world.get("spellcasting_v1")
    if not isinstance(state, dict) or state.get("version") != 1 or state.get("class") not in PREPARING:
        return
    validate(state, character)
    cls = state["class"]
    if cls == "Wizard" and not _book_from(character):
        # Save formats 1-3 carry no creation spells (load_game empties them): there is no book to build and the engine
        # never chooses one. Stay version 1 (behaves exactly as before); the window reports `spellbook_missing`.
        return
    fighting = world.get("combat", {}).get("active")
    migrated = {**copy.deepcopy(state), "version": 2,
                "spellbook": _book_from(character) if cls == "Wizard" else None,
                "prepare_window": ({"opened_second": clock_second(world), "reason": "migration"}
                                   if cls in PREPARING and not fighting else None)}
    validate(migrated, character)
    world["spellcasting_v1"] = migrated


def validate(state, character):
    if state is None:
        return
    if (not isinstance(state, dict) or type(state.get("version")) is not int
            or set(state) != {1: _V1_KEYS, 2: _V2_KEYS}.get(state["version"]) or state["class"] != character["class"]):
        raise ValueError("Invalid saved spell state.")
    cls = state["class"]
    definition = CLASS_DEFINITIONS[cls]
    if not definition.get("is_spellcaster"):
        raise ValueError("Spell access requires a legitimate class feature.")
    catalog = SPELLS_CATALOG.get(cls, {})
    import character_progression
    sourced = character_progression.capacity(character)  # the applied level's table row (C06), or None: the legacy level-1 definition
    preparing = state["version"] == 2 and cls in PREPARING
    for field, source, limit in (
        ("cantrips", "cantrips", sourced["cantrips"] if sourced else definition["cantrips_count"]),
        # A version-1 Wizard/Cleric state predates preparation and keeps its empty list even with a table (4C.3).
        ("prepared", "spells_level_1", 0 if cls in {"Wizard", "Cleric", "Druid"} and not preparing
         else sourced["prepared_spells"] if sourced else definition["spells_count"]),
    ):
        selected = state[field]
        allowed = {s["id"] for s in catalog.get(source, [])} | character_progression.extra_spell_ids(character, field)
        if (not isinstance(selected, list) or any(not isinstance(s, str) for s in selected)
                or len(selected) != len(set(selected)) or len(selected) > limit
                or not set(selected).issubset(allowed)):
            raise ValueError("Invalid saved spell access.")
    capacity = sourced["slots"] if sourced else definition["spell_slots"]
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
    if state["version"] == 2:
        _validate_v2(state, character)


def _validate_v2(state, character):
    cls, book, window = state["class"], state["spellbook"], state["prepare_window"]
    if cls == "Wizard":
        import character_progression
        allowed = ({s["id"] for s in SPELLS_CATALOG["Wizard"]["spells_level_1"]}
                   | character_progression.extra_spell_ids(character, "prepared"))  # level 2+ spells once their slots exist
        if (not isinstance(book, list) or any(not isinstance(s, str) for s in book)
                or len(book) != len(set(book)) or not set(book) <= allowed
                or not set(state["prepared"]) <= set(book)):
            raise ValueError("Invalid saved spellbook.")
    elif book is not None:
        raise ValueError("Only a Wizard keeps a spellbook.")
    if window is None:
        return
    if (cls not in PREPARING or not isinstance(window, dict) or set(window) != {"opened_second", "reason"}
            or type(window["opened_second"]) is not int or window["opened_second"] < 0
            or not isinstance(window["reason"], str) or window["reason"] not in WINDOW_REASONS):
        raise ValueError("Invalid saved spell preparation window.")


def restore_slots(session):
    state = session.world_state.get("spellcasting_v1")
    validate(state, session.character)
    if state is not None:
        import character_progression
        state["slots"] = (character_progression.slot_capacity(session.character)
                          or copy.deepcopy(CLASS_DEFINITIONS[state["class"]]["spell_slots"]))
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


def cast(session, spell_id, target_id, slot_level=None, *, metamagic=None):
    with initiative.atomic(session):
        barbarian_rage.settle(session)
        if barbarian_rage.active(session):
            fail("rage_spellcasting_forbidden", "Spells cannot be cast while Rage is active.")
        if metamagic is not None:
            if metamagic != "quickened_spell" or spell_id != "Magic Missile":
                fail("unsupported_metamagic", "Only selected Quickened Magic Missile is supported.")
            with economy.quickened_cast_budget(session):
                return _cast(session, spell_id, target_id, slot_level, metamagic=metamagic)
        return _cast(session, spell_id, target_id, slot_level)


def _cast(session, spell_id, target_id, slot_level, *, metamagic=None):
    session.require_player_can_act()
    if spell_id not in CATALOG:
        fail("unsupported_spell", "Spell mechanics are outside the bounded V1 catalog.")
    state = session.world_state.get("spellcasting_v1")
    validate(state, session.character)
    level, maximum_range, sides, damage_type = CATALOG[spell_id]
    if state is None or spell_id not in state["prepared" if level else "cantrips"]:
        fail("spell_not_available", "This spell is not available/prepared through this caster's feature.")
    if slot_level is not None and (type(slot_level) is not int or
            (slot_level != level and not (spell_id == "Magic Missile" and slot_level in (2, 3)))):
        fail("unsupported_spell_mode", "Only Magic Missile with a level-two or level-three slot supports upcasting.")
    selected_level = level if slot_level is None else slot_level
    character = session.character
    character_level = character["level"]
    import character_progression
    if level and character_level != 1 and not character_progression.has_table(character):
        fail("unsupported_spell_progression", "Only sourced level-one slot progression is supported.")
    pb = character["proficiency_bonus"]
    if type(character_level) is not int or not 1 <= character_level <= 20 or pb != proficiency_bonus_for_level(character_level):
        fail("unsupported_spell_progression", "Authoritative level/proficiency state is inconsistent.")
    ability = CLASS_DEFINITIONS[character["class"]]["spellcasting_ability"]
    score = character.get(ability)
    if type(score) is not int:
        fail("invalid_spell_state", "Authoritative spellcasting ability is missing.")
    modifier = (score - 10) // 2
    combat = session.world_state.get("combat", {})
    if not combat.get("active"):
        fail("unsupported_spell_mode", "V1 spells use an existing active combat turn.")
    resource = "bonus" if metamagic == "quickened_spell" else "action"
    economy.action_slot(session, "player", "magic", resource=resource)
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
        if state["slots"].get(str(selected_level), 0) < 1:
            fail("spell_slot_unavailable", "No spell slot of the selected level remains.")
        if state["slot_turn"] == marker:
            fail("spell_slot_turn_limit", "Only one spell slot may be expended on this turn.")
    # No canonical cast starts until every supported-mode prerequisite passes.
    economy.consume_action(session, "player", "magic", resource=resource)
    if metamagic is not None:
        import sorcery_points
        sorcery_points.spend_quickened(session)
    if level:
        state["slots"][str(selected_level)] -= 1
        state["slot_turn"] = marker
    result = {"spell_id": spell_id, "target_id": target_id, "slot_level": selected_level,
              "spell_attack_modifier": modifier + pb, "spell_save_dc": 8 + modifier + pb,
              "damage": 0, "healing": 0, "resolution": None,
              # Event fields (4C.1): read by the public result, never saved.
              "damage_type": damage_type, "slot_spent": bool(level), "casting_ability": ability}
    if spell_id == "Cure Wounds":
        before = character["current_hp"]
        amount = max(0, session.roll_damage(8, 2, modifier))
        session.heal_player(amount)
        result.update(healing=character["current_hp"] - before, rolled_healing=amount, heal_source="spell")
    else:
        dice = 1 + sum(character_level >= threshold for threshold in (5, 11, 17))
        critical = False
        hits = True
        if spell_id == "Fire Bolt":
            resolution = resolve_attack_roll(
                roll_fn=session.roll_d20, attack_bonus=modifier + pb,
                target_ac=target["armor_class"] + spatial_rules.COVER_AC[cover],
                actor_id="player", target_id=target_id,
            )
            result["resolution"] = resolution
            result["attack_or_save"] = "attack"
            hits = resolution["outcome"] != "MISS"
            critical = resolution["outcome"] == "CRITICAL_HIT"
        elif spell_id == "Sacred Flame":
            resolution = attacks.save(session, target_id, ["dexterity"], 8 + modifier + pb,
                                      effect_context={"source": "Sacred Flame", "severity": "harmful"})
            result["resolution"] = resolution
            result.update(attack_or_save="save", save_roll=resolution.get("selected_roll"))
            hits = resolution["outcome"] == "FAILURE"
        if hits:
            if spell_id == "Magic Missile":
                # One recipient, simultaneous darts; mitigate each damage instance.
                darts = [session.roll_damage(4, 1, 1) for _ in range(2 + selected_level)]
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
