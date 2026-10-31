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
