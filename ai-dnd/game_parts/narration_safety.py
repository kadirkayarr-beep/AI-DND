import game
import interaction_adventure
import json
import living_world
import local_dialogue
import re


def _unregistered_persistent_object_claim(world_state, narration):
    """Reject asserted persistent objects absent from canonical scene state."""
    normalized = game._normalize_turkish_typos(
        re.sub(r"\s+", " ", str(narration).casefold())
    )
    heads = "|".join(
        re.escape(head) for head in game._NARRATION_PERSISTENT_OBJECT_HEADS
    )
    state = "|".join(
        re.escape(term) for term in game._NARRATION_PERSISTENT_OBJECT_STATE
    )
    claims = (
        re.search(
            rf"\b(?:yerdeki|yerde|buradaki|yakındaki|masadaki|duvardaki|"
            rf"onundeki|yanindaki|odadaki)\b.{{0,40}}"
            rf"\b(?P<head>{heads})[a-z0-9]*\b",
            normalized,
        ),
        re.search(
            rf"\b(?:bir|yeni|eski)\s+(?P<head>{heads})[a-z0-9]*\b"
            rf".{{0,45}}\b(?:{state})\b",
            normalized,
        ),
        re.search(
            rf"\b(?P<head>{heads})[a-z0-9]*\b.{{0,35}}\b"
            rf"(?:{state})\b",
            normalized,
        ),
    )
    claim = next((match for match in claims if match), None)
    if not claim:
        return None

    head = claim.group("head")
    prefix = normalized[max(0, claim.start() - 45):claim.start()]
    claim_context = f"{prefix} {claim.group(0)}"
    ground_reference = bool(re.search(
        r"\b(?:yerdeki|yerde|masadaki|masada|duvardaki|duvarda|"
        r"onundeki|onunde|yanindaki|yaninda|odadaki|odada|zemindeki|"
        r"zeminde|kutudaki|kutuda)\b",
        claim_context,
    ))
    registered_names = game._registered_persistent_object_names(
        world_state, include_carried=not ground_reference
    )
    matches = [
        name for name in registered_names
        if re.search(
            rf"\b{re.escape(head)}[a-z0-9]*\b",
            game._normalize_turkish_typos(name.casefold()),
        )
    ]
    if matches:
        return None
    return claim.group(0)

def _unregistered_held_object(world_state, narration):
    """A thing in a hand, or a named prop, that the scene does not have."""
    normalized = re.sub(r"\bdikkat cekici\b", " ", game._normalize_turkish_typos(narration))
    names = " ".join(
        game._normalize_turkish_typos(name)
        for name in game._registered_persistent_object_names(world_state, include_carried=True)
    )
    for head in ("caydanlik", "supurge", "cekic"):
        if re.search(rf"\b{head}", normalized) and not re.search(rf"\b{head}", names):
            return head
    marker = re.search(r"\b(?:elindeki|elinde|tuttugu)\b", normalized)
    if marker is None:
        return None
    window = normalized[marker.end():marker.end() + 48]
    for word in re.findall(r"[a-z]+", window):
        stem = re.sub(r"(?:nin|nun|in|un|si|su|yi|yu|i|u)$", "", word)
        if word in game._HELD_SKIP or stem in game._HELD_SKIP or len(stem) < 4:
            continue
        if re.search(rf"\b{re.escape(stem)}", names):
            return None
        return window.strip()
    return None

def _resolve_campaign_npc_reference(player_input, world_state=None):
    if not isinstance(player_input, str):
        return None
    if world_state is None:
        world_state = game._session().world_state
    text = game._normalize_turkish_typos(player_input)
    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        if game._entity_reference_in_text(npc.get("name", ""), text) or game._entity_reference_in_text(npc.get("role", ""), text):
            return npc
    return None

