import effect_targeting


RACES = [
    "Aasimar",
    "Human",
    "Elf",
    "Dwarf",
    "Halfling",
    "Gnome",
    "Half-Elf",
    "Half-Orc",
    "Tiefling",
    "Dragonborn",
    "Goliath",
    "Orc",
]

RACE_FEATURES = {

    "Human": [
        "Resourceful",
        "Skillful",
        "Versatile",
    ],

    "Elf": [
        "Darkvision",
        "Elven Lineage",
        "Fey Ancestry",
        "Keen Senses",
        "Trance",
    ],

    "Dwarf": [
        "Darkvision",
        "Dwarven Resilience",
        "Dwarven Toughness",
        "Stonecunning",
    ],

    "Halfling": [
        "Brave",
        "Halfling Nimbleness",
        "Lucky",
        "Naturally Stealthy",
    ],

    "Gnome": [
        "Darkvision",
        "Gnomish Cunning",
        "Gnomish Lineage",
    ],

    "Half-Elf": [
        "Darkvision",
        "Fey Ancestry",
        "Skill Versatility",
    ],

    "Half-Orc": [
        "Darkvision",
        "Menacing",
        "Relentless Endurance",
        "Savage Attacks",
    ],

    "Tiefling": [
        "Darkvision",
        "Fiendish Legacy",
        "Otherworldly Presence",
    ],

    "Dragonborn": [
        "Breath Weapon",
        "Darkvision",
        "Draconic Ancestry",
        "Draconic Flight",
    ],

    "Aasimar": [
        "Celestial Resistance",
        "Celestial Revelation",
        "Darkvision",
        "Healing Hands",
        "Light Bearer",
    ],

    "Goliath": [
        "Giant Ancestry",
        "Large Form",
        "Powerful Build",
    ],

    "Orc": [
        "Adrenaline Rush",
        "Darkvision",
        "Relentless Endurance",
    ],
}

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
        "Nature",
        "Religion"
    ]
}

DIFFICULTY_DC = {

    "easy": 10,
    "medium": 15,
    "hard": 20,
    "very_hard": 25,
    "extreme": 30
}

RANDOM_NAMES = [
    "Aldric", "Kael", "Thorne", "Riven", "Darius",
    "Elias", "Garrick", "Rowan", "Cedric", "Aric",
    "Mira", "Lyra", "Elara", "Seraphine", "Nyra",
    "Freya", "Astrid", "Kara", "Selene", "Rhea"
]

GIANT_ANCESTRY_IDS = ("cloud", "fire", "frost", "hill", "stone", "storm")

CELESTIAL_REVELATION_FORMS = (
    "heavenly_wings",
    "inner_radiance",
    "necrotic_shroud",
)

INNER_RADIANCE_SPEC = effect_targeting.EffectSpec("inner_radiance", 10, "PHB 2024 p.185 (PDF) Aasimar: Inner Radiance")

NECROTIC_SHROUD_SPEC = effect_targeting.EffectSpec(
    "necrotic_shroud", 10, "PHB 2024 p.185 (PDF) Aasimar: Necrotic Shroud", excludes_allies=True)

SPECIES_WITH_TRAIT_STATE = frozenset({"Aasimar", "Goliath", "Orc", "Half-Orc"})

_ABILITY_NAMES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")

_ORIGIN_TEXT_KEYS = ("background", "alignment", "ability_score_method", "background_equipment_option", "species_bonus_feat")

_ORIGIN_LIST_KEYS = ("languages", "origin_feats")

_ORIGIN_SCORE_KEYS = ("background_ability_bonuses", "base_ability_scores")

DEATH_MODES = ("NORMAL", "PERMADEATH", "IRONMAN")

CHECK_FEATURES = ('primal_knowledge', 'tactical_mind')
