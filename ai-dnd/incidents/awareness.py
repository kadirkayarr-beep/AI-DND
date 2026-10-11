"""What the player knows about an incident. Separate from its lifecycle.

Evidence lives in world["player_knowledge"] as ``incident:{incident_id}:{key}``
strings, the list the Phase 7 knowledge facade already reads. A guess in
player text never reaches this module; only Python check results do.
"""

from __future__ import annotations

PREFIX = "incident:"
NOTICED = "noticed"
REVEAL_SKILLS = frozenset({"perception", "investigation", "insight"})


def entry(incident_id, key):
    return f"{PREFIX}{incident_id}:{key}"


def _knowledge(world):
    knowledge = world.setdefault("player_knowledge", [])
    if not isinstance(knowledge, list):
        raise ValueError("Oyuncu bilgisi geçersiz.")
    return knowledge


def _add(world, value):
    knowledge = _knowledge(world)
    if value not in knowledge:
        knowledge.append(value)


def noticed(world, incident_id):
    return entry(incident_id, NOTICED) in world.get("player_knowledge", [])


def known_fact_ids(world, incident_id):
    marker = f"{PREFIX}{incident_id}:"
    return [
        item[len(marker):] for item in world.get("player_knowledge", [])
        if isinstance(item, str) and item.startswith(marker) and item[len(marker):] != NOTICED
    ]


def witness(world, record):
    """The player is in the scene: they notice it and see its surface facts."""
    _add(world, entry(record["incident_id"], NOTICED))
    hidden = set(record["hidden_fact_ids"])
    for fact_id in record["details"]["facts"]:
        if fact_id not in hidden:
            _add(world, entry(record["incident_id"], fact_id))


def reveal(world, record, fact_id, *, evidence):
    """Reveal one hidden fact on Python evidence. Returns True when it is new."""
    if fact_id not in record["details"]["facts"]:
        return False
    if not _valid_evidence(evidence):
        return False
    value = entry(record["incident_id"], fact_id)
    if value in world.get("player_knowledge", []):
        return False
    _add(world, entry(record["incident_id"], NOTICED))
    _add(world, value)
    return True


def _valid_evidence(evidence):
    if not isinstance(evidence, dict):
        return False
    if evidence.get("kind") == "check":
        return (
            evidence.get("success") is True
            and isinstance(evidence.get("skill"), str)
            and evidence["skill"].casefold() in REVEAL_SKILLS
        )
    return evidence.get("kind") == "introduction" and isinstance(evidence.get("npc_id"), str)


def reveal_from_check(world, action_result):
    """A successful Perception, Investigation, or Insight check here reveals
    the first hidden fact of the oldest open incident at this location."""
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return None
    if action_result.get("action") not in ("skill_check", "adventure_check"):
        return None
    evidence = {"kind": "check", "success": True, "skill": action_result.get("skill")}
    if not _valid_evidence(evidence):
        return None
    here = world.get("location")
    rows = sorted(
        (row for row in world.get("incidents", {}).values()
         if row.get("location_id") == here and row.get("lifecycle") in ("PRESENT", "ENGAGED")),
        key=lambda row: (row["created_clock"], row["incident_id"]),
    )
    for row in rows:
        known = set(known_fact_ids(world, row["incident_id"]))
        for fact_id in row["hidden_fact_ids"]:
            if fact_id not in known and reveal(world, row, fact_id, evidence=evidence):
                return entry(row["incident_id"], fact_id)
    return None