def _unsupported_npc_history_or_relationship_claim(
    narration, npc_target=None, player_input="", *, spoken_start=None, own_words=False
):
    """Detect invented relationship mutations or campaign-history claims not grounded in Python state."""
    text = str(narration).casefold()

    # 1. Relationship / trust / alliance mutation without canonical backing
    rel_patterns = (
        r"\b(?:artık\s+)?(?:tamamen\s+)?güven(?:iyor|ir|ini\s+kazandın|i\s+tam)\b",
        r"\b(?:en\s+iyi|en\s+yakın)\s+dost(?:u|umuz|um|sunuz)?\b",
        r"\b(?:artık\s+)?(?:dost|müttefik)\s+(?:olduk|oldu|ilan\s+eder|sayılırız)\b",
        r"\bartık\s+sana\s+güven\w*\b",
    )
    for pat in rel_patterns:
        match = re.search(pat, text)
        if match:
            rel = (npc_target or {}).get("relationship") if isinstance(npc_target, dict) else None
            if rel not in ("friendly", "allied"):
                return ("CANONICAL_RELATIONSHIP_CONTRADICTION", match.group(0))

    # 2. Campaign history / past agreements / past debts / past encounters
    history_patterns = (
        (r"\b(?:sana|bana)\s+(?:olan\s+)?borc(?:um|un|umu|unu)\b|\bborcum\s+var\b|\bborçluyum\b", "debt"),
        (r"\b(?:iş|görev)\s+sözü\s+ver\w*|\biş\s+vadet\w*|\b(?:iş|görev)\s+borçluyum\b", "job_promise"),
        (r"\bödül(?:de|\s+için)?\s+anlaş\w*|\bödül\s+sözü\s+ver\w*", "reward_agreement"),
        (r"\b(?:kardeşimi|hayatımı|babamı|annemi)\s+kurtar\w*", "life_saving"),
        (r"\b(?:dün|geçen\s+gün|daha\s+önce)\s+(?:burada\s+)?(?:buluş\w*|görüş\w*|karşılaş\w*|tanış\w*)", "prior_meeting"),
        (r"\b(?:bana|bize)\s+.{1,60}\b(?:söylemiş\w*|anlatmış\w*|bahsetmiş\w*|demiş\w*|söyledi\w*|anlattı\w*|bahsetti\w*|dedi\w*)\b", "prior_disclosure"),
        (r"\b\w+(?:'nin|'nın|'nun|'nün|in|ın|un|ün)?\s+sözleri\b.{0,60}\b(?:belirtti|söyledi|anlattı|bahsetti)\b", "npc_speech_affirmation"),
        (r"\b(?:yıllardır|uzun\s+zamandır|eskiden\s+beri)\s+tanı\w*", "longstanding_acquaintance"),
        (r"\b(?:eski|geçmiş)\s+macera\w*", "past_adventures"),
    )
    for pat, _category in history_patterns:
        for match in re.finditer(pat, text):
            if spoken_start is not None and match.start() >= spoken_start:
                from npc_speech_boundary import explicit_history_denial
                if explicit_history_denial(text, match):
                    continue
            supported = False
            target = npc_target or game._resolve_campaign_npc_reference(player_input or narration)
            if isinstance(target, dict):
                if game.npc_memory_supports_claim(target, match.group(0)):
                    supported = True
                elif any(match.group(0) in str(k).casefold() for k in target.get("knowledge", [])):
                    supported = True
            if not supported:
                return ("UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM", match.group(0))

    if player_input and not own_words and game.is_npc_historical_claim(player_input):
        target = npc_target or game._resolve_campaign_npc_reference(player_input)
        supported = False
        if isinstance(target, dict):
            if game.npc_memory_supports_claim(target, player_input):
                supported = True
            elif any(player_input.casefold() in str(k).casefold() for k in target.get("knowledge", [])):
                supported = True
        if not supported:
            denial_pattern = (
                r"\b(?:hatırlam\w*|hatirlam\w*|kayıt\s+yok|kayit\s+yok|bilmi\w*|"
                r"bahsetme\w*|söyleme\w*|soyleme\w*|anlatma\w*|demedi\w*|"
                r"doğrulanm\w*|dogrulanm\w*|belirsiz|bulunmuyor|böyle\s+bir\s+şey\b|"
                # In-character refusals: a person rejecting a claim does not need
                # to talk about records ("söz vermedim", "beni karıştırıyorsun").
                r"vermedim|vermem\b|vermedik|karıştır\w*|karistir\w*|"
                r"yanıl\w*|yanil\w*|yanlış|yanlis|hayır|hayir|anımsam\w*|animsam\w*|"
                r"(?:öyle|oyle)\s+bir\s+(?:söz|soz|şey|sey)|sözüm\s+yok|sozum\s+yok)"
            )
            if not re.search(denial_pattern, text):
                return ("UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM", player_input[:160])

    return None

