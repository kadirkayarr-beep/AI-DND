import game
import living_world
import re
import tr_case


def _narration_fact_packet(action_result):
    """Facts the narrator may state. Empty fields are not events."""
    import narration_claims
    result = action_result if isinstance(action_result, dict) else {}
    door = game._venue_door_for(result.get("target_id")) or game._current_door()
    hidden = None
    if result.get("skill") == "Stealth":
        hidden = game._session().world_state.get("flags", {}).get("player_hidden")
    return narration_claims.packet_from_result(
        result, door=door, player_hidden=hidden
    )

def _repair_internal_marks(narration):
    """An id copied from the context reads as the public label; any other mark goes."""
    if not isinstance(narration, str) or not game._INTERNAL_MARK_RE.search(narration):
        return narration
    world_state = game._session().world_state
    labels = {
        npc["id"]: living_world.public_npc_name(npc)
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict) and isinstance(npc.get("id"), str)
    }
    present = game.active_npcs()

    def label_for(match):
        if match.group(4) is not None:
            return match.group(4)
        key = match.group(1) or match.group(3)
        suffix = match.group(2) or ""
        rest = narration[match.end():].lstrip()
        label = labels.get(key)
        if label is None and key and game._PROPOSAL_MARKER_RE.fullmatch(f"[[{key}]]"):
            # "tezgahın arkasındaki [[n1]] sakinlikle": the mark stood for the person.
            if len(present) == 1 and (suffix or rest[:1].islower() or rest[:1] in {",", ";"}):
                label = living_world.public_npc_name(present[0])
            elif suffix:
                return "birinin"
        if label is None:
            return ""
        # "barmen [[npc_003]]" and "[[npc_003]] Hadrik" already say who it is.
        head = game._normalize_turkish_typos(label).split()[-1]
        before = narration[:match.start()].rstrip()
        words_before = game._normalize_turkish_typos(before).split()
        words_after = game._normalize_turkish_typos(rest).split()
        if (words_before and words_before[-1] == head) or (
            words_after and words_after[0].startswith(head)
        ):
            return ""
        at_start = not before or before[-1] in ".!?\n“\""
        shown = label if at_start or not game._is_generic_speaker_label(label) else living_world.turkish_initial_lower(label)
        return shown + suffix

    repaired = game._INTERNAL_MARK_RE.sub(label_for, narration)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"[ \t]+([,.;:!?])", r"\1", repaired)).strip()

def _filter_unaccepted_proposal_mentions(narration, accepted_keys, rejected_names):
    if not isinstance(narration, str):
        return narration
    accepted = set(accepted_keys)
    rejected = [
        name for name in rejected_names
        if isinstance(name, str) and name
    ]
    filtered_paragraphs = []
    for paragraph in re.split(r"(\n\s*\n)", narration):
        if not paragraph or re.fullmatch(r"\n\s*\n", paragraph):
            filtered_paragraphs.append(paragraph)
            continue
        markers = game._PROPOSAL_MARKER_RE.findall(paragraph)
        # With nothing rejected a marker names no proposal at all: the sentence stays.
        if rejected and any(marker not in accepted for marker in markers):
            continue
        if any(
            re.search(
                rf"(?<![\w]){re.escape(name)}(?![\w])",
                paragraph,
                re.IGNORECASE,
            )
            for name in rejected
        ):
            continue
        filtered_paragraphs.append(game._strip_proposal_markers(paragraph))
    return "".join(filtered_paragraphs).strip()

def _drop_absent_counter_sentences(narration):
    """A counter the player is not standing at leaves the prose; the rest stays."""
    world_state = game._session().world_state
    if (
        not isinstance(narration, str)
        or not living_world.on_open_street(world_state)
        or any(game._serves_at_a_counter(npc) for npc in game.active_npcs())
        or any(
            word in game._normalize_turkish_typos(str(feature.get("name", "")))
            for feature in game.location_features(world_state.get("location"))
            if isinstance(feature, dict) for word in game._COUNTER_WORDS
        )
    ):
        return narration
    kept = [
        sentence for sentence in re.split(r"(?<=[.!?…])\s+", narration)
        if not re.search(r"\b(?:tezgah|banko)\w*", game._normalize_turkish_typos(sentence))
    ]
    if not kept or len(kept) == len(re.split(r"(?<=[.!?…])\s+", narration)):
        return narration
    return " ".join(kept)

