"""Python director. It returns bindings, never prose, and never invents entities."""

from __future__ import annotations

import hashlib

from adventure import templates
from adventure.transitions import TransitionError, transition

REFRESH_REASONS = frozenset({
    "enter_settlement",
    "npc_conversation",
    "ask_rumors",
    "aftermath",
    "adventure_completed",
    "adventure_failed",
    "meaningful_discovery",
})
PACING = frozenset({"CALM", "EXPLORATION", "TENSION", "DANGER", "AFTERMATH"})
CATEGORIES = frozenset({
    "combat", "social", "exploration", "investigation", "travel", "dungeon",
})
MAX_OPEN = 3
MAX_ACTIVE = 1


def opportunity_key(campaign_id, template_id, trigger, source_id, binding_ids, evidence_id):
    parts = [
        campaign_id or "",
        template_id,
        trigger,
        source_id or "",
        ",".join(sorted(binding_ids)),
        evidence_id or "",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"opportunity:{digest}"


def pacing_for(world):
    recent = _recent(world)
    if not recent:
        return "CALM"
    if recent[-1] == "combat":
        return "DANGER"
    if recent[-1] == "dungeon":
        return "TENSION"
    if recent[-1] == "investigation":
        return "EXPLORATION"
    if recent[-1] == "social":
        return "AFTERMATH"
    return "EXPLORATION"


def note_category(world, category):
    if category not in CATEGORIES:
        return
    recent = world.setdefault("adventure_recent_categories", [])
    if not isinstance(recent, list):
        world["adventure_recent_categories"] = []
        recent = world["adventure_recent_categories"]
    recent.append(category)
    del recent[:-6]


def refresh(world, *, reason, trigger, source_id, bindings, rumor, evidence_id, campaign_id=""):
    """Create at most one missing opportunity for this evidence boundary."""
    if reason not in REFRESH_REASONS:
        return None
    if not _entities_exist(world, bindings):
        return None
    template_id = _choose_template(world)
    key = opportunity_key(
        campaign_id,
        template_id,
        trigger,
        source_id,
        _binding_identity(bindings),
        evidence_id,
    )
    quests = world.setdefault("quests", [])
    if any(isinstance(item, dict) and item.get("opportunity_key") == key for item in quests):
        return None
    if any(
        isinstance(item, dict) and item.get("creation_evidence") == evidence_id
        for item in quests
    ):
        return None
    if _open_count(quests) >= MAX_OPEN:
        return None
    quest_id = f"adv.{key.removeprefix('opportunity:')}"
    record = templates.instantiate(
        template_id,
        quest_id=quest_id,
        turn=_turn(world),
        opportunity_key=key,
        creation_evidence=evidence_id,
        bindings=bindings,
        rumor=rumor,
    )
    quests.append(record)
    return record


def discover(world, quest_id):
    """The player hears the rumor. Hidden offers stay out of the journal."""
    quest = _quest(world, quest_id)
    if quest.get("status") == "DISCOVERED":
        return quest
    turn = _turn(world)
    if turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    updated = transition(quest, "DISCOVERED", turn)
    quest.clear()
    quest.update(updated)
    return quest


def _choose_template(world):
    """Recent combat shifts the next unused template. The mix is not stored as canon."""
    combat_heavy = _recent(world).count("combat") >= 2
    order = ("BOUNTY", "MISSING_PERSON") if combat_heavy else ("MISSING_PERSON", "BOUNTY")
    used = _used(world)
    for template_id in order:
        if template_id not in used:
            return template_id
    return order[-1]


def _used(world):
    return {
        item.get("template_id")
        for item in world.get("quests", [])
        if isinstance(item, dict)
    }


def _open_count(quests):
    return sum(
        1 for item in quests
        if isinstance(item, dict)
        and item.get("record_kind") == "dynamic"
        and item.get("status") in {"AVAILABLE", "DISCOVERED"}
    )


def _quest(world, quest_id):
    quest = next(
        (
            item for item in world.get("quests", [])
            if isinstance(item, dict) and item.get("quest_id") == quest_id
        ),
        None,
    )
    if quest is None or quest.get("record_kind") != "dynamic":
        raise TransitionError("Macera yok.")
    return quest


def maybe_refresh_on_arrival(world, before_world, campaign_id=""):
    """Settlement entry is a refresh point. An ordinary turn is not."""
    if not isinstance(world, dict) or not isinstance(before_world, dict):
        return None
    current = world.get("location")
    if not isinstance(current, str) or before_world.get("location") == current:
        return None
    import living_world

    if living_world.scene_kind(world, current) not in {"tavern", "city"}:
        return None
    present = [
        npc for npc in world.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("location") == current
        and isinstance(npc.get("id"), str)
    ]
    if len(present) < 2:
        return None
    source, target = present[0], present[1]
    label = target.get("name") if isinstance(target.get("name"), str) and target.get("name").strip() else "biri"
    return refresh(
        world,
        reason="enter_settlement",
        trigger="arrival",
        source_id=source["id"],
        bindings=templates.prepared_bindings(
            source_npc_id=source["id"],
            target_npc_id=target["id"],
            location_ids=[current],
        ),
        rumor=f"{label} hakkında bir söylenti dolaşıyor.",
        evidence_id=f"arrival:{current}:{source['id']}:{target['id']}",
        campaign_id=campaign_id or str(world.get("campaign_id") or ""),
    )


def abandon_dynamic(world, quest_id):
    """Leave a heard or accepted adventure. Hidden offers are not cancelled."""
    quest = _quest(world, quest_id)
    if quest.get("status") in {"ABANDONED", "COMPLETED", "FAILED"}:
        return quest
    if quest.get("status") not in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
        raise TransitionError("Geçersiz macera geçişi.")
    turn = _turn(world)
    if turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    updated = transition(quest, "ABANDONED", turn, outcome="abandoned")
    quest.clear()
    quest.update(updated)
    return quest


def accept_dynamic(world, quest_id):
    quest = _quest(world, quest_id)
    if quest.get("status") == "ACTIVE":
        return quest
    if active_count(world.get("quests", [])) >= MAX_ACTIVE:
        raise TransitionError("Zaten süren bir macera var.")
    turn = _turn(world)
    if turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    updated = transition(quest, "ACTIVE", turn)
    quest.clear()
    quest.update(updated)
    return quest


def active_count(quests):
    return sum(
        1 for item in quests
        if isinstance(item, dict)
        and item.get("record_kind") == "dynamic"
        and item.get("status") == "ACTIVE"
    )


def _entities_exist(world, bindings):
    if not isinstance(bindings, dict):
        return False
    npcs = {npc.get("id") for npc in world.get("npcs", []) if isinstance(npc, dict)}
    locations = set(world.get("locations", {}))
    for key in ("source_npc_id", "target_npc_id"):
        identity = bindings.get(key)
        if identity is not None and identity not in npcs:
            return False
    for identity in bindings.get("location_ids", []):
        if identity not in locations:
            return False
    return True


def _binding_identity(bindings):
    values = []
    for key in ("source_npc_id", "target_npc_id"):
        if isinstance(bindings.get(key), str):
            values.append(bindings[key])
    values.extend(item for item in bindings.get("location_ids", []) if isinstance(item, str))
    return values


def _recent(world):
    recent = world.get("adventure_recent_categories", [])
    if not isinstance(recent, list):
        return []
    return [item for item in recent if item in CATEGORIES]


def _turn(world):
    turn = world.get("flags", {}).get("turn_index", 0)
    return turn if isinstance(turn, int) and turn >= 0 else 0
