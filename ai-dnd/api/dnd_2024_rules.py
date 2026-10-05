"""Authoritative D&D 2024 Level 1 character creation rules and options.

Implements rules from the D&D 5e Player's Handbook (2024) and setting options:
- 12 Classes with hit dice, saving throws, skill options, spellcasting, features
- 16 Backgrounds with ability score boosts (+2/+1 or +1/+1/+1), skills, tools, origin feats
- 10 D&D 2024 PHB species plus retained 2014 Half-Elf and Half-Orc options
- 3 Ability Score generation methods: Standard Array, Point Buy (27 pts), Rolled (4d6 drop lowest)
- Starting Equipment packages
- Spellcasting setup (cantrips & 1st-level spells)
- Full derivation: ability modifiers, HP, AC, proficiency bonus, saving throws, skill modifiers
"""

from __future__ import annotations

import copy
import random
from typing import Any


class CharacterCreationError(ValueError):
    """Raised when character choices violate D&D 2024 rules."""


# ============================================================================
# ABILITIES
# ============================================================================

ABILITY_KEYS = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")

ABILITY_NAMES = {
    "strength": {"name": "Kuvvet", "short": "KUV", "abbr": "STR"},
    "dexterity": {"name": "Çeviklik", "short": "ÇEV", "abbr": "DEX"},
    "constitution": {"name": "Dayanıklılık", "short": "DAY", "abbr": "CON"},
    "intelligence": {"name": "Zeka", "short": "ZEK", "abbr": "INT"},
    "wisdom": {"name": "Bilgelik", "short": "BİL", "abbr": "WIS"},
    "charisma": {"name": "Karizma", "short": "KAR", "abbr": "CHA"},
}

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

POINT_BUY_BUDGET = 27

POINT_BUY_COSTS = {
    8: 0,
    9: 1,
    10: 2,
    11: 3,
    12: 4,
    13: 5,
    14: 7,
    15: 9,
}


def get_modifier(score: int) -> int:
    return (score - 10) // 2


# ============================================================================
# SKILLS
# ============================================================================

SKILL_DEFINITIONS = {
    "Acrobatics": {"ability": "dexterity", "name_tr": "Akrobasi"},
    "Animal Handling": {"ability": "wisdom", "name_tr": "Hayvan Terbiyesi"},
    "Arcana": {"ability": "intelligence", "name_tr": "Arkana (Büyü Bilgisi)"},
    "Athletics": {"ability": "strength", "name_tr": "Atletizm"},
    "Deception": {"ability": "charisma", "name_tr": "Kandırma"},
    "History": {"ability": "intelligence", "name_tr": "Tarih"},
    "Insight": {"ability": "wisdom", "name_tr": "İçgörü"},
    "Intimidation": {"ability": "charisma", "name_tr": "Gözdağı"},
    "Investigation": {"ability": "intelligence", "name_tr": "Soruşturma"},
    "Medicine": {"ability": "wisdom", "name_tr": "Tıp (İlk Yardım)"},
    "Nature": {"ability": "intelligence", "name_tr": "Doğa"},
    "Perception": {"ability": "wisdom", "name_tr": "Algı"},
    "Performance": {"ability": "charisma", "name_tr": "Gösteri"},
    "Persuasion": {"ability": "charisma", "name_tr": "İkna"},
    "Religion": {"ability": "intelligence", "name_tr": "Din"},
    "Sleight of Hand": {"ability": "dexterity", "name_tr": "El Çabukluğu"},
    "Stealth": {"ability": "dexterity", "name_tr": "Gizlilik"},
    "Survival": {"ability": "wisdom", "name_tr": "Hayatta Kalma"},
}


# ============================================================================
# ALIGNMENTS
# ============================================================================

ALIGNMENTS = [
    {"id": "Lawful Good", "name_tr": "Hukuki İyi", "desc": "Doğru olanı kurallara ve onura bağlı kalarak yapar."},
    {"id": "Neutral Good", "name_tr": "Tarafsız İyi", "desc": "Kurallardan bağımsız olarak başkalarına yardım etmeyi seçer."},
    {"id": "Chaotic Good", "name_tr": "Kaotik İyi", "desc": "Kendi vicdanını ve özgürlüğü her şeyin üstünde tutarak iyilik yapar."},
    {"id": "Lawful Neutral", "name_tr": "Hukuki Tarafsız", "desc": "Yasalara, geleneklere ve kişisel kurallara sadık kalır."},
    {"id": "True Neutral", "name_tr": "Tam Tarafsız", "desc": "Dengeyi savunur, uç kararlardan kaçınır."},
    {"id": "Chaotic Neutral", "name_tr": "Kaotik Tarafsız", "desc": "Kendi heveslerini ve kişisel özgürlüğünü takip eder."},
    {"id": "Lawful Evil", "name_tr": "Hukuki Kötü", "desc": "Sistemleri ve kuralları kendi çıkarları için acımasızca kullanır."},
    {"id": "Neutral Evil", "name_tr": "Tarafsız Kötü", "desc": "Kendi çıkarları için sınır tanımaksızın kötülük yapar."},
    {"id": "Chaotic Evil", "name_tr": "Kaotik Kötü", "desc": "Yıkım, şiddet ve kaostan beslenir."},
    {"id": "Unaligned", "name_tr": "Hizalanmamış", "desc": "Ahlaki bir felsefesi olmayan, hayatta kalmaya odaklanan tutum."},
]


# ============================================================================
# LANGUAGES (2024 PHB Chapter 2, Page 37)
# ============================================================================

STANDARD_LANGUAGES = (
    "Common",
    "Common Sign Language",
    "Draconic",
    "Dwarvish",
    "Elvish",
    "Giant",
    "Gnomish",
    "Goblin",
    "Halfling",
    "Orc",
)

RARE_LANGUAGES = (
    "Abyssal",
    "Celestial",
    "Deep Speech",
    "Druidic",
    "Infernal",
    "Primordial",
    "Sylvan",
    "Thieves' Cant",
    "Undercommon",
)


# ============================================================================
# ORIGIN FEATS (2024 PHB)
# ============================================================================

ORIGIN_FEATS = {
    "Alert": {
        "name_tr": "Uyanık (Alert)",
        "desc": "İnisiyatif zarlarına ustalık bonusu (+2) eklenir. Tur başında istekli bir müttefikle inisiyatif sırası takas edilebilir.",
    },
    "Crafter": {
        "name_tr": "Zanaatkâr (Crafter)",
        "desc": "Büyü dışı eşyaları %20 indirimle alır ve hızlı eşya üretebilir.",
    },
    "Healer": {
        "name_tr": "Şifacı (Healer)",
        "desc": "Şifa verirken atılan zarlardaki 1'ler yeniden atılabilir. Şifacı çantasıyla can yenileyebilir.",
    },
    "Lucky": {
        "name_tr": "Şanslı (Lucky)",
        "desc": "Ustalık bonusun kadar (2) Şans Puanı kazandırır. Kendi zarlarına avantaj ekleyebilir veya rakibin zarını zorlaştırabilir.",
    },
    "Magic Initiate": {
        "name_tr": "Büyüye Giriş (Magic Initiate)",
        "desc": "Seçilen sınıftan 2 cantrip ve 1 adet 1. seviye büyü öğrenilir. 1. seviye büyü günde bir kez ücretsiz kullanılır.",
    },
    "Musician": {
        "name_tr": "Müzisyen (Musician)",
        "desc": "Kısa veya Uzun Dinlenmeden sonra müttefiklere Kahramanca İlham (Heroic Inspiration) verir.",
    },
    "Savage Attacker": {
        "name_tr": "Vahşi Saldırgan (Savage Attacker)",
        "desc": "Turda bir kez silah hasarı zarı iki kez atılıp yüksek olanı seçilebilir.",
    },
    "Skilled": {
        "name_tr": "Yetenekli (Skilled)",
        "desc": "İstenen 3 beceri veya alet uzmanlığı kazandırır.",
    },
    "Tavern Brawler": {
        "name_tr": "Meyhane Dövüşçüsü (Tavern Brawler)",
        "desc": "Silahsız vuruşlar 1d4 + KUV hasar verir, hasar zarlarındaki 1'ler yeniden atılır ve hedef 5 fit itilebilir.",
    },
    "Tough": {
        "name_tr": "Dayanıklı (Tough)",
        "desc": "Maksimum can puanı seviye başına 2 artar (1. seviyede +2 Can).",
        "hp_bonus": 2,
    },
}


def canonical_origin_feat_name(feat: str | None) -> str:
    """Return the base feat name, ignoring a specialization in parentheses."""
    return feat.split(" (", 1)[0].strip() if isinstance(feat, str) else ""


# ============================================================================
# BACKGROUNDS (2024 PHB)
# ============================================================================

ARTISAN_TOOLS = (
    "Alchemist's Supplies", "Brewer's Supplies", "Calligrapher's Supplies",
    "Carpenter's Tools", "Cartographer's Tools", "Cobbler's Tools",
    "Cook's Utensils", "Glassblower's Tools", "Jeweler's Tools",
    "Leatherworker's Tools", "Mason's Tools", "Painter's Supplies",
    "Potter's Tools", "Smith's Tools", "Tinker's Tools", "Weaver's Tools",
    "Woodcarver's Tools",
)