def _unverified_player_mental_state_trigger(player_action_text, second_person_verb):
    for match in second_person_verb.finditer(player_action_text):
        normalized_verb = game._normalize_turkish_typos(match.group(0))
        if normalized_verb.endswith(
            ("abilirsin", "ebilirsin", "abilirsiniz", "ebilirsiniz",
             "malisin", "melisin", "malisiniz", "melisiniz")
        ):
            continue
        if normalized_verb.startswith(game._PLAYER_MENTAL_STATE_PREFIXES):
            return match.group(0)

        clause_prefix = re.split(
            r"[.!?;]", player_action_text[:match.start()]
        )[-1]
        context = game._normalize_turkish_typos(clause_prefix[-45:])
        if (
            normalized_verb.startswith(("ol", "et", "ed", "ver", "al", "duy", "kal", "his", "gor"))
            and game._PLAYER_MENTAL_STATE_CONTEXT_RE.search(context)
        ):
            return match.group(0)

    for pattern in (
        game._PLAYER_MENTAL_STATE_COPULA_RE,
        game._PLAYER_MENTAL_STATE_EXPLICIT_SUBJECT_RE,
        game._PLAYER_MENTAL_STATE_AFFECT_RE,
    ):
        match = pattern.search(player_action_text)
        if match:
            return match.group(0)
    return None

def _authorized_item_transfer_matches(text, action_result):
    if (
        not isinstance(action_result, dict)
        or action_result.get("action") != "equipment_transaction"
        or action_result.get("status") != "resolved"
        or action_result.get("success") is not True
    ):
        return False
    normalized_text = game._normalize_turkish_typos(str(text or "").casefold())
    for transfer in action_result.get("item_transfers", []):
        if not isinstance(transfer, dict) or transfer.get("to") != "player":
            continue
        name = game._normalize_turkish_typos(str(transfer.get("name") or "").casefold())
        if not name:
            continue
        item_pattern = (
            rf"(?<![a-z0-9çğıöşü]){re.escape(name)}"
            r"[a-zçğıöşü]*(?![a-z0-9çğıöşü])"
        )
        if re.search(item_pattern, normalized_text):
            return True
    return False

def _is_explicitly_negated_transfer(match, text):
    """Do not treat a locally negated transfer verb as an item hand-off."""
    if "transfer_verb" not in match.re.groupindex:
        return False
    verb = game._normalize_turkish_typos(str(match.group("transfer_verb") or "").casefold())
    if not re.fullmatch(
        r"(?:ver|birak|uzat|sana uzat|eline ver|onune birak|"
        r"teslim et|ikram et|hediye et|envanterine ekle|envanterine eklen)"
        r"(?:m[ae](?:dim|din|di|dik|diniz|diler)|"
        r"m(?:iyorum|iyorsun|iyor|iyoruz|iyorsunuz|iyorlar)|m[ae]m|m[ae]z)",
        verb,
    ):
        return False
    tail = game._normalize_turkish_typos(str(text[match.end():match.end() + 48]).casefold())
    # "Vermedim diyemem" and "vermedim değil" are not clear denials.
    if re.match(
        r"\s*(?:[\"'”’)]\s*)?(?:degil\b|diyemem\b|soyleyemem\b|"
        r"inkar\s+edemem\b|yalan\s+soyleyemem\b)",
        tail,
    ):
        return False
    return True

