"""Effect target eligibility (K01): one owner decides who an area effect can reach.

A target must be a canonical creature of the actor's current scene, active, a combat participant while combat is open,
and inside the rule's own range. The range comes from the effect's rule data (`EffectSpec`), never from a universal
default; an unknown distance excludes the target instead of being guessed. Spatial facts come from weapon_attack.pair.
"""
from __future__ import annotations

from dataclasses import dataclass

from combat_lifecycle import CombatRequestError
import weapon_attack


@dataclass(frozen=True)
class EffectSpec:
    effect_id: str
    range_ft: int | None  # None: the rule carries no range requirement of its own
    source_ref: str
    excludes_allies: bool = False  # rule text "other than your allies"

    def __post_init__(self):
        if not self.effect_id or not self.source_ref:
            raise ValueError("An effect spec needs an id and the rule source it comes from.")
        if self.range_ft is not None and (type(self.range_ft) is not int or self.range_ft < 0):
            raise ValueError("An effect range must be a non-negative integer or None.")


def eligible_effect_targets(session: object, actor_id: str, spec: EffectSpec) -> list[str]:
    world = session.world_state
    combat = world.get("combat", {})
    participants = combat.get("participants", []) if combat.get("active") else None
    actor_side = "party" if actor_id == "player" else weapon_attack.actor_data(session, actor_id).get("combat_side", "enemy")
    companions = {row.get("npc_id") for row in world.get("companions", []) if isinstance(row, dict)} if actor_id == "player" else set()
    targets = []
    for npc in world.get("npcs", []):
        target_id = npc.get("id") if isinstance(npc, dict) else None
        if not isinstance(target_id, str) or target_id == actor_id:
            continue
        if npc.get("location") != world.get("location") or npc.get("combat_status") != "active":
            continue
        if participants is not None and target_id not in participants:
            continue
        if spec.excludes_allies and (npc.get("combat_side", "enemy") == actor_side or target_id in companions):
            continue
        if spec.range_ft is not None:
            try:
                distance = weapon_attack.pair(session, actor_id, target_id)["distance_ft"]
            except CombatRequestError:
                continue  # unknown distance: not reached, never invented
            if distance > spec.range_ft:
                continue
        targets.append(target_id)
    return targets
