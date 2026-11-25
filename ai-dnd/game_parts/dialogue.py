import game
import collections
import logging
import combat_lifecycle
import hashlib
import interaction_adventure
import living_world
import local_dialogue
import npc_statements
import re
import talk_front
import talk_mode
import tr_case
import money_owner


def _claimed_completed_outcome(player_input):
    if not isinstance(player_input, str):
        return False
    text = game._normalize_turkish_typos(player_input)
    if "?" in player_input or re.search(r"\b(?:degil|olmadim|almadim|olacagim|alacagim)\b", text):
        return False
    return bool(re.search(r"\b(?:oldum|aldim|kazandim|kabul ettim|tamamladim)\b", text))

def _conversation_npcs():
    import exploration
    awake = [npc for npc in game.active_npcs() if npc.get("combat_status") != "unconscious"]
    return exploration.player_entities(game._session().world_state, awake)

def _active_interlocutor():
    """Return the current valid Python-owned conversation target without mutating state."""
    return talk_mode.current(game._session().world_state)

def _clear_active_interlocutor(reason):
    return talk_mode.close(game._session().world_state, reason)

def _is_end_conversation_request(player_input):
    text = game._normalize_turkish_typos(str(player_input))
    return bool(re.search(
        r"\b(?:konusmayi|sohbeti)\s+(?:bitir|bitiriyorum|sonlandir|sonlandiriyorum)\b",
        text,
    ))

def _without_place_names(text, world_state):
    """The player's text with every place name blanked, Turkish endings included."""
    for location in world_state.get("locations", {}).values():
        name = location.get("name") if isinstance(location, dict) else None
        normalized = game._normalize_turkish_typos(name) if isinstance(name, str) else ""
        if normalized:
            text = re.sub(rf"(?<![a-z0-9]){re.escape(normalized)}[a-z0-9]*", " ", text)
    return text

def _words_fit_person(npc, text):
    """A plain word for what this person visibly is, beyond the shown label."""
    return (bool(game._GUARD_WORD.search(text)) and game._is_guard(npc)) or (
        any(word in text for word in game._COUNTER_WORDS) and game._serves_at_a_counter(npc)
    )

def most_plausible_addressee(people, player_input=""):
    """Who an address with no named person goes to; None when nobody is here.

    The current conversation partner, then the last person addressed, then the
    one the words fit, then the nearest person who is not standing guard.
    """
    people = [npc for npc in people if isinstance(npc, dict) and npc.get("id")]
    if not people:
        return None
    flags = game._session().world_state.get("flags", {})
    for key in ("active_npc_id", "last_npc_id"):
        partner = next((npc for npc in people if npc["id"] == flags.get(key)), None)
        if partner is not None:
            return partner
    text = game._normalize_turkish_typos(str(player_input))
    pool = [npc for npc in people if game._words_fit_person(npc, text)] or people

    def distance(npc):
        value = npc.get("distance_ft")
        return value if isinstance(value, (int, float)) else 1000

    return min(pool, key=lambda npc: (game._is_guard(npc), distance(npc)))

def _absent_described_person(player_input, people):
    """The word for "the man at the counter", when no such place or person is here."""
    match = game._LOCATED_PERSON.search(str(player_input))
    if match is None:
        return None
    stem = living_world.normalize_text(match.group(1))
    if stem.startswith(game._IN_REACH_WORDS):
        return None
    world_state = game._session().world_state
    here = world_state.get("location")
    place = world_state.get("locations", {}).get(here)
    seen = []
    if isinstance(place, dict):
        seen.extend(str(place.get(key) or "") for key in ("name", "description"))
    for feature in world_state.get("features", []):
        if isinstance(feature, dict) and feature.get("location") == here and not feature.get("hidden"):
            seen.append(str(feature.get("name") or ""))
            seen.extend(str(alias) for alias in feature.get("aliases", []) or [])
    for npc in people:
        seen.extend(str(npc.get(key) or "") for key in ("role", "appearance"))
        if stem.startswith(game._COUNTER_WORDS) and game._serves_at_a_counter(npc):
            return None
    if any(stem in living_world.normalize_text(text) for text in seen):
        return None
    return match.group(1)

def _absent_person_text(place_word):
    people = game.active_npcs()[:3]
    present = (
        f" Yakında {living_world.public_scene_people(people)} var." if people else ""
    )
    word = tr_case.upper_first(place_word)
    return f"{word} başında öyle birini göremiyorsun.{present}"

def _settle_address(resolution, player_input):
    """Several people could be meant by a line that is not an attack: pick one."""
    if resolution.get("status") != "ambiguous":
        return resolution
    npc = game.most_plausible_addressee(resolution.get("npcs", []), player_input)
    if npc is None:
        return resolution
    world_state = game._session().world_state
    talk_mode.open(world_state, npc["id"], turn=world_state.setdefault("flags", {}).get("turn_index", 0))
    return {"status": "found", "npc": npc}

def _word_for_nobody_here(word, people):
    """The model's word for a person, kept only when nobody among ``people`` answers to it (else None: today's path)."""
    if not isinstance(word, str) or not word.strip():
        return None
    return None if any(game._npc_answers_to(npc, game._normalize_turkish_typos(word)) for npc in people) else word

def resolve_npc_reference(
    player_input, force_dialogue=False, allow_active_fallback=True, *, named_word=None
):
    world_state = game._session().world_state
    if named_word is None:
        named_word = getattr(game._session(), "_named_word", None)  # this turn's reading, whoever asks
    text = game._normalize_turkish_typos(player_input)
    available = game._conversation_npcs() if force_dialogue else game.active_npcs()
    named_word = game._word_for_nobody_here(named_word, available)  # a word someone here answers to: today's path
    matches = [npc for npc in available if game._npc_answers_to(npc, text)]
    # Hidden canonical identity must never become target authority just because
    # the player guessed an internal name/role string. Generic pronouns may still
    # use the active conversation below. A person the player does know, or a
    # place that shares the hidden name, is not such a guess: names come from
    # one pool and can read as a plain word ("Basim" in "başımla").
    hidden_scan_text = game._without_place_names(text, world_state)
    hidden_identity_reference = any(
        (
            not living_world.npc_name_known_to_player(npc)
            and game._entity_reference_in_text(npc.get("name", ""), hidden_scan_text)
        )
        or (
            not living_world.npc_role_known_to_player(npc)
            and game._entity_reference_in_text(npc.get("role", ""), hidden_scan_text)
        )
        for npc in available
    )
    if hidden_identity_reference and not matches:
        return {"status": "none", "npc": None}

    if len(matches) > 1:
        # "Sera, ..." or "sera'ya soruyorum": the person spoken TO wins over
        # people merely mentioned in the same sentence.
        addressee = game._explicit_addressee(player_input, matches)
        if addressee is not None:
            matches = [addressee]

    if local_dialogue.unresolved_named_address(player_input, available):
        return {"status": "none", "npc": None}

    # Pronouns can use the current conversation; unknown named targets cannot.
    explicit_unresolved_reference = any(
        match.group("target") not in {"ona", "ondan", "onunla", "kendisine"}
        and not local_dialogue.is_nominal_speech_reference(player_input[match.start():])
        and not game._is_plain_person_reference(player_input.casefold()[:match.start()], match.group("target"))
        for match in re.finditer(
            r"\b(?P<target>[\wçğıöşü]+(?:['’](?:dan|den|tan|ten)|la|le|dan|den|tan|ten|a|e))\s+(?:konuş\w*|sohbet\w*|selam\s+ver\w*)\b",
            player_input.casefold(),
        )
    )
    short_followup = game._is_short_conversation_continuation(player_input)
    object_inspection = game._is_object_inspection(player_input) and not re.search(
        r"\b(?:o adam|o kadin|ona|ondan|onunla|kendisine|sana|seni)\b", text
    )
    if allow_active_fallback and not matches:
        absent = game._absent_described_person(player_input, available)
        if absent:
            return {"status": "none", "npc": None, "absent": absent}
        if isinstance(named_word, str) and named_word.strip():
            # The reading named someone who is not here: nobody, never the last one spoken to (the turn closes the talk)
            if talk_mode.addressee(world_state, available, named_word=named_word).status == "nobody_here":
                return {"status": "none", "npc": None, "nobody_here": named_word.strip()}
    if allow_active_fallback and not matches and not explicit_unresolved_reference and not object_inspection and (
        force_dialogue
        or game.is_npc_dialogue_input(player_input)
        or re.search(r"\b(?:o adam|o kadın|ona|ondan|onunla|kendisine)\b", text)
        or interaction_adventure.is_focus_followup(world_state, player_input)
        or short_followup
        or (game._ASKS_SOMETHING.search(text) and game._just_served(world_state))
    ):
        flags = world_state.setdefault("flags", {})
        active_id = flags.get("active_npc_id") or flags.get("last_npc_id")
        active_until = flags.get("active_npc_until_turn", -1)
        active = next((npc for npc in available if npc.get("id") == active_id), None)
        if (active and active.get("location") == world_state.get("location")
                and flags.get("turn_index", 0) <= active_until):
            matches = [active]
        elif short_followup and not force_dialogue:
            # "e sonra" with nobody to continue with is not a call to everyone.
            matches = []
        elif len(available) == 1:
            matches = available[:]
        elif len(available) > 1:
            matches = available[:]
    if len(matches) == 1:
        talk_mode.open(world_state, matches[0].get("id"), turn=world_state.setdefault("flags", {}).get("turn_index", 0))
        return {"status": "found", "npc": matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "npcs": matches}
    return {"status": "none", "npc": None}

