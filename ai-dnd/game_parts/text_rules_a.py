import game
import living_world
import re


def _inside_speech(text, position):
    return any(span.start() < position < span.end() for span in _SPEECH_SPAN_RE.finditer(text))

_SPEECH_SPAN_RE = re.compile(r"""“[^”]*”|"[^"]*"|(?<!\w)'[^']*'(?!\w)""")

def ollama_response_content(response):
    """Read message content from both dict and typed Ollama SDK responses."""
    if isinstance(response, dict):
        message = response.get("message", {})
    else:
        message = getattr(response, "message", None)

    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))

def ollama_reply_was_cut(response):
    """True when the model stopped at its token cap instead of finishing."""
    if isinstance(response, dict):
        return response.get("done_reason") == "length"
    return getattr(response, "done_reason", None) == "length"

_ASKS_SOMETHING = re.compile(
    r"\b(?:mi|mu|misin|musun|misiniz|musunuz|ne|kim|neden|niye|nasil|nerede|nereden|nerden|sence|sizce)\b"
)

def _just_served(world):
    """"Duydun mu birşey", right after the beer: nobody needs a name for the one who poured it."""
    flags = world.get("flags", {})
    return type(flags.get("served_turn")) is int and 0 <= flags.get("turn_index", 0) - flags["served_turn"] <= 2

_THIRD_PERSON_REPORT = re.compile(
    r"\b(?:dedi|soyledi|anlatti|bahsetti|konustu|tavsiye etti|onerdi|demis|soylemis|anlatmis|bahsetmis)\b"
)

_SECOND_PERSON_SAID = re.compile(
    r"\b(?:dedin|soyledin|anlattin|bahsettin|konustun|demistin|soylemistin|anlatmistin"
    r"|bahsetmistin|hatirl\w*)\b"
)

# "Tariq nerde dedim sana": the player repeating their own words, which claims nothing about anyone else's.
_SAID_IT_AGAIN = re.compile(r"\b(?:dedim|diyorum)\b(?:\s+(?:sana|size|ya|be|yahu))*")

_ENDS_IN_SPEECH = re.compile(r"\b(?:dedim|diyorum|soyle|soylesene|soyledim)\b(?:\s+(?:sana|size|ya|be|yahu))*[.! ]*$")

def is_ordinary_environment_look(player_input):
    if not isinstance(player_input, str):
        return False
    text = player_input.casefold().strip()
    if living_world.classify_scene_action(player_input) == "look":
        return not any(
            phrase in text for phrase in ("dikkatlice", "gözlem", "fark etmeye", "bir şey", "araştır")
        )
    simple_view = bool(re.search(
        r"\b(?:etraf[ıi]m[ae]?\s*bak\w*|çevrem[ae]?\s*bak\w*|etrafa\s*bak\w*|çevreye\s*bak\w*|"
        r"etraf[ıi]?m?da\s+ne(?:ler)?\s+var|çevre(?:m|de)?\s+ne(?:ler)?\s+var|"
        r"etrafta\s+ne(?:ler)?\s+görüyorum|çevrede\s+ne(?:ler)?\s+görüyorum|"
        r"etrafta\s+ne(?:ler)?\s+var|çevrede\s+ne(?:ler)?\s+var)\b",
        text,
    ))
    return simple_view and not any(
        phrase in text for phrase in ("dikkatlice", "gözlem", "fark etmeye", "bir şey", "araştır")
    )

def npc_ambiguity_response(resolution):
    """An attack on nobody in particular: the one address the game must not pick."""
    people = living_world.public_scene_people(resolution.get("npcs", []))
    return f"Yakında {people} var; hangisine yöneliyorsun?"

_NEGATED_VERB_SUFFIX = re.compile(r"^(?:ma|me|mi|mu|mı|mü|mam|mem|may|mey|miyor|muyor|mayacag|meyeceg)")

def _affirmative_door_verb(normalized_text, prefix, stems):
    """True when a door verb appears in an affirmative (not negated) form.

    "kapıyı kırıyorum" yes; "kapıyı kırmayacağım", "zorlamıyorum" and the
    passive "zorlanmış" (was it forced?) no.
    """
    for stem in stems:
        for match in re.finditer(rf"\b{prefix}{stem}(\w*)", normalized_text):
            rest = match.group(1)
            if stem == "zorla" and rest.startswith("n"):
                continue  # zorlanmış / zorlandı: passive, describes the lock
            trying = re.match(r"(?:maya|meye)\s+calis", rest + normalized_text[match.end():match.end() + 8])
            if trying:
                return True  # "kırmaya çalışıyorum" is an attempt
            if _NEGATED_VERB_SUFFIX.match(rest):
                continue
            return True
    return False

