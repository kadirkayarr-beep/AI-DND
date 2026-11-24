import game
import hashlib
import interaction_adventure
import json
import living_world
import local_dialogue
import npc_statements
import re
import tr_names
import unicodedata


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

def _is_plain_person_reference(words_before, target):
    """"Kapıdaki adama" or "şu kadına" points at someone here; "kapüşonlu adama" describes one."""
    if not re.match(r"(?:adam|kad[ıi]n|ki[sş]i)\w*$", target):
        return False
    previous = living_world.normalize_text(words_before).rsplit(" ", 1)[-1]
    return previous in {"", "o", "su", "bu"} or previous.endswith(("daki", "deki", "taki", "teki"))

# Social operations need someone to address. Without an addressee (and without
# the player's own words asking for one) the model's guess cannot hijack a
# physical action such as reading a book or following someone.
_ADDRESSEE_OPERATIONS = frozenset({
    "request", "negotiate", "refuse", "agree", "conditional", "threat", "promise",
    "information", "switch_side", "betray", "generate",
})

_OFFER_OPERATIONS = frozenset({"promise", "conditional", "negotiate", "request", "threat"})

_OFFER_MARKER = re.compile(
    r"\b(?:soz ver\w*|yemin\w*|karsilig\w*|anlas\w*|pazarlik\w*|teklif\w*|takas\w*"
    r"|odul\w*|ucret\w*|altin\w*|para\w*|borc\w*|yoksa|aksi halde|pisman\w*"
    r"|ver(?:ir|eb)\w*|ister misin|istiyorum|\w+(?:irsen|irsem|arsan|arsam|ersen|ersem|ursan|ursam|ursen|ursem))\b"
)

def _fold_keep_punctuation(text):
    folded = str(text).replace("İ", "i").replace("I", "ı").casefold().translate(str.maketrans({
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u",
        "â": "a", "î": "i", "û": "u",
    }))
    return re.sub(r"[’'`]", "", folded)

_ADDRESS_VERB = r"(?:sor|don|soyl|diyor|de\b|seslen|konus|anlat|fisild|bagir|cagir|rica|yalvar|danis)"

_SPEAKING_VERB = re.compile(
    r"\b(?:bagir\w*|seslen\w*|soyle\w*|soyli\w*|diyorum|dedim|anlat\w*|"
    r"fisild\w*|rica\w*|yalvar\w*|uyar\w*|guvence\w*|merak etme|endise etme|korkma)\b"
)

_CONTINUATION_TERMS = frozenset({
    "e", "ee", "ya", "peki", "sonra", "yani", "neden", "niye", "nicin", "nasil",
    "ne", "zaman", "zamandan", "beri", "nereden", "nereye", "nerede", "kim", "kimden",
    "kime", "hangi", "hangisi", "kac", "gercekten", "oyle", "mi", "mu", "devam", "et",
    "anlat", "baska", "hem", "de", "da", "bu", "su", "o", "onu", "bunu", "ki", "acaba",
})

_OBJECT_INSPECTION = re.compile(
    r"\b(?:bak|incele|yokla|dokun|kokla|tara|elle|kurcala)\w*"
    r"(?:yorum|iyorum|uyorum|cam|cegim|cagim|ayim|eyim)\b"
)