BACKGROUND_DEFINITIONS = {
    "Acolyte": {
        "name_tr": "Kutsal Hizmetkâr (Acolyte)",
        "desc": "Bir tapınakta dine ve kutsal geleneklere hizmet ederek yetiştin.",
        "abilities": ["wisdom", "intelligence", "charisma"],
        "skills": ["Insight", "Religion"],
        "tool": "Calligrapher's Supplies",
        "feat": "Magic Initiate",
        "equipment": ["Calligrapher's Supplies", "Dua Kitabı", "Kutsal Sembol", "10 Parşömen", "Cübbe", "8 GP"],
        "starting_gp": 8,
    },
    "Artisan": {
        "name_tr": "Zanaatkâr (Artisan)",
        "desc": "Bir loncada ustalıkla alet kullanmayı ve değerli eşyalar üretmeyi öğrendin.",
        "abilities": ["strength", "dexterity", "intelligence"],
        "skills": ["Investigation", "Persuasion"],
        "tool": "Smith's Tools",
        "feat": "Crafter",
        "equipment": ["Artisan's Tools", "2 Kese", "Traveler's Clothes", "32 GP"],
        "tool_options": list(ARTISAN_TOOLS),
        "starting_gp": 32,
    },
    "Charlatan": {
        "name_tr": "Şarlatan (Charlatan)",
        "desc": "İnsanların zaaflarını okuyup onları kandırarak hayatta kaldın.",
        "abilities": ["dexterity", "constitution", "charisma"],
        "skills": ["Deception", "Sleight of Hand"],
        "tool": "Forgery Kit",
        "feat": "Skilled",
        "equipment": ["Sahte Mühür Seti", "Gösterişli Giysi", "İşaretli Zarlar", "15 Altın"],
    },
    "Criminal": {
        "name_tr": "Suçlu (Criminal)",
        "desc": "Şehrin gölgelerinde, kanunların bittiği sokaklarda yetiştin.",
        "abilities": ["dexterity", "constitution", "intelligence"],
        "skills": ["Sleight of Hand", "Stealth"],
        "tool": "Thieves' Tools",
        "feat": "Alert",
        "equipment": ["Hırsız Aletleri", "Koyu Renkli Pelerin", "Levye", "16 Altın"],
    },
    "Entertainer": {
        "name_tr": "Gösterici (Entertainer)",
        "desc": "Tavernaları ve meydanları şarkılarınla, hikâyelerinle büyüledin.",
        "abilities": ["strength", "dexterity", "charisma"],
        "skills": ["Acrobatics", "Performance"],
        "tool": "Musical Instrument (Lute)",
        "feat": "Musician",
        "equipment": ["Lavta (Müzik Aleti)", "Gösteri Kostümü", "Ayna", "16 Altın"],
    },
    "Farmer": {
        "name_tr": "Çiftçi (Farmer)",
        "desc": "Toprağın bereketini, sabrı ve doğanın sert döngüsünü yakından bilirsin.",
        "abilities": ["strength", "constitution", "wisdom"],
        "skills": ["Animal Handling", "Nature"],
        "tool": "Carpenter's Tools",
        "feat": "Tough",
        "equipment": ["Marangoz Aletleri", "Sağlam İş Giysisi", "Demir Orak", "25 Altın"],
    },
    "Guard": {
        "name_tr": "Muhafız (Guard)",
        "desc": "Şehir surlarında ve kapılarda nöbet tutarak düzeni korudun.",
        "abilities": ["strength", "intelligence", "wisdom"],
        "skills": ["Athletics", "Perception"],
        "tool": "Gaming Set (Dice)",
        "feat": "Alert",
        "equipment": ["Şehir Muhafızı Nişanı", "Fener", "Deri Zırh", "Demir Kelepçe", "12 Altın"],
    },
    "Guide": {
        "name_tr": "Rehber (Guide)",
        "desc": "Yabanıl arazide yolunu kaybetmeden yolculara rehberlik ettin.",
        "abilities": ["dexterity", "constitution", "wisdom"],
        "skills": ["Stealth", "Survival"],
        "tool": "Cartographer's Tools",
        "feat": "Magic Initiate",
        "equipment": ["Haritacı Seti", "Yolcu Pusulası", "Sıcak Tutacak Pelerin", "İp (15 metre)", "10 Altın"],
    },
    "Hermit": {
        "name_tr": "Münzevi (Hermit)",
        "desc": "Medeniyetten uzakta, doğanın ve kendi zihninin derinliklerinde tek başına yaşadın.",
        "abilities": ["constitution", "wisdom", "charisma"],
        "skills": ["Medicine", "Religion"],
        "tool": "Herbalism Kit",
        "feat": "Healer",
        "equipment": ["Şifalı Bitkiler Çantası", "Kaba Yün Battaniye", "Kutsal Notlar", "15 Altın"],
    },
    "Merchant": {
        "name_tr": "Tüccar (Merchant)",
        "desc": "Pazarlarda mal alıp satarak ticaret yollarında ömür tükettin.",
        "abilities": ["constitution", "intelligence", "charisma"],
        "skills": ["Animal Handling", "Persuasion"],
        "tool": "Navigator's Tools",
        "feat": "Lucky",
        "equipment": ["Pusula ve Rota Haritası", "Kalem ve Defter", "Tüccar Kesesi", "30 Altın"],
    },
    "Noble": {
        "name_tr": "Soylu (Noble)",
        "desc": "Ayrıcalıklı bir ailede, saray adabı ve güç oyunları içinde büyüdün.",
        "abilities": ["strength", "intelligence", "charisma"],
        "skills": ["History", "Persuasion"],
        "tool": "Gaming Set (Dragonchess)",
        "feat": "Skilled",
        "equipment": ["İpek Giysiler", "Mühür Yüzüğü", "Soy Kütüğü Belgesi", "25 Altın"],
    },
    "Sage": {
        "name_tr": "Bilge (Sage)",
        "desc": "Yıllarını kütüphanelerde tozlu parşömenler ve kadim sırlar arasında geçirdin.",
        "abilities": ["constitution", "intelligence", "wisdom"],
        "skills": ["Arcana", "History"],
        "tool": "Calligrapher's Supplies",
        "feat": "Magic Initiate",
        "equipment": ["Hattat Takımı", "Parşömen ve Mürekkep", "Kadim Bir Teori Kitabı", "10 Altın"],
    },
    "Sailor": {
        "name_tr": "Denizci (Sailor)",
        "desc": "Açık denizlerin fırtınalarıyla ve güvertedeki sert yaşamla yoğruldun.",
        "abilities": ["strength", "dexterity", "wisdom"],
        "skills": ["Acrobatics", "Perception"],
        "tool": "Navigator's Tools",
        "feat": "Tavern Brawler",
        "equipment": ["Denizci Pusulası", "İpek Halat (15 metre)", "Uğurlu Deniz Kabuğu", "15 Altın"],
    },
    "Scribe": {
        "name_tr": "Katip (Scribe)",
        "desc": "Büyük loncaların ve kütüphanelerin resmi kayıtlarını tuttun.",
        "abilities": ["dexterity", "intelligence", "wisdom"],
        "skills": ["Investigation", "Perception"],
        "tool": "Calligrapher's Supplies",
        "feat": "Skilled",
        "equipment": ["Hattat Aletleri", "Kayıt Defteri", "Mumlu Damga Seti", "20 Altın"],
    },
    "Soldier": {
        "name_tr": "Asker (Soldier)",
        "desc": "Düzenli bir ordunun sancağı altında disiplin ve savaş eğitimi aldın.",
        "abilities": ["strength", "dexterity", "constitution"],
        "skills": ["Athletics", "Intimidation"],
        "tool": "Gaming Set (Dice)",
        "feat": "Savage Attacker",
        "equipment": ["Birlik Sancağı Parçası", "Zar Seti", "Askeri Pelerin", "14 Altın"],
    },
    "Wayfarer": {
        "name_tr": "Gezgin (Wayfarer)",
        "desc": "Kök salmadan bir diyardan diğerine yürüyen, sokakları ev bilen bir yolcusun.",
        "abilities": ["dexterity", "wisdom", "charisma"],
        "skills": ["Insight", "Stealth"],
        "tool": "Thieves' Tools",
        "feat": "Lucky",
        "equipment": ["Hırsız Aletleri", "Yıpranmış Yolcu Pelerini", "Yol Haritası", "16 Altın"],
    },
}


# ============================================================================
# SPECIES (2024 PHB, with retained 2014 SRD legacy options)
# ============================================================================