_SKILL_CHECK_WORD = r"(?:check|roll|zar\w*|yoklama\w*|kontrol\w*)"

# a real case ending after a Turkish skill word ("Tarihi", "Atletizmi"); "gösterişli" is no "Gösteri"
_SKILL_ENDING = r"(?:(?:ler|lar)?(?:y?[iuea]|n?in|n?un|d[ae]n?|t[ae]n?|l[ae]|s[iu]|n[ie]|n[ae]|nd[ae]n?))?"

_ABILITY_WORD = (r"(?:strength|dexterity|constitution|intelligence|wisdom|charisma|"
                 r"guc|ceviklik|dayaniklilik|zeka|bilgelik|karizma)")

_OPEN_SCARE = re.compile(
    r"^(?!.*\b(?:diyorum|soyluyorum|fisildiyorum|diye|ozur|sanirim|yarin|sonra|eger|degil|ama|seni|sizi|keske|belki|sanki|diyelim|farz|varsay\w*|bicakla\w*|ruya\w*|hayal\w*|ati|kus\w*|kopek\w*|hayvan\w*)\b)"
    r".*\b(?:korkutmaya\s+calisiyorum|korkutmak\s+icin\s+(?:\w+\s+){0,2}?zar\w*\s+atiyorum|"
    r"gozdagi\s+vermeye\s+calisiyorum|tehdit\s+etmeye\s+calisiyorum)$"
)

# Dice guide 4.4/H01: a hide needs cover or obscurement. The engine knows the dark (night), a place with walls and a
# door, and what cover the player names; anything else in the open by day is no hide (D-094, D-171).
_COVER_WORD = (
    r"(?:golge\w*|karanlig\w*|karanlik\w*|kalabalig\w*|kalabalik\w*|arkasina|arkasinda|ardina|ardinda|altina|"
    r"altinda|calilar\w*|calilig\w*|calilik\w*|caliya|calinin|agac\w*|fici\w*|sandig\w*|sandik\w*|perde\w*|sis\w*|kose\w*|kuytu\w*|siper\w*|"
    r"cuval\w*|kayanin|kayalar\w*|duvarin\s+dibine)")

# D-225: a cover word the line denies is no cover: "hiçbir gölge", "gölgesiz", "siper ya da gölge olmayan", "ağaç
# bile yok", "siper değil".
_COVER = re.compile(
    rf"(?<!\bhicbir )\b{_COVER_WORD}\b(?<!s[iu]z)"
    rf"(?!(?:\s+(?:ya|da|de|ve|veya|ile|bile|falan|filan|hic|{_COVER_WORD}))*\s+"
    r"(?:olmayan\w*|olmadig\w*|olmadan|bulunmayan\w*|bulunmadig\w*|yok(?:tu|tur|ken|mus)?\b(?!\s+ol)|degil\w*)\b)")

# One's own thing hidden on oneself ("hançerimi kolumun içine gizliyorum") is Sleight of Hand, not a hide (D-176).
_OWN_THING_HIDDEN = re.compile(r"\b(?!kendim)\w{2,}m[iu]\s+(?:\w+\s+){0,4}?(?:gizl|sakl)\w*")

_READING_CHECKS = frozenset({"Intimidation", "Deception", "Persuasion", "Insight"})

# Ordinary Turkish sentence openers; capitalized at a sentence start they are
# not person names even when a descriptor word follows ("Belki muhafıza sor").
_COMMON_SENTENCE_OPENERS = frozenset({
    "belki", "evet", "hayır", "tabii", "tabi", "elbette", "şimdi", "sonra", "peki",
    "ama", "çünkü", "eğer", "yoksa", "bence", "açıkçası", "doğrusu", "galiba",
    "herhalde", "mutlaka", "kesinlikle", "ayrıca", "üstelik", "yine", "şöyle",
})

_QUESTION_CUE_RE = re.compile(
    r"\?|\b(?:ne|neler|nere\w*|kim\w*|kac\w*|hangi\w*|nasil|neden|niye|nicin|m[iu](?:y?d[iu](?:m|n|k|n[iu]z|lar|ler)?|y?m[iu]s(?:[iu]m|s[iu]n(?:[iu]z)?|[iu]z|lar|ler)?|y[iu]m|s[iu]n(?:[iu]z)?|y[iu]z|d[iu]r)?)\b"
)