def _narrator_fact_view(packet, action_result):
    """The prompt copy of the fact packet: an untested lock stays unsaid."""
    if not isinstance(packet, dict) or packet.get("door_locked") is not True:
        return packet
    result = action_result if isinstance(action_result, dict) else {}
    door = game._venue_door_for(result.get("target_id")) or game._current_door()
    if isinstance(door, dict) and game._lock_known_to_player(game._session().world_state, door.get("id")):
        return packet
    return {key: value for key, value in packet.items() if key != "door_locked"}

def create_location_from_proposal(proposal):
    world_state = game._session().world_state
    validated = game.validate_location_proposal(proposal)
    if not validated:
        return None
    next_number = max(1, int(world_state.get("next_location_number", 1)))
    locations = world_state.setdefault("locations", {})
    if len(locations) >= 80:
        world_state.setdefault("flags", {})["location_create_status"] = "limit_reached"
        return None
    while f"location_{next_number:03d}" in locations:
        next_number += 1
    location_id = f"location_{next_number:03d}"
    world_state["next_location_number"] = next_number + 1
    location = {
        "id": location_id,
        **validated,
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
    }
    location.pop("proposal_key", None)
    locations[location_id] = location
    return location

def _current_npc_name():
    world_state = game._session().world_state
    for npc in world_state["npcs"]:
        if npc.get("location") == world_state["location"]:
            return living_world.public_npc_name(npc)
    return None

def _quiet_place_line():
    """One line from the scene record: the place, the hour, the weather. None when no model could say it or none fits."""
    from api import ollama_adapter, opening_narrative
    from api.world_metadata import world_metadata_for_state
    spent = ollama_adapter.usage_summary()
    if spent["failed"] and not spent["calls"]:
        return None
    session = game._session()
    world = session.world_state
    meta = world_metadata_for_state(world, getattr(session, "world_metadata", None))
    return opening_narrative.catalog_line(world, world.get("location"), meta["weather"], meta["time_of_day"],
                                          salt=world.get("flags", {}).get("turn_index", 0))

def _generic_no_change_response():
    line = game._quiet_place_line()
    if line:
        return game._stock(line)
    return game._stock(game._GENERIC_NO_CHANGE_RESPONSES[
        game._variation_index(("no_change",), len(game._GENERIC_NO_CHANGE_RESPONSES))
    ])

def _natural_unresolved_action_response(player_input, action_result=None):
    result = action_result if isinstance(action_result, dict) else {}
    if result.get("action") == "use_item":
        return "Hangi eşyayı nasıl kullanmak istediğini belirtir misin?"
    if result.get("action") == "rest":
        return "Dinlenmek istediğini anladım; nerede dinleneceğini belirtir misin?"
    if result.get("action") in {"dialogue", "query"}:
        return game._stock("Karşındaki kişi sözünü dinliyor, ancak buna ekleyeceği bir şey bulamıyor.")
    return game._stock("Sahnedeki hareketlilik sürüyor; ne yapmak istediğini biraz daha belirgin anlatabilirsin.")