SPECIES_DEFINITIONS = {
    "Aasimar": {
        "name_tr": "Göksoylu (Aasimar)",
        "desc": "Ruhunda Yukarı Düzlemlerden bir kıvılcım taşıyan ölümlüler; göksel mirasları ışık, şifa ve kudret olarak belirir.",
        "size": "Medium or Small",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 186",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Göksel Direnç (Celestial Resistance)", "desc": "Necrotic ve radiant hasara karşı direncin vardır."},
            {"name": "Karanlık Görüşü (Darkvision)", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Şifa Veren Eller (Healing Hands)", "desc": "Büyü eylemiyle dokunduğun bir yaratığa Ustalık Bonusun kadar d4 toplamı kadar can kazandırırsın; uzun dinlenmede yenilenir."},
            {"name": "Işık Taşıyıcısı (Light Bearer)", "desc": "Karizmanı kullanarak Light cantrip'ini bilirsin."},
            {"name": "Göksel Tecelli (Celestial Revelation)", "desc": "3. seviyede bir dakikalığına Kanatlı Gökyüzü, İç Işıma veya Nekrotik Örtü biçimlerinden birini seçersin; tur başına bir kez fazladan hasar ve seçilen biçime özgü etki sağlar, uzun dinlenmede yenilenir."},
        ],
    },
    "Human": {
        "name_tr": "İnsan (Human)",
        "desc": "Hırslı, uyumlu ve son derece becerikli. Faerûn'un en yaygın türü.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 0,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 194",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "skill_bonus_count": 1,
        "origin_feat_bonus_count": 1,
        "traits": [
            {"name": "Becerikli (Skillful)", "desc": "Seçtiğin fazladan bir beceride ustalık kazanırsın."},
            {"name": "Çok Yönlü (Versatile)", "desc": "Fazladan 1 adet 1. seviye Başlangıç Hüneri (Origin Feat) kazanırsın."},
            {"name": "Azimli (Resourceful)", "desc": "Uzun dinlenmeyi her tamamladığında Kahramanca İlham kazanırsın."},
        ],
    },
    "Elf": {
        "name_tr": "Elf",
        "desc": "Zarif, uzun ömürlü ve fey kökenli kadim bir halk.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), pp. 189–190",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Karanlık Görüşü (Darkvision)", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Elf Soyu (Elven Lineage)", "desc": "Drow, High Elf veya Wood Elf soyunu seçersin; bu seçim başlangıç büyülerini, 3. ve 5. seviyede öğrendiğin büyüleri etkiler."},
            {"name": "Fey Soyu (Fey Ancestry)", "desc": "Charmed durumunu önlemek veya sona erdirmek için yaptığın kurtarma zarlarında avantajın vardır."},
            {"name": "Keskin Duyular (Keen Senses)", "desc": "Insight, Perception veya Survival becerilerinden birinde uzmanlık kazanırsın."},
            {"name": "Trans (Trance)", "desc": "Uykuya ihtiyaç duymazsın; 4 saatlik bilinçli transla uzun dinlenmeyi tamamlayabilirsin."},
        ],
    },
    "Dwarf": {
        "name_tr": "Cüce (Dwarf)",
        "desc": "Dağların bağrında taş ve maden ustası, sarsılmaz derecede dirençli savaşçılar.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 120,
        "hp_bonus": 1,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), pp. 188–189",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Üstün Karanlık Görüşü", "desc": "120 fit mesafeye kadar zifiri karanlıkta görebilirsin."},
            {"name": "Cüce Dayanıklılığı (Resilience)", "desc": "Zehir hasarına karşı direnç ve zehirlenmeye karşı kurtarma zarlarında avantaj."},
            {"name": "Cüce Sağlamlığı (Toughness)", "desc": "Maksimum can puanın seviye başına 1 artar."},
            {"name": "Taş Hissi (Stonecunning)", "desc": "Taşa temas ederken Bonus Eylemle 10 dakika 60 fit Tremorsense kazanırsın; kullanımların Ustalık Bonusuna eşittir ve uzun dinlenmede yenilenir."},
        ],
    },
    "Halfling": {
        "name_tr": "Buçukluk (Halfling)",
        "desc": "Küçük cüsseli, neşeli, barışçıl ama inanılmaz derecede şanslı ve cesur bir halk.",
        "size": "Small",
        "speed": 30,
        "darkvision": 0,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 193",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Şans (Luck)", "desc": "Bir d20 Testinde d20'de 1 attığında zarı yeniden atıp yeni sonucu kullanabilirsin."},
            {"name": "Cesur (Brave)", "desc": "Frightened durumunu önlemek veya sona erdirmek için yaptığın kurtarma zarlarında avantajın vardır."},
            {"name": "Buçukluk Çevikliği (Halfling Nimbleness)", "desc": "Senden büyük yaratıkların alanından geçebilirsin; onların alanında sona eremezsin."},
            {"name": "Doğal Gizlilik (Naturally Stealthy)", "desc": "Senden en az bir beden büyük bir yaratık seni örterken Hide eylemini kullanabilirsin."},
        ],
    },
    "Gnome": {
        "name_tr": "Gnóm (Gnome)",
        "desc": "Meraklı, zeki ve büyüye doğal yatkınlığı olan mucit ve gözlemciler.",
        "size": "Small",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 191",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Karanlık Görüşü", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Gnom Kurnazlığı (Gnomish Cunning)", "desc": "Intelligence, Wisdom ve Charisma kurtarma zarlarında avantajın vardır."},
            {"name": "Gnom Soyu (Gnomish Lineage)", "desc": "Forest Gnome veya Rock Gnome soyunu seçerek ek doğaüstü yetenekler kazanırsın."},
        ],
    },
    "Tiefling": {
        "name_tr": "Tiefling",
        "desc": "Damarlarında cehennemi miras taşıyan, boynuzlu ve gizemli bir halk.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), pp. 196–197",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Karanlık Görüşü", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Şeytani Miras (Fiendish Legacy)", "desc": "Abyssal, Chthonic veya Infernal mirasını seçersin; direnç, cantrip ve 1., 3. ve 5. seviyelerde büyüler sağlar."},
            {"name": "Öteki Dünyadan Varlık (Otherworldly Presence)", "desc": "Thaumaturgy cantrip'ini seçtiğin büyü yeteneğiyle bilirsin."},
        ],
    },
    "Dragonborn": {
        "name_tr": "Ejderhasoyu (Dragonborn)",
        "desc": "Ejderhaların asil gücünü, pullarını ve nefesini taşıyan kudretli savaşçılar.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 187",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Ejderha Soyu (Draconic Ancestry)", "desc": "Ejderha atana göre nefes silahının hasar türünü ve hasar direncini seçersin."},
            {"name": "Nefes Silahı (Breath Weapon)", "desc": "Bir saldırı yerine 15 fit koni veya 30×5 fit hat boyunca 1d10 hasar verirsin; hasar 5., 11. ve 17. seviyelerde artar. Kullanımların Ustalık Bonusuna eşittir."},
            {"name": "Karanlık Görüşü", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Ejderha Uçuşu (Draconic Flight)", "desc": "5. seviyede bir uzun dinlenmede bir kez, 10 dakika boyunca hızına eşit Uçuş Hızı kazanırsın."},
        ],
    },
    "Half-Elf": {
        "name_tr": "Yarı-Elf (Half-Elf)",
        "desc": "İnsan ve elf miraslarını bir arada taşıyan, 2014 kurallarındaki beceri çok yönlülüğü korunmuş eski bir seçenek.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2014 legacy",
        "source_label_tr": "D&D 2014 · Eski seçenek",
        "source_citation": "Wizards of the Coast, Systems Reference Document 5.1 (2016), Half-Elf Traits",
        "source_url": "https://media.wizards.com/2016/downloads/DND/SRD-OGL_V5.1.pdf",
        "skill_bonus_count": 2,
        "traits": [
            {"name": "Karanlık Görüşü (Darkvision)", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Fey Ataları (Fey Ancestry)", "desc": "Charmed durumuna karşı kurtarma zarlarında avantajın vardır; büyü seni uyutamaz."},
            {"name": "Beceri Çok Yönlülüğü (Skill Versatility)", "desc": "Seçtiğin iki beceride uzmanlık kazanırsın."},
            {"name": "Diller (Languages)", "desc": "Common ve Elvish'in yanı sıra seçtiğin bir dili bilirsin."},
        ],
    },
    "Half-Orc": {
        "name_tr": "Yarı-Ork (Half-Orc)",
        "desc": "İnsan ve ork soylarını birleştiren; 2014 kurallarındaki dayanıklılığı, tehditkâr duruşu ve kritik vuruş gücü korunmuş eski bir seçenek.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 60,
        "rules_version": "2014 legacy",
        "source_label_tr": "D&D 2014 · Eski seçenek",
        "source_citation": "Wizards of the Coast, Systems Reference Document 5.1 (2016), Half-Orc Traits",
        "source_url": "https://media.wizards.com/2016/downloads/DND/SRD-OGL_V5.1.pdf",
        "traits": [
            {"name": "Karanlık Görüşü (Darkvision)", "desc": "60 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Tehditkâr (Menacing)", "desc": "Intimidation becerisinde uzmanlık kazanırsın."},
            {"name": "Yılmayan Direnç (Relentless Endurance)", "desc": "Uzun dinlenmede bir kez, 0 can puanına düşüp anında ölmediğinde 1 can puanıyla ayakta kalırsın."},
            {"name": "Vahşi Saldırılar (Savage Attacks)", "desc": "Yakın dövüş silahı saldırısıyla kritik vuruşta silahın hasar zarlarından birini bir kez daha atıp sonuca eklersin."},
        ],
    },
    "Goliath": {
        "name_tr": "Devsoylu (Goliath)",
        "desc": "İlk devlerin uzak torunları; dev atalarının izleri doğaüstü armağanlarda ve geçici olarak büyüyebilme yetilerinde görülür.",
        "size": "Medium",
        "speed": 35,
        "darkvision": 0,
        "giant_ancestry_options": [
            {"id": "cloud", "name_tr": "Bulut Devi", "desc": "Bonus eylemle 30 fit ışınlan."},
            {"id": "fire", "name_tr": "Ateş Devi", "desc": "İsabetten sonra ek ateş hasarı ver."},
            {"id": "frost", "name_tr": "Ayaz Devi", "desc": "İsabetten sonra soğuk hasarı ver ve hedefi yavaşlat."},
            {"id": "hill", "name_tr": "Tepe Devi", "desc": "İsabetten sonra hedefi yere düşürmeye çalış."},
            {"id": "stone", "name_tr": "Taş Devi", "desc": "Hasar aldığında hasarı azalt."},
            {"id": "storm", "name_tr": "Fırtına Devi", "desc": "İsabetten sonra gök gürültüsü hasarı ver ve hedefi it."},
        ],
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 192",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Dev Atası (Giant Ancestry)", "desc": "Bulut, ateş, ayaz, tepe, taş veya fırtına devi kökenli bir armağan seçersin; Ustalık Bonusun kadar kullanıp uzun dinlenmede yenilersin."},
            {"name": "Büyük Biçim (Large Form)", "desc": "5. seviyede bir uzun dinlenmede bir kez, 10 dakika Büyük boyuta geçersin; Kuvvet kontrollerinde avantaj ve +10 fit hız kazanırsın."},
            {"name": "Güçlü Yapı (Powerful Build)", "desc": "Grappled durumunu sona erdirmek için yaptığın kurtarma zarlarında avantajın vardır; taşıma kapasitesinde bir beden büyük sayılırsın."},
        ],
    },
    "Orc": {
        "name_tr": "Ork (Orc)",
        "desc": "Gruumsh'un armağanlarını taşıyan; dayanıklılık, kararlılık ve karanlıkta görme yetileriyle uzun yolculuklara çıkan bir halk.",
        "size": "Medium",
        "speed": 30,
        "darkvision": 120,
        "rules_version": "2024 PHB",
        "source_label_tr": "D&D 2024 PHB",
        "source_citation": "Player's Handbook (2024), p. 195",
        "source_url": "https://www.dndbeyond.com/sources/dnd/phb-2024",
        "traits": [
            {"name": "Adrenalin Patlaması (Adrenaline Rush)", "desc": "Bonus Eylemle Dash yapıp Ustalık Bonusun kadar geçici can kazanırsın; kullanımların Ustalık Bonusuna eşittir ve kısa veya uzun dinlenmede yenilenir."},
            {"name": "Karanlık Görüşü (Darkvision)", "desc": "120 fit mesafeye kadar karanlıkta görebilirsin."},
            {"name": "Yılmayan Direnç (Relentless Endurance)", "desc": "Uzun dinlenmede bir kez, 0 can puanına düşüp anında ölmediğinde 1 can puanıyla ayakta kalırsın."},
        ],
    },
}