def clean_dm_response(text, *, spoken=False):

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL
    ).strip()

    text = text.replace("```json", "").replace("```", "").strip()

    # Mekanik/meta satırlarını temizle.
    text = re.sub(
        r"(?im)^.*(?:DC|D20|zar sonucu|zar atışı|modifier|toplam bonus|skill check).*$",
        "",
        text
    )

    # Seçenek listelerini temizle.
    text = re.sub(
        r"(?im)^\s*(?:[-*]|\d+[.)])\s+.*$",
        "",
        text
    )

    # Oyuncuya soru/karar yükleyen ifadeleri temizle. Bir NPC bunu sorabilir.
    if not spoken:
        text = re.sub(
            r"(?im)^.*(?:hangisini seçersin|ne yaparsın|ne yapmak istersin)\??.*$",
            "",
            text
        )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    cleaned = []

    for line in lines:
        if line not in cleaned:
            cleaned.append(line)

    return "\n".join(cleaned).strip()

def _hand_names_something(inventory, held):
    """Whether a hand's value is sound: an item id or old name in the bag, or a catalog weapon (the new world's own
    default hand is "longsword" whatever the bag holds)."""
    from weapon_catalog import lookup
    if lookup(held) is not None:
        return True
    return any(item == held if isinstance(item, str)
               else isinstance(item, dict) and held in (item.get("item_id"), item.get("name"))
               for item in inventory)

_ARMED_ROLE = re.compile(r"\b(?:muhafiz|nobetci|cavus|asker|haydut|eskiya)")

_STRONG_ROLE = re.compile(r"\b(?:demirci|liman iscisi|seyis|arabaci|mezarci|barmen|usta|kahya)")

# (armor class, hit points, attack bonus, die, damage type) for a person with no stat block.
_PERSON_FIGHT = {
    "armed": (15, 16, 3, 6, "slashing"),
    "strong": (11, 12, 3, 6, "bludgeoning"),
    "plain": (10, 8, 2, 6, "bludgeoning"),
}

def _clean_world_text(value, limit=240):
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.replace("\x00", "").split()).strip()
    if not cleaned or len(cleaned) > limit:
        return None
    return cleaned

def _scene_texts_for_referents(world_state):
    """Descriptive scene text whose lowercase words are evidence of common nouns (W05)."""
    texts = []
    # NPC descriptions can be model-authored; only the engine's own feature/location text counts as evidence
    for collection in ("features",):
        for item in world_state.get(collection, []) if isinstance(world_state, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("description"), str):
                texts.append(item["description"])
    locations = world_state.get("locations", {}) if isinstance(world_state, dict) else {}
    for location in locations.values() if isinstance(locations, dict) else []:
        if isinstance(location, dict) and isinstance(location.get("description"), str):
            texts.append(location["description"])
    return texts

_ENGLISH_STOP_WORDS = frozenset(("the", "a", "an", "and", "of", "on", "with", "is", "are"))

def _reads_english(text):
    """No Turkish letter and at least two English function words: the text is English, not Turkish."""
    if not isinstance(text, str) or re.search(r"[çğıöşüÇĞİÖŞÜ]", text):
        return False
    words = re.findall(r"[a-z]+", text.casefold())
    return sum(1 for word in words if word in _ENGLISH_STOP_WORDS) >= 2

_SAVE_ABILITY_TR = {"strength": "Güç", "dexterity": "Çeviklik"}

def _unarmed_save_text(target, result, save):
    """A Shove or a Grapple is the target's saving throw, told with its roll and DC; it deals no damage."""
    shove = result["unarmed_option"] == "shove"
    ability = _SAVE_ABILITY_TR.get(save.get("ability"), save.get("ability"))
    told = (f"{ability} kurtarma zarı kendiliğinden başarısız, DC {save.get('dc')}" if save.get("automatic_failure")
            else f"{ability} kurtarma zarı {save.get('total')}, DC {save.get('dc')}")
    move = "itişine" if shove else "kavrayışına"
    if result.get("outcome") == "miss":
        return f"{target} {move} direnir ({told})."
    effects = result.get("additional_effects") or []
    if not shove:
        effect = "kavranır (Grappled)"
    elif any(isinstance(e, dict) and e.get("kind") == "shove_prone" for e in effects):
        effect = "yere düşer (Prone)"
    elif any(isinstance(e, dict) and e.get("kind") == "push" and e.get("applied") for e in effects):
        effect = "5 feet geri itilir"
    else:  # the push rule did not apply (target too large, or no known position to push to): no invented reason
        effect = "itme uygulanamadı, yerinde kalır"
    return f"{target} {move} karşı koyamaz ({told}); {effect}."

