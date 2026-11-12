"""Turkish names for spells and items: one table, content/names/tr_names.json.

Ids stay English everywhere (saves, engine, rules). The table only changes what a
player reads and what a player may type. A name that is not in the table falls
back to the English id, never to a guess.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

TABLE_PATH = Path(__file__).resolve().parents[1] / "content" / "names" / "tr_names.json"
KINDS = ("spells", "items")
_FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
                       "ö": "o", "Ö": "o", "ç": "c", "Ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(text: Any) -> str:
    """Lower case, no Turkish diacritics, single spaces: 'Sihirli  FÜZE' == 'sihirli fuze'."""
    return " ".join(str(text).replace("\u0307", "").translate(_FOLD).casefold().split())


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _reverse() -> dict[str, dict[str, str]]:
    data = table()
    result: dict[str, dict[str, str]] = {kind: {} for kind in KINDS}
    for kind in KINDS:
        for item_id, name in data[kind].items():
            result[kind][fold(name)] = item_id
            result[kind][fold(item_id)] = item_id
    for item_id, names in data.get("aliases", {}).items():
        for kind in KINDS:
            if item_id in data[kind]:
                for name in names:
                    result[kind].setdefault(fold(name), item_id)
    return result


def to_tr(item_id: str, kind: str | None = None) -> str:
    """Turkish name for an engine id; the id itself when the table has none."""
    data = table()
    for k in (kind,) if kind else KINDS:
        name = data[k].get(item_id)
        if name:
            return name
    return item_id


def to_id(text: Any, kind: str | None = None) -> str | None:
    """Engine id for a Turkish (or English) name the player typed; None when unknown."""
    key = fold(text)
    if not key:
        return None
    for k in (kind,) if kind else KINDS:
        found = _reverse()[k].get(key)
        if found:
            return found
    return None


def spellings_for(item_ids, kind: str = "spells") -> dict[str, str]:
    """{player spelling: id} for the given ids: the Turkish name and aliases, with and without diacritics."""
    data = table()
    result: dict[str, str] = {}
    for item_id in item_ids:
        for name in (data[kind].get(item_id), *data.get("aliases", {}).get(item_id, ())):
            if name:
                result[name.replace("̇", "").casefold()] = item_id
                result[fold(name)] = item_id
    return result


def narrator_line(item_ids, kind: str | None = None) -> str:
    """One line for the narrator prompt: use the Turkish name, keep the English id for the engine."""
    pairs = [f"{item_id} = {to_tr(item_id, kind)}" for item_id in item_ids if to_tr(item_id, kind) != item_id]
    if not pairs:
        return ""
    return "Büyü ve eşya adlarını anlatıda Türkçe yaz (motor kimliği İngilizce kalır): " + "; ".join(pairs) + "."


def narrator_note(spell_ids, item_names) -> str:
    """The narrator prompt line for what this character knows and carries (item names may be Turkish or English)."""
    item_ids = [found for found in (to_id(name, "items") for name in item_names) if found]
    parts = [narrator_line(spell_ids, "spells"), narrator_line(item_ids, "items")]
    return " ".join(part for part in parts if part)


def export_json() -> str:
    """The table for the interface: {'spells': {id: tr}, 'items': {id: tr}, 'aliases': {id: [...]}}."""
    data = table()
    return json.dumps({k: data[k] for k in (*KINDS, "aliases")}, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    print(export_json())