# ============================================================================
# CLASSES (2024 PHB)
# ============================================================================

CLASS_DEFINITIONS = {
    "Barbarian": {
        "name_tr": "Barbar (Barbarian)",
        "desc": "Savaş alanında durdurulamaz bir öfkeyle dövüşen vahşi savaşçı.",
        "hit_die": 12,
        "primary_ability": "strength",
        "saving_throws": ["strength", "constitution"],
        "skill_count": 2,
        "skill_options": ["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"],
        "armor_proficiencies": ["Light", "Medium", "Shields"],
        "weapon_proficiencies": ["Simple", "Martial"],
        "features": ["Öfke (Rage)", "Zırsız Savunma (Unarmored Defense)", "Silah Ustalığı (Weapon Mastery)"],
        "is_spellcaster": False,
        "equipment_packages": [
            {"id": "A", "label": "Büyük Balta & Ciritler", "items": ["Büyük Balta (Greataxe)", "4 Cirit", "Macera Çantası", "15 Altın"]},
            {"id": "B", "label": "Çift El Baltası & Ciritler", "items": ["2 El Baltası (Handaxe)", "4 Cirit", "Macera Çantası", "15 Altın"]},
        ],
    },
    "Bard": {
        "name_tr": "Ozan (Bard)",
        "desc": "Müzik, sözler ve fey büyüsüyle müttefiklerine ilham veren çok yönlü sanatçı.",
        "hit_die": 8,
        "primary_ability": "charisma",
        "saving_throws": ["dexterity", "charisma"],
        "skill_count": 3,
        "skill_options": list(SKILL_DEFINITIONS.keys()),
        "expertise_progression": [{"level": 2, "choices": 2}, {"level": 9, "choices": 2}],
        "armor_proficiencies": ["Light"],
        "weapon_proficiencies": ["Simple"],
        "features": ["Ozan İlhamı (Bardic Inspiration d6)", "Büyücülük (Spellcasting)"],
        "is_spellcaster": True,
        "spellcasting_ability": "charisma",
        "cantrips_count": 2,
        "spells_count": 4,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Meç & Lavta", "items": ["Meç (Rapier)", "Deri Zırh", "Lavta (Lute)", "Diplomat Çantası", "18 Altın"]},
            {"id": "B", "label": "Hançer & Kısa Yay", "items": ["Hançer", "Kısa Yay & 20 Ok", "Deri Zırh", "Flüt", "Gösteri Çantası", "18 Altın"]},
        ],
    },
    "Cleric": {
        "name_tr": "Ruhban (Cleric)",
        "desc": "Tanrısının kutsal gücünü kuşanıp şifa veren ve adalet dağıtan ilahi elçi.",
        "hit_die": 8,
        "primary_ability": "wisdom",
        "saving_throws": ["wisdom", "charisma"],
        "skill_count": 2,
        "skill_options": ["History", "Insight", "Medicine", "Persuasion", "Religion"],
        "armor_proficiencies": ["Light", "Medium", "Shields"],
        "weapon_proficiencies": ["Simple"],
        "features": ["İlahi Düzen (Divine Order)", "İlahi Büyücülük (Spellcasting)"],
        "is_spellcaster": True,
        "spellcasting_ability": "wisdom",
        "cantrips_count": 3,
        "spells_count": 2,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Gürz & Pul Zırh & Kalkan", "items": ["Gürz (Mace)", "Pul Zırh", "Kalkan", "Kutsal Sembol", "Rahip Çantası", "15 Altın"]},
            {"id": "B", "label": "Savaş Çekici & Deri Zırh", "items": ["Savaş Çekici", "Deri Zırh", "Kalkan", "Kutsal Sembol", "Macera Çantası", "15 Altın"]},
        ],
    },
    "Druid": {
        "name_tr": "Druid",
        "desc": "Doğanın dengesini koruyan ve vahşi elementleri yönlendiren orman büyücüsü.",
        "hit_die": 8,
        "primary_ability": "wisdom",
        "saving_throws": ["intelligence", "wisdom"],
        "skill_count": 2,
        "skill_options": ["Arcana", "Animal Handling", "Insight", "Medicine", "Nature", "Perception", "Religion", "Survival"],
        "armor_proficiencies": ["Light", "Shields"],
        "weapon_proficiencies": ["Simple"],
        "features": ["Kadim Düzen (Primal Order)", "Doğa Büyücülüğü (Spellcasting)"],
        "is_spellcaster": True,
        "spellcasting_ability": "wisdom",
        "cantrips_count": 2,
        "spells_count": 2,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Pala & Ahşap Kalkan", "items": ["Pala (Scimitar)", "Deri Zırh", "Ahşap Kalkan", "Druid Odak Dalı", "Macera Çantası", "9 Altın"]},
            {"id": "B", "label": "Çeyrek Asa & Şifalı Bitkiler", "items": ["Çeyrek Asa", "Deri Zırh", "Şifalı Bitkiler Çantası", "Macera Çantası", "9 Altın"]},
        ],
    },
    "Fighter": {
        "name_tr": "Savaşçı (Fighter)",
        "desc": "Tüm silahlarda ve zırhlarda uzmanlaşmış, disiplinli dövüş ustası.",
        "hit_die": 10,
        "primary_ability": "strength",
        "saving_throws": ["strength", "constitution"],
        "skill_count": 2,
        "skill_options": ["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Perception", "Survival"],
        "armor_proficiencies": ["Light", "Medium", "Heavy", "Shields"],
        "weapon_proficiencies": ["Simple", "Martial"],
        "features": ["Dövüş Stili (Fighting Style)", "İkinci Nefes (Second Wind)", "Silah Ustalığı (Weapon Mastery)"],
        "is_spellcaster": False,
        "fighting_styles": [
            {"id": "Archery", "name_tr": "Okçuluk (+2 Menzilli Saldırı Bonusu)"},
            {"id": "Defense", "name_tr": "Savunma (+1 Zırh Sınıfı Bonusu)"},
            {"id": "Dueling", "name_tr": "Düello (Tek Elle Silah Kullanırken +2 Hasar)"},
            {"id": "Great Weapon Fighting", "name_tr": "Büyük Silah Dövüşü (İki Elle Silah Zarlarında 1 ve 2'leri Yenile)"},
            {"id": "Protection", "name_tr": "Koruma (Yanındaki Müttefike Yapılan Saldırıyı Zorlaştır)"},
            {"id": "Two-Weapon Fighting", "name_tr": "Çift Silah Dövüşü (Bonus Eylem Saldırısına Yetenek Bonusunu Ekle)"},
        ],
        "equipment_packages": [
            {"id": "A", "label": "Zincir Zırh & Uzun Kılıç & Kalkan", "items": ["Zincir Zırh", "Uzun Kılıç", "Kalkan", "Zindan Çantası", "10 Altın"]},
            {"id": "B", "label": "Deri Zırh & Uzun Yay & Çift Kısa Kılıç", "items": ["Deri Zırh", "Uzun Yay & 20 Ok", "2 Kısa Kılıç", "Zindan Çantası", "10 Altın"]},
            {"id": "C", "label": "İki Elli Kılıç & Ağır Kundaklı Yay", "items": ["Büyük Kılıç (Greatsword)", "Ağır Tatar Yayı & 20 Ok", "Macera Çantası", "10 Altın"]},
        ],
    },
    "Monk": {
        "name_tr": "Keşiş (Monk)",
        "desc": "Bedenini ve zihnini kusursuz bir silaha dönüştürmüş silahsız dövüş ustası.",
        "hit_die": 8,
        "primary_ability": "dexterity",
        "saving_throws": ["strength", "dexterity"],
        "skill_count": 2,
        "skill_options": ["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["Simple", "Martial (Light)"],
        "features": ["Dövüş Sanatları (Martial Arts d6)", "Zırsız Savunma (Unarmored Defense)"],
        "is_spellcaster": False,
        "equipment_packages": [
            {"id": "A", "label": "Mızrak & Hançerler", "items": ["Mızrak (Spear)", "5 Hançer", "Zindan Çantası", "11 Altın"]},
            {"id": "B", "label": "Çeyrek Asa & Dartlar", "items": ["Çeyrek Asa", "10 Dart", "Macera Çantası", "11 Altın"]},
        ],
    },
    "Paladin": {
        "name_tr": "Şövalye (Paladin)",
        "desc": "Kutsal bir yemine bağlı kalarak adaleti ve ışığı savunan ilahi zırhlı şövalye.",
        "hit_die": 10,
        "primary_ability": "strength",
        "saving_throws": ["wisdom", "charisma"],
        "skill_count": 2,
        "skill_options": ["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"],
        "armor_proficiencies": ["Light", "Medium", "Heavy", "Shields"],
        "weapon_proficiencies": ["Simple", "Martial"],
        "features": ["Şifa Eli (Lay on Hands - 5 Can)", "Kutsal Büyücülük (Spellcasting)", "Silah Ustalığı"],
        "is_spellcaster": True,
        "spellcasting_ability": "charisma",
        "cantrips_count": 0,
        "spells_count": 2,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Zincir Zırh & Uzun Kılıç & Kalkan", "items": ["Zincir Zırh", "Uzun Kılıç", "Kalkan", "Kutsal Sembol", "Rahip Çantası", "9 Altın"]},
            {"id": "B", "label": "Pul Zırh & Büyük Kılıç", "items": ["Pul Zırh", "Büyük Kılıç", "5 Cirit", "Kutsal Sembol", "Macera Çantası", "9 Altın"]},
        ],
    },
    "Ranger": {
        "name_tr": "Kolcu (Ranger)",
        "desc": "Yabanıl toprakların iz sürücüsü ve menzilli dövüş uzmanı.",
        "hit_die": 10,
        "primary_ability": "dexterity",
        "saving_throws": ["strength", "dexterity"],
        "skill_count": 3,
        "skill_options": ["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth", "Survival"],
        "armor_proficiencies": ["Light", "Medium", "Shields"],
        "weapon_proficiencies": ["Simple", "Martial"],
        "features": ["Avcı İşareti (Hunter's Mark)", "Doğa Büyücülüğü (Spellcasting)", "Silah Ustalığı"],
        "is_spellcaster": True,
        "spellcasting_ability": "wisdom",
        "cantrips_count": 0,
        "spells_count": 2,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Pul Zırh & Uzun Yay & Çift Kısa Kılıç", "items": ["Pul Zırh", "2 Kısa Kılıç", "Uzun Yay & 20 Ok", "Sadak", "Zindan Çantası", "10 Altın"]},
            {"id": "B", "label": "Deri Zırh & Çift Pala & Kısa Yay", "items": ["Deri Zırh", "2 Pala (Scimitar)", "Kısa Yay & 20 Ok", "Macera Çantası", "10 Altın"]},
        ],
    },
    "Rogue": {
        "name_tr": "Hırsız (Rogue)",
        "desc": "Gölgelerden vuran, tuzakları çözen ve ölümcül zayıflıkları bulan kurnaz uzman.",
        "hit_die": 8,
        "primary_ability": "dexterity",
        "saving_throws": ["dexterity", "intelligence"],
        "skill_count": 4,
        "skill_options": ["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception", "Performance", "Persuasion", "Sleight of Hand", "Stealth"],
        "expertise_progression": [{"level": 1, "choices": 2}, {"level": 6, "choices": 2}],
        "armor_proficiencies": ["Light"],
        "weapon_proficiencies": ["Simple", "Martial (Finesse/Light)"],
        "features": ["Gizli Saldırı (Sneak Attack +1d6)", "Uzmanlık (Expertise)", "Hırsız Dili (Thieves' Cant)", "Silah Ustalığı"],
        "is_spellcaster": False,
        "equipment_packages": [
            {"id": "A", "label": "Deri Zırh & Kısa Kılıç & Hırsız Aletleri", "items": ["Deri Zırh", "Kısa Kılıç", "2 Hançer", "Hırsız Aletleri", "Hırsız Çantası", "8 Altın"]},
            {"id": "B", "label": "Deri Zırh & Kısa Yay & Hırsız Aletleri", "items": ["Deri Zırh", "Kısa Yay & 20 Ok", "2 Hançer", "Hırsız Aletleri", "Zindan Çantası", "8 Altın"]},
        ],
    },
    "Sorcerer": {
        "name_tr": "Büyücü (Sorcerer)",
        "desc": "Büyüyü öğrenmeyen, kanında doğuştan bir ejderha veya kaos kıvılcımıyla taşıyan büyücü.",
        "hit_die": 6,
        "primary_ability": "charisma",
        "saving_throws": ["constitution", "charisma"],
        "skill_count": 2,
        "skill_options": ["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["Simple"],
        "features": ["Doğuştan Büyü (Innate Sorcery)", "Büyücülük (Spellcasting)"],
        "is_spellcaster": True,
        "spellcasting_ability": "charisma",
        "cantrips_count": 4,
        "spells_count": 2,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Kristal Odak & 2 Hançer", "items": ["2 Hançer", "Kristal Büyü Odağı", "Zindan Çantası", "28 Altın"]},
            {"id": "B", "label": "Hafif Kundaklı Yay & 2 Hançer", "items": ["Hafif Tatar Yayı & 20 Ok", "2 Hançer", "Macera Çantası", "28 Altın"]},
        ],
    },
    "Warlock": {
        "name_tr": "Gözcü / Cadı (Warlock)",
        "desc": "Kadim bir varlıkla (İblis, Peri veya Ulu Varlık) karanlık bir anlaşma yaparak güç kazanan büyücü.",
        "hit_die": 8,
        "primary_ability": "charisma",
        "saving_throws": ["wisdom", "charisma"],
        "skill_count": 2,
        "skill_options": ["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"],
        "armor_proficiencies": ["Light"],
        "weapon_proficiencies": ["Simple"],
        "features": ["Pakt Büyüsü (Pact Magic)", "Gizemli Yakarış (Eldritch Invocation)"],
        "is_spellcaster": True,
        "spellcasting_ability": "charisma",
        "cantrips_count": 2,
        "spells_count": 2,
        "spell_slots": {"1": 1},
        "equipment_packages": [
            {"id": "A", "label": "Deri Zırh & Büyü Değneği & Hançer", "items": ["Deri Zırh", "Asa Odak", "2 Hançer", "Gölgeler Kitabı", "Bilgin Çantası", "15 Altın"]},
            {"id": "B", "label": "Deri Zırh & Çeyrek Asa & Hafif Yay", "items": ["Deri Zırh", "Çeyrek Asa", "Hafif Tatar Yayı & 20 Ok", "Zindan Çantası", "15 Altın"]},
        ],
    },
    "Wizard": {
        "name_tr": "Büyücü / İlimci (Wizard)",
        "desc": "Evrenin dokusunu formüllerle çözen, büyü kitabına bağımlı kadim ilim üstadı.",
        "hit_die": 6,
        "primary_ability": "intelligence",
        "saving_throws": ["intelligence", "wisdom"],
        "skill_count": 2,
        "skill_options": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["Simple"],
        "features": ["Büyü Kitabı (Spellbook)", "Gizemli İyileşme (Arcane Recovery)", "Ritüel Büyücülüğü"],
        "is_spellcaster": True,
        "spellcasting_ability": "intelligence",
        "cantrips_count": 3,
        "spells_count": 6,
        "spell_slots": {"1": 2},
        "equipment_packages": [
            {"id": "A", "label": "Çeyrek Asa & Büyü Kitabı & Küre", "items": ["Çeyrek Asa", "Büyü Odak Taşı (Küre)", "Büyü Kitabı (Spellbook)", "Bilgin Çantası", "10 Altın"]},
            {"id": "B", "label": "Hançer & Değnek & Büyü Kitabı", "items": ["Hançer", "Büyü Değneği", "Büyü Kitabı (Spellbook)", "Macera Çantası", "10 Altın"]},
        ],
    },
}


