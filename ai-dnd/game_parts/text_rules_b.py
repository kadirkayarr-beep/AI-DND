import game
import combat_lifecycle
import equipment_economy
import living_world
import re
import unicodedata


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

def _validated_player_line(raw_line, player_input):
    """Return the player's own line to show, or None. The model never writes it.

    A quote the player supplied beats any model rewrite. Otherwise the model may
    only point at words the player actually typed: the line must be a bounded,
    single-line, quote-free substring of the player's own input (whitespace and
    case normalized). Anything else the model invents is dropped.
    """
    if not isinstance(raw_line, dict):
        return None
    import npc_speech_boundary
    supplied = npc_speech_boundary.player_supplied_quote(player_input)
    if supplied:
        return supplied
    text = raw_line.get("text")
    if not isinstance(text, str) or "\n" in text or "\r" in text:
        return None
    text = text.strip()
    if not text or len(text) > 300 or any(mark in text for mark in "“”«»\""):
        return None
    squash = lambda value: " ".join(str(value).split()).casefold()
    if squash(text) not in squash(player_input or ""):
        return None
    return text

_WINDOW_WORDS = re.compile(r"\b(?:pencere\w*|kepenk\w*|panjur\w*|cam(?:dan|a|i)?)\b")

_LOCK_WORDS = re.compile(r"\b(?:kilit\w*|kilid\w*|surgu\w*|mandal\w*|kapi kolu\w*)\b")

_TRACK_WORDS = re.compile(r"\b(?:iz|izler\w*|izleri\w*|ayak izi\w*|ayak izler\w*)\b")

def _resolved_skill_result_narration(result):
    """Describe only the already resolved Python check, with no added consequences."""
    if (not isinstance(result, dict) or result.get("action") != "skill_check"
            or result.get("status") not in ("resolved", "experimental_attributed_speech")):
        return None
    if result.get("status") != "resolved":
        import interaction_adventure
        return interaction_adventure.social_outcome_line(  # D-226: a reply that gave the roll away says what it decided
            result.get("npc_name"), result.get("skill"), result.get("outcome"))
    outcome = result.get("outcome")
    if outcome not in ("success", "failure"):
        return None
    if result.get("skill") == "Stealth":
        if outcome == "success":
            return "Gizlenme girişimin tutar."
        return "Gizlenme girişimin tutmaz; gizli sayılmazsın."
    if result.get("skill") in {"Perception", "Investigation", "Survival"}:
        # A look is described by what it saw (_fallback_narration), not as a
        # bare "check succeeded/failed" line.
        return None
    prefix = {
        "Perception": "Dikkatini topladığın kontrol",
        "Investigation": "İnceleme girişimin",
        "Athletics": "Fiziksel çaban",
        "Acrobatics": "Akrobatik girişimin",
        "Persuasion": "İkna girişimin",
        "Deception": "Kandırma girişimin",
        "Survival": "İz sürme girişimin",
        "Sleight of Hand": "El becerisi girişimin",
    }.get(result.get("skill"), "Yetenek kontrolün")
    return f"{prefix} {'başarılı' if outcome == 'success' else 'başarısız'} olur."

_TELLS_FAILURE = re.compile(r"\w+m[iu]yor\w*|\w+(?:ama|eme)(?:z|di|yacak)\w*|\bbasarisiz|\bsonuc vermedi|\byok\b|\bdegil\b")

# D-226: what tells a scared person unmoved ("geri adım atmıyor", "sözlerin ona işlemiyor", "korkmuyorum").
_UNMOVED = re.compile(
    r"\b(?:geri\s+adim\s+atm(?:iyor|az|adi)|cekilm(?:iyor|ez|edi)|"
    r"islem(?:iyor|ez|edi)|etkilen?m(?:iyor|ez|edi)|umursam(?:iyor|az|adi)|"
    r"aldirm(?:iyor|az|adi)|korkm(?:uyor|az|adi)|yol\s+verm(?:iyor|ez|edi)|istifini\s+bozm(?:uyor|az|adi))\w*")

# D-241: what tells a person giving way to a scare or a plea ("kenara çekiliyor", "yolu açıyor", "boyun eğiyor").
_YIELDS = re.compile(
    r"\b(?:kenara\s+cekil|geri\s+cekil|yol(?:u)?\s+(?:ver|ac)|boyun\s+eg|razi\s+ol|ikna\s+ol|pes\s+ed|"
    r"teslim\s+ol|yutkun|korkuyla|korkup)\w*")

