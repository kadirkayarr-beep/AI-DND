import ollama
import random
import json
import re
import copy
from pathlib import Path
import os
import tempfile
import contextvars
import functools
import sys
import types


def ollama_response_content(response):
    """Read message content from both dict and typed Ollama SDK responses."""
    if isinstance(response, dict):
        message = response.get("message", {})
    else:
        message = getattr(response, "message", None)

    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


# =========================================================
# ZAR SİSTEMİ
# =========================================================

def roll_d20():
    random = _session().rng
    return random.randint(1, 20)


def get_modifier(stat):
    return (stat - 10) // 2


def roll_stat():
    random = _session().rng
    rolls = [random.randint(1, 6) for _ in range(4)]
    rolls.remove(min(rolls))
    return sum(rolls)


# =========================================================
# IRKLAR
# =========================================================

RACES = [
    "Human",
    "Elf",
    "Dwarf",
    "Halfling",
    "Gnome",
    "Half-Elf",
    "Half-Orc",
    "Tiefling",
    "Dragonborn"
]


# =========================================================
# IRK ÖZELLİKLERİ
# =========================================================

RACE_FEATURES = {

    "Human": [
        "Versatile"
    ],

    "Elf": [
        "Darkvision",
        "Fey Ancestry"
    ],

    "Dwarf": [
        "Darkvision",
        "Dwarven Resilience"
    ],

    "Halfling": [
        "Lucky"
    ],

    "Gnome": [
        "Darkvision",
        "Gnome Cunning"
    ],

    "Half-Elf": [
        "Darkvision",
        "Fey Ancestry"
    ],

    "Half-Orc": [
        "Darkvision",
        "Relentless Endurance"
    ],

    "Tiefling": [
        "Darkvision",
        "Hellish Resistance"
    ],

    "Dragonborn": [
        "Breath Weapon"
    ]
}


# =========================================================
# SINIFLAR
# =========================================================

CLASSES = [
    "Barbarian",
    "Bard",
    "Cleric",
    "Druid",
    "Fighter",
    "Monk",
    "Paladin",
    "Ranger",
    "Rogue",
    "Sorcerer",
    "Warlock",
    "Wizard"
]


# =========================================================
# SINIF ÖZELLİKLERİ
# =========================================================

CLASS_FEATURES = {

    "Barbarian": [
        "Rage"
    ],

    "Bard": [
        "Bardic Inspiration"
    ],

    "Cleric": [
        "Spellcasting",
        "Divine Domain"
    ],

    "Druid": [
        "Spellcasting",
        "Wild Shape"
    ],

    "Fighter": [
        "Fighting Style",
        "Second Wind"
    ],

    "Monk": [
        "Martial Arts",
        "Unarmored Defense"
    ],

    "Paladin": [
        "Divine Sense",
        "Lay on Hands"
    ],

    "Ranger": [
        "Favored Enemy",
        "Natural Explorer"
    ],

    "Rogue": [
        "Sneak Attack",
        "Thieves' Cant"
    ],

    "Sorcerer": [
        "Spellcasting",
        "Sorcerous Origin"
    ],

    "Warlock": [
        "Pact Magic",
        "Otherworldly Patron"
    ],

    "Wizard": [
        "Spellcasting",
        "Arcane Recovery"
    ]
}


# =========================================================
# HIT DICE
# =========================================================

CLASS_HIT_DICE = {

    "Barbarian": 12,
    "Bard": 8,
    "Cleric": 8,
    "Druid": 8,
    "Fighter": 10,
    "Monk": 8,
    "Paladin": 10,
    "Ranger": 10,
    "Rogue": 8,
    "Sorcerer": 6,
    "Warlock": 8,
    "Wizard": 6
}


# =========================================================
# SILAHLAR
# =========================================================

WEAPONS = {
    "Kılıç": {
        "damage_die": 8,
        "damage_dice": 1,
        "ability": "strength",
        "proficient": True,
        "damage_type": "slashing",
        "aliases": ["kılıç", "kılıcı", "kılıcımla", "kilic", "kilici", "kilicimla"]
    }
}


# =========================================================
# SKILLER
# =========================================================

SKILLS = {

    "Acrobatics": "dexterity",
    "Animal Handling": "wisdom",
    "Arcana": "intelligence",
    "Athletics": "strength",
    "Deception": "charisma",
    "History": "intelligence",
    "Insight": "wisdom",
    "Intimidation": "charisma",
    "Investigation": "intelligence",
    "Medicine": "wisdom",
    "Nature": "intelligence",
    "Perception": "wisdom",
    "Performance": "charisma",
    "Persuasion": "charisma",
    "Religion": "intelligence",
    "Sleight of Hand": "dexterity",
    "Stealth": "dexterity",
    "Survival": "wisdom"
}


# =========================================================
# SINIF SKILL SEÇENEKLERİ
# =========================================================

CLASS_SKILL_OPTIONS = {

    "Barbarian": [
        "Animal Handling",
        "Athletics",
        "Intimidation",
        "Nature",
        "Perception",
        "Survival"
    ],

    "Bard": [
        "Acrobatics",
        "Animal Handling",
        "Arcana",
        "Deception",
        "History",
        "Insight",
        "Intimidation",
        "Investigation",
        "Medicine",
        "Nature",
        "Perception",
        "Performance",
        "Persuasion",
        "Sleight of Hand",
        "Stealth"
    ],

    "Cleric": [
        "History",
        "Insight",
        "Medicine",
        "Persuasion",
        "Religion"
    ],

    "Druid": [
        "Arcana",
        "Animal Handling",
        "Insight",
        "Medicine",
        "Nature",
        "Perception",
        "Religion",
        "Survival"
    ],

    "Fighter": [
        "Acrobatics",
        "Animal Handling",
        "Athletics",
        "History",
        "Insight",
        "Intimidation",
        "Perception",
        "Survival"
    ],

    "Monk": [
        "Acrobatics",
        "Athletics",
        "History",
        "Insight",
        "Religion",
        "Stealth"
    ],

    "Paladin": [
        "Athletics",
        "Insight",
        "Intimidation",
        "Medicine",
        "Persuasion",
        "Religion"
    ],

    "Ranger": [
        "Animal Handling",
        "Athletics",
        "Insight",
        "Investigation",
        "Nature",
        "Perception",
        "Stealth",
        "Survival"
    ],

    "Rogue": [
        "Acrobatics",
        "Athletics",
        "Deception",
        "Insight",
        "Intimidation",
        "Investigation",
        "Perception",
        "Performance",
        "Persuasion",
        "Sleight of Hand",
        "Stealth"
    ],

    "Sorcerer": [
        "Arcana",
        "Deception",
        "Insight",
        "Intimidation",
        "Persuasion",
        "Religion"
    ],

    "Warlock": [
        "Arcana",
        "Deception",
        "History",
        "Intimidation",
        "Investigation",
        "Nature",
        "Religion"
    ],

    "Wizard": [
        "Arcana",
        "History",
        "Insight",
        "Investigation",
        "Medicine",
        "Religion"
    ]
}


# =========================================================
# ZORLUKLAR
# =========================================================

DIFFICULTY_DC = {

    "easy": 10,
    "medium": 15,
    "hard": 20,
    "very_hard": 25,
    "extreme": 30
}


# =========================================================
# SEÇİM FONKSİYONU
# =========================================================

def choose_option(title, options):

    print()
    print(title)
    print("---------------------------")

    for i, option in enumerate(options, start=1):
        print(f"{i}. {option}")

    while True:

        choice = input("\nSeçimin: ").strip()

        try:

            choice = int(choice)

            if 1 <= choice <= len(options):
                return options[choice - 1]

            print("❌ Geçersiz seçim.")

        except ValueError:

            print("❌ Lütfen sadece numara gir.")


# =========================================================
# RANDOM KARAKTER İSİMLERİ
# =========================================================

RANDOM_NAMES = [
    "Aldric", "Kael", "Thorne", "Riven", "Darius",
    "Elias", "Garrick", "Rowan", "Cedric", "Aric",
    "Mira", "Lyra", "Elara", "Seraphine", "Nyra",
    "Freya", "Astrid", "Kara", "Selene", "Rhea"
]


def create_random_character():
    """
    Testleri hızlandırmak için tamamen random karakter oluşturur.
    """

    random = _session().rng
    name = random.choice(RANDOM_NAMES)
    race = random.choice(RACES)
    character_class = random.choice(CLASSES)

    # 4d6 drop lowest x6
    rolled_stats = [roll_stat() for _ in range(6)]

    # Altı stat değerini tamamen rastgele dağıt
    random.shuffle(rolled_stats)

    (
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma
    ) = rolled_stats

    # Sınıfa uygun rastgele proficiency
    available_skills = CLASS_SKILL_OPTIONS[character_class]

    if character_class == "Rogue":
        number_to_choose = 4
    else:
        number_to_choose = 2

    proficient_skills = random.sample(
        available_skills,
        number_to_choose
    )

    print("\n🎲 RANDOM KARAKTER OLUŞTURULUYOR...")
    print("-----------------------------------")
    print("İsim:", name)
    print("Irk:", race)
    print("Sınıf:", character_class)
    print("Statlar:", rolled_stats)
    print("Skilller:", ", ".join(proficient_skills))

    return (
        name,
        race,
        character_class,
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma,
        proficient_skills
    )


# =========================================================
# STAT DAĞITIMI
# =========================================================

def assign_stats():

    rolled_stats = [roll_stat() for _ in range(6)]

    remaining_stats = rolled_stats.copy()

    stat_names = [
        ("STR", "strength"),
        ("DEX", "dexterity"),
        ("CON", "constitution"),
        ("INT", "intelligence"),
        ("WIS", "wisdom"),
        ("CHA", "charisma")
    ]

    assigned = {}

    print("\n=== STAT SONUÇLARIN ===")
    print("---------------------------")

    for i, value in enumerate(rolled_stats, start=1):
        print(f"{i}. {value}")

    print("---------------------------")

    print(
        "Bu 6 değeri STR, DEX, CON, INT, WIS ve CHA'ya dağıtacağız."
    )

    print()

    for display_name, variable_name in stat_names:

        print("Kalan değerler:", remaining_stats)

        while True:

            try:

                value = int(
                    input(f"{display_name} için değer seç: ")
                )

                if value not in remaining_stats:

                    print(
                        "❌ Bu değer mevcut değil "
                        "veya daha önce kullanıldı."
                    )

                    continue

                assigned[variable_name] = value

                remaining_stats.remove(value)

                break

            except ValueError:

                print("❌ Lütfen listedeki bir sayıyı gir.")

    return (
        assigned["strength"],
        assigned["dexterity"],
        assigned["constitution"],
        assigned["intelligence"],
        assigned["wisdom"],
        assigned["charisma"]
    )


# =========================================================
# SKILL PROFICIENCY SEÇİMİ
# =========================================================

def choose_skill_proficiencies(character_class):

    available_skills = CLASS_SKILL_OPTIONS[character_class]

    if character_class == "Rogue":
        number_to_choose = 4
    else:
        number_to_choose = 2

    chosen_skills = []

    print()
    print("=== SKILL PROFICIENCY ===")
    print("---------------------------")

    print(
        f"{character_class} için "
        f"{number_to_choose} skill seç."
    )

    print()

    for i, skill in enumerate(available_skills, start=1):
        print(f"{i}. {skill}")

    while len(chosen_skills) < number_to_choose:

        print()

        print(
            f"Seçim {len(chosen_skills) + 1}/"
            f"{number_to_choose}"
        )

        try:

            choice = int(input("Skill numarası: "))

        except ValueError:

            print("❌ Lütfen bir numara gir.")

            continue

        if choice < 1 or choice > len(available_skills):

            print("❌ Geçersiz seçim.")

            continue

        selected_skill = available_skills[choice - 1]

        if selected_skill in chosen_skills:

            print("❌ Bu skill zaten seçildi.")

            continue

        chosen_skills.append(selected_skill)

        print("✅ Seçildi:", selected_skill)

    return chosen_skills


# =========================================================
# HP
# =========================================================

def calculate_hp(character_class, constitution_mod):

    hit_die = CLASS_HIT_DICE[character_class]

    return hit_die + constitution_mod


# =========================================================
# AC
# =========================================================

def calculate_ac(
    character_class,
    dexterity_mod,
    constitution_mod,
    wisdom_mod
):

    if character_class == "Barbarian":

        return 10 + dexterity_mod + constitution_mod

    if character_class == "Monk":

        return 10 + dexterity_mod + wisdom_mod

    return 10 + dexterity_mod


# =========================================================
# SKILL CHECK
# =========================================================

def perform_skill_check(
    skill,
    dc,
    modifiers,
    proficient_skills,
    proficiency_bonus
):

    ability = SKILLS[skill]

    modifier = modifiers[ability]

    is_proficient = skill in proficient_skills

    if is_proficient:
        total_bonus = modifier + proficiency_bonus
    else:
        total_bonus = modifier

    dice = roll_d20()

    total = dice + total_bonus

    if dice == 20:

        result = "KRİTİK BAŞARI"

    elif dice == 1:

        result = "KRİTİK BAŞARISIZLIK"

    elif total >= dc:

        result = "BAŞARILI"

    else:

        result = "BAŞARISIZ"

    return {
        "skill": skill,
        "ability": ability,
        "dice": dice,
        "modifier": modifier,
        "proficient": is_proficient,
        "proficiency_bonus": proficiency_bonus if is_proficient else 0,
        "total_bonus": total_bonus,
        "total": total,
        "dc": dc,
        "result": result
    }


# =========================================================
# AI EYLEM ANALİZİ
# =========================================================

def is_dialogue_or_emotion(player_input):
    """Keep ordinary conversation, questions and feelings out of skill checks."""
    return is_npc_dialogue_input(player_input)


def is_npc_dialogue_input(player_input):
    text = player_input.casefold().strip()
    if "?" in text or is_npc_historical_claim(player_input):
        return True
    if re.search(r"\b(?:selam|merhaba|iyi günler|teşekkür|sağ ol)\b", text):
        return True
    if re.search(r"\b(?:konuş\w*|sohbet\w*|laf ed\w*|selam ver\w*)\b", text):
        return True
    return bool(re.match(
        r"^(selam|merhaba|iyi günler|teşekkür|sağ ol|korkuyorum|"
        r"sinirleniyorum|sinirliyim|üzülüyorum|üzgünüm|mutluyum|"
        r"endişeliyim|korkmuş hissediyorum|kim(sin)?\b|"
        r"burada ne zamandır|bu kasabada|bu şehirde|buralarda yeni misin|"
        r"burada güvenli|doğuda ne var|komutanı tanıyor musun|"
        r"bana biraz .{1,40} bahset|burada ne oluyor)\b",
        text
    ))


def is_npc_historical_claim(player_input):
    """Identify claims about prior NPC speech so they cannot create world facts."""
    text = player_input.casefold()
    return bool(re.search(
        r"\b(?:daha önce|az önce|önceden|geçen sefer|bir keresinde)\b.{0,180}"
        r"\b(?:söyle\w*|de\w*|anlat\w*|bahset\w*|konuş\w*)\b|"
        r"\b(?:söylemiştin|demiştin|anlatmıştın|bahsetmiştin)\b|"
        r"\bhatırlıyor musun\b",
        text,
    ))


def is_ordinary_environment_look(player_input):
    text = player_input.casefold().strip()
    simple_view = bool(re.search(
        r"\b(?:etrafıma bak|etrafa bak|çevreme bak|çevreye bak|etrafıma göz at|çevreye göz at|"
        r"etrafta ne görüyorum|çevrede ne görüyorum|etrafta ne var|çevrede ne var)\w*\b",
        text,
    ))
    return simple_view and not any(
        phrase in text for phrase in ("dikkatlice", "gözlem", "fark etmeye", "bir şey", "araştır")
    )


def npc_ambiguity_response(resolution):
    candidates = resolution.get("npcs", [])
    names = ", ".join(npc.get("name", "isimsiz kişi") for npc in candidates)
    return f"Bu tanıma uyan birden fazla kişi var: {names}. Hangisini kastettiğini belirt."


def deterministic_check_for_action(player_input):
    """Map clear, known actions before consulting the model classifier."""
    text = player_input.casefold()
    if any(token in text for token in ("gizlen", "saklan", "sessizce ilerle")):
        return {"action_type": "check", "skill": "Stealth", "difficulty": "medium"}
    if "tırman" in text or "tırmanmaya" in text:
        return {"action_type": "check", "skill": "Athletics", "difficulty": "medium"}
    door = _current_door()
    lockpick_attempt = any(term in text for term in ("kilidi açmaya", "kilidi açıyorum", "lockpick"))
    break_attempt = any(term in text for term in ("kapıyı kır", "kapıyı parçala", "kapıyı yık"))
    force_attempt = any(term in text for term in ("zorla", "iterek", "kırarak", "açmaya çalış"))
    door_attempt = lockpick_attempt or break_attempt or force_attempt or bool(re.search(r"\bkapıyı açıyorum\b", text))
    if ("kapı" in text or "kapıyı" in text or "kilit" in text) and door_attempt and door and not door["open"]:
        if door["locked"] or lockpick_attempt or break_attempt or force_attempt:
            skill = "Sleight of Hand" if lockpick_attempt else "Athletics"
            return {"action_type": "check", "skill": skill, "difficulty": "medium"}
        return {"action_type": "narrative"}
    if ("kapı" in text or "kapıyı" in text or "kilit" in text) and door_attempt and not door:
        return {"action_type": "narrative"}
    if "kilit" in text and "aç" in text and door and door["locked"]:
        return {"action_type": "check", "skill": "Sleight of Hand", "difficulty": "medium"}
    if "yalan" in text and any(token in text for token in ("anlamaya", "söyleyip", "doğru mu")):
        return {"action_type": "check", "skill": "Insight", "difficulty": "medium"}
    if any(token in text for token in (
        "ses dinliyorum", "ses dinle", "bir şey duymaya çalış", "ses geliyor mu",
        "kapının arkasından ses", "tehlike var mı", "tehlikeyi fark etmeye",
        "bir şey fark etmeye çalış", "bir şey görüyor muyum", "etrafı gözlemliyorum",
        "çevreyi gözlemliyorum", "etrafıma dikkatlice bak", "bir şey hissediyor muyum"
    )):
        return {"action_type": "check", "skill": "Perception", "difficulty": "medium"}
    if any(token in text for token in (
        "etrafı araştır", "masayı incel", "kapıyı incel", "izleri incel",
        "kilidin nasıl çalış", "gizli bir bölme ara", "gizli bölme ara",
        "ipuçlarını araştır", "ayrıntıları araştır", "bir şeyi analiz ed"
    )):
        return {"action_type": "check", "skill": "Investigation", "difficulty": "medium"}
    if any(token in text for token in ("onu korkutmaya", "gözdağı vermeye", "tehdit ediyorum")):
        return {"action_type": "check", "skill": "Intimidation", "difficulty": "medium"}
    return None


def known_player_action_narration(player_input):
    """Narrate common explicit actions without asking the model to control the hero."""
    world_state = _session().world_state
    text = player_input.casefold().strip()
    npc_name = _current_npc_name()
    location = location_display_name()

    if re.search(r"\b(masaya oturuyorum|oturuyorum)\b", text):
        if any("masa" in item.casefold() for item in feature_descriptions() + world_state["inventory"]):
            return "Masa başına oturma eylemin tamamlanır; mevcut çevre değişmeden kalır."
        return "Bu konumda world state'e kayıtlı bir masa yok; yeni eşya oluşmadı."
    if re.search(r"\b(ayağa kalkıyorum|kalkıyorum|ayağa kalk)\b", text):
        return "Ayağa kalkma hareketi tamamlanır; çevredeki sahne değişmeden sürer."
    if re.search(r"\b(yürüyorum|yürü|ilerliyorum)\b", text):
        return "Belirttiğin yöndeki yürüyüş sürerken çevredeki sesler devam eder."
    if is_ordinary_environment_look(text):
        features = feature_descriptions()
        if features:
            return f"{location} içinde kayıtlı çevre ayrıntıları şunlardır: {', '.join(features)}."
        # An ordinary glance can receive temporary atmospheric narration from the DM.
        return None
    return None