_FALL_LINE = ("Dizlerin boşalıyor, yere yığılıyorsun; sesler uzaklaşıyor. Bilincini kaybedersin. "
              "Şimdi ölümle arandaki tek şey zar: bir şey yaz ya da zarını at.")

_REWOUND_LINE = ("Karanlık seni yutuyor, ama bu kampanyanın eski kuralı seni bırakmıyor: "
                 "gözlerini çatışmadan önceki anda açıyorsun.")

_PROPOSAL_MARKER_RE = re.compile(r"\[\[([nlfs][1-9]\d?)\]\] ?")

_INTERNAL_MARK_RE = re.compile(
    r"\[\[\s*([^\[\]]{0,60}?)\s*\]\](['’]\w+)?|\b(npc_[a-z0-9_]+)\b|\[([^\[\]]{1,40})\]"
)

def _strip_proposal_markers(narration):
    return _PROPOSAL_MARKER_RE.sub("", narration) if isinstance(narration, str) else narration

def _normalize_interaction_mode(value):
    if value in {"say", "do", "ask_dm"}:
        return value
    return None

_GUARD_ROLE = re.compile(r"muhafiz|guard|nobet|bekci|asker|devriye")

_GUARD_WORD = re.compile(r"\b(?:muhafiz|nobetci|bekci|asker|devriye|guard)\w*")

_GENERIC_PERSON = re.compile(
    r"\b(?:biri|birine|birini|birisi|birisine|birisini|birilerine)\b"
    r"|^(?:(?:su|o|bu|bir|yakin\w*|yan\w*|karsi\w*|oradaki|suradaki|buradaki)\s+)*"
    r"(?:adam|kadin|kisi|insan)\w*\s+(?:dogru\s+)?(?:yaklas|sokul|yanas|yonel)"
)

def _is_guard(npc):
    return bool(_GUARD_ROLE.search(living_world.normalize_text(npc.get("role", ""))))

def _serves_at_a_counter(npc):
    return bool(_COUNTER_ROLE.search(living_world.normalize_text(npc.get("role", ""))))

def _topic_place_name(world):
    """The name of the place just talked about or found, if the talk is still on it."""
    import grounded_action
    import npc_statements
    said = npc_statements.last_said_place(world)
    if said:
        return said.get("name")
    place = world.get("locations", {}).get(grounded_action.last_target_id(world))
    return place.get("name") if isinstance(place, dict) else None

_LOCATED_PERSON = re.compile(
    r"\b([^\W\d_]{3,}?)['’]?(?:daki|deki|taki|teki)\s+"
    r"(?:adam|kad[ıi]n|ki[sş]i|gen[cç]|ya[sş]l[ıi]|[cç]ocuk|ihtiyar|o[gğ]lan|k[ıi]z)",
    re.IGNORECASE,
)

_IN_REACH_WORDS = (
    "yakin", "yan", "karsi", "sag", "sol", "on", "arka", "bura", "ora", "sura", "ileri",
    "ote", "kose", "kapi", "sokak", "cadde", "meydan", "kalabalik", "uzak", "dis", "ic",
)

_COUNTER_WORDS = ("tezgah", "bar", "banko")

_COUNTER_ROLE = re.compile(r"barmen|bartender|hanci|meyhaneci|tuccar|dukkan|satici|merchant|shopkeeper|garson")

def _drop_repeated_sentences(narration, earlier):
    """A paragraph copied from the last turn is not told twice; new sentences stay."""
    if not isinstance(narration, str):
        return narration
    seen = {
        sentence.strip().casefold() for text in earlier if isinstance(text, str)
        for sentence in re.split(r"(?<=[.!?…])\s+", text)
    }
    kept = [
        sentence for sentence in re.split(r"(?<=[.!?…])\s+", narration)
        if sentence.strip().casefold() not in seen
    ]
    if not kept or len(kept) == len(re.split(r"(?<=[.!?…])\s+", narration)):
        return narration
    return " ".join(kept)