_QUOTE_CLOSER_RE = re.compile(r"""(?<=[.!?…,])['"”’](?=\s|$)""")

_QUOTE_OPENER_RE = re.compile(r"""(?:(?<=^)|(?<=[\s:(]))['"“‘](?=\S)""")

def _trim_dangling_quote(text):
    """Drop a leading fragment that ends in a closing quote nobody opened.

    Removing the sentence that carried the opening quote leaves "...alırız.' Fırın
    kokusu..."; keep only what follows. Untouched when balanced; empty when nothing follows
    (a line nobody opened is no line, and the caller falls back).
    """
    closer = _QUOTE_CLOSER_RE.search(text)
    if closer is None:
        return text
    opener = _QUOTE_OPENER_RE.search(text)
    if opener is not None and opener.start() < closer.start():
        return text
    return text[closer.end():].strip()

def _dialogue_repair_has_attributed_answer(narration, npc_target, action_result):
    """Require a bound dialogue turn and actual speech content after repair."""
    if isinstance(narration, dict):
        from npc_speech_boundary import bound_fields
        return bound_fields(narration, npc_target, action_result) is not None
    if (
        not isinstance(narration, str)
        or not narration.strip()
        or not isinstance(npc_target, dict)
        or not isinstance(npc_target.get("id"), str)
        or not isinstance(action_result, dict)
        or action_result.get("action") != "dialogue"
    ):
        return False
    target_id = npc_target["id"]
    result_npc_id = action_result.get("npc_id")
    experimental_speech = (
        action_result.get("status") == "experimental_attributed_speech"
    )
    if result_npc_id is not None and result_npc_id != target_id:
        return False
    if experimental_speech and result_npc_id != target_id:
        return False

    quoted_answers = (
        r"“([^”\n]{3,})”",
        r'"([^"\n]{3,})"',
        r"‘([^’\n]{3,})’",
        r"'([^'\n]{3,})'",
    )
    has_quoted_answer = any(
        len(re.sub(r"[^\wçğıöşü]", "", match.group(1))) >= 3
        for pattern in quoted_answers
        for match in re.finditer(pattern, narration)
    )
    if has_quoted_answer:
        return True

    if not experimental_speech:
        return False
    # Experimental speech is deliberately unquoted until the API adds its
    # speaker wrapper. Require a first-person predicate so a lone stage
    # direction cannot qualify as the NPC's retained answer.
    first_person_predicate = re.search(
        r"\b[\wçğıöşü]+(?:ıyorum|iyorum|uyorum|üyorum|yordum|[dt][ıiuü]m|"
        r"[ıiuü]r[ıiuü]m|(?:y)?(?:acağım|eceğim)|(?:sa|se)m)\b",
        narration,
        re.IGNORECASE,
    )
    return first_person_predicate is not None

def _skill_result_category(result):
    return {
        "BAŞARILI": "success",
        "BAŞARISIZ": "failure",
    }.get(result, "failure")

def _print_skill_result(result, difficulty):
    print()
    print("=" * 35)
    print("D&D SKILL CHECK")
    print("=" * 35)
    print("Skill:", result["skill"])
    print("Difficulty:", difficulty)
    print("DC:", result["dc"])
    print("D20:", result["dice"])
    print("Ability Modifier:", f"+{result['modifier']}" if result["modifier"] >= 0 else result["modifier"])
    print("Proficiency:", f"+{result['proficiency_bonus']}")
    print("Total Bonus:", f"+{result['total_bonus']}" if result["total_bonus"] >= 0 else result["total_bonus"])
    print("Total:", result["total"])
    print("Result:", result["result"])
    print("=" * 35)

_ATTACK_VERB_PATTERN = r"(?:saldir|vur|dov|kes|sapl|bicakl|yumrukl|oldur|bayilt)"

# A blow said as noun + verb, the usual Turkish way: "yumruk atıyorum", "tekme savuruyorum".
_ATTACK_BLOW_PHRASE = re.compile(
    r"\b(?:yumruk|tekme|tokat|kafa|dirsek)\w*\s+(?:\w+\s+)?(?:at|savur|indir|gecir|patlat)"
    r"(?:iyorum|ip|tim|acagim|ar|iyoruz|tik)\b"
)

