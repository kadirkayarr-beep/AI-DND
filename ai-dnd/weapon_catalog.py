"""PHB 2024, printed pp. 213–215 (uploaded PDF pp. 212–214).

One catalog, including the historical Turkish starter-sword alias. Prices are GP.
Catalog entries never grant proficiency or mastery to their wielder.
"""


def weapon(name, category, kind, dice, damage_type, properties, mastery,
           weight, cost, *, ranges=None, ammo=None, versatile=None, aliases=()):
    count, die = dice if isinstance(dice, tuple) else (0, 0)
    return {
        "weapon_id": name.lower().replace(" ", "_"), "name": name,
        "category": category, "kind": kind, "damage_dice": count, "damage_die": die,
        "fixed_damage": dice if isinstance(dice, int) else None,
        "damage_type": damage_type, "properties": properties.split(),
        "mastery": mastery, "weight_lb": weight, "cost_gp": cost,
        "normal_range": ranges[0] if ranges else None,
        "long_range": ranges[1] if ranges else None, "ammunition_type": ammo,
        "versatile_damage_die": versatile, "magic_attack_bonus": 0,
        "magic_damage_bonus": 0, "source": "PHB 2024 p.215",
        "ability": "strength" if kind == "melee" else "dexterity",
        "aliases": list(aliases),
    }


_ROWS = [
    ("Club", "simple", "melee", (1, 4), "bludgeoning", "light", "slow", 2, .1, {}),
    ("Dagger", "simple", "melee", (1, 4), "piercing", "finesse light thrown", "nick", 1, 2, {"ranges": (20, 60), "aliases": ["hançer", "hançerle", "hancer", "hancerle"]}),
    ("Greatclub", "simple", "melee", (1, 8), "bludgeoning", "two-handed", "push", 10, .2, {}),
    ("Handaxe", "simple", "melee", (1, 6), "slashing", "light thrown", "vex", 2, 5, {"ranges": (20, 60)}),
    ("Javelin", "simple", "melee", (1, 6), "piercing", "thrown", "slow", 2, .5, {"ranges": (30, 120)}),
    ("Light Hammer", "simple", "melee", (1, 4), "bludgeoning", "light thrown", "nick", 2, 2, {"ranges": (20, 60)}),
    ("Mace", "simple", "melee", (1, 6), "bludgeoning", "", "sap", 4, 5, {}),
    ("Quarterstaff", "simple", "melee", (1, 6), "bludgeoning", "versatile", "topple", 4, .2, {"versatile": 8}),
    ("Sickle", "simple", "melee", (1, 4), "slashing", "light", "nick", 2, 1, {}),
    ("Spear", "simple", "melee", (1, 6), "piercing", "thrown versatile", "sap", 3, 1, {"ranges": (20, 60), "versatile": 8}),
    ("Dart", "simple", "ranged", (1, 4), "piercing", "finesse thrown", "vex", .25, .05, {"ranges": (20, 60)}),
    ("Light Crossbow", "simple", "ranged", (1, 8), "piercing", "ammunition loading two-handed", "slow", 5, 25, {"ranges": (80, 320), "ammo": "bolt"}),
    ("Shortbow", "simple", "ranged", (1, 6), "piercing", "ammunition two-handed", "vex", 2, 25, {"ranges": (80, 320), "ammo": "arrow", "aliases": ["yay", "yayımla", "yayimla"]}),
    ("Sling", "simple", "ranged", (1, 4), "bludgeoning", "ammunition", "slow", None, .1, {"ranges": (30, 120), "ammo": "bullet"}),
    ("Battleaxe", "martial", "melee", (1, 8), "slashing", "versatile", "topple", 4, 10, {"versatile": 10}),
    ("Flail", "martial", "melee", (1, 8), "bludgeoning", "", "sap", 2, 10, {}),
    ("Glaive", "martial", "melee", (1, 10), "slashing", "heavy reach two-handed", "graze", 6, 20, {}),
    ("Greataxe", "martial", "melee", (1, 12), "slashing", "heavy two-handed", "cleave", 7, 30, {}),
    ("Greatsword", "martial", "melee", (2, 6), "slashing", "heavy two-handed", "graze", 6, 50, {}),
    ("Halberd", "martial", "melee", (1, 10), "slashing", "heavy reach two-handed", "cleave", 6, 20, {}),
    ("Lance", "martial", "melee", (1, 10), "piercing", "heavy reach two-handed", "topple", 6, 10, {}),
    ("Longsword", "martial", "melee", (1, 8), "slashing", "versatile", "sap", 3, 15, {"versatile": 10, "aliases": ["Kılıç", "kılıcımla", "kilic", "kilici", "kilicimla", "kılıcı"]}),
    ("Maul", "martial", "melee", (2, 6), "bludgeoning", "heavy two-handed", "topple", 10, 10, {}),
    ("Morningstar", "martial", "melee", (1, 8), "piercing", "", "sap", 4, 15, {}),
    ("Pike", "martial", "melee", (1, 10), "piercing", "heavy reach two-handed", "push", 18, 5, {}),
    ("Rapier", "martial", "melee", (1, 8), "piercing", "finesse", "vex", 2, 25, {}),
    ("Scimitar", "martial", "melee", (1, 6), "slashing", "finesse light", "nick", 3, 25, {}),
    ("Shortsword", "martial", "melee", (1, 6), "piercing", "finesse light", "vex", 2, 10, {}),
    ("Trident", "martial", "melee", (1, 8), "piercing", "thrown versatile", "topple", 4, 5, {"ranges": (20, 60), "versatile": 10}),
    ("Warhammer", "martial", "melee", (1, 8), "bludgeoning", "versatile", "push", 5, 15, {"versatile": 10}),
    ("War Pick", "martial", "melee", (1, 8), "piercing", "versatile", "sap", 2, 5, {"versatile": 10}),
    ("Whip", "martial", "melee", (1, 4), "slashing", "finesse reach", "slow", 3, 2, {}),
    ("Blowgun", "martial", "ranged", 1, "piercing", "ammunition loading", "vex", 1, 10, {"ranges": (25, 100), "ammo": "needle"}),
    ("Hand Crossbow", "martial", "ranged", (1, 6), "piercing", "ammunition light loading", "vex", 3, 75, {"ranges": (30, 120), "ammo": "bolt"}),
    ("Heavy Crossbow", "martial", "ranged", (1, 10), "piercing", "ammunition heavy loading two-handed", "push", 18, 50, {"ranges": (100, 400), "ammo": "bolt"}),
    ("Longbow", "martial", "ranged", (1, 8), "piercing", "ammunition heavy two-handed", "slow", 2, 50, {"ranges": (150, 600), "ammo": "arrow"}),
    ("Musket", "martial", "ranged", (1, 12), "piercing", "ammunition loading two-handed", "slow", 10, 500, {"ranges": (40, 120), "ammo": "bullet"}),
    ("Pistol", "martial", "ranged", (1, 10), "piercing", "ammunition loading", "vex", 3, 250, {"ranges": (30, 90), "ammo": "bullet"}),
]

WEAPONS = {row[0]: weapon(*row[:9], **row[9]) for row in _ROWS}
# Preserve existing caller keys, not a second set of statistics.
WEAPONS["Kılıç"] = WEAPONS["Longsword"]


def lookup(identity):
    if not isinstance(identity, str):
        return None
    text = identity.casefold()
    for item in WEAPONS.values():
        if text in {item["weapon_id"], item["name"].casefold(),
                    *(alias.casefold() for alias in item["aliases"])}:
            return item
    return None