def _experimental_private_npc_disclosure(
    text, world_state, *, npc_target=None, speech_fields=None
):
    """Match output against dynamically derived, non-shareable NPC source values."""
    folded_text = game._normalize_turkish_typos(str(text or "").casefold())
    public_detail = (
        local_dialogue.public_personal_detail(world_state, npc_target)
        if speech_fields is not None else None
    )

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for nested in value.values():
                yield from strings(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                yield from strings(nested)

    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        profile = npc.get("personal_profile")
        if isinstance(profile, dict):
            for field, value in profile.items():
                if field in interaction_adventure.SHAREABLE_PROFILE_FIELDS:
                    continue
                for private_value in strings(value):
                    folded_value = game._normalize_turkish_typos(
                        private_value.casefold()
                    )
                    compact = re.sub(r"[^a-z0-9]", "", folded_value)
                    if len(compact) < 6:
                        continue
                    field_text = folded_text
                    if (
                        public_detail is not None
                        and npc.get("id") == public_detail["owner_id"]
                        and field == "personal_detail"
                        and private_value == public_detail["value"]
                    ):
                        # Only server-bound spoken text gets this exception.
                        # Narrator stage text and every other NPC remain checked.
                        field_text = game._normalize_turkish_typos(speech_fields[1].casefold())
                    if re.search(
                        rf"(?<![a-z0-9]){re.escape(folded_value)}(?![a-z0-9])",
                        field_text,
                    ):
                        return True

    interaction_state = interaction_adventure.get(world_state)
    perspectives = interaction_state.get("perspectives", {})
    if isinstance(perspectives, dict):
        for entries in perspectives.values():
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict) or not entry.get("secret"):
                    continue
                for private_value in strings(entry.get("text")):
                    folded_value = game._normalize_turkish_typos(
                        private_value.casefold()
                    )
                    compact = re.sub(r"[^a-z0-9]", "", folded_value)
                    if len(compact) < 6:
                        continue
                    if re.search(
                        rf"(?<![a-z0-9]){re.escape(folded_value)}(?![a-z0-9])",
                        folded_text,
                    ):
                        return True
    return False

def _unseen_self_introductions(text, unseen):
    """Each speech span with the sentences in it that introduce the speaker by an unseen registered name."""
    found = []
    for span in game._SPEECH_SPAN_RE.finditer(text):
        parts = game._split_sentences_keep_speech(span.group(0)[1:-1])
        intros = [part for part in parts
                  if (local_dialogue.explicit_player_name_disclosure(part) or "").casefold() in unseen]
        if intros:
            found.append((span, parts, intros))
    return found

def _narration_is_unsafe(narration, player_input, npc_target=None, action_result=None):
    return game._narration_safety_decision(
        narration, player_input, npc_target, action_result
    )["unsafe"]

def is_player_world_assertion(player_input):
    text = player_input.casefold().strip()
    patterns = (
        r"\bben\s+(?:aslında\s+)?(?:kral(?:ım)?|kraliçe(?:yim)?|komutan(?:ım)?|imparator(?:um)?|lord(?:um)?|lady(?:im)?)\b",
        r"\b(?:kapı|kapısı)\s+(?:açık|kapalı|kilitli|kırık)\b",
        r"\b(?:tavernadayım|meyhanedeyim|ormandayım|kalede(?:yim)?|buradayım)\b",
        r"\b(?:çantamda|envanterimde)\b.{0,50}\b(?:altın|kılıç|eşya|potion)\b",
        r"\b(?:öldü|öldürüldü|hayatını kaybetti)\b",
        r"\böldürdüm\b",
        r"\b(?:karşımda|karsımda|önümde|onumde)\s+.{1,40}\b(?:var|duruyor|bekliyor)\b",
        r"\bburada\s+(?:\d+|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|yedi|sekiz|dokuz|on)\s+(?:asker|haydut|muhafız|kisi|kişi)\b",
        r"\b\w+\s+gör(?:üyorum|uyorum|dum|düm)\b",
        r"\b(?:adı|ismi)\s+[A-ZÇĞİÖŞÜ][\w-]+\b",
        r"\b\w+(?:in|ın|un|ün)\s+(?:adı|ismi)\s+(?!ne\b)[\w-]+\b",
    )
    return game.is_npc_historical_claim(player_input) or any(re.search(pattern, text) for pattern in patterns)