def _claim_keywords(text):
    text = text.casefold().translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    tokens = re.findall(r"[a-z]{4,}", text)
    ignored = {
        "daha", "once", "gecen", "sefer", "keresinde", "hatirliyor", "musun", "bana",
        "sana", "bunu", "bunun", "orada", "burada", "soyledin", "soylemistin", "demistin",
        "anlatmistin", "bahsetmistin", "demistin", "ettin", "ettigini", "oldugunu", "varligini", "zaman", "zamandir",
        "gibi", "acaba", "gercekten", "hatirlamiyorum", "hatirlamiyorumdur", "duymadim",
        "soylemisti", "anlatmisti", "bahsetmisti", "demisti", "soyledi", "anlatti", "bahsetti", "dedi",
        "soylemis", "anlatmis", "bahsetmis", "konustu", "konusmustu",
    }
    suffixes = (
        "larindan", "lerinden", "larinda", "lerinde", "larinin", "lerinin", "larina", "lerine",
        "indan", "inden", "inda", "inde", "inin", "unun", "unun", "sini", "sini", "ini", "unu",
        "lari", "leri", "lar", "ler", "dan", "den", "nin", "nun", "yla", "yle", "dir", "tir",
        "siniz", "sunuz", "iyorum", "iyorum", "iyorsun", "iyorum", "misin", "musun", "tigin", "digini",
        "tigi", "digi", "tigini", "digini", "iyorum", "iyorum", "iyor", "uyor", "um", "im", "in",
    )
    result = set()
    for token in tokens:
        if token in ignored:
            continue
        stem = token
        for _ in range(2):
            suffix = next((part for part in suffixes if len(stem) - len(part) >= 4 and stem.endswith(part)), None)
            if not suffix:
                break
            stem = stem[:-len(suffix)]
        if len(stem) >= 4 and stem not in ignored:
            result.add(stem)
    if re.search(r"\b(?:ne zamandir|kac yildir|ne kadar suredir|kac yil|ne kadar zaman)\b", text):
        result.add("__duration__")
    if re.search(r"\b(?:yil\w*|sene\w*|ay\w*|gun\w*|uzun suredir|bir suredir)\b", text):
        result.add("__duration__")
    return result

def _format_npc_memory(memory_entries):
    """Format NPC memory for LLM context - clearly separates player_said and npc_said."""
    if not memory_entries:
        return []
    formatted = []
    for entry in memory_entries:
        if isinstance(entry, dict):
            speaker = entry.get("speaker", "unknown")
            text = entry.get("text", "")
            if text:
                formatted.append(f"[{speaker}] {text}")
    return formatted

_CLAIM_DENIAL_LINES = (
    "{n} bir an sana bakıp kaşlarını çatıyor. “Öyle bir şey konuştuğumuzu "
    "anımsamıyorum. Beni başka biriyle karıştırmış olmalısın.”",
    "{n} başını iki yana sallıyor. “Hayır, öyle bir sözüm yok. Kimden duyduysan "
    "iyi düşün, yanılıyorsun.”",
    "{n} omuz silkiyor. “Yanlış kapıyı çalıyorsun, dostum. Ben böyle bir şey "
    "söylemedim.”",
    "{n} sesini alçaltıyor. “Söz verdiysem hatırlardım; sözümü tutmayan biri "
    "olarak anılmak istemem. Ama bu benim ağzımdan çıkmadı.”",
)

_SPEECH_REPEAT_LINES = (
    "{n} bir an duraksıyor. “Bunu az önce söylemiştim sanırım. Başka bir şey "
    "sormak ister misin?”",
    "{n} başını sallıyor. “Aynı şeyi tekrarlamak istemem; asıl neyi merak "
    "ediyorsun, söyle bakalım.”",
    "{n} hafifçe gülümsüyor. “Bu konuda söyleyeceklerim bu kadar. Başka bir "
    "şeyden konuşalım mı?”",
    "{n} omuz silkiyor. “Aynı cevabı ikinci kez dinlemek sana ne katar ki? "
    "Sor bakalım, başka ne var?”",
)

def _lines_already_said(npc, world_state):
    log = (world_state.get("npc_speech_log") or {}).get(npc.get("id"), [])
    return [entry["npc"] for entry in log if isinstance(entry, dict) and isinstance(entry.get("npc"), str)]

def speech_repeat_line(npc, player_input="", salt=0):
    """In-character line when the model repeated what the NPC already said.

    The model is never retried; this deterministic line keeps the scene moving
    without mentioning records or verification. `salt` varies the pick when
    the same turn text repeats again.
    """
    name = living_world.public_npc_name(npc) if npc else "Bu kişi"
    seed = f"{npc.get('id', '') if isinstance(npc, dict) else ''}|{player_input}|{salt}"
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(
        _SPEECH_REPEAT_LINES
    )
    return _SPEECH_REPEAT_LINES[index].format(n=name)