def known_character_answer(player_input):
    text = player_input.casefold()
    asks_identity = any(phrase in text for phrase in ("ben kimim", "karakterim kim", "kim oynuyorum"))
    asks_class = any(phrase in text for phrase in ("hangi sınıfım", "sınıfım ne", "hangi class"))
    asks_race = any(phrase in text for phrase in ("hangi ırktayım", "ırkım ne", "hangi ırkım"))
    asks_level = any(phrase in text for phrase in ("seviyem kaç", "levelim kaç", "kaçıncı seviyedeyim"))
    asks_name_self = any(phrase in text for phrase in (
        "benim adım ne", "benim ismim ne", "karakterimin adı ne", "karakterimin ismi ne"
    ))
    if not (asks_identity or asks_class or asks_race or asks_level or asks_name_self):
        return None
    facts = []
    if asks_identity or asks_name_self:
        facts.append(f"Adın {_session().character['name']}")
    if asks_race:
        facts.append(f"ırkın {_session().character['race']}")
    if asks_class:
        facts.append(f"sınıfın {_session().character['class']}")
    if asks_level:
        facts.append(f"seviyen {_session().character['level']}")
    return "; ".join(facts) + "."


def _detect_query_type(player_input, npc_target=None):
    """Ground questions in known entities, not in an ambient NPC alone."""
    world_state = _session().world_state
    text = _normalize_turkish_typos(player_input)
    self_phrases = (
        "ben kimim", "karakterim kim", "kim oynuyorum",
        "benim adım ne", "benim ismim ne", "karakterimin adı ne", "karakterimin ismi ne",
        "hangi sınıfım", "sınıfım ne", "hangi class",
        "hangi ırktayım", "ırkım ne", "hangi ırkım",
        "seviyem kaç", "levelim kaç", "kaçıncı seviyedeyim",
    )
    if any(_normalize_turkish_typos(phrase) in text for phrase in self_phrases):
        return "self"
    if re.search(r"\bkim(?:ler)?\b.{0,48}\b(?:var|bulun\w*|bekl\w*|dur\w*)\b", text) or \
            re.search(r"\bkimler\s+(?:burada|etrafta)\b", text):
        return "presence"
    asks_name = bool(re.search(r"\b(?:ad(?:i|in)|ism(?:i|in))\s+(?:ne|nedir)\b", text))
    location_query = any(_normalize_turkish_typos(phrase) in text for phrase in (
        "neredeyim", "nerdeyim", "nerdeyiz", "şu an neredeyim", "hangi yerdeyim", "konumum neresi",
    )) or bool(re.search(r"\bhangi\s+(?:mekan|yer|konum)\w*\b", text))
    location_id = _location_reference_in_text(player_input)
    explicit_npcs = [
        npc for npc in active_npcs()
        if _entity_reference_in_text(npc.get("name", ""), player_input)
        or _entity_reference_in_text(npc.get("role", ""), player_input)
    ]
    location_phrase = bool(re.search(
        r"\b(?:buranin|bu\s+mekanin|bu\s+yerin|bulundugum\s+yerin)\b", text
    ))
    if location_query or (asks_name and (location_phrase or location_id)):
        return "location"
    if asks_name or re.search(r"\b(?:kim|kimsin)\b", text):
        if len(explicit_npcs) == 1:
            return "npc_identity"
        if not explicit_npcs and not location_id and not location_phrase and npc_target in active_npcs():
            return "npc_identity"
        if not explicit_npcs and not location_id and not location_phrase and not npc_target:
            # A known conversational target may be recovered by the action layer,
            # but this classifier cannot invent an NPC from a bare question.
            return None
    return None


def _detect_explore_type(player_input):
    """Distinguish ordinary looking from an investigative search."""
    text = _normalize_turkish_typos(player_input)
    if _detect_query_type(player_input):
        return None
    neighborhood = bool(re.search(r"\b(?:etraf\w*|cevre\w*|bura\w*|yakin\w*|ortam\w*)\b", text))
    look = bool(re.search(r"\b(?:ne|neler|nasil|bak\w*|gor\w*|goz\s+at\w*|suz\w*|kolacan\w*|incele\w*|arastir\w*)\b", text))
    if not (neighborhood and look) and not re.search(r"\bne\s+gor\w*\b", text):
        return None
    if re.search(r"\b(?:incele\w*|arastir\w*|analiz\w*|ipuclar\w*|izleri\s+ara\w*|gizli\w*\s+ara\w*)\b", text):
        return "inspect" if re.search(r"\b(?:incele\w*|analiz\w*)\b", text) else "search"
    return "observe"


def _handle_query(player_input, query_type, npc_target=None):
    """Handle the detected query type and return response or None."""
    world_state = _session().world_state
    if query_type == "self":
        return known_character_answer(player_input)

    if query_type == "location":
        location_id = _location_reference_in_text(player_input) or world_state.get("location")
        return f"Bulunduğun yer: {location_display_name(location_id)}."

    if query_type == "presence":
        location_id = _location_reference_in_text(player_input) or world_state.get("location")
        npcs = active_npcs(location_id)
        if npcs:
            names = [f"{npc['name']} ({npc['role']})" for npc in npcs]
            return f"Burada şunlar var: {', '.join(names)}."
        return "Burada kayıtlı bir NPC yok."

    if query_type == "npc_identity" and npc_target:
        return f"{npc_target['name']}, \"Ben {npc_target['name']}, {npc_target['role']}.\" diye yanıt verir."

    return None


def resolve_python_world_action(player_input):
    """Resolve explicit world interactions and reject unsupported assertions safely."""
    world_state = _session().world_state
    text = player_input.casefold()
    door = _current_door()

    door_action = ("kapı" in text or "kapıya" in text or "kilit" in text) and any(
        token in text for token in ("aç", "kapat", "zorla", "kır", "it", "kilit", "bak", "incele")
    )
    if "kapı" in text and any(token in text for token in ("yok ettim", "yok ettin", "parçaladım", "kırdım")):
        return "Bu oyuncu beyanı kapı state'ini değiştirmez; kayıtlı kapı durumu korunuyor."
    if door_action and not door:
        return "Bu konumda world state'e kayıtlı bir kapı yok; yeni kapı oluşturulmadı."
    if not door and re.search(r"\bkapı(?:yı)?\s+(?:açıldı|açtım|kırıldı|kırdım|kapandı|kapattım)\b", text):
        return "Bu konumda kayıtlı kapı yok; oyuncu beyanı yeni kapı oluşturmaz."
    if door and re.search(r"\bkapı(?:yı)?\s+(?:açıldı|açtım|kırıldı|kırdım|kapandı|kapattım)\b", text):
        state = "açık" if door["open"] else "kilitli ve kapalı" if door["locked"] else "kapalı"
        return f"Bu oyuncu beyanı kapı state'ini değiştirmez; {door['name']} {state} kalır."

    if re.search(r"\b(?:aslında\s+)?kapı\s+yok\b", text):
        if door:
            state = "açık" if door["open"] else "kapalı"
            return f"Söylediğin şey kapı kaydını değiştirmez; {door['name']} world state'te {state} olarak kalır."
        return "Bu konumda kayıtlı bir kapı yok; sözlerin dünya durumunu değiştirmez."

    if any(token in text for token in ("duvarı yumruk", "duvara yumruk", "duvarı kır", "duvarı yık")):
        return "Bu eylem için Python'da tanımlı bir duvar hasarı sonucu yok; duvar durumu değişmedi."
    if "duvar" in text and re.search(r"çatla|yık|kır|yok", text):
        return "Bu oyuncu beyanı duvar durumunu değiştirmez; world state korunuyor."

    weapon_mentioned = any(token in text for token in ("kılıç", "kılıc", "silah"))
    if any(token in text for token in ("kılıç", "kılıc")) and any(token in text for token in ("yiyorum", "yemeye çalış")):
        return "Kılıcı yiyemezsin; Kılıç mevcut konumunda kalır."
    if weapon_mentioned and any(token in text for token in ("kırdım", "yok ettim", "sattım", "parçaladım")):
        if "Kılıç" in world_state["inventory"]:
            return "Bu eylem inventory sistemi tarafından desteklenmiyor; Kılıç envanterinde kalıyor."
        if "Kılıç" in world_state["ground_items"]:
            return "Bu eylem inventory sistemi tarafından desteklenmiyor; Kılıç yerde kalıyor."
        return "Bu eylem inventory state'ini değiştirmez."
    if re.search(r"\buçuyorum\b|\buçmaya çalış", text):
        return "Mevcut karakter durumunda uçmayı sağlayan bir yetenek bulunmuyor; konumun değişmedi."
    if re.search(r"\b(?:öldüm|ölüyorum|öleceğim)\b", text):
        return "Bu ifade tek başına karakter durumunu değiştirmez; mevcut HP durumun korunuyor."
    if re.search(r"\b(?:öldü|öldürüldü|hayatını kaybetti)\b", text):
        return "Birinin öldüğüne dair oyuncu beyanı NPC durumunu değiştirmez; kayıtlı dünya durumu korunuyor."
    if re.search(r"\böldürdüm\b", text):
        return "Bu oyuncu beyanı NPC durumunu değiştirmez; kayıtlı dünya durumu korunuyor."
    if re.search(r"\b\d+\s+altın\b|\baltın ver\b|\bpara ver\b", text):
        return "World state'te bu altını verecek bir kaynak kayıtlı değil; envanterin değişmedi."
    if re.search(r"\bkapı(?:yı|sı)?\s+açık\b", text) and door:
        state = "açık" if door["open"] else "kilitli ve kapalı" if door["locked"] else "kapalı"
        return f"Oyuncu beyanı kapı durumunu değiştirmez; {door['name']} gerçekte {state}."
    if re.search(r"\bben\s+(?:aslında\s+)?(?:kral(?:ım)?|kraliçe(?:yim)?|komutan(?:ım)?|imparator(?:um)?|lord(?:um)?|lady(?:im)?)\b", text):
        return "Bu ifade karakter veya dünya verisini değiştirmez; mevcut karakter bilgileri korunuyor."
    if re.search(r"\b(?:tavernadayım|meyhanedeyim|ormandayım|kalede(?:yim)?|buradayım)\b", text):
        return "Konum yalnızca açık bir seyahat eylemiyle değişir; mevcut konumun korunuyor."
    if re.search(r"\b(?:çantamda|envanterimde)\b.{0,40}\b(?:altın|kılıç|eşya|potion)\b", text):
        return "Oyuncu beyanı envanter verisini değiştirmez; Python envanter durumu korunuyor."
    if re.search(r"\bburada kimse yok\b", text):
        active_names = [npc["name"] for npc in world_state["npcs"] if npc.get("location") == world_state["location"]]
        return "Kayıtlı kişiler: " + (", ".join(active_names) if active_names else "bu konumda NPC yok") + ". Söylemin NPC kayıtlarını değiştirmez."
    if re.search(r"\bgeri geldim\b", text):
        return "Bir hedef konum belirtmediğin için konumun değişmedi."

    missing_item = re.search(
        r"\b([a-zçğıöşü]+(?:['’][a-zçğıöşü]+)?)\s+([a-zçğıöşü]+)\s+(?:ver|getir|hazırla)\b",
        text,
    )
    if missing_item:
        recipient, item_name = missing_item.groups()
        known_recipients = {"bana"}
        for npc in active_npcs():
            known_recipients.update((npc.get("name", "").casefold(), npc.get("role", "").casefold()))
        if not any(recipient.casefold().startswith(target) for target in known_recipients if target):
            missing_item = None
    if missing_item:
        tracked_items = {item.casefold() for item in world_state["inventory"] + world_state["ground_items"]}
        for container in world_state["containers"]:
            tracked_items.update(item.casefold() for item in container.get("contents", []))
        if item_name not in tracked_items:
            return f"World state'te {item_name} bulunduğuna dair kayıt yok; eşya oluşturulmadı."

    if door and re.search(r"\bkapıyı\s+(?:kapatıyorum|kapat)\b", text):
        if door["open"]:
            door["open"] = False
            return f"{door['name']} Python tarafından kapatıldı."
        return f"{door['name']} zaten kapalı."

    # Handle "içeri giriyorum" / "kapıyı açıp içeri giriyorum" type entries
    if re.search(r"\b(içeri giriyorum|içeri gir|içeriye giriyorum|kapıyı açıp içeri giriyorum)\b", text):
        if door:
            if door["open"]:
                return f"{door['name']} zaten açık; içeri girersin."
            if door["locked"]:
                return None  # Locked door needs skill check / key
            # Unlocked, closed door - open it and enter
            door["open"] = True
            npc_name = _current_npc_name()
            location = location_display_name()
            if location == "Taverna" and npc_name:
                return f"{door['name']} açılır. {location} salonundaki sohbet uğultusu belirginleşir. Tezgâhın arkasındaki {npc_name} burada durur."
            return f"{door['name']} açılır. {location} içindeki sesler ve çevre ayrıntıları belirginleşir."
        # No door registered at this location
        return None

    if door and re.search(r"\bkapıy(?:ı|a)\s+(?:aç|zorla|kır)|\bkilidi aç", text):
        if door["open"]:
            return f"{door['name']} zaten açık."
        if any(token in text for token in ("zorla", "kır", "parçala", "yık")):
            return None  # A forced/breaking attempt needs the Python check.
        if door["locked"]:
            return None  # The skill check owns the outcome.
        if not door["open"]:
            door["open"] = True
            return f"{door['name']} Python tarafından açıldı."
        return f"{door['name']} zaten açık."

    if ("kapı" in text or "kapıya" in text) and any(token in text for token in ("bak", "incele")):
        if not door:
            return "Bu konumda world state'e kayıtlı bir kapı yok."
        if "incele" in text or "kilidin nasıl çalış" in text:
            return None  # A real investigation check is resolved below.
        state = "kilitli ve kapalı" if door["locked"] else ("açık" if door["open"] else "kapalı")
        return f"{door['name']} {state}. {door['description']}"
    return None

def analyze_player_action(
    player_input,
    character_class,
    proficient_skills
):
    """Compatibility wrapper for the former action analyzer entry point."""
    intent = validate_intent(normalize_intent(parse_player_intent(player_input), player_input), player_input)
    if intent.get("intent") in {"stealth", "perception", "investigation", "search", "door"}:
        return {"action_type": "check", "skill": intent.get("skill", "Perception"), "difficulty": intent.get("difficulty", "medium")}
    return {"action_type": "narrative"}


# =========================================================
# AI DUNGEON MASTER CEVABI
# =========================================================


def clean_dm_response(text):

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

    # Oyuncuya soru/karar yükleyen ifadeleri temizle.
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


recent_dm_narrations = []
world_state = {
    "location": "Henüz belirlenmedi",
    "locations": {
        "tavern": {
            "id": "tavern", "name": "Taverna", "type": "building",
            "aliases": ["taverna", "tavernaya", "tavernada", "meyhane", "meyhaneye", "meyhanede"],
            "description": "",
        },
        "forest": {
            "id": "forest", "name": "Orman", "type": "wilderness",
            "aliases": ["orman", "ormana", "ormanda"],
            "description": "",
        },
        "castle": {
            "id": "castle", "name": "Kale", "type": "building",
            "aliases": ["kale", "kaleye", "kalede"],
            "description": "",
        },
    },
    "next_location_number": 1,
    "npcs": [],
    "inventory": ["Macera çantası", "Kılıç"],
    "ground_items_by_location": {},
    "ground_items": [],
    "doors": [],
    "containers": [],
    "features": [],
    "events": [],
    "flags": {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    },
    "next_npc_number": 1,
    "combat": {
        "active": False,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
        "participants": [],
        "target_id": None,
    },
    "player_combat_status": "active",
    "player_knowledge": [],
}
INITIAL_WORLD_STATE = copy.deepcopy(world_state)
SAVE_FORMAT_VERSION = 1


def _player_state_for_save():
    return {
        "name": _session().character["name"],
        "race": _session().character["race"],
        "class": _session().character["class"],
        "strength": _session().character["strength"],
        "dexterity": _session().character["dexterity"],
        "constitution": _session().character["constitution"],
        "intelligence": _session().character["intelligence"],
        "wisdom": _session().character["wisdom"],
        "charisma": _session().character["charisma"],
        "proficient_skills": list(_session().character["proficient_skills"]),
        "level": _session().character["level"],
        "proficiency_bonus": _session().character["proficiency_bonus"],
        "max_hp": _session().character["max_hp"],
        "current_hp": _session().character["current_hp"],
        "armor_class": _session().character["armor_class"],
    }


def serialize_game_state():
    """Return a JSON-safe, versioned snapshot of the complete game session."""
    recent_dm_narrations = _session().recent_dm_narrations
    world_state = _session().world_state
    return {
        "format": "ai-dnd-save",
        "version": SAVE_FORMAT_VERSION,
        "player": copy.deepcopy(_player_state_for_save()),
        "world_state": copy.deepcopy(world_state),
        "recent_dm_narrations": list(recent_dm_narrations),
    }


def _validate_save_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Kayıt dosyası bir JSON nesnesi olmalı.")
    if payload.get("format") != "ai-dnd-save":
        raise ValueError("Bu dosya AI-DND kayıt dosyası değil.")
    if payload.get("version") != SAVE_FORMAT_VERSION:
        raise ValueError("Bu kayıt sürümü desteklenmiyor.")

    player = payload.get("player")
    saved_world = payload.get("world_state")
    if not isinstance(player, dict) or not isinstance(saved_world, dict):
        raise ValueError("Kayıt oyuncu veya dünya verisini içermiyor.")

    required_player = {
        "name", "race", "class", "strength", "dexterity", "constitution",
        "intelligence", "wisdom", "charisma", "proficient_skills", "level",
        "proficiency_bonus", "max_hp", "current_hp", "armor_class",
    }
    if not required_player.issubset(player):
        raise ValueError("Kayıt oyuncu alanları eksik.")

    required_world = {
        "location", "locations", "npcs", "inventory", "doors", "features",
        "events", "flags", "combat", "player_combat_status",
    }
    if not required_world.issubset(saved_world):
        raise ValueError("Kayıt dünya alanları eksik.")
    if not isinstance(saved_world["locations"], dict):
        raise ValueError("Kayıt konumları geçersiz.")
    if not isinstance(saved_world["npcs"], list):
        raise ValueError("Kayıt NPC listesi geçersiz.")
    if not isinstance(saved_world["inventory"], list):
        raise ValueError("Kayıt envanteri geçersiz.")
    if not isinstance(player["proficient_skills"], list):
        raise ValueError("Kayıt yetenek listesi geçersiz.")
    for field in required_player - {"name", "race", "class", "proficient_skills"}:
        if type(player[field]) is not int:
            raise ValueError(f"Kayıt sayısal alanı geçersiz: {field}")
    if not isinstance(player["name"], str) or not player["name"].strip():
        raise ValueError("Karakter adı geçersiz.")
    if player["race"] not in RACES or player["class"] not in CLASSES:
        raise ValueError("Karakter ırkı veya sınıfı geçersiz.")
    if any(not isinstance(skill, str) or skill not in SKILLS
           for skill in player["proficient_skills"]):
        raise ValueError("Karakter yetenekleri geçersiz.")
    if not 0 <= player["current_hp"] <= player["max_hp"] or player["max_hp"] < 1:
        raise ValueError("Karakter HP değerleri geçersiz.")
    if player["level"] < 1 or player["proficiency_bonus"] < 0 or player["armor_class"] < 0:
        raise ValueError("Karakter mekanik değerleri geçersiz.")
    for stat in SKILLS.values():
        if not 1 <= player[stat] <= 30:
            raise ValueError("Karakter stat değeri geçersiz.")
    for key, default in INITIAL_WORLD_STATE.items():
        if key in saved_world and type(saved_world[key]) is not type(default):
            raise ValueError(f"Dünya alanı geçersiz: {key}")
    for key in ("inventory", "ground_items", "player_knowledge"):
        if any(not isinstance(item, str) for item in saved_world.get(key, [])):
            raise ValueError(f"Dünya listesi geçersiz: {key}")
    for items in saved_world.get("ground_items_by_location", {}).values():
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise ValueError("Yerdeki eşya listesi geçersiz.")
    for key in ("npcs", "doors", "containers"):
        if any(not isinstance(item, dict) for item in saved_world.get(key, [])):
            raise ValueError(f"Dünya nesneleri geçersiz: {key}")
    if any(not isinstance(item, dict) for item in saved_world["locations"].values()):
        raise ValueError("Konum kayıtları geçersiz.")
    narrations = payload.get("recent_dm_narrations", [])
    if not isinstance(narrations, list) or any(not isinstance(item, str) for item in narrations):
        raise ValueError("Anlatı geçmişi geçersiz.")


