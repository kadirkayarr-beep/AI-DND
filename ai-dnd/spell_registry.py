"""C09: one dispatch boundary for spells over the existing bounded resolvers in `spell_scope` (no spell is re-implemented here).

`cast_spell(spell_id, context, slot_level, choice)` returns the same delta shape as the other rule kernels:
`{"status": "applied" | "rejected" | "unsupported", "spell_id", "slot_level", "reason", "result", "changes", "effects_pending"}`.
"applied" means an existing resolver ran and the owner's own result is in `result`. A spell that is in the PHB manifest but has
no resolver is "unsupported" with an explicit development reason: nothing is rolled, spent or narrated as success. The 391-spell
catalog is C05's; this core only routes. (The plan names `spells/registry.py`; `spells.py` already exists as a module, so a
package of that name would shadow it. The flat name `spell_registry` is used instead.)
"""
from __future__ import annotations

import functools
from typing import Any

import spell_scope
from capabilities import manifest_rows
from combat_lifecycle import CombatRequestError


@functools.lru_cache(maxsize=1)
def _manifest_spells() -> frozenset[str]:
    # category filter: "Shield" is both a spell and an equipment row
    return frozenset(row["name"] for row in manifest_rows() if row["category"] == "spell")


def resolvers() -> dict[str, int]:
    """Spells that have a real resolver, with their spell level (0 = cantrip)."""
    return {name: data[0] for name, data in spell_scope.CATALOG.items()}


def spell_state(spell_id: Any) -> str:
    """"resolver" (real resolver), "catalog_only" (in the PHB manifest, nothing implemented) or "unknown"."""
    if spell_id in spell_scope.CATALOG:
        return "resolver"
    return "catalog_only" if spell_id in _manifest_spells() else "unknown"


def _result(status: str, spell_id: Any, slot_level: int | None, reason: str | None = None, result: dict[str, Any] | None = None,
            changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "spell_id": spell_id, "slot_level": slot_level, "reason": reason, "result": result,
            "changes": changes or [], "effects_pending": []}


def _changes(level: int, result: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if level:
        changes.append({"kind": "spell_slot", "level": level, "spent": 1})
    if result.get("damage"):
        changes.append({"kind": "damage", "target_id": result["target_id"], "amount": result["damage"],
                        "damage_type": result.get("damage_type")})
    if result.get("healing"):
        changes.append({"kind": "healing", "target_id": result["target_id"], "amount": result["healing"],
                        "heal_source": result.get("heal_source")})
    if result.get("hit") is False:  # a miss / successful save is an explicit receipt, not an empty list
        changes.append({"kind": "no_effect", "target_id": result["target_id"], "reason": "miss_or_save_succeeded"})
    return changes


def cast_spell(spell_id: Any, context: dict[str, Any], slot_level: int | None, choice: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the existing resolver. `context["session"]` is the owner's session; `choice["target_id"]` the explicit target."""
    state = spell_state(spell_id) if isinstance(spell_id, str) else "unknown"
    if state == "unknown":
        return _result("unsupported", spell_id, None, "unknown_spell")
    if state == "catalog_only":
        return _result("unsupported", spell_id, None, "spell_resolver_missing")
    level = spell_scope.CATALOG[spell_id][0]
    reported = level or None  # a cantrip has no slot
    if spell_id == "Magic Missile" and type(slot_level) is int and slot_level in (2, 3):
        reported = slot_level
    session = context.get("session") if isinstance(context, dict) else None
    if session is None:
        return _result("rejected", spell_id, reported, "session_required")
    target_id = choice.get("target_id") if isinstance(choice, dict) else None
    try:
        outcome = spell_scope.cast(session, spell_id, target_id, slot_level, metamagic=choice.get("metamagic") if isinstance(choice, dict) else None)
    except CombatRequestError as exc:
        return _result("rejected", spell_id, reported, exc.code)
    except ValueError:  # dead/unconscious player, invalid saved spell state: the owner restored its state (initiative.atomic)
        return _result("rejected", spell_id, reported, "invalid_spell_state")
    actual_level = outcome["slot_level"]
    return _result("applied", spell_id, actual_level or None, None, outcome, _changes(actual_level, outcome))
