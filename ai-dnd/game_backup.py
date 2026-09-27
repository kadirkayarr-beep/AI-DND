import ollama
import random
import json
import re


# =========================================================
# ZAR SİSTEMİ
# =========================================================

def roll_d20():
    return random.randint(1, 20)


def get_modifier(stat):
    return (stat - 10) // 2


def roll_stat():
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

def analyze_player_action(
    player_input,
    character_class,
    proficient_skills
):

    analyzer_prompt = f"""
Sen bir Dungeons & Dragons oyun mekanik analizcisisin.

Karakter sınıfı:
{character_class}

Proficient skilller:
{proficient_skills}

Kullanılabilir skilller:
{list(SKILLS.keys())}


OYUNCUNUN EYLEMİ:

"{player_input}"


ÖNEMLİ KURAL:

Her oyuncu eylemi skill check gerektirmez.

Oyuncu sadece normal bir hareket yapıyorsa
"narrative" döndür.

Örnekler:

"İçeri giriyorum"
=> narrative

"Kapıya gidiyorum"
=> narrative

"Masaya oturuyorum"
=> narrative

"Etrafıma bakıyorum"
=> narrative


Ancak eylem sonucu belirsiz ve başarısız olma ihtimali varsa
skill check kullan.

Örnekler:

"Kapıya sessizce yaklaşıyorum"
=> Stealth

"Kilidi açmaya çalışıyorum"
=> Sleight of Hand

"Kapıyı zorlayarak açıyorum"
=> Athletics

"İnsanları korkutmaya çalışıyorum"
=> Intimidation

"Çevreyi dikkatlice araştırıyorum"
=> Investigation veya Perception


SKILL SEÇİMİ:

Stealth = sessiz hareket, gizlenme, fark edilmemeye çalışma

Sleight of Hand = el çabukluğu, küçük mekanizmalar, yankesicilik, hassas el işi

Athletics = fiziksel güç, itme, çekme, kırma, tırmanma

Acrobatics = denge, çeviklik, takla, dar alanlarda hareket

Perception = duyularla bir şeyi fark etme

Investigation = bir şeyi sistematik şekilde araştırma

Intimidation = korkutma, tehdit

Persuasion = ikna etme

Deception = yalan söyleme, kandırma

Insight = birinin niyetini veya davranışını anlama

Animal Handling = hayvanlarla etkileşim

Survival = doğada iz sürme veya hayatta kalma

Arcana = büyü ve büyülü bilgi

History = tarihsel bilgi

Nature = doğal dünya bilgisi

Religion = dini veya kutsal bilgi

Medicine = tıbbi bilgi

Performance = gösteri veya sanat


ZORLUK:

easy = DC 10
medium = DC 15
hard = DC 20
very_hard = DC 25
extreme = DC 30


CEVAP FORMATI:

Eğer check gerekmiyorsa:

{{"action_type":"narrative"}}

Eğer check gerekiyorsa:

{{"action_type":"check","skill":"Stealth","difficulty":"medium"}}


SADECE JSON DÖNDÜR.

Açıklama yazma.
Markdown yazma.
Zar atma.
Zar sonucu verme.
Modifier hesaplama.
DC sayısı verme.
"""


    try:

        response = ollama.chat(
            model="qwen3:8b",
            messages=[
                {
                    "role": "system",
                    "content": analyzer_prompt
                }
            ]
        )

        content = response["message"]["content"].strip()

        # Qwen bazen düşünme etiketleri üretebilir
        content = re.sub(
            r"<think>.*?</think>",
            "",
            content,
            flags=re.DOTALL
        )

        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

        match = re.search(
            r"\{.*\}",
            content,
            re.DOTALL
        )

        if not match:

            return {
                "action_type": "narrative"
            }

        data = json.loads(match.group())

        if data.get("action_type") == "narrative":

            return {
                "action_type": "narrative"
            }

        if data.get("action_type") == "check":

            skill = data.get("skill")
            difficulty = data.get("difficulty")

            valid_skill = None

            for available_skill in SKILLS:

                if available_skill.lower() == str(skill).lower():

                    valid_skill = available_skill

                    break

            if valid_skill is None:

                return {
                    "action_type": "narrative"
                }

            if difficulty not in DIFFICULTY_DC:

                difficulty = "medium"

            return {
                "action_type": "check",
                "skill": valid_skill,
                "difficulty": difficulty
            }

    except Exception:

        return {
            "action_type": "narrative"
        }

    return {
        "action_type": "narrative"
    }


