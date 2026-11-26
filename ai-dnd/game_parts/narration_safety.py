import game
import interaction_adventure
import json
import living_world
import local_dialogue
import re
import npc_statements


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

def _narration_safety_decision(
    narration, player_input, npc_target=None, action_result=None, *, attributed_speech=None
):
    """Return a reason-coded safety decision without changing canonical state."""
    world_state = game._session().world_state
    scene_type = game._narration_scene_type(action_result)
    attack_claims_assessed = False
    attack_fact_packet = None

    def reject(reason_code, trigger_span=None):
        return {
            "unsafe": True,
            "reason_code": reason_code,
            "trigger_span": str(trigger_span or "")[:160] or None,
            "scene_type": scene_type,
        }

    def accept():
        return {
            "unsafe": False,
            "reason_code": None,
            "trigger_span": None,
            "scene_type": scene_type,
        }

    if not isinstance(narration, str) or not narration.strip():
        return reject("EMPTY_NARRATION")
    import npc_speech_boundary
    speech_fields = npc_speech_boundary.fields_for_narration(
        narration, attributed_speech, npc_target, action_result
    )
    spoken_start = (
        len(narration.casefold()) - len(speech_fields[0].casefold())
        if speech_fields is not None else None
    )
    _exit = game._nsd_action_result_action(action_result=action_result, narration=narration, npc_target=npc_target, reject=reject, speech_fields=speech_fields, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    # A greeting does not authorize reopening a disputed past conversation.
    # Evaluate the NPC's actual quoted reply, not keywords anywhere in the
    # scene (a gesture or narrator's description is not NPC speech).
    greeting_only = scene_type == "conversation" and bool(re.fullmatch(
        r"(?:merhaba|selam|selamlar|gunaydin|iyi gunler|iyi aksamlar)",
        game._normalize_turkish_typos(player_input),
    ))
    _exit = game._nsd_greeting_only_quoted(greeting_only=greeting_only, narration=narration, reject=reject)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        for field, known in (("name", living_world.npc_name_known_to_player),
                             ("role", living_world.npc_role_known_to_player)):
            identity = npc.get(field)
            if not known(npc) and identity and game._entity_reference_in_text(identity, narration):
                identity_view = narration
                if field == "name" and npc.get("id") != (npc_target or {}).get("id"):
                    identity_view = npc_speech_boundary.mask_bound_self_name(
                        narration, identity, world_state, attributed_speech,
                        npc_target, action_result,
                    )
                identity_view = npc_speech_boundary.hidden_identity_scan_text(
                    identity_view, identity, world_state
                )
                identity_view = npc_speech_boundary.mask_calendar_month_name(identity_view, identity)
                if game._entity_reference_in_text(identity, identity_view):
                    return reject("HIDDEN_NPC_IDENTITY_DISCLOSURE", identity)
    action_result = action_result or {}
    elapsed_claim = game._nsd_elapsed_claim_re(narration=narration)
    _exit = game._nsd_elapsed_claim_claimed(action_result=action_result, elapsed_claim=elapsed_claim, reject=reject)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    if action_result.get("action") == "attack":
        # Same facts as the deterministic combat sentence, not the same words.
        import narration_claims
        attack_fact_packet = game._narration_fact_packet(action_result)
        verdict = narration_claims.assess(narration, attack_fact_packet)
        if verdict["reject"]:
            return reject(
                verdict["reason"] or "COMBAT_RESULT_CONTRADICTION",
                verdict.get("span") or narration.strip()[:160],
            )
        attack_claims_assessed = True

    text = game._nsd_text_without_awarded_xp(text=narration.casefold())  # D-012: the real award may be said
    input_text = str(player_input).casefold()

    def is_verified_attack_damage_claim(claim):
        if not attack_claims_assessed or not isinstance(action_result, dict):
            return False
        amount_match = re.search(r"\b\d+\b", claim.group(0))
        if not amount_match:
            return False
        amount = int(amount_match.group(0))
        exchanges = (attack_fact_packet or {}).get("exchanges", [])
        received = [
            exchange for exchange in exchanges
            if exchange.get("target") == "player"
            and exchange.get("outcome") in ("hit", "critical_hit")
            and exchange.get("damage") == amount
        ]
        if received and re.search(
            r"\b\d+\s*(?:puan\s+)?hasar\s+alirsin\w*\b|"
            r"\bhasar\s*(?:puan\s*)?\d+\s+alirsin\w*\b",
            claim.group(0),
        ):
            return True

        if (
            action_result.get("action") != "attack"
            or action_result.get("outcome") not in ("hit", "critical_hit")
            or action_result.get("damage") != amount
        ):
            return False
        target = str(
            action_result.get("target_name") or action_result.get("target") or ""
        ).strip()
        if not target:
            return False

        clause_start = max(
            text.rfind(mark, 0, claim.start()) for mark in ".!?"
        ) + 1
        clause_end = min(
            (position for mark in ".!?"
             if (position := text.find(mark, claim.end())) >= 0),
            default=len(text),
        )
        clause = text[clause_start:clause_end]
        damage_pattern = (
            r"\b\d+\s*(?:puan\s+)?hasar\b.{0,25}"
            r"\b(?:al\w*|ver\w*|uğra\w*)"
        )
        if len(list(re.finditer(damage_pattern, clause))) != 1:
            return False

        import narration_claims
        folded_clause = narration_claims.fold(clause)
        folded_target = narration_claims.fold(target)
        folded_amount = str(amount)
        bound_outgoing_pattern = (
            rf"\b{re.escape(folded_target)}\b.{{0,48}}"
            rf"\b(?:kritik\s+)?(?:bir\s+)?(?:agir\s+)?"
            rf"(?:darbe|vurus)\s+al\w*.{{0,24}}"
            rf"\b{folded_amount}\s*(?:puan\s+)?hasar\b.{{0,12}}\bal\w*"
        )
        return re.search(bound_outgoing_pattern, folded_clause) is not None

    if npc_target and isinstance(npc_target, dict) and npc_target.get("id"):
        target_name = str(npc_target.get("name", "")).strip()
        target_id = npc_target.get("id")
        # A "Name: “...”" label attributes the speech. The roster check below
        # only catches names of NPCs already in the world; an invented speaker
        # who exists nowhere must not pass either.
        speaker_label = re.match(r"\s*([^\s:,\"“”']{2,40})\s*:\s*[\"“]", narration)
        _exit = game._nsd_speaker_label_label(npc_target=npc_target, reject=reject, speaker_label=speaker_label, target_name=target_name)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        first_person_identities = re.finditer(
            r"\b(?:(?i:ben)\s+|(?i:benim\s+adım|adım|ismim)\s+)"
            r"([A-ZÇĞİÖŞÜ][a-zçğıöşü'’-]{1,})\b(?=\s*[,!.?])",
            narration,
        )
        for first_person_identity in first_person_identities:
            claimed_name = first_person_identity.group(1)
            allowed_names = game._nsd_allowed_names_normalize(npc_target=npc_target, target_name=target_name)
            if claimed_name and not npc_speech_boundary.matches_speaker_identity(claimed_name, allowed_names):
                return reject(
                    "WRONG_NPC_SPEAKER_ATTRIBUTION",
                    first_person_identity.group(1),
                )
        for other_npc in world_state.get("npcs", []):
            if not isinstance(other_npc, dict):
                continue
            if other_npc.get("id") == target_id:
                continue
            other_name = str(other_npc.get("name", "")).strip()
            if not other_name:
                continue
            norm_other = game._normalize_turkish_typos(other_name.casefold())
            norm_narration = game._normalize_turkish_typos(text)
            speaker_pattern = game._nsd_speaker_pattern_rf(norm_other=norm_other)
            match = re.search(speaker_pattern, norm_narration)
            if match:
                return reject("WRONG_NPC_SPEAKER_ATTRIBUTION", other_name)

        other_disclosed_names = set()
        for other_npc in world_state.get("npcs", []):
            if not isinstance(other_npc, dict) or other_npc.get("id") == target_id:
                continue
            for entry in other_npc.get("memory", []):
                if isinstance(entry, dict) and entry.get("speaker") == "player":
                    disclosed = game._explicit_player_name_disclosure(entry.get("text", ""))
                    if disclosed:
                        other_disclosed_names.add(disclosed.casefold())

        target_known_names = set()
        for entry in npc_target.get("memory", []):
            if isinstance(entry, dict) and entry.get("speaker") == "player":
                disclosed = game._explicit_player_name_disclosure(entry.get("text", ""))
                if disclosed:
                    target_known_names.add(disclosed.casefold())
        curr_disclosed = game._explicit_player_name_disclosure(player_input)
        if curr_disclosed:
            target_known_names.add(curr_disclosed.casefold())

        leaked_names = other_disclosed_names - target_known_names
        for leaked_name in leaked_names:
            pat = rf"(?<![a-zçğıöşü]){re.escape(leaked_name)}(?![a-zçğıöşü])"
            match = re.search(pat, text)
            if match:
                return reject("NPC_MEMORY_DISCLOSURE_LEAK", match.group(0))

    if action_result.get("action") == "dialogue":
        # Dialogue is not an authoritative item/door action. Unrelated state
        # changes in the same turn cannot authorize a claimed transfer or
        # door change; those actions must be committed under their own result.
        normalized_narration = game._normalize_turkish_typos(text)
        transfer_claim = re.search(
            r"\bsana\b[^.!?]{0,60}"
            r"\b(?:verdi|verdim|uzatti|uzattim|teslim etti|birakti|biraktim)\b",
            normalized_narration,
        )
        figurative_transfer = transfer_claim and re.search(
            r"\b(?:kalb\w*|yureg\w*|sevgi\w*|guven\w*|umut\w*|"
            r"dostlug\w*|cesaret\w*|destek\w*|soz\w*)\b",
            transfer_claim.group(0),
        )
        if transfer_claim and not figurative_transfer:
            return reject("UNVERIFIED_NARRATED_TRANSFER", transfer_claim.group(0))
        door_claim = re.search(
            r"\bkap\w+\s+(?:acti|acildi)\b", normalized_narration
        )
        if door_claim:
            return reject("UNVERIFIED_NARRATED_TRANSFER", door_claim.group(0))

    unsupported_npc_claim = game._unsupported_npc_history_or_relationship_claim(
        narration, npc_target=npc_target, player_input=player_input,
        spoken_start=spoken_start, own_words=action_result.get("own_words") is True,
    )
    if unsupported_npc_claim:
        return reject(unsupported_npc_claim[0], unsupported_npc_claim[1])
    action_outcome = action_result.get("outcome")
    character_name = str(game._session().character.get("name", "")).casefold()
    character_name_pattern = (
        rf"(?<![a-zçğıöşü]){re.escape(character_name)}(?![a-zçğıöşü])"
        if character_name else None
    )
    character_name_matches = (
        list(re.finditer(character_name_pattern, text)) if character_name_pattern else []
    )
    if speech_fields is not None and character_name in target_known_names:
        character_name_matches = [
            match for match in character_name_matches
            if not npc_speech_boundary.is_spoken_player_address(text, match, spoken_start)
        ]
    if character_name_matches:
        travel_result = (
            action_result.get("action") == "travel"
            and action_result.get("status") == "completed"
            and action_result.get("success") is True
        )
        if not travel_result or len(character_name_matches) != 1:
            result = reject("PLAYER_NAME_IN_NARRATION", character_name_matches[0].group(0))
            if spoken_start is not None and all(match.start() < spoken_start for match in character_name_matches):
                result["source_field"] = "stage_direction"
            return result
        match = character_name_matches[0]
        arrival_clause = re.split(r"[,;.!?]", text[match.end():], maxsplit=1)[0]
        current_location = world_state.get("location")
        record = world_state.get("locations", {}).get(current_location, {})
        aliases = game._location_alias_values(record) or [
            game._normalize_turkish_typos(game.location_display_name(current_location))
        ]
        location_pattern = "|".join(
            re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)
        )
        committed_arrival = bool(location_pattern) and re.fullmatch(
            rf"(?:{location_pattern})\w*\s+(?:ulas\w*|var\w*|gir\w*|gel\w*)",
            game._normalize_turkish_typos(arrival_clause),
        )
        if not committed_arrival:
            return reject("PLAYER_NAME_IN_NARRATION", match.group(0))

    # First-person NPC speech (attributed, non-canonical, no operation) may offer
    # and propose ("istersen", "içelim"): an offer decides nothing for the player,
    # and gifts/transfers/state claims are still rejected by their own rules.
    # The player-agency rules below were written for narrator text and stay on
    # for it.
    npc_speech = (
        isinstance(action_result, dict)
        and action_result.get("status") == "experimental_attributed_speech"
    )
    conditional = None
    conditional = game._nsd_npc_speech_quoted(conditional=conditional, npc_speech=npc_speech, text=text)
    if conditional:
        return reject("UNSUPPORTED_PLAYER_CHOICE", conditional.group(0))

    pre_agency_claims = game._nsd_pre_agency_claims()
    for reason_code, pattern in pre_agency_claims:
        claims = (
            list(re.finditer(pattern, text))
            if reason_code == "CANONICAL_DAMAGE_CONTRADICTION"
            else [re.search(pattern, text)]
        )
        for claim in filter(None, claims):
            if (
                reason_code == "CANONICAL_DAMAGE_CONTRADICTION"
                and is_verified_attack_damage_claim(claim)
            ):
                continue
            return reject(reason_code, claim.group(0))
    _exit = game._nsd_action_outcome_mechanical(action_outcome=action_outcome, player_input=player_input, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    arrival_text = living_world._text_outside_quotes(narration)
    current_location = world_state.get("location")
    current_record = world_state.get("locations", {}).get(current_location, {})
    current_is_city = (
        isinstance(current_record, dict)
        and current_record.get("type") == "city"
    ) or living_world.scene_kind(world_state, current_location) == "city"
    uncommitted_departure = game._nsd_uncommitted_departure_re(arrival_text=arrival_text)
    committed_travel = game._nsd_committed_travel_action(action_result=action_result)
    if current_is_city and uncommitted_departure and not committed_travel:
        return reject("CANONICAL_LOCATION_CONTRADICTION", uncommitted_departure.group(0))

    for npc in world_state.get("npcs", []):
        npc_location = npc.get("location")
        npc_name = str(npc.get("name", "")).strip()
        if not npc_name or not npc_location or npc_location == current_location:
            continue
        normalized_name = game._normalize_turkish_typos(npc_name.casefold())
        if not normalized_name:
            continue
        name_pattern = rf"(?<![a-z0-9çğıöşü]){re.escape(normalized_name)}(?![a-z0-9çğıöşü])"
        normalized_text = game._normalize_turkish_typos(text)
        if not re.search(name_pattern, normalized_text):
            continue
        duplicates = [
            candidate for candidate in world_state.get("npcs", [])
            if str(candidate.get("name", "")).casefold() == npc_name.casefold()
        ]
        if len(duplicates) > 1:
            target_id = (npc_target or {}).get("id")
            matching_target = next(
                (candidate for candidate in duplicates if candidate.get("id") == target_id),
                None,
            )
            if not matching_target:
                return reject("AMBIGUOUS_NPC_IDENTITY", npc_name)
            if matching_target.get("location") == current_location:
                continue
        present_action = re.search(
            name_pattern + r".{0,28}(?:[\"“]|gozleri|basini|yanina|"
            r"yaklas\w*|konus\w*|yanit ver\w*|der\b|durur\b)",
            normalized_text,
        )
        if present_action:
            return reject("CANONICAL_NPC_LOCATION_CONTRADICTION", npc_name)

    if game._unsupported_available_quest_claim(narration):
        return reject("UNSUPPORTED_QUEST_CLAIM", "quest availability")

    second_person_verb = game._nsd_second_person_verb()
    player_action_text = text
    player_action_text = game._nsd_npc_target_re_2(npc_target=npc_target, player_action_text=player_action_text, text=text)
    player_action_text = npc_speech_boundary.mask_spoken_questions(
        player_action_text, spoken_start
    )
    normalized_action_text = game._normalize_turkish_typos(
        player_action_text.casefold()
    ).strip()
    npc_name_question = False
    if npc_target:
        npc_name = game._normalize_turkish_typos(
            living_world.public_npc_name(npc_target).casefold()
        ).strip()
        npc_name_question = bool(npc_name) and re.fullmatch(
            re.escape(npc_name) + r"\s+mi\s+dedin[?!.]*",
            normalized_action_text,
        ) is not None
    travel_result = game._nsd_travel_result_action(action_result=action_result)
    observe_result = game._nsd_observe_result_action(action_result=action_result)
    agency_prefixes = game._nsd_agency_prefixes_cek()
    travel_prefixes = (
        "ulas", "var", "gir", "git", "yuru", "gec", "ilerle", "don", "yaklas"
    )
    if action_result.get("proposal_required"):
        # This walk is told before it happens, so its present-tense verbs are the walk itself.
        travel_prefixes += ("gid", "ilerl", "uzakl", "yonel")
    input_verb_suffixes = game._nsd_input_verb_suffixes()
    input_verb_stems = set()
    for word in re.findall(
        r"[a-zçğıöşü]+", game._normalize_turkish_typos(input_text)
    ):
        if word in agency_prefixes:
            input_verb_stems.add(word)
            continue
        for suffix in input_verb_suffixes:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                input_verb_stems.add(word[:-len(suffix)])
                break
    for match in second_person_verb.finditer(player_action_text):
        if game._normalize_turkish_typos(match.group(1)) in input_verb_stems:
            continue
        normalized_verb = game._normalize_turkish_typos(match.group(0))
        if normalized_verb.startswith("gel") and re.search(
            r"\bho[sş]\s*$", game._normalize_turkish_typos(player_action_text[:match.start()])
        ):
            # "Hoş geldin(iz)" is the ordinary welcome, not a claim of arrival.
            continue
        if npc_name_question and normalized_verb.startswith("de"):
            # This exact NPC-attributed clarifying question asks whether the
            # player said the NPC's name; it does not commit a player action.
            continue
        if normalized_verb.endswith(
            ("abilirsin", "ebilirsin", "abilirsiniz", "ebilirsiniz")
        ):
            # Modal ability preserves player choice; it does not state that
            # the player actually performs the action.
            continue
        if observe_result and normalized_verb.startswith(
            ("gor", "duy", "isit", "sez", "algila", "gozlemle", "hisset")
        ):
            continue
        # "Seslerin arasında kaybolmak" is a common sensory metaphor, not a
        # literal travel-state change. Literal disorientation remains blocked.
        if normalized_verb.startswith("kaybol") and re.search(
            r"\b(?:ses|seslerin|isik|isiklar|koku|aroma|muzik)\w*\b.{0,55}"
            r"\b(?:arasında|icinde|arasinda)\b",
            player_action_text[:match.start()],
        ):
            continue
        is_clear_agency = normalized_verb.startswith(agency_prefixes)
        nearby_decision = player_action_text[max(0, match.start() - 55):match.end() + 15]
        is_clear_agency = is_clear_agency or bool(re.search(
            r"\b(?:kabul|onay|anlas\w*|karar|soz|yalan|gercek ad\w*|"
            r"sec\w*|tercih|inan\w*|guven\w*)\b",
            nearby_decision,
        ))
        if normalized_verb.startswith("et") and re.search(
            r"\bkabul\b", nearby_decision
        ):
            # The calibration corpus classifies unverified consent as a
            # mental-state claim; keep the claim rejected under that reason.
            continue
        if not is_clear_agency:
            continue
        # "Bir tane alırsın": what an NPC says the player may do, not what the player did.
        if (
            spoken_start is not None and match.start() >= spoken_start
            and re.search(r"[aeiu]rsin$", normalized_verb)
            and not re.match(r"gir|cik|git|gid|yuru|don", normalized_verb)  # a walk told this way still moves the player
        ):
            continue
        committed_step = normalized_verb.startswith("at") and re.search(
            r"\badım\s*$", text[:match.start()]
        )
        if travel_result and (
            normalized_verb.startswith(travel_prefixes) or committed_step
        ):
            continue
        return reject("INVENTED_PLAYER_ACTION", match.group(0))

    mental_state_trigger = game._unverified_player_mental_state_trigger(
        player_action_text, second_person_verb
    )
    feeling = game._PLAYER_FEELING_RE.search(player_action_text)
    if feeling and not mental_state_trigger:
        mental_state_trigger = feeling.group(0)
    if mental_state_trigger:
        return reject("INVENTED_PLAYER_MENTAL_STATE", mental_state_trigger)

    unsupported_goal = game._nsd_unsupported_goal_re(text=text)
    _exit = game._nsd_travel_result_unsupported(input_text=input_text, reject=reject, travel_result=travel_result, unsupported_goal=unsupported_goal)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    for sitting in re.finditer(r"\bbirlikte\s+(otur\w*)\b", text):
        if (
            isinstance(action_result, dict)
            and action_result.get("action") == "sit"
            and action_result.get("status") == "completed"
            and action_result.get("success") is True
        ):
            continue
        if (
            spoken_start is not None and sitting.start() >= spoken_start
            and npc_speech_boundary.is_nonassertive_collective(
                sitting.group(1), text[sitting.end():sitting.end() + 100]
            )
        ):
            continue
        return reject("INVENTED_PLAYER_ACTION", sitting.group(0))
    forced_player_action = game._nsd_forced_player_action(text=text)
    if forced_player_action:
        return reject("INVENTED_PLAYER_ACTION", forced_player_action.group(0))
    unsolicited_offer = game._nsd_unsolicited_offer_re(text=text)
    if unsolicited_offer and not npc_speech and not any(
        term in input_text for term in ("iç", "yemek", "bira", "kahve", "şarap", "otur")
    ):
        return reject("UNSOLICITED_PLAYER_CHOICE", unsolicited_offer.group(0))
    unsupported_transfer = game._nsd_unsupported_transfer_re()
    for transfer_claim in unsupported_transfer.finditer(text):
        if game._is_explicitly_negated_transfer(transfer_claim, text):
            continue
        if (
            "anahtar" in transfer_claim.group(0).casefold()
            and game._is_figurative_key_transfer(text, transfer_claim.start())
        ):
            continue
        if not game._authorized_item_transfer_matches(
            transfer_claim.group(0), action_result
        ):
            return reject("UNSUPPORTED_ITEM_TRANSFER", transfer_claim.group(0))
    inventory_transfer = game._nsd_inventory_transfer_re()
    for transfer_claim in inventory_transfer.finditer(text):
        if game._is_explicitly_negated_transfer(transfer_claim, text):
            continue
        if not game._authorized_item_transfer_matches(
            transfer_claim.group(0), action_result
        ):
            return reject("UNSUPPORTED_ITEM_TRANSFER", transfer_claim.group(0))
    generic_transfer = re.search(
        r"\b(?:ikram ed\w*|sana.{0,40}(?:verir|verilir|sunar|uzatır|uzatılır|hediye eder))\b",
        text,
    )
    if generic_transfer and not game._authorized_item_transfer_matches(
        generic_transfer.group(0), action_result
    ):
        return reject("UNSUPPORTED_ITEM_TRANSFER", generic_transfer.group(0))

    _exit = game._nsd_npc_target_re(input_text=input_text, npc_target=npc_target, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    registered_names = game._nsd_registered_names_str(world_state=world_state)
    registered_name_tokens = {
        part for name in registered_names for part in name.split()
    }
    known_places = {str(world_state.get("location", "")).casefold()}
    for location in world_state.get("locations", {}).values():
        known_places.update(alias.casefold() for alias in game._location_alias_values(location))
    known_place_forms = {
        game._normalize_turkish_typos(place) for place in known_places if place
    }
    for place in tuple(known_place_forms):
        game._nsd_known_place_forms(known_place_forms=known_place_forms, place=place)
    name_patterns = game._NARRATED_NAME_PATTERNS
    unseen_people = game._unseen_registered_names(world_state)
    import npc_speech_boundary
    entity_narration = npc_speech_boundary.narrated_entity_text(
        narration, attributed_speech, npc_target, action_result
    )
    def reject_entity(trigger=None):
        verdict = reject("UNREGISTERED_NAMED_ENTITY", trigger)
        if entity_narration != narration:
            verdict["source_field"] = "stage_direction"
        return verdict
    entity_scan = npc_speech_boundary.mask_visible_entity_labels(entity_narration, world_state)
    for pattern in name_patterns:
        for match in re.finditer(pattern, entity_scan):
            quote_prefix = entity_narration[:match.start()].rstrip()
            if match.group(1).casefold() == "bir" and quote_prefix.endswith(
                ("'", "’", '"', "“", "‘")
            ):
                continue
            candidate = match.group(1).casefold()
            if candidate in game._COMMON_SENTENCE_OPENERS:
                continue
            normalized_candidate = game._normalize_turkish_typos(candidate)
            if candidate not in (
                registered_names | registered_name_tokens | known_places
            ) and normalized_candidate not in known_place_forms:
                if game._authorized_item_transfer_matches(match.group(1), action_result):
                    continue
                # W05: a common scene object is not an invented person; unknown names still fail closed.
                import referent_span
                if referent_span.classify_referent_span(
                    match.group(1),
                    {npc_statements.fold(npc.get("name", "")): npc.get("id")
                     for npc in world_state.get("npcs", []) if isinstance(npc, dict) and npc.get("name")},
                    {"scene_texts": game._scene_texts_for_referents(world_state)}
                )["kind"] == "common_object":
                    continue
                return reject_entity(match.group(1))
    if game._has_unregistered_person_name(entity_scan):
        return reject_entity()
    # A saved person who is not here cannot speak or arrive in this scene, nor introduce themselves in a line.
    # Inside someone's speech, any other use of the name is a mention.
    unseen_speakers = game._unseen_speakers(entity_scan, unseen_people)
    if unseen_speakers:
        start, end = unseen_speakers[0]
        return reject_entity(entity_narration[start:end])
    introductions = game._unseen_self_introductions(entity_narration, unseen_people)
    if introductions:
        return reject_entity(local_dialogue.explicit_player_name_disclosure(introductions[0][2][0]))

    unregistered_object = game._unregistered_persistent_object_claim(
        world_state, narration
    )
    if unregistered_object:
        return reject("UNREGISTERED_PERSISTENT_OBJECT", unregistered_object)
    held_object = game._unregistered_held_object(world_state, narration)
    held_action = action_result.get("action") if isinstance(action_result, dict) else None
    held_outcome = action_result.get("outcome") if isinstance(action_result, dict) else None
    _exit = game._nsd_held_object_held(held_action=held_action, held_object=held_object, held_outcome=held_outcome, reject=reject)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    arrival_sentences = game._nsd_arrival_sentences_re(arrival_text=arrival_text)
    completed_player_arrival = game._nsd_completed_player_arrival()
    for location_id, location in world_state.get("locations", {}).items():
        if location_id == current_location:
            continue
        aliases = game._location_alias_values(location) or [game.location_display_name(location_id)]
        for alias in aliases:
            normalized_alias = game._normalize_turkish_typos(alias.casefold())
            if not normalized_alias:
                continue
            alias_pattern = re.compile(
                rf"(?<![a-z0-9çğıöşü]){re.escape(normalized_alias)}"
            )
            for sentence in arrival_sentences:
                if "?" in sentence:
                    continue
                normalized_sentence = game._normalize_turkish_typos(sentence)
                if (
                    alias_pattern.search(normalized_sentence)
                    and completed_player_arrival.search(normalized_sentence)
                ):
                    return reject("CANONICAL_LOCATION_CONTRADICTION", alias)

    # A registered NPC at another location cannot appear, speak, or approach
    # in the current scene merely because the model remembers the name.
    for npc in world_state.get("npcs", []):
        npc_location = npc.get("location")
        npc_name = str(npc.get("name", "")).strip()
        if not npc_name or not npc_location or npc_location == current_location:
            continue
        normalized_name = game._normalize_turkish_typos(npc_name.casefold())
        if not normalized_name:
            continue
        name_pattern = rf"(?<![a-z0-9çğıöşü]){re.escape(normalized_name)}(?![a-z0-9çğıöşü])"
        if not re.search(name_pattern, game._normalize_turkish_typos(text)):
            continue
        duplicate_ids = [
            candidate for candidate in world_state.get("npcs", [])
            if str(candidate.get("name", "")).casefold() == npc_name.casefold()
        ]
        if len(duplicate_ids) > 1:
            targeted_id = (npc_target or {}).get("id")
            if not targeted_id or all(
                candidate.get("id") != targeted_id
                for candidate in duplicate_ids
            ):
                return reject("AMBIGUOUS_NPC_IDENTITY", npc_name)
            if next(
                (candidate for candidate in duplicate_ids
                 if candidate.get("id") == targeted_id),
                {},
            ).get("location") == current_location:
                continue
        present_action = re.search(
            name_pattern + r".{0,28}(?:[\"“]|gözleri|başını|yanına|"
            r"yaklaş\w*|konuş\w*|yanıt ver\w*|der\b|durur\b)",
            game._normalize_turkish_typos(text),
        )
        if present_action:
            return reject("CANONICAL_NPC_LOCATION_CONTRADICTION", npc_name)

    hard_claims = game._nsd_hard_claims_canonical()
    for reason_code, pattern in hard_claims:
        claims = (
            list(re.finditer(pattern, text))
            if reason_code == "CANONICAL_DAMAGE_CONTRADICTION"
            else [re.search(pattern, text)]
        )
        for claim in filter(None, claims):
            if (
                reason_code == "CANONICAL_DAMAGE_CONTRADICTION"
                and is_verified_attack_damage_claim(claim)
            ):
                continue
            return reject(reason_code, claim.group(0))

    quest_outcomes = action_result.get("quest_outcomes")
    quest_transition = game._nsd_quest_transition_re(text=text)
    if quest_transition and not quest_outcomes:
        return reject("CANONICAL_QUEST_CONTRADICTION", quest_transition.group(0))

    weather_change = re.search(
        r"\b(?:hava|gökyüzü)\b.{0,35}\b(?:değişir|kararır|açılır|soğur|ısınır)\b",
        text,
    )
    if weather_change:
        return reject("CANONICAL_WEATHER_CHANGE", weather_change.group(0))

    for npc in world_state.get("npcs", []):
        defeated = (
            npc.get("combat_status") in {"unconscious", "defeated", "dead"}
            or npc.get("current_hp", 1) <= 0
        )
        npc_name = str(npc.get("name", "")).strip()
        if not defeated or not npc_name:
            continue
        normalized_name = game._normalize_turkish_typos(npc_name.casefold())
        resurrection = game._nsd_resurrection_re_search(normalized_name=normalized_name, text=text)
        if resurrection:
            return reject("DEFEATED_ENTITY_RESURRECTION", npc_name)

    _exit = game._nsd_any_phrase_text(reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    outcome = action_outcome or game._mechanical_outcome(player_input)
    _exit = game._nsd_outcome_failure_critical(action_result=action_result, outcome=outcome, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._nsd_outcome_success_critical(action_result=action_result, outcome=outcome, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._nsd_kap_input_text(input_text=input_text, outcome=outcome, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    door = game._current_door()
    _exit = game._nsd_door_open_claim(door=door, reject=reject, text=text)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    import narration_claims
    verdict = narration_claims.assess(narration, game._narration_fact_packet(action_result))
    if verdict["reject"]:
        return reject(verdict["reason"] or "NARRATION_CLAIM_REJECTED", verdict.get("span"))

    _exit = game._nsd_speech_fields_narration(reject=reject, speech_fields=speech_fields, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._nsd_combat_lifecycle_quoted(narration=narration, narration_claims=narration_claims, player_input=player_input, reject=reject)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    return accept()
