"""The dead stay where they fell: not people in the scene, but bodies in it."""

from __future__ import annotations

from typing import Any

import living_world


def here(world: dict[str, Any]) -> list[dict[str, Any]]:
    location = world.get("location")
    return [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
            and npc.get("combat_status") == "dead" and npc.get("location") == location]


def scene_line(world: dict[str, Any]) -> str:
    """One sentence for a look or an arrival; empty when nobody lies here."""
    bodies = here(world)
    if not bodies:
        return ""
    return f"Yerde {living_world.public_scene_people(bodies[:3])} kıpırtısız yatıyor."


def addressed_body(session, text: str) -> dict[str, Any] | None:
    """The body a line names, when nobody living answers to those words."""
    normalized = session._normalize_turkish_typos(text)
    bodies = [npc for npc in here(session.world_state)
              if session.named_by_sight(npc, normalized)
              or session._entity_reference_in_text(npc.get("name", ""), normalized)]
    if not bodies or any(session.named_by_sight(npc, normalized) for npc in session.active_npcs()):
        return None
    return bodies[0]


def silence(npc: dict[str, Any]) -> str:
    return f"{living_world.public_npc_name(npc)} yerde kıpırtısız yatıyor; sana cevap verecek biri değil artık."


def named_in(session, text: str, bodies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The body among these that the line calls by name or by how they looked."""
    normalized = session._normalize_turkish_typos(text)
    return next((npc for npc in bodies if session.named_by_sight(npc, normalized)
                 or session._entity_reference_in_text(npc.get("name", ""), normalized)), None)


def named_elsewhere(session, text: str) -> dict[str, Any] | None:
    """A body the line names that lies in some other place."""
    world = session.world_state
    return named_in(session, text, [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
                                    and npc.get("combat_status") == "dead"
                                    and npc.get("location") != world.get("location")])


def lies_elsewhere(world: dict[str, Any], npc: dict[str, Any]) -> str:
    place = world.get("locations", {}).get(npc.get("location"))
    where = place.get("name") if isinstance(place, dict) else None
    who = living_world.public_npc_name(npc)
    return (f"{who} burada değil; onu {where} içinde bıraktın." if where
            else f"{who} burada değil; onu başka bir yerde bıraktın.")