def save_game(path):
    """Atomically save a validated JSON snapshot to *path*."""
    destination = Path(path).expanduser()
    payload = serialize_game_state()
    _validate_save_payload(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_game(path):
    """Validate and restore a JSON snapshot without executing arbitrary code."""
    recent_dm_narrations = _session().recent_dm_narrations
    world_state = _session().world_state
    source = Path(path).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    _validate_save_payload(payload)

    player = payload["player"]
    saved_world = copy.deepcopy(payload["world_state"])
    saved_world.setdefault("ground_items_by_location", {})
    saved_world.setdefault("ground_items", [])
    saved_world.setdefault("containers", [])
    saved_world.setdefault("player_knowledge", [])

    world_state.clear()
    world_state.update(saved_world)
    character = _session().character
    for field in ("name", "race", "class"):
        character[field] = str(player[field])
    for field in ("strength", "dexterity", "constitution", "intelligence",
                  "wisdom", "charisma", "level", "proficiency_bonus",
                  "max_hp", "current_hp", "armor_class"):
        character[field] = int(player[field])
    character["proficient_skills"] = list(player["proficient_skills"])
    character["modifiers"] = {
        ability: get_modifier(character[ability])
        for ability in ("strength", "dexterity", "constitution",
                        "intelligence", "wisdom", "charisma")
    }
    for ability, modifier in character["modifiers"].items():
        character[f"{ability}_mod"] = modifier
    recent_dm_narrations.clear()
    recent_dm_narrations.extend(payload.get("recent_dm_narrations", []))
    _normalize_ground_items()
    ensure_combat_state()
    return serialize_game_state()


def _current_door():
    world_state = _session().world_state
    return next(
        (door for door in world_state["doors"] if door.get("location") == world_state["location"]),
        None
    )


def _normalize_ground_items():
    """Migrate legacy ground_items list to ground_items_by_location dict."""
    # Ensure ground_items_by_location exists (safe init for legacy state)
    world_state = _session().world_state
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


def ensure_combat_state():
    """Normalize legacy encounter data without reviving an incapacitated player."""
    world_state = _session().world_state
    defaults = {"active": False, "round": 0, "initiative_order": [],
                "current_turn_index": 0, "participants": [], "target_id": None}
    combat = world_state.get("combat")
    if not isinstance(combat, dict):
        combat = {}
        world_state["combat"] = combat
    for key, value in defaults.items():
        combat.setdefault(key, value)
    order = combat.get("initiative_order")
    valid_order = (isinstance(order, list) and len(order) == 2
                   and all(isinstance(actor, str) for actor in order)
                   and "player" in order and combat.get("target_id") in order
                   and combat.get("target_id") != "player")
    if combat.get("active") is not True or not valid_order:
        combat.clear()
        combat.update(defaults)
    else:
        combat["participants"] = ["player", combat["target_id"]]
        if type(combat.get("round")) is not int or combat["round"] < 1:
            combat["round"] = 1
        index = combat.get("current_turn_index")
        if type(index) is not int or not 0 <= index < len(order):
            combat["current_turn_index"] = order.index("player")
    if world_state.get("player_combat_status") not in ("active", "unconscious"):
        world_state["player_combat_status"] = "unconscious" if _session().character.get("current_hp", 1) <= 0 else "active"
    return combat


def ensure_npc_enemy_stats(npc):
    """Ensure NPC has enemy combat stats with safe defaults for legacy NPCs."""
    if "attack_bonus" not in npc:
        npc["attack_bonus"] = 2
    if "damage_die" not in npc:
        npc["damage_die"] = 6
    if "damage_dice" not in npc:
        npc["damage_dice"] = 1
    if "damage_modifier" not in npc:
        npc["damage_modifier"] = 0
    # Ensure base combat stats
    ensure_npc_combat_stats(npc)
    return npc


def location_features(location=None):
    world_state = _session().world_state
    location = location or world_state["location"]
    return [feature for feature in world_state["features"] if feature.get("location") == location]


def feature_descriptions(location=None):
    return [
        f"{feature['name']} — {feature['description']}" if feature.get("description") else feature["name"]
        for feature in location_features(location)
    ]


def active_npcs(location=None):
    world_state = _session().world_state
    location = location or world_state["location"]
    return [npc for npc in world_state["npcs"] if npc.get("location") == location]


def generate_npc_id():
    world_state = _session().world_state
    number = max(1, int(world_state.get("next_npc_number", 1)))
    existing = {npc.get("id") for npc in world_state["npcs"]}
    while f"npc_{number:03d}" in existing:
        number += 1
    world_state["next_npc_number"] = number + 1
    return f"npc_{number:03d}"


def _clean_world_text(value, limit=240):
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.replace("\x00", "").split()).strip()
    if not cleaned or len(cleaned) > limit:
        return None
    return cleaned


def _clean_world_text_list(value, item_limit=180, max_items=8):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:max_items]:
        cleaned = _clean_world_text(item, item_limit)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _has_unregistered_person_name(value, extra_names=()):
    world_state = _session().world_state
    if not isinstance(value, str):
        return False
    allowed = {_session().character["name"].casefold(), *(name.casefold() for name in extra_names if isinstance(name, str))}
    allowed.update(npc.get("name", "").casefold() for npc in world_state["npcs"])
    for location_id, location in world_state.get("locations", {}).items():
        allowed.add(str(location_id).casefold())
        allowed.update(alias.casefold() for alias in _location_alias_values(location))
    allowed.update(feature.get("name", "").casefold() for feature in world_state["features"])
    # Turkish possessive suffixes mark proper names clearly (for example, "Elias'ın").
    for match in re.finditer(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})['’][a-zçğıöşü]+\b", value):
        possessive_word = match.group(1).casefold()
        preceding = value[:match.start()].casefold().rstrip()
        is_registered_name_end = any(
            entity.endswith(" " + possessive_word)
            and preceding.endswith(entity[:-(len(possessive_word) + 1)])
            for entity in allowed if " " in entity
        )
        if possessive_word not in allowed and not is_registered_name_end:
            return True
    return False


def validate_npc_proposal(proposal, allow_other_location=False):
    world_state = _session().world_state
    if not isinstance(proposal, dict):
        return None
    name = _clean_world_text(proposal.get("name"), 40)
    role = _clean_world_text(proposal.get("role"), 48)
    location = normalize_location_id(proposal.get("location", world_state["location"]))
    if not name or not role or not location:
        return None
    if not re.fullmatch(r"[\w .’'-]+", name, flags=re.UNICODE) or "_" in name:
        return None
    if name.casefold() == _session().character["name"].casefold():
        return None
    if location not in world_state.get("locations", {}):
        return None
    if not allow_other_location and location != world_state["location"]:
        return None
    relationship = _clean_world_text(proposal.get("relationship", "neutral"), 40) or "neutral"
    backstory = _clean_world_text(proposal.get("backstory", ""), 240) or ""
    if _has_unregistered_person_name(backstory, (name,)):
        backstory = ""
    knowledge = [
        value for value in _clean_world_text_list(proposal.get("knowledge", []), 180, 8)
        if not _has_unregistered_person_name(value, (name,))
    ]
    return {
        "name": name,
        "role": role,
        "location": location,
        "personality": _clean_world_text(proposal.get("personality", ""), 180) or "",
        "appearance": _clean_world_text(proposal.get("appearance", ""), 180) or "",
        "relationship": relationship,
        "knowledge": knowledge,
        # NPC memory is recorded by Python from actual player turns, not AI claims.
        "memory": [],
        "backstory": backstory,
    }


def create_npc_from_ai(proposal):
    world_state = _session().world_state
    validated = validate_npc_proposal(proposal)
    if not validated:
        return None
    normalized_name = validated["name"].casefold()
    normalized_role = validated["role"].casefold()
    for npc in world_state["npcs"]:
        if (
            npc.get("location") == validated["location"]
            and npc.get("name", "").casefold() == normalized_name
            and npc.get("role", "").casefold() == normalized_role
        ):
            return npc
    if len(world_state["npcs"]) >= 60 or len(active_npcs(validated["location"])) >= 6:
        return None
    npc = {"id": generate_npc_id(), **validated}
    ensure_npc_combat_stats(npc)
    world_state["npcs"].append(npc)
    return npc


def ensure_npc_combat_stats(npc):
    """Ensure NPC has combat stats with safe defaults for legacy NPCs."""
    if "max_hp" not in npc:
        npc["max_hp"] = 10
    if "current_hp" not in npc:
        npc["current_hp"] = npc["max_hp"]
    if "armor_class" not in npc:
        npc["armor_class"] = 10
    if "combat_status" not in npc:
        npc["combat_status"] = "active"
    return npc


def calculate_attack_bonus():
    """Calculate player's melee attack bonus."""
    return _session().character["strength_mod"] + _session().character["proficiency_bonus"]


def roll_attack():
    """Roll d20 for attack."""
    return roll_d20()


def roll_damage(damage_die, damage_dice, ability_mod):
    """Roll damage dice."""
    random = _session().rng
    total = 0
    for _ in range(damage_dice):
        total += random.randint(1, damage_die)
    return total + ability_mod


def resolve_combat_target(player_input, npc_target=None):
    """Resolve the combat target from player input or current NPC target.
    
    Validates that the target is a canonical NPC from world_state["npcs"]
    and is in the current location. Rejects forged/detached NPC dicts.
    """
    # If explicit NPC target from reference resolution, validate it
    world_state = _session().world_state
    if npc_target:
        # Validate it's a canonical NPC from world_state
        target_id = npc_target.get("id")
        if not target_id:
            return None
        
        # Find canonical NPC by ID
        canonical_npc = next(
            (npc for npc in world_state.get("npcs", []) if npc.get("id") == target_id),
            None
        )
        if not canonical_npc:
            return None  # Not a registered NPC
        
        # Check location matches current location
        if canonical_npc.get("location") != world_state.get("location"):
            return None
        
        # Return canonical NPC (not the passed dict)
        ensure_npc_combat_stats(canonical_npc)
        return canonical_npc
    
    # Try to resolve NPC reference from player input
    resolution = resolve_npc_reference(player_input)
    if resolution["status"] == "found":
        ensure_npc_combat_stats(resolution["npc"])
        return resolution["npc"]
    elif resolution["status"] == "ambiguous":
        return "ambiguous"
    
    return None


def resolve_attack(player_input, weapon_name, weapon_data, target_npc):
    """Resolve a melee attack against a target NPC."""
    ensure_npc_combat_stats(target_npc)
    
    # Check if target is valid for combat
    if target_npc.get("combat_status") != "active":
        return {
            "action": "attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "target_id": target_npc.get("id"),
            "target_name": target_npc.get("name"),
            "reason": "Target not combat active"
        }
    
    # Roll attack
    attack_roll = roll_attack()
    attack_bonus = calculate_attack_bonus()
    attack_total = attack_roll + attack_bonus
    target_ac = target_npc.get("armor_class", 10)
    
    # Natural 1 = auto miss
    if attack_roll == 1:
        outcome = "miss"
        critical = False
    # Natural 20 = critical hit
    elif attack_roll == 20:
        critical = True
        outcome = "critical_hit"
        damage_die = WEAPONS[weapon_name]["damage_die"]
        damage_dice = WEAPONS[weapon_name]["damage_dice"] * 2
        ability_mod = _session().character.get(f"{WEAPONS[weapon_name]['ability']}_mod", 0)
        damage = roll_damage(damage_die, damage_dice, ability_mod)
    # Normal hit/miss
    elif attack_total >= target_ac:
        outcome = "hit"
        critical = False
        damage_die = WEAPONS[weapon_name]["damage_die"]
        damage_dice = WEAPONS[weapon_name]["damage_dice"]
        ability_mod = _session().character.get(f"{WEAPONS[weapon_name]['ability']}_mod", 0)
        damage = roll_damage(damage_die, damage_dice, ability_mod)
    else:
        outcome = "miss"
        critical = False
        damage = 0
    
    # Apply damage if hit
    target_hp_before = target_npc.get("current_hp", target_npc.get("max_hp", 10))
    target_hp_after = target_hp_before
    
    if outcome in ("hit", "critical_hit"):
        damage = max(1, damage)  # Minimum 1 damage
        target_hp_after = max(0, target_hp_before - damage)
        target_npc["current_hp"] = target_hp_after
        
        # Check if unconscious
        if target_hp_after <= 0:
            target_npc["combat_status"] = "unconscious"
    
    outcome_mapping = {
        "hit": "hit",
        "critical_hit": "critical_hit",
        "miss": "miss"
    }
    
    return {
        "action": "attack",
        "status": "resolved",
        "success": outcome in ("hit", "critical_hit"),
        "outcome": outcome_mapping.get(outcome, outcome),
        "target_id": target_npc.get("id"),
        "target_name": target_npc.get("name"),
        "weapon": weapon_name,
        "attack_roll": attack_roll,
        "attack_bonus": attack_bonus,
        "attack_total": attack_total,
        "target_ac": target_ac,
        "critical": critical,
        "damage": damage if outcome in ("hit", "critical_hit") else 0,
        "target_hp_before": target_hp_before,
        "target_hp_after": target_hp_after,
        "target_status": target_npc.get("combat_status", "active")
    }


def roll_initiative(dex_mod=0):
    """Roll initiative: d20 + dexterity modifier."""
    return roll_d20() + dex_mod


def roll_initiative_npc():
    """Roll initiative for NPC (default modifier 0)."""
    return roll_d20()


def roll_initiative_player():
    """Roll initiative for player."""
    return roll_initiative(_session().character["dexterity_mod"])


def find_weapon_in_inventory(weapon_name):
    """Find a specific weapon in inventory by name/aliases."""
    world_state = _session().world_state
    for item in world_state.get("inventory", []):
        for w_name, weapon_data in WEAPONS.items():
            if w_name.casefold() == weapon_name.casefold() or any(weapon_name.casefold() == alias.casefold() for alias in weapon_data.get("aliases", [])):
                if item.casefold() == w_name.casefold() or any(item.casefold() == alias.casefold() for alias in weapon_data.get("aliases", [])):
                    return w_name, weapon_data
    return None, None


def start_combat(player_target_npc):
    """Initialize combat state between player and target NPC."""
    world_state = _session().world_state
    ensure_combat_state()
    
    # Roll initiatives
    player_init = roll_initiative_player()
    npc_init = roll_initiative_npc()
    
    # Determine turn order (player wins ties)
    if player_init >= npc_init:
        initiative_order = ["player", player_target_npc.get("id")]
    else:
        initiative_order = [player_target_npc.get("id"), "player"]
    
    combat = world_state["combat"]
    combat["active"] = True
    combat["round"] = 1
    combat["initiative_order"] = initiative_order
    combat["current_turn_index"] = 0
    combat["participants"] = ["player", player_target_npc.get("id")]
    combat["target_id"] = player_target_npc.get("id")
    
    return {
        "combat_started": True,
        "round": 1,
        "initiative_order": initiative_order,
        "player_initiative": player_init,
        "npc_initiative": npc_init,
    }


def resolve_enemy_attack(target_npc):
    """Resolve one canonical local enemy attack, retaining exact HP values."""
    world_state = _session().world_state
    combat = ensure_combat_state()
    canonical = resolve_combat_target("", target_npc)
    if not canonical or canonical == "ambiguous" or (combat["active"] and canonical["id"] != combat["target_id"]):
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "invalid_target", "damage": 0}
    target_npc = ensure_npc_enemy_stats(canonical)
    if target_npc["combat_status"] != "active" or target_npc["current_hp"] <= 0:
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "invalid_target", "damage": 0}
    if _session().character["current_hp"] <= 0 or world_state["player_combat_status"] == "unconscious":
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "player_unconscious", "damage": 0}
    attack_roll = roll_d20()
    attack_bonus = target_npc["attack_bonus"]
    attack_total = attack_roll + attack_bonus
    critical = attack_roll == 20
    hit = attack_roll != 1 and (critical or attack_total >= _session().character["armor_class"])
    damage = 0
    player_hp_before = _session().character["current_hp"]
    if hit:
        dice = target_npc["damage_dice"] * (2 if critical else 1)
        damage = max(1, roll_damage(target_npc["damage_die"], dice, target_npc["damage_modifier"]))
    player_hp_after = max(0, player_hp_before - damage)
    _session().character["current_hp"] = player_hp_after
    if player_hp_after == 0:
        world_state["player_combat_status"] = "unconscious"
    return {"action": "enemy_attack", "status": "resolved", "success": hit,
            "outcome": "critical_hit" if critical else "hit" if hit else "miss",
            "actor": target_npc["id"], "target": "player", "attack_roll": attack_roll,
            "attack_bonus": attack_bonus, "attack_total": attack_total, "target_ac": _session().character["armor_class"],
            "critical": critical, "damage": damage, "target_hp_before": player_hp_before,
            "target_hp_after": player_hp_after, "target_status": world_state["player_combat_status"]}


def end_combat(reason="combat_ended"):
    """Clear the encounter idempotently; HP and incapacitation are unchanged."""
    combat = ensure_combat_state()
    combat.clear()
    combat.update({"active": False, "round": 0, "initiative_order": [],
                   "current_turn_index": 0, "participants": [], "target_id": None})
    return {"combat_ended": True, "reason": reason}


def advance_combat_turn():
    """Safely advance metadata; V2 exchanges do not use index choreography."""
    combat = ensure_combat_state()
    order = combat["initiative_order"]
    if not combat["active"] or not order:
        return False, None, False
    combat["current_turn_index"] = (combat["current_turn_index"] + 1) % len(order)
    round_changed = combat["current_turn_index"] == 0
    if round_changed:
        combat["round"] += 1
    return True, order[combat["current_turn_index"]], round_changed


def _combat_snapshot():
    """Detached snapshot of committed encounter and player combat state."""
    world_state = _session().world_state
    combat = ensure_combat_state()
    snapshot = {key: list(value) if isinstance(value, list) else value for key, value in combat.items()}
    snapshot.update(
        player_current_hp=_session().character["current_hp"],
        player_max_hp=_session().character["max_hp"],
        player_combat_status=world_state["player_combat_status"]
    )
    return snapshot


def _finish_combat_result(result, before):
    result["combat"] = _combat_snapshot()
    result["state_changes"] = _changed_state_fields(before)
    return result


def _combat_narration(result):
    """Render mechanical outcomes in natural language without another model call."""
    if result.get("direct_response"):
        return result["direct_response"]
    target = result.get("target_name") or "Rakibin"
    outcome = result.get("outcome")
    if outcome == "miss":
        text = "Saldırın hedefi ıskalar."
    elif outcome in ("hit", "critical_hit"):
        kind = "kritik bir darbe" if outcome == "critical_hit" else "bir darbe"
        text = f"{target}, {kind} alır: {result.get('damage', 0)} hasar."
    else:
        return "Bu saldırı gerçekleşmez."
    if result.get("target_status") == "unconscious":
        text += f" {target} bilincini kaybeder."
    enemy = result.get("enemy_action", {})
    if enemy.get("outcome") == "miss":
        text += " Rakibinin karşı saldırısı seni ıskalar."
    elif enemy.get("outcome") in ("hit", "critical_hit"):
        kind = "kritik " if enemy["outcome"] == "critical_hit" else ""
        text += f" Rakibinin {kind}karşı saldırısı sana isabet eder; {enemy['damage']} hasar alırsın."
    if result.get("combat", {}).get("player_combat_status") == "unconscious":
        text += " Bilincini kaybedersin."
    return text




