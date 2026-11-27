import game
import interaction_adventure
import json
import living_world
import local_dialogue
import re
import scheduled_events


def _empty_lore_authority_context():
    return {
        "authority_boundary": {
            "official_lore_is_not_campaign_history": True,
            "campaign_state_is_not_official_canon": True,
            "procedural_content_never_promotes_to_official": True,
            "narrative_texture_is_not_world_fact": True,
            "unknown_or_unloaded_must_remain_unknown": True,
        },
        "sections": {
            "official_forgotten_realms_lore": [],
            "campaign_canon": [],
            "player_known_lore": [],
            "npc_known_lore": [],
            "procedural_local_content": [],
            "unknown_or_unloaded": [],
        },
    }

def _prepare_lore_authority_context(lore_context):
    context = game._empty_lore_authority_context() if lore_context is None else lore_context
    if not isinstance(context, dict):
        raise ValueError("Lore Authority context must be an object.")
    boundary = context.get("authority_boundary")
    sections = context.get("sections")
    expected_boundaries = game._empty_lore_authority_context()["authority_boundary"]
    if (
        not isinstance(boundary, dict)
        or any(boundary.get(key) is not True for key in expected_boundaries)
        or not isinstance(sections, dict)
    ):
        raise ValueError("Lore Authority context is missing required authority boundaries.")
    for name in game._empty_lore_authority_context()["sections"]:
        if not isinstance(sections.get(name), list):
            raise ValueError("Lore Authority context has an invalid section.")
    encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 12 * 1024:
        raise ValueError("Lore Authority context exceeds the supported size.")
    return context

def _is_registered_lore_name(candidate, known_phrases, known_tokens):
    normalized = game._lore_guard_text(candidate)
    if not normalized:
        return True
    if normalized in known_phrases or normalized in known_tokens:
        return True
    words = normalized.split()
    while words and words[0] in {
        "king", "queen", "monarch", "emperor", "empress", "lord", "lady",
        "city", "town", "village", "river", "mountain", "region", "kingdom",
        "ruler", "the", "of", "kral", "kraliçe", "hükümdar", "şehir",
        "kasaba", "nehir", "dağ", "bölge", "krallık",
    }:
        words.pop(0)
    stripped = " ".join(words)
    if stripped in known_phrases or stripped in known_tokens:
        return True
    return bool(words) and all(
        word in known_tokens or word in known_phrases for word in words
    )

def _has_unregistered_narrative_entity(sentence, known_phrases, known_tokens):
    normalized_sentence = game._lore_guard_text(sentence)
    contains_dr_year = bool(
        re.search(r"\b(?:dr\s*\d{4}|\d{4}\s*dr)\b", normalized_sentence)
    )

    def is_date_marker(candidate):
        if not contains_dr_year:
            return False
        normalized_candidate = game._lore_guard_text(candidate).strip()
        return normalized_candidate == "dr" or bool(
            re.fullmatch(r"(?:dr\s*)?\d{4}(?:\s*dr)?", normalized_candidate)
        )

    for match in game._LORE_ENTITY_TITLE_RE.finditer(sentence):
        if is_date_marker(match.group(0)):
            continue
        if not game._is_registered_lore_name(
            match.group(0), known_phrases, known_tokens
        ):
            return True

    for match in game._LORE_PROPER_NAME_RE.finditer(sentence):
        candidate = match.group(0)
        if is_date_marker(candidate):
            continue
        if game._is_registered_lore_name(candidate, known_phrases, known_tokens):
            continue
        prefix = sentence[:match.start()]
        # A verified speaker label is not part of the spoken sentence. Without
        # this boundary, ordinary capitalized words ("Evet", "Yolcuyum") are
        # mistaken for new entities solely because dialogue has a label.
        speaker = re.match(r'^\s*([^:«»“”"\n]{1,160}):\s*[“"«]', prefix)
        if speaker and (
            game._is_registered_lore_name(speaker.group(1), known_phrases, known_tokens)
            or game._is_generic_speaker_label(speaker.group(1))
        ):
            prefix = prefix[speaker.end():]
        sentence_prefix = re.split(r"[.!?]\s*", prefix)[-1]
        at_sentence_start = not sentence_prefix.strip(
            " \t\r\n\"'“‘([{"
        ) or bool(re.search(r"[:]\s*['\"“‘]\s*$", prefix))  # speech opened after a colon
        if at_sentence_start:
            first_word = game._lore_guard_text(candidate.split()[0])
            if first_word in game._LORE_SENTENCE_START_WORDS:
                remaining = candidate.split()[1:]
                if not remaining:
                    continue
                candidate = " ".join(remaining)
                if game._is_registered_lore_name(
                    candidate, known_phrases, known_tokens
                ):
                    continue
            suffix = sentence[match.end():match.end() + 72]
            if not game._LORE_ENTITY_FOLLOWING_CUE_RE.search(suffix):
                continue
        return True
    return False

