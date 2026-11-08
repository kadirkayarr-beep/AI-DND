"""Turn the authored thread catalog into world thread kinds.

The catalog (content/world/catalog/thread_templates.json) is a richer source than
the starter file and is not an import format. This adapter reads only the public
line, the owner terms, the place tags and the offer window, plus a refusal or
expiry outcome once its bookkeeping words are off and every slot in it is bound;
every other field (rewards, private conditions) stays out of play.
content/world/catalog/mapping.json holds the explicit decisions: which catalog
place tag is which engine place kind (no match means the tag is not used, it is
never guessed), and the pay and day ranges, because the catalog gives none.

A template with a slot this adapter cannot fill from a real record is left out.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import local_places
import tr_case

CATALOG_DIR = Path(__file__).resolve().parents[1] / "content" / "world" / "catalog"
_LOG = logging.getLogger(__name__)


def place_kinds(tags: Any, mapping: dict[str, Any]) -> list[str]:
    """Engine place kinds for catalog tags, through the explicit table only."""
    found: list[str] = []
    table = mapping.get("place_tags", {})
    for tag in tags if isinstance(tags, list) else ():
        for kind in table.get(tag, ()):
            if kind in local_places.PLACE_KINDS and kind not in found:
                found.append(kind)
    return found


def _topic(public: str) -> str:
    """The public line as a plain clause, for the slot that restates what the matter is."""
    return public.rstrip(" .")


def _package(public: str) -> str | None:
    """'{place_name} üzerinden iade eşyası gönderilecek.' -> 'İade eşyası'."""
    found = re.fullmatch(r"\{place_name\} üzerinden (.+) gönderilecek\.", public)
    if not found:
        return None
    text = found.group(1)
    return tr_case.upper_first(text)


def _owner_line(item: dict[str, Any]) -> str | None:
    line = str(item.get("owner_terms_template") or "")
    public = str(item.get("public_line_template") or "")
    package = _package(public) if "{delivery_package}" in line else ""
    if package is None:
        return None
    slots = {
        "{work_summary}": _topic(public).replace("{place_name}", "{place}"),
        "{local_issue_summary}": _topic(public).replace("{place_name}", "{place}"),
        "{delivery_package}": package,
        "{recipient_name}": "{recipient}",
        "{contact_name}": "{recipient}",
        "{delivery_location}": "{target}",
        "{work_days}": "{days}",
        "{eligibility_condition}": "",  # no real requirement exists yet, so none is spoken
    }
    for slot, value in slots.items():
        line = line.replace(slot, value)
    line = line.strip()
    return None if set(re.findall(r"\{(\w+)\}", line)) - {"place", "recipient", "target", "pay", "days"} else line


_EXPIRY_PREFIX = re.compile(r"^Yalnız kabul edilmemiş ipin teklif vadesi dolduğunda, motorun doğruladığı yerel gelişme önerisi:\s*")
_REFUSAL_TAIL = re.compile(r"[;,]\s*(?:notun ulaştırılmaması )?oyuncu\w*\b.*$")
_RULE_WORDS = ("oyuncu", "motor", "otomatik", "varsay", "sayılmaz", "oluşmaz", "kendiliğinden")  # the engine's bookkeeping, not speech


def _outcome_line(text: Any, *, expiry: bool = False) -> str | None:
    """A consequence as the owner could say it, or None when it only speaks to the engine."""
    line = str(text or "").strip()
    line = _EXPIRY_PREFIX.sub("", line) if expiry else _REFUSAL_TAIL.sub(".", line)
    kept = [part.strip() for part in line.rstrip(" .").split(";")
            if not any(word in part.casefold() for word in _RULE_WORDS)]
    line = "; ".join(kept)
    return f"{line}." if line and "{" not in line else None


def _item_noun(owner: str, public: str) -> str | None:
    if "{delivery_package}" not in owner:
        return None
    package = _package(public)
    return package.casefold().replace("i̇", "i") if package else None


def adapt(item: Any, mapping: dict[str, Any]) -> dict[str, Any] | None:
    """One engine template, or None when the catalog record cannot be bound honestly."""
    if not isinstance(item, dict) or item.get("type") not in {"hiring", "errand", "trouble"}:
        return None
    kinds = place_kinds(item.get("location_types"), mapping)
    public = str(item.get("public_line_template") or "")
    owner = _owner_line(item)
    hours = item.get("deadline_game_hours")
    if not kinds or not public or owner is None or type(hours) is not int or hours <= 0:
        return None
    hours *= int(mapping.get("offer_hours_scale", 1))
    template = {
        "id": str(item.get("id")), "type": item["type"], "place_kinds": kinds,
        "public_lines": [public.replace("{place_name}", "{place}")], "owner_lines": [owner],
        "offer_hours": [hours, hours],
    }
    if item.get("requester_group"):
        template["group"] = str(item["requester_group"])
    if item.get("requester_group"):
        template["group"] = str(item["requester_group"])
    if "{recipient}" in owner or "{target}" in owner:
        template["target_place_kinds"] = list(mapping.get("target_place_kinds", ()))
    if "{pay}" in owner:
        template["pay"] = list(mapping["pay"][item["type"]])
    if "{days}" in owner:
        template["work_days"] = list(mapping["work_days"])
    if item["type"] == "hiring":
        template["pay_basis"] = "total"
    noun = _item_noun(str(item.get("owner_terms_template") or ""), public)
    if noun:
        template["item_noun"] = noun
    lines = {"declined": _outcome_line(item.get("refusal_consequence_template")),
             "expired": _outcome_line(item.get("expiry_consequence_template"), expiry=True)}
    lines = {key: value for key, value in lines.items() if value}
    if lines:
        template["status_lines"] = lines
    return template


def load() -> list[dict[str, Any]]:
    """Every usable catalog template; an absent or broken catalog simply adds none."""
    try:
        mapping = json.loads((CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))
        data = json.loads((CATALOG_DIR / "thread_templates.json").read_text(encoding="utf-8"))
        return [template for item in data.get("items", []) if (template := adapt(item, mapping))]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        _LOG.warning("The thread catalog could not be read.")
        return []