def _record_narration_safety(decision, handling):
    """Keep concise, ephemeral diagnostics out of player-facing response data."""
    session = game._session()
    decision = decision or {}
    diagnostic = {
        "handling": handling,
        "reason_code": decision.get("reason_code"),
        "trigger_span": str(decision.get("trigger_span") or "")[:160] or None,
        "scene_type": decision.get("scene_type"),
        "tier": (
            "tier_0_accept" if handling == "accepted"
            else "tier_2_repair" if handling == "repaired"
            else "tier_3_fallback"
        ),
    }
    session.last_narration_safety = diagnostic
    history = getattr(session, "narration_safety_history", None)
    if not isinstance(history, list):
        history = []
        session.narration_safety_history = history
    history.append(dict(diagnostic))
    del history[:-32]
    if game.DEBUG_MODE and handling != "accepted":
        print(
            "[NARRATION SAFETY] "
            + json.dumps(diagnostic, ensure_ascii=False, separators=(",", ":"))
        )

def _remove_trigger_sentence(narration, decision, action_result=None):
    """Remove one complete unsafe sentence: a bad line costs its sentence, not the turn.

    A combat report and an off-topic greeting have no safe remainder to keep.
    """
    if decision.get("reason_code") not in {
        "INVENTED_PLAYER_ACTION", "INVENTED_PLAYER_OBJECTIVE", "INVENTED_PLAYER_MENTAL_STATE",
    } and (
        decision.get("reason_code") == "UNRELATED_GREETING_REPLY"
        or (isinstance(action_result, dict) and action_result.get("action") in {"attack", "death_save"})
    ):
        return None
    # A long span can run over a sentence end, so only its first words find the sentence.
    trigger = " ".join(str(decision.get("trigger_span") or "").casefold().split()[:3])[:30].strip()
    if not trigger:
        return None
    paragraphs = []
    removed = False
    for paragraph in str(narration).split("\n\n"):
        sentences = game._split_sentences_keep_speech(paragraph.strip())
        kept = []
        for sentence in sentences:
            # Some checks report folded text.
            if not removed and (
                trigger in sentence.casefold() or trigger in game._normalize_turkish_typos(sentence)
            ):
                removed = True
                continue
            if sentence:
                kept.append(sentence)
        if kept:
            paragraphs.append(" ".join(kept))
    repaired = game._trim_dangling_quote("\n\n".join(paragraphs).strip())
    return repaired if removed else None

def _unsupported_available_quest_claim(narration):
    """Reject a claim that quests exist when Python has none to offer."""
    if not isinstance(narration, str) or not narration.strip():
        return False
    text = living_world.normalize_text(narration)
    session = game._session()
    positive_clause = False
    if re.search(r"\b(?:gorev|quest)\w*\b", text):
        clauses = [
            clause.strip()
            for clause in re.split(r"[,.]|\b(?:ama|fakat|ancak)\b", text)
            if clause.strip()
        ]
        for clause in clauses:
            if not re.search(r"\b(?:gorev|quest)\w*\b", clause):
                continue
            if re.search(r"\b(?:yok|degil|bulunmuyor|sunulmamis|sunulmadi)\b", clause):
                continue
            if re.search(r"\b(?:var|duydum|oldugunu|sunulmus|sunuldu|mevcut)\b", clause):
                positive_clause = True
                break
    authorized = False
    if positive_clause:
        world_state = session.world_state
        authorized = any(
            isinstance(quest, dict) and quest.get("status") == "accepted"
            for quest in world_state.get("quests", [])
        ) or bool(session.quest_offers())
    unsupported = positive_clause and not authorized
    return unsupported
