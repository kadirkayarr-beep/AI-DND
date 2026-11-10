"""Read-only request guards for the existing Python combat scheduler."""

import re
from dataclasses import dataclass
from typing import Literal

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
    if _conditional_self_defense(text) or told_of_the_past(session, text):
        return True
    return quoted_report(session, message)


_PAST_BLOW = re.compile(
    r"\b(?:saldir|vur|dov|kes|sapl|bicakl|yumrukl|oldur)\w*?(?:d[iu]m|d[iu]k|t[iu]m|t[iu]k|mistim|mustum)\b"
)


def told_of_the_past(session, text):
    """"Kalilayı ben öldürdüm" tells what was done: nobody here is being struck.

    A past verb stays a move in a fight, beside a present verb, or at someone standing here.
    """
    if not _PAST_BLOW.search(text) or session.world_state.get("combat", {}).get("active"):
        return False
    if session._has_explicit_attack_verb(_PAST_BLOW.sub(" ", text)):
        return False
    return not any(
        session._entity_reference_in_text(npc.get(field, ""), text)
        for npc in session.active_npcs() for field in ("name", "role")
    ) and not any(session.named_by_sight(npc, text) for npc in session.active_npcs())


def is_attack_decision(session, message):
    if getattr(session, "_front_strike", None):
        return True  # the turn's reading found a blow on a listed person and Python stood behind it
    import bold_acts
    if quoted_or_conditional_not_attack(session, message) or bold_acts.is_theft(session, message):
        return False
    spoken = living_world._text_outside_quotes(str(message))
    text = session._normalize_turkish_typos(spoken)
    return (session._has_explicit_attack_verb(spoken)
            and not session._is_explicitly_negated_attack(spoken)
            and not re.search(r"\b(?:tehdit|gozdagi|varsay)\w*\b|\b\w+(?:sam|sem)\b", text)  # "vursam ne olur": no blow yet
            and not str(message).rstrip().endswith("?"))


def pointed_targets(session, message):
    """Who the words point at: a name, a role, what shows, or a word for the one at hand."""
    world = session.world_state
    text = session._normalize_turkish_typos(message)
    available = session.active_npcs()
    named = [n for n in available if
             (living_world.npc_name_known_to_player(n)
              and session._entity_reference_in_text(n.get("name", ""), text))
             or (living_world.npc_role_known_to_player(n)
                 and session._entity_reference_in_text(n.get("role", ""), text))
             or session.named_by_sight(n, text)]
    if named:
        return named
    combat = world.get("combat", {})
    if combat.get("active"):
        # In a fight "vursana" means the one you are fighting.
        opponents = [n for n in available if n.get("id") in combat.get("participants", [])]
        fought = [n for n in opponents if n.get("id") == combat.get("target_id")]
        return fought or opponents
    if re.search(r"\b(?:o adam|o kadin|ona|ondan|onunla|kendisine|onu|herif\w*|adam\w*)\b", text):
        flags = world.get("flags", {})
        reference = flags.get("active_npc_id") or flags.get("last_npc_id")
        return [n for n in available if n.get("id") == reference] or available
    return []


def _attack_targets(session, message, target_id):
    """The people this attack can mean: named, pointed at, or the one being spoken to."""
    world = session.world_state
    if target_id is not None:
        return [n for n in world.get("npcs", [])
                if n.get("location") == world.get("location") and n.get("id") == target_id]
    targets = pointed_targets(session, message)
    if targets:
        return targets
    text = session._normalize_turkish_typos(message)
    # A guessed hidden name passes this preflight; the attack's owner then asks who.
    guessed = [n for n in session.active_npcs() if
               session._entity_reference_in_text(n.get("name", ""), text)
               or session._entity_reference_in_text(n.get("role", ""), text)]
    people = session.active_npcs()
    if guessed or (len(people) != 1 and not re.fullmatch(r"\W*(?:ben\s+)?saldir\w*\W*", text)):
        return guessed
    if re.search(r"\b[A-ZÇĞİÖŞÜ]\w+['’]", str(message)):
        return []  # "Gromm'a vuruyorum": someone by name who is not here, not the one who is
    flags = world.get("flags", {})
    reference = flags.get("active_npc_id") or flags.get("last_npc_id")
    return [n for n in people if n.get("id") == reference] or people