def _stage_within_the_street(stage, world_state):
    """On the street a counter, room or table nobody recorded leaves the stage direction."""
    if not living_world.on_open_street(world_state):
        return stage
    here = world_state.get("location")
    people = [npc for npc in scheduled_events.visible_npcs(world_state) if npc.get("location") == here]
    place = world_state.get("locations", {}).get(here)
    recorded = [str(place.get("description") or "")] if isinstance(place, dict) else []
    for feature in world_state.get("features", []):
        if isinstance(feature, dict) and feature.get("location") == here:
            recorded.extend(str(feature.get(key) or "") for key in ("name", "description"))
            recorded.extend(str(alias) for alias in feature.get("aliases", []) or [])
    for npc in people:
        recorded.extend(str(npc.get(key) or "") for key in ("role", "appearance"))
    recorded = game._normalize_turkish_typos(" ".join(recorded))
    stall_here = any(game._serves_at_a_counter(npc) for npc in people)

    def fits(sentence):
        for match in game._INDOOR_DETAIL.finditer(game._normalize_turkish_typos(sentence)):
            word = match.group(1) or match.group(2)
            if not re.search(rf"\b{word}", recorded) and not (stall_here and word in ("tezgah", "banko")):
                return False
        return True

    return " ".join(
        sentence for sentence in re.split(r"(?<=[.!?…])\s+", stage) if fits(sentence)
    )

def _shown_stage_direction(stage, world_state):
    """Drop a stage direction that puts an unrecorded object in someone's hand or leaves the place."""
    if not isinstance(stage, str) or not stage.strip():
        return ""
    if game._unregistered_held_object(world_state, stage):
        return ""
    return game._stage_within_the_street(stage.strip(), world_state)

def _unverified_lore_response(player_input, npc_target=None):
    text = local_dialogue.normalize_text(player_input)
    speaking_npc = npc_target if isinstance(npc_target, dict) else None
    if game._ASKS_DISTANCE.search(text):
        if speaking_npc:
            return interaction_adventure.immersive_unknown(speaking_npc, player_input)
        return game._UNVERIFIED_DISTANCE_RESPONSE
    if re.search(
        r"\b(?:kralice|kral|hukumdar|yonetici|lord|king|queen|ruler)\w*\b",
        text,
    ):
        if speaking_npc and (
            game._entity_reference_in_text(speaking_npc.get("name", ""), player_input)
            or game._entity_reference_in_text(speaking_npc.get("role", ""), player_input)
        ):
            return (
                f'{living_world.public_npc_name(speaking_npc)}, “Bu konuda kesin bir şey '
                'söyleyemem; yanlış yönlendirmek istemem,” der.'
            )
        if speaking_npc:
            return interaction_adventure.immersive_unknown(speaking_npc, player_input)
        return game._UNVERIFIED_RULER_RESPONSE
    if speaking_npc:
        return interaction_adventure.immersive_unknown(speaking_npc, player_input)
    return game._UNVERIFIED_LORE_RESPONSE

def _names_the_district_here(word, world_state):
    """"Bu mahalle" in a district the campaign accepted is the place, not invented damage to one."""
    place = world_state.get("locations", {}).get(world_state.get("location"), {})
    return (
        isinstance(place, dict) and place.get("type") == "district"
        and bool(re.match(r"(?:mahalle|semt)", game._lore_guard_text(word)))
    )

