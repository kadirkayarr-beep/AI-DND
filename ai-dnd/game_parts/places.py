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

def _normalize_ground_items():
    """Migrate legacy ground_items list to ground_items_by_location dict."""
    # Ensure ground_items_by_location exists (safe init for legacy state)
    world_state = game._session().world_state
    if not isinstance(world_state.get("ground_items_by_location"), dict):
        world_state["ground_items_by_location"] = {}
    # If already normalized (dict exists and list is empty), nothing to do
    if not world_state.get("ground_items"):
        return
    # If we have legacy list items but no dict yet, migrate them to current location
    legacy_items = world_state.get("ground_items", [])
    if legacy_items:
        current_loc = world_state.get("location", "tavern")
        if current_loc not in world_state["ground_items_by_location"]:
            world_state["ground_items_by_location"][current_loc] = []
        for item in legacy_items:
            if item not in world_state["ground_items_by_location"][current_loc]:
                world_state["ground_items_by_location"][current_loc].append(item)
        # Clear legacy list
        world_state["ground_items"] = []

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
            world_state["inventory"].remove(sword)
            held_weapon.release_hand(world_state, sword)
            game._normalize_ground_items()
            current_loc = world_state.get("location", "tavern")
            loc_items = world_state["ground_items_by_location"].setdefault(current_loc, [])
            if "Kılıç" not in loc_items:
                loc_items.append("Kılıç")
            return "Python durumu: Kılıç envanterden yere taşındı."

    if any(isinstance(i, dict) for _, items in equipment_economy.containers(world_state) for i in items):
        return equipment_economy.legacy_sword_move(game._session(), dropping)

    game._normalize_ground_items()
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