def validate_world_updates(updates, allow_new_npcs=False, allow_new_features=False, allow_new_locations=False):
    """Whitelist narrative state updates; mechanical state is never accepted here."""
    world_state = _session().world_state
    if not isinstance(updates, dict):
        return {"create_locations": [], "create_npcs": [], "update_npcs": [], "create_features": [], "events": []}
    result = {"create_locations": [], "create_npcs": [], "update_npcs": [], "create_features": [], "events": []}

    if allow_new_locations and isinstance(updates.get("create_locations"), list):
        for proposal in updates["create_locations"][:2]:
            validated = validate_location_proposal(proposal)
            if validated:
                result["create_locations"].append(validated)

    if allow_new_npcs and isinstance(updates.get("create_npcs"), list):
        for proposal in updates["create_npcs"][:2]:
            validated = validate_npc_proposal(proposal)
            if validated:
                result["create_npcs"].append(validated)

    if isinstance(updates.get("update_npcs"), list):
        existing_by_id = {npc.get("id"): npc for npc in world_state["npcs"]}
        for proposal in updates["update_npcs"][:4]:
            if not isinstance(proposal, dict) or proposal.get("id") not in existing_by_id:
                continue
            existing_npc = existing_by_id[proposal["id"]]
            update = {"id": proposal["id"]}
            for key, limit in (("personality", 180), ("appearance", 180), ("backstory", 240), ("relationship", 40)):
                value = _clean_world_text(proposal.get(key), limit)
                if value and not _has_unregistered_person_name(value, (existing_npc.get("name", ""),)):
                    update[key] = value
            for key in ("knowledge",):
                if key in proposal:
                    additions = [
                        value for value in _clean_world_text_list(proposal[key], 180, 8)
                        if not _has_unregistered_person_name(value, (existing_npc.get("name", ""),))
                    ]
                    if additions:
                        update[key] = additions
            result["update_npcs"].append(update)

    if allow_new_features and isinstance(updates.get("create_features"), list):
        existing_features = {
            (feature.get("location"), feature.get("name", "").casefold())
            for feature in world_state["features"]
        }
        for proposal in updates["create_features"][:4]:
            if not isinstance(proposal, dict):
                continue
            location = normalize_location_id(proposal.get("location", world_state["location"]))
            name = _clean_world_text(proposal.get("name"), 60)
            description = _clean_world_text(proposal.get("description", ""), 200) or ""
            if location != world_state["location"] or not name or "\n" in name:
                continue
            item_terms = ("kahve", "bira", "şarap", "içecek", "yemek", "kadeh", "bardak", "tabak", "kavanoz", "potion", "iksir", "makine")
            if any(term in f"{name} {description}".casefold() for term in item_terms):
                continue
            key = (location, name.casefold())
            if key in existing_features or len(location_features(location)) >= 16:
                continue
            existing_features.add(key)
            result["create_features"].append({"location": location, "name": name, "description": description})

    if (allow_new_npcs or allow_new_features) and isinstance(updates.get("events"), list):
        for event in _clean_world_text_list(updates["events"], 200, 3):
            if re.search(r"\b(?:hp|damage|hasar|envanter|altın|zar|d20|dc|kapı|kılıç|silah|eşya|satın aldı|satıldı|öldü|öldür|location)\b", event.casefold()):
                continue
            if _has_unregistered_person_name(event):
                continue
            result["events"].append(event)
    return result


def merge_world_updates(updates):
    """Apply only prevalidated proposals, assigning entity IDs in Python."""
    world_state = _session().world_state
    created = []
    for proposal in updates.get("create_locations", []):
        create_location_from_proposal(proposal)
    for proposal in updates.get("create_npcs", []):
        npc = create_npc_from_ai(proposal)
        if npc and npc not in created:
            created.append(npc)
    for update in updates.get("update_npcs", []):
        npc = next((item for item in world_state["npcs"] if item.get("id") == update.get("id")), None)
        if not npc:
            continue
        for key in ("personality", "appearance", "backstory", "relationship"):
            if update.get(key):
                npc[key] = update[key]
        for key in ("knowledge",):
            if update.get(key):
                npc[key] = (npc.get(key, []) + update[key])[-8:]
    world_state["features"].extend(updates.get("create_features", []))
    for event in updates.get("events", []):
        world_state["events"].append({"location": world_state["location"], "description": event})
    world_state["events"] = world_state["events"][-20:]
    return created


def resolve_npc_reference(player_input):
    world_state = _session().world_state
    text = _normalize_turkish_typos(player_input)
    available = active_npcs()
    matches = []
    for npc in available:
        name_match = _entity_reference_in_text(npc.get("name", ""), text)
        role_match = _entity_reference_in_text(npc.get("role", ""), text)
        if name_match or role_match:
            matches.append(npc)
    explicit_unresolved_reference = bool(re.search(
        r"\b[\wçğıöşü]+(?:la|le|dan|den|tan|ten|a|e)\s+(?:konuş\w*|sohbet\w*|selam\s+ver\w*)\b",
        player_input.casefold(),
    ))
    if not matches and not explicit_unresolved_reference and (is_npc_dialogue_input(player_input) or re.search(
        r"\b(?:o adam|o kadın|ona|ondan|onunla|kendisine)\b", text
    )):
        flags = world_state.setdefault("flags", {})
        active_id = flags.get("active_npc_id") or flags.get("last_npc_id")
        active_until = flags.get("active_npc_until_turn", -1)
        active = next((npc for npc in available if npc.get("id") == active_id), None)
        if active and flags.get("turn_index", 0) <= active_until:
            matches = [active]
        elif len(available) == 1:
            matches = available[:]
        elif len(available) > 1:
            matches = available[:]
    if len(matches) == 1:
        flags = world_state.setdefault("flags", {})
        flags["last_npc_id"] = matches[0].get("id")
        flags["active_npc_id"] = matches[0].get("id")
        flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 6
        return {"status": "found", "npc": matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "npcs": matches}
    return {"status": "none", "npc": None}


def record_npc_interaction(npc, npc_reply, player_input, npc_target=None):
    """Remember a realized NPC reply AND the player's actual utterance.
    
    Stores structured memory entries with speaker attribution:
    - player_said: what the player actually said
    - npc_said: what the NPC actually replied
    
    This prevents false-memory claims while preserving actual conversation history.
    """
    # Record if NPC is explicitly targeted OR if input looks like dialogue
    is_dialogue = is_npc_dialogue_input(player_input)
    has_active_npc = npc_target is not None
    
    if not npc or not npc_reply or (not is_dialogue and not has_active_npc):
        return
    
    # Initialize memory as list if not exists
    entries = npc.setdefault("memory", [])
    
    # Clean player input
    player_text = _clean_world_text(player_input, 260)
    npc_text = _clean_world_text(npc_reply, 260)
    
    if not player_text or not npc_text:
        return
    
    # Create structured entries
    player_entry = {"speaker": "player", "text": player_text}
    npc_entry = {"speaker": "npc", "text": npc_text}
    
    # Avoid consecutive duplicates (by text content)
    def _last_text(entries):
        for e in reversed(entries):
            if isinstance(e, dict) and e.get("text"):
                return e["text"]
            elif isinstance(e, str):
                return e
        return None
    
    last = _last_text(entries)
    if last != player_text:
        entries.append(player_entry)
    if last != npc_text:
        entries.append(npc_entry)
    
    # Keep memory bounded (up to 16 structured entries)
    del entries[:-16]


def _claim_keywords(text):
    text = text.casefold().translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    tokens = re.findall(r"[a-z]{4,}", text)
    ignored = {
        "daha", "once", "gecen", "sefer", "keresinde", "hatirliyor", "musun", "bana",
        "sana", "bunu", "bunun", "orada", "burada", "soyledin", "soylemistin", "demistin",
        "anlatmistin", "bahsetmistin", "demistin", "ettin", "ettigini", "oldugunu", "varligini", "zaman", "zamandir",
        "gibi", "acaba", "gercekten", "hatirlamiyorum", "hatirlamiyorumdur", "duymadim",
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


def npc_memory_supports_claim(npc, player_input):
    return bool(npc_memory_supporting_entry(npc, player_input))


def npc_memory_supporting_entry(npc, player_input):
    """Check if NPC memory supports a player's claim about past conversation.
    
    Speaker-aware:
    - Claims about what NPC said ("sen bana X demiştin") → only search npc_said entries
    - Claims about what player said ("ben sana X söylemiştim") → only search player_said entries
    - General claims → search both
    """
    claim_terms = _claim_keywords(player_input)
    if not npc or not claim_terms:
        return None
    
    # Determine which speaker the claim refers to
    claim_text = player_input.casefold()
    claim_about_npc = any(phrase in claim_text for phrase in (
        "sen ", "senin ", "söylemiştin", "demistin", "anlatmıştın", "bahsetmiştin",
        "söylemistin", "demistin", "anlatmistin", "bahsetmistin",
        "söyledin", "dedin", "anlattın", "bahsettin",
        "hatırlıyor musun", "hatirliyor musun"
    ))
    claim_about_player = any(phrase in claim_text for phrase in (
        "ben ", "benim ", "söylemiştim", "demistim", "anlattım", "bahsetmistim",
        "söylemistim", "demistim", "anlattim", "bahsettim",
        "söyledim", "dedim", "anlattim", "bahsettim"
    ))
    
    # Determine which entries to search
    search_speakers = set()
    if claim_about_npc:
        search_speakers.add("npc")
    if claim_about_player:
        search_speakers.add("player")
    if not search_speakers:
        search_speakers = {"npc", "player"}  # General claim - search both
    
    for entry in npc.get("memory", []):
        # Handle both legacy string format and new structured format
        if isinstance(entry, dict):
            speaker = entry.get("speaker", "")
            memory_text = entry.get("text", "")
        else:
            # Legacy format - treat as unknown speaker
            speaker = "unknown"
            memory_text = entry
        
        if speaker not in search_speakers:
            continue
            
        memory_folded = memory_text.casefold()
        if any(term in memory_folded for term in (
            "böyle bir şey söylediğimi hatırlamıyorum", "boyle bir sey soyledigimi hatirlamiyorum",
            "belleğimde buna dair bir kayıt yok", "bellegimde buna dair bir kayit yok",
            "bunu söylemedim", "bunu soylemedim", "buna dair bir kayıt yok", "buna dair bir kayit yok",
        )):
            continue
        memory_terms = _claim_keywords(memory_text)
        if "__duration__" in claim_terms and "__duration__" in memory_terms:
            return memory_text
        overlap = sum(
            1 for claim in claim_terms
            if any(claim.startswith(saved) or saved.startswith(claim) for saved in memory_terms)
        )
        if overlap >= min(2, len(claim_terms)):
            return memory_text
    return None


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
        elif isinstance(entry, str):
            # Legacy format
            formatted.append(f"[legacy] {entry}")
    return formatted


def historical_claim_denial(npc):
    name = npc.get("name", "NPC") if npc else "NPC"
    return f'{name}, "Böyle bir şey söylediğimi hatırlamıyorum; belleğimde buna dair bir kayıt yok," diye yanıt verir.'


def build_world_context(npc_target=None):
    world_state = _session().world_state
    _normalize_ground_items()
    npcs = active_npcs()
    if npc_target and all(npc.get("id") != npc_target.get("id") for npc in npcs):
        npcs.append(npc_target)
    context = {
        "character": {
            "name": _session().character["name"],
            "race": _session().character["race"],
            "class": _session().character["class"],
            "level": _session().character["level"],
        },
        "player_combat": {
            "current_hp": _session().character["current_hp"],
            "max_hp": _session().character["max_hp"],
            "armor_class": _session().character["armor_class"],
            "combat_status": world_state.get("player_combat_status", "active"),
        },
        "combat": {
            "active": world_state.get("combat", {}).get("active", False),
            "round": world_state.get("combat", {}).get("round", 0),
            "initiative_order": world_state.get("combat", {}).get("initiative_order", []),
            "current_turn_index": world_state.get("combat", {}).get("current_turn_index", 0),
            "target_id": world_state.get("combat", {}).get("target_id"),
        },
        "location": {
            "id": world_state["location"],
            "label": location_display_name(world_state["location"]),
        },
        "npcs": [
            {key: npc.get(key) for key in (
                "id", "name", "role", "personality", "appearance", "relationship",
                "knowledge", "backstory",
                "current_hp", "max_hp", "armor_class", "combat_status"
            ) if npc.get(key) not in (None, "", [])}
            | {"verified_npc_memory": _format_npc_memory(npc.get("memory", []))}
            for npc in npcs[:8]
        ],
        "active_npc_id": world_state.get("flags", {}).get("active_npc_id"),
        "current_npc_target": {"id": npc_target.get("id"), "name": npc_target.get("name"), "role": npc_target.get("role")} if npc_target else None,
        "features": [{"name": item["name"], "description": item.get("description", "")} for item in location_features()[:16]],
        "inventory_summary": list(world_state["inventory"]),
        "ground_items_summary": list(world_state["ground_items_by_location"].get(world_state["location"], [])),
        "recent_events": [event["description"] for event in world_state["events"][-5:] if event.get("location") == world_state["location"]],
    }
    door = _current_door()
    if door:
        context["door"] = {key: door.get(key) for key in ("name", "description", "locked", "open", "broken")}
    return context

def location_display_name(location_id=None):
    world_state = _session().world_state
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
    return [_normalize_turkish_typos(value) for value in values if isinstance(value, str) and value.strip()]


def _reference_token_matches(reference_token, input_token):
    reference_token = _normalize_turkish_typos(reference_token)
    input_token = _normalize_turkish_typos(input_token)
    if reference_token == input_token:
        return True
    case_endings = (
        "larindan", "lerinden", "larina", "lerine", "larinda", "lerinde",
        "larini", "lerini", "ndan", "nden", "ntan", "nten", "dan", "den",
        "tan", "ten", "yla", "yle", "lar", "ler", "la", "le", "ya", "ye",
        "na", "ne", "da", "de", "ta", "te", "nin", "nun", "in", "un",
        "i", "u", "a", "e",
    )
    return any(input_token.endswith(suffix) and input_token[:-len(suffix)] == reference_token
               for suffix in case_endings)


def _entity_reference_in_text(reference, text):
    """Match a complete name, allowing Turkish case endings."""
    reference_words = re.findall(r"[a-z0-9]+", _normalize_turkish_typos(reference))
    text_words = re.findall(r"[a-z0-9]+", _normalize_turkish_typos(text))
    if not reference_words or len(text_words) < len(reference_words):
        return False
    return any(
        all(_reference_token_matches(ref_word, text_words[start + offset])
            for offset, ref_word in enumerate(reference_words))
        for start in range(len(text_words) - len(reference_words) + 1)
    )


def resolve_location_reference(reference):
    """Resolve a natural-language place name or alias to its Python-owned ID."""
    world_state = _session().world_state
    if not isinstance(reference, str) or not reference.strip():
        return None
    normalized = _normalize_turkish_typos(reference)
    locations = world_state.get("locations", {})
    if normalized in locations:
        return normalized
    for location_id, location in locations.items():
        for alias in _location_alias_values(location):
            if normalized == alias or (len(alias.split()) == 1 and _entity_reference_in_text(alias, normalized)):
                return location_id
    return None


def _location_reference_in_text(text):
    world_state = _session().world_state
    if not isinstance(text, str):
        return None
    for location_id, location in world_state.get("locations", {}).items():
        for alias in sorted(_location_alias_values(location), key=len, reverse=True):
            if _entity_reference_in_text(alias, text):
                return location_id
    return None


def normalize_location_id(value):
    return resolve_location_reference(value)


def validate_location_proposal(proposal):
    """Validate creative location data while assigning no model-provided ID."""
    if not isinstance(proposal, dict):
        return None
    name = _clean_world_text(proposal.get("name"), 60)
    location_type = _clean_world_text(proposal.get("type", "other"), 24) or "other"
    description = _clean_world_text(proposal.get("description", ""), 240) or ""
    if not name or not re.fullmatch(r"[\w .’'-]+", name, flags=re.UNICODE) or "_" in name:
        return None
    if resolve_location_reference(name):
        return None
    if location_type.casefold() not in {
        "city", "town", "village", "building", "settlement", "wilderness",
        "region", "landmark", "dungeon", "other", "şehir", "kasaba",
        "köy", "bina", "bölge", "orman", "mekân", "city_gate", "city gate",
    }:
        location_type = "other"
    elif location_type.casefold() in ("city_gate", "city gate"):
        location_type = "city"
    mechanical_terms = ("hp", "damage", "hasar", "inventory", "envanter", "altın", "d20", "dc", "zar", "kapı açık", "öldü")
    if any(term in description.casefold() for term in mechanical_terms):
        description = ""
    aliases = _clean_world_text_list(proposal.get("aliases", []), 60, 8)
    safe_aliases = []
    for alias in aliases:
        if alias.casefold() == name.casefold() or resolve_location_reference(alias):
            continue
        if re.fullmatch(r"[\w .’'-]+", alias, flags=re.UNICODE) and "_" not in alias:
            safe_aliases.append(alias)
    return {"name": name, "type": location_type, "aliases": safe_aliases, "description": description}


def create_location_from_proposal(proposal):
    world_state = _session().world_state
    validated = validate_location_proposal(proposal)
    if not validated:
        return None
    next_number = max(1, int(world_state.get("next_location_number", 1)))
    locations = world_state.setdefault("locations", {})
    while f"location_{next_number:03d}" in locations:
        next_number += 1
    location_id = f"location_{next_number:03d}"
    world_state["next_location_number"] = next_number + 1
    location = {"id": location_id, **validated}
    locations[location_id] = location
    return location


def commit_location_change(location_id):
    """Commit a location transition after Python has resolved its destination."""
    world_state = _session().world_state
    if location_id not in world_state.get("locations", {}):
        return False
    previous_location = world_state.get("location")
    world_state["location"] = location_id
    _ensure_location_entities(location_id)
    if previous_location != location_id:
        if ensure_combat_state()["active"]:
            end_combat("location_changed")
        flags = world_state.setdefault("flags", {})
        flags["active_npc_id"] = None
        flags["last_npc_id"] = None
        flags["active_npc_until_turn"] = -1
    return previous_location != location_id


INTENT_TYPES = {
    "narrative", "travel", "dialogue", "observe", "perception", "investigation",
    "stealth", "attack", "combat", "inventory", "interact", "door", "search",
    "rest", "use_item", "unknown", "query", "explore",
}
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(INTENT_TYPES)},
        "action": {"type": "string"},
        "target": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["location", "npc", "item", "feature", "none"]},
                "reference": {"type": "string"},
            },
            "required": ["type", "reference"],
            "additionalProperties": False,
        },
        "completion": {"type": "string", "enum": ["intended", "completed", "unclear"]},
        "confidence": {"type": "number"},
        "query_type": {"type": "string", "enum": ["self", "location", "presence", "npc_identity"]},
        "explore_type": {"type": "string", "enum": ["observe", "inspect", "search"]},
    },
    "required": ["intent", "action", "target", "completion", "confidence"],
    "additionalProperties": False,
}


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


