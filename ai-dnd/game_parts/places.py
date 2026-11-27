import game
import attributed_claims
import equipment_economy
import held_weapon
import living_world
import local_dialogue
import name_catalog
import npc_statements
import re
import scheduled_events
import talk_mode
import copy
import timed_gameplay
import turn_close


def _tavern_door_notice(tavern_id):
    door = game._venue_door_for(tavern_id)
    if not isinstance(door, dict):
        return "Sokağa açılan kapısı kolayca fark ediliyor."
    if door.get("open"):
        return "Sokağa açılan kapısı açık."
    if door.get("locked"):
        return "Sokağa açılan kapısı kapalı ve kilitli."
    return "Sokağa açılan kapısı kapalı."

def _venue_door_id(location_id):
    return f"venue-door:{location_id}"

def _venue_door_for(location_id):
    if not isinstance(location_id, str) or not location_id:
        return None
    door_id = game._venue_door_id(location_id)
    for door in game._session().world_state.get("doors", []):
        if isinstance(door, dict) and door.get("id") == door_id:
            return door
    return None

def _venue_entry_door(world_state, origin, destination):
    """Return a locked registered venue door for any incoming route.

    A closed door that is not locked is no obstacle: the visitor opens it.
    """
    locations = world_state.get("locations", {})
    target = locations.get(destination) if isinstance(locations, dict) else None
    if (
        not isinstance(target, dict)
        or target.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
        or origin == destination
    ):
        return None
    door_id = game._venue_door_id(destination)
    doors = world_state.get("doors", [])
    door = next(
        (item for item in doors if isinstance(item, dict) and item.get("id") == door_id),
        None,
    ) if isinstance(doors, list) else None
    if isinstance(door, dict) and door.get("locked") and not door.get("open"):
        # LR00 fix: being turned back at a closed door leaves the player at it,
        # so "kapısını çalıyorum" next means this door, not the street's first.
        if door.get("location") == world_state.get("location"):
            import grounded_action
            grounded_action.note_near(world_state, door["id"])
        return door
    return None

def _locked_door_refusal(door):
    game._mark_lock_seen(game._session().world_state, door)
    return f"{door.get('name', 'Kapı')} kilitli; içeri giremiyorsun."

def _mark_lock_seen(world_state, door):
    """W03: call only where the player is actually shown that the door is LOCKED (the text says "kilitli").

    The knowledge lives in flags, not on the door: what the player knows is not the door's mechanical state.
    """
    if isinstance(door, dict) and door.get("locked") is True and isinstance(door.get("id"), str):
        flags = world_state.setdefault("flags", {})
        known = flags.get("known_locked_door_ids")
        if not isinstance(known, list):
            known = flags["known_locked_door_ids"] = []
        if door["id"] not in known:
            known.append(door["id"])
    return door

def _lock_known_to_player(world_state, door_id):
    flags = world_state.get("flags") if isinstance(world_state, dict) else None
    known = flags.get("known_locked_door_ids") if isinstance(flags, dict) else None
    return isinstance(known, list) and door_id in known

def _current_door():
    world_state = game._session().world_state
    here = [door for door in world_state["doors"] if door.get("location") == world_state["location"]]
    # LR00 fix: the door the player stands at (grounded_action position) wins
    # over list order; with several doors the first one is no longer a guess.
    import grounded_action
    near = grounded_action.near_door_id(world_state)
    chosen = next((door for door in here if door.get("id") == near), None)
    # Inside a venue the door at hand is the one the player came through.
    return chosen or next(iter(here), None) or grounded_action._entry_door_of(
        world_state, world_state.get("location")
    )

def location_features(location=None):
    world_state = game._session().world_state
    location = location or world_state["location"]
    return [feature for feature in world_state["features"] if feature.get("location") == location]

def feature_descriptions(location=None):
    return [
        f"{feature['name']} — {feature['description']}" if feature.get("description") else feature["name"]
        for feature in game.location_features(location)
    ]

def active_npcs(location=None):
    world_state = game._session().world_state
    location = location or world_state["location"]
    return [npc for npc in scheduled_events.visible_npcs(world_state) if npc.get("location") == location]

def _clean_world_text_list(value, item_limit=180, max_items=8):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:max_items]:
        cleaned = game._clean_world_text(item, item_limit)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result