# =========================================================
# AI DUNGEON MASTER CEVABI
# =========================================================

def ask_dungeon_master(
    messages,
    player_input
):

    messages.append({
        "role": "user",
        "content": player_input
    })

    response = ollama.chat(
        model="qwen3:8b",
        messages=messages
    )

    dm_response = response["message"]["content"].strip()

    messages.append({
        "role": "assistant",
        "content": dm_response
    })

    return dm_response


# =========================================================
# OYUN BAŞLANGICI
# =========================================================

print("===================================")
print("       AI DUNGEON MASTER")
print("===================================")

print("Oyuna hoş geldin.\n")

print("=== KARAKTER OLUŞTURMA ===\n")

character_name = input("Karakterinin adı: ")


# =========================================================
# IRK
# =========================================================

character_race = choose_option(
    "=== IRK SEÇ ===",
    RACES
)


# =========================================================
# SINIF
# =========================================================

character_class = choose_option(
    "=== SINIF SEÇ ===",
    CLASSES
)


# =========================================================
# STATLAR
# =========================================================

(
    strength,
    dexterity,
    constitution,
    intelligence,
    wisdom,
    charisma
) = assign_stats()


# =========================================================
# MODIFIERLAR
# =========================================================

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
    "charisma": charisma_mod
}


# =========================================================
# SKILL PROFICIENCIES
# =========================================================

proficient_skills = choose_skill_proficiencies(
    character_class
)


# =========================================================
# LEVEL
# =========================================================

level = 1


# =========================================================
# PROFICIENCY BONUS
# =========================================================

proficiency_bonus = 2


# =========================================================
# HP
# =========================================================

max_hp = calculate_hp(
    character_class,
    constitution_mod
)

current_hp = max_hp


# =========================================================
# AC
# =========================================================

armor_class = calculate_ac(
    character_class,
    dexterity_mod,
    constitution_mod,
    wisdom_mod
)


# =========================================================
# KARAKTER KARTI
# =========================================================

print()
print("===================================")
print("       KARAKTERİN OLUŞTURULDU")
print("===================================")

print("İsim:", character_name)
print("Irk:", character_race)
print("Sınıf:", character_class)

print()
print("LEVEL:", level)
print("HP:", current_hp, "/", max_hp)
print("AC:", armor_class)
print("Proficiency Bonus: +", proficiency_bonus)


print()
print("IRK ÖZELLİKLERİ")
print("---------------------------")

for feature in RACE_FEATURES[character_race]:

    print("-", feature)


print()
print("SINIF ÖZELLİKLERİ")
print("---------------------------")

for feature in CLASS_FEATURES[character_class]:

    print("-", feature)


print()
print("SKILL PROFICIENCIES")
print("---------------------------")

for skill in proficient_skills:

    ability = SKILLS[skill]

    print(
        "-",
        skill,
        "(" + ability.upper() + ")"
    )


print()
print("STATLAR")
print("---------------------------")

print("STR:", strength)
print("DEX:", dexterity)
print("CON:", constitution)
print("INT:", intelligence)
print("WIS:", wisdom)
print("CHA:", charisma)


print()
print("MODIFIERLAR")
print("---------------------------")

print("STR:", strength_mod)
print("DEX:", dexterity_mod)
print("CON:", constitution_mod)
print("INT:", intelligence_mod)
print("WIS:", wisdom_mod)
print("CHA:", charisma_mod)


print()
print("SAVAŞ BİLGİLERİ")
print("---------------------------")

print("Level:", level)
print("HP:", current_hp, "/", max_hp)
print("AC:", armor_class)
print("Proficiency Bonus: +", proficiency_bonus)

print("===================================")


# =========================================================
# AI DUNGEON MASTER
# =========================================================