def _unseen_speaker_repaired(narration, world_state, npc_target):
    """A saved person who is not here does not speak here: the one who is here does, by what can be seen of them.

    Their name in the speaking shape outside speech becomes the public label of the person in the scene (the target,
    or the only one here); a self-introduction by that name inside speech is dropped (a line that is only that goes
    with the words that lead into it). Mentions of absent people are left alone. With nobody here nothing is
    rewritten (the check decides).
    """
    if not isinstance(narration, str) or not isinstance(world_state, dict):
        return narration
    here = world_state.get("location")
    people = [npc for npc in world_state.get("npcs", []) if isinstance(npc, dict) and npc.get("location") == here
              and npc.get("name") and npc.get("combat_status") != "dead"]
    speaker = (npc_target if isinstance(npc_target, dict) and npc_target.get("location") == here
               else people[0] if len(people) == 1 else None)
    unseen = game._unseen_registered_names(world_state)
    if speaker is None or not unseen:
        return narration
    label = living_world.public_npc_name(speaker)
    for start, end in reversed(game._unseen_speakers(narration, unseen)):
        opens = not narration[:start].rstrip() or narration[:start].rstrip()[-1] in ".!?…\n\"”'’"
        shown = label if living_world.npc_name_known_to_player(speaker) else (
            living_world.turkish_initial_upper(label) if opens else living_world.turkish_initial_lower(label))
        narration = narration[:start] + shown + narration[end:]
    for span, parts, intros in reversed(game._unseen_self_introductions(narration, unseen)):
        kept = [part for part in parts if part not in intros]
        quote = span.group(0)
        if kept:
            narration = narration[:span.start()] + quote[0] + " ".join(kept) + quote[-1] + narration[span.end():]
            continue
        # Nothing of the line is left: its lead-in ("X gülümser:") goes with it.
        before = narration[:span.start()]
        lead = re.search(r"(?:^|(?<=[.!?…]))[^.!?…]*$", before)
        cut = lead.start() if lead and lead.group(0).rstrip().endswith((":", ",")) else span.start()
        narration = (narration[:cut].rstrip() + " " + narration[span.end():].lstrip()).strip()
    return narration

def should_generate_npcs(player_input, location_changed=False):
    if game.is_player_world_assertion(player_input):
        return False
    text = player_input.casefold()
    if re.search(r"\b(?:ara\w*|bul\w*|sor\w*|tanış\w*|karşılaş\w*)\b", text):
        return True
    return bool(location_changed and not game.active_npcs())

def should_generate_features(player_input, location_changed=False, interaction_mode=None):
    if interaction_mode in {"say", "ask_dm"}:
        return False
    if game.is_player_world_assertion(player_input):
        return False
    if living_world.is_exploratory_structure_question(
        player_input, interaction_mode
    ):
        return True
    current_scene_id = game._session().world_state.get("location")
    if (
        living_world.affirmative_structure_inspection(player_input, interaction_mode)
        and game._scene_detail_parent(current_scene_id, player_input) is not None
    ):
        return True
    if living_world.is_anchored_structure_inquiry(player_input):
        return living_world.affirmative_structure_inspection(
            player_input, interaction_mode
        )
    text = player_input.casefold()
    if re.search(r"(?:etrafı araştır|çevreyi incele|etrafı incel|ipuçlarını araştır|gizli .{0,20} ara)", text):
        return True
    if game._mechanical_outcome(player_input) in ("success", "critical_success") and re.search(
        r"^Skill:\s*(?:Perception|Investigation)", player_input, re.IGNORECASE | re.MULTILINE
    ):
        return True
    return bool(location_changed and not game.location_features())

def _rejected_lore_narration(player_input, npc_target=None):
    """A lore miss on a question stays the rumor line. A social act does not."""
    text = game._normalize_turkish_typos(player_input or "")
    asked = "?" in str(player_input or "") or bool(re.search(
        r"\b(?:nedir|kimdir|nerede|ne kadar|soyler misin|anlatir misin)\b", text
    ))
    if asked:
        return game._unverified_lore_response(player_input, npc_target)
    return game._generic_no_change_response()

def _feature_refs_are_visible(refs):
    """Absent refs are fine; every given id must be a visible feature here."""
    if refs is None:
        return True
    if not isinstance(refs, list) or len(refs) > 8 or not all(isinstance(r, str) for r in refs):
        return False
    world_state = game._session().world_state
    visible = {
        feature.get("id")
        for feature in living_world.visible_features(world_state, world_state.get("location"))
    }
    return all(ref in visible for ref in refs)