def _narration_has_unsupported_lore_claim(
    narration, lore_claims, lore_context, world_state
):
    if not isinstance(narration, str) or not narration.strip():
        return False
    facts = game._lore_fact_records(lore_context, lore_claims)
    evidence_parts = []
    for fact in facts:
        evidence_parts.extend(
            str(fact.get(key, ""))
            for key in (
                "fact_id", "subject_id", "predicate", "object_id_or_value",
                "notes",
            )
        )
    evidence = game._lore_guard_text(" ".join(evidence_parts))
    names_by_id, known_phrases, known_tokens = game._lore_entity_names(
        lore_context, world_state
    )
    for fact in facts:
        for field in ("subject_id", "object_id_or_value"):
            value = fact.get(field)
            if isinstance(value, str) and value in names_by_id:
                for name in names_by_id[value]:
                    evidence_parts.append(name)
    evidence = game._lore_guard_text(" ".join(evidence_parts))
    cited_relations = {
        (
            fact.get("subject_id"),
            fact.get("object_id_or_value"),
            game._lore_guard_text(" ".join(
                str(fact.get(key, ""))
                for key in ("predicate", "object_id_or_value", "notes")
            )),
        )
        for fact in facts
    }

    for sentence in re.split(r"(?<=[.!?。！？])\s+", narration):
        if game._has_unregistered_narrative_entity(
            sentence, known_phrases, known_tokens
        ):
            return True
        normalized_sentence = game._lore_guard_text(sentence)
        for pattern, _reason in game._LORE_UNSUPPORTED_DETAIL_PATTERNS:
            for match in pattern.finditer(sentence):
                if (
                    _reason == "craft_specialization"
                    and game._scene_has_registered_craft_role(
                        match.group(0), world_state
                    )
                ):
                    continue
                if (
                    _reason == "unsupported_urban_damage_detail"
                    and game._names_the_district_here(match.group(0), world_state)
                ):
                    continue
                if game._lore_guard_text(match.group(0)) not in evidence:
                    return True

        for match in game._LORE_RULER_TITLE_RE.finditer(sentence):
            title = game._lore_guard_text(match.group(0))
            prior = game._lore_guard_text(sentence[max(0, match.start() - 18):match.start()])
            negated = bool(re.search(r"\b(?:not|isnt|is not|değil|degil)\b", prior))
            if title in {"kingdom", "krallik"} and negated and "not a realm" in evidence:
                continue
            if title not in evidence:
                return True

        if game._LORE_ENTITY_RELATION_RE.search(sentence):
            mentioned_ids = {
                entity_id
                for entity_id, names in names_by_id.items()
                if any(
                    re.search(
                        rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])",
                        normalized_sentence,
                    )
                    for name in names
                )
            }
            if len(mentioned_ids) >= 2:
                linked = any(
                    (left in mentioned_ids and right in mentioned_ids)
                    or (
                        isinstance(right, str)
                        and right in mentioned_ids
                        and left in mentioned_ids
                    )
                    for left, right, _ in cited_relations
                )
                has_outcome_evidence = any(
                    any(
                        token in normalized_sentence
                        for token in relation_text.split()
                        if len(token) >= 5
                    )
                    for _, _, relation_text in cited_relations
                )
                if not linked or not has_outcome_evidence:
                    return True
    return False

def _repair_unsupported_lore_narration(narration, lore_claims, lore_context, world_state):
    """Drop only the unsupported sentences; None when nothing usable remains."""
    sentences = game._split_sentences_keep_speech(narration)
    kept = [
        sentence for sentence in sentences
        if not game._narration_has_unsupported_lore_claim(
            sentence, lore_claims, lore_context, world_state
        )
    ]
    repaired = game._trim_dangling_quote(" ".join(kept).strip())
    # A removed first sentence can leave an unbalanced quote and no speaker.
    if not repaired or repaired.count("“") != repaired.count("”"):
        return None
    return repaired

def _scene_has_registered_craft_role(term, world_state):
    """Allow a craft mention only when a present, saved NPC has that role."""
    normalized_term = game._lore_guard_text(term)
    if not normalized_term or not isinstance(world_state, dict):
        return False
    location_id = world_state.get("location")
    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict) or npc.get("location") != location_id:
            continue
        if game._lore_guard_text(npc.get("role", "")) == normalized_term:
            return True
    return False