def _interaction_proposal_applies(raw_intent, npc_target, player_input):
    if combat_lifecycle.quoted_report(game._session(), player_input):
        return False
    interaction = raw_intent.get("interaction") if isinstance(raw_intent, dict) else None
    if not isinstance(interaction, dict) or interaction.get("operation") in (None, "none"):
        return False
    hint = interaction_adventure.hint(player_input)
    if (
        npc_target is None
        and interaction.get("operation") in game._ADDRESSEE_OPERATIONS
        and hint is None
    ):
        return False
    # An offer, promise or threat must be in the player's own words. "Kapıyı
    # kırmayacağım, merak etme Sera" is reassurance, not a deal to negotiate.
    grounded_item_request = game._grounded_item_request_proposal(
        raw_intent, npc_target, player_input
    )
    if (
        interaction.get("operation") in game._OFFER_OPERATIONS
        and hint not in game._OFFER_OPERATIONS
        and not game._OFFER_MARKER.search(game._normalize_turkish_typos(player_input))
        and not (
            interaction.get("operation") == "request"
            and grounded_item_request
        )
    ):
        return False
    return True

def _grounded_item_request_proposal(raw_intent, npc_target, player_input):
    """Authorize the non-conversation request route only with independent grounding."""
    if not isinstance(raw_intent, dict) or not isinstance(npc_target, dict):
        return False
    interaction = raw_intent.get("interaction")
    if not isinstance(interaction, dict) or interaction.get("operation") != "request":
        return False
    if raw_intent.get("intent") not in {"dialogue", "interact"}:
        return False
    proposed_action = raw_intent.get("action")
    if not isinstance(proposed_action, str) or proposed_action.casefold() not in {
        "dialogue", "interact",
    }:
        return False

    world_npcs = game._session().world_state.get("npcs", [])
    canonical_npc = next(
        (
            candidate for candidate in world_npcs
            if isinstance(candidate, dict)
            and candidate.get("id") == npc_target.get("id")
        ),
        None,
    )
    if canonical_npc is None:
        return False

    target = raw_intent.get("target")
    if isinstance(target, dict):
        proposed_npc_id = target.get("npc_id")
        if proposed_npc_id and proposed_npc_id != canonical_npc["id"]:
            return False
        if target.get("type") == "npc" and proposed_npc_id != canonical_npc["id"]:
            return False

    quote = interaction.get("quote")
    requested_item = interaction.get("requested_item")
    if (
        not isinstance(quote, str)
        or not quote.strip()
        or quote not in player_input
        or not isinstance(requested_item, str)
        or not requested_item.strip()
    ):
        return False

    # Bind the requested identity to text outside quoted/reporting speech. If the
    # NPC owns that identity, use its canonical visible name as the text evidence.
    # Unknown names are allowed through to the resolver so it can return not_owned.
    references = [requested_item]
    for item in canonical_npc.get("inventory", []):
        if not isinstance(item, dict):
            continue
        identities = {
            value for value in (
                item.get("item_id"), item.get("name"), item.get("weapon_id")
            )
            if isinstance(value, str) and value.strip()
        }
        if game._normalize_turkish_typos(requested_item) in {
            game._normalize_turkish_typos(value) for value in identities
        }:
            references.extend(
                value for value in (item.get("name"), item.get("weapon_id"))
                if isinstance(value, str) and value.strip()
            )

    player_words = living_world._text_outside_quotes(str(player_input))
    return any(
        game._entity_reference_in_text(reference, player_words)
        for reference in dict.fromkeys(references)
        if isinstance(reference, str) and reference.strip()
    )

def _explicit_addressee(player_input, candidates):
    """Return the one candidate the sentence is spoken to, or None."""
    folded = game._fold_keep_punctuation(player_input)
    words = re.findall(r"[a-z0-9]+", folded)

    def labels(npc):
        values = [npc.get("name")]
        if living_world.npc_role_known_to_player(npc):
            values.append(living_world.public_npc_role(npc))
        return [
            re.findall(r"[a-z0-9]+", game._fold_keep_punctuation(v))
            for v in values if isinstance(v, str) and v.strip()
        ]

    def dative_speech(npc):
        for label in labels(npc):
            if len(label) != 1:
                continue
            stem = label[0]
            for index, word in enumerate(words):
                if word in {stem + "ya", stem + "ye", stem + "a", stem + "e"} and any(
                    re.match(game._ADDRESS_VERB, later) for later in words[index + 1:index + 4]
                ):
                    return True
        return False

    def leading_vocative(npc):
        for label in labels(npc):
            name = " ".join(label)
            if name and (
                re.match(rf"^\s*{re.escape(name)}\s*[,!:]", folded)
                # "..., merak etme Sera." / "..., Marek!" - name closing a clause
                or re.search(rf"[,;]\s*(?:\w+\s+){{0,3}}{re.escape(name)}\s*[.!?]", folded)
                # "Kavga istemiyorum Sera, sadece ..." - name closing a clause
                or re.search(rf"\b{re.escape(name)}\s*,", folded)
            ):
                return True
        return False

    for test in (dative_speech, leading_vocative):
        picked = [npc for npc in candidates if test(npc)]
        if len(picked) == 1:
            return picked[0]
    return None

def _is_spoken_to(player_input, npc):
    """A sentence said to this person (vocative, dative + speech, or a speech
    verb) is conversation even without a question mark."""
    if not isinstance(npc, dict) or not game._npc_speech_enabled():
        return False
    if game._has_explicit_attack_verb(player_input) or game._is_object_inspection(player_input):
        return False
    if game._explicit_addressee(player_input, [npc]) is not None:
        return True
    return bool(game._SPEAKING_VERB.search(game._normalize_turkish_typos(player_input)))

def _is_short_conversation_continuation(player_input):
    """'e sonra', 'ne zamandan beri', 'gerçekten mi?' - a short nudge to keep talking."""
    words = re.findall(r"[a-z0-9]+", game._normalize_turkish_typos(player_input))
    return 0 < len(words) <= 4 and all(word in game._CONTINUATION_TERMS for word in words)

def _is_object_inspection(player_input):
    return bool(game._OBJECT_INSPECTION.search(game._normalize_turkish_typos(player_input)))

def _is_door_inspection_request(player_input):
    if not isinstance(player_input, str):
        return False
    text = game._normalize_turkish_typos(
        living_world._text_outside_quotes(player_input)
    )
    is_inspection = (
        game._is_object_inspection(text)
        or re.search(r"\b(?:incele|incel)\w*\b", text)
    )
    return bool(re.search(r"\bkapi\w*\b", text) and is_inspection)

def record_npc_interaction(npc, npc_reply, player_input, npc_target=None):
    """Remember a realized NPC reply AND the player's actual utterance.
    
    Stores structured memory entries with speaker attribution:
    - player_said: what the player actually said
    - npc_said: what the NPC actually replied
    
    This prevents false-memory claims while preserving actual conversation history.
    """
    # Record if NPC is explicitly targeted OR if input looks like dialogue
    is_dialogue = game.is_npc_dialogue_input(player_input)
    has_active_npc = npc_target is not None
    
    if not npc or not npc_reply or (not is_dialogue and not has_active_npc):
        return
    if game._unverified_past_event_assertion(player_input):
        return
    
    entries = npc.setdefault("memory", [])
    
    player_text = game._clean_world_text(player_input, 260)
    npc_text = game._clean_world_text(npc_reply, 260)
    
    if not player_text or not npc_text:
        return
    if game._unsupported_npc_history_or_relationship_claim(npc_text, npc, player_input):
        return
    
    player_entry = {"speaker": "player", "text": player_text}
    npc_entry = {"speaker": "npc", "text": npc_text}
    
    # Avoid consecutive duplicates (by text content)
    def _last_text(entries):
        for e in reversed(entries):
            if isinstance(e, dict) and e.get("text"):
                return e["text"]
            elif isinstance(e, str):
                return e
        return None
    
    last = _last_text(entries)
    if last != player_text:
        entries.append(player_entry)
    if last != npc_text:
        entries.append(npc_entry)
    
    # Keep memory bounded (up to 16 structured entries)
    del entries[:-16]
    # LR00 fix: what this NPC really said (places named, commitments made) is
    # kept apart from world facts so it is neither forgotten nor promoted.
    import npc_statements
    npc_statements.record(game._session().world_state, npc, player_input, npc_reply, turn=None)

