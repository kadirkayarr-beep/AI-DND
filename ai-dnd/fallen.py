"""The dead stay where they fell: not people in the scene, but bodies in it."""

from __future__ import annotations

from typing import Any

import living_world


_DOWN = {"dead", "unconscious"}
_WAKES_AFTER = 3600  # the Short Rest a knocked-out creature starts


def here(world: dict[str, Any]) -> list[dict[str, Any]]:
    import world_reactions
    location = world.get("location")
    gone = world_reactions.carried_off(world)
    return [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
            and npc.get("combat_status") in _DOWN and npc.get("location") == location and npc.get("id") not in gone]


def knock_out(session, npc: dict[str, Any]) -> None:
    npc.update(current_hp=1, combat_status="unconscious",
               knocked_out_at=session.world_state.get("campaign_time", {}).get("elapsed_seconds", 0))
    import weapon_attack
    weapon_attack.add_condition(npc, "unconscious")
    import bold_acts
    bold_acts.put_down(session.world_state, npc)
    import game
    import xp
    session._receive_xp_award(xp.award_downed, npc, session.world_state, session.character,
                              person_kind=game.person_fight_kind(npc))


def wake(session) -> None:
    """Whoever was knocked out comes round once the hour is up, hurt and still at 1 HP."""
    now = session.world_state.get("campaign_time", {}).get("elapsed_seconds", 0)
    for npc in session.world_state.get("npcs", []):
        if (isinstance(npc, dict) and npc.get("combat_status") == "unconscious"
                and "knocked_out_at" in npc and now - npc["knocked_out_at"] >= _WAKES_AFTER):
            del npc["knocked_out_at"]
            npc["combat_status"] = "active"
            conditions = npc.get("conditions", [])
            if isinstance(conditions, dict):
                conditions.pop("unconscious", None)
            else:
                npc["conditions"] = [name for name in conditions if name != "unconscious"]


def scene_line(world: dict[str, Any]) -> str:
    """One sentence for a look or an arrival; empty when nobody lies here."""
    bodies = here(world)
    dead = [npc for npc in bodies if npc.get("combat_status") == "dead"]
    out_cold = [npc for npc in bodies if npc.get("combat_status") != "dead"]
    parts = []
    if dead:
        parts.append(f"Yerde {living_world.public_scene_people(dead[:3])} kıpırtısız yatıyor.")
    if out_cold:
        parts.append(f"Yerde {living_world.public_scene_people(out_cold[:3])} baygın yatıyor, nefes alıyor.")
    import world_reactions
    parts.append(world_reactions.scene_marks(world))
    return " ".join(part for part in parts if part)


def addressed_body(session, text: str) -> dict[str, Any] | None:
    """The body a line names, when nobody living answers to those words."""
    normalized = session._normalize_turkish_typos(text)
    down = here(session.world_state)
    bodies = [npc for npc in down
              if session.named_by_sight(npc, normalized)
              or session._entity_reference_in_text(npc.get("name", ""), normalized)]
    awake = [npc for npc in session.active_npcs() if not any(npc is body for body in down)]
    if not bodies and not awake:  # the one being talked to went down and nobody else is here to answer
        focus = (session.world_state.get("flags") or {}).get("active_npc_id")
        bodies = [npc for npc in down if npc.get("id") == focus]
    if not bodies or any(session.named_by_sight(npc, normalized) for npc in awake):
        return None
    return bodies[0]


def silence(npc: dict[str, Any]) -> str:
    who = living_world.public_npc_name(npc)
    if npc.get("combat_status") == "unconscious":
        return f"{who} baygın; sesini duyacak durumda değil."
    return f"{who} yerde kıpırtısız yatıyor; sana cevap verecek biri değil artık."


def named_in(session, text: str, bodies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The body among these that the line calls by name or by how they looked."""
    normalized = session._normalize_turkish_typos(text)
    return next((npc for npc in bodies if session.named_by_sight(npc, normalized)
                 or session._entity_reference_in_text(npc.get("name", ""), normalized)), None)


def named_elsewhere(session, text: str) -> dict[str, Any] | None:
    """A body the line names that lies in some other place."""
    import world_reactions
    world = session.world_state
    gone = world_reactions.carried_off(world)
    return named_in(session, text, [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
                                    and npc.get("combat_status") == "dead"
                                    and (npc.get("location") != world.get("location") or npc.get("id") in gone)])


def lies_elsewhere(world: dict[str, Any], npc: dict[str, Any]) -> str:
    place = world.get("locations", {}).get(npc.get("location"))
    where = place.get("name") if isinstance(place, dict) else None
    who = living_world.public_npc_name(npc)
    import world_reactions
    if npc.get("id") in world_reactions.carried_off(world):
        return f"{who} artık burada değil; cesedini götürmüşler."
    return (f"{who} burada değil; onu {where} içinde bıraktın." if where
            else f"{who} burada değil; onu başka bir yerde bıraktın.")
