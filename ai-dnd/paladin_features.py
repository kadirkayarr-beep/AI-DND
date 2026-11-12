"""Paladin 1-5 feature effects on the existing owners; it holds rules and spent counters, not a budget or a resource system.

Values only (PHB 2024 PDF 108 Lay On Hands, PDF 109 Paladin's Smite and Channel Divinity, PDF 110 Divine Sense, PDF 112/113 Oath of
Devotion, PDF 264 Divine Smite, PDF 363 Critical Hit). `character["paladin_uses"]` is additive, like `hit_dice` and `fighter_uses`: a save without it spent
nothing. Pools follow the APPLIED Paladin level; a level granted by XP alone changes nothing here.
Bonus Actions come from action_economy, slots from spell_scope's state, damage from weapon_attack.mitigate and the NPC damage owner.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

import character_progression as core
from combat_lifecycle import CombatRequestError, player_incapacitated

logger = logging.getLogger(__name__)

KEY = "paladin_uses"
_FIELDS = {"lay_on_hands_spent", "channel_divinity_spent", "free_smite_spent", "divine_sense_until", "sacred_weapon"}
SUBCLASS = "oath_of_devotion"
SUBCLASS_LEVEL = 3
BLESSED_WARRIOR = "Blessed Warrior"
BLESSED_WARRIOR_CANTRIPS = 2
STYLE_LEVEL = 2
SMITE_LEVEL = 2
CHANNEL_DIVINITY_LEVEL = 3
STEED_LEVEL = 5
LAY_ON_HANDS_PER_LEVEL = 5
LAY_ON_HANDS_POISON_COST = 5
EFFECT_SECONDS = 600  # Divine Sense and Sacred Weapon: 10 minutes
DIVINE_SENSE_RANGE_FT = 60
DIVINE_SENSE_TYPES = frozenset({"celestial", "fiend", "undead"})
SMITE_DIE = 8
SMITE_BASE_DICE = 2
SMITE_EXTRA_TYPES = frozenset({"fiend", "undead"})
SACRED_WEAPON_MINIMUM = 1
ALWAYS_PREPARED = ((SMITE_LEVEL, ("Divine Smite",)), (STEED_LEVEL, ("Find Steed",)))
OATH_SPELLS = ((3, ("Protection from Evil and Good", "Shield of Faith")), (5, ("Aid", "Zone of Truth")))
SMITE_WINDOW = "smite_window"
_VOICELESS = frozenset({"silenced", "silence", "cannot_speak", "petrified"})


def fresh_uses() -> dict[str, Any]:
    return {"lay_on_hands_spent": 0, "channel_divinity_spent": 0, "free_smite_spent": 0, "divine_sense_until": None, "sacred_weapon": None}


def paladin_level(character: Any) -> int | None:
    """The applied Paladin level, or None when this is not a verified Paladin 1-5 (at 3+ the Oath must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Paladin":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= SUBCLASS_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def devotion(character: Any) -> bool:
    level = paladin_level(character)
    return level is not None and level >= SUBCLASS_LEVEL


def pool_maximum(level: int) -> int:
    return LAY_ON_HANDS_PER_LEVEL * level


def channel_divinity_maximum(level: int) -> int:
    try:
        value = core.table("Paladin")["levels"][str(level)]["channel_divinity"]
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid Channel Divinity table value.") from error
    if value is None:
        return 0
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Channel Divinity table value.")
    return value


def always_prepared(level: int, oath: bool) -> list[str]:
    """Spells the class and the Oath keep prepared at this level; they do not count against the prepared number."""
    rows = [*ALWAYS_PREPARED, *(OATH_SPELLS if oath else ())]
    return [name for needed, names in rows if level >= needed for name in names]


def _bad(message: str) -> ValueError:
    return ValueError(f"Kayıt Paladin alanı geçersiz: {message}.")


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: this field exists only on a verified Paladin, with counts its applied level allows."""
    if player.get("class") == "Paladin" and player.get("fighting_style") is not None and (paladin_level(player) or 0) < STYLE_LEVEL:
        raise _bad("Fighting Style")
    if KEY not in player:
        return
    level, uses = paladin_level(player), player[KEY]
    if level is None or type(uses) is not dict or set(uses) != _FIELDS:
        raise _bad("uses")
    if any(type(uses[name]) is not int or uses[name] < 0 for name in ("lay_on_hands_spent", "channel_divinity_spent", "free_smite_spent")):
        raise _bad("counter")
    if (uses["lay_on_hands_spent"] > pool_maximum(level) or uses["channel_divinity_spent"] > channel_divinity_maximum(level)
            or uses["free_smite_spent"] > (1 if level >= SMITE_LEVEL else 0)):
        raise _bad("spent")
    sense, sacred = uses["divine_sense_until"], uses["sacred_weapon"]
    if sense is not None and (type(sense) is not int or sense < 0 or level < CHANNEL_DIVINITY_LEVEL):
        raise _bad("Divine Sense")
    if sacred is not None and (level < SUBCLASS_LEVEL or type(sacred) is not dict or set(sacred) != {"until", "weapon_id"}
                               or type(sacred["until"]) is not int or sacred["until"] < 0
                               or type(sacred["weapon_id"]) is not str or not sacred["weapon_id"]):
        raise _bad("Sacred Weapon")


def validate_clock_bounds(player: dict[str, Any], world: dict[str, Any]) -> None:
    """A stored end time is at most one full duration ahead of the canonical clock."""
    uses = player.get(KEY)
    if type(uses) is not dict:
        return
    ends = [uses.get("divine_sense_until"), (uses.get("sacred_weapon") or {}).get("until")]
    ends = [value for value in ends if value is not None]
    if ends:
        clock = world.get("campaign_time")
        now = clock.get("elapsed_seconds") if isinstance(clock, dict) else None
        if type(now) is not int or any(value > now + EFFECT_SECONDS for value in ends):
            raise _bad("effect end")


def _uses(character: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(character.get(KEY)) if KEY in character else fresh_uses()


def _store(character: dict[str, Any], uses: dict[str, Any]) -> None:
    character[KEY] = uses


def _now(session: Any) -> int | None:
    clock = session.world_state.get("campaign_time")
    value = clock.get("elapsed_seconds") if isinstance(clock, dict) else None
    return value if type(value) is int else None


def rest_recovery(session: Any, kind: str) -> None:
    """Short Rest: one Channel Divinity use back. Long Rest: all of it, the Lay On Hands pool and the free Divine Smite."""
    character = session.character
    if KEY not in character:
        return
    uses = _uses(character)
    if kind == "short_rest":
        uses["channel_divinity_spent"] = max(0, uses["channel_divinity_spent"] - 1)
    else:
        uses.update(lay_on_hands_spent=0, channel_divinity_spent=0, free_smite_spent=0)
    _store(character, uses)


def end_divine_sense(session: Any) -> None:
    """Divine Sense ends with the Incapacitated condition; it does not come back when the condition clears."""
    character = session.character
    if KEY in character and character[KEY].get("divine_sense_until") is not None:
        uses = _uses(character)
        uses["divine_sense_until"] = None
        _store(character, uses)


def settle(session: Any) -> None:
    """Called before an action step: a Divine Sense that met Incapacitated stays ended."""
    if player_incapacitated(session.character, session.world_state):
        end_divine_sense(session)


def divine_sense_active(session: Any) -> bool:
    now, until = _now(session), _uses(session.character)["divine_sense_until"]
    return (now is not None and until is not None and now < until
            and not player_incapacitated(session.character, session.world_state))


def sacred_weapon_active(session: Any, weapon_id: Any = None) -> bool:
    """`weapon_id` narrows it to the imbued weapon; attacking with it needs it in hand, so "carrying" holds for every attack it adds to."""
    now, sacred = _now(session), _uses(session.character)["sacred_weapon"]
    return (now is not None and sacred is not None and now < sacred["until"]
            and (weapon_id is None or sacred["weapon_id"] == weapon_id))


def _reason_in_turn(session: Any, prefix: str) -> str | None:
    import fighter_features
    return fighter_features.turn_reason(session, prefix)


def _bonus_spent(session: Any) -> bool:
    return bool(session.world_state["combat"].get("turn_resources", {}).get("player", {}).get("bonus_action_spent"))


def _touch_reason(session: Any) -> str | None:
    """Lay On Hands in or out of combat: in combat it is a Bonus Action on the current turn; outside there is no turn budget."""
    level = paladin_level(session.character)
    if level is None:
        return "lay_on_hands_not_available"
    if session.world_state.get("combat", {}).get("active"):
        reason = _reason_in_turn(session, "lay_on_hands")
        if reason:
            return reason
        if _bonus_spent(session):
            return "bonus_action_spent"
    elif player_incapacitated(session.character, session.world_state):
        return "lay_on_hands_incapacitated"
    if _uses(session.character)["lay_on_hands_spent"] >= pool_maximum(level):
        return "lay_on_hands_pool_exhausted"
    return None


def _remove_condition(character: dict[str, Any], name: str) -> None:
    names = character.get("conditions", [])
    if isinstance(names, dict):
        names.pop(name, None)
    elif name in names:
        names.remove(name)


def _has_condition(character: dict[str, Any], name: str) -> bool:
    names = character.get("conditions", [])
    return bool(names.get(name)) if isinstance(names, dict) else name in names


def _lay_on_hands(session: Any, amount: Any, remove_poisoned: Any, *, on_turn: bool) -> dict[str, Any]:
    character = session.character
    reason = _touch_reason(session)
    if reason:
        raise CombatRequestError(reason, "Lay On Hands is unavailable: " + reason)
    if (amount is not None and (type(amount) is not int or amount < 1)) or type(remove_poisoned) is not bool or (amount is None and not remove_poisoned):
        raise CombatRequestError("lay_on_hands_choice_invalid", "Choose Hit Points to restore, removing the Poisoned condition, or both.")
    if remove_poisoned and not _has_condition(character, "poisoned"):
        raise CombatRequestError("lay_on_hands_not_poisoned", "You do not have the Poisoned condition.")
    level = paladin_level(character)
    uses = _uses(character)
    remaining = pool_maximum(level) - uses["lay_on_hands_spent"]
    cost = (amount or 0) + (LAY_ON_HANDS_POISON_COST if remove_poisoned else 0)
    if cost > remaining:
        raise CombatRequestError("lay_on_hands_pool_exceeded", "The pool does not hold that many Hit Points.")
    if amount is not None and not remove_poisoned and character["current_hp"] >= character["max_hp"]:
        raise CombatRequestError("lay_on_hands_no_wounds", "You have no Hit Points to restore.")
    if on_turn:
        import action_economy as economy
        economy.consume_feature_bonus(session)
    healing = session.heal_player(amount) if amount else 0
    if remove_poisoned:
        _remove_condition(character, "poisoned")
    spent = healing + (LAY_ON_HANDS_POISON_COST if remove_poisoned else 0)  # only restored points leave the pool
    uses["lay_on_hands_spent"] += spent
    _store(character, uses)
    return {"healing": healing, "heal_source": "class_feature", "poisoned_removed": remove_poisoned, "pool_spent": spent, "current_hp": character["current_hp"],
            "pool_remaining": pool_maximum(level) - uses["lay_on_hands_spent"]}


def activate_lay_on_hands(session: Any, amount: Any, remove_poisoned: Any) -> dict[str, Any]:
    from initiative import atomic
    with atomic(session):
        if not session.world_state.get("combat", {}).get("active"):
            raise CombatRequestError("lay_on_hands_current_combat_turn_required", "Outside combat Lay On Hands has its own route.")
        return _lay_on_hands(session, amount, bool(remove_poisoned), on_turn=True)


def lay_on_hands_outside_combat(session: Any, amount: Any, remove_poisoned: Any) -> dict[str, Any]:
    """Outside combat a Bonus Action has no turn budget to spend; the pool is the same one."""
    if session.world_state.get("combat", {}).get("active"):
        raise ValueError("Çatışmada Lay On Hands, kendi turunda Bonus Action ile kullanılır.")
    try:
        return _lay_on_hands(session, amount, bool(remove_poisoned), on_turn=False)
    except CombatRequestError as error:
        raise ValueError(str(error)) from error


def _channel_reason(session: Any, prefix: str) -> str | None:
    level = paladin_level(session.character)
    if level is None or level < CHANNEL_DIVINITY_LEVEL:
        return f"{prefix}_not_available"
    if _now(session) is None:
        return "paladin_clock_required"
    if _uses(session.character)["channel_divinity_spent"] >= channel_divinity_maximum(level):
        return "channel_divinity_uses_exhausted"
    return None


def _divine_sense_reason(session: Any) -> str | None:
    reason = _channel_reason(session, "divine_sense")
    if reason:
        return reason
    if session.world_state.get("combat", {}).get("active"):
        reason = _reason_in_turn(session, "divine_sense")
        if reason:
            return reason
        return "bonus_action_spent" if _bonus_spent(session) else None
    return "divine_sense_incapacitated" if player_incapacitated(session.character, session.world_state) else None


def _start_divine_sense(session: Any) -> dict[str, Any]:
    uses = _uses(session.character)
    uses["channel_divinity_spent"] += 1
    uses["divine_sense_until"] = _now(session) + EFFECT_SECONDS
    _store(session.character, uses)
    level = paladin_level(session.character)
    return {"remaining_seconds": EFFECT_SECONDS, "uses_remaining": channel_divinity_maximum(level) - uses["channel_divinity_spent"],
            "detected": detected(session)}


def activate_divine_sense(session: Any) -> dict[str, Any]:
    from initiative import atomic
    import action_economy as economy
    with atomic(session):
        reason = _divine_sense_reason(session)
        if reason:
            raise CombatRequestError(reason, "Divine Sense is unavailable: " + reason)
        economy.consume_feature_bonus(session)
        return _start_divine_sense(session)


def divine_sense_outside_combat(session: Any) -> dict[str, Any]:
    if session.world_state.get("combat", {}).get("active"):
        raise ValueError("Çatışmada Divine Sense, kendi turunda Bonus Action ile kullanılır.")
    reason = _divine_sense_reason(session)
    if reason:
        raise ValueError("Divine Sense kullanılamıyor: " + reason)
    return _start_divine_sense(session)


def _creature_type(data: dict[str, Any]) -> str | None:
    block = data.get("monster_stat_block")
    value = block.get("creature_type") if isinstance(block, dict) else None
    return value.casefold() if isinstance(value, str) else None


def detected(session: Any) -> list[dict[str, Any]]:
    """Combat participants with a sourced creature type inside the radius. Exploration has no authoritative distance, so nothing is guessed there."""
    import weapon_attack as attacks
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or not divine_sense_active(session):
        return []
    found = []
    for actor in combat.get("participants", []):
        if actor == "player":
            continue
        data = attacks.actor_data(session, actor)
        kind = _creature_type(data)
        if kind not in DIVINE_SENSE_TYPES or data.get("current_hp", 0) <= 0:
            continue
        try:
            distance = attacks.pair(session, "player", actor)["distance_ft"]
        except CombatRequestError:
            continue
        if distance <= DIVINE_SENSE_RANGE_FT:
            found.append({"target_id": actor, "creature_type": kind, "distance_ft": distance})
    return found


def attack_rules(session: Any, data: dict[str, Any], weapon: dict[str, Any], choice: dict[str, Any], origin: str) -> dict[str, Any]:
    """Pure: the attack preview reads this. `sacred_weapon` asks to imbue on this Attack action; the use is spent by `begin_sacred_weapon`."""
    wanted, radiant = choice.get("sacred_weapon"), choice.get("radiant_damage")
    if wanted is None and radiant is None and not (paladin_level(data) and sacred_weapon_active(session)):
        return {}
    if any(value is not None and type(value) is not bool for value in (wanted, radiant)):
        raise CombatRequestError("invalid_attack_choice", "Sacred Weapon choices are strict booleans.", 400)
    instance = weapon.get("instance_id")
    if wanted:
        reason = _sacred_weapon_reason(session, weapon, origin)
        if reason:
            raise CombatRequestError(reason, "Sacred Weapon is unavailable: " + reason, 400)
    elif not instance or not sacred_weapon_active(session, instance):
        if radiant:
            raise CombatRequestError("sacred_weapon_not_active", "Radiant damage needs an active Sacred Weapon on this weapon.", 400)
        return {}
    value = max(SACRED_WEAPON_MINIMUM, (data["charisma"] - 10) // 2)
    return {"attack_modifiers": [{"source": "sacred_weapon", "value": value}]}


def _sacred_weapon_reason(session: Any, weapon: dict[str, Any], origin: str) -> str | None:
    character = session.character
    if not devotion(character):
        return "sacred_weapon_not_available"
    if origin not in {"action", "continuation"}:
        return "sacred_weapon_attack_action_required"
    if weapon.get("kind") != "melee" or not weapon.get("instance_id"):
        return "sacred_weapon_melee_weapon_required"
    reason = _channel_reason(session, "sacred_weapon")
    if reason:
        return reason
    return _reason_in_turn(session, "sacred_weapon")


def begin_sacred_weapon(session: Any, weapon: dict[str, Any]) -> None:
    """Spends the use for an attack whose request carried `sacred_weapon`; using the feature again replaces the earlier imbuing."""
    uses = _uses(session.character)
    uses["channel_divinity_spent"] += 1
    uses["sacred_weapon"] = {"until": _now(session) + EFFECT_SECONDS, "weapon_id": weapon["instance_id"]}
    _store(session.character, uses)


def observe_attack(session: Any, *, weapon: dict[str, Any], target: str, landed: bool, critical: bool) -> None:
    """Runs on every resolved player attack: only the latest one can open the window, and only a hit on the player's own turn does."""
    if paladin_level(session.character) is None:
        return
    combat = session.world_state.get("combat", {})
    sequence = combat.get("turn_resources", {}).get("player", {}).get("weapon_sequence")
    if not isinstance(sequence, dict):
        return
    sequence.pop(SMITE_WINDOW, None)
    if landed and weapon.get("kind") == "melee" and combat.get("current_actor_id") == "player":
        sequence[SMITE_WINDOW] = {"target_id": target, "critical": critical}


def close_smite_window(session: Any) -> None:
    """"Immediately after hitting": any other step closes it."""
    sequence = session.world_state.get("combat", {}).get("turn_resources", {}).get("player", {}).get("weapon_sequence")
    if isinstance(sequence, dict):
        sequence.pop(SMITE_WINDOW, None)


def _smite_window(session: Any) -> dict[str, Any] | None:
    sequence = session.world_state.get("combat", {}).get("turn_resources", {}).get("player", {}).get("weapon_sequence")
    window = sequence.get(SMITE_WINDOW) if isinstance(sequence, dict) else None
    participants = session.world_state.get("combat", {}).get("participants", [])
    if not isinstance(window, dict) or window.get("target_id") not in participants or window["target_id"] == "player":
        return None
    return window if type(window.get("critical", False)) is bool else None  # a window saved before the flag has none and stays open


def _smite_known(session: Any, level: int | None) -> bool:
    if level is None:
        return False
    state = session.world_state.get("spellcasting_v1")
    return level >= SMITE_LEVEL or (isinstance(state, dict) and "Divine Smite" in state.get("prepared", []))


def _smite_reason(session: Any) -> str | None:
    """Everything but the slot choice."""
    import weapon_attack as attacks
    level = paladin_level(session.character)
    if not _smite_known(session, level):
        return "divine_smite_not_available"
    reason = _reason_in_turn(session, "divine_smite")
    if reason:
        return reason
    if _bonus_spent(session):
        return "bonus_action_spent"
    if attacks.conditions(session, "player", session.character) & _VOICELESS:
        return "spell_components_unavailable"
    window = _smite_window(session)
    if window is None:
        return "divine_smite_requires_a_melee_hit"
    if attacks.actor_data(session, window["target_id"]).get("current_hp", 0) <= 0:
        return "divine_smite_target_gone"
    return None


def _available_slots(session: Any) -> list[int]:
    state = session.world_state.get("spellcasting_v1")
    if not isinstance(state, dict):
        return []
    return sorted(int(level) for level, remaining in state["slots"].items() if remaining > 0)


def _slot_marker(session: Any) -> list[Any]:
    import action_economy as economy
    combat = session.world_state["combat"]
    return [combat["combat_id"], combat["round"], economy.ensure(session)["player"]["attack_turn_counter"]]


def _free_smite_ready(session: Any, level: int | None) -> bool:
    return level is not None and level >= SMITE_LEVEL and _uses(session.character)["free_smite_spent"] == 0


def cast_divine_smite(session: Any, slot_level: Any) -> dict[str, Any]:
    """`slot_level` None is the once-per-Long-Rest cast without a slot. A Critical Hit doubles every die: PDF 264 calls it damage from the attack, PDF 363 rolls all of the attack's dice twice."""
    from initiative import atomic
    import action_economy as economy
    import spell_scope
    import weapon_attack as attacks
    with atomic(session):
        reason = _smite_reason(session)
        if reason:
            raise CombatRequestError(reason, "Divine Smite is unavailable: " + reason)
        character = session.character
        level = paladin_level(character)
        state = session.world_state.get("spellcasting_v1")
        spell_scope.validate(state, character)
        if slot_level is None:
            if not _free_smite_ready(session, level):
                raise CombatRequestError("divine_smite_free_cast_spent", "The free cast returns on a Long Rest.")
            spent_level = 1
        else:
            if type(slot_level) is not int or state["slots"].get(str(slot_level), 0) < 1:
                raise CombatRequestError("spell_slot_unavailable", "No spell slot of the selected level remains.")
            if state["slot_turn"] == _slot_marker(session):
                raise CombatRequestError("spell_slot_turn_limit", "Only one spell slot may be expended on this turn.")
            spent_level = slot_level
        window = _smite_window(session)
        target_id = window["target_id"]
        target = attacks.actor_data(session, target_id)
        economy.consume_feature_bonus(session)
        if slot_level is None:
            uses = _uses(character)
            uses["free_smite_spent"] = 1
            _store(character, uses)
        else:
            state["slots"][str(slot_level)] -= 1
            state["slot_turn"] = _slot_marker(session)
        kind = _creature_type(target)
        dice = (SMITE_BASE_DICE + (spent_level - 1) + (1 if kind in SMITE_EXTRA_TYPES else 0)) * (2 if window.get("critical") else 1)
        raw = session.roll_damage(SMITE_DIE, dice, 0)
        damage = attacks.mitigate(session, target_id, "radiant", raw)["final_damage"]
        close_smite_window(session)
        before = target["current_hp"]
        session.apply_npc_damage(target, damage)
        session._combat_end_if_decided()
        return {"target_id": target_id, "slot_level": slot_level, "free_cast": slot_level is None, "dice": dice, "die": SMITE_DIE,
                "raw_damage": raw, "damage": damage, "hp_before": before, "hp_after": target["current_hp"]}


def native_command(command: Any) -> bool:
    """One exact typed Bonus Action step; a free-standing Paladin command never rides with another step."""
    if type(command) is not dict or set(command) != {"steps"} or type(command["steps"]) is not list or len(command["steps"]) != 1:
        return False
    step = command["steps"][0]
    if type(step) is not dict or step.get("resource") != "bonus":
        return False
    fields = {key for key, value in step.items() if value is not None} - {"kind", "resource"}
    if step.get("kind") == "divine_sense":
        return not fields
    if step.get("kind") == "divine_smite":
        return fields <= {"slot_level"} and (step.get("slot_level") is None or type(step["slot_level"]) is int)
    if step.get("kind") == "lay_on_hands":
        return (fields <= {"healing_amount", "remove_poisoned"} and bool(fields)
                and (step.get("healing_amount") is None or (type(step["healing_amount"]) is int and step["healing_amount"] > 0))
                and (step.get("remove_poisoned") is None or step["remove_poisoned"] is True))
    return False


def style(character: Any) -> str | None:
    return character.get("fighting_style") if (paladin_level(character) or 0) >= STYLE_LEVEL else None


def _availability(reason: str | None) -> dict[str, Any]:
    return {"available": reason is None, "reason": reason}


def _spell_rows(session: Any) -> list[dict[str, Any]]:
    import spell_registry
    state = session.world_state.get("spellcasting_v1")
    prepared = list(state.get("prepared", [])) if isinstance(state, dict) else []
    return [{"id": spell, "castable": spell == "Divine Smite" or spell_registry.spell_state(spell) == "resolver"} for spell in prepared]


def projection(session: Any) -> dict[str, Any] | None:
    """The public block. Invalid saved state hides the controls and leaves a log line; any other fault is a real error."""
    character = session.character
    try:
        level = paladin_level(character)
        if level is None:
            return None
        validate_saved(character)
        uses = _uses(character)
        now = _now(session)
        oath = devotion(character)
        channel = None
        if level >= CHANNEL_DIVINITY_LEVEL:
            maximum = channel_divinity_maximum(level)
            channel = {"uses_remaining": maximum - uses["channel_divinity_spent"], "max_uses": maximum}
        sense = None
        if channel:
            active = divine_sense_active(session)
            sense = {"active": active, "remaining_seconds": uses["divine_sense_until"] - now if active else None,
                     "detected": detected(session), "activate": _availability(_divine_sense_reason(session))}
        sacred = None
        if oath:
            active = sacred_weapon_active(session)
            record = uses["sacred_weapon"]
            sacred = {"active": active, "weapon_id": record["weapon_id"] if active else None,
                      "remaining_seconds": record["until"] - now if active else None,
                      "attack_bonus": max(SACRED_WEAPON_MINIMUM, (character["charisma"] - 10) // 2),
                      "start": _availability(_channel_reason(session, "sacred_weapon"))}
        smite = None
        if _smite_known(session, level):
            window = _smite_window(session)
            reason = _smite_reason(session)
            smite = {"activate": _availability(reason), "target_id": window["target_id"] if window else None,
                     "free_cast_available": _free_smite_ready(session, level), "slot_levels": _available_slots(session)}
        return {
            "fighting_style": character.get("fighting_style"),
            "lay_on_hands": {"pool_remaining": pool_maximum(level) - uses["lay_on_hands_spent"], "pool_maximum": pool_maximum(level),
                             "poison_cost": LAY_ON_HANDS_POISON_COST, "activate": _availability(_touch_reason(session))},
            "divine_smite": smite,
            "channel_divinity": channel,
            "divine_sense": sense,
            "sacred_weapon": sacred,
            "always_prepared": always_prepared(level, oath),
            "prepared_spells": _spell_rows(session),
        }
    except ValueError as error:
        logger.warning("Paladin controls hidden: %s", error)
        return None