# ============================================================================
# SPELLS CATALOG (Level 1 & Cantrips)
# ============================================================================

SPELLS_CATALOG = {
    "Wizard": {
        "cantrips": [
            {"id": "Fire Bolt", "name_tr": "Ateş Oku (Fire Bolt)", "desc": "120 fit menzile 1d10 ateş hasarı fırlatır."},
            {"id": "Ray of Frost", "name_tr": "Buz Işını (Ray of Frost)", "desc": "60 fit menzile 1d8 soğuk hasarı verir ve hedefi 10 fit yavaşlatır."},
            {"id": "Mage Hand", "name_tr": "Büyücü Eli (Mage Hand)", "desc": "30 fit menzilde 10 pounda kadar nesneleri taşıyan hayalet el oluşturur."},
            {"id": "Light", "name_tr": "Işık (Light)", "desc": "Dokunulan bir nesneye 20 fit parlak, 20 fit loş ışık saçtırır."},
            {"id": "Prestidigitation", "name_tr": "Hokkabazlık (Prestidigitation)", "desc": "Işık, koku, tat veya temizlik gibi küçük büyü hileleri yapar."},
            {"id": "Shocking Grasp", "name_tr": "Şok Dokunuşu (Shocking Grasp)", "desc": "Yakın dövüşte 1d8 yıldırım hasarı verir ve hedefin tepkisini engeller."},
            {"id": "Minor Illusion", "name_tr": "Küçük Yanılsama (Minor Illusion)", "desc": "Görsel veya işitsel yanılsama yaratır."},
        ],
        "spells_level_1": [
            {"id": "Magic Missile", "name_tr": "Sihirli Füze (Magic Missile)", "desc": "Iskalamayan üç büyü oku fırlatır (her biri 1d4 + 1 güç hasarı)."},
            {"id": "Shield", "name_tr": "Kalkan (Shield)", "desc": "Tepki olarak zırh sınıfına +5 ekler ve Sihirli Füzeyi engeller."},
            {"id": "Mage Armor", "name_tr": "Büyücü Zırhı (Mage Armor)", "desc": "Zırsız hedefin Zırh Sınıfını 13 + ÇEV mod yapar."},
            {"id": "Detect Magic", "name_tr": "Büyü Algılama (Detect Magic)", "desc": "30 fit içindeki büyü etkilerini ve okullarını hisseder."},
            {"id": "Sleep", "name_tr": "Uyku (Sleep)", "desc": "Hedefleri büyülü uykuya daldırır."},
            {"id": "Burning Hands", "name_tr": "Alevli Eller (Burning Hands)", "desc": "15 fitlik koniye 3d6 ateş hasarı saçar."},
            {"id": "Thunderwave", "name_tr": "Gök Gürültüsü Dalgası", "desc": "15 fit alandaki hedefleri 10 fit iter ve 2d8 ses hasarı verir."},
            {"id": "Feather Fall", "name_tr": "Kuş Tüyü Düşüşü", "desc": "Düşen yaratıkların düşüşünü yavaşlatıp hasarı sıfırlar."},
            {"id": "Identify", "name_tr": "Eşya Teşhisi (Identify)", "desc": "Büyülü bir nesnenin özelliklerini öğrenir."},
            {"id": "Charm Person", "name_tr": "Büyüleme (Charm Person)", "desc": "Bir insansı yaratığı dostane davranmaya zorlar."},
        ],
    },
    "Cleric": {
        "cantrips": [
            {"id": "Sacred Flame", "name_tr": "Kutsal Alev (Sacred Flame)", "desc": "Işıltılı alevle hedefe 1d8 radyant hasarı verir."},
            {"id": "Guidance", "name_tr": "Rehberlik (Guidance)", "desc": "Bir yetenek zarına +1d4 ekler."},
            {"id": "Thaumaturgy", "name_tr": "Mucize Gösterisi (Thaumaturgy)", "desc": "Kapıları açma, göz parlatma, ses yükseltme gibi doğaüstü işaretler."},
            {"id": "Toll the Dead", "name_tr": "Ölüm Çanı (Toll the Dead)", "desc": "Hedefe 1d8 veya yaralıysa 1d12 nekrotik hasar verir."},
            {"id": "Spare the Dying", "name_tr": "Can Kurtaran Dokunuş", "desc": "0 Candaki ölmekte olan bir yaratığı hemen stabilize eder."},
            {"id": "Light", "name_tr": "Işık (Light)", "desc": "Dokunulan bir nesneyi fener gibi parlatır."},
        ],
        "spells_level_1": [
            {"id": "Cure Wounds", "name_tr": "Yara İyileştirme (Cure Wounds)", "desc": "Dokunulan hedefe 2d8 + BİL mod kadar can yeniler (2024 güçlendirmesi)."},
            {"id": "Healing Word", "name_tr": "Şifa Sözü (Healing Word)", "desc": "Bonus eylemle 60 fitteki hedefe 2d4 + BİL mod can yeniler."},
            {"id": "Bless", "name_tr": "Kutsama (Bless)", "desc": "Üç müttefike saldırı ve kurtarma zarlarında +1d4 ekler."},
            {"id": "Guiding Bolt", "name_tr": "Yol Gösteren Işın", "desc": "4d6 radyant hasarı verir ve bir sonraki saldırıya avantaj sağlar."},
            {"id": "Sanctuary", "name_tr": "Sığınak (Sanctuary)", "desc": "Düşmanları hedefe saldırmadan önce kurtarma zarı atmaya zorlar."},
            {"id": "Bane", "name_tr": "Lanet (Bane)", "desc": "Üç düşmanın saldırı ve kurtarma zarlarından 1d4 çıkarır."},
            {"id": "Command", "name_tr": "Emir (Command)", "desc": "Hedefe tek kelimelik ('Yaklaş', 'Düş', 'Kaç') emri uygulatır."},
        ],
    },
    "Druid": {
        "cantrips": [
            {"id": "Druidcraft", "name_tr": "Druid Hüneri (Druidcraft)", "desc": "Hava tahmini, tohum yeşertme gibi küçük doğa efektleri."},
            {"id": "Shillelagh", "name_tr": "Sihirli Sopa (Shillelagh)", "desc": "Asanın hasarını 1d8 + BİL mod yapar ve vuruşta BİL modunu kullanır."},
            {"id": "Produce Flame", "name_tr": "Alev Yaratma (Produce Flame)", "desc": "Elde meşale gibi alev oluşturur veya 1d8 menzilli fırlatır."},
            {"id": "Thorn Whip", "name_tr": "Dikenli Kırbaç (Thorn Whip)", "desc": "1d6 delici hasar verir ve hedefi 10 fit kendine çeker."},
            {"id": "Guidance", "name_tr": "Rehberlik (Guidance)", "desc": "Yetenek zarlarına +1d4 ekler."},
        ],
        "spells_level_1": [
            {"id": "Cure Wounds", "name_tr": "Yara İyileştirme (Cure Wounds)", "desc": "Dokunarak 2d8 + BİL can tazeler."},
            {"id": "Healing Word", "name_tr": "Şifa Sözü (Healing Word)", "desc": "Bonus eylemle uzaktan 2d4 + BİL can tazeler."},
            {"id": "Entangle", "name_tr": "Sarmaşık Tuzağı (Entangle)", "desc": "Bitkileri filizlendirip düşmanları kısıtlar (Restrained)."},
            {"id": "Faerie Fire", "name_tr": "Peri Ateşi (Faerie Fire)", "desc": "Işıltıyla alanı parlatır, hedeflere saldırılarda avantaj sağlar."},
            {"id": "Thunderwave", "name_tr": "Gök Gürültüsü Dalgası", "desc": "15 fitlik alana 2d8 hasar ve itiş uygular."},
            {"id": "Speak with Animals", "name_tr": "Hayvanlarla Konuşma", "desc": "Hayvanlarla iletişim kurmayı sağlar."},
        ],
    },
    "Paladin": {
        "cantrips": [],
        "spells_level_1": [
            {"id": "Bless", "name_tr": "Kutsama (Bless)", "desc": "Üç müttefikin saldırı ve kurtarma zarlarına destek verir."},
            {"id": "Cure Wounds", "name_tr": "Yara İyileştirme (Cure Wounds)", "desc": "Dokunulan bir canlının yaralarını iyileştirir."},
            {"id": "Command", "name_tr": "Emir (Command)", "desc": "Hedefe tek kelimelik bir emir verir."},
        ],
    },
    "Ranger": {
        "cantrips": [],
        "spells_level_1": [
            {"id": "Cure Wounds", "name_tr": "Yara İyileştirme (Cure Wounds)", "desc": "Dokunulan bir canlının yaralarını iyileştirir."},
            {"id": "Entangle", "name_tr": "Sarmaşık Tuzağı (Entangle)", "desc": "Bitkilerle bir alanı sararak içindeki hedefleri kısıtlar."},
            {"id": "Speak with Animals", "name_tr": "Hayvanlarla Konuşma", "desc": "Hayvanlarla iletişim kurmayı sağlar."},
        ],
    },
    "Sorcerer": {
        "cantrips": [
            {"id": "Fire Bolt", "name_tr": "Ateş Oku (Fire Bolt)", "desc": "1d10 ateş hasarı fırlatır."},
            {"id": "Ray of Frost", "name_tr": "Buz Işını (Ray of Frost)", "desc": "1d8 soğuk hasarı verir ve yavaşlatır."},
            {"id": "Mage Hand", "name_tr": "Büyücü Eli (Mage Hand)", "desc": "Görünmez büyü eli yaratır."},
            {"id": "Minor Illusion", "name_tr": "Küçük Yanılsama", "desc": "Görsel/ses yanılsaması üretir."},
            {"id": "Shocking Grasp", "name_tr": "Şok Dokunuşu", "desc": "1d8 yıldırım hasarı ve tepkiyi kilitler."},
            {"id": "Prestidigitation", "name_tr": "Hokkabazlık", "desc": "Küçük büyü efektleri üretir."},
        ],
        "spells_level_1": [
            {"id": "Magic Missile", "name_tr": "Sihirli Füze", "desc": "Üç isabetli füze fırlatır (3x 1d4 + 1)."},
            {"id": "Shield", "name_tr": "Kalkan (Shield)", "desc": "Tepki olarak +5 Zırh Sınıfı sağlar."},
            {"id": "Burning Hands", "name_tr": "Alevli Eller", "desc": "15 fit koniye 3d6 ateş hasarı saçar."},
            {"id": "Chromatic Orb", "name_tr": "Renk Küresi (Chromatic Orb)", "desc": "Seçilen element türünde 3d8 güçlü hasar fırlatır."},
            {"id": "Chaos Bolt", "name_tr": "Kaos Oku (Chaos Bolt)", "desc": "Rastgele elementte 2d8 + 1d6 hasar verir ve sıçrayabilir."},
            {"id": "Disguise Self", "name_tr": "Kılık Değiştirme", "desc": "Dış görünüşü tamamen yanılsamayla değiştirir."},
        ],
    },
    "Warlock": {
        "cantrips": [
            {"id": "Eldritch Blast", "name_tr": "Mistik Patlama (Eldritch Blast)", "desc": "120 fitten 1d10 saf kuvvet (Force) hasarı vurur."},
            {"id": "Toll the Dead", "name_tr": "Ölüm Çanı", "desc": "1d8 / 1d12 nekrotik hasar verir."},
            {"id": "Mage Hand", "name_tr": "Büyücü Eli", "desc": "Uzakta nesne taşıyan büyü eli."},
            {"id": "Minor Illusion", "name_tr": "Küçük Yanılsama", "desc": "Görsel ve ses efektleri."},
            {"id": "Prestidigitation", "name_tr": "Hokkabazlık", "desc": "Ufak büyü dokunuşları."},
        ],
        "spells_level_1": [
            {"id": "Hex", "name_tr": "Uğursuzluk (Hex)", "desc": "Hedefe her vuruşta +1d6 nekrotik hasar verir ve bir özelliğine dezavantaj koyar."},
            {"id": "Hellish Rebuke", "name_tr": "Cehennem Misillemesi", "desc": "Sana vuran düşmana tepki olarak 2d10 ateş hasarı püskürtür."},
            {"id": "Armor of Agathys", "name_tr": "Agathys Zırhı", "desc": "5 Geçici Can verir ve sana vuranlara 5 soğuk hasarı yansıtır."},
            {"id": "Arms of Hadar", "name_tr": "Hadar'ın Kolları", "desc": "Karanlık dokunaçlarla 2d6 nekrotik hasar verir ve tepkileri engeller."},
            {"id": "Charm Person", "name_tr": "Büyüleme", "desc": "İnsansı bir yaratığı dost edinir."},
        ],
    },
    "Bard": {
        "cantrips": [
            {"id": "Vicious Mockery", "name_tr": "Aşağılayıcı Alay (Vicious Mockery)", "desc": "1d4 psişik hasar verir ve hedefin sonraki saldırısına dezavantaj yükler."},
            {"id": "Minor Illusion", "name_tr": "Küçük Yanılsama", "desc": "Yanılsama görüntüsü veya sesi üretir."},
            {"id": "Dancing Lights", "name_tr": "Dans Eden Işıklar", "desc": "Dört adet hareketli ışık küresi yaratır."},
            {"id": "Mage Hand", "name_tr": "Büyücü Eli", "desc": "Mesafe nesnelerini yöneten el."},
            {"id": "Prestidigitation", "name_tr": "Hokkabazlık", "desc": "Göz boyama ve temizlik hileleri."},
        ],
        "spells_level_1": [
            {"id": "Dissonant Whispers", "name_tr": "Uyumsuz Fısıltılar", "desc": "3d6 psişik hasar vurur ve hedefi derhal kaçmaya zorlar."},
            {"id": "Healing Word", "name_tr": "Şifa Sözü", "desc": "Bonus eylemle uzaktan 2d4 + KAR can yeniler."},
            {"id": "Thunderwave", "name_tr": "Gök Gürültüsü Dalgası", "desc": "15 fit alandaki düşmanları fırlatır."},
            {"id": "Charm Person", "name_tr": "Büyüleme", "desc": "İnsansı hedefi kendine ısındırır."},
            {"id": "Disguise Self", "name_tr": "Kılık Değiştirme", "desc": "Görünüşünü büyüyle baştan yaratır."},
            {"id": "Cure Wounds", "name_tr": "Yara İyileştirme (Cure Wounds)", "desc": "Dokunulan hedefe 2d8 + KAR mod can yeniler (2024)."},
        ],
    },
}