def _remember_owner_locked_tavern_focus(player_input, npc_target, action_id):
    if (
        not living_world.is_tavern_search(player_input)
        or not isinstance(npc_target, dict)
        or not isinstance(npc_target.get("id"), str)
        or not isinstance(action_id, str)
        or not action_id
    ):
        return
    world = game._session().world_state
    root_location = world.get("location")
    while game._engine_location_parent(root_location):
        root_location = game._engine_location_parent(root_location)
    tavern = next(
        (
            location for location in world.get("locations", {}).values()
            if isinstance(location, dict)
            and location.get("parent_location_id") == root_location
            and (
                location.get("scene_kind") == "tavern"
                or location.get("type") in {"tavern", "inn", "meyhane", "han"}
            )
        ),
        None,
    )
    if not isinstance(tavern, dict):
        return
    door = next(
        (
            item for item in world.get("doors", [])
            if isinstance(item, dict)
            and item.get("id") == f"venue-door:{tavern.get('id')}"
            and item.get("locked") is True
        ),
        None,
    )
    if not isinstance(door, dict):
        return
    interaction_adventure.remember_conversation_focus(
        world,
        speaker_id=npc_target["id"],
        scene_id=world.get("location"),
        subject_id=door["id"],
        predicate="locked",
        value=True,
        turn=world.get("flags", {}).get("turn_index", 0),
        action_id=action_id,
        evidence_id=door["id"],
        epistemic="owner_verified",
    )

def _remember_accepted_profile_focus(player_input, npc_target, action_id, field=None):
    if (
        not isinstance(npc_target, dict)
        or npc_target.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
        or not isinstance(npc_target.get("id"), str)
        or not isinstance(action_id, str)
        or not action_id
    ):
        return
    profile = npc_target.get("personal_profile")
    if (
        field not in {
            "occupation", "current_activity", "recent_activity", "origin",
            "day", "personal_context", "reason_for_being_here",
        }
        or not isinstance(profile, dict)
        or not isinstance(profile.get(field), str)
    ):
        return
    world = game._session().world_state
    interaction_adventure.remember_conversation_focus(
        world,
        speaker_id=npc_target["id"],
        scene_id=world.get("location"),
        subject_id=f"npc-profile:{npc_target['id']}:{field}",
        predicate=field,
        value=profile[field],
        turn=world.get("flags", {}).get("turn_index", 0),
        action_id=action_id,
        evidence_id=f"npc-profile:{npc_target['id']}:v1:{field}",
        epistemic="witnessed",
    )

def npc_memory_supports_claim(npc, player_input):
    import npc_statements
    ledger = npc_statements.claim_support(game._session().world_state, npc, player_input)
    if ledger["status"] != "absent":
        return ledger["status"] == "supported"
    entry = game.npc_memory_supporting_entry(npc, player_input)
    return bool(entry) and npc_statements.entry_supports_claim(entry, player_input)

def npc_memory_supporting_entry(npc, player_input):
    """Check if NPC memory supports a player's claim about past conversation.
    
    Speaker-aware:
    - Claims about what NPC said ("sen bana X demiştin") → only search npc_said entries
    - Claims about what player said ("ben sana X söylemiştim") → only search player_said entries
    - General claims → search both
    """
    claim_terms = game._claim_keywords(player_input)
    if not npc or not claim_terms:
        return None
    
    # Determine which speaker the claim refers to
    claim_text = player_input.casefold()
    claim_about_npc = any(phrase in claim_text for phrase in (
        "sen ", "senin ", "söylemiştin", "demistin", "anlatmıştın", "bahsetmiştin",
        "söylemistin", "demistin", "anlatmistin", "bahsetmistin",
        "söyledin", "dedin", "anlattın", "bahsettin",
        "söylemişti", "demişti", "anlatmıştı", "bahsetmişti",
        "söyledi", "dedi", "anlattı", "bahsetti",
        "hatırlıyor musun", "hatirliyor musun"
    ))
    claim_about_player = any(phrase in claim_text for phrase in (
        "ben ", "benim ", "söylemiştim", "demistim", "anlattım", "bahsetmistim",
        "söylemistim", "demistim", "anlattim", "bahsettim",
        "söyledim", "dedim", "anlattim", "bahsettim"
    ))
    
    # Determine which entries to search
    search_speakers = set()
    if claim_about_npc:
        search_speakers.add("npc")
    if claim_about_player:
        search_speakers.add("player")
    if not search_speakers:
        search_speakers = {"npc", "player"}  # General claim - search both
    
    for entry in npc.get("memory", []):
        if not isinstance(entry, dict):
            continue
        speaker = entry.get("speaker", "")
        memory_text = entry.get("text", "")
        
        # Past-event truth requires independently accepted event provenance;
        # neither a player utterance, NPC repetition nor legacy text provides it.
        if game._unverified_past_event_assertion(player_input) or game._claimed_completed_outcome(player_input):
            # No trusted campaign-event lookup is wired here. Metadata on an
            # NPC memory entry cannot independently prove a past event.
            continue
        elif speaker not in search_speakers or speaker == "unknown":
            continue
            
        memory_folded = memory_text.casefold()
        if any(term in memory_folded for term in (
            "böyle bir şey söylediğimi hatırlamıyorum", "boyle bir sey soyledigimi hatirlamiyorum",
            "belleğimde buna dair bir kayıt yok", "bellegimde buna dair bir kayit yok",
            "bunu söylemedim", "bunu soylemedim", "buna dair bir kayıt yok", "buna dair bir kayit yok",
        )):
            continue
        memory_terms = game._claim_keywords(memory_text)
        if "__duration__" in claim_terms and "__duration__" in memory_terms:
            return memory_text
        overlap = sum(
            1 for claim in claim_terms
            if any(claim.startswith(saved) or saved.startswith(claim) for saved in memory_terms)
        )
        if overlap >= min(2, len(claim_terms)):
            return memory_text
    return None

# Sentences written for the narrator or the engine, never for a person's mouth. Each one is marked where it is
# written, so the door at the turn's end knows it by where it came from, not by a list of its words.
_STOCK_SAID = collections.deque(maxlen=256)  # only for a call with no session; a session keeps its own

def _stock_said():
    try:
        session = game._session()
    except Exception:  # best effort: without a session the module's own list still marks stock lines
        logging.getLogger("game_parts.dialogue").warning("No session for the stock-line list; the module list is used", exc_info=True)
        session = None
    if session is None:
        return _STOCK_SAID
    said = getattr(session, "_stock_lines", None)
    if said is None:
        said = session._stock_lines = collections.deque(maxlen=256)
    return said

def _stock(text):
    if isinstance(text, str) and text.strip():
        game._stock_said().append(text.strip())
    return text

def _is_stock(text):
    """A line Python wrote for the scene is in this text: the same words, from the producer that marked them."""
    return isinstance(text, str) and any(line in text for line in game._stock_said())

def _only_stock(text):
    """The whole reply is Python's scene lines, beside at most the player's own words shown back: nothing else was said."""
    if not game._is_stock(text):
        return False
    rest = text
    for line in sorted(game._stock_said(), key=len, reverse=True):
        rest = rest.replace(line, " ")
    return re.search(r"\w", re.sub(r"Sen: “[^”]*”", " ", rest)) is None

def _without_lines_already_said(spoken, npc, world_state, player_input):
    """A sentence already said goes when the reply has something new to say instead.

    The same question may get the same answer, and a reply that is only a
    repeat stays: a repeated real answer beats any substitute (c48df86).
    """
    log = (world_state.get("npc_speech_log") or {}).get(npc.get("id"), [])
    asked = str(player_input).strip().casefold()
    if any(isinstance(entry, dict) and str(entry.get("player", "")).strip().casefold() == asked for entry in log):
        return spoken
    return game._drop_repeated_sentences(spoken, game._lines_already_said(npc, world_state))

def historical_claim_denial(npc, player_input=""):
    """The last resort for a claim with nothing behind it. Never the same words twice to one player."""
    name = living_world.public_npc_name(npc) if npc else "Bu kişi"
    seed = f"{npc.get('id', '') if isinstance(npc, dict) else ''}|{player_input}"
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(
        game._CLAIM_DENIAL_LINES
    )
    said = game._lines_already_said(npc, game._session().world_state) if game._has_session() and isinstance(npc, dict) else []
    for step in range(len(game._CLAIM_DENIAL_LINES)):
        line = game._CLAIM_DENIAL_LINES[(index + step) % len(game._CLAIM_DENIAL_LINES)].format(n=name)
        if not any(line.split("“", 1)[-1].rstrip("”") in earlier for earlier in said):
            return line
    return interaction_adventure.immersive_unknown(npc, player_input)

def named_by_sight(npc, text):
    """"Çelimsize", "işçiye", "cüppeli birine": what a stranger is called by what shows.

    The trait as a whole or its last word, and the shown role's head word with a
    compound's -si dropped ("Liman işçisi" is "işçi"). A hidden role never counts.
    """
    words = re.findall(r"[a-z0-9]+", game._normalize_turkish_typos(text))
    trait = game._normalize_turkish_typos(living_world.npc_visible_trait(npc))
    role = game._normalize_turkish_typos(living_world.public_npc_role(npc) or "")
    heads = [trait.split()[-1]] if trait else []
    if role:
        head = role.split()[-1]
        heads.append(head[:-2] if len(head) > 5 and head.endswith(("si", "su")) else head)
    return game._entity_reference_in_text(trait, text) or any(
        game._reference_token_matches(head, word) for head in heads for word in words
    )

def _npc_speech_enabled():
    """Compatibility switch for the existing target/focus routing extensions.

    Resolved ordinary NPC speech uses the structured schema independently.
    This switch still controls the broader experimental targeting behavior.
    """
    if getattr(game._session(), "_experimental_npc_dialogue_enabled", False) is True:
        return True
    return game.os.environ.get("AI_DND_NPC_SPEECH", "").strip() == "1"