def _single_valid_target(session, targets):
    combat = session.world_state.get("combat", {})
    return (len(targets) == 1
            and targets[0].get("combat_status", "active") in (
                {"active", "unconscious"} if combat.get("active") else {"active"})
            and (combat.get("active") or targets[0].get("current_hp", 1) > 0))


_FLIGHT = re.compile(
    r"\b(?:kac(?:iyorum|ip|acagim|ayim|alim)|sivis\w*|uzaklasiyorum|geri cekiliyorum|tabanlari yagl\w*|"
    r"\w+(?:dan|den|tan|ten) cik(?:iyorum|acagim|ayim))\b|\bdisari cik\w*"
)


def is_flight(session, message):
    """In a fight, walking off is running away."""
    world = session.world_state
    return (isinstance(message, str) and "?" not in message and bool(world.get("combat", {}).get("active"))
            and bool(_FLIGHT.search(session._normalize_turkish_typos(message))))


def _flight_refused(session, reason_code, narration):
    """No flight happened: the fight and the place stay as they were, and nothing claims a move."""
    return {"messages": session.messages, "narration": narration, "model_calls": 0,
            "action_result": {"action": "flee", "status": "rejected", "success": False,
                              "reason_code": reason_code, "state_changes": [], "direct_response": narration}}


def _flight_cut_off(session, action_id, session_id, reason_code, lead):
    """The attempt was made but led nowhere: the turn is lost in the fight, and no move is claimed."""
    import action_economy
    result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]}, action_id, session_id)
    result["narration"] = f"{lead} {result.get('narration', '')}".strip()
    result["action_result"].update(reason_code=reason_code, state_changes=["combat"])
    return result


def flee(session, action_id=None, session_id=None):
    """A real attempt: away and out of the place, or the turn is lost and the blows land.

    Speed and the way out are checked before the roll; the fight ends only with a committed change of place.
    """
    import action_economy
    world = session.world_state
    combat = world["combat"]
    if combat.get("current_actor_id") != "player" or session.character.get("current_hp", 0) <= 0:
        return None
    if action_economy.speed(session, "player") <= 0:
        return _flight_refused(session, "speed_zero", "Kıpırdayamıyorsun; kaçmak şu an elinde değil.")
    import exits
    import refusals
    import world_reactions
    way_out = exits.way_out(world, world.get("location"), open_if_needed=True)
    if way_out is None:
        code = "no_exit_held" if world_reactions.arrester(world) is not None else "no_exit"
        refusals.note(session, code)
        return _flight_cut_off(session, action_id, session_id, "no_exit", refusals.text_for(code))
    character = session.character
    check = session.perform_skill_check(
        "Acrobatics", 12, character["modifiers"], character.get("proficient_skills") or [],
        character.get("proficiency_bonus") or 2, expertise_skills=character.get("expertise_skills") or (),
    )
    if check["result"] == "BAŞARILI":
        # The way out takes what walking it takes (a long road is no step through a door): the same as a walk out.
        left = (world.get("locations") or {}).get(world.get("location")) or {}
        road_seconds = int(left.get("walk_seconds") or 0)
        if not session.commit_location_change(way_out):
            return _flight_cut_off(session, action_id, session_id, "exit_blocked",
                                   "Boşluğu buluyorsun ama çıkış yolun kapalı; kavga sürüyor.")
        session.end_combat("player_fled")  # commit already closed it on leaving; this keeps the fight's own reason
        world["combat"]["end_reason"] = "player_fled"
        narration = "Bir boşluk yakalayıp sıyrılıyorsun; ardından gelen bağırışlar geride kalıyor."
        changes = ["combat", "location"]
        if road_seconds > 0 and "campaign_time" in world:
            passed = session.advance_campaign_time(road_seconds, "exploration") or {}
            changes.append("campaign_time")
            known = " ".join(event["summary"] for event in passed.get("player_known_events") or [])
            narration = f"{narration} {known}".strip()
        return {"messages": session.messages, "narration": narration, "model_calls": 0,
                "action_result": {"action": "flee", "status": "resolved", "success": True,
                                  "state_changes": changes, "direct_response": narration}}
    result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]}, action_id, session_id)
    result["narration"] = f"Kaçacak bir açık bulamıyorsun; yolun kesiliyor. {result.get('narration', '')}".strip()
    return result