def _ensure_venue_window(door):
    """A venue seen from the street has a window once a player looks for it."""
    world_state = game._session().world_state
    venue_id = str(door.get("id", "")).split(":", 1)[-1]
    venue = world_state.get("locations", {}).get(venue_id, {})
    venue_name = venue.get("name") if isinstance(venue, dict) else None
    name = f"{venue_name or 'Binanın'} penceresi" if venue_name else "Binanın penceresi"
    existing = next(
        (
            feature for feature in world_state.get("features", [])
            if isinstance(feature, dict) and feature.get("location") == world_state.get("location")
            and str(feature.get("name", "")).casefold() == name.casefold()
        ),
        None,
    )
    if existing:
        return existing
    return game.create_local_feature({
        "location": world_state.get("location"),
        "name": name[:60],
        "description": "Sokağa bakan küçük bir pencere; kepenkleri içeriden kapatılmış.",
        "kind": "structure",
        "aliases": ["pencere", "kepenk", "kepenkler", "panjur"],
    })

def _bound_on_a_named_word(word, line):
    """A pass on something no record holds yet: the engine saves the thing, and only then are the words bound to it."""
    import bound_text
    import world_threads
    world_state = game._session().world_state
    here = world_state.get("location")
    tag = bound_text.object_tag(word) or bound_text.object_tag(line)  # the reader may name a crack and the line the floor
    if tag is None:
        return None
    key = f"word:{here}:{tag}"
    kept = bound_text.seen(world_state, key)
    if kept is None:
        world_threads.ensure(world_state)
        choice = bound_text.choose_detail(world_state, key, bound_text.place_tags(world_state, here), tag)
        name = next(iter(bound_text.rules()["object_words"][tag])) if bound_text.object_tag(word) is None else game._clean_world_text(word, 60)
        feature = choice and game.create_local_feature({"location": here, "description": choice["text"], "kind": "detail",
                                                   "name": f"{tr_case.upper_first(name)}", "aliases": [name]})
        if not isinstance(feature, dict):
            return None
        bound_text.keep(world_state, key, choice, feature_id=feature.get("id"))
        bound_text.keep(world_state, f"feature:{feature.get('id')}", choice)
        kept = bound_text.seen(world_state, key)
    feature = next((row for row in world_state.get("features", [])
                    if isinstance(row, dict) and row.get("id") == kept.get("feature_id")), None)
    return {"target_kind": "feature", "target_id": kept.get("feature_id"),
            "target_name": feature.get("name") if feature else None, "found": True, "text": kept["text"]}

def _found_on_a_pass(line=""):
    """A pass with no saved fact to show: the reading proposed what is there, and Python keeps it as a real detail."""
    text, word = getattr(game._session(), "_front_found", None) or ("", "")
    bound = game._bound_on_a_named_word(word, line)
    if bound is not None:
        return bound
    text = game._clean_world_text(text, 120)
    if not text or game._finding_says_too_much(text):
        return None
    world_state = game._session().world_state
    if any(isinstance(row, dict) and row.get("description") == text and row.get("location") == world_state.get("location")
           for row in world_state.get("features", [])):
        return None  # the small model said the last finding again: that is no new finding
    name = game._clean_world_text(word, 60) or "Gözüne çarpan ayrıntı"
    feature = game.create_local_feature({"location": game._session().world_state.get("location"), "description": text,
                                    "name": f"{tr_case.upper_first(name)}", "aliases": [name], "kind": "detail"})
    if not isinstance(feature, dict):
        return None
    return {"target_kind": "feature", "target_id": feature.get("id"), "target_name": feature.get("name"),
            "found": True, "text": text}