# ============================================================================
# AUTHORITATIVE CATALOG ACCESSOR
# ============================================================================

ARMOR_CLASS_RULES = {
    "Chain Mail": {"base_ac": 16, "dexterity_mode": "none"},
    "Scale Mail": {
        "base_ac": 14,
        "dexterity_mode": "capped",
        "max_dexterity_bonus": 2,
    },
    "Leather Armor": {"base_ac": 11, "dexterity_mode": "full"},
}

ARMOR_NAME_ALIASES = {
    "Zincir Zırh": "Chain Mail",
    "Chain Mail": "Chain Mail",
    "Pul Zırh": "Scale Mail",
    "Scale Mail": "Scale Mail",
    "Deri Zırh": "Leather Armor",
    "Leather Armor": "Leather Armor",
}

SHIELD_ITEM_TOKENS = ("kalkan", "shield")


def get_equipment_armor_and_shield(
    equipment_choices: list[str] | None,
) -> tuple[str | None, bool]:
    """Resolve armor and shield from the same labels exposed to the client."""
    if not equipment_choices:
        return None, False

    joined = " ".join(equipment_choices).casefold()
    armor = next(
        (
            canonical_name
            for alias, canonical_name in ARMOR_NAME_ALIASES.items()
            if alias.casefold() in joined
        ),
        None,
    )
    has_shield = any(token in joined for token in SHIELD_ITEM_TOKENS)
    return armor, has_shield