def parse_player_intent(player_input):
    """Ask Qwen only to label the current input; it cannot read or write state."""
    world_state = _session().world_state
    locations = [
        {"name": value.get("name"), "aliases": value.get("aliases", [])[:6]}
        for value in list(world_state.get("locations", {}).values())[:20]
    ]
    nearby_npcs = [{"name": npc.get("name"), "role": npc.get("role")} for npc in active_npcs()[:6]]
    prompt = (
        "Oyuncunun yalnızca mevcut mesajındaki niyeti sınıflandır. Hikâye yazma, zar/DC/sonuç belirleme, "
        "dünya veya karakter state'i değiştirme. Sadece schema'daki JSON'u döndür. "
        "intent değerleri: narrative, travel, query, explore, dialogue, observe, perception, investigation, stealth, attack, "
        "combat, inventory, interact, door, search, rest, use_item, unknown. "
        "Bilgi sorularında query_type kullan: self, location, presence veya npc_identity. "
        "Çevreye sıradan bakış explore_type=observe; ayrıntılı inceleme inspect; ipucu/nesne arama search olur. "
        "Bir konum adının veya 'var' kelimesinin geçmesi tek başına seyahat değildir. "
        "Kibar soru, selam veya duygu dialogue/narrative olur; kendiliğinden skill check değildir. "
        "Duyularla fark etme perception; sistemli inceleme investigation; saklanma stealth. "
        "Yalnızca gerçekten seyahat etmeyi belirten eylem travel olur. 'X'e gitmek istiyorum' completion=intended; "
        "'X'e gidiyorum/ulaştım/girdim' completion=completed. Hedefi oyuncunun mesajından aynen çıkar; "
        "belirsizse target.reference boş kalsın. JSON alanları: intent, action, target={type,reference}, completion, confidence.\n\n"
        f"Current location: {location_display_name()}\n"
        f"Known locations: {json.dumps(locations, ensure_ascii=False)}\n"
        f"Nearby NPCs: {json.dumps(nearby_npcs, ensure_ascii=False)}\n"
        f"Current player message: {player_input}"
    )
    try:
        response = ollama.chat(
            model="qwen3:8b",
            messages=[
                {"role": "system", "content": "You are a small D&D intent parser. Return JSON only; Python owns every game fact."},
                {"role": "user", "content": prompt},
            ],
            format=INTENT_SCHEMA,
            think=False,
            options={"temperature": 0.0, "num_predict": 120},
        )
        data = _extract_json_object(ollama_response_content(response))
        return data if isinstance(data, dict) else {"intent": "unknown"}
    except Exception:
        return {"intent": "unknown"}


def _has_travel_language(player_input):
    text = _normalize_turkish_typos(player_input)
    if re.search(r"\b(?:gitmiyorum|gitme|gitmek istemiyorum|donmuyorum|donme)\b", text):
        return False
    if re.search(r"\b(?:ne|neler|kim|kimler)\b.{0,32}\bvar\b", text):
        return False
    return bool(re.search(
        r"\b(?:git\w*|gid\w*|don\w*|ulas\w*|var(?:iyorum|iyorsun|iyor|iyoruz|iyorlar|dim|din|dik|diniz|dilar|acak\w*|mak|maya)|gir\w*|gec\w*|ilerl\w*|yuru\w*)\b",
        text,
    ))


def _travel_completion(player_input, model_completion="unclear"):
    text = str(player_input).casefold()
    if re.search(r"\b(?:gitmiyorum|gitme|gitmek istemiyorum|dönmüyorum|dönme)\b", text):
        return "unclear"
    if re.search(r"\b(?:istiyorum|isterim|planlıyorum|niyetim|gideceğim|gitmeyi düşünüyorum)\b", text):
        return "intended"
    if re.search(r"\b(?:gidiyorum|gidiyoruz|gittim|girdim|giriyorum|giriyoruz|ulaştım|ulaşıyorum|vardım|varıyorum|döndüm|dönüyorum|dönüyoruz|içeri giriyorum)\b", text):
        return "completed"
    if re.search(r"\b(?:gitme|gitmiyorum|dönme|dönmüyorum)\b", text):
        return "intended"
    if model_completion in ("intended", "completed"):
        return model_completion
    return "completed" if _has_travel_language(text) else "unclear"


def _normalize_turkish_typos(text):
    """Accent-fold for matching only; retain the original wording for Qwen."""
    text = str(text).casefold().translate(str.maketrans({
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u",
    }))
    text = re.sub(r"[’'`]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def normalize_intent(raw_intent, player_input):
    """Normalize untrusted classifier output and apply deterministic intent hints."""
    world_state = _session().world_state
    raw_intent = raw_intent if isinstance(raw_intent, dict) else {}
    intent_type = str(raw_intent.get("intent", "unknown")).strip().casefold()
    if intent_type not in INTENT_TYPES:
        intent_type = "unknown"
    target = raw_intent.get("target", {})
    if isinstance(target, str):
        target = {"type": "location", "reference": target}
    if not isinstance(target, dict):
        target = {}
    reference = target.get("reference", "")
    reference = reference.strip()[:80] if isinstance(reference, str) else ""
    target_type = str(target.get("type", "none")).casefold()
    if target_type not in {"location", "npc", "item", "feature", "none"}:
        target_type = "none"
    confidence = raw_intent.get("confidence", 0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    # Normalize only for matching; preserve the player's original wording.
    normalized_input = _normalize_turkish_typos(player_input)
    query_type = raw_intent.get("query_type")
    if query_type not in {"self", "location", "presence", "npc_identity"}:
        query_type = None
    explore_type = raw_intent.get("explore_type")
    if explore_type not in {"observe", "inspect", "search"}:
        explore_type = None
    detected_query = _detect_query_type(player_input)
    detected_explore = _detect_explore_type(player_input)
    if detected_query:
        intent_type, query_type, explore_type = "query", detected_query, None
    elif detected_explore:
        intent_type, explore_type, query_type = "explore", detected_explore, None
    elif intent_type in ("observe", "explore"):
        intent_type, explore_type, query_type = "explore", explore_type or "observe", None

    known_location = _location_reference_in_text(normalized_input)
    pending = world_state.get("flags", {}).get("pending_destination")
    pending_followup = bool(pending and _has_travel_language(normalized_input) and re.search(
        r"\b(?:oraya|orada|iceri|iceriye|hedefe)\b", normalized_input
    ))
    reference_mentioned = bool(reference and _entity_reference_in_text(reference, player_input))
    if intent_type in {"query", "explore"}:
        pass
    elif known_location and _has_travel_language(normalized_input):
        intent_type = "travel"
        target_type = "location"
        reference = known_location
    elif (intent_type == "travel" or (target_type == "location" and reference_mentioned)) and _has_travel_language(normalized_input):
        intent_type = "travel"
    if pending_followup:
        intent_type = "travel"
        target_type = "location"
        reference = str(pending)

    deterministic = deterministic_check_for_action(player_input)
    if deterministic and deterministic.get("action_type") == "check":
        skill = deterministic.get("skill")
        category = {"Stealth": "stealth", "Perception": "perception", "Investigation": "investigation"}.get(skill)
        if category:
            intent_type = category
        else:
            intent_type = "door" if re.search(r"kapı|kilit", player_input.casefold()) else "interact"

    if intent_type == "unknown" and is_npc_dialogue_input(player_input):
        intent_type = "dialogue"
    completion = _travel_completion(player_input, raw_intent.get("completion", "unclear")) if intent_type == "travel" else "unclear"
    normalized = {
        "intent": intent_type,
        "action": str(raw_intent.get("action", ""))[:100],
        "target": {"type": target_type, "reference": reference},
        "completion": completion,
        "confidence": confidence,
    }
    if query_type:
        normalized["query_type"] = query_type
    if explore_type:
        normalized["explore_type"] = explore_type
    return normalized


def _normalize_turkish_location(text, reference):
    """Ground a model location target in complete player words."""
    world_state = _session().world_state
    location_id = resolve_location_reference(reference)
    if location_id:
        location = world_state.get("locations", {}).get(location_id, {})
        return any(_entity_reference_in_text(alias, text) for alias in _location_alias_values(location))
    return _entity_reference_in_text(reference, text)


def validate_intent(intent, player_input):
    """Reject unsupported/mismatched intent fields before the Python rule engine."""
    world_state = _session().world_state
    if not isinstance(intent, dict) or intent.get("intent") not in INTENT_TYPES:
        return {"intent": "unknown", "action": "", "target": {"type": "none", "reference": ""}, "completion": "unclear", "confidence": 0.0}
    target = intent.get("target", {})
    if not isinstance(target, dict):
        target = {"type": "none", "reference": ""}
    reference = target.get("reference", "")
    if not isinstance(reference, str):
        reference = ""
    reference = reference.strip()[:80]
    target_type = target.get("type", "none")
    if target_type not in {"location", "npc", "item", "feature", "none"}:
        target_type = "none"
    valid = dict(intent)
    valid["target"] = {"type": target_type, "reference": reference}
    detected_query = _detect_query_type(player_input)
    detected_explore = _detect_explore_type(player_input)
    if detected_query:
        valid.update(intent="query", query_type=detected_query, completion="unclear")
        valid.pop("explore_type", None)
        return valid
    if detected_explore:
        valid.update(intent="explore", explore_type=detected_explore, completion="unclear")
        valid.pop("query_type", None)
        return valid
    if valid["intent"] == "query":
        if valid.get("query_type") not in {"self", "location", "presence", "npc_identity"}:
            valid["intent"] = "narrative"
        valid["completion"] = "unclear"
        return valid
    if valid["intent"] in {"explore", "observe"}:
        subtype = valid.get("explore_type", "observe")
        valid.update(intent="explore", explore_type=subtype if subtype in {"observe", "inspect", "search"} else "observe", completion="unclear")
        valid.pop("query_type", None)
        return valid
    if valid["intent"] == "travel":
        text = str(player_input).casefold()
        pending = world_state.get("flags", {}).get("pending_destination")
        pending_followup = bool(pending and re.search(r"\b(?:oraya|orada|iceri|iceriye|hedefe)\b", _normalize_turkish_typos(text)))
        if not (_has_travel_language(player_input) or pending_followup):
            valid["intent"] = "dialogue" if is_npc_dialogue_input(player_input) else "narrative"
        elif not reference and not pending_followup:
            valid["intent"] = "narrative"
        elif reference and not pending_followup:
            mentioned_location = _location_reference_in_text(text)
            # More flexible reference matching for Turkish case endings
            named_in_input = _normalize_turkish_location(text, reference)
            if mentioned_location:
                valid["target"] = {"type": "location", "reference": mentioned_location}
            elif not named_in_input:
                # Even a known place cannot be selected by the model if the player did not name it.
                valid["intent"] = "dialogue" if is_npc_dialogue_input(player_input) else "narrative"
        if pending_followup and not reference:
            valid["target"] = {"type": "location", "reference": str(pending)}
        valid["completion"] = _travel_completion(player_input, valid.get("completion", "unclear"))
    return valid


def _ensure_location_entities(location):
    """Create only Python-owned mechanical entities for a known location."""
    world_state = _session().world_state
    predefined_doors = {
        "tavern": {
            "name": "Taverna Kapısı", "description": "Taverna giriş kapısı.",
            "locked": False, "open": False, "broken": False
        },
        "castle": {
            "name": "Kale Kapısı", "description": "Kalenin giriş kapısı.",
            "locked": True, "open": False, "broken": False
        },
    }
    door_data = predefined_doors.get(location)
    if door_data and not any(door.get("location") == location for door in world_state["doors"]):
        world_state["doors"].append({**door_data, "location": location})


def update_world_state_from_player(player_input):
    """Compatibility wrapper; all travel decisions use the central resolver."""
    intent = validate_intent(normalize_intent(parse_player_intent(player_input), player_input), player_input)
    result = execute_intent(intent, player_input)
    return result


def update_inventory_from_player(player_input):
    """Move the explicitly named sword using Python-owned inventory state."""
    world_state = _session().world_state
    text = player_input.casefold()
    mentions_weapon = any(token in text for token in ("kılıç", "kılıc", "silah"))
    if not mentions_weapon:
        return None

    dropping = any(token in text for token in ("bırak", "yere koy", "yere at"))
    picking_up = any(token in text for token in ("alıyorum", "yerden al", "tekrar al"))
    if not (dropping or picking_up):
        return None

    _normalize_ground_items()
    current_loc = world_state.get("location", "tavern")
    loc_items = world_state["ground_items_by_location"].get(current_loc, [])

    if dropping:
        if "Kılıç" in world_state["inventory"]:
            world_state["inventory"].remove("Kılıç")
            loc_items = world_state["ground_items_by_location"].setdefault(current_loc, [])
            if "Kılıç" not in loc_items:
                loc_items.append("Kılıç")
            return "Python durumu: Kılıç envanterden yere taşındı."
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
    world_state = _session().world_state
    text = player_input.casefold()
    succeeded = result["result"] in ("BAŞARILI", "KRİTİK BAŞARI")

    if "gizlen" in text or "saklan" in text:
        world_state["flags"]["player_hidden"] = succeeded

    door_attempt = any(phrase in text for phrase in (
        "kapıyı aç", "kapı aç", "kilidi aç", "kapıyı zorla", "kapıyı kır",
        "kapıyı parçala", "kapıyı yık", "kapıyı it",
    ))
    if door_attempt:
        door = _current_door()
        if door and succeeded:
            door["locked"] = False
            door["open"] = True
            if any(token in text for token in ("kır", "parçala", "yık")):
                door["broken"] = True


def _current_npc_name():
    world_state = _session().world_state
    for npc in world_state["npcs"]:
        if npc.get("location") == world_state["location"]:
            return npc.get("name")
    return None


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


def _fallback_narration(player_input):
    world_state = _session().world_state
    outcome = _mechanical_outcome(player_input)
    skill_match = re.search(r"(?im)^Skill:\s*(.+?)\s*$", player_input)
    skill_name = skill_match.group(1).strip() if skill_match else None
    text = player_input.casefold()
    npc_name = _current_npc_name()
    stealth_action = "gizlen" in text or "saklan" in text
    door_action = "kapı" in text or "kapıyı" in text or "kilit" in text
    known_npcs = [npc for npc in world_state["npcs"] if npc.get("location") == world_state["location"]]

    if "kılıc" in text or "kılıç" in text or "silah" in text:
        if "Kılıç" in world_state["ground_items"]:
            return "Kılıç yerde duruyor ve envanterinde bulunmuyor."
        if "Kılıç" in world_state["inventory"]:
            return "Kılıç envanterinde bulunuyor."

    target = resolve_npc_reference(player_input)
    target_npc = target.get("npc") if target.get("status") == "found" else None
    if target_npc and is_npc_historical_claim(player_input) and not npc_memory_supports_claim(target_npc, player_input):
        return historical_claim_denial(target_npc)
    if target_npc and is_npc_historical_claim(player_input):
        remembered = npc_memory_supporting_entry(target_npc, player_input) or ""
        quote = re.search(r"[\"“](.*?)[\"”]", remembered)
        if quote:
            return f'{target_npc["name"]}, "Evet, bunu söylemiştim: {quote.group(1)}" diye yanıt verir.'
        return f'{target_npc["name"]}, "Evet, bunu daha önce konuştuğumuzu hatırlıyorum," diye yanıt verir.'
    if target_npc and re.search(r"(isim|adı|adın|ismin|kimsin|kim\?)", text):
        return f'{target_npc["name"]}, "Ben {target_npc["name"]}; rolüm {target_npc["role"]}," diye yanıt verir.'
    if target_npc and re.search(r"\b(selam|merhaba|iyi günler)\b", text):
        return f'{target_npc["name"]} selamını alır ve "Merhaba," diye karşılık verir.'
    if target_npc and re.search(r"\b(?:burada ne zamandır|kaç yıldır|ne kadar süredir)\b.{0,50}\b(?:çalış|burada|taverna)", text):
        return f'{target_npc["name"]}, "Uzun süredir burada çalışıyorum; tam yıl sayısını net hatırlamıyorum," diye yanıt verir.'
    if target_npc and re.search(r"\b(?:bu kasabada|bu şehirde|doğuda ne var|güvenli bir yer|bu yerden bahset)", text):
        return f'{target_npc["name"]}, "Bu konuda bildiğim doğrulanmış ayrıntı yok; yanlış yönlendirmek istemem," diye karşılık verir.'
    if target_npc and is_npc_dialogue_input(player_input):
        return f'{target_npc["name"]}, "Bu konuda bildiğim doğrulanmış bir bilgi yok," diye yanıt verir.'
    if re.search(r"tavernaya (?:git|gidiyorum|dön|geri dön)|ormana (?:git|gidiyorum|dön|geri dön)|kaleye (?:git|gidiyorum|dön|geri dön)", text):
        place = location_display_name()
        details = feature_descriptions()
        people = [f"{npc['name']} ({npc['role']})" for npc in active_npcs()]
        people_text = f" Bu sahnede {', '.join(people)} bulunuyor." if people else ""
        details_text = f" Çevrede {', '.join(details)} var." if details else ""
        return f"{place} konumuna vardın.{people_text}{details_text}"

    if stealth_action and outcome in ("critical_failure", "failure"):
        if npc_name:
            return f"Saklanma girişimin başarısız olur; {npc_name} seni fark eder."
        return "Saklanma girişimin başarısız olur."
    if stealth_action and outcome in ("critical_success", "success"):
        if npc_name:
            return f"Saklanma girişimin başarılı olur; {npc_name} seni fark etmez."
        return "Saklanma girişimin başarılı olur."

    if skill_name == "Perception":
        if outcome in ("critical_success", "success"):
            known_features = feature_descriptions()
            details = ", ".join(known_features) if known_features else "ek kayıtlı çevre ayrıntısı"
            return f"Algılama kontrolü başarılı; mevcut kayıtlardaki çevre ayrıntıları: {details}."
        return "Algılama kontrolü başarısız; kayıtlı çevre özelliklerinin ötesinde yeni bir şey fark edilmedi."
    if skill_name == "Investigation":
        if outcome in ("critical_success", "success"):
            return "İnceleme kontrolü başarılı; Python world state'te bulunan bilgiler doğrulandı, yeni nesne veya ipucu eklenmedi."
        return "İnceleme kontrolü başarısız; world state'e yeni ipucu veya nesne eklenmedi."

    if door_action and outcome in ("critical_failure", "failure"):
        door = _current_door()
        return f"Girişim başarısız olur; {door['name']} kapalı kalır." if door else "Bu konumda açılacak kayıtlı bir kapı yok."
    if door_action and outcome in ("critical_success", "success"):
        door = _current_door()
        if door and door["open"]:
            result = f"{door['name']} açılır."
            if door.get("broken"):
                result = f"{door['name']} kırılarak açılır."
            return result
        return "Kapı açılmadı; mevcut durum korunuyor."

    if outcome in ("critical_success", "success"):
        return "Girişimin başarıya ulaşır; amaçladığın sonuç gerçekleşir."
    if outcome in ("critical_failure", "failure"):
        return "Girişimin ters gider ve amaçladığın sonuç gerçekleşmez."
    return "Belirttiğin eylem dışında sahnede yeni bir değişiklik olmaz."


def _narration_is_unsafe(narration, player_input, npc_target=None, action_result=None):
    world_state = _session().world_state
    if not isinstance(narration, str) or not narration.strip():
        return True
    if (action_result or {}).get("action") == "attack":
        # Free-form prose cannot reliably establish actor/outcome agreement.
        # Accept the verified mechanical rendering; otherwise use it as fallback.
        return narration.strip() != _combat_narration(action_result)
    text = narration.casefold()
    input_text = player_input.casefold()
    action_outcome = (action_result or {}).get("outcome")
    character_name_pattern = rf"(?<![a-zçğıöşü]){re.escape(_session().character['name'].casefold())}(?![a-zçğıöşü])"
    character_name_matches = list(re.finditer(character_name_pattern, text))
    if character_name_matches:
        travel_result = (
            (action_result or {}).get("action") == "travel"
            and (action_result or {}).get("status") == "completed"
            and (action_result or {}).get("success") is True
        )
        if not travel_result or len(character_name_matches) != 1:
            return True
        match = character_name_matches[0]
        arrival_clause = re.split(r"[,;.!?]", text[match.end():], maxsplit=1)[0]
        current_location = world_state.get("location")
        record = world_state.get("locations", {}).get(current_location, {})
        aliases = _location_alias_values(record) or [_normalize_turkish_typos(location_display_name(current_location))]
        location_pattern = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
        committed_arrival = bool(location_pattern) and re.fullmatch(
            rf"(?:{location_pattern})\w*\s+(?:ulas\w*|var\w*|gir\w*|gel\w*)",
            _normalize_turkish_typos(arrival_clause),
        )
        if not committed_arrival:
            return True
    if re.search(r"\b(eğer|belki|istersen|dilersen|açtıysan|başardıysan)\b", text):
        return True

    # The narrator may describe NPCs, but cannot add actions for the player.
    second_person_verb = re.compile(
        r"\b(?!kadın\b|adın\b|çadırın\b|yardımın\b|sırrın\b)"
        r"([a-zçğıöşü]{2,}?)(?:dın|din|dun|dün|tın|tin|tun|tün|"
        r"yorsun|ıyorsun|iyorsun|uyorsun|üyorsun|arsın|ersin|"
        r"ırsın|irsin|ursun|ürsün|mışsın|mişsin|muşsun|müşsün|"
        r"dınız|diniz|dunuz|dünüz|tınız|tiniz|tunuz|tünüz|"
        r"sınız|siniz|sunuz|sünüz|acaksın|eceksin)\b"
    )
    player_action_text = text
    if npc_target:
        quotes = re.compile(r'"[^"]*"|“[^”]*”|‘[^’]*’|\'[^\']*\'')
        player_action_text = quotes.sub(lambda quoted: " " * len(quoted.group(0)), text)
    for match in second_person_verb.finditer(player_action_text):
        if match.group(1) not in input_text:
            normalized_verb = _normalize_turkish_typos(match.group(0))
            travel_result = (
                (action_result or {}).get("action") == "travel"
                and (action_result or {}).get("status") == "completed"
                and (action_result or {}).get("success") is True
            )
            observe_result = (
                (action_result or {}).get("action") == "explore"
                and (action_result or {}).get("status") == "resolved"
                and (action_result or {}).get("explore_type") == "observe"
            )
            perceptual = observe_result and (
                normalized_verb.startswith(("gor", "duy", "isit", "sez", "algila", "gozlemle"))
                or (normalized_verb.startswith(("ede", "edi")) and text[:match.start()].rstrip().endswith("fark"))
            )
            committed_step = normalized_verb.startswith("at") and re.search(r"\badım\s*$", text[:match.start()])
            if not (travel_result and (
                normalized_verb.startswith(("ulas", "var", "gir", "git", "yuru", "gec", "ilerle", "don", "yaklas"))
                or committed_step
            )) and not perceptual:
                return True
    if re.search(r"\bsana\b.{0,35}hissettir(?:iyor|ir|di)", text):
        return True
    if re.search(r"\bbirlikte\s+otur\w*\b", text) and "otur" not in input_text:
        return True
    if re.search(r"\b(?:seni|sana)\b.{0,50}\b(?:oturt\w*|içir\w*|yedir\w*|giydir\w*|aldır\w*|kaldır\w*)\b", text):
        return True
    if re.search(r"\b(?:içelim|yiyelim|oturalım|kahve iç|bira iç|şarap iç|yemek ye)\b", text) and not any(
        term in input_text for term in ("iç", "yemek", "bira", "kahve", "şarap", "otur")
    ):
        return True
    if re.search(r"\b(?:ne içmek istersin|ne içersin|içmek ister misin|bir şey içmek ister misin)\b", text) and not any(
        term in input_text for term in ("içecek", "içmek", "kahve", "bira", "şarap")
    ):
        return True
    if re.search(r"\b(?:kahve|bira|şarap|yemek|bardak|kadeh)\b.{0,40}\b(?:önüne bırak|eline ver|sana uzat|ikram et)\w*", text):
        return True
    if npc_target:
        if re.search(r"\b(?:adın ne|ismin ne|barmenin adı ne)\b", input_text) and re.search(
            r"\b(?:sana|oyuncuya)\b.{0,70}\b(?:sorar|soruyor|diye sorar)\b.{0,70}\b(?:adın|ismin)\s+ne\b", text
        ):
            return True
        if re.search(r"\b(?:burada ne zamandır|kaç yıldır|ne kadar süredir)\b.{0,50}\b(?:çalış|burada|taverna)", input_text):
            has_relevant_reply = re.search(
                r"\b(?:yıl\w*|ay\w*|gün\w*|çalış\w*|uzun süredir|bir süredir|yeni başladım|bilmiyorum|hatırlamıyorum|emin değilim|doğrulanmış bilgi yok)\b",
                text,
            )
            if not has_relevant_reply:
                return True

    registered_names = {npc.get("name", "").casefold() for npc in world_state["npcs"]}
    registered_name_tokens = {part for name in registered_names for part in name.split()}
    known_places = {str(world_state.get("location", "")).casefold()}
    for location in world_state.get("locations", {}).values():
        known_places.update(alias.casefold() for alias in _location_alias_values(location))
    name_patterns = (
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})(?:,)?\s+(?=(?:içeri|dışarı|düşünür|korkar|yaklaşır|girer|konuşur|yanıt verir|şöyle der|"
        r"sana|senden|yakınında|yanında|ortaya çıkar|belirir|vardır|durur|gözleri|başını|adlı|isimli|"
        r"barmen|gezgin|tüccar|muhafız|komutan|sakin|yaşlı|genç|sessiz|eski|yorgun|orta yaşlı|"
        r"uzun boylu|kısa saçlı|solgun|iri yapılı|kır saçlı|kararlı))",
        r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}),\s*[\"“]",
    )
    for pattern in name_patterns:
        for match in re.finditer(pattern, narration):
            quote_prefix = narration[:match.start()].rstrip()
            if match.group(1).casefold() == "bir" and quote_prefix.endswith(("'", "’", '"', "“", "‘")):
                continue
            if match.group(1).casefold() not in registered_names | registered_name_tokens | known_places:
                return True
    if _has_unregistered_person_name(narration):
        return True

    current_location = world_state.get("location")
    current_record = world_state.get("locations", {}).get(current_location, {})
    known_facts = " ".join(feature_descriptions() + [location_display_name(current_location)] + _location_alias_values(current_record)).casefold()
    for npc in active_npcs():
        known_facts += " " + " ".join(
            str(npc.get(key, "")) for key in ("name", "role", "personality", "appearance", "backstory")
        ).casefold()
    for term in (
        "kahve", "bira", "şarap", "yemek", "kadeh", "bardak", "tabak", "kavanoz",
        "sandalye", "şömine", "masa", "müşteri", "müzisyen", "garson", "kitap",
        "sandık", "gizli oda", "gizli geçit", "hayvan", "köpek", "kedi", "at"
    ):
        item_pattern = r"\bat(?:lar|ler|ı|i|u|ü|ın|in|un|ün|a|e|ta|te|da|de)?\b" if term == "at" else rf"\b{re.escape(term)}\w*\b"
        if re.search(item_pattern, text) and term not in input_text and term not in known_facts:
            sensory_atmosphere = term in ("kahve", "bira", "şarap", "yemek") and bool(re.search(
                rf"(?:{re.escape(term)}\w*.{{0,24}}(?:kok\w*|aroma\w*|ses\w*)|(?:kok\w*|aroma\w*|ses\w*).{{0,24}}{re.escape(term)}\w*)",
                text,
            ))
            passive_setting = term in ("şömine", "masa", "sandalye") and not re.search(
                r"\b(?:önüne|sana|eline|otur|al|verir|uzatır|ikram)\b", text
            )
            if not sensory_atmosphere and not passive_setting:
                return True
    for person_term in ("adam", "kadın", "gezgin", "yolcu", "tüccar", "müşteri", "barmen", "müzisyen", "garson", "muhafız", "komutan", "asker"):
        npc_facts = " ".join(
            str(npc.get(key, ""))
            for npc in active_npcs()
            for key in ("name", "role", "personality", "appearance", "backstory")
        ).casefold()
        if person_term in text and person_term not in input_text and person_term not in npc_facts:
            return True

    if any(phrase in text for phrase in (
        "duvar çatırdar", "duvar çatlar", "duvar yıkılır", "duvar kırılır",
        "kapı parçalanır", "kapı kırılır", "karakterin ölür", "öldün", "uçmaya başlarsın",
        "500 altın kazan", "envanterine eklenir", "envanterinden çıkar"
    )):
        return True
    outcome = action_outcome or _mechanical_outcome(player_input)
    if outcome in ("failure", "critical_failure") and re.search(r"başarılı olur|başarıya ulaşır|başarır|kazanırsın", text):
        return True
    if outcome in ("success", "critical_success") and re.search(r"başarısız olur|başaramaz", text):
        return True
    if ("kapı" in input_text or "kilit" in input_text) and outcome in ("failure", "critical_failure") and re.search(
        r"(?:kapı|kapısı|giriş).{0,35}(?:açılır|aralanır|açık olur)", text
    ):
        return True

    if any(item_term in text and item_term not in input_text for item_term in ("kılıç", "kılıc", "silah")):
        return True
    if "ikram" in text or re.search(r"\b(?:sana|eline|önüne).{0,40}(?:verir|sunar|uzatır|hediye eder)\b", text):
        return True

    door = _current_door()
    if door:
        open_claim = re.search(r"(?:kapı|kapısı|giriş)\b.{0,35}\b(?:açıldı|açılır|açık|aralandı|aralanır|kırıldı|parçalandı)\b", text)
        closed_claim = re.search(r"(?:kapı|kapısı|giriş)\b.{0,35}\b(?:kapalı|kilitli)\b", text)
        if open_claim and not door["open"]:
            return True
        if closed_claim and door["open"]:
            return True
        if re.search(r"(?:kapı|kapısı)\b.{0,35}\b(?:kırıldı|parçalandı|yıkıldı)", text) and not door.get("broken", False):
            return True
        if re.search(r"(?:kilit|kapı|kapısı)\b.{0,35}\b(?:açıldı|kilitsiz|çözüldü)", text) and door["locked"]:
            return True
        if re.search(r"(?:kilit|kapı|kapısı)\b.{0,35}\bkilitli\b", text) and not door["locked"]:
            return True

    return False


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
    return is_npc_historical_claim(player_input) or any(re.search(pattern, text) for pattern in patterns)


def should_generate_npcs(player_input, location_changed=False):
    if is_player_world_assertion(player_input):
        return False
    text = player_input.casefold()
    if re.search(r"\b(?:ara\w*|bul\w*|sor\w*|tanış\w*|karşılaş\w*)\b", text):
        return True
    return bool(location_changed and not active_npcs())


def should_generate_features(player_input, location_changed=False):
    if is_player_world_assertion(player_input):
        return False
    text = player_input.casefold()
    if re.search(r"(?:etrafı araştır|çevreyi incele|etrafı incel|ipuçlarını araştır|gizli .{0,20} ara)", text):
        return True
    if _mechanical_outcome(player_input) in ("success", "critical_success") and re.search(
        r"^Skill:\s*(?:Perception|Investigation)", player_input, re.IGNORECASE | re.MULTILINE
    ):
        return True
    return bool(location_changed and not location_features())


NPC_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"}, "role": {"type": "string"},
        "location": {"type": "string"}, "personality": {"type": "string"},
        "appearance": {"type": "string"}, "relationship": {"type": "string"},
        "knowledge": {"type": "array", "items": {"type": "string"}},
        "memory": {"type": "array", "items": {"type": "string"}},
        "backstory": {"type": "string"},
    },
    "required": ["name", "role", "location"],
    "additionalProperties": False,
}
LOCATION_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "description": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "type", "description", "aliases"],
    "additionalProperties": False,
}
WORLD_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "create_locations": {"type": "array", "items": LOCATION_SCHEMA},
        "create_npcs": {"type": "array", "items": NPC_SCHEMA},
        "update_npcs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}, "personality": {"type": "string"},
                    "appearance": {"type": "string"}, "relationship": {"type": "string"},
                    "knowledge": {"type": "array", "items": {"type": "string"}},
                    "memory": {"type": "array", "items": {"type": "string"}},
                    "backstory": {"type": "string"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        "create_features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}, "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["location", "name"],
                "additionalProperties": False,
            },
        },
        "events": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["create_locations", "create_npcs", "update_npcs", "create_features", "events"],
    "additionalProperties": False,
}
DM_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "world_updates": WORLD_UPDATE_SCHEMA,
        "narration": {"type": "string"},
    },
    "required": ["narration", "world_updates"],
    "additionalProperties": False,
}


