"""One follow-up and one faction gate. No second adventure authority."""

from __future__ import annotations

from adventure.director import active_count, refresh


def maybe_follow_up(world, quest, *, bindings, rumor, evidence_id, campaign_id=""):
    if quest.get("follow_up_key"):
        return None
    if quest.get("status") not in {"COMPLETED", "FAILED"}:
        return None
    if active_count(world.get("quests", [])) > 1:
        return None
    created = refresh(
        world,
        reason="adventure_completed" if quest["status"] == "COMPLETED" else "adventure_failed",
        trigger=f"follow:{quest['quest_id']}",
        source_id=bindings.get("source_npc_id"),
        bindings=bindings,
        rumor=rumor,
        evidence_id=evidence_id,
        campaign_id=campaign_id,
    )
    if created is None:
        return None
    quest["follow_up_key"] = created["opportunity_key"]
    return created


def faction_gate(world, standing, *, threshold, bindings, rumor, evidence_id, campaign_id=""):
    if type(standing) is not int or standing < threshold:
        return None
    return refresh(
        world,
        reason="aftermath",
        trigger="faction-gate",
        source_id=bindings.get("source_npc_id"),
        bindings=bindings,
        rumor=rumor,
        evidence_id=evidence_id,
        campaign_id=campaign_id,
    )