def _inspection_findings(player_input, outcome, *, rolled=True):
    """Concrete, target-bound result of a look or search (LR00-P2).

    Only saved facts are revealed. A failed or empty look is stated as limited
    to this attempt ("bu bakışla"), never as proof that nothing is there.
    rolled=False is a look with no check: what the reading proposed takes a pass.
    """
    import bound_text
    world_state = game._session().world_state
    # Words inside quotes are only words, never the thing being looked at.
    text = game._normalize_turkish_typos(living_world._text_outside_quotes(str(player_input)))
    success = outcome in ("success", "critical_success")
    proposed = rolled and success
    a_reading_ran = proposed and getattr(game._session(), "_front_found", None) is not None
    door = game._current_door()
    if isinstance(door, dict) and game._WINDOW_WORDS.search(text):
        window = game._ensure_venue_window(door)
        if isinstance(window, dict):
            if success:
                line = (
                    f"{window['name']}: {window.get('description', '')} Kepenklerin aralığından "
                    "içerisi loş ve sessiz görünüyor; bu açıdan fazlası seçilmiyor."
                )
            else:
                line = f"{window['name']}: kepenkler kapalı; aralıktan bu açıdan bir şey seçilmiyor."
            return {"target_kind": "feature", "target_id": window.get("id"),
                    "target_name": window["name"], "found": success, "text": line}
    if isinstance(door, dict) and (game._LOCK_WORDS.search(text) or re.search(r"\bkapi\w*\b", text)):
        state = "kilitli" if door.get("locked") else ("açık" if door.get("open") else "kapalı")
        if door.get("broken"):
            detail = "Kilit yerinden oynamış; kırıldığı belli."
        elif door.get("locked"):
            detail = "Kilit sağlam ve yerinde; zorlandığına dair bir iz görmüyorsun."
        else:
            detail = "Kilit açık duruyor."
        line = (f"{door.get('name', 'Kapı')} {state}. {detail}" if success
                else f"{door.get('name', 'Kapı')} {state}; bu bakışla kilidin ayrıntısını seçemiyorsun.")
        bound = bound_text.detail_of(world_state, f"door:{door.get('id')}", "mentese" if "mentese" in text else "kapi", proposed)
        line = f"{line} {bound}" if bound else line
        return {"target_kind": "door", "target_id": door.get("id"),
                "target_name": door.get("name"), "found": success, "state": state, "text": line}
    here = world_state.get("location")
    for feature in world_state.get("features", []):
        if (
            not isinstance(feature, dict) or feature.get("location") != here
            or feature.get("hidden") is True
            # A building's own detail is only reached through that building.
            or feature.get("parent_id") is not None
        ):
            continue
        labels = [feature.get("name", ""), *(feature.get("aliases") or [])]
        if any(isinstance(label, str) and label.strip() and game._entity_reference_in_text(label, text)
               for label in labels):
            recorded = game._normalize_turkish_typos(" ".join(
                str(part) for part in (
                    feature.get("name", ""), feature.get("description") or "", *labels
                )
            ))
            named_absence = []
            for word in re.findall(r"[a-z0-9]+", text):
                if len(word) < 6 or word.endswith(("yorum", "iyorum", "uyorum", "sunuz")):
                    continue
                stem = re.sub(r"(?:da|de|ta|te|ya|ye|yi|yu|na|ne|nin|nun|in|un|i|u)$", "", word)
                if stem in recorded or word in recorded:
                    continue
                named_absence.append(word)
            bound = bound_text.detail_of(world_state, f"feature:{feature.get('id')}", bound_text.object_tag(*labels), proposed)
            if bound is not None:
                shown = bound if bound == feature.get("description") else f"{feature.get('description') or ''} {bound}".strip()
                return {"target_kind": "feature", "target_id": feature.get("id"),
                        "target_name": feature.get("name"), "found": True, "text": f"{feature['name']}: {shown}"}
            if feature.get("kind") == "detail":
                named_absence = []  # already found once: a second look sees that, not one more thing
            found_now = game._found_on_a_pass(text) if proposed and named_absence else None
            if found_now is not None:
                return found_now
            found = success and not named_absence
            # A pass the reading had nothing to add to still shows what is saved, and no prose invents the rest.
            line = (f"{feature['name']}: {feature.get('description') or 'olağan görünüyor.'}" if found or a_reading_ran
                    else f"{feature['name']} üzerinde bu bakışla yeni bir ayrıntı seçemiyorsun.")
            return {"target_kind": "feature", "target_id": feature.get("id"),
                    "target_name": feature.get("name"), "found": found, "text": line}
    if game._TRACK_WORDS.search(text):
        bound = bound_text.detail_of(world_state, f"tracks:{here}", "ayak_izi", proposed)
        if bound is not None:
            return {"target_kind": "tracks", "target_id": None, "target_name": "izler", "found": True, "text": bound}
        found = game._found_on_a_pass(text) if proposed else None
        if found is not None:
            return found
        line = ("İzleri dikkatle inceliyorsun: kalabalık bir zeminde beklendiği gibi birbirine "
                "karışmışlar; belirli birinin izini ayırmak bu haliyle mümkün değil." if success
                else "İzler birbirine karışmış; bu bakışla bir şey çıkaramıyorsun.")
        return {"target_kind": "tracks", "target_id": None, "target_name": "izler", "found": False, "text": line}
    # Only a successful search for a detail the scene lacks is a Python miss;
    # a failed roll keeps its normal (guarded) failure narration.
    if success and re.search(r"\b(?:incel|arastir)\w*", text):
        if re.search(r"\b(?:etraf|cevre)\w*", text):
            # The surroundings are the thing looked at, so the answer is what is there.
            return {"target_kind": "feature", "target_id": None, "target_name": None, "found": False,
                    "text": game._scene_look_text(world_state.get("location"))}
        return (game._found_on_a_pass(text) if proposed else None) or {
            "target_kind": "feature",
            "target_id": None,
            "target_name": None,
            "found": False,
            "text": game._stock("Bu bakışla adlandırdığın ayrıntı seçilmiyor."),
        }
    return game._found_on_a_pass(text) if proposed else None