# Folded words that share an attack stem but are not attacks: kesinlikle,
# keşif/keşfetmek, kestirme (shortcut), vurgulamak, and the instrumental nouns
# "bıçakla"/"yumrukla" ("with a knife/fist") that only name the means.
_CHARGING_IN = re.compile(r"\b\w+(?:la|le|yla|yle)\s+(?:\w+\s+)?(?:giriyorum|daliyorum|atiliyorum)\b")

_ATTACK_LOOKALIKE_TOKEN = re.compile(
    r"^(?:kesin|kesif|kesfe|kesfi|kestirme|vurgu|vurdumduymaz)"
)

_ATTACK_INSTRUMENT_TOKENS = frozenset({"bicakla", "yumrukla", "bicaklar", "bicaklarla"})

# Things one knocks on, rings, cuts or taps. Hitting one of these is knocking,
# ringing or cutting - never a combat decision - unless a creature is named.
_INANIMATE_HIT_OBJECT = re.compile(
    r"\b(?:kapi(?!ci)|pencere|kepenk|panjur|masa|tezgah|duvar|zil|can(?:i|a|in)?\b"
    r"|sandi[kg]|kutu|ip(?:i|in|e|ini|ine|ten|ler\w*)?\b|halat|urgan|zincir|cuval|fici|varil|sepet"
    r"|kilit|cam(?:a|i)?\b|tahta|agac|odun|kaya"
    r"|kitap|ekmek|sopa|direk|kazik|kumas|bez|dal(?:i|a)?\b|davul|gong|tokmak)\w*"
)

_CREATURE_REFERENCE = re.compile(
    r"\b(?:ona|onu|ondan|onunla|kendisine|adam\w*|kadin\w*|cocug\w*|muhafiz\w*"
    r"|nobetci\w*|asker\w*|haydut\w*|eskiya\w*|goblin\w*|ork\w*|kurt\w*|yaratig\w*"
    r"|canavar\w*|dusman\w*|rakib\w*|hirsiz\w*|haydud\w*)\b"
)

def _attack_verb_tokens(text):
    import grounded_action
    verbs = []
    for token in text.split():
        match = re.match(_ATTACK_VERB_PATTERN, token)
        if not match or _ATTACK_LOOKALIKE_TOKEN.match(token) or token in _ATTACK_INSTRUMENT_TOKENS:
            continue
        tail = token[match.end():]
        # Reuse the action owner's morphology instead of treating every word
        # beginning with an attack stem as an attack (Kestrin, keskin, saldırgan).
        if (not tail or grounded_action._VERB_TAIL.fullmatch(tail)
                or grounded_action._NEGATIVE_TAIL.match(tail)):
            verbs.append(token)
    return verbs

def _immediate_check_refusal(check_feature, message):
    """The route refusal in the chosen feature's own name; `{feature}` in a message is that name."""
    code, name = (('tactical_mind_immediate_check_only', 'Tactical Mind') if check_feature == 'tactical_mind'
                  else ('primal_knowledge_immediate_check_only', 'Primal Knowledge'))
    return combat_lifecycle.CombatRequestError(code, message.format(feature=name), 400)

def _turkish_genitive_form(name):
    value = str(name or "").strip()
    if not value:
        return ""
    vowels = "aıeiouöü"
    last_vowel = next(
        (character for character in reversed(value.casefold()) if character in vowels),
        None,
    )
    if last_vowel is None:
        return value
    suffix = {
        "a": "ın",
        "ı": "ın",
        "o": "un",
        "u": "un",
        "e": "in",
        "i": "in",
        "ö": "ün",
        "ü": "ün",
    }[last_vowel]
    if value[-1].casefold() in vowels:
        suffix = "n" + suffix
    return f"{value}'{suffix}"

def _asks_what_is_going_on(player_input):
    text = living_world.normalize_text(player_input)
    return bool(
        re.search(r"\b(?:bugun|burada|buralarda|su an)\b", text)
        and re.search(r"\b(?:ne oluyor|neler oluyor|ne var|neler var)\b", text)
    )

