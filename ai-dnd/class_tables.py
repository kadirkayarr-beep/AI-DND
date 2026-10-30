"""Source-backed PHB 2024 class progression TABLES for ten classes (Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger,
Rogue, Warlock, Wizard) -- a DATA ORACLE only.

The tables live in `content/rules/phb2024/class_tables/<class>.json` (a class that gained real progression moves to `classes/`,
see MOVED_TO_CLASSES) and use the same shape as the `classes/` files
(`source`, `levels` -> "1".."20" with `proficiency_bonus`, `features` and class columns, `subclass_options`).  They are kept
in a SEPARATE directory on purpose: `character_progression.table()` treats every file in `classes/` as "this class has a
progression table" (creation, level-up, spell scope), so putting these files there would change gameplay behaviour.  This
module never feeds `character_progression`; no class becomes supported for creation or level-up through it.
Only values and feature NAMES are stored, never book text.  A cell that could not be verified is stored as null and listed
in `source.unverified_cells`; a null without that listing is the table's own em dash ("no value at this level").
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from api.dnd_2024_rules import proficiency_bonus_for_level

TABLE_DIR = Path(__file__).resolve().parents[1] / "content" / "rules" / "phb2024" / "class_tables"
MOVED_TO_CLASSES = {"Fighter"}  # progression owns these files now; the oracle reads the one file, never a copy
CLASSES = ("Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Warlock", "Wizard")

# Class-specific columns per class (besides proficiency_bonus and features). Columns that may be null (em dash) are listed too.
COLUMNS: dict[str, tuple[str, ...]] = {
    "Bard": ("bardic_die", "cantrips", "prepared_spells", "slots"),
    "Cleric": ("channel_divinity", "cantrips", "prepared_spells", "slots"),
    "Druid": ("wild_shape", "cantrips", "prepared_spells", "slots"),
    "Fighter": ("second_wind", "weapon_mastery"),
    "Monk": ("martial_arts_die", "focus_points", "unarmored_movement_ft"),
    "Paladin": ("channel_divinity", "prepared_spells", "slots"),
    "Ranger": ("favored_enemy", "prepared_spells", "slots"),
    "Rogue": ("sneak_attack_dice", "sneak_attack_die"),
    "Warlock": ("eldritch_invocations", "cantrips", "prepared_spells", "pact_slots", "mystic_arcanum_spell_level"),
    "Wizard": ("cantrips", "prepared_spells", "slots"),
}
NULLABLE = {
    "Cleric": {"channel_divinity"}, "Druid": {"wild_shape"}, "Paladin": {"channel_divinity"},
    "Monk": {"focus_points", "unarmored_movement_ft"}, "Warlock": {"mystic_arcanum_spell_level"},
}
MAX_SLOT_LEVEL = {"Bard": 9, "Cleric": 9, "Druid": 9, "Wizard": 9, "Paladin": 5, "Ranger": 5}
_cache: dict[str, dict[str, Any] | None] = {}


def table_path(class_name: str) -> Path:
    return (TABLE_DIR.parent / "classes" if class_name in MOVED_TO_CLASSES else TABLE_DIR) / f"{class_name.lower()}.json"


def table(class_name: Any) -> dict[str, Any] | None:
    """A detached copy of the class table, or None for a class outside CLASSES or a missing file."""
    if not isinstance(class_name, str) or class_name not in CLASSES:
        return None
    if class_name not in _cache:
        path = table_path(class_name)
        _cache[class_name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return copy.deepcopy(_cache[class_name])


def _is_int(value: Any) -> bool:
    return type(value) is int


def validate(class_name: str, data: Any) -> list[str]:
    """Structural problems of one class table (empty list = well formed). Oracle VALUES are checked by the tests, not here."""
    problems: list[str] = []
    if class_name not in CLASSES:
        return [f"unknown class {class_name!r}"]
    if not isinstance(data, dict) or not isinstance(data.get("levels"), dict):
        return ["table has no levels object"]
    source = data.get("source")
    if not isinstance(source, dict) or source.get("class") != class_name or not isinstance(source.get("unverified_cells"), list):
        problems.append("source block is missing, names another class, or has no unverified_cells list")
    levels = data["levels"]
    if list(levels) != [str(n) for n in range(1, 21)]:
        problems.append("levels must be exactly '1'..'20' in order")
        return problems
    expected_keys = {"proficiency_bonus", "features", *COLUMNS[class_name]}
    unverified = ({tuple(cell) for cell in source.get("unverified_cells", [])
                   if isinstance(cell, list) and len(cell) == 2 and _is_int(cell[0]) and isinstance(cell[1], str)}
                  if isinstance(source, dict) and isinstance(source.get("unverified_cells"), list) else set())
    for n in range(1, 21):
        row = levels[str(n)]
        if not isinstance(row, dict) or set(row) != expected_keys:
            problems.append(f"level {n}: keys differ from the class column set")
            continue
        if row["proficiency_bonus"] != proficiency_bonus_for_level(n) or not _is_int(row["proficiency_bonus"]):
            problems.append(f"level {n}: proficiency_bonus does not match the Proficiency Bonus table")
        features = row["features"]
        if not isinstance(features, list) or any(not isinstance(f, str) or not f or f != f.strip() for f in features) \
                or len(set(features)) != len(features):
            problems.append(f"level {n}: features must be a list of distinct non-empty names")
        for column in COLUMNS[class_name]:
            value = row[column]
            if column == "slots":
                if not isinstance(value, dict) or any(k not in {str(i) for i in range(1, MAX_SLOT_LEVEL[class_name] + 1)}
                                                      or not _is_int(v) or v < 1 for k, v in value.items()):
                    problems.append(f"level {n}: slots must map slot levels 1..{MAX_SLOT_LEVEL[class_name]} to positive counts")
            elif column == "pact_slots":
                if not isinstance(value, dict) or set(value) != {"count", "level"} or not all(_is_int(v) and 1 <= v <= 5 for v in value.values()):
                    problems.append(f"level {n}: pact_slots must be {{count, level}} with level 1..5")
            elif value is None:
                if column not in NULLABLE.get(class_name, set()) and (n, column) not in unverified:
                    problems.append(f"level {n}: {column} is null but not an em-dash column or a listed unverified cell")
            elif not _is_int(value) or value < 0:
                problems.append(f"level {n}: {column} must be a non-negative integer")
    for cell in source.get("unverified_cells", []) if isinstance(source, dict) else []:
        if not (isinstance(cell, list) and len(cell) == 2 and _is_int(cell[0]) and isinstance(cell[1], str)
                and levels.get(str(cell[0]), {}).get(cell[1], 0) is None):
            problems.append(f"unverified cell {cell!r} is malformed or the cell is not null")
    return problems
