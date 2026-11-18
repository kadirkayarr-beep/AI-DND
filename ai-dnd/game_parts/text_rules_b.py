import game
import equipment_economy
import re


_NARRATION_PERSISTENT_OBJECT_HEADS = (
    "sandik", "hazine", "anahtar", "silah", "kilic", "kalkan",
    "zirh", "iksir", "kitap", "muhur", "tilsim", "kasa",
)

_NARRATION_PERSISTENT_OBJECT_STATE = (
    "acik", "acildi", "acilmis", "kapali", "kilitli", "kirik", "durur",
    "duruyor", "bulunur", "bulunuyor", "vardir", "var", "yatar", "uzanir",
    "asili",
)

def _registered_persistent_object_names(world_state, include_carried=False):
    """Collect canonical persistent objects that may be described in-scene."""
    location = world_state.get("location")
    scene_names = set()
    carried_names = set()

    def add_name(target, value):
        value = equipment_economy.label(value)
        if isinstance(value, str) and value.strip():
            target.add(value.strip())

    ground_by_location = world_state.get("ground_items_by_location", {})
    if isinstance(ground_by_location, dict):
        values = ground_by_location.get(location, [])
        if isinstance(values, list):
            for value in values:
                add_name(scene_names, value)
    legacy_ground = world_state.get("ground_items", [])
    if isinstance(legacy_ground, list):
        for value in legacy_ground:
            add_name(scene_names, value)

    for container in world_state.get("containers", []):
        if not isinstance(container, dict):
            continue
        if container.get("location") not in (None, location):
            continue
        add_name(scene_names, container.get("name"))
        contents = container.get("contents", [])
        if isinstance(contents, list):
            for value in contents:
                add_name(scene_names, value)

    for feature in world_state.get("features", []):
        if not isinstance(feature, dict) or feature.get("location") != location:
            continue
        add_name(scene_names, feature.get("name"))
        add_name(scene_names, feature.get("description"))

    import exploration
    for door in exploration.visible_doors(world_state):
        if not isinstance(door, dict) or door.get("location") != location:
            continue
        add_name(scene_names, door.get("name"))

    for value in world_state.get("inventory", []):
        add_name(carried_names, value)
    if include_carried:
        scene_names.update(carried_names)
    return scene_names

_HELD_SKIP = frozenset({
    "el", "goz", "yuz", "bas", "omuz", "kol", "parmak", "sac", "agiz",
    "kucuk", "buyuk", "eski", "yeni", "pasli", "tozlu", "tuttugu", "tutan",
})

_PLAYER_MENTAL_STATE_PREFIXES = (
    "anla", "kavra", "dusun", "inan", "guven", "hatirla", "unut",
    "kork", "urk", "endiselen", "kaygilan", "sevin", "uzul", "utan",
    "hoslan", "ist", "arzu", "niyet", "plan", "tercih", "sec",
)

_PLAYER_MENTAL_STATE_CONTEXT_RE = re.compile(
    r"\b(?:idrak|karar|kabul|redd|tercih|arzu|niyet|plan|"
    r"memnun|mutlu|mutsuz|hosnut|uzgun|korkmus|kork|endiseli|kaygili|heyecan|"
    r"keyif|gurur|rahatsiz|hosuna)\b"
)

_PLAYER_MENTAL_STATE_COPULA_RE = re.compile(
    r"\b(?:mutlu|mutsuz|memnun|hoşnut|üzgün|endişeli|kaygılı|"
    r"korkmuş|heyecanlı|kararsız|niyetli|kararlı|istekli)"
    r"(?:sın|sin|sun|sün)\b"
)

_PLAYER_MENTAL_STATE_EXPLICIT_SUBJECT_RE = re.compile(
    r"\b(?:oyuncu|karakter(?:in)?|kahraman(?:ın)?)\b[^.!?;]{0,48}\b"
    r"(?:anla|kavra|düşün|inan|güven|hatırla|unut|kork|ürk|"
    r"endişelen|kaygılan|sevin|üzül|utan|hoşlan|iste|arzu\s+et|"
    r"niyetlen|planla|tercih\s+et|seç|fark\s+et|idrak\s+et|"
    r"mutlu\s+ol|mutsuz\s+ol|memnun\s+ol|hoşnut\s+ol|üzgün\s+ol|"
    r"karar\s+ver|kabul\s+et|reddet)"
    r"\w*(?:d[ıiuü]|t[ıiuü]|yor|m[ıiuü]ş|acak|ecek|r)\b"
)