def _is_bare_greeting(player_input, npc_target):
    """'Merhaba Marek' yes; 'selam verip burada bir sorun var mı diye soruyorum' no."""
    if "?" in str(player_input):
        return False
    text = living_world.normalize_text(player_input)
    words = text.split()
    name_words = set(living_world.normalize_text(
        npc_target.get("name", "") if isinstance(npc_target, dict) else ""
    ).split())
    rest = [
        word for word in words
        if word not in name_words and not re.match(
            r"(?:selam|merhaba|iyi|gunler|gunaydin|aksamlar|veriyorum|ver|basimla|"
            r"bas|sallay\w*|el|elimi|ona|onunla|kendisiyle|kisa|bir|biraz|yanina|gidip|"
            r"yaklasip|dostum|hey)", word)
    ]
    return len(rest) <= 2 and not re.search(
        r"\b(?:sor\w*|anlat\w*|soyle\w*|ogren\w*|nasil|neden|nerede|kim|ne)\b", text
    )

def _is_scene_referent_activity_observation(player_input):
    if not isinstance(player_input, str):
        return False
    text = living_world.normalize_text(player_input)
    activity_question = bool(
        re.search(
            r"\b(?:ne|neler)\s+yap\w*\b|\bneyle\s+ugras\w*\b",
            text,
        )
    )
    return bool(
        (
            activity_question
            or (
                re.search(r"\b(?:dikkat\w*|gozlemle\w*|izle\w*)\b", text)
                and re.search(
                    r"\b(?:etkinli\w*|davran\w*|hareket\w*|yaptig\w*)\b",
                    text,
                )
            )
        )
        and not re.search(
            r"\b(?:sor\w*|konus\w*|selam\w*|yaklas\w*)\b",
            text,
        )
    )

def _public_scene_person_text(npc):
    label = living_world.public_npc_name(npc)
    role = living_world.public_npc_role(npc)
    if living_world.npc_name_known_to_player(npc) and role and role.casefold() != label.casefold():
        return f"{label} ({role})"
    return label

_LOOK_OPENINGS = (
    "{name} çevresine göz gezdiriyorsun.",
    "Bakışların {name} çevresinde bir kez daha dolaşıyor.",
    "Bir an durup {name} çevresindeki hareketi izliyorsun.",
    "{name} çevresini yeniden, bu sefer daha dikkatle süzüyorsun.",
)

_CONVERSATION_OPENINGS = (
    "{name} sana dönüyor. “Seni dinliyorum,” der.",
    "{name} işini bir an bırakıp sana bakıyor. “Buyur, ne vardı?” diye sorar.",
    "{name} başını kaldırıyor. “Evet, söyle bakalım,” der.",
    "{name} hafifçe gülümsüyor. “Yine sen! Dinliyorum,” der.",
)

# Front readings that are the player's own doing, with no one spoken to: a second part after one is read on its own.
_OWN_ACTS = frozenset({"consume", "wield", "sit", "bag", "look", "wait"})

_WALKED_UP = re.compile(r"(?i)\b(?:yaklaş\w*|yanaş\w*|yanına\s+gid\w*|yanına\s+git\w*|sokul\w*)[.,;:!]?\s+")

def _said_after_approach(player_input):
    """"...adama yaklaşıyorum. selam, ne yazıyorsun?": what comes after the walk is said to them."""
    match = _WALKED_UP.search(player_input) if isinstance(player_input, str) else None
    rest = player_input[match.end():].strip() if match else ""
    return rest if len(rest.split()) >= 2 else None

_SAY_VERBS = re.compile(r"^(?:soyl|sor|anlat|ver|diyorum|dedim|ilet|seslen|danis|rica|teklif|uzat|goster|tesekkur)")

_SAY_ENGLISH = r"\b(?:tell|ask|give|hand|pay|show|thank|say to|speak to|talk to|offer)\s+(?:the\s+)?"

_HAIL_FILLERS = {"ey", "hey", "pardon", "selam", "merhaba", "sayin", "affedersiniz", "bakin", "bak"}