_STAND_DOWN = re.compile(
    r"\b(?:kusura bakma\w*|ozur dile\w*|affet\w*|bagisla\w*|yanlislik\w*|dur dur|sakin ol\w*|barisalim|"
    r"kilic\w* indir\w*|silah\w* (?:indir|birak|kinina)\w*|saldirmiyorum|saldirmayacagim|vurmayacagim|"
    r"(?:dovusmek|kavga etmek) istemiyorum|kavga bitsin|teslim ol\w*|vazgectim)\b"
)


def is_standing_down(session, message):
    """"Kılıcı indiriyorum, kusura bakma": the words end the fight, unless a blow goes with them."""
    world = session.world_state
    if not isinstance(message, str) or not world.get("combat", {}).get("active"):
        return False
    text = session._normalize_turkish_typos(message)
    return bool(_STAND_DOWN.search(text)) and not is_attack_decision(session, message)


def _meant_no_harm(session):
    combat = session.world_state["combat"]
    others = [npc for npc in session.world_state.get("npcs", [])
              if isinstance(npc, dict) and npc.get("id") in combat.get("participants", [])]
    return bool(others) and not any(npc.get("hostile") for npc in others), others


def stand_down(session, action_id=None, session_id=None):
    """Someone who never wanted this fight may take the way out. A real attempt, and it can fail."""
    import relationships
    world = session.world_state
    combat = world["combat"]
    harmless, others = _meant_no_harm(session)
    if not harmless or combat.get("current_actor_id") != "player" or session.character.get("current_hp", 0) <= 0:
        return None
    character = session.character
    check = session.perform_skill_check(
        "Persuasion", 12, character["modifiers"], character.get("proficient_skills") or [],
        character.get("proficiency_bonus") or 2, expertise_skills=character.get("expertise_skills") or (),
    )
    turn = world.get("flags", {}).get("turn_index", 0)
    if check["result"] == "BAŞARILI":
        session.end_combat("stood_down")
        for npc in others:
            relationships.note(world, npc["id"], -1, f"stood_down:{turn}")
        who = living_world.public_npc_name(others[0])
        narration = (f"{who} soluk soluğa bir adım geri çekiliyor, ellerini indirmiyor ama "
                     "üstüne de gelmiyor. Kavga bitti; bu iş unutulmuş değil.")
        return {"messages": session.messages, "narration": narration, "model_calls": 0,
                "action_result": {"action": "stand_down", "status": "resolved", "success": True,
                                  "state_changes": ["combat", "relationships"], "direct_response": narration}}
    import action_economy
    result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]}, action_id, session_id)
    result["narration"] = f"Seni dinleyecek halde değil; üstüne gelmeyi bırakmıyor. {result.get('narration', '')}".strip()
    return result


# An English yes (Dilim 4A): decided only for a line that LEADS with an English yes-word, so no Turkish word is ever read
# as English (Turkish "ok" is an arrow). An English no, not, never, n't or any question mark voids it, and so do the English
# twins of the Turkish guards (a condition, a threat, a hold word): a wrong blow at the wrong person cannot be taken back.
_ENGLISH_YES_LEADS = re.compile(r"\W*(?:yes|yeah|yep|sure|okay|ok|do it)\b")
_ENGLISH_NO = re.compile(r"\b(?:no|not|never|dont)\b|n['’]t\b")
_ENGLISH_NOT_NOW = re.compile(r"\b(?:if|when|unless|until|once|threaten\w*|wait|later|hold|stop|hang)\b")
_THEM = re.compile(r"\b(?:him|her|them)\b")


def _move_at_the_person(session, message, blow):
    """The words name a move the engine reads and aim it at the one asked about (named, or him/her/them)."""
    import weapon_attack
    if not weapon_attack.names_a_move(session, message):
        return False
    named = [npc["id"] for npc in pointed_targets(session, message)]
    if named:
        return blow is None or blow in named
    return _THEM.search(str(message).lower()) is not None