_PLAYER_MENTAL_STATE_AFFECT_RE = re.compile(
    r"\bseni\b[^.!?;]{0,28}\b(?:korkut|mutlu\s+et|mutsuz\s+et|"
    r"memnun\s+et|rahatsız\s+et|endişelendir)\w*\b"
)

_PLAYER_FEELING_RE = re.compile(
    r"\b(?:(?:gerginlik|tedirginlik|huzursuzluk|korku|endişe|kaygı|heyecan|rahatsızlık|öfke|"
    r"utanç|sevinç|merak|şüphe|gurur|rahatlama|ürperti|pişmanlık)\w*(?:\s+\w+){0,2}|"
    r"\w+[dt][ıiuü]ğ[ıiuü]n[ıiuü]|gibi|"
    r"(?:gergin|tedirgin|huzursuz|rahatsız|endişeli|güvende|rahat))\s+"
    r"(?:hissed\w*|hisset\w*|duyuyorsun|duydun)\b",
    re.IGNORECASE,
)

def _is_figurative_key_transfer(text, match_start):
    prefix = str(text or "")[:match_start].casefold().rstrip(" \t\r\n:;,“”\"'")
    return bool(re.search(r"(?:kalbimin|yüreğimin|yuregimin)$", prefix))

# A capitalised word in a person's place: acting, standing, described, or the speaker before a quote.
_NARRATED_NAME_PATTERNS = (
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})(?:,)?\s+(?=(?:içeri|dışarı|düşünür|korkar|yaklaşır|girer|konuşur|yanıt verir|şöyle der|"
    r"sana|senden|yakınında|yanında|ortaya çıkar|belirir|vardır|durur|gözleri|başını|adlı|isimli|adında|isminde|"
    r"barmen|gezgin|tüccar|muhafız|komutan|sakin|yaşlı|genç|sessiz|eski|yorgun|orta yaşlı|"
    r"uzun boylu|kısa saçlı|solgun|iri yapılı|kır saçlı|kararlı)\b)",
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}),\s*[\"“]",
)

def _unseen_registered_names(world_state):
    """Saved people and the people places have named who are not in this scene: each name word -> full name.

    A word shared with someone standing here is theirs and left out.
    """
    here = world_state.get("location")
    present, names = set(), {}
    for npc in world_state.get("npcs", []):
        name = str(npc.get("name") or "").strip() if isinstance(npc, dict) else ""
        if name and npc.get("location") == here:
            present.update(name.casefold().split())
        elif name:
            names.setdefault(name, None)
    for place in world_state.get("locations", {}).values():
        name = str(place.get("resident_name") or "").strip() if isinstance(place, dict) else ""
        if name:
            names.setdefault(name, None)
    return {word: name for name in names for word in name.casefold().split() if word not in present}

