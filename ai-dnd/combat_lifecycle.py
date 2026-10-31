"""Read-only request guards for the existing Python combat scheduler."""

import re

import living_world

INCAPACITATED = {"incapacitated", "unconscious", "dead", "paralyzed", "stunned", "petrified"}


class CombatRequestError(ValueError):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def player_incapacitated(character, world):
    """The player cannot use a class feature: 0 HP, a non-active combat status, death, or a condition that stops action."""
    conditions = character.get("conditions", [])
    if isinstance(conditions, dict):
        conditions = [name for name, present in conditions.items() if present]
    names = {str(name).lower() for name in conditions}
    return (character.get("current_hp", 0) <= 0 or world.get("player_combat_status", "active") != "active"
            or bool(world.get("death_state", {}).get("dead")) or bool(names & INCAPACITATED))


def registered_name_candidates(session):
    """Read local multiword names without requiring migrated target IDs.

    Combat preflight runs before scene migration. Merely recognizing a name
    must not create doors/references or require a complete targeting registry.
    """
    world = session.world_state
    here = world.get("location")
    locations = world.get("locations", {})
    current = locations.get(here, {}) if isinstance(locations, dict) else {}
    parent = current.get("parent_location_id") if isinstance(current, dict) else None
    anchors = {value for value in (here, parent) if isinstance(value, str)}
    records = [place for key, place in locations.items()
               if isinstance(place, dict) and not place.get("hidden")
               and (key in anchors or place.get("parent_location_id") in anchors)] if isinstance(locations, dict) else []
    records.extend(record for key in ("doors", "features") for record in world.get(key, [])
                   if isinstance(record, dict) and not record.get("hidden")
                   and record.get("discovered") is not False
                   and (record.get("location") == here or record.get("place_id") == here))
    records.extend(npc for npc in session.active_npcs()
                   if isinstance(npc, dict) and not npc.get("hidden")
                   and living_world.npc_name_known_to_player(npc))
    return [{"names": [record["name"]]} for record in records
            if isinstance(record.get("name"), str) and len(record["name"].split()) > 1]


def _conditional_self_defense(text):
    """Someone else might attack, and the player only says they will defend."""
    if not re.search(
        r"\b(?:saldirirsa|saldirirlarsa|saldirdiginda|saldirdiklarinda)\b", text
    ):
        return False
    if not re.search(r"\bsavun(?:acag\w*|urum|uruz|uyorum|uyoruz)\b", text):
        return False
    return not re.search(
        r"\b(?:saldir|vur|dov|kes|sapla|bicakl|yumrukla)"
        r"(?:iyorum|iyoruz|acagim|acagiz|ecegim|ecegiz|dim|dik|dum|duk)\b",
        text,
    )


def quoted_report(session, message):
    """An attack verb that survives only inside quotation is a report."""
    spoken = living_world._text_outside_quotes(str(message))
    return (
        not session._has_explicit_attack_verb(spoken)
        and session._has_explicit_attack_verb(message)
    )


def quoted_or_conditional_not_attack(session, message):
    """A quoted report or a conditional defense is not the player's attack.

    Called from is_attack_decision and from game.execute_intent. Reads only the
    player message. Writes nothing: no HP, distance, or combat mutation.
    """
    spoken = living_world._text_outside_quotes(str(message))
    text = session._normalize_turkish_typos(spoken)
    if _conditional_self_defense(text):
        return True
    return quoted_report(session, message)


def is_attack_decision(session, message):
    if quoted_or_conditional_not_attack(session, message):
        return False
    spoken = living_world._text_outside_quotes(str(message))
    text = session._normalize_turkish_typos(spoken)
    return (session._has_explicit_attack_verb(spoken)
            and not session._is_explicitly_negated_attack(spoken)
            and not re.search(r"\b(?:tehdit|gozdagi|varsay|saldirsam)\w*\b", text)
            and not str(message).rstrip().endswith("?"))


def _attack_targets(session, message, target_id):
    """The people this attack can mean: named, pointed at, or the one being spoken to."""
    world = session.world_state
    text = session._normalize_turkish_typos(message)
    targets = [n for n in world.get("npcs", []) if n.get("location") == world.get("location") and (
        n.get("id") == target_id if target_id is not None else
        session._entity_reference_in_text(n.get("name", ""), text)
        or session._entity_reference_in_text(n.get("role", ""), text)
    )]
    if not targets and target_id is None and (
        re.search(r"\b(?:o adam|o kadin|ona|ondan|onunla|kendisine)\b", text)
        or re.fullmatch(r"\W*(?:ben\s+)?saldir\w*\W*", text)
    ):
        available = session.active_npcs()
        flags = world.get("flags", {})
        reference = flags.get("active_npc_id") or flags.get("last_npc_id")
        referenced = [n for n in available if n.get("id") == reference]
        targets = referenced if referenced else available
    return targets