def _experimental_recent_exchanges(npc_id):
    """Last exchanges (player line -> shown NPC line) with this NPC.

    Stored inside the campaign world_state, so they survive save/resume and
    roll back with a failed turn. Conversation history only: never evidence,
    never memory, never a world fact.
    """
    log = game._session().world_state.get(game._NPC_SPEECH_LOG_KEY)
    entries = log.get(npc_id) if isinstance(log, dict) else None
    result = []
    for item in entries if isinstance(entries, list) else []:
        if (
            isinstance(item, dict)
            and isinstance(item.get("player"), str)
            and isinstance(item.get("npc"), str)
        ):
            result.append({"player": item["player"], "npc": item["npc"]})
    return result[-game._NPC_SPEECH_KEEP:]

def _speech_answer_rules() -> str:
    """The answer rules; with the rumour lane on the model may name places and trails (not new persons, jobs or facts)."""
    if not game._rumour_lane_on():
        return game._SPEECH_ANSWER_RULES
    return (game._SPEECH_ANSWER_RULES
            .replace("yeni ad uydurmadan)", "yeni kişi ya da iş adı uydurmadan)")
            .replace("yeni kişi, yer veya olgu uydurmadan", "yeni kişi ya da olgu uydurmadan"))

def _remember_experimental_npc_speech(npc_id, player_text, npc_text, remember: bool = False, voiced=None):
    """Remember one exchange the player actually saw. Not state, not evidence."""
    if (
        not isinstance(npc_id, str)
        or not isinstance(npc_text, str)
        or not npc_text.strip()
    ):
        return
    world = game._session().world_state
    local_dialogue.remember_speech_exchange(world, npc_id, player_text, npc_text)
    import town_knowledge
    # LR00 fix: the short log above is conversation context only; the
    # statement ledger keeps places and commitments for the whole campaign.
    import npc_statements
    npc = next((n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id), None)
    if npc is not None:
        listener = game._active_interlocutor()
        if (remember is True and isinstance(player_text, str) and "?" not in player_text
                and listener is not None and listener.get("id") == npc_id
                and npc.get("current_hp", 1) > 0
                and npc.get("combat_status") != "dead" and npc.get("status") != "dead"
                and not world.get("combat", {}).get("active")
                and not game.is_npc_historical_claim(player_text)
                and not game._has_private_profile_value(npc, player_text)):
            import npc_told
            npc_told.remember(world, npc_id, player_text,
                              turn=world.get("flags", {}).get("turn_index", 0))
        npc_statements.record(world, npc, player_text, npc_text, turn=None)
        town_knowledge.note_mention(world, npc, npc_text, voiced=voiced, job_talk=game._job_talk_with(npc),
                                    offer_talk=game._offer_talk_with(npc))

def _clean_npc_speech(raw):
    """Return the NPC's own words from a model string, or "" when none survive.

    Small models sometimes write past the end of the JSON string: a stray
    closing brace, emoji, "</think>" or sentences copied from the prompt. Cut
    everything from the first structural character on, drop pictographs, and
    refuse text that talks about the prompt itself (English meta commentary).
    """
    if not isinstance(raw, str):
        return ""
    cut = game._SPEECH_CUT_RE.search(raw)
    text = raw[:cut.start()] if cut else raw
    text = game._strip_pictographs(text)
    text = game._without_real_world_faith(re.sub(r"\s+", " ", text).strip())
    if not text or game._SPEECH_META_RE.search(text):
        return ""
    # A cut or the token limit can leave a half sentence: keep the whole
    # sentences before it; with none, end the fragment openly instead.
    if text[-1] not in ".!?…\"”’'":
        last_end = max(text.rfind(mark) for mark in ".!?…")
        if last_end >= 0:
            text = text[: last_end + 1]
            if text.count("“") > text.count("”"):
                text += "”"
        else:
            text += "…"
            if text.count("“") > text.count("”"):
                text += "”"
    return text if len(re.sub(r"[^\w]", "", text)) >= 3 else ""

def _render_experimental_npc_speech(payload, npc):
    """Render server-attributed speech; keep stage direction outside its quote."""
    name = living_world.public_npc_name(npc)
    stage = payload.get("stage_direction", "").strip().rstrip(".!?…")
    # Identity and safety checks already saw the original stage. Avoid printing
    # the same server-selected subject twice; do not remove another actor.
    stage = re.sub(r"^" + re.escape(name) + r"(?:\s*[:,]\s*|\s+)", "", stage, count=1, flags=re.IGNORECASE)
    stage = game._without_label_variant(stage, name)
    spoken = payload.get("spoken_text", "").strip()
    if stage:
        return f"{name} {stage}. “{spoken}”"
    return f"{name}: “{spoken}”"

def _npc_speech_is_claim_refusal(text, npc=None):
    """True for an NPC line that does not grant an unrecorded claim.

    The model's own answer stands as long as it does not go along with the claim; the
    in-character stock lines used when a reply had to be replaced are refusals too.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    name = living_world.public_npc_name(npc) if isinstance(npc, dict) else ""
    return not game._npc_speech_grants_claim(text) or any(
        text.strip() == line.format(n=name)
        for line in game._CLAIM_DENIAL_LINES
    )

def _npc_name_stance(world, npc, player_input):
    """Python's answer to a question about this NPC's own name: reveal, withhold or None."""
    if (
        not isinstance(npc, dict)
        or game._detect_query_type(player_input, npc) != "npc_identity"
        or local_dialogue.identity_disclosure_is_negated(player_input)
    ):
        return None
    if (
        not living_world.npc_name_known_to_player(npc)
        and local_dialogue.name_withheld_reason(world, npc)
    ):
        return "withhold"
    return "reveal"

def _town_note(world, npc):
    """This person's share of the town; a failure here costs the line, never the turn."""
    import town_knowledge
    import world_threads
    try:
        world_threads.ensure(world)
        turn = getattr(game._session(), "_thread_turn", None) if game._has_session() else None
        return town_knowledge.speech_note(world, npc, turn)
    except Exception:
        town_knowledge.log_failure()
        return ""

def _has_spoken_to_player(npc):
    """Words of this person are on the record."""
    if not isinstance(npc, dict):
        return False
    return bool(npc_statements.view(game._session().world_state)["statements"].get(npc.get("id")))

def _job_talk_with(npc):
    """This turn was about this person's work, whatever the model made of it."""
    turn = getattr(game._session(), "_thread_turn", None)
    return bool(turn and isinstance(npc, dict) and turn.get("npc_id") == npc.get("id"))

def _offer_terms_shown(world, npc, player_input, shown):
    """An owner asked for the work always shows the real terms; a reply that left them out gets them added."""
    import talk_front
    import town_knowledge
    try:
        reading = talk_front.job_reading(game._session())  # the reading says whether the line speaks of work (BM Task 4)
        asked = None if reading is None else talk_front.work_reading(reading, npc, world) is not None
        return town_knowledge.terms_to_add(world, npc, player_input, shown, asked_about_work=asked)
    except Exception:
        town_knowledge.log_failure()
        return None

def _nobody_here(word):
    """The line named someone who is not here: tell the narrator who is, and end the old talk. Once per turn."""
    session = game._session()
    word = str(word).strip()
    here = game.active_npcs()[:3]
    note = (None, f"burada '{word}' diye biri görünmüyor; görünenler: "
                  f"{living_world.public_scene_people(here) if here else 'kimse'}")
    if getattr(session, "_turn_notes", None) is None:
        session._turn_notes = []
    if note in session._turn_notes:
        return
    session._turn_notes.append(note)
    talk_mode.close(session.world_state, "addressed_absent")

def _thread_person(player_input, target_id):
    """Who this line is for, if anyone is here to answer for a job."""
    people = game.active_npcs()
    if target_id is not None:
        return next((npc for npc in people if npc.get("id") == target_id), None)
    named = game._explicit_addressee(player_input, people)
    if isinstance(named, dict):
        return named
    word = game._word_for_nobody_here(getattr(game._session(), "_named_word", None), people)
    if talk_mode.addressee(game._session().world_state, people, named_word=word).status == "nobody_here":
        game._nobody_here(word)
        return None
    active = game._active_interlocutor()
    if isinstance(active, dict) and any(npc.get("id") == active.get("id") for npc in people):
        return active
    last = game._session().world_state.get("flags", {}).get("last_npc_id")
    spoken = next((npc for npc in people if last and npc.get("id") == last), None)
    return spoken or (people[0] if len(people) == 1 else None)

def _physical_line(player_input):
    import grounded_action
    session = game._session()
    plan = grounded_action.plan(session, player_input)
    acts = [step for step in plan["steps"] if not any(step.get(k) for k in ("question", "reported", "not_now", "negated"))
            and step["verb"] not in {"talk", "other"}]
    import timed_gameplay
    return (bool(acts) or session._has_explicit_attack_verb(player_input)
            or timed_gameplay.explicit_wait_request(player_input)
            or bool(timed_gameplay._SLEEPING.search(game._normalize_turkish_typos(player_input))))