system_prompt = f"""
Sen bir Dungeons & Dragons Dungeon Masterısın.

Karakter:

İsim: {character_name}
Irk: {character_race}
Sınıf: {character_class}
Level: {level}

HP: {current_hp}/{max_hp}
AC: {armor_class}
Proficiency Bonus: +{proficiency_bonus}

Irk özellikleri:
{RACE_FEATURES[character_race]}

Sınıf özellikleri:
{CLASS_FEATURES[character_class]}

Proficiency skillleri:
{proficient_skills}

STATLAR:

STR: {strength}
DEX: {dexterity}
CON: {constitution}
INT: {intelligence}
WIS: {wisdom}
CHA: {charisma}

MODIFIERLAR:

STR: {strength_mod}
DEX: {dexterity_mod}
CON: {constitution_mod}
INT: {intelligence_mod}
WIS: {wisdom_mod}
CHA: {charisma_mod}


=========================
DUNGEON MASTER
=========================

Dünyayı, NPC'leri, yaratıkları ve olayları yönet.

Oyuncunun karakterini oyuncunun yerine oynama.

Oyuncunun söylediği eylemi gerçekleştirmesine izin ver.

Oyuncunun özgürce karar vermesine izin ver.

NPC'leri karakter gibi canlandır.

Atmosferik ve doğal cevaplar ver.

Her zaman Türkçe konuş.


=========================
ÇOK ÖNEMLİ
=========================

Oyuncuya asla numaralı seçenekler verme.

Asla:

1.
2.
3.

şeklinde seçenek listesi oluşturma.

"Hangisini seçersin?" şeklinde seçenek menüsü oluşturma.

Oyuncunun önüne alternatif eylemler sıralama.

Oyuncunun ne yapacağına oyuncu karar verir.

Sadece dünyanın ve NPC'lerin tepkisini anlat.


=========================
MEKANİKLER
=========================

Python gerçek zarları atar.

Python gerçek modifierları hesaplar.

Python proficiency hesaplar.

Python DC belirler.

Python tarafından verilen mekanik sonucu değiştirme.

Kendi başına zar atma.

Kendi başına DC oluşturma.

Kendi başına modifier oluşturma.

Kendi başına başarı yüzdesi oluşturma.

Python'dan gelen başarılı veya başarısız sonucunu hikâyeye doğal şekilde yansıt.


=========================
ANLATIM
=========================

Kısa ama atmosferik cevaplar ver.

Aynı olayı tekrar tekrar anlatma.

Oyuncunun yapmadığı eylemleri karaktere yaptırma.

Oyuncunun yerine karar verme.

Oyuncu bir kapıya gidiyorsa kapıya gitmiştir.

Oyuncu içeri giriyorsa içeri girmiştir.

Oyuncu bir şeyi incelemek isterse inceleme sürecini anlat.

Oyuncu açıkça bir şey yapmadıysa karaktere ekstra eylem yaptırma.
"""


messages = [
    {
        "role": "system",
        "content": system_prompt
    }
]


# =========================================================
# MACERA
# =========================================================

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
    # AI EYLEM ANALİZİ
    # =====================================================

    action_analysis = analyze_player_action(
        player_input,
        character_class,
        proficient_skills
    )


    # =====================================================
    # CHECK GEREKİYOR
    # =====================================================

    if action_analysis["action_type"] == "check":

        skill = action_analysis["skill"]

        difficulty = action_analysis["difficulty"]

        dc = DIFFICULTY_DC[difficulty]


        result = perform_skill_check(
            skill,
            dc,
            modifiers,
            proficient_skills,
            proficiency_bonus
        )


        print()
        print("===================================")
        print("🎲 D&D SKILL CHECK")
        print("===================================")

        print("Skill:", result["skill"])
        print("Difficulty:", difficulty)
        print("DC:", result["dc"])
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
            "Total Bonus:",
            f"+{result['total_bonus']}"
            if result["total_bonus"] >= 0
            else result["total_bonus"]
        )

        print("Total:", result["total"])
        print("Result:", result["result"])

        print("===================================")


        # -------------------------------------------------
        # MEKANİK SONUCU DM'YE GÖNDER
        # -------------------------------------------------

        mechanical_result = f"""
OYUNCUNUN EYLEMİ:

{player_input}

PYTHON MEKANİK SONUCU:

Skill: {result["skill"]}
Ability: {result["ability"]}
D20: {result["dice"]}
Ability Modifier: {result["modifier"]}
Proficiency Bonus: {result["proficiency_bonus"]}
Total Bonus: {result["total_bonus"]}
Total: {result["total"]}
DC: {result["dc"]}
Result: {result["result"]}

Bu mekanik sonucu değiştirme.

Oyuncunun eyleminin sonucunu kısa ve atmosferik şekilde anlat.

Zarı tekrar atma.

Yeni DC oluşturma.

Oyuncuya seçenek listesi sunma.

Oyuncunun yerine başka bir eylem yapma.
"""


        dm_response = ask_dungeon_master(
            messages,
            mechanical_result
        )


        print()
        print("Dungeon Master:")
        print(dm_response)
        print()

        continue


    # =====================================================
    # NORMAL HİKÂYE
    # =====================================================

    dm_response = ask_dungeon_master(
        messages,
        player_input
    )


    print()
    print("Dungeon Master:")
    print(dm_response)
    print()