def _line_addresses(player_input, npc):
    """Whether the line is said TO this person: their name or role at the head with a comma after it ("Orhan, kapı
    nerede?"), or their name in the dative with a say verb ("Orhan'a soruyorum"). A mention is no address
    ("Orhan'ı tanıyor musun?", "Orhan nerede?", "Muhafız sana ne dedi?")."""
    if not isinstance(player_input, str) or not isinstance(npc, dict):
        return False
    ascii_line = unicodedata.normalize("NFKD", player_input.casefold().replace("İ", "i").replace("ı", "i"))
    tokens = re.findall(r"[^\W_]+|,", ascii_line.encode("ascii", "ignore").decode())  # words and commas, folded
    words = {w for w in living_world.normalize_text(f"{living_world.public_npc_name(npc)} {npc.get('role') or ''}").split()
             if len(w) >= 3}
    if not words:
        return False
    head = tokens[:6]
    first = next((i for i, t in enumerate(head) if t in words), None)
    if first is not None and all(t in _HAIL_FILLERS for t in head[:first]):
        j = first
        while j < len(tokens) and (tokens[j] in words or (j > first and len(tokens[j]) <= 3 and tokens[j] != ",")):
            j += 1
        if j < len(tokens) and tokens[j] == ",":
            return True
    for i, token in enumerate(tokens):
        dative = (token in words and i + 1 < len(tokens) and tokens[i + 1] in {"a", "e", "ya", "ye"}) or any(
            token in {w + "a", w + "e", w + "ya", w + "ye"} for w in words)
        if dative and any(_SAY_VERBS.match(t) for t in tokens):
            return True
    folded_text = " ".join(tokens)
    return any(re.search(_SAY_ENGLISH + re.escape(w) + r"\b", folded_text) for w in words)

# What the line is, once read, leaves the scene planner nothing to do: it only ever walks, sits or looks.
_PLANNER_STAYS_OUT = {"speak_to", "talk_around", "go_to", "offer_answer", "hand_over", "work", "take", "bag", "strike",
                      "blow_asked", "heavy_asked", "which_move", "wait", "consume", "wield"}  # D-109: asked moves nothing

_NO_BLOW_NOW = re.compile(r"\b(?!yarim\b)\w+(?:m[iu]yorum|m[iu]yom|mayacag\w*|meyeceg\w*|[aeiu]r[iu]m)\b")

# Hands, things swung and things thrown: what a blow is made of, whatever else the sentence says.
_BLOW_WORDS = re.compile(
    r"\b(?:yumru[kg]|tekme|tokat|samar|dirsek)\w*"
    r"|\b(?:cak|gecir|firlat|savur|indir|patlat|yapistir|sall)(?:[iuae]|ip|up)\w*"
    r"|\b(?:surat|kafa|yuz)\w*\s+(?:\w+\s+)?at(?:iyorum|ip)\b"
)

def _word_root(word):
    """A word cut to a root that still meets its endings ('takımı' 'takımını', 'emanet' 'emanetini'); short words whole."""
    return word if len(word) <= 5 else word[:max(5, len(word) - 2)]

_NOT_A_LOCAL_PLACE = {
    "city", "town", "village", "settlement", "region", "wilderness", "dungeon",
    "şehir", "kasaba", "köy", "orman",
}

_NARRATOR_PRONOUNS = {
    "siz": "sen", "size": "sana", "sizi": "seni", "sizin": "senin",
    "sizden": "senden", "sizinle": "seninle", "sizde": "sende",
}

_NARRATOR_PLURAL = (
    (re.compile(r"\b(?:siz|size|sizi|sizin|sizden|sizinle|sizde)\b", re.IGNORECASE),
     lambda match: (
         _NARRATOR_PRONOUNS[match.group(0).lower()].capitalize()
         if match.group(0)[0].isupper()
         else _NARRATOR_PRONOUNS[match.group(0).lower()]
     )),
    (re.compile(
        r"\b(etraf|çevre|üzer|yakın|ön|arka|yan|karşı|iç|ayak|ayaklar|el|eller|göz|gözler|omuz|"
        r"omuzlar|sırt|baş|yüz|ses|bakış|bakışlar|şarkı|teklif|söz|hareket|gösteri|adım|adımlar)"
        r"([ıiuü]?n)[ıiuü]z(\w*)", re.IGNORECASE),
     r"\1\2\3"),
    (re.compile(r"\b(\w+[ıiuü]yor)sunuz\b"), r"\1sun"),
    (re.compile(r"\b(\w{2,}[dt][ıiuü]n)[ıiuü]z\b"), r"\1"),
)

def _singular_narrator(text):
    """The narrator's own words say sen; anything inside a quote belongs to the speaker."""
    if not isinstance(text, str):
        return text
    parts = re.split(r"(“[^”]*”|«[^»]*»|\"[^\"]*\")", text)
    for index in range(0, len(parts), 2):
        for pattern, replacement in _NARRATOR_PLURAL:
            parts[index] = pattern.sub(replacement, parts[index])
    return "".join(parts)
