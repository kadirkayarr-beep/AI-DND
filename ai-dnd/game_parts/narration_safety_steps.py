import campaign_time
import combat_lifecycle
import living_world
import re
import game


def _nsd_speech_fields_narration(*, reject, speech_fields, world_state):
    # Attributed words may be rumors; the optional narrator field is not speech.
    # Reuse the narrator's existing lore authority, never the model's claim IDs.
    if speech_fields is not None and game._narration_has_unsupported_lore_claim(
        speech_fields[1], [],
        game._prepare_lore_authority_context(getattr(game._session(), "lore_authority_context", None)),
        world_state,
    ):
        return {**reject("UNVERIFIED_LORE_CLAIM"), "source_field": "stage_direction"}
    return game._TURN_FALL_THROUGH


def _nsd_door_open_claim(*, door, reject, text):
    if door:
        # (what the narration says, whether the door's real state contradicts it); the first contradiction rejects
        claims = (
            (r"(?:kapı|kapısı|giriş)\b.{0,35}\b"
             r"(?:açıldı|açılır|açık|aralandı|aralanır|kırıldı|parçalandı)\b", lambda: not door["open"]),
            (r"(?:kapı|kapısı|giriş)\b.{0,35}\b(?:kapalı|kilitli)\b", lambda: door["open"]),
            (r"(?:kapı|kapısı)\b.{0,35}\b(?:kırıldı|parçalandı|yıkıldı)", lambda: not door.get("broken", False)),
            (r"(?:kilit|kapı|kapısı)\b.{0,35}\b(?:açıldı|kilitsiz|çözüldü)", lambda: door["locked"]),
            (r"(?:kilit|kapı|kapısı)\b.{0,35}\bkilitli\b", lambda: not door["locked"]),
        )
        for pattern, contradicted in claims:
            claim = re.search(pattern, text)
            if claim and contradicted():
                return reject("DOOR_STATE_CONTRADICTION", claim.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_kap_input_text(*, input_text, outcome, reject, text):
    if ("kapı" in input_text or "kilit" in input_text) and outcome in (
        "failure", "critical_failure"
    ):
        opened_door = re.search(
            r"(?:kapı|kapısı|giriş).{0,35}(?:açılır|aralanır|açık olur)",
            text,
        )
        if opened_door:
            return reject("DOOR_RESULT_CONTRADICTION", opened_door.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_outcome_success_critical(*, action_result, outcome, reject, text):
    if outcome in ("success", "critical_success"):
        contradicted_failure = re.search(r"başarısız olur|başaramaz", text)
        if contradicted_failure:
            return reject("SKILL_RESULT_CONTRADICTION", contradicted_failure.group(0))
        unmoved = game._UNMOVED.search(game._normalize_turkish_typos(text)) if action_result.get("skill") == "Intimidation" else None
        if unmoved:
            return reject("SKILL_RESULT_CONTRADICTION", unmoved.group(0))  # D-226: a won scare moves the person
    return game._TURN_FALL_THROUGH


def _nsd_outcome_failure_critical(*, outcome, reject, text):
    if outcome in ("failure", "critical_failure"):
        contradicted_success = re.search(
            r"başarılı olur|başarıya ulaşır|başarır|kazanırsın|"
            r"izleri bul\w*|gizli geçidi bul\w*|"
            r"hedefi tespit ed\w*",
            text,
        )
        if contradicted_success:
            return reject("SKILL_RESULT_CONTRADICTION", contradicted_success.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_any_phrase_text(*, reject, text):
    if any(phrase in text for phrase in (
        "duvar çatırdar", "duvar çatlar", "duvar yıkılır", "duvar kırılır",
        "kapı parçalanır", "kapı kırılır", "karakterin ölür", "öldün",
        "uçmaya başlarsın", "envanterine eklenir", "envanterinden çıkar"
    )):
        return reject("CANONICAL_STATE_CONTRADICTION")
    return game._TURN_FALL_THROUGH


def _nsd_quest_transition_re(*, text):
    quest_transition = re.search(
        r"\b(?:görev|görevi|hedef|amaç)\b.{0,55}"
        r"\b(?:tamamlandı|tamamladın|bitirdin|kabul ettin|iptal edildi|"
        r"ilerledi|ilerletildi|başladı)\b",
        text,
    )
    return quest_transition


def _nsd_hard_claims_canonical():
    # Major canonical mutations are not free-form narration. This list targets
    # explicit state changes while leaving sensory weather and scenery prose open.
    hard_claims = (
        ("CANONICAL_HP_CONTRADICTION",
         r"\b(?:hp|isabet puan\w*|can puan\w*|sağlık puan\w*)\b.{0,24}\b\d+\b|"
         r"\b\d+\s*(?:hp|isabet puan\w*|can puan\w*)\b"),
        ("CANONICAL_DAMAGE_CONTRADICTION",
         r"\b\d+\s*(?:puan\s+)?hasar\b.{0,25}\b(?:al\w*|ver\w*|uğra\w*)"),
        ("CANONICAL_REWARD_CONTRADICTION",
         r"\b(?:\d+\s*(?:altın|gp)|(?:altın|gp)\s+\d+)\b.{0,35}"
         r"\b(?:kazan\w*|al\w*|elde et\w*|bul\w*)|"
         r"\b(?:kazan\w*|al\w*|elde et\w*)\b.{0,35}\b\d+\s*(?:altın|gp)\b"),
        ("CANONICAL_XP_CONTRADICTION",
         r"\b(?:deneyim puan\w*|xp)\b.{0,35}\b(?:kazan\w*|al\w*|elde et\w*)|"
         r"\b(?:kazan\w*|al\w*|elde et\w*)\b.{0,35}\b(?:deneyim puan\w*|xp)\b"),
        ("CANONICAL_LEVEL_CONTRADICTION",
         r"\b(?:seviye atla\w*|level up|seviye\w* yüksel\w*)\b"),
        ("CANONICAL_SPELL_CONTRADICTION",
         r"\b(?:ateş|ışık|yıldırım|buz|koruma|iyileştirme)\s+büyüsü\b"
         r".{0,45}\b(?:belir\w*|oluş\w*|etki et\w*|vur\w*)"),
        ("CANONICAL_WEATHER_CHANGE",
         r"\b(?:yağmur|kar|fırtına|sis)\b.{0,35}\b(?:başla\w*|din\w*|dur\w*|"
         r"kesil\w*|güçlen\w*)|"
         r"\b(?:başla\w*|din\w*|dur\w*|kesil\w*)\b.{0,35}"
         r"\b(?:yağmur|kar|fırtına|sis)\b"),
    )
    return hard_claims


def _nsd_npc_target_re(*, input_text, npc_target, reject, text):
    if npc_target:
        if re.search(r"\b(?:adın ne|ismin ne|barmenin adı ne)\b", input_text):
            asks_player_name = re.search(
                r"\b(?:sana|oyuncuya)\b.{0,70}\b(?:sorar|soruyor|diye sorar)\b"
                r".{0,70}\b(?:adın|ismin)\s+ne\b",
                text,
            )
            if asks_player_name:
                return reject("NPC_REPLY_MISMATCH", asks_player_name.group(0))
        if re.search(
            r"\b(?:burada ne zamandır|kaç yıldır|ne kadar süredir)\b"
            r".{0,50}\b(?:çalış|burada|taverna)",
            input_text,
        ):
            has_relevant_reply = re.search(
                r"\b(?:yıl\w*|ay\w*|gün\w*|çalış\w*|uzun süredir|bir süredir|"
                r"yeni başladım|bilmiyorum|hatırlamıyorum|emin değilim|"
                r"doğrulanmış bilgi yok)\b",
                text,
            )
            if not has_relevant_reply:
                return reject("NPC_REPLY_MISMATCH")
    return game._TURN_FALL_THROUGH


def _nsd_unsupported_transfer_re():
    unsupported_transfer = re.compile(
        r"\b(?:kahve|bira(?!z)|şarap|yemek|bardak|kadeh|eşya|silah|kılıç|"
        r"tılsım|mühür|iksir|altın|(?:han[ıi]n\s+)?anahtar)\w*\b.{0,55}?"
        r"\b(?P<transfer_verb>önüne bırak\w*|eline ver\w*|sana uzat\w*|"
        r"uzat\w*|bırak\w*|ikram et\w*|ver\w*|hediye et\w*|"
        r"envanterine eklen\w*|teslim et\w*)",
        re.IGNORECASE,
    )
    return unsupported_transfer


def _nsd_travel_result_unsupported(*, input_text, reject, travel_result, unsupported_goal):
    if travel_result and unsupported_goal and not re.search(
        r"\b(?:izini|yolunu|gizli yolu|kaynağı)\b.{0,55}"
        r"\b(?:bul|ara|takip et)\w*",
        input_text,
    ):
        return reject("INVENTED_PLAYER_OBJECTIVE", unsupported_goal.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_unsupported_goal_re(*, text):
    unsupported_goal = re.search(
        r"\b(?:izini|yolunu|gizli yolu|kaynağı)\b.{0,55}"
        r"\b(?:bulmak|aramak|takip etmek)\b.{0,75}"
        r"\b(?:gitmelisin|gitmelisiniz|aramalısın|aramalısınız|bulmalısın|bulmalısınız)\b",
        text,
    )
    return unsupported_goal


def _nsd_input_verb_suffixes():
    input_verb_suffixes = tuple(sorted((
        "iyorum", "ıyorum", "uyorum", "üyorum",
        "ıyorsun", "iyorsun", "uyorsun", "üyorsun",
        "ıyor", "iyor", "uyor", "üyor",
        "ıyordum", "iyordum", "uyordum", "üyordum",
        "dım", "dim", "dum", "düm", "tım", "tim", "tum", "tüm",
        "dın", "din", "dun", "dün", "tın", "tin", "tun", "tün",
        "di", "dı", "du", "dü", "ti", "tı", "tu", "tü",
        "yorum",
        "erim", "arım", "irim", "ırım", "ürüm", "urum",
        "eceğim", "acağım", "eceksin", "acaksın",
        "ayip", "eyip", "yip", "yup",
        "mak", "mek",
    ), key=len, reverse=True))
    return input_verb_suffixes


def _nsd_agency_prefixes_cek():
    agency_prefixes = (
        "cek", "cikar", "savur", "vur", "saldir", "sapla", "firlat", "it",
        "tekme", "soyle", "konus", "anlat", "itiraf", "fisilda", "bagir",
        "sor", "yanitla", "de", "git", "gel", "yuru", "kos", "ilerle",
        "ilerli",
        "yaklas", "don", "gir", "cik", "gec", "kaybol", "saklan", "atla",
        "tirman", "yuz", "kac", "otur", "kalk", "al", "ver", "ic", "ye",
        "giy", "kullan", "tasi", "ac", "kapat", "imzala", "guven", "inan",
        "dusun", "karar", "kabul", "onay", "anlas", "suphelen", "sec",
        "ara", "bul",
        "tercih", "vaat", "soz"
    )
    return agency_prefixes


def _nsd_second_person_verb():
    # Suffixes alone are not proof of player agency in Turkish. Only reject
    # clear actions, commitments, speech, or movement; sensory language and
    # ordinary nouns such as "tütün" are not treated as verbs.
    second_person_verb = re.compile(
        r"\b(?!kadın\b|adın\b|çadırın\b|yardımın\b|sırrın\b)"
        r"([a-zçğıöşü]{2,}?)(?:dın|din|dun|dün|(?<=[çfhkpsşt])(?:tın|tin|tun|tün)|"
        r"yorsun|ıyorsun|iyorsun|uyorsun|üyorsun|arsın|ersin|"
        r"ırsın|irsin|ursun|ürsün|mışsın|mişsin|muşsun|müşsün|"
        r"dınız|diniz|dunuz|dünüz|(?<=[çfhkpsşt])(?:tınız|tiniz|tunuz|tünüz)|"
        r"sınız|siniz|sunuz|sünüz|acaksın|eceksin)\b"
    )
    return second_person_verb


def _nsd_action_outcome_mechanical(*, action_outcome, player_input, reject, text):
    if (action_outcome or game._mechanical_outcome(player_input)) in (
        "failure", "critical_failure"
    ):
        failed_check_claim = re.search(
            r"başarılı olur|başarıya ulaşır|başarır|kazanırsın|"
            r"izleri bul\w*|gizli geçidi bul\w*|hedefi tespit ed\w*",
            text,
        )
        if failed_check_claim:
            return reject("SKILL_RESULT_CONTRADICTION", failed_check_claim.group(0))
        reported_find = re.search(
            r"fark ed|goruyorsun|buluyorsun|secebiliyorsun",
            game._normalize_turkish_typos(text),
        )
        if reported_find:
            return reject("SKILL_RESULT_CONTRADICTION", reported_find.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_pre_agency_claims():
    # Resolve clear canonical claims before the more general player-agency
    # matcher so diagnostics identify the actual state contradiction.
    pre_agency_claims = (
        ("CANONICAL_HP_CONTRADICTION",
         r"\b(?:hp|isabet puan\w*|can puan\w*|sağlık puan\w*)\b.{0,24}\b\d+\b|"
         r"\b\d+\s*(?:hp|isabet puan\w*|can puan\w*)\b"),
        ("CANONICAL_DAMAGE_CONTRADICTION",
         r"\b\d+\s*(?:puan\s+)?hasar\b.{0,25}\b(?:al\w*|ver\w*|uğra\w*)"),
        ("CANONICAL_REWARD_CONTRADICTION",
         r"\b(?:\d+\s*(?:altın|gp)|(?:altın|gp)\s+\d+)\b.{0,35}"
         r"\b(?:kazan\w*|al\w*|elde et\w*|bul\w*)|"
         r"\b(?:kazan\w*|al\w*|elde et\w*)\b.{0,35}\b\d+\s*(?:altın|gp)\b"),
        ("CANONICAL_XP_CONTRADICTION",
         r"\b(?:deneyim puan\w*|xp)\b.{0,35}\b(?:kazan\w*|al\w*|elde et\w*)|"
         r"\b(?:kazan\w*|al\w*|elde et\w*)\b.{0,35}\b(?:deneyim puan\w*|xp)\b"),
        ("CANONICAL_LEVEL_CONTRADICTION",
         r"\b(?:seviye atla\w*|level up|seviye\w* yüksel\w*)\b"),
    )
    return pre_agency_claims


def _nsd_npc_speech_quoted(*, conditional, npc_speech, text):
    if not npc_speech:
        quoted_spans = [
            (quoted.start(), quoted.end())
            for quoted in re.finditer(r'"[^"]*"|“[^”]*”', text)
        ]
        # A person's quoted "istersen" is an offer in their voice, not a choice
        # the narrator makes for the player; only unquoted text is rejected.
        conditional = next(
            (
                found for found in re.finditer(
                    r"\b(?:istersen|dilersen|açtıysan|başardıysan)\b"
                    r"|\beğer\b.{0,80}\b\w*(?:rsen|rsanız)\b",
                    text,
                )
                if not any(start <= found.start() < end for start, end in quoted_spans)
            ),
            None,
        )
    return conditional


def _nsd_greeting_only_quoted(*, greeting_only, narration, reject):
    if greeting_only:
        for quoted in re.findall(r"['\"“‘]([^'\"”’]{3,220})['\"”’]", narration):
            spoken = game._normalize_turkish_typos(quoted)
            if (
                re.search(r"\b(?:gormedim|duymadim|hatirlamiyorum|"
                          r"hatirlamadim|soylemedim|konusmadik)\b", spoken)
                and not re.search(r"\b(?:merhaba|selam|gunaydin|"
                                  r"hos geldin\w*|iyi gunler|iyi aksamlar)\b", spoken)
            ):
                return reject("UNRELATED_GREETING_REPLY", quoted)

        # Editorial summaries of a scene are not in-world NPC responses.
        meta = re.search(
            r"\bbu\s+(?:kisa\s+)?(?:etkilesim|konusma|sahne)\b"
            r".{0,130}\b(?:orneg\w*|yansitir\w*)\b",
            game._normalize_turkish_typos(narration),
        )
        if meta:
            return reject("META_NARRATOR_COMMENTARY", meta.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_action_result_action(*, action_result, narration, npc_target, reject, speech_fields, world_state):
    if (
        isinstance(action_result, dict)
        and action_result.get("status") == "experimental_attributed_speech"
        and game._experimental_private_npc_disclosure(
            narration, world_state, npc_target=npc_target, speech_fields=speech_fields
        )
    ):
        return reject("NPC_PRIVATE_PROFILE_DISCLOSURE")
    return game._TURN_FALL_THROUGH


def _nsd_known_place_forms(*, known_place_forms, place):
    known_place_forms.update(
        place + suffix
        for suffix in (
            "i", "u", "a", "e", "in", "un", "nin", "nun",
            "da", "de", "ta", "te", "dan", "den", "tan", "ten",
            "la", "le", "yla", "yle",
        )
    )


def _nsd_speaker_label_label(*, npc_target, reject, speaker_label, target_name):
    if speaker_label:
        label = game._normalize_turkish_typos(speaker_label.group(1).casefold())
        allowed_labels = {
            game._normalize_turkish_typos(target_name.casefold()),
            game._normalize_turkish_typos(
                str(living_world.public_npc_name(npc_target) or "").casefold()
            ),
        }
        if label and label not in allowed_labels:
            return reject(
                "WRONG_NPC_SPEAKER_ATTRIBUTION", speaker_label.group(1)
            )
    return game._TURN_FALL_THROUGH


def _nsd_combat_lifecycle_quoted(*, narration, narration_claims, player_input, reject):
    if combat_lifecycle.quoted_or_conditional_not_attack(game._session(), player_input):
        folded_narration = narration_claims.fold(narration)
        fight = re.search(r"\b(?:saldir|savun)\w*|\bkan\b", folded_narration)
        if fight:
            return reject("REPORTED_NON_ATTACK", fight.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_completed_player_arrival():
    completed_player_arrival = re.compile(
        r"\b(?:vardin|variyorsun|ulastin|ulasiyorsun|geldin|geliyorsun|"
        r"girdin|giriyorsun|bulundun|bulunuyorsun|icindesin|iceridesin|"
        r"varis\s+gercekles\w*)\b"
    )
    return completed_player_arrival


def _nsd_arrival_sentences_re(*, arrival_text):
    arrival_sentences = re.split(
        r"(?<=[.!?;,:])\s+|\s+\b(?:ama|ancak|fakat|oysa|ve|ya da|yoksa)\b\s+",
        arrival_text,
        flags=re.IGNORECASE,
    )
    return arrival_sentences


def _nsd_held_object_held(*, held_action, held_object, held_outcome, reject):
    if held_object and (
        held_action == "narrative"
        or held_outcome in {"failure", "critical_failure"}
    ):
        return reject("UNREGISTERED_PERSISTENT_OBJECT", held_object)
    return game._TURN_FALL_THROUGH


def _nsd_registered_names_str(*, world_state):
    registered_names = {
        str(npc.get("name", "")).casefold()
        for npc in world_state.get("npcs", [])
        if npc.get("name")
    }
    return registered_names


def _nsd_inventory_transfer_re():
    inventory_transfer = re.compile(
        r"\benvanter\w*.{0,55}?\b(?:eklen\w*|aktarıl\w*|çıkarıl\w*|"
        r"cikaril\w*|girer\w*|ekle\w*)",
        re.IGNORECASE,
    )
    return inventory_transfer


def _nsd_unsolicited_offer_re(*, text):
    unsolicited_offer = re.search(
        r"\b(?:içelim|yiyelim|oturalım|kahve iç|bira iç|şarap iç|yemek ye|"
        r"ne içmek istersin|ne içersin|içmek ister misin|bir şey içmek ister misin)\b",
        text,
    )
    return unsolicited_offer


def _nsd_forced_player_action(*, text):
    forced_player_action = re.search(
        r"\b(?:seni|sana)\b.{0,50}"
        r"\b(?:oturt\w*|içir\w*|yedir\w*|giydir\w*|aldır(?!m|ış)\w*|kaldır\w*)\b",
        text,
    )
    return forced_player_action


def _nsd_observe_result_action(*, action_result):
    observe_result = (
        action_result.get("action") == "explore"
        and action_result.get("status") == "resolved"
        and action_result.get("explore_type") == "observe"
    )
    return observe_result


def _nsd_travel_result_action(*, action_result):
    travel_result = (
        action_result.get("action") == "travel"
        and action_result.get("status") == "completed"
        and action_result.get("success") is True
    )
    return travel_result


def _nsd_npc_target_re_2(*, npc_target, player_action_text, text):
    # Quoted words are somebody's speech, not the narrator committing the
    # player; that holds with or without a resolved addressee.
    if npc_target or re.search(r'"[^"]+"|“[^”]+”', text):
        quotes = re.compile(r'"[^"]*"|“[^”]*”|‘[^’]*’|\'[^\']*\'')
        player_action_text = quotes.sub(
            lambda quoted: " " * len(quoted.group(0)), text
        )
    return player_action_text


def _nsd_committed_travel_action(*, action_result):
    committed_travel = (
        action_result.get("action") == "travel"
        and action_result.get("status") == "completed"
        and action_result.get("success") is True
    )
    return committed_travel


def _nsd_uncommitted_departure_re(*, arrival_text):
    uncommitted_departure = re.search(
        r"\b(?:sehrin|kasabanin|yerlesimin)(?:\s+sinirl\w*)?\s+"
        r"(?:disina|otesine)\s+(?:cik\w*|gec\w*)\b",
        game._normalize_turkish_typos(arrival_text.casefold()),
    )
    return uncommitted_departure


def _nsd_elapsed_claim_claimed(*, action_result, elapsed_claim, reject):
    if elapsed_claim:
        claimed = campaign_time.requested_duration(elapsed_claim.group(1))
        verified = action_result.get("time_result", {}).get("elapsed_seconds", 0)
        if claimed != verified:
            return reject("UNVERIFIED_ELAPSED_TIME", elapsed_claim.group(0))
    return game._TURN_FALL_THROUGH


def _nsd_elapsed_claim_re(*, narration):
    elapsed_claim = re.search(
        r"((?:\d+|bir|iki|üç|dört|beş|altı|yarım)\s+(?:saniye|dakika|saat|gün))"
        r"\s+(?:geçti|geçiyor|sonra|boyunca)",
        narration, re.IGNORECASE,
    )
    return elapsed_claim


def _nsd_resurrection_re_search(*, normalized_name, text):
    resurrection = re.search(
        rf"(?<![a-z0-9çğıöşü]){re.escape(normalized_name)}(?![a-z0-9çğıöşü])"
            r".{0,55}\b(?:ayaga kalk\w*|gozlerini ac\w*|hayata don\w*|"
            r"yeniden canlan\w*|konus\w*|saldir\w*)",
        game._normalize_turkish_typos(text),
    )
    return resurrection


def _nsd_speaker_pattern_rf(*, norm_other):
    speaker_pattern = (
        rf"\b{re.escape(norm_other)}\b.{{0,40}}(?:der|yanit\s+verir|cevap\s+verir|fisildar|konusur|seslenir|soyler)\b|"
                rf"\b{re.escape(norm_other)},\s*[\"“]|"
                rf"[\"“][^\"”]{{1,200}}[\"”]\s*(?:diye\s+)?(?:der|yanit\s+verir|cevap\s+verir|fisildar|konusur|seslenir|soyler)\s+{re.escape(norm_other)}\b|"
                rf"\b{re.escape(norm_other)}\s+sana\s+.{{0,40}}(?:diye\s+)?(?:hitap\s+eder|seslenir|der|yanit\s+verir)\b"
    )
    return speaker_pattern


def _nsd_allowed_names_normalize(*, npc_target, target_name):
    allowed_names = {
        game._normalize_turkish_typos(target_name.casefold()),
        game._normalize_turkish_typos(
            str(living_world.public_npc_name(npc_target) or "").casefold()
        ),
    }
    return allowed_names