def _supported_lore_question_response(player_input, lore_context, world_state):
    """Answer only from loaded, structured facts matched to a query intent."""
    if not isinstance(player_input, str) or not player_input.strip():
        return None
    is_overview_request = bool(re.search(
        r"\b(?:describe\w*|overview|summary|tell me(?: more)? about|"
        r"what is|what are|what about|what is known|what do you know|"
        r"genel bilgi|tasvir|hakkinda|anlat)\b",
        game._lore_guard_text(player_input),
        re.IGNORECASE,
    ))
    if not is_overview_request and "?" not in player_input and not re.match(
        r"^\s*(?:who|what|where|when|why|how|which|whose|"
        r"is|are|was|were|does|do|did|can|could|should|would|will|"
        r"kim|ne|nerede|hangi|neden|nasıl|nasil|mi|mı|mu|mü)\b",
        player_input,
        re.IGNORECASE,
    ):
        return None

    normalized_input = game._lore_guard_text(player_input)
    diagnostics = lore_context.get("diagnostics", {}) if isinstance(lore_context, dict) else {}
    query_intents = {
        intent
        for intent in diagnostics.get("query_intents", [])
        if isinstance(intent, str)
    } if isinstance(diagnostics, dict) else set()
    if is_overview_request:
        query_intents.add("overview")
    if re.search(
        r"\b(?:status|condition\w*|state|situation|rebuild\w*|"
        r"reconstruct\w*|reconstruction|under construction|durum\w*|"
        r"kosul\w*|yeniden insa)\b",
        normalized_input,
    ):
        query_intents.add("current_status")
    if re.search(
        r"\b(?:continu\w*|connect\w*|becom\w*|turn\w*|lead\w*|"
        r"join\w*|extend\w*|devam\w*|baglan\w*|donus\w*)\b",
        normalized_input,
    ):
        query_intents.add("route_continuation")
    names_by_id, known_phrases, known_tokens = game._lore_entity_names(
        lore_context, world_state
    )
    if game._has_unregistered_narrative_entity(
        player_input,
        known_phrases,
        known_tokens,
    ):
        return None
    mentioned_ids = {
        entity_id
        for entity_id, names in names_by_id.items()
        if any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])",
                normalized_input,
            )
            for name in names
        )
    }
    if (
        "current_ruler" in query_intents
        and re.search(
            r"\b(?:this\s+(?:city|town|settlement)|current\s+"
            r"(?:city|town|settlement)|bu\s+(?:sehir|sehr|kent|yer)\w*|"
            r"burada\w*|here)\b",
            normalized_input,
        )
    ):
        current_location_entity_id = diagnostics.get(
            "current_location_entity_id"
        )
        if (
            isinstance(current_location_entity_id, str)
            and current_location_entity_id in names_by_id
        ):
            mentioned_ids.add(current_location_entity_id)
    if not mentioned_ids:
        return None

    sections = lore_context.get("sections", {}) if isinstance(lore_context, dict) else {}
    facts = []
    for section_name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
    ):
        items = sections.get(section_name, []) if isinstance(sections, dict) else []
        facts.extend(item for item in items if isinstance(item, dict))
    canonical_names = {
        entity["entity_id"]: entity["canonical_name"]
        for entity in sections.get("verified_entities", [])
        if isinstance(entity, dict)
        and isinstance(entity.get("entity_id"), str)
        and isinstance(entity.get("canonical_name"), str)
        and entity["canonical_name"].strip()
    } if isinstance(sections, dict) else {}
    if isinstance(world_state, dict):
        for location_id, location in world_state.get("locations", {}).items():
            if isinstance(location, dict) and isinstance(location.get("name"), str):
                canonical_names.setdefault(location_id, location["name"])
        for collection in ("npcs", "features"):
            for entity in world_state.get(collection, []):
                if not isinstance(entity, dict) or not isinstance(entity.get("name"), str):
                    continue
                entity_id = entity.get("id") or entity.get("feature_id")
                if isinstance(entity_id, str):
                    canonical_names.setdefault(entity_id, entity["name"])

    def entity_name(entity_id):
        if isinstance(entity_id, str) and entity_id in canonical_names:
            return canonical_names[entity_id]
        names = names_by_id.get(entity_id, set())
        return min(names, key=lambda name: (len(name), name)) if names else None

    is_turkish = bool(
        re.search(r"[çğıöşüÇĞİÖŞÜ]", player_input)
        or re.search(
            r"\b(?:mi|mu|olarak|devam|yonet|hukumdar|gercekten|"
            r"yeniden|insaat)\b",
            normalized_input,
        )
    )

    overview_priority = {
        "known_as": 0,
        "known_for": 1,
        "current_status": 2,
        "current_lord_id": 3,
        "current_lord": 3,
        "political_form": 4,
        "member_of": 5,
        "distinct_from_region": 5,
        "route_role": 5,
        "safety_status": 6,
        "continues_as": 7,
    }

    def display_fact_value(value):
        if isinstance(value, str):
            verified_name = entity_name(value)
            if verified_name:
                return verified_name
            if value in canonical_names:
                return canonical_names[value]
            if ":" in value:
                return None
            return value.replace("_", " ")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return None

    def loaded_year_mentioned():
        match = re.search(r"\b(\d{4})\b", normalized_input)
        if not match:
            return None
        for year_fact in facts:
            if (
                year_fact.get("predicate") in {"current_dr_year", "present_year_dr"}
                and str(year_fact.get("object_id_or_value")) == match.group(1)
            ):
                return match.group(1)
        return None

    def render_loaded_fact(fact, include_year=False):
        predicate = str(fact.get("predicate", "")).casefold()
        subject_name = entity_name(fact.get("subject_id"))
        value = fact.get("object_id_or_value")
        value_name = display_fact_value(value)
        if not subject_name or not value_name:
            return None
        if predicate == "safety_status":
            if fact.get("fact_id") == "fr:fact:high_road_safety_restored" and value == "renewed":
                return f"{subject_name} yeniden güvenle yolculuk edilebilir durumdadır." if is_turkish else f"{subject_name} is again safe to travel."
        if predicate in {"current_status"} or predicate.endswith("_status"):
            if is_turkish:
                if value in {"rebuilding", "under_reconstruction"}:
                    sentence = f"{subject_name} yeniden inşa ediliyor."
                else:
                    sentence = f"{subject_name} için güncel durum: {value_name}."
                year = loaded_year_mentioned() if include_year else None
                return f"{year} DR itibarıyla {sentence}" if year else sentence
            if predicate == "current_status" and value == "rebuilding":
                sentence = f"{subject_name} is rebuilding."
            else:
                sentence = f"{subject_name}'s status is {value_name}."
            year = loaded_year_mentioned() if include_year else None
            return f"As of {year} DR, {sentence}" if year else sentence
        if predicate == "known_as":
            return f"{subject_name} is known as {value_name}."
        if predicate == "known_for":
            return f"{subject_name} is known for {value_name}."
        if predicate in {"current_lord_id", "current_lord"}:
            return f"{value_name} is the current Lord of {subject_name}."
        if predicate == "member_of":
            if is_turkish:
                return f"{subject_name}, {value_name} üyesidir."
            alliance_name = (
                value_name
                if value_name.casefold().startswith("the ")
                else f"the {value_name}"
            )
            return f"{subject_name} is a member of {alliance_name}."
        if predicate == "distinct_from_region":
            if is_turkish:
                return f"{subject_name} ve {value_name}, kitabın bölge sınıflandırmasında ayrı bölgelerdir."
            region_name = (
                value_name
                if value_name.casefold().startswith("the ")
                else f"the {value_name}"
            )
            return f"{subject_name} is distinct from {region_name} in the book’s regional grouping."
        if predicate == "purpose":
            if is_turkish:
                purpose = (
                    "yerleşimlerin güvenliği ve refahı"
                    if value == "settlement_safety_and_prosperity"
                    else value_name
                )
                return f"{subject_name} için belirtilen amaç {purpose}."
            organization_name = (
                subject_name
                if subject_name.casefold().startswith("the ")
                else f"the {subject_name}"
            )
            return (
                f"The stated purpose of {organization_name} includes "
                f"{value_name}."
            )
        if predicate == "continues_as":
            if is_turkish:
                return f"{subject_name}, {value_name} olarak devam eder."
            return f"{subject_name} continues as {value_name}."
        if predicate == "route_role":
            if value == "major_northern_trade_route":
                return f"{subject_name}, Kuzey’in başlıca ticaret yollarından biridir." if is_turkish else f"{subject_name} is one of the North’s major trade routes."
            return f"{subject_name} is a {value_name}."
        if predicate == "safety_status":
            return f"{subject_name}'s safety status is {value_name}."
        if predicate == "political_form":
            if value == "settlement_coalition_not_a_realm":
                return f"{subject_name} is a settlement coalition, not a realm."
            return f"{subject_name}'s political form is {value_name}."
        return None

    if "current_status" in query_intents:
        status_facts = [
            fact
            for fact in facts
            if (
                str(fact.get("predicate", "")).casefold() == "current_status"
                or str(fact.get("predicate", "")).casefold().endswith("_status")
            )
            and fact.get("subject_id") in mentioned_ids
        ]
        status_facts.sort(
            key=lambda fact: (
                0 if fact.get("predicate") == "current_status" else 1,
                str(fact.get("fact_id", "")),
            )
        )
        for fact in status_facts:
            response = render_loaded_fact(fact, include_year=True)
            if response:
                return response

    if "route_continuation" in query_intents:
        route_facts = [
            fact
            for fact in facts
            if fact.get("predicate") in {
                "continues_as",
                "connects_to",
                "leads_to",
                "joins",
                "turns_into",
                "extends_to",
            }
            and fact.get("subject_id") in mentioned_ids
            and (
                len(mentioned_ids) <= 1
                or mentioned_ids.issubset(
                    {
                        fact.get("subject_id"),
                        fact.get("object_id_or_value"),
                    }
                )
            )
        ]
        for fact in route_facts:
            notes = fact.get("notes")
            if isinstance(notes, str) and notes.strip():
                return notes.strip()
            response = render_loaded_fact(fact)
            if response:
                return response

    distance_question = bool(re.search(
        r"\b(?:distance|how far|how many\s+(?:miles?|kilometers?|"
        r"kilometres?|meters?|metres?)|miles?|kilometers?|"
        r"kilometres?|meters?|metres?|kac mil|kac kilometre|"
        r"ne kadar uzak|uzaklik)\b",
        normalized_input,
    ))
    lord_question = bool(re.search(
        r"\b(?:rule\w*|lord\w*|leader\w*|lead\w*|role\w*|position\w*|"
        r"hukumdar\w*|yonet\w*)\b",
        normalized_input,
    ))
    route_continuation_question = bool(re.search(
        r"\b(?:contin\w*|devam\w*)\b",
        normalized_input,
    ))
    political_form_question = bool(re.search(
        r"\b(?:realm|kingdom|country|nation|krallik|ulke|devlet)\b",
        normalized_input,
    ))
    membership_question = bool(re.search(
        r"\b(?:member(?:ship)?|belong\w*|part of|üye\w*|uye\w*)\b",
        normalized_input,
    ))
    purpose_question = bool(re.search(
        r"\b(?:purpose|goal\w*|aim\w*|amaç\w*|amac\w*|hedef\w*)\b",
        normalized_input,
    ))
    distinct_relation_question = bool(re.search(
        r"\b(?:same|identical|distinct|different|aynı|ayni|farklı|farkli)\b",
        normalized_input,
    ))
    rebuilding_question = bool(re.search(
        r"\b(?:rebuild\w*|reconstruction|yeniden insa|insaat)\b",
        normalized_input,
    ))

    if membership_question or purpose_question:
        membership_statements = []
        purpose_statements = []
        for fact in facts:
            predicate = str(fact.get("predicate", "")).casefold()
            if (
                membership_question
                and predicate == "member_of"
                and fact.get("subject_id") in mentioned_ids
                and fact.get("object_id_or_value") in mentioned_ids
            ):
                statement = render_loaded_fact(fact)
                if statement and statement not in membership_statements:
                    membership_statements.append(statement)
            if (
                purpose_question
                and predicate == "purpose"
                and fact.get("subject_id") in mentioned_ids
            ):
                statement = render_loaded_fact(fact)
                if statement and statement not in purpose_statements:
                    purpose_statements.append(statement)
        focused_statements = membership_statements + purpose_statements
        if focused_statements:
            return " ".join(focused_statements)

    if distinct_relation_question:
        for fact in facts:
            if (
                fact.get("predicate") == "distinct_from_region"
                and fact.get("subject_id") in mentioned_ids
                and fact.get("object_id_or_value") in mentioned_ids
            ):
                response = render_loaded_fact(fact)
                if response:
                    return response

    for fact in facts:
        subject_id = fact.get("subject_id")
        object_id = fact.get("object_id_or_value")
        predicate = str(fact.get("predicate", ""))
        notes = fact.get("notes")
        notes = notes.strip() if isinstance(notes, str) else ""
        if (
            predicate in {"current_lord_id", "current_lord"}
            and lord_question
            and subject_id in mentioned_ids
            and (
                object_id in mentioned_ids
                or re.search(r"\b(?:who|whose|kim(?:dir)?)\b", normalized_input)
            )
        ):
            if notes:
                return notes
            subject_name = entity_name(subject_id)
            object_name = entity_name(object_id)
            if (
                object_name is None
                and predicate == "current_lord"
                and isinstance(object_id, str)
                and ":" not in object_id
            ):
                object_name = object_id.replace("_", " ")
            if subject_name and object_name:
                if is_turkish:
                    return f"{subject_name} kentinin güncel Lordu {object_name}."
                return (
                    f"{object_name} is the current Lord of {subject_name}."
                )
        if (
            predicate == "continues_as"
            and not distance_question
            and route_continuation_question
            and subject_id in mentioned_ids
            and object_id in mentioned_ids
        ):
            if notes:
                return notes
            subject_name = entity_name(subject_id)
            object_name = entity_name(object_id)
            if subject_name and object_name:
                if is_turkish:
                    return f"{subject_name}, {object_name} olarak devam eder."
                return f"{subject_name} continues as {object_name}."
        if (
            predicate == "political_form"
            and political_form_question
            and subject_id in mentioned_ids
        ):
            subject_name = entity_name(subject_id)
            if object_id == "settlement_coalition_not_a_realm" and subject_name:
                if is_turkish:
                    return (
                        f"{subject_name}, yerleşim koalisyonudur; "
                        "bir realm değildir."
                    )
                display_name = (
                    subject_name
                    if subject_name.casefold().startswith("the ")
                    else f"The {subject_name}"
                )
                return (
                    f"{display_name} is a settlement coalition, not a realm."
                )
            if notes and not re.search(
                r"\b(?:normalized|institutional form)\b",
                game._lore_guard_text(notes),
            ):
                return notes
        if (
            predicate == "current_status"
            and rebuilding_question
            and subject_id in mentioned_ids
        ):
            subject_name = entity_name(subject_id)
            if subject_name and object_id in {"rebuilding", "under_reconstruction"}:
                if is_turkish:
                    return f"{subject_name} yeniden inşa ediliyor."
                return f"{subject_name} is rebuilding."
            if notes:
                return notes

    if "overview" in query_intents:
        overview_facts = [
            fact
            for fact in facts
            if fact.get("subject_id") in mentioned_ids
            and fact.get("predicate") in overview_priority
        ]
        overview_facts.sort(
            key=lambda fact: (
                overview_priority.get(fact.get("predicate"), 99),
                str(fact.get("fact_id", "")),
            )
        )
        statements = []
        for fact in overview_facts[:4]:
            statement = render_loaded_fact(fact)
            if statement and statement not in statements:
                statements.append(statement)
        if statements:
            return " ".join(statements)
    return None