def _job_gate(world, person, player_input):
    """What this line does to this person's work. With the model's reading (BM Task 4) the reading chooses the job and
    Python validates the decision; without a reading (flag off, the reading failed, a kind that is no talk) the word
    reader `turn_gate` answers as before."""
    import talk_front
    import world_threads
    if not isinstance(person, dict):
        return None
    reading = talk_front.job_reading(game._session())
    if reading is None:
        return world_threads.turn_gate(world, person, player_input)
    found = talk_front.work_reading(reading, person, world)
    return world_threads.reading_gate(world, person, found["thread_id"], player_input, reading) if found else None

def _town_in_play(world):
    import world_threads
    return world_threads.ensure(world) is not None

def _named_elsewhere_line(world, player_input):
    """'Özpil nerede?' with nobody to ask: where the town says a person it named is (None when it names no one)."""
    import town_knowledge
    name = town_knowledge.person_named_in(world, player_input)
    if not name or living_world.normalize_text(name) in {
            living_world.normalize_text(npc.get("name")) for npc in game.active_npcs()}:
        return None  # standing here, introduced or not
    place = town_knowledge.place_of_person(world, name)
    locations = world.get("locations", {})
    current, seen = world.get("location"), set()
    while isinstance(current, str) and current not in seen:  # here, or a room inside their place
        if place is not None and current == place.get("id"):
            return None
        seen.add(current)
        current = (locations.get(current) or {}).get("parent_location_id")
    return game._elsewhere_line(world, name)

def _town_fallback(world, npc, player_input):
    """Only when no model reply could be used: work, the news, or any question not about the person or the player.

    D-237/D-247 (K7, Kadir): such a question gets a real lead or a place to ask, never a bare "I don't know".
    """
    import town_knowledge
    kind = local_dialogue.personal_question_kind(player_input)
    open_question = (kind is None and interaction_adventure._asks(player_input)
                     and not game._ASKS_WHO_YOU_ARE.search(game._normalize_turkish_typos(player_input)))
    if kind != "local_work" and not game._asks_what_is_going_on(player_input) and not open_question:
        return None
    try:
        import heard_rumours
        # D-249 F2: asked about what she herself said, she says it again before any other lead.
        return heard_rumours.own_line(world, npc, player_input) or town_knowledge.fallback_line(world, npc)
    except Exception:
        town_knowledge.log_failure()
        return None

def _person_fallback(world, npc, player_input):
    """What a person says from Python alone when no model reply can be used."""
    return (game._job_fallback(world) or game._town_fallback(world, npc, player_input)
            or interaction_adventure.immersive_unknown(npc, player_input))

def _experimental_npc_dialogue_context(
    world, npc, *, unverified_claim=False, followup=False, personal_context=True
):
    """Small, target-bound context for the internal attributed-speech trial."""
    if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
        return {}
    source = interaction_adventure.context(world, npc)
    # "Burada nerede iş bulabilirim?" is not about this person: a profile in the
    # prompt was answered instead of the question.
    speech_profile_facts = (
        list(source.get("conversation_candidates", [])) if personal_context else []
    )
    # Small talk about the person, not a stock fact to reach for on any question.
    public_detail = (
        local_dialogue.public_personal_detail(world, npc)
        if personal_context else None
    )
    if public_detail is not None:
        speech_profile_facts.append(public_detail)
    addressee = source.get("addressee") or {}
    allowed_kinds = {"witnessed", "player_claim", "belief", "rumor", "lie"}
    perspective = [
        {
            "kind": entry["kind"],
            "text": entry["text"],
            "source_id": entry["source_id"],
        }
        for entry in addressee.get("entries", [])
        if isinstance(entry, dict)
        and entry.get("kind") in allowed_kinds
        and isinstance(entry.get("text"), str)
        and isinstance(entry.get("source_id"), str)
        and not entry.get("secret")
    ][-6:]

    exchanges = game._experimental_recent_exchanges(npc["id"])
    recent_player_utterances = []
    for entry in npc.get("memory", []) if isinstance(npc.get("memory"), list) else []:
        if (
            not isinstance(entry, dict)
            or entry.get("speaker") != "player"
            or not isinstance(entry.get("text"), str)
            or not entry["text"].strip()
        ):
            continue
        text = entry["text"].strip()[:240]
        if game._has_private_profile_value(npc, text):
            continue
        recent_player_utterances.append(text)
    return {
        "npc_id": npc["id"],
        "addressee": {
            "name": living_world.public_npc_name(npc),
            "role": living_world.public_npc_role(npc),
        },
        "shareable_profile_facts": speech_profile_facts,
        "conversation_focus": interaction_adventure.public_door_conversation_focus(world, npc),
        "scene": living_world.visible_scene_facts(world),
        # A bare follow-up ("Neden onu?") is about the last exchange. Rumors and
        # old player lines pulled a small model away from it (18 Oct live T5),
        # so they are withheld for that turn only.
        "perspective": [] if followup else perspective,
        # Prior NPC prose is never evidence. Only exchanges the player actually
        # saw are carried (player line -> NPC line), newest last, so short
        # follow-ups ("Neden?", "onu") resolve against last_exchange.
        "conversation_status": "attributed_speech_not_fact",
        "conversation_so_far": [
            {"player": item["player"], "npc_reply": item["npc"]}
            for item in exchanges
        ],
        "last_exchange": (
            {"player": exchanges[-1]["player"], "npc_reply": exchanges[-1]["npc"]}
            if exchanges else None
        ),
        "recent_player_utterances": [] if followup else recent_player_utterances[-4:],
        **(
            {"player_claims_unrecorded_past_event": True}
            if unverified_claim else {}
        ),
        # BM Task 6: the hour, the arrival scene shown here, own words and work, last replies. A bare follow-up
        # keeps the rumours out, like `perspective`.
        **{key: value for key, value in talk_front.speech_extras(world, npc).items()
           if not (followup and key == "kendi_sozlerin")},
    }

def _is_player_name_inquiry_to_npc(player_input):
    if not isinstance(player_input, str):
        return False
    text = game._normalize_turkish_typos(player_input)
    if bool(re.search(r"\b(?:adim|adimi|ismim|ismimi)\b", text)) and (
        game.is_npc_historical_claim(player_input)
        or bool(re.search(r"\b(?:neydi|biliyor\s+musun|hatirla\w*|soyle\w*|hitap\s+et\w*)\b", text))
    ):
        return True
    if bool(re.search(r"\b(?:adimla|ismimle)\s+hitap\s+et\w*\b", text)):
        return True
    return False

def _is_historical_player_name_query(player_input):
    normalized_input = game._normalize_turkish_typos(str(player_input).casefold())
    return (
        (game.is_npc_historical_claim(player_input) and bool(re.search(r"\b(?:adimi|ismimi)\b", normalized_input)))
        or game._is_player_name_inquiry_to_npc(player_input)
    )

def _hero_first_name():
    return str((game._session().character or {}).get("name") or "").strip().split(" ")[0]

def _explicit_player_name_disclosure(text):
    hero = game._hero_first_name()
    folded = game._normalize_turkish_typos(text) if isinstance(text, str) else ""
    own = game._normalize_turkish_typos(hero)
    if own and re.search(rf"\bben\s+{re.escape(own)}\b|\badimi\b.*\b{re.escape(own)}\b", folded):
        return hero  # "selam, ben carius. iş var mı": said in passing is still said
    name = (
        local_dialogue.explicit_player_name_disclosure(text)
        or local_dialogue.implied_self_introduction(text, hero)
    )
    return local_dialogue.player_name_spelling(name, hero) if name else None

def _known_player_name(npc):
    """The latest name the player gave this person, if any."""
    for entry in reversed((npc or {}).get("memory", [])):
        if isinstance(entry, dict) and entry.get("speaker") == "player":
            name = game._explicit_player_name_disclosure(entry.get("text"))
            if name:
                return name
    return None

def _historical_player_name_from_npc_memory(npc, player_input):
    """Read the latest explicit player-name disclosure in canonical NPC memory."""
    if not isinstance(npc, dict) or not npc.get("id"):
        return None
    if not game._is_historical_player_name_query(player_input):
        return None

    for entry in reversed(npc.get("memory", [])):
        if not isinstance(entry, dict) or entry.get("speaker") != "player":
            continue
        name = game._explicit_player_name_disclosure(entry.get("text"))
        if name:
            return name
    return None

def _historical_player_name_from_claims(
    npc, player_input, supported_player_claims
):
    """Read an explicitly stated player name bound to the same NPC ID."""
    if not isinstance(npc, dict) or not npc.get("id"):
        return None
    if not game._is_historical_player_name_query(player_input):
        return None
    if not isinstance(supported_player_claims, (list, tuple)):
        return None

    for claim in supported_player_claims:
        if not isinstance(claim, dict) or claim.get("npc_id") != npc.get("id"):
            continue
        text = claim.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        name = game._explicit_player_name_disclosure(text)
        if name:
            return name
    return None

