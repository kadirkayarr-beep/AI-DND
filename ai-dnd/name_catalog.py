"""Names a new campaign draws from, read from content/world/catalog/name_pools.json.

A campaign is marked once when it is created; a save without the mark keeps the
pool it always had. Every name is drawn from the campaign seed and stored on its
record, so it is never drawn again. A name gives a person or a place nothing else:
no history, no knowledge, no job. Only the first name of a person is used, because
people are matched and spoken of by one word; surnames stay in the file unused.

Which place template fits which kind is an explicit table in mapping.json. A kind
with no table, or a name that would read as something else, falls back to the
caller's own "person name + word" form.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

VERSION = 1
CATALOG_DIR = Path(__file__).resolve().parents[1] / "content" / "world" / "catalog"
_LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _pools() -> dict[str, Any]:
    try:
        pools = json.loads((CATALOG_DIR / "name_pools.json").read_text(encoding="utf-8"))
        mapping = json.loads((CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOG.warning("The name catalog could not be read.")
        return {}
    return {"pools": pools, "names": mapping.get("names") or {}}


def adopt(world: dict[str, Any]) -> None:
    """Mark a campaign being created. Never called for one already saved."""
    import living_world
    living_world.ensure_scene_state(world)["name_pool"] = VERSION


def in_use(world: dict[str, Any]) -> bool:
    state = world.get("scene_state")
    return isinstance(state, dict) and state.get("name_pool") == VERSION


@lru_cache(maxsize=1)
def people() -> tuple[str, ...]:
    pools = _pools().get("pools") or {}
    return tuple(p["ad"] for p in pools.get("kişiler", ()) if p.get("adult") is True and p.get("ad"))


def place_templates() -> dict[str, list[str]]:
    """Kind -> filled-in template texts, through the explicit id table only."""
    data = _pools()
    pools = data.get("pools") or {}
    by_id = {t["template_id"]: t["kalıp"] for key in ("han_kalıpları", "dükkân_kalıpları") for t in pools.get(key, ())}
    table = (data.get("names") or {}).get("place_templates") or {}
    return {kind: [by_id[i] for i in ids if i in by_id] for kind, ids in table.items()}


def _rank(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("\x00".join(map(str, parts)).encode("utf-8")).digest()[:4], "big")


def _fill(template: str, slots: dict[str, Any], seed: str, identity: str, attempt: int) -> str:
    """Identity carries the kind, so two trades of one town do not share the same word."""
    text = template
    for slot, entry in slots.items():
        marker = "{" + slot + "}"
        if marker in text:
            values = entry["örnek_değerler"]
            text = text.replace(marker, values[_rank(seed, identity, slot, attempt) % len(values)])
    return text


def _reads_as_something_else(name: str, kind: str) -> bool:
    import living_world
    import local_places
    avoid = tuple((_pools().get("names") or {}).get("place_name_avoid") or ())
    stems = tuple(stem for other, spec in local_places.PLACE_KINDS.items() if other != kind for stem in spec["stems"])
    return any(word.startswith(avoid + stems) for word in living_world.normalize_text(name).split())


def place_name(world: dict[str, Any], kind: str, identity: str) -> str | None:
    """A free name for this kind of place, or None when the catalog has none to give."""
    import living_world
    seed = living_world._campaign_seed(world)
    templates = place_templates().get(kind)
    if not seed or not in_use(world) or not templates:
        return None
    slots = (_pools().get("pools") or {}).get("yuva_sözlüğü") or {}
    taken = {living_world.normalize_text(place.get("name")) for place in (world.get("locations") or {}).values()
             if isinstance(place, dict)}
    start = _rank(seed, identity, kind)
    for attempt in range(len(templates) * 6):
        name = _fill(templates[(start + attempt) % len(templates)], slots, seed, f"{identity}:{kind}", attempt)
        if living_world.normalize_text(name) not in taken and not _reads_as_something_else(name, kind):
            return name
    return None