def _repair_attributed_speech(payload, decision):
    """Remove the trigger only from the source field that contains it."""
    if not isinstance(payload, dict):
        return None
    if (
        decision.get("reason_code") in {
            "UNREGISTERED_NAMED_ENTITY", "PLAYER_NAME_IN_NARRATION",
            "UNVERIFIED_LORE_CLAIM",
        }
        and decision.get("source_field") == "stage_direction"
    ):
        # This field marker is produced only for exact, server-bound speech.
        # Discard the optional scene description, then revalidate every word
        # of the retained answer. Do not repair a narrator or a speaker ID.
        return {**payload, "stage_direction": ""}
    trigger = str(decision.get("trigger_span") or "").casefold()
    if not trigger:
        return None
    repaired = dict(payload)
    changed = False
    for field in ("spoken_text", "stage_direction"):
        value = repaired.get(field)
        if isinstance(value, str) and trigger in value.casefold():
            field_repair = game._remove_trigger_sentence(value, decision)
            if field_repair is None:
                return None
            repaired[field] = field_repair
            changed = True
    return repaired if changed else None

def _narration_contradicts_supported_name_memory(npc, player_input, narration):
    """Catch a direct denial of a name already present in speaker-attributed memory."""
    if not npc or not game.is_npc_historical_claim(player_input):
        return None
    normalized_input = game._normalize_turkish_typos(str(player_input).casefold())
    if not re.search(r"\b(?:ad|isim)\w*\b", normalized_input):
        return None
    if not game.npc_memory_supports_claim(npc, player_input):
        return None
    normalized_narration = game._normalize_turkish_typos(str(narration).casefold())
    contradiction = re.search(
        r"\b(?:adini|ismini)\b.{0,28}"
        r"\b(?:soylemen|soylemedigin|vermen|vermedigin)\b"
        r".{0,24}\b(?:gerek\w*|lazim\w*|soylemedin|vermedin)\b|"
        r"\b(?:bana|bize)\b.{0,20}\b(?:adini|ismini)\b.{0,20}"
        r"\b(?:soylemedin|vermedin)\b",
        normalized_narration,
    )
    return contradiction.group(0) if contradiction else None