def _direct_npc_smalltalk_response(player_input, npc_target):
    if (
        not isinstance(player_input, str)
        or not isinstance(npc_target, dict)
        or not isinstance(npc_target.get("id"), str)
        or not game.is_npc_dialogue_input(player_input)
        or game.is_npc_historical_claim(player_input)
    ):
        return None


    text = living_world.normalize_text(player_input)
    name = living_world.public_npc_name(npc_target)

    if living_world.is_tavern_search(player_input):
        world_state = game._session().world_state
        root_location = world_state.get("location")
        while game._engine_location_parent(root_location):
            root_location = game._engine_location_parent(root_location)
        tavern = next(
            (
                location
                for location in world_state.get("locations", {}).values()
                if isinstance(location, dict)
                and location.get("parent_location_id") == root_location
                and (
                    location.get("scene_kind") == "tavern"
                    or location.get("type") in {"tavern", "inn", "meyhane", "han"}
                )
            ),
            None,
        ) or game._ensure_local_tavern(root_location)
        if tavern:
            door = next(
                (
                    item for item in world_state.get("doors", [])
                    if isinstance(item, dict)
                    and item.get("id") == f"venue-door:{tavern.get('id')}"
                ),
                None,
            )
            if isinstance(door, dict) and door.get("locked") is True:
                return (
                    f'{name}, “{tavern.get("name", "Han")} şu saatte kapalı, kapısı kilitli; '
                    'orada dinlenemezsin,” diye yanıt verir.'
                )
            return (
                f'{name}, “Yakınlarda {tavern.get("name", "bir han")} var,” '
                'diye yanıt verir.'
            )
        return (
            f'{name}, “Yakınlarda bildiğim belirli bir han yok,” '
            'diye yanıt verir.'
        )

    if game._is_conversation_start_input(player_input):
        return game._conversation_opening_line(name)

    if game._is_local_place_question(player_input):
        location_name = game.location_display_name()
        role = (living_world.public_npc_role(npc_target) or "biri").casefold()
        return (
            f'{name}, “Burası {location_name}. Ben de burada {role} olarak '
            'bulunuyorum,” diye yanıt verir.'
        )

    if game._asks_what_is_going_on(player_input):
        if game._town_in_play(game._session().world_state):
            return None  # this person answers from what they know, in their own voice
        return (
            f'{name}, “Şimdilik göze çarpan özel bir şey yok; '
            'ben kendi işimle ilgileniyorum,” diye yanıt verir.'
        )

    personal_question = local_dialogue.personal_question_kind(player_input)
    if (
        not game._npc_speech_enabled()
        and game._explicit_addressee(player_input, [npc_target]) is None
        and personal_question in {
            "occupation",
            "current_activity",
            "recent_activity",
            "day",
            "origin",
            "personal_context",
        }
    ):
        personal = local_dialogue.personal_answer(npc_target, player_input)
        if personal:
            return personal[0]

    asks_about_day = bool(
        re.search(r"\b(?:gunun|bugunun|keyfin|halin)\b", text)
        and re.search(r"\b(?:nasil|gidiyor|geciyor)\b", text)
    ) or bool(re.search(r"\b(?:nasilsin|keyfin nasil)\b", text))
    if asks_about_day:
        return (
            f'{name}, “Fena değil, teşekkür ederim. '
            'Sorduğun için sağ ol,” diye karşılık verir.'
        )

    asks_about_conditions = bool(
        re.search(r"\b(?:yol\w*|guvenli\w*|emniyet\w*)\b", text)
        and re.search(r"\b(?:bugun|su an|nasil|durum|guvenli)\b", text)
    )
    if asks_about_conditions:
        return (
            f'{name}, “Yolların ne durumda olduğunu bilemem; kesin bir şey '
            'söylersem seni yanıltırım,” diye yanıt verir.'
        )

    if re.search(
        r"\b(?:selam\w*|merhaba|iyi gunler|gunaydin|iyi aksamlar)\b",
        text,
    ) and game._is_bare_greeting(player_input, npc_target):
        return f'{name}, “Merhaba,” diye karşılık verir.'
    return None

def _conversation_opening_line(name):
    """The first opening is the plain line; later ones with the same person vary."""
    openings = [line.format(name=name) for line in game._CONVERSATION_OPENINGS]
    return openings[game._variation_index(("opening", name), len(openings))]

def _stock_hearer(result, player_input, target_id):
    """Whoever a scene or system line would be answering, or None when the line was said to nobody here."""
    import npc_speech_boundary
    session = game._session()
    text = result.get("narration")
    action_result = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    read = getattr(session, "_front_read", None) or {}
    here = {npc.get("id"): npc for npc in game._conversation_npcs()}
    if action_result.get("npc_id") in here and ("“" in text or '"' in text):
        return here[action_result["npc_id"]]  # it already came out of a mouth
    if target_id in here:
        return here[target_id]
    if read.get("kind") in {"speak_to", "heavy_asked"}:  # D-109: an asked threat is for the one threatened
        return here.get(read["id"])
    if not (read.get("kind") == "talk_around" or npc_speech_boundary.player_supplied_quote(player_input)
            or (not read and game._reads_as_address(player_input))):
        return None
    active = game._active_interlocutor()
    if isinstance(active, dict) and active.get("id") in here:
        return here[active["id"]]
    return next(iter(here.values())) if len(here) == 1 else None

def _said_to_someone_here(session, reading) -> dict | None:
    """The person a line of several clauses is said to, or None when it stays the player's own plan.

    The model proposes, Python checks: the reading's intent is `talk` and it names a living person here
    (`talk_mode.people_here`), or names nobody while talk mode is open with a living person here.
    """
    if not isinstance(reading, dict) or reading.get("intent") != "talk":
        return None
    world = session.world_state
    target = reading.get("target") if isinstance(reading.get("target"), dict) else {}
    named = target.get("npc_id")
    if isinstance(named, str) and named.strip() and named != "none":
        return next((npc for npc in talk_mode.people_here(world)
                     if isinstance(npc, dict) and npc.get("id") == named
                     and npc.get("combat_status") not in {"dead", "unconscious"}), None)
    return talk_mode.current(world)

def _npc_answers_to(npc, text):
    """Does the text name this person the way the player knows them: name, shown role or shown label?"""
    name_match = (
        living_world.npc_name_known_to_player(npc)
        and game._entity_reference_in_text(npc.get("name", ""), text)
    )
    # The player reads the public role ("dükkâncı"), not the internal one
    # ("shopkeeper"): both name the same NPC, only when the role is shown.
    role_match = (
        living_world.npc_role_known_to_player(npc)
        and (
            game._entity_reference_in_text(npc.get("role", ""), text)
            or game._entity_reference_in_text(
                living_world.public_npc_role(npc) or "", text
            )
        )
    )
    # The label the player is shown ("Yakındaki kişi", "Bir köylü") is public
    # by construction, so typing it back must address that person.
    descriptor_match = (
        not living_world.npc_name_known_to_player(npc)
        and (
            game._entity_reference_in_text(living_world.public_npc_descriptor(npc), text)
            or game.named_by_sight(npc, text)
        )
    )
    return bool(name_match or role_match or descriptor_match)

def _offer_talk_with(npc):
    """This reply answers the offer itself: the money was argued, it was turned down, or the line named the work."""
    turn = getattr(game._session(), "_thread_turn", None)
    return game._job_talk_with(npc) and bool(turn.get("offer_talk") or turn.get("decision") in {"questioning_terms", "declined"})

def _job_fallback(world):
    """A person's own short word on the money when the reply could not be used."""
    import town_knowledge
    try:
        return town_knowledge.job_reply(world, getattr(game._session(), "_thread_turn", None))
    except Exception:
        town_knowledge.log_failure()
        return None

def _coin_persuasion(action_result):
    """D-166: the Persuasion roll asking a person for coin takes, at their DC (`influence.dc`).

    A Persuasion this turn already rolled is reused against that DC, never rerolled; any other roll this turn asked
    for something else, so it gives no coin (None). Otherwise one fresh roll, its card returned for the turn to show.
    """
    def persuade(dc, advantage):
        if action_result.get("action") == "skill_check":
            total = action_result.get("total")
            if action_result.get("skill") != "Persuasion" or type(total) is not int:
                return None
            return {"success": total >= dc}
        character = game._session().character
        check = game.perform_skill_check("Persuasion", dc, character["modifiers"], character["proficient_skills"],
                                    character["proficiency_bonus"], advantage=advantage,
                                    expertise_skills=character.get("expertise_skills", ()))
        outcome = game._skill_result_category(check.get("result"))
        card = {
            "action": "skill_check", "skill": check["skill"], "ability": check["ability"], "dice": check["dice"],
            **({"dice_rolls": check["dice_rolls"]} if "dice_rolls" in check else {}),
            "modifier": check["modifier"], "proficiency_bonus": check["proficiency_bonus"],
            "expertise": check["expertise"], "advantage": check["advantage"], "disadvantage": check["disadvantage"],
            "action_id": check["resolution"].get("action_id"), "resolution_id": check["resolution"].get("resolution_id"),
            "resolution": check["resolution"], "total": check["total"], "dc": check["dc"], "outcome": outcome,
            "success": outcome == "success", "status": "resolved",
        }
        return {"success": outcome == "success", "card": card}
    return persuade

def _show_coin_roll(action_result, card):
    """D-166: the coin ask's roll shows on the turn, while the turn stays what it was: a talk stays a talk (its
    action, success and status, which 'talk to X' objectives and a guard's question read). A turn that already
    rolled a check keeps its own card."""
    if card and action_result.get("action") != "skill_check":
        action_result.update({key: value for key, value in card.items() if key not in {"action", "success", "status"}},
                             coin_ask_roll=True)