def _has_unregistered_person_name(value, extra_names=()):
    world_state = game._session().world_state
    if not isinstance(value, str):
        return False
    allowed = {
        game._normalize_turkish_typos(game._session().character["name"]),
        *(
            game._normalize_turkish_typos(name)
            for name in extra_names if isinstance(name, str)
        ),
    }
    allowed.update(
        game._normalize_turkish_typos(npc.get("name", ""))
        for npc in world_state["npcs"]
    )
    for location_id, location in world_state.get("locations", {}).items():
        allowed.add(game._normalize_turkish_typos(location_id))
        allowed.update(game._location_alias_values(location))
    allowed.update(
        game._normalize_turkish_typos(feature.get("name", ""))
        for feature in world_state["features"]
    )
    # Turkish possessive suffixes mark proper names clearly (for example, "Elias'ın").
    for match in re.finditer(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})['’][a-zçğıöşü]+\b", value):
        possessive_word = game._normalize_turkish_typos(match.group(1))
        preceding_name = re.search(
            r"(?:\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}\s+)*$",
            value[:match.start()],
        )
        complete_name = game._normalize_turkish_typos(
            f"{preceding_name.group(0) if preceding_name else ''}{match.group(1)}"
        )
        if possessive_word not in allowed and complete_name not in allowed:
            return True
    return False

def validate_npc_proposal(proposal, allow_other_location=False):
    world_state = game._session().world_state
    if not isinstance(proposal, dict):
        return None
    name = game._clean_world_text(proposal.get("name"), 40)
    role = game._clean_world_text(proposal.get("role"), 48)
    location = game.normalize_location_id(proposal.get("location", world_state["location"]))
    if not name or not role or not location:
        return None
    if not re.fullmatch(r"[\w .’'-]+", name, flags=re.UNICODE) or "_" in name:
        return None
    if name.casefold() == game._session().character["name"].casefold():
        return None
    if location not in world_state.get("locations", {}):
        return None
    if not allow_other_location and location != world_state["location"]:
        return None
    relationship = game._clean_world_text(proposal.get("relationship", "neutral"), 40) or "neutral"
    backstory = game._clean_world_text(proposal.get("backstory", ""), 240) or ""
    if game._has_unregistered_person_name(backstory, (name,)):
        backstory = ""
    knowledge = [
        value for value in game._clean_world_text_list(proposal.get("knowledge", []), 180, 8)
        if not game._has_unregistered_person_name(value, (name,))
    ]
    return {
        "name": name,
        "role": role,
        "location": location,
        "personality": game._clean_world_text(proposal.get("personality", ""), 180) or "",
        "appearance": game._clean_world_text(proposal.get("appearance", ""), 180) or "",
        "relationship": relationship,
        "knowledge": knowledge,
        # NPC memory is recorded by Python from actual player turns, not AI claims.
        "memory": [],
        "backstory": backstory,
    }

def create_local_feature(proposal):
    """Register a harmless, addressable local feature with a stable Python ID."""
    world_state = game._session().world_state
    if not isinstance(proposal, dict):
        return None
    location = game.normalize_location_id(
        proposal.get("location", world_state.get("location"))
    )
    name = game._clean_world_text(proposal.get("name"), 60)
    description = game._clean_world_text(proposal.get("description", ""), 200) or ""
    if location != world_state.get("location") or not name or "\n" in name:
        return None
    if game._reads_english(f"{name} {description}"):
        return None  # the game is told in Turkish; an English name and line is not stored
    parent_id = (
        game._valid_local_feature_parent_id(proposal.get("parent_id"), location)
        if proposal.get("parent_id") is not None
        else None
    )
    if proposal.get("parent_id") is not None and parent_id is None:
        return None
    if game._legacy_hidden_feature_name_collision(
        proposal, location, parent_id, name
    ) or game._local_detail_claims_unsupported_mechanics(proposal, parent_id):
        return None
    existing = next(
        (
            feature for feature in world_state.get("features", [])
            if isinstance(feature, dict)
            and feature.get("location") == location
            and feature.get("parent_id") == parent_id
            and str(feature.get("name", "")).casefold() == name.casefold()
        ),
        None,
    )
    if existing:
        # A proposal may only reuse a feature the player can see; handing back a
        # hidden record would let its name pass as a registered, citable object.
        visible_ids = {
            feature.get("id")
            for feature in living_world.visible_features(world_state, location)
        }
        return existing if existing.get("id") in visible_ids else None
    if len(game.location_features(location)) >= 16:
        return None
    scene_state = living_world.ensure_scene_state(world_state)
    number = max(1, scene_state["next_feature_number"])
    used_ids = {
        feature.get("id")
        for feature in world_state.get("features", [])
        if isinstance(feature, dict)
    }
    while f"feature_{number:03d}" in used_ids:
        number += 1
    scene_state["next_feature_number"] = number + 1
    return_record = {
        "id": f"feature_{number:03d}",
        "location": location,
        **({"parent_id": parent_id} if parent_id else {}),
        "name": name,
        "description": description,
        "kind": game._clean_world_text(proposal.get("kind", "feature"), 32) or "feature",
        **({"text": game._clean_world_text(proposal.get("text"), 200)}
           if game._clean_world_text(proposal.get("text"), 200) else {}),
        "aliases": game._clean_world_text_list(proposal.get("aliases", []), 80, 8),
        "tags": ["campaign_local", "interactable_prop"],
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
    }
    world_state.setdefault("features", []).append(return_record)
    return return_record

def _valid_local_feature_parent_id(parent_id, location):
    """Allow parent links only to existing, visible entities in this scene."""
    parent_id = game._clean_world_text(parent_id, 128)
    if not parent_id:
        return None
    if parent_id == location:
        return parent_id
    world_state = game._session().world_state
    parent_location = world_state.get("locations", {}).get(parent_id)
    if (
        isinstance(parent_location, dict)
        and parent_location.get("parent_location_id") == location
        and parent_location.get("hidden") is not True
    ):
        return parent_id
    for collection in ("features", "doors", "npcs"):
        for entity in world_state.get(collection, []):
            if (
                isinstance(entity, dict)
                and entity.get("id") == parent_id
                and entity.get("location") == location
                and entity.get("hidden") is not True
            ):
                return parent_id
    return None

def _legacy_hidden_feature_name_collision(proposal, location, parent_id, name):
    if parent_id is None:
        return False
    names = {
        living_world.normalize_text(value)
        for value in (name, *(proposal.get("aliases", []) if isinstance(proposal, dict) and isinstance(proposal.get("aliases"), list) else []))
        if isinstance(value, str) and living_world.normalize_text(value)
    }
    return any(
        isinstance(feature, dict)
        and feature.get("location") == location
        and feature.get("hidden") is True
        and not isinstance(feature.get("parent_id"), str)
        and bool(names & {
            living_world.normalize_text(value)
            for value in (feature.get("name", ""), *(feature.get("aliases", []) if isinstance(feature.get("aliases"), list) else []))
            if isinstance(value, str) and living_world.normalize_text(value)
        })
        for feature in game._session().world_state.get("features", [])
    )

def _local_detail_claims_unsupported_mechanics(proposal, parent_id):
    if not isinstance(proposal, dict):
        return False
    text = living_world.normalize_text(
        " ".join(
            value for value in (proposal.get("name", ""), proposal.get("description", ""))
            if isinstance(value, str)
        )
    )
    if re.search(r"\b(?:passage|gecit|path|route|koridor)\b.*\b(?:leads?|connects?|opens?|takes?)\b", text):
        return True
    if proposal.get("kind", "detail") != "detail":
        return False
    door = game._venue_door_for(parent_id)
    if not isinstance(door, dict) or not re.search(
        r"\b(?:entrance|entry|door|gate|giris|kapi)\b", text
    ):
        return False
    return game._feature_proposal_conflicts_with_canonical_door(proposal, parent_id)

def _feature_proposal_conflicts_with_canonical_door(proposal, parent_id):
    door = game._venue_door_for(parent_id)
    if not isinstance(door, dict):
        return False
    text = living_world.normalize_text(
        " ".join(
            value for value in (
                proposal.get("name", ""),
                proposal.get("description", ""),
                *(proposal.get("aliases", []) if isinstance(proposal.get("aliases"), list) else []),
            )
            if isinstance(value, str)
        )
    )
    door_names = [door.get("name", ""), *door.get("aliases", [])]
    names_door = any(
        isinstance(name, str)
        and living_world.normalize_text(name)
        and living_world.normalize_text(name) in text
        for name in door_names
    )
    generic_door_reference = bool(
        re.search(r"\b(?:entrance|entry|door|gate|giris|kapi)\b", text)
    )
    if not names_door and not generic_door_reference:
        return False
    claims_open = bool(re.search(r"\b(?:acik|acildi|aciliyor|open)\b", text))
    claims_closed = bool(re.search(r"\b(?:kapali|kapandi|closed)\b", text))
    claims_locked = bool(re.search(r"\b(?:kilitli|locked)\b", text))
    claims_unlocked = bool(re.search(r"\b(?:kilitsiz|unlocked)\b", text))
    return (
        (door.get("open") is False and claims_open)
        or (door.get("open") is True and claims_closed)
        or (door.get("locked") is True and claims_unlocked)
        or (door.get("locked") is False and claims_locked)
    )

def location_display_name(location_id=None):
    world_state = game._session().world_state
    location_id = world_state.get("location") if location_id is None else location_id
    location = world_state.get("locations", {}).get(location_id)
    if location:
        return location.get("name", location_id)
    return "Henüz belirlenmedi" if location_id in (None, "", "Henüz belirlenmedi") else str(location_id)

def _location_alias_values(location):
    if not isinstance(location, dict):
        return []
    values = [location.get("name", "")]
    values.extend(location.get("aliases", []))
    return [game._normalize_turkish_typos(value) for value in values if isinstance(value, str) and value.strip()]

def _reference_token_matches(reference_token, input_token):
    reference_token = game._normalize_turkish_typos(reference_token)
    input_token = game._normalize_turkish_typos(input_token)
    if reference_token == input_token:
        return True
    case_endings = (
        "larindan", "lerinden", "larina", "lerine", "larinda", "lerinde",
        "larini", "lerini", "ndan", "nden", "ntan", "nten", "dan", "den",
        "tan", "ten", "yla", "yle", "lar", "ler", "la", "le", "ya", "ye",
        "yi", "yu",
        "na", "ne", "da", "de", "ta", "te", "nin", "nun", "in", "un",
        "i", "u", "a", "e",
    )
    return any(input_token.endswith(suffix) and input_token[:-len(suffix)] == reference_token
               for suffix in case_endings)

def _entity_reference_in_text(reference, text):
    """Match a complete name, allowing Turkish case endings."""
    reference_words = re.findall(r"[a-z0-9]+", game._normalize_turkish_typos(reference))
    text_words = re.findall(r"[a-z0-9]+", game._normalize_turkish_typos(text))
    if not reference_words or len(text_words) < len(reference_words):
        return False
    return any(
        all(game._reference_token_matches(ref_word, text_words[start + offset])
            for offset, ref_word in enumerate(reference_words))
        for start in range(len(text_words) - len(reference_words) + 1)
    )

def resolve_location_reference(reference):
    """Resolve a natural-language place name or alias to its Python-owned ID."""
    world_state = game._session().world_state
    if not isinstance(reference, str) or not reference.strip():
        return None
    normalized = game._normalize_turkish_typos(reference)
    locations = world_state.get("locations", {})
    if normalized in locations:
        return normalized
    current = world_state.get("location")
    root = current
    while isinstance(root, str):
        record = locations.get(root, {})
        parent = record.get("parent_location_id") if isinstance(record, dict) else None
        if not isinstance(parent, str) or parent not in locations:
            break
        root = parent
    local_matches = []
    for location_id, location in locations.items():
        if (
            not isinstance(location, dict)
            or location.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
            or location.get("parent_location_id") != root
        ):
            continue
        aliases = game._location_alias_values(location)
        if any(
            normalized == alias
            or game._entity_reference_in_text(alias, normalized)
            for alias in aliases
        ):
            local_matches.append(location_id)
    if len(local_matches) == 1:
        return local_matches[0]
    for location_id, location in locations.items():
        for alias in game._location_alias_values(location):
            if normalized == alias or (len(alias.split()) == 1 and game._entity_reference_in_text(alias, normalized)):
                return location_id
    return None

def _location_reference_in_text(text):
    world_state = game._session().world_state
    if not isinstance(text, str):
        return None
    current = world_state.get("location")
    root = current
    locations = world_state.get("locations", {})
    while isinstance(root, str):
        record = locations.get(root, {})
        parent = record.get("parent_location_id") if isinstance(record, dict) else None
        if not isinstance(parent, str) or parent not in locations:
            break
        root = parent
    local_matches = []
    for location_id, location in locations.items():
        if (
            isinstance(location, dict)
            and location.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            and location.get("parent_location_id") == root
            and any(
                game._entity_reference_in_text(alias, text)
                for alias in game._location_alias_values(location)
            )
        ):
            local_matches.append(location_id)
    if len(local_matches) == 1:
        return local_matches[0]
    for location_id, location in locations.items():
        for alias in sorted(game._location_alias_values(location), key=len, reverse=True):
            if game._entity_reference_in_text(alias, text):
                return location_id
    return None

def normalize_location_id(value):
    locations = game._session().world_state.get("locations", {})
    if isinstance(value, str) and value in locations:
        return value
    return game.resolve_location_reference(value)

def validate_location_proposal(proposal):
    """Validate creative location data while assigning no model-provided ID."""
    if not isinstance(proposal, dict):
        return None
    name = game._clean_world_text(proposal.get("name"), 60)
    location_type = game._clean_world_text(proposal.get("type", "other"), 24) or "other"
    description = game.clean_location_description(proposal.get("description", ""))
    if not name or not re.fullmatch(r"[\w .’'-]+", name, flags=re.UNICODE) or "_" in name:
        return None
    if game.resolve_location_reference(name):
        return None
    if location_type.casefold() not in {
        "city", "town", "village", "building", "settlement", "wilderness",
        "region", "landmark", "dungeon", "other", "şehir", "kasaba",
        "köy", "bina", "bölge", "orman", "mekân", "city_gate", "city gate",
        "district", "neighborhood", "neighbourhood", "quarter", "street", "square", "market",
        "mahalle", "semt", "sokak", "cadde", "meydan", "pazar",
    }:
        location_type = "other"
    elif location_type.casefold() in ("city_gate", "city gate"):
        location_type = "city"
    aliases = game._clean_world_text_list(proposal.get("aliases", []), 60, 8)
    safe_aliases = []
    for alias in aliases:
        if alias.casefold() == name.casefold() or game.resolve_location_reference(alias):
            continue
        if re.fullmatch(r"[\w .’'-]+", alias, flags=re.UNICODE) and "_" not in alias:
            safe_aliases.append(alias)
    return {"name": name, "type": location_type, "aliases": safe_aliases, "description": description}

def _local_place_recommendation_options(npc_target, world_state, place_kind=None):
    if not isinstance(npc_target, dict):
        return []
    local_location_id = npc_target.get("location")
    if (
        not isinstance(local_location_id, str)
        or local_location_id != world_state.get("location")
    ):
        return []
    options = [
        {
            "location_id": place_id,
            "name": str(place.get("name", ""))[:80],
            "kind": str(place.get("place_kind") or place.get("scene_kind", ""))[:40],
            "access": game._local_place_access(place_id, world_state),
        }
        for place_id, place in world_state.get("locations", {}).items()
        if isinstance(place, dict)
        and place_id != local_location_id
        and place.get("parent_location_id") == local_location_id
        and place.get("hidden") is not True
        and isinstance(place.get("name"), str)
        and place.get("name", "").strip()
        and (place.get("provenance") or {}).get("source") != "world_thread"
        and (
            place_kind is None
            or (place.get("place_kind") or place.get("scene_kind")) == place_kind
        )
    ]
    return sorted(options, key=lambda option: option["name"].casefold())[:6]

def _local_place_access(place_id, world_state):
    for door in world_state.get("doors", []):
        if not isinstance(door, dict):
            continue
        if (
            door.get("place_id") == place_id
            or door.get("location_id") == place_id
            or door.get("id") == f"venue-door:{place_id}"
        ):
            if door.get("locked") is True:
                return "locked"
    return "available"

def _attributed_place_note(spoken_text, npc_target, world_state, player_input):
    """W03: the separate narrator note for a locked venue the NPC named, only when the player already knows the lock."""
    if not isinstance(spoken_text, str) or not local_dialogue.is_local_place_recommendation_request(player_input):
        return None
    options = game._local_place_recommendation_options(
        npc_target, world_state, place_kind=local_dialogue.local_place_recommendation_kind(player_input))
    folded = npc_statements.fold(spoken_text)
    for option in options:
        if option["access"] != "locked" or npc_statements.fold(option["name"]) not in folded:
            continue
        view = attributed_claims.present_claim(
            {"speaker_text": spoken_text, "source_event_id": f"speech:{npc_target.get('id')}",
             "subject": {"name": option["name"], "locked": True}},
            {"lock_known_to_player": game._lock_known_to_player(world_state, f"venue-door:{option['location_id']}")})
        return view["narrator_note"]
    return None

def _ground_local_place_recommendation_reply(
    spoken_text, npc_target, world_state, player_input
):
    """A person's word about a place stands, unless a real place fits it better.

    What is said is an attributed reference, and it becomes real only if the
    player follows it. A hidden place stays unsaid; a place that does not exist
    gives way to an open one the speaker can name.
    """
    if (
        not isinstance(spoken_text, str)
        or not local_dialogue.is_local_place_recommendation_request(player_input)
    ):
        return spoken_text
    folded_reply = npc_statements.fold(spoken_text)
    if any(
        (place.get("provenance") or {}).get("source") == "world_thread"
        and npc_statements.fold(place.get("name", "")) in folded_reply
        for place in world_state.get("locations", {}).values() if isinstance(place, dict)
    ):
        return spoken_text  # a real place of this town, handed to this person to name
    requested_kind = local_dialogue.local_place_recommendation_kind(player_input)
    options = game._local_place_recommendation_options(
        npc_target, world_state, place_kind=requested_kind
    )
    available = [item for item in options if item["access"] == "available"]
    folded_spoken = npc_statements.fold(spoken_text)
    for place in world_state.get("locations", {}).values():
        name = place.get("name") if isinstance(place, dict) and place.get("hidden") is True else None
        if isinstance(name, str) and name.strip() and re.search(
            r"(?<!\w)" + re.escape(npc_statements.fold(name)) + r"[a-z0-9]*(?!\w)", folded_spoken,
        ):
            if available:
                return (
                    f'Bildiğim ve şu anda gidebileceğin yerlerden '
                    f'{available[0]["name"]} iyi bir seçenek olabilir.'
                )
            return "Orayı pek bilmem."
    names = npc_statements._named_places(spoken_text)
    generic_place = npc_statements._unnamed_place(folded_spoken)
    by_name = {}
    for option in options:
        by_name[npc_statements.fold(option["name"])] = option
        place = world_state.get("locations", {}).get(option["location_id"], {})
        for alias in place.get("aliases", []) if isinstance(place, dict) else []:
            if isinstance(alias, str) and alias.strip():
                by_name[npc_statements.fold(alias)] = option
    spoken_options = [item for item in options if npc_statements.fold(item["name"]) in folded_spoken]
    if len(spoken_options) == 1 and all(
        npc_statements.fold(name) in npc_statements.fold(spoken_options[0]["name"]) for name, _, _ in names
    ):
        return spoken_text  # a catalog name need not end in a word the parser reads whole
    matched = [by_name.get(npc_statements.fold(name)) for name, _, _ in names]
    if matched and all(item is not None for item in matched) and len(
        {item["location_id"] for item in matched}
    ) == 1:
        # W03 (Rev2 5.5): the NPC's own recommendation stays the NPC's; a lock the player already knows is a
        # separate narrator note (attributed_claims.present_claim), an unknown lock is never revealed here.
        return spoken_text
    if local_dialogue.is_open_local_place_discovery(player_input) or not (names or generic_place):
        # A general request such as "another place" is not permission to replace
        # an attributed NPC reference, and a line naming no venue is left alone.
        return spoken_text
    if available:
        return (
            f'Bildiğim ve şu anda gidebileceğin yerlerden '
            f'{available[0]["name"]} iyi bir seçenek olabilir.'
        )
    return spoken_text

def _ground_local_place_recommendation_stage(stage_direction, npc_target, world_state, player_input):
    """Remove only stage clauses that point to unverified places or imply travel."""
    if (
        not isinstance(stage_direction, str)
        or not stage_direction.strip()
        or not local_dialogue.is_local_place_recommendation_request(player_input)
    ):
        return stage_direction
    options = game._local_place_recommendation_options(npc_target, world_state)
    known_names = [
        npc_statements.fold(option["name"])
        for option in options
    ]
    for option in options:
        place = world_state.get("locations", {}).get(option["location_id"], {})
        if isinstance(place, dict):
            known_names.extend(
                npc_statements.fold(alias)
                for alias in place.get("aliases", [])
                if isinstance(alias, str) and alias.strip()
            )
    hidden_names = [
        npc_statements.fold(place["name"])
        for place in world_state.get("locations", {}).values()
        if isinstance(place, dict)
        and place.get("hidden") is True
        and isinstance(place.get("name"), str)
        and place["name"].strip()
    ]
    retained = []
    for clause in re.split(r"(?<=[.!?])\s+|;\s*", stage_direction.strip()):
        folded = npc_statements.fold(clause)
        if not folded:
            continue
        if any(
            re.search(r"(?<!\w)" + re.escape(name) + r"(?:[a-z0-9]*)?(?!\w)", folded)
            for name in hidden_names
        ):
            continue
        place_names = npc_statements._named_places(clause)
        unknown_name = any(
            npc_statements.fold(name) not in known_names
            for name, _, _ in place_names
        )
        place_words = [
            word for word in folded.split()
            if npc_statements.place_kind_of(word) is not None
        ]
        known_place_named = any(name in folded for name in known_names if name)
        if unknown_name or (place_words and not known_place_named):
            continue
        locked_place_named = any(
            option["access"] == "locked"
            and npc_statements.fold(option["name"]) in folded
            for option in options
        )
        if locked_place_named and re.search(
            r"\b(?:ac\w*|iceri gir\w*|giriyor|girer|girdi|"
            r"gidiyor|gider|gitti|yuru\w*|yaklas\w*)\b",
            folded,
        ):
            continue
        if re.search(
            r"\b(?:uzaklas\w*|yaklas\w*|yuru\w*|ilerle\w*|ayril\w*|"
            r"gidiyor|gider|gitti|gitmek|iceri gir\w*|giriyor|girer|"
            r"girdi|cikiyor|cikar|cikti|disari cik\w*|gotur\w*|"
            r"eslik et\w*|takip et\w*)\b",
            folded,
        ):
            continue
        retained.append(clause.strip())
    return " ".join(retained)

def _explicit_sword_drop(player_input):
    """Only an unambiguous present-tense sword drop bypasses model intent."""
    if not isinstance(player_input, str):
        return False
    return re.fullmatch(  # the owner types without the dots
        r"\s*(?:kilicimi|kilici|kilic)\s+(?:yere\s+)?"
        r"(?:birakiyorum|koyuyorum|atiyorum)\s*[.!]?\s*",
        game._normalize_turkish_typos(player_input),
    ) is not None

def update_inventory_from_player(player_input):
    """Move the explicitly named sword using Python-owned inventory state."""
    world_state = game._session().world_state
    text = game._normalize_turkish_typos(player_input)
    mentions_weapon = any(token in text for token in ("kilic", "silah"))
    if not mentions_weapon:
        return None

    dropping = any(token in text for token in ("birak", "yere koy", "yere at"))
    picking_up = any(token in text for token in ("aliyorum", "yerden al", "tekrar al"))
    if not (dropping or picking_up):
        return None

    if dropping:
        sword = held_weapon.held_sword(world_state)
        equipment = world_state.get("equipment")
        hand = equipment.get("main_hand") if isinstance(equipment, dict) else None
        if sword is not None and hand == held_weapon._identity(sword):
            if isinstance(sword, dict):
                return equipment_economy.carry_named(game._session(), "Kılıç", dropping=True, item_id=hand)
            world_state["inventory"].remove(sword)
            held_weapon.release_hand(world_state, sword)
            current_loc = world_state.get("location", "tavern")
            loc_items = world_state["ground_items_by_location"].setdefault(current_loc, [])
            if "Kılıç" not in loc_items:
                loc_items.append("Kılıç")
            return "Python durumu: Kılıç envanterden yere taşındı."

    if any(isinstance(i, dict) for _, items in equipment_economy.containers(world_state) for i in items):
        return equipment_economy.carry_named(game._session(), "Kılıç", dropping=dropping)

    current_loc = world_state.get("location", "tavern")
    loc_items = world_state["ground_items_by_location"].get(current_loc, [])

    if dropping:
        inventory = world_state.get("inventory")
        if isinstance(inventory, list) and inventory.count("Kılıç") == 1:
            inventory.remove("Kılıç")
            equipment = world_state.get("equipment")
            hand = equipment.get("main_hand") if isinstance(equipment, dict) else None
            if isinstance(hand, str) and held_weapon._fold(hand) in held_weapon.SWORD_ALIASES:
                equipment["main_hand"] = None
            loc_items = world_state["ground_items_by_location"].setdefault(current_loc, [])
            if "Kılıç" not in loc_items:
                loc_items.append("Kılıç")
            return "Python durumu: Kılıç envanterden yere taşındı."
        sword = held_weapon.held_sword(world_state)
        if sword is not None:
            world_state["inventory"].remove(sword)
            held_weapon.release_hand(world_state, sword)
            loc_items = world_state["ground_items_by_location"].setdefault(current_loc, [])
            if "Kılıç" not in loc_items:
                loc_items.append("Kılıç")
            return "Python durumu: Kılıç envanterden yere taşındı."
        if "Kılıç" in loc_items:
            return "Python durumu: Kılıç zaten yerde."
        return "Python durumu: Kılıç zaten envanterde değil; yerde olup olmadığı world_state içindedir."

    if picking_up:
        if "Kılıç" in loc_items:
            loc_items.remove("Kılıç")
            if "Kılıç" not in world_state["inventory"]:
                world_state["inventory"].append("Kılıç")
            return "Python durumu: Yerdeki Kılıç envantere alındı."
        return "Python durumu: Yerde alınabilecek bir Kılıç yok."

    return None

def apply_check_outcome_to_world_state(player_input, result):
    """Resolve simple stealth/door facts in Python after the actual roll."""
    world_state = game._session().world_state
    text = player_input.casefold()
    succeeded = result["result"] == "BAŞARILI"

    if "gizlen" in text or "saklan" in text:
        world_state["flags"]["player_hidden"] = succeeded

    # LR00-P1: only a door operation (strength or lockpicking) can change a
    # door, and only when the player affirmatively tries it. A successful look
    # at the lock ("kırmayacağım, sadece kilide bakacağım", "açmaya
    # kalkmıyorum") must never open or break it.
    if result.get("skill") not in {"Athletics", "Sleight of Hand"} or "?" in str(player_input):
        return
    folded = game._normalize_turkish_typos(player_input)
    breaking = game._affirmative_door_verb(folded, r"kapiyi\s+", ("kir", "parcala", "yik"))
    door_attempt = breaking or game._affirmative_door_verb(
        folded, r"(?:kapiyi|kapi|kilidi)\s+", ("ac", "zorla", "it")
    ) or game._affirmative_door_verb(folded, r"", ("zorla",))
    if door_attempt:
        door = game._current_door()
        if door and succeeded:
            door["locked"] = False
            door["open"] = True
            if breaking:
                door["broken"] = True

def _names_current_local_exit(player_input):
    """True when the player names the parent of the current local venue."""
    if not isinstance(player_input, str):
        return False
    world_state = game._session().world_state
    current = world_state.get("locations", {}).get(world_state.get("location"), {})
    if (
        not isinstance(current, dict)
        or current.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
    ):
        return False
    import exits
    parent = world_state.get("locations", {}).get(exits.way_out(world_state, world_state.get("location")))
    if not isinstance(parent, dict):
        return False
    normalized = living_world.normalize_text(player_input)
    if not re.search(r"\b(?:geri\s+don\w*|disari\s+cik\w*)\b", normalized):
        return False
    names = [parent.get("name", "")]
    aliases = parent.get("aliases")
    if isinstance(aliases, list):
        names.extend(aliases)
    matched = False
    for name in names:
        if not isinstance(name, str):
            continue
        needle = living_world.normalize_text(name)
        if len(needle) >= 4 and re.search(rf"\b{re.escape(needle)}\b", normalized):
            matched = True
            break
    return matched

def _engine_location_parent(location_id):
    world_state = game._session().world_state
    location = world_state.get("locations", {}).get(location_id, {})
    parent = location.get("parent_location_id") if isinstance(location, dict) else None
    return parent if isinstance(parent, str) and parent in world_state.get("locations", {}) else None

def _existing_local_tavern(parent_location_id):
    locations = game._session().world_state.get("locations", {})
    if not isinstance(locations, dict):
        return None
    return next(
        (
            location for location in locations.values()
            if isinstance(location, dict)
            and location.get("parent_location_id") == parent_location_id
            and location.get("scene_kind") == "tavern"
        ),
        None,
    )

def _resolve_explicit_local_scene_parent(
    parent_location_id, player_input, *, fallback_single=True
):
    locations = game._session().world_state.get("locations", {})
    if not isinstance(locations, dict):
        return None
    candidates = [
        location for location in locations.values()
        if isinstance(location, dict)
        and location.get("parent_location_id") == parent_location_id
        and location.get("hidden") is not True
        and isinstance(location.get("id"), str)
    ]
    target_text = living_world._text_outside_quotes(player_input)
    matched = [
        location for location in candidates
        if any(
            isinstance(name, str) and game._entity_reference_in_text(name, target_text)
            for name in [location.get("name", ""), *location.get("aliases", [])]
        )
    ]
    if len(matched) == 1:
        return matched[0]
    if matched:
        return None
    if re.search(
        r"\b[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)+\s+(?:inn|tavern|han|building)\b",
        target_text,
    ):
        return None
    # "The building" means the one in view; a place the town only talks about is not it.
    in_view = [item for item in candidates if (item.get("provenance") or {}).get("source") != "world_thread"]
    return in_view[0] if fallback_single and len(in_view) == 1 else None

def _scene_detail_parent(scene_id, player_input):
    """Bind a proposed detail to a named local structure or the current scene."""
    if not isinstance(scene_id, str):
        return None
    explicitly_named = game._resolve_explicit_local_scene_parent(
        scene_id, player_input, fallback_single=False
    )
    if explicitly_named:
        return explicitly_named
    if (
        living_world.affirmative_structure_inspection(player_input)
        and not living_world.is_anchored_structure_inquiry(player_input)
    ):
        return {"id": scene_id, "name": game.location_display_name()}
    if (
        living_world.is_anchored_structure_inquiry(player_input)
        or living_world.is_exploratory_structure_question(player_input)
    ):
        return game._resolve_explicit_local_scene_parent(scene_id, player_input)
    if living_world.affirmative_structure_inspection(player_input):
        return {"id": scene_id, "name": game.location_display_name()}
    return None

def _anchored_structure_features(player_input, location_id, parent_id):
    text = living_world.normalize_text(
        living_world._text_outside_quotes(player_input)
    )
    visible = []
    hidden = []
    for feature in game._session().world_state.get("features", []):
        if (
            not isinstance(feature, dict)
            or feature.get("location") not in {location_id, parent_id}
            or feature.get("parent_id") not in {None, parent_id}
        ):
            continue
        aliases = [feature.get("name", ""), *feature.get("aliases", [])]
        if not any(
            isinstance(alias, str) and alias
            and (
                game._entity_reference_in_text(alias, text)
            )
            for alias in aliases
        ):
            continue
        if feature.get("hidden") is True:
            hidden.append(feature)
        else:
            visible.append(feature)
    return visible, hidden

def _ensure_local_tavern(parent_location_id, *, open_for_entry=False):
    world_state = game._session().world_state
    locations = world_state.setdefault("locations", {})
    if parent_location_id not in locations or len(locations) >= 80:
        return None
    existing = next(
        (
            location for location in locations.values()
            if isinstance(location, dict)
            and location.get("parent_location_id") == parent_location_id
            and location.get("scene_kind") == "tavern"
        ),
        None,
    )
    if existing:
        return existing
    number = max(1, int(world_state.get("next_location_number", 1)))
    while f"location_{number:03d}" in locations:
        number += 1
    name = name_catalog.place_name(world_state, "tavern", parent_location_id) or (
        living_world.stable_local_name(world_state, parent_location_id, "local tavern") + " Hanı"
    )
    location_id = f"location_{number:03d}"
    world_state["next_location_number"] = number + 1
    record = {
        "id": location_id,
        "name": name,
        "type": "building",
        "aliases": ["taverna", "tavern", "inn", "han", "meyhane", name],
        "description": "Sokağa açılan, sade ve sıcak bir han.",
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "parent_location_id": parent_location_id,
        "exit_location_id": parent_location_id,
        "scene_kind": "tavern",
        "tags": ["campaign_local", "public_house"],
    }
    locations[location_id] = record
    # New venues only. An already saved han does not gain a door later.
    import grounded_action
    door_id = game._venue_door_id(location_id)
    world_state.setdefault("doors", []).append({
        "id": door_id,
        "name": f"{name} Kapısı",
        "location": parent_location_id,
        "description": f"{name} sokağa açılan kapısı.",
        **(
            {"open": True, "locked": False} if open_for_entry
            else grounded_action.public_door_state(world_state, door_id, "tavern")
        ),
        "broken": False,
    })
    return record

def _scene_feature_match(player_input, location_id):
    matches = []
    text = living_world.normalize_text(
        living_world._text_outside_quotes(player_input)
    )
    for feature in game._session().world_state.get("features", []):
        if not isinstance(feature, dict) or feature.get("location") != location_id:
            continue
        aliases = [feature.get("name", ""), *feature.get("aliases", [])]
        best = 0
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                continue
            if (
                game._entity_reference_in_text(alias, text)
                or living_world.normalize_text(alias) in text
            ):
                words = re.findall(r"[a-z0-9]+", game._normalize_turkish_typos(alias))
                best = max(best, len(words))
        if best:
            matches.append((best, feature))
    if not matches:
        return []
    longest = max(score for score, _feature in matches)
    return [feature for score, feature in matches if score == longest]

def _scene_names(location_id):
    return [
        npc for npc in game.active_npcs(location_id)
        if isinstance(npc, dict) and npc.get("name")
    ]

def _variation_index(key, size):
    """0 on first use of ``key``, then one step per turn; stable within a turn.

    Transient presentation state only: never saved, never read by rules.
    """
    session = game._session()
    store = session.__dict__.setdefault("_variation_state", {})
    turn = session.world_state.get("flags", {}).get("turn_index", 0)
    last_turn, count = store.get(key, (None, -1))
    if last_turn != turn:
        count += 1
        store[key] = (turn, count)
    return store[key][1] % size

def _look_opening(location_name):
    """First look keeps the plain line; repeated looks do not repeat it verbatim."""
    openings = [line.format(name=location_name) for line in game._LOOK_OPENINGS]
    return openings[game._variation_index(("look", location_name), len(openings))]

def _scene_look_text(location_id):
    world_state = game._session().world_state
    location_name = game.location_display_name(location_id)
    people = [npc for npc in game._scene_names(location_id) if not npc.get("hidden")]
    features = living_world.visible_scene_facts(world_state).get("features", [])
    turn_index = world_state.get("flags", {}).get("turn_index", 0)
    scene = living_world.ensure_scene_record(
        world_state,
        location_id,
        turn_index,
    )
    if isinstance(location_id, str):
        living_world.expire_referents(
            world_state, turn_index, location_id=location_id
        )
    parts = [game._look_opening(location_name)]
    if people:
        parts.append(
            "Yakında " + living_world.public_scene_people(people[:3]) + " var."
        )
        parts.extend(
            f"{living_world.turkish_initial_upper(living_world.public_npc_name(npc))}: {npc['appearance']}"
            for npc in people[:2]
            if isinstance(npc.get("appearance"), str) and npc["appearance"].strip()
        )
    import fallen
    parts.append(fallen.scene_line(world_state))
    if features:
        parts.append(
            living_world.turkish_initial_upper(
                ", ".join(feature.get("name", "bir ayrıntı") for feature in features[:3])
            ) + " gözüne çarpıyor."
        )
    referent = next(
        (
            ref for ref in scene.get("referents", [])
            if ref.get("lifecycle") == "presented"
        ),
        None,
    )
    if referent and isinstance(referent.get("description"), str):
        parts.append(referent["description"])
    elif scene.get("kind") == "wilderness":
        parts.append("Burası sakin; doğal sesler dışında belirgin bir hareket yok.")
    elif scene.get("last_beat"):
        parts.append(scene["last_beat"])
    return " ".join(part for part in parts if part)

def _look_scene_changed():
    """True on a first look and whenever people, details or the moment here have changed."""
    world_state = game._session().world_state
    here = world_state.get("location")
    scene = world_state.get("scene_state", {}).get("scenes", {}).get(here)
    seen = [
        here,
        sorted(str(npc.get("id")) for npc in game._scene_names(here) if not npc.get("hidden")),
        sorted(str(item.get("name")) for item in living_world.visible_scene_facts(world_state).get("features", [])),
        scene.get("last_beat") if isinstance(scene, dict) else None,
    ]
    flags = world_state.setdefault("flags", {})
    changed = flags.get("last_look_scene") != seen
    flags["last_look_scene"] = seen
    return changed

def _keep_people_in_look(narration, action_result):
    """A narrated look may reword the scene but nobody standing here disappears from it."""
    if not isinstance(narration, str) or not (action_result or {}).get("scene_look"):
        return narration
    told = game._normalize_turkish_typos(narration)
    here = game._session().world_state.get("location")
    missing = [
        npc for npc in game._scene_names(here)[:3]
        if not npc.get("hidden")
        and game._normalize_turkish_typos(living_world.public_npc_name(npc)) not in told
    ]
    if not missing:
        return narration
    return f"{narration} Yakında {living_world.public_scene_people(missing)} var."

def _set_scene_active_npc(npc, turn_index):
    if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
        return
    talk_mode.open(game._session().world_state, npc["id"], turn=turn_index)

def _reopen_public_doors():
    import grounded_action
    grounded_action.reopen_public_doors(game._session().world_state)

def _a_walk(read, action_result):
    """The first part was a walk: the reading said go_to, or the receipt is a walk's own (grounded go/enter, travel)."""
    if read.get("kind") == "go_to":
        return True
    steps = action_result.get("steps") if action_result.get("action") == "grounded_action" else None
    return action_result.get("action") == "travel" or bool(
        isinstance(steps, list) and steps and isinstance(steps[0], dict) and steps[0].get("verb") in {"go", "enter"})

def _walked_there(read, action_result, place_before):
    """The walk got there: the player stands in the place walked to, or in front of it (its receipt completed)."""
    here = game._session().world_state.get("location")
    if action_result.get("action") == "travel":
        if action_result.get("status") == "already_here":  # "zaten içindesin": being there is having got there
            return here == action_result.get("target_id")
        return action_result.get("status") == "resolved" and here == action_result.get("target_id") != place_before
    if action_result.get("action") != "grounded_action" or action_result.get("status") != "completed":
        return False
    target = read.get("id") if read.get("kind") == "go_to" else action_result.get("target_id")
    if target is None:
        return False
    steps = [step for step in action_result.get("steps") or [] if isinstance(step, dict)]
    return here == target or (here == place_before and any(
        step.get("target_id") == target and step.get("position") in {"at_door", "outside"}
        and not (step.get("door_state") or {}).get("locked")  # a locked door is where the walk stopped
        for step in steps))

def _may_propose_local_place(resolved_turn, player_input):
    """Only an unknown destination, asked for from the open streets of a settlement."""
    import heard_rumours
    import local_places
    result = resolved_turn.action_result
    world_state = game._session().world_state
    settlement = local_places.settlement_of(world_state, world_state.get("location"))
    return bool(
        resolved_turn.allow_new_locations
        and isinstance(result, dict)
        and result.get("action") == "travel"
        and result.get("status") == "awaiting_proposal"
        and (
            living_world.on_open_street(world_state)
            # An NPC of this settlement said the name aloud: the player may follow it from indoors too.
            or heard_rumours.heard_in_speech(world_state, settlement, result.get("target_reference")) is not None
        )
        and settlement
        and not game.is_player_world_assertion(player_input)
    )

def _accepted_local_place(packet, action_result):
    """Take one place from the packet, named in the player's words; the rest of it is dropped."""
    updates = packet.get("world_updates")
    proposals = updates.get("create_locations") if isinstance(updates, dict) else None
    proposal = proposals[0] if isinstance(proposals, list) and proposals else None
    if not isinstance(proposal, dict):
        return []
    import heard_rumours
    validated = game.validate_location_proposal({
        "type": proposal.get("type"), "description": proposal.get("description"),
        "name": heard_rumours.base_name(action_result.get("target_reference") or ""), "aliases": [proposal.get("name")],
    })
    if not validated or validated["type"].casefold() in game._NOT_A_LOCAL_PLACE:
        return []
    if living_world.reads_as_street(validated["name"], proposal.get("type")):
        validated["type"] = "district"
    return [validated]

def _settle_local_place(action_result):
    """A new local place hangs under its settlement, which also gives it the walking route."""
    import heard_rumours
    import local_places
    world_state = game._session().world_state
    settlement = local_places.settlement_of(world_state, world_state.get("location"))
    place_id = game.resolve_location_reference(heard_rumours.base_name(action_result.get("target_reference", "")))
    place = world_state["locations"].get(place_id)
    if settlement and isinstance(place, dict):
        place.update(parent_location_id=settlement, exit_location_id=settlement, tags=["campaign_local"])
        said_by = heard_rumours.heard_in_speech(world_state, settlement, action_result.get("target_reference"))
        if said_by:
            place["provenance"] = {"source": "npc_rumour", "said_by": said_by,
                                   "turn": world_state.get("flags", {}).get("turn_index", 0)}
        # The kind decides what the scene may hold and which people and street life it gets.
        if place.get("type") == "district":
            place.update(scene_kind="city", environment="city")
        elif living_world.scene_kind(world_state, place_id) == "quiet":
            place["scene_kind"] = "building"

def _is_canonical_city_id(loc_id):
    if not isinstance(loc_id, str):
        return False
    lid = loc_id.casefold()
    return (
        lid in ("city", "town", "village", "settlement")
        or ":city:" in lid
        or ":town:" in lid
        or ":village:" in lid
        or ":settlement:" in lid
        or lid.startswith(("city:", "town:", "village:", "settlement:"))
    )

def generate_npc_id():
    world_state = game._session().world_state
    number = max(1, int(world_state.get("next_npc_number", 1)))
    existing = {npc.get("id") for npc in world_state["npcs"]}
    while f"npc_{number:03d}" in existing:
        number += 1
    world_state["next_npc_number"] = number + 1
    return f"npc_{number:03d}"

def create_npc_from_ai(proposal, request_key=None, *, allow_other_location=False):
    world_state = game._session().world_state
    validated = game.validate_npc_proposal(proposal, allow_other_location=allow_other_location)
    if not validated:
        return None
    if isinstance(request_key, str) and re.fullmatch(r"[0-9a-f]{64}", request_key):
        existing_request = next(
            (
                npc for npc in world_state["npcs"]
                if npc.get("origin_request_key") == request_key
                and npc.get("location") == validated["location"]
            ),
            None,
        )
        if existing_request is not None:
            return existing_request
    normalized_name = validated["name"].casefold()
    normalized_role = validated["role"].casefold()
    for npc in world_state["npcs"]:
        if (
            npc.get("location") == validated["location"]
            and npc.get("name", "").casefold() == normalized_name
        ):
            if npc.get("role", "").casefold() != normalized_role:
                return None
            local_dialogue.ensure_personal_profile(npc)
            return npc
    if len(world_state["npcs"]) >= 60 or len(game.active_npcs(validated["location"])) >= 6:
        return None
    npc = {
        "id": game.generate_npc_id(),
        **validated,
        **(
            {"origin_request_key": request_key}
            if isinstance(request_key, str)
            and re.fullmatch(r"[0-9a-f]{64}", request_key)
            else {}
        ),
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "tags": [],
        # Canonical identity exists immediately, but the player must learn the name.
        # Legacy saves without this field remain name-known for compatibility.
        "name_known_to_player": False,
        "role_known_to_player": living_world.role_is_visibly_obvious(validated.get("role")),
    }
    living_world.assign_visible_trait(world_state, npc)
    local_dialogue.ensure_personal_profile(npc)
    npc["voice_trait"] = local_dialogue.voice_trait(world_state, npc)
    game.ensure_npc_combat_stats(npc)
    equipment_economy.give_person_gear(world_state, npc)  # D-231
    equipment_economy.give_person_purse(world_state, npc)  # D-207
    world_state["npcs"].append(npc)
    return npc

def clean_location_description(text, *, whole_words=False):
    """A place description on one line, at most 240 characters and free of game mechanics; "" otherwise.

    `whole_words` is for a heard rumour's claim only, which also loses unbacked money afterwards: there 'altında',
    'pazar', 'zarar', 'öldürdü' stay. A place the model proposes keeps the substring check ('altınlık' goes too).
    """
    description = game._clean_world_text(text, 240) or ""
    mechanical_terms = ("hp", "damage", "hasar", "inventory", "envanter", "altın", "d20", "dc", "zar", "kapı açık", "öldü")
    folded = description.casefold()
    if any((re.search(rf"\b{re.escape(term)}\b", folded) if whole_words else term in folded) for term in mechanical_terms):
        return ""
    return description

def commit_location_change(location_id, turn_index=None):
    """Commit a location transition after Python has resolved its destination."""
    world_state = game._session().world_state
    previous_location = world_state.get("location")
    if game._venue_entry_door(world_state, previous_location, location_id):
        return False
    import authored_dungeon
    authored_dungeon.require_transition(world_state, location_id)
    if location_id not in world_state.get("locations", {}):
        return False
    entry = game._venue_door_for(location_id)
    if isinstance(entry, dict) and not entry.get("open") and not entry.get("broken"):
        entry["open"] = True  # walking in through a door that was only closed
    world_state["location"] = location_id
    game.ensure_campaign_clock()
    game._ensure_location_entities(location_id)
    effective_turn = (
        turn_index
        if type(turn_index) is int
        else world_state.get("flags", {}).get("turn_index", 0)
    )
    living_world.record_scene_visit(world_state, location_id, effective_turn)
    living_world.materialize_scene(
        world_state,
        location_id,
        effective_turn,
        create_npc=game.create_npc_from_ai,
        create_feature=game.create_local_feature,
    )
    if previous_location != location_id:
        # BM T6: the arrival text belongs to one arrival; a move by any path drops it, `narrate` writes the new one.
        (world_state.get("scene_state") or {})["arrival_text"] = None
        import economic_actions
        import grounded_action
        # C13: a card prepared before this turn is about the place left behind; this turn's own cards stay.
        economic_actions.cancel_prepared(world_state, actor_id="player",
                                         except_source_action_id=game.turn_source_key(game._session()))
        grounded_action.clear_near(world_state)
        # Narrator lines about the street just left are not this place's facts.
        game._session().recent_dm_narrations.clear()
        if game.ensure_combat_state()["active"]:
            game.end_combat("location_changed")
        talk_mode.close(world_state, "moved")
        scheduled_events.arm_table_absence(world_state, previous_location)
        now = world_state["campaign_time"]["elapsed_seconds"]
        scheduled_events.process_events(
            world_state, now, now,
            observation={"kind": "arrival", "location_id": location_id},
        )
    import exploration
    exploration.apply_environment(world_state)
    exploration.record_knowledge(world_state)
    exploration.notice_passively(game._session())
    return previous_location != location_id

def _ensure_location_entities(location):
    """Create only Python-owned mechanical entities for a known location."""
    world_state = game._session().world_state
    predefined_doors = {
        "tavern": {
            "name": "Taverna Kapısı", "description": "Taverna giriş kapısı.",
            "locked": False, "open": False, "broken": False
        },
        "castle": {
            "name": "Kale Kapısı", "description": "Kalenin giriş kapısı.",
            "locked": True, "open": False, "broken": False
        },
    }
    door_data = predefined_doors.get(location)
    if door_data and not any(door.get("location") == location for door in world_state["doors"]):
        world_state["doors"].append({**door_data, "location": location})

def _commit_travel_action(action_result):
    """Resolve a proposed/known travel destination and commit only a registered ID."""
    world_state = game._session().world_state
    target_reference = action_result.get("target_reference", "")
    target_id = game.resolve_location_reference(target_reference)
    if not target_id:
        world_state.setdefault("flags", {})["pending_destination"] = None
        action_result.update({"success": False, "status": "failed", "target": None})
        action_result["state_changes"] = ["flags.pending_destination"]
        return False
    action_result["target"] = target_id
    if action_result.get("completion") == "intended":
        world_state.setdefault("flags", {})["pending_destination"] = target_id
        action_result.update({"success": None, "status": "intended"})
        action_result["state_changes"] = ["flags.pending_destination"]
        return True
    if world_state.get("location") in world_state.get("locations", {}):
        action_result.update(timed_gameplay.start_travel(game._session(), target_id))
        return action_result.get("success") is True
    combat_was_active = game.ensure_combat_state()["active"]
    changed = game.commit_location_change(target_id)
    if not changed and game._venue_entry_door(
        world_state, world_state.get("location"), target_id
    ):
        door = game._venue_entry_door(world_state, world_state.get("location"), target_id)
        action_result.update({
            "success": False,
            "status": "blocked",
            "direct_response": game._locked_door_refusal(door),
            "state_changes": [],
        })
        return False
    if changed and combat_was_active:
        action_result.update(combat_ended=True, end_reason="location_changed", combat=game._combat_snapshot())
    world_state.setdefault("flags", {})["pending_destination"] = None
    action_result.update({
        "success": True,
        "status": "completed",
        "previous_location": action_result.get("previous_location", "Henüz belirlenmedi"),
        "new_location": target_id,
    })
    changes = ["player.location"] if changed else []
    changes.append("flags.pending_destination")
    action_result["state_changes"] = changes
    return True

def _ensure_local_merchant(location_id, *, create=True):
    world_state = game._session().world_state
    existing = next(
        (
            npc for npc in world_state.get("npcs", [])
            if isinstance(npc, dict)
            and npc.get("location") == location_id
            and game._is_shopkeeper_role(npc.get("role"))
        ),
        None,
    )
    if existing:
        shop = next(
            (
                item for item in world_state.get("shops", [])
                if isinstance(item, dict)
                and item.get("shopkeeper_id") == existing.get("id")
            ),
            None,
        )
        return existing, shop
    if not create:
        return None, None
    local_merchants = [
        npc for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("location") == location_id
        and game._is_shopkeeper_role(npc.get("role"))
    ]
    if (
        len(local_merchants) >= 3
        or len(world_state.get("shops", [])) >= 12
        or len(world_state.get("npcs", [])) >= 60
    ):
        return None, None
    merchant = game.create_npc_from_ai({
        "name": living_world.stable_local_name(
            world_state, location_id, "Tüccar"
        ),
        "role": "Tüccar",
        "location": location_id,
        "appearance": "Sade giysili, çevresini dikkatle gözleyen bir gezgin.",
        "personality": "Sohbet etmeye açık, aceleci değil.",
        "relationship": "neutral",
    })
    if not merchant:
        return None, None
    shop_id = game.generate_shop_id()
    shop = {
        "id": shop_id,
        "name": f"{game._turkish_genitive_form(merchant['name'])} Tezgâhı",
        "description": "Küçük, sade bir yerel tezgâh.",
        "location": location_id,
        "tags": ["campaign_local", "shop"],
        "shopkeeper_id": merchant["id"],
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
    }
    merchant["tags"] = ["campaign_local", "shopkeeper", f"shop:{shop_id}"]
    merchant["shop_id"] = shop_id
    world_state.setdefault("shops", []).append(shop)
    return merchant, shop

def _scene_presence_text(location_id):
    world_state = game._session().world_state
    people = game._scene_names(location_id)
    shops = [
        shop for shop in world_state.get("shops", [])
        if isinstance(shop, dict) and shop.get("location") == location_id
    ]
    turn_index = world_state.get("flags", {}).get("turn_index", 0)
    scene = living_world.ensure_scene_record(
        world_state,
        location_id,
        turn_index,
    )
    if isinstance(location_id, str):
        living_world.expire_referents(
            world_state, turn_index, location_id=location_id
        )
    visible = living_world.public_scene_people(people[:4])
    ref_descriptions = [
        ref.get("description")
        for ref in scene.get("referents", [])
        if ref.get("lifecycle") == "presented"
        and isinstance(ref.get("description"), str)
    ]
    import fallen
    bodies = fallen.scene_line(world_state)
    if bodies and not visible:
        return bodies
    if visible:
        response = f"Yakınında {visible} var."
        if bodies:
            response += " " + bodies
        if ref_descriptions:
            response += " " + ref_descriptions[0]
        if shops:
            response += " " + ", ".join(
                living_world.public_shop_name(world_state, shop) for shop in shops[:3]
            ) + " da yakında."
        return response
    if shops:
        return "Yakında " + ", ".join(
            living_world.public_shop_name(world_state, shop) for shop in shops[:3]
        ) + " var."
    if scene.get("kind") == "wilderness":
        return "Çevre sessiz; doğal seslerden başka belirgin bir hareket yok."
    return "Şu an yakınında konuşabileceğin biri görünmüyor; çevredeki hareketliliği izleyebilirsin."

def _promote_scene_referent(referent, location_id):
    world_state = game._session().world_state
    promoted_id = referent.get("promoted_npc_id")
    if referent.get("lifecycle") == "promoted" and isinstance(promoted_id, str):
        return next(
            (
                npc for npc in world_state.get("npcs", [])
                if isinstance(npc, dict) and npc.get("id") == promoted_id
            ),
            None,
        )
    npc = game.create_npc_from_ai({
        "name": living_world.stable_local_name(
            world_state, location_id, "Yolcu"
        ),
        "role": "Yolcu",
        "location": location_id,
        "appearance": "",  # the referent describes what happened, not this person
        "personality": "Kibar, konuşmaya açık ve temkinli.",
        "relationship": "neutral",
    })
    if not npc:
        return None
    living_world.promote_referent(world_state, referent, npc["id"])
    profile = local_dialogue.ensure_personal_profile(npc)
    if profile and isinstance(referent.get("description"), str):
        # This person was in the event; it is what they can talk about.
        profile["current_activity"] = referent["description"]
    return npc

def _adventure_travel_reply(session, destination):
    before = copy.deepcopy(session.world_state)
    # D-123: the same journey owner as any trip - closed roads, venue doors and road time all apply.
    action_result = timed_gameplay.start_travel(session, destination)
    turn_close.advance(session.world_state)
    session.evaluate_quest_events(before, action_result)
    narration = action_result["direct_response"]
    turn_close.record_exchange(session.messages, destination, narration)
    return {
        "messages": session.messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": action_result,
    }