def get_character_creation_catalog() -> dict[str, Any]:
    """Expose complete D&D 2024 rules options for client-side player choices."""
    return {
        "races": copy.deepcopy(SPECIES_DEFINITIONS),
        "classes": copy.deepcopy(CLASS_DEFINITIONS),
        "backgrounds": copy.deepcopy(BACKGROUND_DEFINITIONS),
        "ability_score_methods": [
            {
                "id": "standard_array",
                "name_tr": "Standart Dizi (Standard Array)",
                "scores": STANDARD_ARRAY,
                "desc": "Altı temel değer (15, 14, 13, 12, 10, 8) istediğin yeteneklere serbestçe atanır.",
            },
            {
                "id": "point_buy",
                "name_tr": "Puan Satın Alma (Point Buy)",
                "budget": POINT_BUY_BUDGET,
                "min_score": 8,
                "max_score": 15,
                "costs": POINT_BUY_COSTS,
                "desc": "27 puanlık bütçeyle 8 ile 15 arasındaki değerleri kendi oyun tarzına göre dağıt.",
            },
            {
                "id": "rolled",
                "name_tr": "Zar Atma (4d6 Drop Lowest)",
                "desc": "Her yetenek için 4 adet altılı zar atılır, en düşük zar atılır ve kalan 3 zar toplanır.",
            },
        ],
        "alignments": copy.deepcopy(ALIGNMENTS),
        "languages": {
            "standard": list(STANDARD_LANGUAGES),
            "rare": list(RARE_LANGUAGES),
        },
        "origin_feats": copy.deepcopy(ORIGIN_FEATS),
        "spells_catalog": copy.deepcopy(SPELLS_CATALOG),
        "skills": {k: {"ability": v["ability"], "name_tr": v["name_tr"]} for k, v in SKILL_DEFINITIONS.items()},
        "equipment_rules": {
            "armor_class": copy.deepcopy(ARMOR_CLASS_RULES),
            "armor_name_aliases": copy.deepcopy(ARMOR_NAME_ALIASES),
            "shield_item_tokens": list(SHIELD_ITEM_TOKENS),
        },
    }


def get_expertise_choice_count(character_class: str, level: int) -> int:
    """Return the number of Expertise skill choices granted by 2024 class features."""
    if type(level) is not int or level < 1:
        raise CharacterCreationError("Character level must be a positive integer.")
    class_data = CLASS_DEFINITIONS.get(character_class)
    if class_data is None:
        raise CharacterCreationError(f"Unsupported class: {character_class}")
    return sum(
        feature["choices"]
        for feature in class_data.get("expertise_progression", [])
        if level >= feature["level"]
    )


# ============================================================================
# VALIDATION & DERIVATION LOGIC
# ============================================================================

def roll_4d6_drop_lowest(rng: random.Random) -> int:
    rolls = [rng.randint(1, 6) for _ in range(4)]
    rolls.remove(min(rolls))
    return sum(rolls)


def validate_ability_scores(
    method: str,
    base_scores: dict[str, int],
    rolled_pool: list[int] | None = None,
) -> None:
    if not isinstance(base_scores, dict):
        raise CharacterCreationError("Ability scores must be provided as a dictionary.")
    for key in ABILITY_KEYS:
        if key not in base_scores or not isinstance(base_scores[key], int):
            raise CharacterCreationError(f"Missing or invalid ability score for {key}.")

    scores = [base_scores[k] for k in ABILITY_KEYS]

    if method == "standard_array":
        if sorted(scores) != sorted(STANDARD_ARRAY):
            raise CharacterCreationError(
                f"Standard Array requires assigning exact values {STANDARD_ARRAY}."
            )
    elif method == "point_buy":
        total_cost = 0
        for val in scores:
            if val < 8 or val > 15:
                raise CharacterCreationError("Point buy scores must be between 8 and 15.")
            total_cost += POINT_BUY_COSTS[val]
        if total_cost != POINT_BUY_BUDGET:
            raise CharacterCreationError(
                f"Point buy must spend exactly {POINT_BUY_BUDGET} points (spent {total_cost})."
            )
    elif method == "rolled":
        if rolled_pool:
            if sorted(scores) != sorted(rolled_pool):
                raise CharacterCreationError(
                    "Assigned scores do not match the rolled dice pool."
                )
        else:
            raise CharacterCreationError(
                "Rolled scores require a verified dice pool from the game engine; arbitrary manual scores are not accepted."
            )
    elif method == "manual":
        for val in scores:
            if not 3 <= val <= 18:
                raise CharacterCreationError("Manual scores must be between 3 and 18.")
    else:
        raise CharacterCreationError(f"Unsupported ability score generation method: {method}")