# The speaking shape among them: arriving, acting in the scene, or the speaker before a quote (a mention, such as
# "X sana ... gönderecekti" or "X adlı tüccar", is not one).
_SPEAKING_NAME_PATTERNS = (
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})(?:,)?\s+(?=(?:içeri|yaklaşır|girer|konuşur|yanıt verir|şöyle der|"
    r"ortaya çıkar|belirir|durur)\b)",
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\s*[,:]\s*[\"“]",
)

def _unseen_speakers(text, unseen):
    """(start, end) of each unseen registered name in the speaking shape outside speech, the whole name when said."""
    found = set()
    for pattern in _SPEAKING_NAME_PATTERNS:
        for match in re.finditer(pattern, text):
            full = unseen.get(match.group(1).casefold())
            if not full or game._inside_speech(text, match.start(1)):
                continue
            start, end = match.span(1)
            low = max(0, start - len(full))
            for said in re.finditer(re.escape(full), text[low:end + len(full)], re.IGNORECASE):
                if low + said.start() <= start < low + said.end():
                    start, end = low + said.start(), low + said.end()
                    break
            found.add((start, end))
    return sorted(found)

def _lore_claims_are_supported(lore_claims, lore_context):
    if not isinstance(lore_claims, list) or len(lore_claims) > 24:
        return False
    sections = lore_context.get("sections", {})
    supported_ids = set()
    for section_name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
        "npc_known_lore",
    ):
        for item in sections.get(section_name, []):
            if not isinstance(item, dict):
                continue
            fact_id = item.get("fact_id") or item.get("override_id")
            if isinstance(fact_id, str):
                supported_ids.add(fact_id)
    seen = set()
    for fact_id in lore_claims:
        if (
            not isinstance(fact_id, str)
            or not fact_id
            or len(fact_id) > 128
            or fact_id not in supported_ids
            or fact_id in seen
        ):
            return False
        seen.add(fact_id)
    from api.lore_authority.claim_authorization import freeze_claims_authorized

    return freeze_claims_authorized(list(seen), lore_context)

def _lore_guard_text(value):
    text = str(value or "").casefold().translate(
        str.maketrans({
            "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c",
        })
    )
    text = re.sub(r"['’](?:s|[a-z]{1,5})\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))

def _lore_fact_records(lore_context, lore_claims):
    if not isinstance(lore_context, dict) or not isinstance(lore_claims, list):
        return []
    sections = lore_context.get("sections", {})
    if not isinstance(sections, dict):
        return []
    records = []
    for section_name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
        "npc_known_lore",
    ):
        items = sections.get(section_name, [])
        for item in items if isinstance(items, list) else []:
            if (
                isinstance(item, dict)
                and (item.get("fact_id") or item.get("override_id")) in lore_claims
            ):
                records.append(item)
    return records

_LORE_ENTITY_TITLE_RE = re.compile(
    r"\b(?:king|queen|monarch|emperor|empress|deity|god|goddess|"
    r"city|town|village|river|mountain|region|kingdom|ruler|"
    r"kral|kraliçe|hükümdar|imparator|tanrı|tanrıça|şehir|kasaba|"
    r"nehir|dağ|bölge|krallık)\s+(?:of\s+)?"
    r"([A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü'’\-]*"
    r"(?:\s+[A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü'’\-]*){0,2})"
)

_LORE_PROPER_NAME_RE = re.compile(
    r"\b[A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü'’\-]*"
    r"(?:\s+[A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü'’\-]*){0,2}\b"
)

_LORE_ENTITY_FOLLOWING_CUE_RE = re.compile(
    r"\b(?:is|was|became|rules?|ruled|lives?|located|founded|"
    r"known as|called|named|merchant|trader|shopkeeper|innkeeper|"
    r"deity|god|goddess|city|town|kingdom|ruler|"
    r"adlı|isimli|denilen|olarak bilinen|şehri|kasabası|nehri|"
    r"yaşar|yönetir|hükmeder|tanrısı|tanrıçası)\b",
    re.IGNORECASE,
)

_LORE_SENTENCE_START_WORDS = {
    "how", "why", "what", "who", "whom", "where", "when", "which", "whose",
    "does", "do", "did", "is", "are", "was", "were", "has", "have", "had",
    "can", "could", "should", "would", "will", "may", "might", "tell",
    "a", "an", "and", "as", "at", "before", "but", "during", "for",
    "from", "here", "however", "in", "it", "near", "next", "one", "on",
    "recent", "several", "some", "the", "then", "there", "this", "today",
    "when", "while", "with", "after", "bir", "bu", "bölgede", "birkaç",
    "gece", "gün", "halk", "insanlar", "ışık", "karanlık", "kentin",
    "loş", "market", "ortam", "ortalık", "pazar", "rüzgar", "rüzgâr",
    "sabah", "sessizlik", "sokak", "sonra", "şehir", "şehrin", "taverna",
    "uzakta", "yağmur", "yakınlarda", "yerel", "akşam", "büyük", "sıcak",
    "ben", "benim", "adım", "ismim",
}

_GENERIC_SPEAKER_LABEL_RE = re.compile(
    r"(?:yakındaki kişi|bir [a-zçğıöşü]+(?: [a-zçğıöşü]+)?|(?:[a-zçğıöşü]+ ){1,3}biri)",
    re.IGNORECASE,
)

def _is_generic_speaker_label(label):
    """A player-facing descriptor ("Yakındaki kişi", "Bir muhafız") names no entity."""
    return bool(_GENERIC_SPEAKER_LABEL_RE.fullmatch(str(label).strip()))

_LORE_UNSUPPORTED_DETAIL_PATTERNS = (
    (
        re.compile(
            r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|"
            r"yedi|sekiz|dokuz|on)\s*(?:miles?|mi|kilometers?|kilometres?|"
            r"km|meters?|metres?|yards?|leagues?|mil|kilometre|metre)\b"
            r"|\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|"
            r"yedi|sekiz|dokuz|on)\s*(?:hours?|days?|saat|gün|gun)\s*"
            r"(?:away|from\b|journey|travel|by road|uzak\w*|mesafe\w*|"
            r"yol\w*|kuzey\w*|güney\w*|guney\w*|doğu\w*|dogu\w*|"
            r"batı\w*|bati\w*)"
            r"|\b(?:few|several|short)\s+(?:miles?|days?|hours?|"
            r"gün|gun|saat)\s+(?:away|from\b|journey|travel|by road|"
            r"uzak\w*|mesafe\w*|yol\w*)",
            re.IGNORECASE,
        ),
        "distance",
    ),
    (
        re.compile(
            r"\b(?:council|elected|election|tax(?:es)?|laws?|senate|"
            r"legislature|govern(?:ance|ed|s|ment)?|policy|policies|"
            r"administration|government|hükümet|yönetim|yönetir|"
            r"seçim|vergi|kanun|yasa|meclis|konsey|liderlik|politika)\b",
            re.IGNORECASE,
        ),
        "governance",
    ),
    (
        re.compile(
            r"\b(?:silver|metalworking|smithing|blacksmith|jewel(?:ry)?|"
            r"weapon.?smith|armou?rer|shipbuilding|pottery|weaving|"
            r"glassblow\w*|gümüş|gumus|demircilik|demirci|kuyum\w*|"
            r"silah ustası|zırh|zirh|seramik|dokuma|cam işçiliği|"
            r"cam isçiligi)\b",
            re.IGNORECASE,
        ),
        "craft_specialization",
    ),
    (
        re.compile(
            r"\b(?:fall of|rise of|collapse of|conquered|founded|"
            r"destroyed by|histor(?:y|ical)|history|recent calamities|"
            r"recent disasters|recent catastrophes|after the eruption|"
            r"tarih|yıkılışı|yikilisi|kuruluşu|kurulusu|fethedil|"
            r"çöküş|cokus|felaket)\b",
            re.IGNORECASE,
        ),
        "history",
    ),
    (
        re.compile(
            r"\b(?:because of|due to|thanks to|caused by|resulted from|"
            r"as a result|attributed to|led(?: by| to)?|responsible for|"
            r"directed(?: by)?|managed(?: by)?|oversaw|"
            r"under (?:the )?leadership of|efforts? of|helped rebuild|"
            r"sayesinde|nedeniyle|sebebiyle|yol açtı|yol acti|"
            r"katkı sağladı|katki sagladi)\b",
            re.IGNORECASE,
        ),
        "causal_attribution",
    ),
    (
        re.compile(
            r"\b(?:junction|intersection|confluence|crosses|connects? to|"
            r"meets|joins|road to|route to|leads? to|north of|south of|"
            r"east of|west of|direct route|kavşak|kavsak|birleşir|"
            r"birlesir|bağlanır|baglanir|yol ayrımı|yol ayrimi|"
            r"kuzeyinde|güneyinde|guneyinde|doğusunda|dogusunda|"
            r"batısında|batisinda)\b",
            re.IGNORECASE,
        ),
        "geographic_relation",
    ),
    (
        re.compile(
            r"\b(?:tirelessly|bustling|crowded|flourishing|prosperous|"
            r"recent calamities|recent disasters|son felaketler|"
            r"yoğun biçimde|yogun bicimde|canla başla|canla basla)\b",
            re.IGNORECASE,
        ),
        "unsupported_setting_state",
    ),
    (
        re.compile(
            r"\b(?:most important|largest|important city|major city|"
            r"en önemli şehir\w*|en onemli sehir\w*|en büyük şehir\w*|"
            r"en buyuk sehir\w*|kuzeyin merkezi|center of the north)\b",
            re.IGNORECASE,
        ),
        "unsupported_city_prominence",
    ),
    (
        re.compile(
            r"\b(?:neighborhood\w*|district\w*|ward\w*|quarter\w*|"
            r"mahalle\w*|semt\w*|destroy\w*|devastat\w*|demolish\w*|"
            r"damag\w*|ruin\w*|yıkım\w*|yikim\w*|yıkıl\w*|yikil\w*|"
            r"tahrip\w*|yok ol\w*)\b",
            re.IGNORECASE,
        ),
        "unsupported_urban_damage_detail",
    ),
    (
        re.compile(
            r"\b(?:newly built buildings?|new buildings?|modern technolog\w*|"
            r"old architecture|older architecture|new construction|"
            r"yeni yapılan binalar?|yeni yapilan binalar?|"
            r"modern teknoloj\w*|eski mimari\w*|"
            r"eski taşlar?|eski taslar?|ahşap ve demir|"
            r"ahsap ve demir|wood and iron)\b",
            re.IGNORECASE,
        ),
        "unsupported_built_environment_detail",
    ),
    (
        re.compile(
            r"\b(?:econom\w*|economy|population|citizens?|"
            r"ekonomi\w*|ekonomisi\w*|ekonomisini\w*|halkını zorla\w*|"
            r"halkini zorla\w*|people.{0,30}(?:struggle|suffer)|"
            r"(?:struggle|suffer).{0,30}people)\b",
            re.IGNORECASE,
        ),
        "unsupported_social_or_economic_state",
    ),
)

_LORE_RULER_TITLE_RE = re.compile(
    r"\b(?:king|queen|monarch|emperor|empress|kingdom|kral|kraliçe|"
    r"hükümdar|imparator|imparatoriçe)\b",
    re.IGNORECASE,
)

_LORE_ENTITY_RELATION_RE = re.compile(
    r"\b(?:because of|due to|thanks to|caused by|resulted from|"
    r"as a result|attributed to|led(?: by| to)?|responsible for|"
    r"directed(?: by)?|managed(?: by)?|oversaw|"
    r"under (?:the )?leadership of|efforts? of|helped rebuild|"
    r"junction|intersection|confluence|"
    r"crosses|connects? to|meets|joins|road to|route to|leads? to|"
    r"kavşak|kavsak|birleşir|birlesir|bağlanır|baglanir|"
    r"sayesinde|nedeniyle|sebebiyle|katkı sağladı|katki sagladi)\b",
    re.IGNORECASE,
)

_LORE_ROUTE_DISTANCE_QUERY_RE = re.compile(
    r"\b(?:road|route|path|way|distance|miles?|kilometers?|kilometres?|"
    r"how far|how many\s+(?:miles?|kilometers?|kilometres?|meters?|metres?)|"
    r"far from|on the road|"
    r"yol|rota|guzergah|mesafe\w*|uzaklik\w*|kac mil|kac kilometre|"
    r"ne kadar uzak|arasi)\b",
    re.IGNORECASE,
)

# Unverified lore is answered inside the fiction. With a present NPC the person
# says, in their own voice, that they do not know; without one the narrator
# describes how unsettled the talk around the player is. Nothing here names
# records, data, memory or verification, and nothing here asserts a fact.
_UNVERIFIED_LORE_RESPONSE = (
    "Bu konudaki söylentiler belirsiz; kulağına çalınan her ağız başka konuşuyor."
)

_UNVERIFIED_DISTANCE_RESPONSE = (
    "Yolun uzunluğu hakkında duyduklarının hiçbiri birbirini tutmuyor; kimi bir "
    "günlük yürüyüş diyor, kimi iki. Kesin bir ölçü henüz elinde değil."
)

_UNVERIFIED_RULER_RESPONSE = (
    "Bu yerin yöneticisinin kim olduğu hakkında herkes başka bir şey fısıldıyor; "
    "hangisinin doğru olduğunu henüz seçemiyorsun."
)

_INDOOR_DETAIL = re.compile(
    r"\b(?:(tezgah|banko|salon|mutfak|somine)\w*|(masa|oda|raf)(?:n?in|ya|da|dan|si\w*|lar\w*|a|ta|tan)?)\b"
)

_ASKS_DISTANCE = re.compile(r"\b(?:mesafe|uzaklik|kac mil|kac kilometre|ne kadar uzak)\b")

def _salvage_plain_speech(raw_intent):
    """Keep a usable reply when only its helper conversation proposal is bad.

    Safe only for plain speech: with a real operation (promise, trade, item
    request...) a malformed packet must still be vetoed, so nothing is kept.
    The rejected proposal is cleared and grants no authority.
    """
    if not isinstance(raw_intent, dict):
        return False
    interaction = raw_intent.get("interaction")
    narration = raw_intent.get("narration")
    if not isinstance(interaction, dict):
        return False
    if interaction.get("operation") not in (None, "none"):
        return False
    if not isinstance(narration, str) or not narration.strip():
        return False
    proposal = interaction.get("conversation")
    # A factual reading (personal purpose, cause, identity, lore...) needs
    # evidence; without it the answer must stay the in-character "I don't know".
    if isinstance(proposal, dict) and proposal.get("meaning") not in (None, "other"):
        return False
    interaction["conversation"] = None
    return True

_TERMINATOR_MASK = {".": "\u0001", "!": "\u0002", "?": "\u0003"}

def _split_sentences_keep_speech(text):
    """Split on sentence ends, but never inside a quoted utterance."""
    masked = game._SPEECH_SPAN_RE.sub(
        lambda span: "".join(_TERMINATOR_MASK.get(c, c) for c in span.group(0)), text
    )
    unmask = {mask: char for char, mask in _TERMINATOR_MASK.items()}
    return [
        "".join(unmask.get(c, c) for c in part)
        for part in re.split(r"(?<=[.!?。！？])\s+", masked)
    ]

def _spoken_lore_fact_ids(lore_context, response, selected_ids):
    """Keep only packet facts whose object is actually present in the answer."""
    if not isinstance(response, str) or not isinstance(lore_context, dict):
        return []
    sections = lore_context.get("sections", {})
    if not isinstance(sections, dict):
        return []
    names = {
        entity["entity_id"]: entity["canonical_name"]
        for entity in sections.get("verified_entities", [])
        if isinstance(entity, dict)
        and isinstance(entity.get("entity_id"), str)
        and isinstance(entity.get("canonical_name"), str)
    }
    text = response.casefold()
    spoken = []
    for section_name in (
        "official_forgotten_realms_lore",
        "campaign_canon",
        "player_known_lore",
    ):
        items = sections.get(section_name, [])
        if not isinstance(items, list):
            continue
        for fact in items:
            if not isinstance(fact, dict):
                continue
            fact_id = fact.get("fact_id")
            if not isinstance(fact_id, str) or fact_id not in selected_ids or fact_id in spoken:
                continue
            value = fact.get("object_id_or_value")
            token = names.get(value) if isinstance(value, str) else None
            if not isinstance(token, str):
                token = value if isinstance(value, str) and ":" not in value else ""
            token = token.replace("_", " ").strip()
            notes = fact.get("notes")
            note_text = notes.strip() if isinstance(notes, str) else ""
            if (len(token) >= 4 and token.casefold() in text) or (
                len(note_text) >= 20 and note_text.casefold() in text
            ):
                spoken.append(fact_id)
    return spoken

def _has_active_local_npc_focus_for_place_request(world_state, *, target_id=None):
    if not isinstance(world_state, dict):
        return False
    flags = world_state.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}
    try:
        focus_is_active = int(flags.get("active_npc_until_turn", -1)) >= (
            int(flags.get("turn_index", 0)) + 1
        )
    except (TypeError, ValueError):
        focus_is_active = False
    candidate_ids = [target_id] if isinstance(target_id, str) and target_id else []
    if focus_is_active:
        candidate_ids.extend(
            value
            for value in (flags.get("active_npc_id"), flags.get("last_npc_id"))
            if isinstance(value, str) and value
        )
    return bool(candidate_ids) and any(
        isinstance(npc, dict)
        and npc.get("id") in candidate_ids
        and npc.get("location") == world_state.get("location")
        and npc.get("status") == "active"
        and npc.get("combat_status") not in {"unconscious", "dead"}
        for npc in world_state.get("npcs", [])
    )