# What anyone can see of a person right now. Goals, past and details stay out
# until the person says them, which the speech path carries on its own.
_NARRATOR_PROFILE_FIELDS = ("current_activity", "mood")

def _narrator_visible_profile(profile):
    if not isinstance(profile, dict):
        return {}
    return {key: profile[key] for key in _NARRATOR_PROFILE_FIELDS if isinstance(profile.get(key), str)}

def _bodies_here_context(world_state):
    """Nobody narrates an empty room over a body the world says is lying in it."""
    import fallen
    bodies = fallen.here(world_state)
    return {"bodies_here": [living_world.public_npc_name(npc) for npc in bodies[:4]]} if bodies else {}

def _untrusted_player_block(prefix, text):
    """Show player text verbatim in a block whose boundary the text cannot forge."""
    raw = str(text)
    boundary = hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    return (
        f'<UNTRUSTED_USER_INPUT id="{boundary}">\n{prefix}{raw}\n'
        f'</UNTRUSTED_USER_INPUT id="{boundary}">'
    )

def _extract_json_object(raw):
    """Parse one JSON object, closing only unmatched containers outside strings."""
    if not isinstance(raw, str):
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        return None
    stack = []
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()
            if not stack:
                try:
                    value = json.loads(cleaned[start:index + 1])
                    return value if isinstance(value, dict) else None
                except (json.JSONDecodeError, TypeError, ValueError):
                    return None
    if stack and not in_string:
        try:
            value = json.loads(cleaned[start:] + "".join(reversed(stack)))
            return value if isinstance(value, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return None

_NPC_SPEECH_LOG_KEY = "npc_speech_log"

_NPC_SPEECH_KEEP = 4

_MENTIONS_PROMPT_RULE = (
    "mentions: Konuşmada adını verdiğin bir yer ya da iz varsa onu yaz (kind place ya da trail, name tam ad, "
    "konuşmada geçtiği gibi); yer için türü listeden seç. Para, ödül, görev ya da eşya yazma. "
    "Adını verdiğin yer ya da iz yoksa kind none, name boş."
)

_VOICED_PROMPT_RULE = (
    "\nvoiced: Kentte duyduğun ve bildiğin şeyler listesinden konuşmanda gerçekten aktardıklarının anahtarlarını "
    "(k1, k2, ...) yaz, en çok üç; hiçbirini aktarmadıysan [\"none\"]. Bir şeyi aktardıysan onun kendi sözcüklerini "
    "kullan: oyuncunun günlüğüne konuşmanda gerçekten geçen yazılır."
)

def _rumour_lane_on() -> bool:
    import heard_rumours
    return heard_rumours.lane_enabled()

def _voiced_keys(raw_intent):
    """The keys the model said it passed on; None (not given or not a list) leaves the reply's own words to decide."""
    value = raw_intent.get("voiced") if isinstance(raw_intent, dict) else None
    return [key for key in value if isinstance(key, str)] if isinstance(value, list) else None

_CLAIM_REJECTION_RE = re.compile(
    r"\b(?:hatirlamiyorum|hatirlamam|animsamiyorum|soylemedim|vermedim|"
    r"yanlis|yanilgi|karistir\w*|sanmiyorum|hayir|bilmiyorum|anlamadim|"
    r"olmadi|olmaz|degil|hic)\b"
)

_CLAIM_ACCEPTANCE_RE = re.compile(
    r"\b(?:buyur\w*|iste|veriyorum|verecegim|verelim|tamam|elbette|tabii|"
    r"evet|dogru|soyledim|hatirliyorum|al|alin|"
    # Live 18 Oct: "Hayır, unutmadım", "seninle söz verdiklerim var".
    r"unutmadim|unutmam|unutmadik|hatirladim|hatirlarim|verecektim|vericektim|"
    r"tutacagim|tutarim|soz\s+verdi\w*|soz\s+vermis\w*|sozum\s+var|"
    r"soz\s+verdiklerim\w*|odeme\w*|odeyecegim|oderim)\b"
)

_SPEECH_CUT_RE = re.compile(r"[{}<>\[\]\\]|</?think|\bthe player message\b", re.IGNORECASE)

_SPEECH_META_RE = re.compile(
    r"\b(?:json|narration field|player message|context are data|instructions?|"
    r"the npc|returned is|as requested|this output|adheres)\b",
    re.IGNORECASE,
)

def _strip_pictographs(text):
    """Drop emoji and other symbol characters a small model sprays when it derails."""
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category in ("So", "Sk", "Cs", "Co", "Cn") or char in "\u200d\ufe0f\u20e3":
            continue
        kept.append(char)
    return "".join(kept)

# D-100: a Faerûn person never greets or swears by a real-world faith; these fixed phrases get this world's words.
_REAL_WORLD_FAITH = (
    (re.compile(r"\b(?:[Vv]e\s+)?[Aa]leyk[uü]m\s*(?:es)?\s*[Ss]elam\b"), "selam"),
    (re.compile(r"\b[Ss]elam(?:[uü]n|[ıi]n)\s*[Aa]leyk[uü]m\b"), "selam"),
    (re.compile(r"(?<!\w)[iİI]n[sş]allah\b"), "tanrılar izin verirse"),
    (re.compile(r"\b[Mm]a[sş]allah\b"), "vay be"),
    (re.compile(r"\b[Ee]lhamd[uü]lillah\b"), "tanrılara şükür"),
    (re.compile(r"\bAllah['’]?a\s+emanet(?:\s+ol(?:un)?)?\b"), "Tymora yar olsun"),
)

def _without_real_world_faith(text):
    """D-100: the fixed real-world faith phrases swapped for this world's, capitalised where a sentence starts."""
    for pattern, words in _REAL_WORLD_FAITH:
        def put(match, words=words, text=text):
            before = text[:match.start()].rstrip()
            return words[0].upper() + words[1:] if not before or before[-1] in ".!?…“\"" else words
        text = pattern.sub(put, text)
    return text

def _is_explicit_name_led_gesture_line(spoken_text, npc):
    """Reject only the reviewed standalone physical gesture mislabeled as speech."""
    if not isinstance(spoken_text, str) or not isinstance(npc, dict):
        return False
    name = npc.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    text = spoken_text.strip()
    for opening, closing in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")):
        if text.startswith(opening) and text.endswith(closing) and len(text) > 2:
            text = text[1:-1].strip()
            break
    return re.fullmatch(
        re.escape(name.strip()) + r"\s+kaşlarını\s+kaldırıyor[.!?…]*",
        text,
        re.IGNORECASE,
    ) is not None

def _clean_npc_stage_direction(raw):
    """Bound an optional untrusted stage direction without treating it as speech."""
    if not isinstance(raw, str) or len(raw) > 600:
        return ""
    return re.sub(r"\s+", " ", raw).strip()

def _compose_experimental_npc_speech(payload):
    """Join model fields only for whole-narration safety checks."""
    if not isinstance(payload, dict):
        return ""
    return " ".join(
        value.strip()
        for key in ("stage_direction", "spoken_text")
        if isinstance((value := payload.get(key)), str) and value.strip()
    )

def _without_label_variant(stage, name):
    """An unnamed person's stage often opens with the label again in other words ('Bir muhafız' / 'Muhafız ...').

    Only the label's own words are compared: the stage's leading words that repeat them go, and one stand-in
    word for the label's last word ('Mavi kuşaklı kişi,') goes with them when a comma closes it.
    """
    core = [w for w in living_world.normalize_text(name).split() if w != "bir"]
    words = stage.split()
    kept = 0
    while kept < len(words) and kept < len(core) and living_world.normalize_text(words[kept]) == core[kept]:
        kept += 1
    if kept == 0:
        return stage
    if kept < len(core) and kept < len(words) and words[kept].endswith(","):
        kept += 1
    return " ".join(words[kept:]).lstrip(",:; ")

def _npc_speech_rejects_claim(text):
    """True when the NPC's line clearly refuses an unverified past-promise claim."""
    folded = local_dialogue.normalize_text(text)
    if _CLAIM_ACCEPTANCE_RE.search(folded):
        return False
    return bool(_CLAIM_REJECTION_RE.search(folded))

_CLAIM_PLAIN_DENIAL_RE = re.compile(
    r"\b(?:hatirlamiyorum|hatirlamam|animsamiyorum|soylemedim|sozum\s+yok|karistir\w*)\b"
)

def _npc_speech_grants_claim(text):
    """True when the line goes along with an unrecorded claim; asking back is a person's own answer."""
    folded = local_dialogue.normalize_text(text)
    return bool(_CLAIM_ACCEPTANCE_RE.search(folded)) and not _CLAIM_PLAIN_DENIAL_RE.search(folded)

def _spoken_name_answer(spoken_text, npc):
    """The engine decided to give the name, so the shown reply carries it."""
    name = str(npc.get("name") or "").strip()
    import npc_speech_boundary
    if npc_speech_boundary.says_own_name(spoken_text, name):
        return spoken_text
    kept = [
        sentence for sentence in re.split(r"(?<=[.!?…])\s+", str(spoken_text).strip())
        if sentence and not re.search(r"\b(?:adım\w*|ismim\w*)", sentence, re.IGNORECASE)
    ]
    return " ".join([f"Adım {name}.", *kept])

_SPEECH_ANSWER_RULES = (
    "Önce oyuncunun sorusunu cevapla; sorulan şey senin işin değilse kendi işini anlatma. "
    "Biliyorsan söyle. Bilmiyorsan çıplak bir “bilmiyorum” ile bitirme: kendi sesinle, aşağıda duyduğun bir "
    "söylentiyi ya da yeri aktar veya bunu kimin ya da nerenin bilebileceğini söyle (aşağıdaki adlar ya da hancı, "
    "muhafız, pazar gibi; yeni ad uydurmadan); gizem, kaçamak veya fısıltı ekleme. Reddetmek için kişiliğinden ya da durumdan gelen bir nedenin olsun. "
    "Sıradan ifadeleri konuşmanın bağlamıyla anla; konu belliyse yeniden sordurma. "
    "Pazarlık ve yaratıcı denemelere alan aç, başarıyı garanti etme; yeni kilit, şart veya ücret "
    "uydurma. Oyuncuya karar, rıza, söz, duygu veya hareket yazma. Doğal konuş: önemli anda ağırbaşlı, "
    "uygun yerde hafif ve duruma özgü esprili; her cümleyi şakaya çevirme. Kısa cevap yeterlidir; ama kenti, "
    "bir yeri ya da olan biteni anlatman istenirse iki ile dört cümleyle, bildiğin yerlerden ve duyduklarından somut "
    "ayrıntı ver. Aynı kalıbı ve kapanış sorusunu alışkanlık yapma. Cevabın yanına bir insani dokunuş ekleyebilirsin: "
    "küçük bir yakınma, bir tepki, işine dair kısa bir söz; yeni kişi, yer veya olgu uydurmadan. "
    "Faerûn'dasın: selam, dua ve yemin bu dünyanın tanrıları ve gelenekleriyle söylenir; gerçek dünyanın dinlerine ait sözler kullanılmaz. "
    "Aleykümselam, Selamünaleyküm, inşallah, maşallah, Allah'a emanet denmez; yerine “Selam”, “Tymora yar olsun”, "
    "“Tanrılar korusun” gibi sözler söylenir.\n"
)

def _job_news_line(world, place_id):
    """Coming back to a place you had a job at, how it ended is simply there to see ("" when nothing)."""
    import town_knowledge
    import world_threads
    try:
        return world_threads.arrival_line(world, place_id) or ""
    except Exception:
        town_knowledge.log_failure()
        return ""

def _turns_to_someone_else(player_input):
    """'Yandaki kişiye dönüyorum', 'başka birine soruyorum': not whoever was being talked to."""
    words = living_world.normalize_text(player_input).split()
    return any(word in {"baska", "diger", "yandaki", "obur", "oteki"} for word in words) and any(
        word.startswith(("kisi", "biri", "adam", "kadin")) for word in words)

def _elsewhere_line(world, name):
    """Someone the town talks about is real, just not here."""
    import grounded_action
    import town_knowledge
    try:
        place = town_knowledge.place_of_person(world, name)
        if place is None:
            return None
        grounded_action.note_last(world, place["id"])
        return f"{name} burada değil; {place['name']} tarafında bulursun."
    except Exception:
        town_knowledge.log_failure()
        return None

def _overheard_work(world):
    """Nobody here to ask: what a stranger picks up in the street, tied to a real place."""
    import grounded_action
    import local_places
    import town_knowledge
    import world_threads
    try:
        world_threads.ensure(world)
        settlement = local_places.settlement_of(world, world.get("location"))
        threads = world_threads.active(world, settlement) if settlement else []
        if not threads:
            return None
        turn = int(world.get("flags", {}).get("turn_index", 0) or 0)
        fresh = [t for t in threads if t.get("heard_turn") is None]
        thread = (fresh or threads)[turn % len(fresh or threads)]
        world_threads.mark_heard(thread, turn)
        world_threads.note_heard_names(world, thread["public_line"])
        grounded_action.note_last(world, thread["place_id"])
        npc_statements.overheard_place(world, thread["place_id"], world["locations"][thread["place_id"]].get("name", ""))
        return f"Sana doğrudan iş öneren yok ama sokakta bir laf dönüyor: {thread['public_line']}"
    except Exception:
        town_knowledge.log_failure()
        return None

_ASKS_WHO_YOU_ARE = re.compile(r"\b(?:adin|adiniz|isim|ismin|isminiz|kimsin|kimsiniz)\b")

def _accept_named_job(session, world, npc, thread):
    """The same writers a yes read from the lists goes through."""
    from adventure import dialogue_jobs
    import world_threads
    if thread.get("type") == "errand":
        dialogue_jobs.accept_thread_job(session, thread, npc)
    else:
        # A reply is settled after the turn was counted; a yes read from the lists before it.
        world_threads.apply_decision(world, thread, "accepted", int(world.get("flags", {}).get("turn_index", 0) or 0) - 1)

# Right under the narrator's truth card, in one place (Dilim 2, Task 15; rc3): an instruction, not an output filter.
_REFUSED_MOVE_RULE = "MOTOR GERÇEĞİ 'olmadı' diyen bir hamleyi olmuş gibi anlatma; denemeyi ve neden olmadığını anlat."

def _bag_note(names):
    listed = ", ".join(names) if names else "hiçbir şey"
    return f"Oyuncunun üstünde gerçekten olanlar: {listed}. Başka bir şey onun elinde değildir."

def _dm_prompt_note(character, bag_names):
    """Turkish spell and item names for the narrator (ids and mechanics stay English)."""
    note = tr_names.narrator_note([*(character.get("cantrips") or []), *(character.get("spells") or [])], bag_names)
    return note + "\n" if note else ""

def _claim_denial_quotes():
    return tuple(line.split("“", 1)[-1].rstrip("”") for line in _CLAIM_DENIAL_LINES)

def _has_private_profile_value(npc, text) -> bool:
    profile = npc.get("personal_profile")
    if not isinstance(profile, dict) or not isinstance(text, str):
        return False
    return any(value.casefold() in text.casefold()
               for field, value in profile.items()
               if field not in interaction_adventure.SHAREABLE_PROFILE_FIELDS
               and isinstance(value, str) and value.strip())

_FOLLOWUP_WORDS = frozenset({
    "ismi", "adi",
    "neden", "niye", "nicin", "nasil", "yani", "peki", "onu", "bunu", "sunu",
    "hangisi", "demek",
})

def _is_short_followup(player_input):
    """True for a short reply-referring turn: "Neden?", "Neden onu?", "Nasıl yani?".

    Deliberately conservative (at most three words, one of a closed set): a real
    new question keeps all of its context, only a bare follow-up is narrowed.
    """
    if not isinstance(player_input, str) or not player_input.strip():
        return False
    words = local_dialogue.normalize_text(player_input).split()
    return 0 < len(words) <= 3 and any(word in _FOLLOWUP_WORDS for word in words)

def _experimental_speech_recap(interaction_context):
    """Plain-words recap of the last exchange, read just before the new message.

    Small models weight the end of the prompt most; the JSON alone let the
    model ignore a short follow-up such as 'Neden?'. This is attributed speech,
    not fact, and carries nothing the JSON context does not already hold.
    """
    last = (
        interaction_context.get("last_exchange")
        if isinstance(interaction_context, dict) else None
    )
    if not isinstance(last, dict):
        return ""
    player_line = str(last.get("player", "")).strip()[:240]
    npc_line = str(last.get("npc_reply", "")).strip()[:400]
    if not player_line or not npc_line:
        return ""
    return (
        "Previous exchange (what was actually said, attributed speech, not fact):\n"
        f"Player: {player_line}\n"
        f"You (the NPC): {npc_line}\n"
        "A short follow-up refers to this exchange: answer it directly, in "
        "character, without repeating your previous words.\n"
    )

def _normalize_turkish_typos(text):
    """Accent-fold for matching only; retain the original wording for Qwen."""
    text = str(text).replace("İ", "i").replace("I", "ı").casefold().translate(str.maketrans({
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u",
        # Circumflex vowels (dükkâncı, kâtip, hâlâ) fold too: typed with or
        # without the hat they must match the same word.
        "â": "a", "î": "i", "û": "u",
    }))
    text = re.sub(r"[’'`]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())

def _mechanical_outcome(player_input):
    match = re.search(r"(?im)^Result:\s*(.+?)\s*$", player_input)
    if not match:
        return None
    result = match.group(1).strip().upper()
    if "KRİTİK BAŞARISIZLIK" in result:
        return "critical_failure"
    if "KRİTİK BAŞARI" in result:
        return "critical_success"
    if result == "BAŞARISIZ":
        return "failure"
    if result == "BAŞARILI":
        return "success"
    return None

_GENERIC_NO_CHANGE_RESPONSE = (
    "Çevrede şimdilik belirgin bir değişiklik olmuyor."
)

# Every variant is marked as a scene line where it is returned.
_GENERIC_NO_CHANGE_RESPONSES = (
    _GENERIC_NO_CHANGE_RESPONSE,
    "Çevrede şimdilik belirgin bir değişiklik olmuyor; herkes kendi işine "
    "bakıyor, söz sende.",
    "Çevrede şimdilik belirgin bir değişiklik olmuyor; gözün bir şey "
    "yakalamıyor, sıra sende.",
)

_INTERNAL_PLAYER_FACING_RE = re.compile(
    r"\bpython\b|\bworld[_ ]state\b|\bunverified_lore_claim\b|"
    r"dünya\s+durumu\s+değişmedi|belirttiğin\s+eylem\s+dışında\s+sahnede\s+"
    r"yeni\s+bir\s+değişiklik\s+olmaz|no\s+state\s+change|"
    r"no\s+new\s+changes",
    re.IGNORECASE,
)

def _is_internal_player_facing_text(value):
    return isinstance(value, str) and bool(
        _INTERNAL_PLAYER_FACING_RE.search(value)
    )

def _narration_scene_type(action_result):
    action_result = action_result or {}
    action = action_result.get("action")
    if action == "attack":
        return "combat"
    if action == "travel":
        return "travel"
    if action in {"query", "inventory", "status"}:
        return "direct_query"
    if action == "skill_check":
        return "skill_check"
    if action == "dialogue" or action_result.get("npc_id"):
        return "conversation"
    return "exploration"