def validate_background_bonuses(
    background_key: str,
    bonuses: dict[str, int],
    base_scores: dict[str, int] | None = None,
) -> None:
    bg = BACKGROUND_DEFINITIONS.get(background_key)
    if not bg:
        raise CharacterCreationError(f"Unsupported background: {background_key}")

    permitted_abilities = set(bg["abilities"])
    for ability, val in bonuses.items():
        if val > 0 and ability not in permitted_abilities:
            raise CharacterCreationError(
                f"Ability '{ability}' is not eligible for bonuses from background '{background_key}'."
            )

    positive_bonuses = [b for b in bonuses.values() if b > 0]
    is_two_one = sorted(positive_bonuses) == [1, 2]
    is_one_one_one = sorted(positive_bonuses) == [1, 1, 1]

    if not (is_two_one or is_one_one_one):
        raise CharacterCreationError(
            "Background bonuses must be either (+2 to one, +1 to another) or (+1 to three distinct abilities)."
        )

    if base_scores is not None:
        for ability, bonus in bonuses.items():
            if bonus > 0 and ability in base_scores:
                if base_scores[ability] + bonus > 20:
                    raise CharacterCreationError(
                        f"Ability score for '{ability}' cannot exceed 20 after background bonuses (score was {base_scores[ability]} + {bonus})."
                    )


def calculate_derived_stats(
    character_class: str,
    species: str,
    final_scores: dict[str, int],
    chosen_feat: str | None = None,
    fighting_style: str | None = None,
    equipped_armor: str | None = None,
    has_shield: bool = False,
    chosen_feats: list[str] | None = None,
) -> dict[str, Any]:
    cls_def = CLASS_DEFINITIONS.get(character_class)
    if not cls_def:
        raise CharacterCreationError(f"Unsupported class: {character_class}")

    modifiers = {k: get_modifier(final_scores[k]) for k in ABILITY_KEYS}

    # Hit points: Max hit die + CON mod
    hit_die = cls_def["hit_die"]
    base_hp = hit_die + modifiers["constitution"]

    # Species HP bonuses are part of the same catalog the client previews.
    base_hp += int(SPECIES_DEFINITIONS.get(species, {}).get("hp_bonus", 0))

    # Feat bonus (Tough); include both background and species-granted feats.
    all_chosen_feats = {
        canonical_origin_feat_name(feat)
        for feat in [chosen_feat, *(chosen_feats or [])]
        if feat
    }
    base_hp += sum(
        int(ORIGIN_FEATS.get(feat, {}).get("hp_bonus", 0))
        for feat in all_chosen_feats
    )

    max_hp = max(1, base_hp)

    # Armor class
    dex_mod = modifiers["dexterity"]
    con_mod = modifiers["constitution"]
    wis_mod = modifiers["wisdom"]

    canonical_armor = ARMOR_NAME_ALIASES.get(equipped_armor, equipped_armor)
    armor_rule = ARMOR_CLASS_RULES.get(canonical_armor)
    armor_worn = armor_rule is not None
    if armor_rule:
        ac = armor_rule["base_ac"]
        if armor_rule["dexterity_mode"] == "full":
            ac += dex_mod
        elif armor_rule["dexterity_mode"] == "capped":
            ac += min(armor_rule["max_dexterity_bonus"], dex_mod)
    elif character_class == "Barbarian":
        ac = 10 + dex_mod + con_mod
    elif character_class == "Monk":
        ac = 10 + dex_mod + wis_mod
    else:
        ac = 10 + dex_mod

    if has_shield:
        ac += 2

    if fighting_style == "Defense" and armor_worn:
        ac += 1

    proficiency_bonus = 2

    # Saving throws
    saving_throws = cls_def["saving_throws"]
    saving_throw_mods = {
        ability: modifiers[ability] + (proficiency_bonus if ability in saving_throws else 0)
        for ability in ABILITY_KEYS
    }

    # Spellcasting DC and attack bonus
    spell_dc = None
    spell_attack = None
    if cls_def.get("is_spellcaster"):
        casting_mod = modifiers[cls_def["spellcasting_ability"]]
        spell_dc = 8 + proficiency_bonus + casting_mod
        spell_attack = proficiency_bonus + casting_mod

    # Initiative bonus
    initiative = dex_mod
    if chosen_feat == "Alert":
        initiative += proficiency_bonus

    return {
        "max_hp": max_hp,
        "current_hp": max_hp,
        "armor_class": ac,
        "proficiency_bonus": proficiency_bonus,
        "modifiers": modifiers,
        "saving_throws": saving_throws,
        "saving_throw_mods": saving_throw_mods,
        "initiative": initiative,
        "spell_save_dc": spell_dc,
        "spell_attack_bonus": spell_attack,
        "passive_perception": 10 + modifiers["wisdom"],
    }


def generate_random_2024_character(rng: random.Random) -> dict[str, Any]:
    """Authoritative server-side random character generation for D&D 2024 rules."""
    name = rng.choice([
        "Aldric", "Kael", "Thorne", "Riven", "Darius",
        "Elias", "Garrick", "Rowan", "Cedric", "Aric",
        "Mira", "Lyra", "Elara", "Seraphine", "Nyra",
        "Freya", "Astrid", "Kara", "Selene", "Rhea",
    ])
    species = rng.choice(list(SPECIES_DEFINITIONS.keys()))
    character_class = rng.choice(list(CLASS_DEFINITIONS.keys()))
    background = rng.choice(list(BACKGROUND_DEFINITIONS.keys()))
    alignment = rng.choice([a["id"] for a in ALIGNMENTS if a["id"] != "Unaligned"])

    bg_def = BACKGROUND_DEFINITIONS[background]
    cls_def = CLASS_DEFINITIONS[character_class]

    # Standard array assigned smartly to primary ability
    primary = cls_def["primary_ability"]
    remaining_abilities = [a for a in ABILITY_KEYS if a != primary]
    rng.shuffle(remaining_abilities)

    assigned_scores = {primary: 15}
    scores_pool = [14, 13, 12, 10, 8]
    for ability, score in zip(remaining_abilities, scores_pool):
        assigned_scores[ability] = score

    # Background bonus: +2 to primary if in background abilities, else pick from background
    bg_abilities = list(bg_def["abilities"])
    if primary in bg_abilities:
        plus_two = primary
        remaining_bg = [a for a in bg_abilities if a != primary]
        plus_one = rng.choice(remaining_bg)
    else:
        plus_two = rng.choice(bg_abilities)
        remaining_bg = [a for a in bg_abilities if a != plus_two]
        plus_one = rng.choice(remaining_bg)

    bonuses = {plus_two: 2, plus_one: 1}
    final_scores = {
        ability: assigned_scores[ability] + bonuses.get(ability, 0)
        for ability in ABILITY_KEYS
    }

    # Skills: background skills + class skills (avoiding duplicates)
    bg_skills = list(bg_def["skills"])
    available_class_skills = [s for s in cls_def["skill_options"] if s not in bg_skills]
    skill_count = min(len(available_class_skills), cls_def["skill_count"])
    chosen_class_skills = rng.sample(available_class_skills, skill_count)
    all_skills = bg_skills + chosen_class_skills

    species_bonus_skill_count = SPECIES_DEFINITIONS[species].get("skill_bonus_count", 0)
    species_bonus_skills = rng.sample(
        [skill for skill in SKILL_DEFINITIONS if skill not in all_skills],
        min(species_bonus_skill_count, len(SKILL_DEFINITIONS)),
    )
    all_skills.extend(species_bonus_skills)

    # Equipment
    pkg = rng.choice(cls_def["equipment_packages"])
    equipment_items = list(pkg["items"]) + list(bg_def["equipment"])

    # Spells if spellcaster
    cantrips = []
    spells = []
    if cls_def.get("is_spellcaster"):
        spells_for_class = SPELLS_CATALOG.get(character_class, {})
        available_cantrips = [c["id"] for c in spells_for_class.get("cantrips", [])]
        available_spells = [s["id"] for s in spells_for_class.get("spells_level_1", [])]

        c_count = min(len(available_cantrips), cls_def.get("cantrips_count", 0))
        s_count = min(len(available_spells), cls_def.get("spells_count", 0))

        if c_count > 0:
            cantrips = rng.sample(available_cantrips, c_count)
        if s_count > 0:
            spells = rng.sample(available_spells, s_count)

    # Fighting style for Fighter
    fighting_style = None
    if character_class == "Fighter" and cls_def.get("fighting_styles"):
        fighting_style = rng.choice([f["id"] for f in cls_def["fighting_styles"]])

    origin_feat = bg_def["feat"]
    species_bonus_feat = None
    if SPECIES_DEFINITIONS[species].get("origin_feat_bonus_count", 0):
        feat_options = [
            feat for feat in ORIGIN_FEATS
            if canonical_origin_feat_name(feat) != canonical_origin_feat_name(origin_feat)
        ]
        if feat_options:
            species_bonus_feat = rng.choice(feat_options)
    origin_feats = [origin_feat, *([species_bonus_feat] if species_bonus_feat else [])]

    # Derived stats
    equipped_armor, has_shield = get_equipment_armor_and_shield(equipment_items)
    derived = calculate_derived_stats(
        character_class=character_class,
        species=species,
        final_scores=final_scores,
        chosen_feat=origin_feat,
        chosen_feats=origin_feats,
        fighting_style=fighting_style,
        equipped_armor=equipped_armor,
        has_shield=has_shield,
    )

    return {
        "name": name,
        "species": species,
        "race": species,
        "class": character_class,
        "background": background,
        "alignment": alignment,
        "ability_score_method": "standard_array",
        "base_ability_scores": assigned_scores,
        "background_ability_bonuses": bonuses,
        "final_ability_scores": final_scores,
        "proficient_skills": all_skills,
        "species_bonus_skills": species_bonus_skills,
        "proficient_tools": [bg_def["tool"]],
        "origin_feat": origin_feat,
        "species_bonus_feat": species_bonus_feat,
        "origin_feats": origin_feats,
        "fighting_style": fighting_style,
        "equipment_choices": equipment_items,
        "cantrips": cantrips,
        "spells": spells,
        "derived": derived,
    }