def ask_dungeon_master(
    messages,
    player_input,
    allow_new_npcs=False,
    allow_new_features=False,
    npc_target=None,
    world_entry=False,
    action_result=None,
    allow_new_locations=False,
    return_details=False,
):
    """Request one structured narration turn; apply only Python-validated lore updates."""
    world_state = _session().world_state
    context = json.dumps(build_world_context(npc_target), ensure_ascii=False, separators=(",", ":"))
    outcome = _mechanical_outcome(player_input) or (action_result or {}).get("outcome")
    outcome_guidance = ""
    if outcome in ("critical_success", "success"):
        outcome_guidance = "Python sonucu BAŞARILI; bunu değiştirme."
    elif outcome in ("critical_failure", "failure"):
        outcome_guidance = "Python sonucu BAŞARISIZ; bunu değiştirme."
    travel_guidance = ""
    if isinstance(action_result, dict) and action_result.get("action") == "travel":
        if action_result.get("status") == "intended":
            travel_guidance = "Seyahat yalnızca niyet edildi; oyuncu hedefe ulaşmadı ve konumu değişmedi."
        elif action_result.get("status") == "awaiting_proposal":
            if action_result.get("completion") == "completed":
                travel_guidance = "Oyuncu hedefe girdiğini belirtti. Hedef kayıtlı değilse yalnızca hedef adıyla eşleşen create_locations öner; Python doğrularsa bu tur varış tamamlanır."
            else:
                travel_guidance = "Oyuncu hedefe gitmek istediğini belirtti; yalnızca hedef adıyla eşleşen create_locations öner, varış olduğunu anlatma."
        elif action_result.get("status") == "failed":
            travel_guidance = "Seyahat hedefi doğrulanmadı; varış veya konum değişikliği anlatma."
    update_permissions = (
        f"create_locations izinli={'evet' if allow_new_locations else 'hayır'}; "
        f"create_npcs izinli={'evet' if allow_new_npcs else 'hayır'}; "
        f"create_features izinli={'evet' if allow_new_features else 'hayır'}; "
        f"bu tura yeni lokasyona giriş mi={'evet' if world_entry else 'hayır'}."
    )
    if world_entry and allow_new_npcs and not active_npcs():
        update_permissions += " Bu lokasyonda NPC kaydı yok; sahneye uygunsa bir özgün NPC oluştur."
    elif world_entry and active_npcs():
        update_permissions += " Bu lokasyondaki kayıtlı NPC'leri tekrar kullan; yenisini oluşturma."
    if world_entry and allow_new_features and not location_features():
        update_permissions += " Bu lokasyon için en fazla iki özgün çevre özelliği kaydet."
    npc_dialogue_guidance = ""
    if npc_target:
        npc_dialogue_guidance = (
            f" Bu tur doğrudan {npc_target.get('name')} adlı {npc_target.get('role')} ile devam eden konuşmadır. "
            "İkinci tekil kişiyle sorulan sorular bu NPC'ye yöneliktir; oyuncuya aynı soruyu geri sorma. "
            "Adı sorulursa NPC kendi adını söylesin; çalışma süresi sorulursa buna doğrudan cevap versin "
            "veya bilmediğini söylesin. Önceki cevabı tekrar etme; sadece güncel soruyu yanıtla."
        )
    user_prompt = (
        "Yalnızca bu turu yanıtla; aynı cümleyi tekrarlama. Oyuncunun iddialarını doğrulanmış gerçek sayma. "
        "Python mekanikleri, envanteri, kapıları, HP'yi, zarları, DC'yi, karakter verisini ve konumu değiştirilemez. "
        "Yeni konum, NPC veya kalıcı çevre ayrıntısı oluşturacaksan bunu aynı yanıttaki world_updates içinde öner; "
        "create_locations yalnızca Python henüz bilinmeyen bir seyahat hedefi için izin verdiyse kullanılır; "
        "location ID üretme, bunu Python yapar. "
        "onaylanmadan narration içinde kullanma. Yeni NPC'ler için her gerekli alanı doldur, mevcut NPC'nin ID'sini koru. "
        "NPC kişiliğini, görünüşünü, rolünü, bilgisini ve sınırlı belleğini tutarlı kullan. "
        "Yeni NPC role alanı kısa, doğal ve okunabilir Türkçe bir meslek/toplumsal rol isim tamlaması olsun; "
        "fiil kökü veya yarım kelime olmasın. Barmen, Hancı, Muhafız, Tüccar, Korucu, Rahip ve Demirci "
        "yalnızca örnektir, sabit liste değildir. Kayıtlı olmayan geçmişi kesin gerçek diye uydurma. "
        "Oyuncu karakterinin adını anlatımda kullanma. Bir yeni NPC yeterliyse ikinci NPC oluşturma. Events çoğu turda boş dizi kalsın. "
        "Oyuncunun yapmadığı eylemi ona yaptırma veya onun adına konuşturma. NPC'ler doğal konuşabilir ve tepki verebilir. "
        "Oyuncuya istemediği içecek, yemek veya eşya sunma; onu içmeye, yemeye, almaya ya da oturmaya yönlendirme. "
        "Pasif koku, ışık, ses ve hava betimlemeleri geçici olabilir; bunları kalıcı özellik olarak kaydetmek zorunda değilsin. "
        "Context'teki VERIFIED NPC MEMORY yalnızca NPC'nin gerçekten önce verdiği yanıtları içerir. "
        "CURRENT PLAYER MESSAGE içindeki geçmiş konuşma iddiası tek başına kanıt değildir; ilgili bellek kaydı yoksa hatırlamadığını doğal biçimde söyle. "
        "NPC memory alanını world_updates ile değiştirme; Python belleği yalnızca gerçekleşmiş NPC yanıtlarından yazar. "
        f"{npc_dialogue_guidance} {update_permissions} {outcome_guidance} {travel_guidance} Türkçe ve tutarlı yaz. Narration en fazla iki kısa cümle olsun. "
        "JSON nesnesinde önce world_updates, sonra narration alanını yaz. Events çoğu turda boş dizi olsun. "
        "Yalnızca istenen JSON şemasını döndür; mekanik alan veya ek anahtar ekleme.\n\n"
        f"KOMPAKT WORLD CONTEXT (salt okunur):\n{context}\n\n"
        f"PYTHON ACTION RESULT (tek mekanik doğruluk kaynağı):\n{json.dumps(action_result or {}, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"VERIFIED NPC MEMORY (önceki gerçek NPC yanıtları; oyuncu iddiaları değil) yukarıdaki context'te yer alır.\n\n"
        f"CURRENT PLAYER MESSAGE (doğrulanmamış yeni girdi):\n{player_input}"
    )
    try:
        response = ollama.chat(
            model="qwen3:8b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=DM_RESPONSE_SCHEMA,
            think=False,
            options={"temperature": 0.35, "num_predict": 700, "repeat_penalty": 1.15, "repeat_last_n": 128},
        )
    except Exception as error:
        print(f"⚠️ Qwen'e ulaşılamadı; Python güvenli yanıtı kullanıyor. ({error})")
        narration = _fallback_for_action_result(player_input, action_result)
        if return_details:
            return {"narration": narration, "world_updates": {}, "valid_response": False}
        if npc_target and (action_result or {}).get("action") != "attack":
            record_npc_interaction(npc_target, narration, player_input, npc_target)
        return narration

    raw = ollama_response_content(response).strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = None
    candidate = re.search(r"\{.*\}", raw, re.DOTALL)
    if candidate:
        json_text = candidate.group().strip()
        try:
            parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                data = parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            # If generation stopped after complete nested data, close only the
            # unmatched JSON containers and retry. Never repair an open string.
            stack = []
            in_string = False
            escaped = False
            for char in json_text:
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
            if stack and not in_string:
                try:
                    parsed = json.loads(json_text + "".join(reversed(stack)))
                    if isinstance(parsed, dict):
                        data = parsed
                except (json.JSONDecodeError, TypeError, ValueError):
                    data = None

    narration = data.get("narration") if data else None
    if not isinstance(narration, str) or not narration.strip():
        partial = re.search(r'"narration"\s*:\s*"((?:\\.|[^"\\])*)', raw, re.DOTALL)
        if partial:
            try:
                narration = json.loads('"' + partial.group(1) + '"')
            except (json.JSONDecodeError, TypeError, ValueError):
                narration = None

    updates = data.get("world_updates", {}) if data else {}
    if return_details:
        return {
            "narration": narration,
            "world_updates": updates if isinstance(updates, dict) else {},
            "valid_response": bool(data),
        }
    is_assertion = is_player_world_assertion(player_input)
    validated = validate_world_updates(
        updates,
        allow_new_npcs=allow_new_npcs and not is_assertion,
        allow_new_features=allow_new_features and not is_assertion,
        allow_new_locations=allow_new_locations and not is_assertion,
    )
    created_npcs = []
    if not is_assertion and data:
        created_npcs = merge_world_updates(validated)
        if len(created_npcs) == 1:
            flags = world_state.setdefault("flags", {})
            flags["last_npc_id"] = created_npcs[0].get("id")
            flags["active_npc_id"] = created_npcs[0].get("id")
            flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 6

    return finalize_narration(narration, player_input, npc_target, action_result)