def _says_yes(session, message, blow=None):
    """A short yes, or a yes that leads a longer line still standing behind the blow ('Evet, adamı itiyorum')."""
    import game
    text = session._normalize_turkish_typos(str(message))
    spoken = living_world._text_outside_quotes(str(message)).lower()  # a yes or a blow only quoted is nobody's act
    if _ENGLISH_YES_LEADS.match(spoken) is not None:
        if (_ENGLISH_NO.search(spoken) or "?" in spoken or _ENGLISH_NOT_NOW.search(spoken)
                or game._CLAIM_REJECTION_RE.search(text) is not None):
            return False
        if len(spoken.split()) <= 4:
            return True
        # A long yes in English needs the move in its own words, aimed at the person asked about: "Yes, tell me about
        # the guard", "Yes, I punch the wall" start nothing.
        return game._blow_stands(spoken) and _move_at_the_person(session, spoken, blow)
    if game._CLAIM_ACCEPTANCE_RE.search(text) is None or game._CLAIM_REJECTION_RE.search(text) is not None:
        return False
    if len(text.split()) <= 4:
        return True
    leads = game._CLAIM_ACCEPTANCE_RE.match(text.split()[0]) is not None
    return leads and game._blow_stands(message)


def answered_attack_question(session, message):
    """"Kime saldırıyorsun?" - "çelimsiz biri": the answer finishes the sentence."""
    asked = getattr(session, "_attack_asked", False)
    session._attack_asked = False
    blow, session._blow_asked = getattr(session, "_blow_asked", None), None
    asked_line, session._blow_asked_line = getattr(session, "_blow_asked_line", None) or {}, None
    here = bool(blow) and any(npc.get("id") == blow for npc in session.active_npcs())
    import game
    import weapon_attack
    if here and asked_line.get("choose"):
        # "itip yere mi düşürüyorsun, yumruk mu?": only an answer naming a move the engine reads makes the blow
        if weapon_attack.names_a_move(session, message) and game._blow_stands(message):
            session._front_strike = {"kind": "strike", "id": blow, "with": "", "said": ""}
        elif _says_yes(session, message, blow):
            session._which_move = blow  # a second bare yes is no answer: the same question again
        return message
    if here and _says_yes(session, message, blow):
        said = asked_line.get("said") or ""
        if not asked_line.get("with") and not weapon_attack.names_a_move(session, f"{said} {message}"):
            session._which_move = blow  # a yes to words naming no move the engine has (a trip): asked, nothing rolls
            return message
        # "kavga mı başlatıyorsun?" - "evet": the blow is the one the asked line said, never the bare yes alone
        session._front_strike = {"kind": "strike", "id": blow, "with": asked_line.get("with") or "", "said": said}
        return message
    if not asked or len(str(message).split()) > 4:
        return message
    return f"{message} saldırıyorum" if pointed_targets(session, message) else message


def strike_the_fallen(session, message, target_id=None):
    """Someone already out cold: no roll to hit them, and no second knock-out to give."""
    world = session.world_state
    if (world.get("combat", {}).get("active") or session.character.get("current_hp", 0) <= 0
            or not is_attack_decision(session, message)):
        return None
    targets = _attack_targets(session, message, target_id)
    if len(targets) != 1 or targets[0].get("combat_status") != "unconscious":
        return None
    import weapon_attack
    who = living_world.public_npc_name(targets[0])
    if weapon_attack.natural_choice(session, message)[1].get("knock_out") is True:
        return f"{who} zaten baygın; bir daha vurmana gerek yok."
    session.apply_npc_damage(targets[0], targets[0]["current_hp"])
    return f"{who} yerde savunmasız yatıyor; darben son nefesini alıyor."


def unbound_attack_reply(session, message, target_id=None):
    """An attack with no single target is asked about in the world."""
    if (
        target_id is not None
        or session.character.get("current_hp", 0) <= 0
        or not is_attack_decision(session, message)
        or _single_valid_target(session, _attack_targets(session, message, None))
    ):
        return None
    people = session.active_npcs()
    if not people:
        return "Kime saldırıyorsun? Şu an yakınında kimse görünmüyor."
    return f"Kime saldırıyorsun? Yakında {living_world.public_scene_people(people[:4])} var."


