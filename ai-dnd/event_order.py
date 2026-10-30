"""Ordering of simultaneous due items (K04).

Items that become due at the SAME timestamp resolve once, in one recorded rule order; the stable event id is the only
technical tie-break inside one rank. An item whose kind has no rank, due at the same timestamp as another item, is an
unresolved conflict: it stops (UnresolvedRuleOrder) instead of depending on call order. Items alone at their timestamp
need no rank.

DEFAULT_RULE_ORDER is a TECHNICAL decision record, not a PHB rule: the 2024 rules fix no order between these
independent moments. Effects that have run out stop applying first, then damage lands, then the death check reads the
resulting state, and only then does regeneration/stabilisation heal. Change it here, in one place.
"""
from __future__ import annotations

DEFAULT_RULE_ORDER: dict[str, int] = {
    "effect_expiry": 0,
    "damage": 1,
    "death": 2,
    "regeneration": 3,
}


class UnresolvedRuleOrder(ValueError):
    """Two items due together have no recorded order between them."""


def require_complete(rule_order: dict[str, int], kinds=("effect_expiry", "damage", "death", "regeneration")) -> None:
    """Refuse an incomplete table up front, before any clock moves."""
    missing = [kind for kind in kinds if kind not in rule_order]
    if missing:
        raise UnresolvedRuleOrder("Rule order table is missing: " + ", ".join(missing))


def order_due_events(events: list[dict], rule_order: dict[str, int]) -> list[dict]:
    by_time: dict = {}
    for item in events:
        by_time.setdefault(item["at"], []).append(item)
    for group in by_time.values():
        if len(group) > 1 and any(item["kind"] not in rule_order for item in group):
            raise UnresolvedRuleOrder(
                "Simultaneous items without a recorded rule order: "
                + ", ".join(sorted(item["event_id"] for item in group if item["kind"] not in rule_order)))
    return sorted(events, key=lambda item: (item["at"], rule_order.get(item["kind"], 0), item["event_id"]))