def _player_question_has_unverified_lore_claim(
    player_input,
    lore_context,
    world_state,
):
    if not isinstance(player_input, str) or not player_input.strip():
        return False
    normalized_input = game._lore_guard_text(player_input)
    starts_with_question_word = bool(re.match(
        r"^\s*(?:who|what|where|when|why|how|which|whose|"
        r"is|are|was|were|does|do|did|can|could|should|would|will|"
        r"kim|ne|nerede|hangi|neden|nasıl|nasil|"
        r"mi|mı|mu|mü)\b",
        player_input,
        re.IGNORECASE,
    ))
    requests_route_distance = bool(
        game._LORE_ROUTE_DISTANCE_QUERY_RE.search(normalized_input)
        and re.search(
            r"\b(?:tell|give|provide|state|calculate|estimate|"
            r"soyle\w*|ver\w*|belirt\w*|hesapla\w*|aktar\w*)\b",
            normalized_input,
        )
    )
    if (
        "?" not in player_input
        and not starts_with_question_word
        and not requests_route_distance
    ):
        return False

    names_by_id, known_phrases, known_tokens = game._lore_entity_names(
        lore_context, world_state
    )
    if game._has_unregistered_narrative_entity(
        player_input,
        known_phrases,
        known_tokens,
    ):
        return True

    mentioned_ids = {
        entity_id
        for entity_id, names in names_by_id.items()
        if any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])",
                normalized_input,
            )
            for name in names
        )
    }
    sections = lore_context.get("sections", {}) if isinstance(lore_context, dict) else {}
    facts = []
    evidence_parts = []
    for section_name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
        "npc_known_lore",
    ):
        items = sections.get(section_name, []) if isinstance(sections, dict) else []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                facts.append(item)
                evidence_parts.extend(
                    str(item.get(key, ""))
                    for key in (
                        "fact_id", "subject_id", "predicate",
                        "object_id_or_value", "notes",
                    )
                )
    evidence = game._lore_guard_text(" ".join(evidence_parts))
    route_intent = bool(re.search(
        r"\b(?:continu\w*|connect\w*|becom\w*|turn\w*|lead\w*|"
        r"join\w*|extend\w*|road to|route to|devam\w*|baglan\w*|"
        r"donus\w*)\b",
        normalized_input,
    ))

    def has_loaded_route_relation():
        if not route_intent:
            return False
        route_predicates = {
            "continues_as",
            "connects_to",
            "leads_to",
            "joins",
            "turns_into",
            "extends_to",
        }
        for fact in facts:
            if fact.get("predicate") not in route_predicates:
                continue
            subject_id = fact.get("subject_id")
            if subject_id not in mentioned_ids:
                continue
            if len(mentioned_ids) <= 1:
                return True
            endpoints = {subject_id, fact.get("object_id_or_value")}
            if mentioned_ids.issubset(endpoints):
                return True
        return False

    for pattern, _reason in game._LORE_UNSUPPORTED_DETAIL_PATTERNS:
        for match in pattern.finditer(player_input):
            if game._lore_guard_text(match.group(0)) in evidence:
                continue
            if _reason == "geographic_relation" and has_loaded_route_relation():
                continue
            return True

    if game._LORE_ROUTE_DISTANCE_QUERY_RE.search(normalized_input):
        mentioned_ids = {
            entity_id
            for entity_id, names in names_by_id.items()
            if any(
                re.search(
                    rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])",
                    normalized_input,
                )
                for name in names
            )
        }
        distance_question = bool(re.search(
            r"\b(?:distance|how far|how many\s+(?:miles?|kilometers?|"
            r"kilometres?|meters?|metres?)|miles?|kilometers?|"
            r"kilometres?|meters?|metres?|kac mil|kac kilometre|"
            r"ne kadar uzak\w*|mesafe\w*|uzaklik\w*)\b",
            normalized_input,
        ))
        if distance_question and len(mentioned_ids) == 1:
            current_location_id = (
                world_state.get("location")
                if isinstance(world_state, dict)
                else None
            )
            if isinstance(current_location_id, str) and current_location_id in names_by_id:
                mentioned_ids.add(current_location_id)

        if distance_question:
            if len(mentioned_ids) == 1:
                current_location_id = (
                    world_state.get("location")
                    if isinstance(world_state, dict)
                    else None
                )
                if (
                    isinstance(current_location_id, str)
                    and current_location_id in names_by_id
                ):
                    mentioned_ids.add(current_location_id)

            def fact_has_requested_distance(fact):
                fact_text = game._lore_guard_text(" ".join(
                    str(fact.get(key, ""))
                    for key in (
                        "predicate", "object_id_or_value", "notes",
                    )
                ))
                if not re.search(
                    r"\b\d+\s*(?:miles?|mi|kilometers?|kilometres?|"
                    r"km|meters?|metres?|yards?|leagues?|mil|kilometre|metre)\b",
                    fact_text,
                ):
                    return False
                endpoints = {
                    fact.get("subject_id"),
                    fact.get("object_id_or_value"),
                }
                if len(mentioned_ids) >= 2 and mentioned_ids.issubset(endpoints):
                    return True
                if len(mentioned_ids) >= 2:
                    return all(
                        any(
                            re.search(
                                rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])",
                                fact_text,
                            )
                            for name in names_by_id.get(entity_id, set())
                        )
                        for entity_id in mentioned_ids
                    )
                return bool(mentioned_ids & endpoints)

            if not any(fact_has_requested_distance(fact) for fact in facts):
                return True
        elif len(mentioned_ids) >= 2:
            has_supported_pair = any(
                fact.get("subject_id") in mentioned_ids
                and fact.get("object_id_or_value") in mentioned_ids
                for fact in facts
            )
            if not has_supported_pair:
                return True
    return False

