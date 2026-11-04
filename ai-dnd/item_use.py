"""Consumption reads exact catalog names; possession changes have one owner."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import equipment_economy


@lru_cache(maxsize=1)
def _catalog():
    return json.loads((Path(__file__).resolve().parent.parent / "content" / "items" / "item_use.json").read_text(encoding="utf-8"))


def kind_of(item: Mapping | str) -> Literal["food", "drink"] | None:
    name = item.get("name") if isinstance(item, Mapping) else item
    return _catalog()["kinds"].get(name) if isinstance(name, str) else None


@dataclass(frozen=True)
class ConsumeResult:
    status: Literal["consumed", "not_consumable", "not_in_bag", "in_combat"]
    name: str | None
    note: str | None


def consume(world: dict, item_id: str) -> ConsumeResult:
    if (world.get("combat") or {}).get("active"):
        return ConsumeResult("in_combat", None, None)
    item = next((row for row in world.get("inventory", [])
                 if isinstance(row, dict) and row.get("item_id") == item_id), None)
    if item is None:
        return ConsumeResult("not_in_bag", None, None)
    kind = kind_of(item)
    if kind is None:
        return ConsumeResult("not_consumable", item.get("name"), None)
    removed = equipment_economy.remove_item(world, item_id)
    name = removed["name"]
    return ConsumeResult("consumed", name, f"{name} {'içildi' if kind == 'drink' else 'yendi'}")

def _unseeded_packs(world):
    for item in world.get("inventory", []):
        if isinstance(item, Mapping) and item.get("ammo_seeded_v1"):
            continue
        name = item.get("name") if isinstance(item, Mapping) else item
        pack = _catalog()["ammunition"].get(name) if isinstance(name, str) else None
        if pack is not None:
            yield item, pack


def ammo_available(world: Mapping, ammo_type: str) -> int:
    return world.get("ammunition", {}).get(ammo_type, 0) + sum(
        pack["count"] for _, pack in _unseeded_packs(world) if pack["type"] == ammo_type)


def ensure_ammunition(world: dict) -> dict[str, int]:
    equipment_economy.materialize(world)
    ammunition = world.setdefault("ammunition", {})
    for item, pack in _unseeded_packs(world):
        kind = pack["type"]
        ammunition[kind] = ammunition.get(kind, 0) + pack["count"]
        item["ammo_seeded_v1"] = True
    return ammunition


def ammo_note(world: Mapping) -> str:
    return " ".join(f"({label}: {count})" for kind, label in (("arrow", "ok"), ("bolt", "cıvata"))
                    if (count := ammo_available(world, kind)) > 0)