"""Read-only request guards for the existing Python combat scheduler."""

import re


class CombatRequestError(ValueError):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def is_attack_decision(session, message):
    text = session._normalize_turkish_typos(message)
    return (session._has_explicit_attack_verb(message)
            and not session._is_explicitly_negated_attack(message)
            and not re.search(r"\b(?:tehdit|gozdagi|varsay|saldirsam)\w*\b", text)
            and not text.rstrip().endswith("?"))


def validate_request(session, message, target_id=None, *, combat_id=None,
                     combat_round=None, combat_turn_index=None):
    """Client context is an optimistic precondition, never combat authority."""
    world = session.world_state
    combat = world.get("combat", {})
    if combat_id is not None and (
        not combat.get("active") or combat.get("combat_id") != combat_id
        or combat.get("round") != combat_round
        or combat.get("current_turn_index") != combat_turn_index
    ):
        raise CombatRequestError("stale_combat", "Combat or turn context is stale.")
    attack = is_attack_decision(session, message)
    if attack and session.character.get("current_hp", 0) > 0:
        if not session.find_weapon_in_inventory("Kılıç")[0]:
            raise CombatRequestError("no_weapon", "No valid weapon is available.", 400)
        text = session._normalize_turkish_typos(message)
        targets = [n for n in world.get("npcs", []) if n.get("location") == world.get("location") and (
            n.get("id") == target_id if target_id is not None else
            session._entity_reference_in_text(n.get("name", ""), text)
            or session._entity_reference_in_text(n.get("role", ""), text)
        )]
        if not targets and target_id is None and re.search(
            r"\b(?:o adam|o kadin|ona|ondan|onunla|kendisine)\b", text
        ):
            available = session.active_npcs()
            flags = world.get("flags", {})
            reference = flags.get("active_npc_id") or flags.get("last_npc_id")
            referenced = [n for n in available if n.get("id") == reference]
            targets = referenced if referenced else available
        if len(targets) != 1 or targets[0].get("combat_status", "active") != "active" or targets[0].get("current_hp", 1) <= 0:
            raise CombatRequestError("invalid_combat_target", "Select one valid local target.", 400)
        if combat.get("active") and targets[0]["id"] not in combat["participants"]:
            raise CombatRequestError("invalid_combat_target", "Target is not a participant.", 400)
    if combat.get("active"):
        session._validate_combat_v3_payload(combat)
        if attack and session.character.get("current_hp", 0) > 0:
            import action_economy
            if combat["current_actor_id"] != "player":
                raise CombatRequestError("out_of_turn", "It is not the player's action turn.")
        # Also validate a selected target on an NPC-turn pulse; never run a
        # real automatic turn on behalf of a forged target request.
        if target_id is not None:
            npc = next((n for n in world.get("npcs", []) if n.get("id") == target_id), None)
            if (not npc or target_id not in combat["participants"]
                or npc.get("location") != world.get("location")
                or npc.get("combat_status", "active") != "active"
                or npc.get("current_hp", 1) <= 0):
                raise CombatRequestError("invalid_combat_target", "Target is not an active local participant.", 400)
        text = session._normalize_turkish_typos(message)
        if re.search(r"\b(?:gidiyorum|gitmek|giriyorum|yolculu|seyahat)", text):
            raise CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)