def _single_valid_target(session, targets):
    combat = session.world_state.get("combat", {})
    return (len(targets) == 1
            and targets[0].get("combat_status", "active") in (
                {"active", "unconscious"} if combat.get("active") else {"active"})
            and (combat.get("active") or targets[0].get("current_hp", 1) > 0))


def unbound_attack_reply(session, message, target_id=None):
    """An attack out of combat with no single target is asked about in the world."""
    world = session.world_state
    if (
        world.get("combat", {}).get("active") or target_id is not None
        or session.character.get("current_hp", 0) <= 0
        or not is_attack_decision(session, message)
        or _single_valid_target(session, _attack_targets(session, message, None))
    ):
        return None
    people = session.active_npcs()
    if not people:
        return "Kime saldırıyorsun? Şu an yakınında kimse görünmüyor."
    return f"Kime saldırıyorsun? Yakında {living_world.public_scene_people(people[:4])} var."


def validate_request(session, message, target_id=None, *, combat_id=None,
                     combat_round=None, combat_turn_index=None):
    """Client context is an optimistic precondition, never combat authority."""
    world = session.world_state
    combat = world.get("combat", {})
    if combat_id is not None and (
        not combat.get("active") or combat.get("combat_id") != combat_id
        or combat.get("round") != combat_round
        or combat.get("current_turn_index") != combat_turn_index
    ):
        raise CombatRequestError("stale_combat", "Combat or turn context is stale.")
    attack = is_attack_decision(session, message)
    if attack and session.character.get("current_hp", 0) > 0:
        import weapon_attack
        weapon, choice = weapon_attack.natural_choice(session, message)
        if weapon != "unarmed" and not session.find_weapon_in_inventory(weapon)[0]:
            raise CombatRequestError("no_weapon", "No valid weapon is available.", 400)
        targets = _attack_targets(session, message, target_id)
        if not _single_valid_target(session, targets):
            if target_id is None and combat_id is None and not combat.get("active"):
                return  # asked in the world by unbound_attack_reply, not refused
            raise CombatRequestError("invalid_combat_target", "Select one valid local target.", 400)
        if not combat.get("active"):
            # A person in the scene with no recorded distance is within a step:
            # an opening strike must not end as an HTTP refusal.
            targets[0].setdefault("distance_ft", 5)
        if combat.get("active") and targets[0]["id"] not in combat["participants"]:
            raise CombatRequestError("invalid_combat_target", "Target is not a participant.", 400)
        if combat.get("active") and combat["current_actor_id"] != "player":
            raise CombatRequestError("out_of_turn", "It is not the player's action turn.")
        import action_economy
        command = action_economy.natural_command(session, message, targets[0]["id"])
        origin = (command["steps"][0].get("attack_origin", "action")
                  if command and command["steps"][0]["kind"] == "attack" else "action")
        weapon_attack.preview(session, "player", targets[0]["id"], weapon, choice, origin=origin)
    if combat.get("active"):
        session._validate_combat_v3_payload(combat)
        if attack and session.character.get("current_hp", 0) > 0:
            import action_economy
            if combat["current_actor_id"] != "player":
                raise CombatRequestError("out_of_turn", "It is not the player's action turn.")
        # Also validate a selected target on an NPC-turn pulse; never run a
        # real automatic turn on behalf of a forged target request.
        if target_id is not None:
            npc = next((n for n in world.get("npcs", []) if n.get("id") == target_id), None)
            if (not npc or target_id not in combat["participants"]
                or npc.get("location") != world.get("location")
                or npc.get("combat_status", "active") not in {"active", "unconscious"}):
                raise CombatRequestError("invalid_combat_target", "Target is not an active local participant.", 400)
        text = session._normalize_turkish_typos(message)
        if (re.search(r"\b(?:gidiyorum|gitmek|giriyorum|yolculu|seyahat)", text)
                or re.fullmatch(r"geri don(?:uyorum|uyoruz|dum|duk)?", text)
                or living_world.classify_scene_action(message) == "exit"):
            raise CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)