def _lore_entity_names(lore_context, world_state):
    names_by_id = {}
    known_phrases = set()
    known_tokens = set()

    def add_name(entity_id, name):
        if not isinstance(name, str) or not name.strip():
            return
        normalized = game._lore_guard_text(name)
        if not normalized:
            return
        known_phrases.add(normalized)
        if isinstance(entity_id, str) and entity_id:
            names_by_id.setdefault(entity_id, set()).add(normalized)
        for token in normalized.split():
            if len(token) >= 4 and token not in {
                "city", "town", "river", "mount", "mountain", "region",
                "road", "north", "south", "east", "west",
            }:
                known_tokens.add(token)

    sections = lore_context.get("sections", {}) if isinstance(lore_context, dict) else {}
    verified_entities = (
        sections.get("verified_entities", []) if isinstance(sections, dict) else []
    )
    for entity in verified_entities if isinstance(verified_entities, list) else []:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("entity_id")
        add_name(entity_id, entity.get("canonical_name"))
        for alias in entity.get("aliases", []):
            add_name(entity_id, alias)

    if isinstance(world_state, dict):
        for location_id, location in world_state.get("locations", {}).items():
            if isinstance(location, dict):
                add_name(location_id, location.get("name"))
                for alias in location.get("aliases", []):
                    add_name(location_id, alias)
        for collection in ("npcs", "features", "shops"):
            for entity in world_state.get(collection, []):
                if not isinstance(entity, dict):
                    continue
                entity_id = entity.get("id") or entity.get("feature_id")
                add_name(entity_id, entity.get("name"))
                for alias in entity.get("aliases", []):
                    add_name(entity_id, alias)
                if (
                    collection == "npcs"
                    and entity.get("location") == world_state.get("location")
                ):
                    add_name(entity_id, entity.get("role"))

    return names_by_id, known_phrases, known_tokens