def _settle_spoken_commitment(world, npc, player_input, raw, spoken, *, threat=None, persuade=None, stage=None):
    """What the reply proposed reaches the record if it checks out. A failure here costs the turn nothing."""
    import town_knowledge
    session = game._session()
    gate = getattr(session, "_thread_turn", None)
    try:
        import world_happenings
        said = threat.split()[0] if isinstance(threat, str) and threat.strip() else None
        if said == world_happenings.PLAYER_THREATENED and not game._heavy_allowed("threat", player_input,
                                                                             person_id=npc.get("id")):
            threat = None  # D-109: only a threat said now and asked yes hurts a tie; the reply's own claim stays words
        settled = town_knowledge.settle_reply(
            world, npc, player_input, raw, spoken,
            accept_job=lambda thread: game._accept_named_job(session, world, npc, thread),
            moved=(gate or {}).get("paid_cp") or 0, threat=threat, purchase=getattr(session, "_purchase_said", False),
            persuade=persuade, stage=stage,
        )
        import pocket
        settled["spoken"], settled["unbacked"] = pocket.settle_claim(session, raw, settled["spoken"], npc)
        return settled
    except Exception:
        town_knowledge.log_failure()
        return {"spoken": spoken, "note": None, "allowed": set(), "moved": 0, "stage": stage}

def _with_only_backed_money(speech, settled):
    """The sentences that claim money Python did not move leave the line. False when nothing is left to say."""
    import town_knowledge
    for field in ("spoken_text", "stage_direction"):
        speech[field] = town_knowledge.without_unbacked_money(
            speech[field], allowed=settled.get("allowed"), moved=bool(settled.get("moved")))
    return bool(speech["spoken_text"].strip())

def _experimental_speech_note(world, npc, name_stance, player_input):
    """Plain Turkish lines read just before the player's message: who speaks, the name, the ask."""
    label = living_world.public_npc_name(npc)
    lines = [
        f"Konuşan sensin; sahnedeki “{label}” sensin, oyuncu karşındaki kişidir.",
        f"Konuşma biçimin: {local_dialogue.voice_trait(world, npc)} Sıradan birisin, herkese yardım etmek zorunda değilsin.",
    ]
    name = str(npc.get("name") or "").strip()
    if name_stance == "withhold":
        reason = local_dialogue.name_withheld_reason(world, npc)
        lines.append(
            f"Adını söylemek istemiyorsun ({reason}); ad vermeden doğal biçimde geçiştir, "
            "sahte ad söyleme."
        )
    elif name_stance == "reveal":
        lines.append(
            f"Adın {name}. Oyuncu adını soruyor: adını kendi sesinle söyle; tek kelimeyle bırakma, yanına konuşma biçimine uyan kısa bir söz ekle."
        )
    elif living_world.npc_name_known_to_player(npc):
        lines.append(f"Adın {name}; sorulmadıkça tekrar etme.")
    else:
        lines.append("Adın sorulmadı: kendini tanıtma, kendine ad uydurma.")
    rest = getattr(game._session(), "_front_rest", "")
    if rest:
        lines.append(f"Oyuncu aynı sözde şunu da söyledi: {rest} Buna da cevap ver.")
    player_name = game._known_player_name(npc)
    if player_name:
        said = len((world.get("npc_speech_log") or {}).get(npc.get("id"), []))
        lines.append(
            f"Karşındakinin adı {player_name}."
            + (" Bu cevapta onu adıyla hitap et." if said % 3 == 0
               else " Bu cevapta adını söylemene gerek yok.")
        )
    import town_knowledge
    asked_for = town_knowledge.person_named_in(world, player_input)  # "Özpil nerede?" asked of someone here (Task 29)
    place = (town_knowledge.place_of_person(world, asked_for)
             if asked_for and npc_statements.fold(asked_for) != npc_statements.fold(name) else None)
    if place is not None:
        lines.append(f"Kasabanın bildiği (motor kaydı): {asked_for}, {place['name']} tarafında bulunur. "
                     "Sorulursa bunu söyleyebilirsin; başka bir yer söyleme.")
    earlier = town_knowledge.said_before_note(world, npc, game._claim_denial_quotes()).strip()
    if earlier:
        lines.append(earlier)
    import npc_told
    about = npc_statements.claim_about(player_input)
    supported = npc_told.supports(world, npc.get("id"), player_input, about=about)
    told = supported if supported else npc_told.relevant(world, npc.get("id"), player_input)
    if told:
        lines.append(npc_told.view(told,
            header="Oyuncunun sana daha önce söyledikleri (söylendi; doğruluğunu bilmezsin):"))
    elif about == "own_words":
        context = npc_told.context_rows(world, npc.get("id"))
        if context:
            lines.append(npc_told.view(context,
                header="Oyuncunun sana son söyledikleri (yalnız bağlam; bu sözle ilgisi belli değil):"))
    said_before = game._lines_already_said(npc, world)[-3:]
    if said_before:
        lines.append(
            "Az önce şunları söyledin: " + " / ".join(line[:120] for line in said_before)
            + " Bunları aynen tekrar etme, yeni bir şey söyle."
        )
    extras = talk_front.speech_extras(world, npc)  # BM Task 6: one line for each field the context carries
    if "zaman" in extras:
        lines.append(f"Şu an saat {extras['zaman']['saat']}, vakit {extras['zaman']['vakit']}: sözünü bu saate uydur "
                     "(akşamsa sabah duasından ya da sabah işinden söz etme).")
    if "sahne_anlatimi" in extras:
        lines.append("Oyuncuya `sahne_anlatimi` alanındaki sahne gösterildi; sen o sahnenin içindesin: "
                     "gösterilenleri inkâr etme, çelişme; en fazla azıcık ekleyebilirsin.")
    if "son_sozlerin" in extras:
        lines.append("Son sözlerin `son_sozlerin` alanında; aynı reddi ya da bahaneyi yeniden söyleme.")
    if local_dialogue.personal_question_kind(player_input) == "local_work":
        lines.append(
            "Oyuncu kendine iş arıyor, senin işini sormuyor: bildiğin bir iş veya yer "
            "varsa onu söyle, yoksa kimin ya da nerenin bilebileceğini söyle."
        )
    handed = getattr(game._session(), "_handed_note", None)
    if handed:
        lines.append(f"Oyuncu az önce sana şunu verdi, artık sende: {handed}.")
        game._session()._handed_note = None
    decision = money_owner.current(game._session())
    told_coin = False
    if decision is not None and decision.amount_cp > 0 and decision.npc_id == npc.get("id"):
        # Read from the money owner's decision: coin waiting for a card is not theirs yet (decisions 3 and 11), coin
        # with no meaning opens no card and is only shown. Only the person it was held out to hears of it; a past
        # payment is no coin held out now, and the guard weighs a bribe on its own card.
        if decision.kind in money_owner.WAITS_FOR_CONFIRMATION:
            lines.append(f"Oyuncu sana {decision.amount_cp} bakır uzatıyor; para henüz sende değil, "
                         "oyuncu kartı onaylarsa geçer.")
            told_coin = True
        elif decision.kind == "unclear":
            lines.append(f"Oyuncu sana {decision.amount_cp} bakır gösterdi, ne için olduğu belli değil; "
                         "para el değiştirmedi.")
            told_coin = True
    pending = getattr(game._session(), "_spoken_coin_proposal", None)
    if not told_coin and pending is not None and pending.recipient_id == npc.get("id"):
        # A validated gift or tip waiting for this person's own spoken answer (D0): prompt evidence only, never tender.
        lines.append(f"Oyuncu sana {pending.amount_cp} bakır uzatıyor; para henüz sende değil, "
                     "oyuncu kartı onaylarsa geçer.")
    import bold_acts
    import pocket
    lines.append(bold_acts.room_note(npc, player_input, world=world))
    lines.append(bold_acts.price_note(npc, player_input, world=world))
    lines.append(game._bag_note(pocket.bag_names(world)))
    if getattr(game._session(), "_empty_handed", False):
        lines.append("Oyuncu bir şey uzatıyor gibi konuşuyor ama elinde öyle bir şey yok; ondan bir şey almış gibi yazma.")
    import bold_acts
    import truth_card
    held_out_cp = (decision.amount_cp if decision is not None and decision.npc_id == npc.get("id")
                   and decision.kind != "paid_before" else 0)
    card = truth_card.npc_view(world, npc=npc, held_out_cp=held_out_cp,
                               this_turn=getattr(game._session(), "_turn_notes", ()))
    return (game._speech_answer_rules() + " ".join(lines) + "\n" + card + "\n" + bold_acts.speech_note(world, npc) + game._town_note(world, npc)
            + town_knowledge.promise_note(world, npc)
            + town_knowledge.money_decided_note(getattr(game._session(), "_thread_turn", None)) + "\n")