def _fallback_for_action_result(player_input, action_result=None):
    world_state = _session().world_state
    result = action_result if isinstance(action_result, dict) else {}
    action = result.get("action")
    if action == "attack":
        return _combat_narration(result)
    status = result.get("status")
    if action == "travel":
        place = location_display_name(result.get("target")) if result.get("target") else result.get("target_reference", "hedef")
        if status == "intended":
            return f"{place} yönüne gitmek istediğini anladım; henüz oraya ulaşmadın."
        if status == "completed":
            return f"{place} konumuna ulaştın."
        return "Bu seyahat hedefi doğrulanamadı; konumun değişmedi."
    if action == "explore":
        place = location_display_name()
        visible = [npc.get("name", "kayıtlı kişi") for npc in active_npcs()]
        visible.extend(feature.get("name", "kayıtlı çevre özelliği") for feature in location_features())
        visible.extend(world_state.get("ground_items_by_location", {}).get(world_state.get("location"), []))
        door = _current_door()
        if door:
            state = "açık" if door.get("open") else "kilitli ve kapalı" if door.get("locked") else "kapalı"
            visible.append(f"{door.get('name', 'Kapı')} ({state})")
        if visible:
            return f"{place} çevresinde kayıtlı olanlar: {', '.join(visible)}."
        return f"{place} içinde şu an kayıtlı ayrı bir kişi, çevre özelliği veya yerde duran eşya yok."
    if result.get("direct_response"):
        return str(result["direct_response"])
    if action == "skill_check":
        skill = result.get("skill", "kontrol")
        outcome = result.get("outcome", "failure")
        door = _current_door()
        if skill == "Stealth":
            return _fallback_narration(f"gizleniyorum\nResult: {'BAŞARILI' if outcome in ('success', 'critical_success') else 'BAŞARISIZ'}")
        if skill in ("Perception", "Investigation"):
            return _fallback_narration(f"Skill: {skill}\nResult: {'BAŞARILI' if outcome in ('success', 'critical_success') else 'BAŞARISIZ'}")
        if result.get("target_type") == "door":
            if outcome in ("success", "critical_success") and door and door.get("open"):
                return f"{door.get('name', 'Kapı')} açılır."
            return f"Girişimin başarısız olur; {door.get('name', 'kapı') if door else 'kapı'} kapalı kalır."
    return _fallback_narration(player_input)


def finalize_narration(narration, player_input, npc_target=None, action_result=None):
    """Sanitize narration after Python has applied every validated proposal and state change."""
    recent_dm_narrations = _session().recent_dm_narrations
    if not isinstance(narration, str) or not narration.strip():
        narration = _fallback_for_action_result(player_input, action_result)
    narration = clean_dm_response(narration)
    if _narration_is_unsafe(narration, player_input, npc_target, action_result):
        narration = _fallback_for_action_result(player_input, action_result)
    if not narration:
        narration = _fallback_for_action_result(player_input, action_result)

    normalized = re.sub(r"\s+", " ", narration).strip().casefold()
    if any(normalized == old for old in recent_dm_narrations):
        narration = _fallback_for_action_result(player_input, action_result)

    history_target = npc_target
    if is_npc_historical_claim(player_input) and not history_target:
        resolution = resolve_npc_reference(player_input)
        history_target = resolution.get("npc") if resolution.get("status") == "found" else None
    if (action_result or {}).get("action") != "attack" and is_npc_historical_claim(player_input) and history_target and not npc_memory_supports_claim(history_target, player_input):
        narration = historical_claim_denial(history_target)

    if npc_target and (action_result or {}).get("action") != "attack":
        record_npc_interaction(npc_target, narration, player_input, npc_target)
    normalized = re.sub(r"\s+", " ", narration).strip().casefold()
    recent_dm_narrations.append(normalized)
    del recent_dm_narrations[:-8]
    return narration


# =========================================================
# OYUN BAŞLANGICI
# =========================================================

def initialize_game(creation_choice=None, input_fn=input, print_fn=print):
    """Create or reset the player state without running the game loop.

    Importing this module is intentionally side-effect free.  The terminal
    entry point calls this function interactively, while tests and other
    callers can pass a choice and receive a ready-to-use rules engine.
    """
    world_state = _session().world_state
    interactive = creation_choice is None
    if interactive:
        print_fn("===================================")
        print_fn("       AI DUNGEON MASTER")
        print_fn("===================================")
        print_fn("Oyuna hoş geldin.\n")
        print_fn("=== KARAKTER OLUŞTURMA ===")
        print_fn("---------------------------")
        print_fn("1. Normal karakter oluştur")
        print_fn("2. 🎲 Tamamen random karakter")
        while True:
            creation_choice = input_fn("\nSeçimin: ").strip()
            if creation_choice in ("1", "2"):
                break
            print_fn("❌ Lütfen 1 veya 2 seç.")
    else:
        creation_choice = str(creation_choice)

    if creation_choice == "2":
        if interactive:
            (
                character_name,
                character_race,
                character_class,
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma,
                proficient_skills
            ) = create_random_character()
        else:
            # Stable, quiet defaults give imported callers a valid game state.
            (
                character_name,
                character_race,
                character_class,
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma,
                proficient_skills
            ) = (
                "TestHero",
                "Human",
                "Fighter",
                16,
                14,
                14,
                10,
                12,
                10,
                ["Athletics", "Perception"],
            )
    else:
        character_name = input_fn("\nKarakterinin adı: ") if interactive else "TestHero"
        character_race = choose_option("=== IRK SEÇ ===", RACES) if interactive else "Human"
        character_class = choose_option("=== SINIF SEÇ ===", CLASSES) if interactive else "Fighter"
        if interactive:
            (
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma
            ) = assign_stats()
            proficient_skills = choose_skill_proficiencies(character_class)
        else:
            strength, dexterity, constitution = 16, 14, 14
            intelligence, wisdom, charisma = 10, 12, 10
            proficient_skills = ["Athletics", "Perception"]

    strength_mod = get_modifier(strength)
    dexterity_mod = get_modifier(dexterity)
    constitution_mod = get_modifier(constitution)
    intelligence_mod = get_modifier(intelligence)
    wisdom_mod = get_modifier(wisdom)
    charisma_mod = get_modifier(charisma)
    modifiers = {
        "strength": strength_mod,
        "dexterity": dexterity_mod,
        "constitution": constitution_mod,
        "intelligence": intelligence_mod,
        "wisdom": wisdom_mod,
        "charisma": charisma_mod,
    }
    level = 1
    proficiency_bonus = 2
    max_hp = calculate_hp(character_class, constitution_mod)
    current_hp = max_hp
    armor_class = calculate_ac(
        character_class,
        dexterity_mod,
        constitution_mod,
        wisdom_mod,
    )
    _session().character.update({
        "name": character_name, "race": character_race, "class": character_class,
        "strength": strength, "dexterity": dexterity, "constitution": constitution,
        "intelligence": intelligence, "wisdom": wisdom, "charisma": charisma,
        "proficient_skills": proficient_skills, "level": level,
        "proficiency_bonus": proficiency_bonus, "max_hp": max_hp,
        "current_hp": current_hp, "armor_class": armor_class,
        "strength_mod": strength_mod, "dexterity_mod": dexterity_mod,
        "constitution_mod": constitution_mod, "intelligence_mod": intelligence_mod,
        "wisdom_mod": wisdom_mod, "charisma_mod": charisma_mod, "modifiers": modifiers,
    })

    if interactive:
        print_fn()
        print_fn("===================================")
        print_fn("       KARAKTERİN OLUŞTURULDU")
        print_fn("===================================")
        print_fn("İsim:", character_name)
        print_fn("Irk:", character_race)
        print_fn("Sınıf:", character_class)
        print_fn()
        print_fn("LEVEL:", level)
        print_fn("HP:", current_hp, "/", max_hp)
        print_fn("AC:", armor_class)
        print_fn("Proficiency Bonus: +", proficiency_bonus)
        print_fn()
        print_fn("IRK ÖZELLİKLERİ")
        print_fn("---------------------------")
        for feature in RACE_FEATURES[character_race]:
            print_fn("-", feature)
        print_fn()
        print_fn("SINIF ÖZELLİKLERİ")
        print_fn("---------------------------")
        for feature in CLASS_FEATURES[character_class]:
            print_fn("-", feature)
        print_fn()
        print_fn("SKILL PROFICIENCIES")
        print_fn("---------------------------")
        for skill in proficient_skills:
            print_fn("-", skill, "(" + SKILLS[skill].upper() + ")")
        print_fn()
        print_fn("INVENTORY")
        print_fn("---------------------------")
        for item in world_state["inventory"]:
            print_fn("-", item)
        print_fn()
        print_fn("STATLAR")
        print_fn("---------------------------")
        for label, value in (
            ("STR", strength),
            ("DEX", dexterity),
            ("CON", constitution),
            ("INT", intelligence),
            ("WIS", wisdom),
            ("CHA", charisma),
        ):
            print_fn(f"{label}:", value)
        print_fn()
        print_fn("MODIFIERLAR")
        print_fn("---------------------------")
        for label, value in (
            ("STR", strength_mod),
            ("DEX", dexterity_mod),
            ("CON", constitution_mod),
            ("INT", intelligence_mod),
            ("WIS", wisdom_mod),
            ("CHA", charisma_mod),
        ):
            print_fn(f"{label}:", value)
        print_fn()
        print_fn("SAVAŞ BİLGİLERİ")
        print_fn("---------------------------")
        print_fn("Level:", level)
        print_fn("HP:", current_hp, "/", max_hp)
        print_fn("AC:", armor_class)
        print_fn("Proficiency Bonus: +", proficiency_bonus)
        print_fn("===================================")

    return {
        "name": character_name,
        "race": character_race,
        "class": character_class,
        "level": level,
        "current_hp": current_hp,
        "max_hp": max_hp,
        "armor_class": armor_class,
        "modifiers": modifiers.copy(),
        "proficient_skills": list(proficient_skills),
    }


# =========================================================
# AI DUNGEON MASTER
# =========================================================

system_prompt = """
Sen Dungeons & Dragons oyununda yaratıcı Dungeon Master ve anlatıcısısın.
Python gerçek oyun motorudur; world state içindeki kayıtlar kalıcı olgulardır.

Python tek başına yönetir: karakter verisi, HP, hasar, inventory, eşya transferi,
konum, kapılar, zarlar, modifiers, proficiency, DC ve mekanik sonuçlar. Bunları
world_updates içinde asla değiştirmeye çalışma.

Oyuncunun yapmadığı bir hareketi, sözü, düşünceyi veya kararı oyuncu karakterine
ekleme. NPC'ler doğal biçimde konuşabilir, tepki verebilir ve kendi kayıtlı
kişiliklerine uygun davranabilir. Oyuncunun iddialarını doğrulanmış dünya gerçeği
sayma. NPC belleği yalnızca önceki turlarda gerçekten verilmiş NPC yanıtlarını içerir.
Oyuncunun bugünkü iddiası, önceki bir konuşmanın kanıtı değildir.

Kayıtlı NPC'lerin ID, ad, rol, kişilik, görünüş, geçmiş ve ilişkilerini tutarlı
kullan. Yeni NPC yalnızca izin verildiğinde ve sahneye anlamlı katkı sağlıyorsa
öner; kişi yığını oluşturma. Yeni NPC'yi narration'da kullanacaksan aynı yanıttaki
create_npcs içinde öner. Python kabul etmezse o kişiyi anlatımda kullanma.

Yeni kalıcı çevre ayrıntıları yalnızca izin verildiğinde create_features içinde öner.
Geçici atmosfer (rüzgâr, ışık, koku, ses, yağmur) world state'e kaydedilmeden
anlatılabilir. Kalıcı özellikleri yeniden kullan; aynı şeyi tekrar oluşturma. Eşya,
içecek ve yemek menüsü envantere dönüşmez. NPC belleğini Python yönetir.

NPC'nin bilmediği aile, geçmiş, sır veya dünya bilgilerini kesin gerçek diye
uydurma. Küçük ve sahneye uygun ayrıntılar yaratıcı olabilir; önemli kalıcı lore
world_updates içinde kaydedilmelidir. VERIFIED NPC MEMORY bölümündeki ilgili kayıt
yoksa oyuncunun 'bunu daha önce söylemiştin' iddiasını doğrulama; doğal biçimde
hatırlamadığını belirt. Konuşma önceki turlardan kopyalanmaz; gerekli bellek context'te.
NPC'ye kendi işi veya geçmişi hakkında sıradan bir soru sorulursa kısa ve tutarlı bir
kişisel yanıt verebilir; bu yanıt gerçekten söylenmiş kabul edilip Python belleğine alınır.

Her turda sadece mevcut eylem/mesaja yanıt ver. Kısa ve doğal Türkçe anlat.
Mekanik sonucu açıkça başarılı/başarısız anlat. Soru, seçenek listesi veya yeni
oyuncu eylemi üretme. Yanıtı tam olarak istenen JSON şemasında döndür; başka
anahtar, Markdown veya metin ekleme.
"""


messages = [
    {
        "role": "system",
        "content": system_prompt
    }
]


DEBUG_MODE = False


def _world_snapshot():
    world_state = _session().world_state
    _normalize_ground_items()
    return {
        "combat": json.dumps(world_state.get("combat", {}), sort_keys=True),
        "player_current_hp": _session().character["current_hp"],
        "player_max_hp": _session().character["max_hp"],
        "player_combat_status": world_state.get("player_combat_status"),
        "location": world_state.get("location"),
        "inventory": tuple(world_state.get("inventory", [])),
        "ground_items": tuple(world_state.get("ground_items", [])),
        "ground_items_by_location": {k: tuple(v) for k, v in world_state.get("ground_items_by_location", {}).items()},
        "doors": tuple(sorted(
            (door.get("name"), door.get("location"), door.get("open"), door.get("locked"), door.get("broken"))
            for door in world_state.get("doors", [])
        )),
        "player_hidden": world_state.get("flags", {}).get("player_hidden"),
        "pending_destination": world_state.get("flags", {}).get("pending_destination"),
        "locations": tuple(sorted(
            (location_id, location.get("name", ""), tuple(location.get("aliases", [])))
            for location_id, location in world_state.get("locations", {}).items()
        )),
        "npcs": tuple(json.dumps(npc, ensure_ascii=False, sort_keys=True) for npc in world_state.get("npcs", [])),
        "features": tuple(json.dumps(feature, ensure_ascii=False, sort_keys=True) for feature in world_state.get("features", [])),
        "events": tuple(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in world_state.get("events", [])),
    }


def _changed_state_fields(before):
    after = _world_snapshot()
    fields = {
        "combat": "world.combat",
        "player_current_hp": "player.current_hp",
        "player_max_hp": "player.max_hp",
        "player_combat_status": "player.combat_status",
        "location": "player.location",
        "inventory": "player.inventory",
        "ground_items": "ground_items",
        "ground_items_by_location": "ground_items",
        "doors": "doors",
        "player_hidden": "flags.player_hidden",
        "pending_destination": "flags.pending_destination",
        "locations": "world.locations",
        "npcs": "world.npcs",
        "features": "world.features",
        "events": "world.events",
    }
    return [fields[key] for key in fields if before.get(key) != after.get(key)]


def _skill_result_category(result):
    return {
        "KRİTİK BAŞARI": "critical_success",
        "BAŞARILI": "success",
        "KRİTİK BAŞARISIZLIK": "critical_failure",
        "BAŞARISIZ": "failure",
    }.get(result, "failure")


def _print_skill_result(result, difficulty):
    print()
    print("===================================")
    print("🎲 D&D SKILL CHECK")
    print("===================================")
    print("Skill:", result["skill"])
    print("Difficulty:", difficulty)
    print("DC:", result["dc"])
    print("D20:", result["dice"])
    print("Ability Modifier:", f"+{result['modifier']}" if result["modifier"] >= 0 else result["modifier"])
    print("Proficiency:", f"+{result['proficiency_bonus']}")
    print("Total Bonus:", f"+{result['total_bonus']}" if result["total_bonus"] >= 0 else result["total_bonus"])
    print("Total:", result["total"])
    print("Result:", result["result"])
    print("===================================")


def _commit_travel_action(action_result):
    """Resolve a proposed/known travel destination and commit only a registered ID."""
    world_state = _session().world_state
    target_reference = action_result.get("target_reference", "")
    target_id = resolve_location_reference(target_reference)
    if not target_id:
        world_state.setdefault("flags", {})["pending_destination"] = None
        action_result.update({"success": False, "status": "failed", "target": None})
        action_result["state_changes"] = ["flags.pending_destination"]
        return False
    action_result["target"] = target_id
    if action_result.get("completion") == "intended":
        world_state.setdefault("flags", {})["pending_destination"] = target_id
        action_result.update({"success": None, "status": "intended"})
        action_result["state_changes"] = ["flags.pending_destination"]
        return True
    combat_was_active = ensure_combat_state()["active"]
    changed = commit_location_change(target_id)
    if changed and combat_was_active:
        action_result.update(combat_ended=True, end_reason="location_changed", combat=_combat_snapshot())
    world_state.setdefault("flags", {})["pending_destination"] = None
    action_result.update({
        "success": True,
        "status": "completed",
        "previous_location": action_result.get("previous_location", "Henüz belirlenmedi"),
        "new_location": target_id,
    })
    changes = ["player.location"] if changed else []
    changes.append("flags.pending_destination")
    action_result["state_changes"] = changes
    return True