def walks_off(session, message):
    """The player's own words say they walk away now; telling someone else to go is no walk."""
    text = session._normalize_turkish_typos(str(message))
    return bool(re.search(r"\b(?:gidiyorum|gitmek|giriyorum|yolculu|seyahat)", text)
                or re.fullmatch(r"geri don(?:uyorum|uyoruz|dum|duk)?", text)
                or living_world.classify_scene_action(message) == "exit")


def walks_on_own_feet(session, message):
    """A travel reading where the player's own '-yorum' moves them ('sokağa yürüyorum', 'çıkıyorum'): a walk, not words."""
    import grounded_action
    text = session._normalize_turkish_typos(living_world._text_outside_quotes(str(message)))
    for word in re.findall(r"\w+", text):
        verb = grounded_action._verb_of(word)
        if (verb and verb[0] in {"go", "enter", "leave", "wander", "climb"} and not verb[1]
                and grounded_action._FIRST_PERSON_ACT.fullmatch(word)):
            return True
    return False


@dataclass(frozen=True)
class ApproachResult:
    status: Literal["moved", "short", "which", "not_a_participant"]
    moved_ft: int
    left_ft: int            # moved: the movement still left this turn; short: the feet still to go to reach the target
    target_id: str | None
    names: tuple[str, ...]


def asked_names(names):
    """'Haydut mu, Okçu mu': each name with the question word that follows its last vowel."""
    def asked(name):
        vowel = next((c for c in reversed(name.lower()) if c in "aıoueiöü"), "a")
        return f"{name} {'mı' if vowel in 'aı' else 'mi' if vowel in 'ei' else 'mu' if vowel in 'ou' else 'mü'}"
    return ", ".join(asked(name) for name in names)


def approach(session, target_id, *, named):
    """Walking toward someone in the fight is combat movement: the distance less 5 feet, held to the movement left.
    With no id but a person named, the one enemy is the target; with several the player is asked which (no move)."""
    import action_economy
    import spatial_rules
    combat = session.world_state["combat"]
    fighting = [n for n in session.active_npcs() if n.get("id") in combat["participants"] and n.get("id") != "player"]
    enemies = [n for n in fighting if n.get("combat_status", "active") == "active"]
    if target_id is None and named and len(enemies) > 1:
        names = tuple(living_world.public_npc_name(n) for n in enemies)
        return ApproachResult("which", 0, 0, None, names)
    if target_id is None and named and len(enemies) == 1:
        target_id = enemies[0]["id"]
    target = next((n for n in fighting if n.get("id") == target_id
                   and n.get("combat_status", "active") in {"active", "unconscious"}), None)
    if target is None:
        return ApproachResult("not_a_participant", 0, 0, target_id, ())
    distance = target.get("distance_ft", 5)
    need = max(0, distance - 5)
    r = action_economy.ensure(session)["player"]
    left = action_economy.movement_limit(session, "player") - r["movement_used"]
    crawling = bool(action_economy.actor_data(session, "player").get("prone")
                    or "prone" in action_economy.conditions(session, "player"))
    step_cost = spatial_rules.movement_cost(1, crawling=crawling)
    can = max(0, left) // step_cost if action_economy.speed(session, "player") > 0 else 0
    moved = min(need, can)
    if moved:
        action_economy.move(session, "player", moved)   # the fight's own movement owner checks and spends it
        if "distance_ft" in target:                      # an encounter's own map may have taken the feet over
            target["distance_ft"] = distance - moved
    name = (living_world.public_npc_name(target),)
    if moved == need:
        return ApproachResult("moved", moved, max(0, left - moved * step_cost), target_id, name)
    return ApproachResult("short", moved, need - moved, target_id, name)


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
            if target_id is None and combat_id is None:
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
        import action_economy
        if is_flight(session, message) or action_economy.wants_rage(session, text):
            return
        if is_attack_decision(session, message):
            return
        if walks_off(session, message):
            raise CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)