def _repair_npc_speech(world, npc, player_input, rejected, reason_code, action_result):
    """D-332: the one repair of an answer the safety check rejected. Two fields come back and nothing else is read."""
    import json
    import town_knowledge
    import model_phase
    problems = {
        "INVENTED_PLAYER_ACTION": "Oyuncunun yaptığı bir şeyi anlattın; yalnız kendi sözünü ve jestini yaz.",
        "UNSUPPORTED_ITEM_TRANSFER": "Oyuncuya eşya ya da ikram verdiğini söyledin; verilmeyen bir şeyi anlatma.",
    }
    try:
        user = {
            "context": game._experimental_npc_dialogue_context(world, npc),
            "player_message": player_input,
            "rejected": {key: rejected.get(key, "") for key in ("spoken_text", "stage_direction")},
            "known": [item.get("text") for item in town_knowledge.public_knowledge(world, npc)],
            "problem": problems.get(
                reason_code, "Cevabın denetimden geçmedi; aynı soruya kısa ve kendi sözünle yeniden cevap ver."),
        }
        schema = {"type": "object",
                  "properties": {"spoken_text": {"type": "string", "maxLength": 600},
                                 "stage_direction": {"type": "string", "maxLength": 600}},
                  "required": ["spoken_text", "stage_direction"], "additionalProperties": False}
        system = ("Aynı NPC olarak oyuncunun son sorusuna yeniden cevap ver; aşağıdaki sorunu düzelt, başka hiçbir şeyi "
                  "değiştirme. Yalnız JSON yaz.\n" + game._speech_answer_rules())
        with model_phase.resolved_narration_scope(True), model_phase.repair_call():  # an optional call: its outage never refuses the turn
            response = game.ollama.chat(
                model="qwen3:8b",
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
                format=schema, think=False, options=game._EXPERIMENTAL_NPC_SPEECH_OPTIONS)
        packet = game._extract_json_object(game.ollama_response_content(response))
        if not isinstance(packet, dict) or not isinstance(packet.get("spoken_text"), str):
            return None
        import npc_speech_boundary
        # The repaired line passes every cleaner a first answer passes (_run_player_turn_internal), then the money cut.
        spoken = game._clean_npc_speech(npc_speech_boundary.normalize_bound_speech_label(
            packet["spoken_text"].strip(), npc,
            visible=any(n.get("id") == npc.get("id") for n in game._conversation_npcs())))
        if spoken.strip():
            spoken = game._ground_local_place_recommendation_reply(spoken, npc, world, player_input)
        stage = game._ground_local_place_recommendation_stage(
            game._clean_npc_stage_direction(packet.get("stage_direction")), npc, world, player_input)
        spoken = npc_speech_boundary.strip_player_echo(spoken, player_input)
        spoken = npc_speech_boundary.drop_ungrounded_prop_sentences(
            spoken, [{"name": feature.get("name"), "description": feature.get("description"),
                      "aliases": feature.get("aliases") or []}
                     for feature in living_world.visible_features(world) if isinstance(feature, dict)])
        spoken = npc_speech_boundary.without_no_name_claim(spoken)
        spoken = npc_speech_boundary.without_false_presence(world, spoken, world.get("location"))
        stage = npc_speech_boundary.strip_player_quote(stage, player_input)
        stage = game._shown_stage_direction(stage, world)
        spoken = game._without_lines_already_said(spoken, npc, world, player_input)
        if (not spoken.strip() or not interaction_adventure.safe_narration(game._compose_experimental_npc_speech(
                {"spoken_text": spoken, "stage_direction": stage}))):
            return None
        backed = town_knowledge.money_backed_by(world, npc)  # the repair's own figures are never trusted
        payload = {
            "source": "experimental_attributed_speech",  # stamped by Python, as the speech call's own payload
            "speaker_id": npc["id"],
            "spoken_text": town_knowledge.without_unbacked_money(spoken.strip(), allowed=backed),
            "stage_direction": town_knowledge.without_unbacked_money(stage, allowed=backed),
        }
        if not payload["spoken_text"].strip() or len(payload["spoken_text"]) > 600:
            return None
        decision = game._narration_safety_decision(
            game._compose_experimental_npc_speech(payload), player_input, npc, action_result, attributed_speech=payload)
        if (decision.get("unsafe") or game._is_explicit_name_led_gesture_line(payload["spoken_text"], npc)
                or not game._dialogue_repair_has_attributed_answer(payload, npc, action_result)):
            return None
        return payload
    except Exception as error:  # never the player's words: only the kind of failure
        import logging
        logging.getLogger("game_parts.dialogue").warning("speech repair failed: %s", type(error).__name__)
        return None


def _question_bound_answer(world, npc, player_input):
    """D-332: what this person says when no model answer could be used: bound to their question, never a rumour
    that does not answer it. Without a reading there is nothing to bind to: today's lead."""
    import town_knowledge
    reading = talk_front.current(game._session())
    asks = reading.get("asks") if isinstance(reading, dict) else None
    if asks is None or asks in ("rumour", "work"):
        return game._person_fallback(world, npc, player_input)
    place = world.get("locations", {}).get(reading.get("place_id"))
    import local_places
    town = town_knowledge._settlement(world)  # no town (the wilderness) answers no place; nor is the town its own street
    known = (isinstance(place, dict) and place.get("name") and not place.get("hidden") and town is not None
             and reading.get("place_id") != town
             and local_places.settlement_of(world, reading.get("place_id")) == town)
    if asks == "place" and known:
        where = "Bu sokakta" if place.get("parent_location_id") == npc.get("location") else "Yakınlarda"
        last = next((ch for ch in reversed(place["name"].casefold()) if ch in "aıoueiöü"), "a")  # mı / mi / mu / mü
        particle = "mı" if last in "aı" else "mi" if last in "ei" else "mu" if last in "ou" else "mü"
        spoken = f"{place['name']} {particle}? {where}."
    elif asks == "small_talk":  # a hal hatır question no answer could be used for: one short neutral word, no rumour
        words = ("Fena sayılmaz; günler geçip gidiyor.", "İdare ediyoruz, sağ ol.", "Her zamanki gibi; işler yürüyor.")
        spoken = words[int(hashlib.sha256(f"{npc.get('id')}|{player_input}".encode("utf-8")).hexdigest(), 16) % len(words)]
    elif asks == "none":
        return interaction_adventure.immersive_unknown(npc, "")
    else:
        ask_there = town_knowledge._brush_off_place(world, npc)
        spoken = (f"Onu bilmiyorum; {ask_there} tarafına sor." if ask_there
                  else interaction_adventure.immersive_unknown(npc, player_input))
    return game._compose_experimental_npc_speech({"spoken_text": spoken, "stage_direction": ""})


def _speech_after_check(text, *, world_state, npc_target, player_input, action_result, experimental_npc_dialogue,
                        experimental_unverified_claim, narration_source, python_town_response, attributed_speech=None):
    narration_safety = getattr(game._session(), "last_narration_safety", None)
    narration_safety = (
        narration_safety if isinstance(narration_safety, dict) else {}
    )
    final_safety_reason_code = narration_safety.get("reason_code")
    final_safety_handling = narration_safety.get("handling", "accepted")
    if (
        final_safety_reason_code
        and final_safety_handling == "python_fallback"
    ):
        narration_source = "deterministic_fallback"
    stock_swapped = experimental_npc_dialogue and game._is_stock(text)
    if stock_swapped:
        # A clear line never earns "say it again": the person answers from what Python has for them.
        text = game._question_bound_answer(world_state, npc_target, player_input)
    elif (experimental_npc_dialogue and final_safety_handling == "python_fallback"
            and not experimental_unverified_claim and action_result.get("action") != "skill_check"
            and interaction_adventure._asks(player_input)):  # a greeting keeps the fallback's own answer
        # D-249 F1: a speech the safety check rejected is replaced by what the person has to say from Python
        # (job, town lead, place to ask), never by the stock "I don't know" the fallback wrote.
        paid = game._session()  # coin already moved this turn: no repair is asked, the line must not talk about it
        coin_moved = bool((getattr(paid, "_thread_turn", None) or {}).get("paid_cp")) or bool(getattr(paid, "_coin_paid", None))
        repaired = (game._repair_npc_speech(world_state, npc_target, player_input, attributed_speech,
                                            final_safety_reason_code, action_result)
                    if isinstance(attributed_speech, dict) and str(attributed_speech.get("spoken_text", "")).strip()
                    and not coin_moved
                    else None)  # an empty line is no answer a safety check rejected
        from api import ollama_adapter
        game._session()._speech_repair_calls = sum(  # a repair call really made counts in the route log
            1 for call in ollama_adapter._MODEL_CALLS.get() or () if getattr(call, "repair", False))
        if repaired is not None:
            text = game._render_experimental_npc_speech(repaired, npc_target)
            narration_source = "qwen"
            game._session()._speech_repair = "model_repair"
        else:
            text = game._question_bound_answer(world_state, npc_target, player_input)
            game._session()._speech_repair = "model_repair_skipped" if coin_moved else "model_repair_failed"
            reading = talk_front.current(game._session())
            asks = reading.get("asks") if isinstance(reading, dict) else None
            if (asks is None or asks in ("rumour", "work")) and text != interaction_adventure.immersive_unknown(
                    npc_target, player_input):
                python_town_response = text  # only a line that really is the town's lead is labelled one
    return {"text": text, "python_town_response": python_town_response, "narration_source": narration_source,
            "reason_code": final_safety_reason_code, "handling": final_safety_handling, "stock_swapped": stock_swapped}