def execute_intent(intent, player_input, npc_target=None):
    """Central Python rule engine: validate intent effects and return a structured result."""
    world_state = _session().world_state
    intent = intent if isinstance(intent, dict) else {"intent": "unknown"}
    intent_type = intent.get("intent", "unknown")
    before = _world_snapshot()
    result = {
        "action": intent_type,
        "success": True,
        "status": "resolved",
        "state_changes": [],
    }

    combat_was_active = bool(ensure_combat_state()["active"])
    if intent_type in {"attack", "combat"} and (_session().character["current_hp"] <= 0 or world_state["player_combat_status"] == "unconscious"):
        result.update(action="attack", success=False, outcome="player_unconscious",
                      direct_response="Bilincin kapalı; saldırı yapamazsın.")
        return _finish_combat_result(result, before)

    character_reply = known_character_answer(player_input)
    if character_reply:
        result.update({"action": "character_query", "direct_response": character_reply})
        return result

    # Handle identity/location/presence queries
    query_type = _detect_query_type(player_input, npc_target) or intent.get("query_type")
    if query_type:
        query_response = _handle_query(player_input, query_type, npc_target)
        if query_response:
            result.update({"action": "query", "query_type": query_type, "direct_response": query_response})
            return result

    if intent_type == "travel":
        reference = intent.get("target", {}).get("reference", "")
        pending = world_state.get("flags", {}).get("pending_destination")
        if (not reference or reference in ("orada", "oraya", "içeri")) and pending:
            reference = pending
        if not reference:
            result.update({"success": False, "status": "clarification", "direct_response": "Hangi konuma gitmek istediğini belirt."})
            return result
        previous = world_state.get("location")
        target_id = resolve_location_reference(reference)
        result.update({
            "action": "travel",
            "completion": intent.get("completion", "completed"),
            "target_reference": str(reference),
            "target": target_id,
            "previous_location": previous,
            "success": None,
            "status": "awaiting_proposal" if not target_id else "ready",
        })
        flags = world_state.setdefault("flags", {})
        if not target_id:
            # A changed target invalidates any older pending destination.
            flags["pending_destination"] = None
            result["proposal_required"] = True
        elif result["completion"] == "intended":
            flags["pending_destination"] = target_id
            result.update({"status": "intended", "state_changes": ["flags.pending_destination"]})
        else:
            changed = commit_location_change(target_id)
            flags["pending_destination"] = None
            result.update({
                "success": True,
                "status": "completed",
                "new_location": target_id,
                "state_changes": (["player.location"] if changed else []) + ["flags.pending_destination"],
            })
        if combat_was_active and world_state.get("location") != previous:
            result.update(combat_ended=True, end_reason="location_changed", combat=_combat_snapshot())
            result["state_changes"] = _changed_state_fields(before)
        return result

    if intent_type == "observe":
        intent_type = "explore"
    explore_type = intent.get("explore_type", "observe") if intent_type == "explore" else None
    if intent_type == "explore":
        result.update({"action": "explore", "explore_type": explore_type, "status": "resolved", "success": True})

    if intent_type == "dialogue" and npc_target:
        result.update({"npc_id": npc_target.get("id"), "npc_name": npc_target.get("name")})

    deterministic = deterministic_check_for_action(player_input)
    skill = None
    difficulty = "medium"
    if deterministic and deterministic.get("action_type") == "check":
        skill = deterministic.get("skill")
    else:
        inferred_skill = {
            "stealth": "Stealth",
            "perception": "Perception",
            "investigation": "Investigation",
            "search": "Investigation",
        }.get(intent_type)
        if intent_type == "explore" and explore_type in {"inspect", "search"}:
            inferred_skill = "Investigation"
        if inferred_skill and (
            not is_npc_dialogue_input(player_input)
            or intent_type in {"perception", "investigation", "search", "stealth"}
        ):
            skill = inferred_skill
    if skill in SKILLS:
        dc = DIFFICULTY_DC.get(difficulty, DIFFICULTY_DC["medium"])
        check_result = perform_skill_check(skill, dc, _session().character["modifiers"],
                                           _session().character["proficient_skills"],
                                           _session().character["proficiency_bonus"])
        apply_check_outcome_to_world_state(player_input, check_result)
        outcome = _skill_result_category(check_result.get("result"))
        result.update({
            "action": "skill_check",
            "intent": intent_type,
            "skill": check_result["skill"],
            "ability": check_result["ability"],
            "dice": check_result["dice"],
            "modifier": check_result["modifier"],
            "proficiency_bonus": check_result["proficiency_bonus"],
            "total": check_result["total"],
            "dc": check_result["dc"],
            "outcome": outcome,
            "success": outcome in ("success", "critical_success"),
            "status": "resolved",
            "state_changes": _changed_state_fields(before),
            "target_type": "door" if ("kapı" in player_input.casefold() or "kilit" in player_input.casefold()) else None,
        })
        _print_skill_result(check_result, difficulty)
        return result

    if intent_type == "explore":
        return result

    python_reply = resolve_python_world_action(player_input)
    if python_reply:
        result.update({
            "action": "world_interaction",
            "status": "resolved",
            "direct_response": python_reply,
            "state_changes": _changed_state_fields(before),
        })
        return result

    inventory_reply = update_inventory_from_player(player_input)
    if inventory_reply:
        if "envanterden yere taşındı" in inventory_reply:
            reply = "Kılıç envanterinden çıkar ve yerde durur."
        elif "Yerdeki Kılıç envantere alındı" in inventory_reply:
            reply = "Yerdeki Kılıç yerden alınır ve yeniden envanterine eklenir."
        elif "Yerde alınabilecek" in inventory_reply:
            reply = "Yerde alabileceğin bir kılıç yok."
        else:
            reply = "Kılıç envanterinde değil; yerde duruyor."
        result.update({
            "action": "inventory",
            "status": "resolved",
            "direct_response": reply,
            "state_changes": _changed_state_fields(before),
        })
        return result

    fixed_reply = known_player_action_narration(player_input)
    if fixed_reply:
        result.update({"action": "narrative", "direct_response": fixed_reply, "state_changes": []})
        return result

    if intent_type in {"attack", "combat"}:
        combat = ensure_combat_state()
        result["action"] = "attack"
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        if not weapon_name:
            result.update(success=False, outcome="no_weapon",
                          direct_response="Envanterinde saldırmak için kullanabileceğin bir kılıç yok.")
            return _finish_combat_result(result, before)
        target_npc = resolve_combat_target(player_input, npc_target)
        if target_npc == "ambiguous":
            result.update(success=False, status="clarification", outcome="ambiguous_target",
                          direct_response="Hangi hedefe saldırıyorsun?")
            return _finish_combat_result(result, before)
        if not target_npc:
            result.update(success=False, outcome="no_target",
                          direct_response="Burada saldırabileceğin o hedef bulunmuyor.")
            return _finish_combat_result(result, before)
        if combat["active"] and target_npc["id"] != combat["target_id"]:
            result.update(success=False, outcome="target_mismatch",
                          direct_response="Önce mevcut rakibinle çatışmayı bitirmelisin.")
            return _finish_combat_result(result, before)
        ensure_npc_enemy_stats(target_npc)
        if target_npc["combat_status"] != "active" or target_npc["current_hp"] <= 0:
            result.update(success=False, outcome="invalid_target", target_id=target_npc["id"],
                          direct_response="Bu hedef savaşabilecek durumda değil.")
            if combat["active"]:
                end_combat("target_defeated")
                result.update(combat_ended=True, end_reason="target_defeated")
            return _finish_combat_result(result, before)
        started = not combat["active"]
        if started:
            start_combat(target_npc)
            # First attack: round is 1 (set by start_combat)
        # V2 contract: the initiating command attacks first regardless of initiative.
        result = resolve_attack(player_input, weapon_name, weapon_data, target_npc)
        result["combat_started"] = started
        
        if target_npc["combat_status"] != "active":
            end_combat("target_defeated")
            result.update(combat_ended=True, end_reason="target_defeated")
        else:
            canonical_target = next(npc for npc in world_state["npcs"] if npc["id"] == combat["target_id"])
            enemy_result = resolve_enemy_attack(canonical_target)
            result["enemy_action"] = enemy_result
            if _session().character["current_hp"] <= 0 or world_state["player_combat_status"] == "unconscious":
                end_combat("player_defeated")
                result.update(combat_ended=True, end_reason="player_defeated")
            else:
                # After enemy acts, a full exchange is complete -> advance round
                combat["round"] += 1
                # Reset turn index to player for next round
                combat["current_turn_index"] = combat["initiative_order"].index("player")
        return _finish_combat_result(result, before)

    elif intent_type in {"rest", "use_item"}:
        result.update({
            "success": False,
            "status": "unsupported",
            "direct_response": "Bu eylem için henüz bir Python kuralı tanımlı değil; dünya durumu değişmedi.",
            "state_changes": [],
        })
    else:
        result.update({"action": "dialogue" if intent_type == "dialogue" else intent_type, "state_changes": []})
    return result


def run_player_turn(player_input, messages=None):
    """Intent → rules → validated updates → committed state → narration."""
    world_state = _session().world_state
    if messages is None:
        messages = _session().messages
    flags = world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1

    npc_resolution = resolve_npc_reference(player_input)
    if npc_resolution["status"] == "ambiguous":
        result = {"action": "dialogue", "status": "clarification", "success": False, "state_changes": []}
        return {"action_result": result, "narration": npc_ambiguity_response(npc_resolution)}
    npc_target = npc_resolution.get("npc") if npc_resolution["status"] == "found" else None

    raw_intent = parse_player_intent(player_input)
    normalized_intent = normalize_intent(raw_intent, player_input)
    validated_intent = validate_intent(normalized_intent, player_input)
    if DEBUG_MODE:
        print("[INTENT]")
        print(json.dumps(validated_intent, ensure_ascii=False, indent=2))

    previous_location = world_state.get("location")
    action_result = execute_intent(validated_intent, player_input, npc_target)
    if DEBUG_MODE:
        print("[RULE ENGINE]")
        print(json.dumps({key: value for key, value in action_result.items() if key != "direct_response"}, ensure_ascii=False, indent=2))

    if action_result.get("direct_response"):
        narration = action_result["direct_response"]
        if npc_target and (action_result or {}).get("action") != "attack":
            record_npc_interaction(npc_target, narration, player_input, npc_target)
        return {"action_result": action_result, "narration": narration}

    proposed_entry = action_result.get("action") == "travel" and action_result.get("completion") == "completed"
    allow_new_locations = bool(action_result.get("proposal_required"))
    expected_location_change = proposed_entry or world_state.get("location") != previous_location
    allow_new_npcs = should_generate_npcs(player_input, expected_location_change) and not is_player_world_assertion(player_input)
    allow_new_features = should_generate_features(player_input, expected_location_change) and not is_player_world_assertion(player_input)
    packet = ask_dungeon_master(
        messages,
        player_input,
        allow_new_npcs=allow_new_npcs,
        allow_new_features=allow_new_features,
        npc_target=npc_target,
        world_entry=expected_location_change,
        action_result=action_result,
        allow_new_locations=allow_new_locations,
        return_details=True,
    )
    packet = packet if isinstance(packet, dict) else {"narration": None, "world_updates": {}, "valid_response": False}
    raw_updates = packet.get("world_updates", {})
    is_assertion = is_player_world_assertion(player_input)
    proposal_snapshot = _world_snapshot()

    # Location proposals are validated and committed before the player location changes.
    location_updates = validate_world_updates(
        raw_updates,
        allow_new_locations=allow_new_locations and not is_assertion,
    )
    if allow_new_locations and location_updates.get("create_locations"):
        expected = str(action_result.get("target_reference", "")).casefold().strip(" .,!?:;\"'")
        expected_words = re.findall(r"[a-z0-9çğıöşü]+", expected)
        matching = []
        for proposal in location_updates["create_locations"]:
            candidates = [proposal.get("name", ""), *proposal.get("aliases", [])]
            candidate_words = [re.findall(r"[a-z0-9çğıöşü]+", candidate.casefold()) for candidate in candidates]
            exact_or_contained = any(
                expected == " ".join(words)
                or bool(expected_words and any(
                    words[index:index + len(expected_words)] == expected_words
                    for index in range(max(0, len(words) - len(expected_words) + 1))
                ))
                for words in candidate_words
            )
            if exact_or_contained:
                original_name = proposal.get("name", "")
                if original_name.casefold() != expected:
                    aliases = list(proposal.get("aliases", []))
                    if original_name and original_name not in aliases:
                        aliases.append(original_name)
                    proposal["aliases"] = aliases[:8]
                    proposal["name"] = action_result.get("target_reference", original_name)
                matching.append(proposal)
        location_updates["create_locations"] = matching[:1]
    if location_updates.get("create_locations"):
        merge_world_updates({"create_locations": location_updates["create_locations"]})
    if action_result.get("action") == "travel" and action_result.get("status") == "awaiting_proposal":
        _commit_travel_action(action_result)

    # Validate NPC/feature/lore proposals only after any accepted location exists.
    validated_updates = validate_world_updates(
        raw_updates,
        allow_new_npcs=allow_new_npcs and not is_assertion,
        allow_new_features=allow_new_features and not is_assertion,
    )
    created_npcs = merge_world_updates(validated_updates) if not is_assertion else []
    if len(created_npcs) == 1:
        flags["last_npc_id"] = created_npcs[0].get("id")
        flags["active_npc_id"] = created_npcs[0].get("id")
        flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 6

    proposal_changes = _changed_state_fields(proposal_snapshot)
    action_result["state_changes"] = list(dict.fromkeys(action_result.get("state_changes", []) + proposal_changes))

    if DEBUG_MODE:
        print("[ACTION RESULT]")
        print(json.dumps(action_result, ensure_ascii=False, indent=2))
        print("[WORLD STATE CHANGE]")
        print(json.dumps(action_result.get("state_changes", []), ensure_ascii=False))

    narration = finalize_narration(packet.get("narration"), player_input, npc_target, action_result)
    return {"action_result": action_result, "narration": narration}


DEFAULT_SAVE_PATH = Path(__file__).resolve().parent / "saves" / "adventure.json"


def start_terminal_game(input_fn=input, print_fn=print, save_path=DEFAULT_SAVE_PATH):
    """Resume a default save, or start a new character when none is chosen."""
    save_path = Path(save_path).expanduser()
    if save_path.is_file():
        print_fn("Kayıtlı macera bulundu.")
        print_fn("1. Yeni karakter oluştur")
        print_fn("2. Kayıtlı maceraya devam et")
        while True:
            choice = input_fn("Seçimin: ").strip()
            if choice == "1":
                break
            if choice == "2":
                try:
                    load_game(save_path)
                except (OSError, ValueError, TypeError) as error:
                    print_fn(f"Kayıt yüklenemedi: {error}")
                    print_fn("Yeni karakter oluşturabilir veya oyundan çıkabilirsin.")
                    continue
                print_fn(f"Oyun yüklendi: {save_path}")
                return True
            if choice.casefold() in ("çık", "exit"):
                return False
            print_fn("Lütfen 1 veya 2 seç.")
    initialize_game(input_fn=input_fn, print_fn=print_fn)
    return True


# All mutable engine references above resolve through _session(). The wrapper
# below provides an explicit session= argument and propagates it to nested calls.
_ENGINE_FUNCTIONS = tuple(name for name, value in globals().items()
                          if isinstance(value, types.FunctionType)
                          and value.__module__ == __name__)
_CHARACTER_GLOBALS = {
    "character_name": "name", "character_race": "race",
    "character_class": "class",
    **{key: key for key in (
        "strength", "dexterity", "constitution", "intelligence", "wisdom",
        "charisma", "proficient_skills", "level", "proficiency_bonus",
        "max_hp", "current_hp", "armor_class", "strength_mod",
        "dexterity_mod", "constitution_mod", "intelligence_mod",
        "wisdom_mod", "charisma_mod", "modifiers",
    )},
}
_ACTIVE_SESSION = contextvars.ContextVar("ai_dnd_active_session", default=None)
_DEFAULT_SESSION = None
_ENGINE_NAMESPACE = globals()


class GameSession:
    """Independent player, world, narration history, conversation and dice."""

    def __init__(self, seed=None):
        self.character = {}
        self.world_state = copy.deepcopy(INITIAL_WORLD_STATE)
        self.recent_dm_narrations = []
        self.messages = [{"role": "system", "content": system_prompt}]
        self.rng = random.Random(seed)

    def __getattr__(self, name):
        helper = _ENGINE_NAMESPACE.get(name)
        if callable(helper) and getattr(helper, "_session_bound", False):
            return functools.partial(helper, session=self)
        raise AttributeError(name)


def _session():
    return _ACTIVE_SESSION.get() or _DEFAULT_SESSION


def _bind_session_engine():
    for name in _ENGINE_FUNCTIONS:
        implementation = _ENGINE_NAMESPACE[name]

        @functools.wraps(implementation)
        def bound(*args, __implementation=implementation, session=None, **kwargs):
            selected = session if session is not None else _session()
            if not isinstance(selected, GameSession):
                raise TypeError("session must be a GameSession")
            token = _ACTIVE_SESSION.set(selected)
            try:
                return __implementation(*args, **kwargs)
            finally:
                _ACTIVE_SESSION.reset(token)

        bound._session_bound = True
        _ENGINE_NAMESPACE[name] = bound


_DEFAULT_SESSION = GameSession()
_DEFAULT_SESSION.world_state = world_state
_DEFAULT_SESSION.recent_dm_narrations = recent_dm_narrations
_DEFAULT_SESSION.messages = messages
_bind_session_engine()
initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None)


def create_session(seed=None):
    """Create an initialized, independent adventure; seed controls its dice."""
    session = GameSession(seed=seed)
    initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None,
                    session=session)
    return session


if __name__ != "__main__":
    class _GameModule(types.ModuleType):
        def __getattribute__(self, name):
            if name in _CHARACTER_GLOBALS:
                return _DEFAULT_SESSION.character[_CHARACTER_GLOBALS[name]]
            return super().__getattribute__(name)

        def __setattr__(self, name, value):
            if name in _CHARACTER_GLOBALS:
                _DEFAULT_SESSION.character[_CHARACTER_GLOBALS[name]] = value
                return
            super().__setattr__(name, value)

    # Imported modules retain live character aliases. Plain exec dictionaries
    # must use create_session() and explicit session-owned state instead.
    if isinstance(sys.modules.get(__name__), types.ModuleType) and sys.modules[__name__].__dict__ is globals():
        sys.modules[__name__].__class__ = _GameModule


# =========================================================
# MACERA
# =========================================================

if __name__ == "__main__":
    if not start_terminal_game():
        raise SystemExit(0)
    print("\nMacera başlıyor...\n")


# =========================================================
# ANA OYUN DÖNGÜSÜ
# =========================================================

    while True:

        player_input = input("Sen: ").strip()


        # =====================================================
        # BOŞ INPUT
        # =====================================================

        if not player_input:

            continue


        command = player_input.lower()

        if command.split(maxsplit=1)[0] in ("/save", "/kaydet", "/load", "/yükle"):
            parts = player_input.split(maxsplit=1)
            save_path = parts[1] if len(parts) == 2 else DEFAULT_SAVE_PATH
            try:
                if parts[0].lower() in ("/save", "/kaydet"):
                    save_game(save_path)
                    print(f"Oyun kaydedildi: {save_path}")
                else:
                    load_game(save_path)
                    print(f"Oyun yüklendi: {save_path}")
            except (OSError, ValueError, TypeError) as error:
                print(f"Kayıt işlemi başarısız: {error}")
            continue


        # =====================================================
        # ÇIKIŞ
        # =====================================================

        if command == "çık" or command == "exit":

            print("\nOyun kapatılıyor...")

            break


        # =====================================================
        # NORMAL D20
        # =====================================================

        if command == "zar at":

            dice = roll_d20()

            print()
            print("🎲 D20 sonucu:", dice)
            print()

            continue


        # =====================================================
        # MANUEL SKILL
        # =====================================================

        if command.startswith("/skill"):

            parts = command.split()

            if len(parts) != 3:

                print()
                print("❌ Kullanım:")
                print("/skill stealth 15")
                print()

                continue


            skill_name_input = parts[1]


            try:

                dc = int(parts[2])

            except ValueError:

                print()
                print("❌ DC bir sayı olmalı.")
                print()

                continue


            matched_skill = None

            for skill in SKILLS:

                if skill.lower() == skill_name_input:

                    matched_skill = skill

                    break


            if matched_skill is None:

                print()
                print("❌ Geçersiz skill.")
                print()

                continue


            result = perform_skill_check(
                matched_skill,
                dc,
                modifiers,
                proficient_skills,
                proficiency_bonus
            )


            print()
            print("===================================")
            print("🎲 SKILL CHECK")
            print("===================================")

            print("Skill:", result["skill"])
            print("Ability:", result["ability"].upper())
            print("D20:", result["dice"])

            print(
                "Ability Modifier:",
                f"+{result['modifier']}"
                if result["modifier"] >= 0
                else result["modifier"]
            )

            print(
                "Proficiency:",
                f"+{result['proficiency_bonus']}"
            )

            print(
                "Proficient:",
                "EVET"
                if result["proficient"]
                else "HAYIR"
            )

            print(
                "Toplam Bonus:",
                f"+{result['total_bonus']}"
                if result["total_bonus"] >= 0
                else result["total_bonus"]
            )

            print("Toplam:", result["total"])
            print("DC:", result["dc"])
            print("Sonuç:", result["result"])

            print("===================================")
            print()

            continue


        # =====================================================
        turn_result = run_player_turn(player_input, messages)
        print()
        print("Dungeon Master:")
        print(turn_result["narration"])
        print()
