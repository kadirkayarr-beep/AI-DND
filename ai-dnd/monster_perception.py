"""Small authoritative perception adapter, not a new stealth/world engine."""
import copy

import weapon_attack as attacks
import action_economy as economy
from combat_lifecycle import CombatRequestError


def relationship(session, actor, target):
    a, b = attacks.actor_data(session, actor), attacks.actor_data(session, target)
    explicit = a.get("combat_relationships", {}).get(target)
    if explicit in {"enemy", "ally", "neutral"}:
        return explicit
    af, bf = a.get("faction"), b.get("faction")
    if af and bf:
        if af == bf:
            return "ally"
        return a.get("faction_relationships", {}).get(bf, "neutral")
    # Only explicit hostility/encounter opposition supports the legacy side.
    combat = session.world_state["combat"]
    def hostile(identity, data):
        return identity != "player" and (data.get("hostile") is True
            or data.get("combat_role") in {"enemy", "hostile"} or combat.get("target_id") == identity)
    ah, bh = hostile(actor, a), hostile(target, b)
    if actor == "player":
        return "enemy" if bh else "neutral"
    if target == "player":
        return "enemy" if ah else "neutral"
    return "ally" if ah and bh else "neutral"


def snapshot(session, actor, memory):
    """Never pass exact target HP, secret defenses, invisible coordinates to AI."""
    a = attacks.actor_data(session, actor)
    acond = attacks.conditions(session, actor, a)
    facts = session.world_state.get("monster_perception", {}).get(actor, {})
    targets, allies = [], []
    for target in session.world_state["combat"]["participants"][:128]:
        if target == actor:
            continue
        data = attacks.actor_data(session, target)
        fact = facts.get(target, {})
        if not isinstance(fact, dict):
            continue
        tcond = attacks.conditions(session, target, data)
        try:
            spatial = attacks.pair(session, actor, target)
        except CombatRequestError as error:
            if getattr(error, "code", None) != "distance_unknown":
                raise
            spatial = {}
        distance = spatial.get("distance_ft")
        visible = (fact.get("visible") is True or spatial.get("attacker_sees_target") is True)
        visible &= "blinded" not in acond and "invisible" not in tcond and not data.get("hidden", False)
        sensed = False
        if distance is not None:
            for sense in fact.get("verified_senses", []):
                limit = a.get("senses", {}).get(sense, 0)
                if type(limit) is not int or limit < distance:
                    continue
                if sense in {"blindsight", "truesight"} and not data.get("hidden", False):
                    sensed = True
                elif sense == "tremorsense" and fact.get("ground_contact") is True:
                    sensed = True
        # Revealing Hidden requires a perception owner result, not just a sense label.
        if fact.get("located") is True and fact.get("source") in {"perception_check", "canonical_effect"}:
            sensed = True
        if not (visible or sensed):
            continue
        record = {"id": target, "distance_ft": distance,
                  "conditions": sorted(tcond - {"invisible"}) if visible else [],
                  "downed": bool(tcond & {"unconscious", "dead", "incapacitated", "paralyzed", "stunned"}) if visible else False,
                  "threat": memory.get("observations", {}).get(target, {}).get("threat", 0),
                  "beliefs": copy.deepcopy(memory.get("observations", {}).get(target, {}).get("beliefs", {}))}
        if fact.get("position_known") is True and "position" in fact:
            record["position"] = copy.deepcopy(fact["position"])
        relation = relationship(session, actor, target)
        if relation == "enemy":
            targets.append(record)
        elif relation == "ally":
            allies.append(record)
        memory.setdefault("last_known", {})[target] = {
            "turn": session.world_state["combat"]["round"],
            **({"position": record["position"]} if "position" in record else {}),
        }
    return {"targets": targets, "allies": allies, "conditions": sorted(acond)}


def communicate(session, actor, leader, snapshot):
    """No sharing without canonical nearby language/telepathy evidence."""
    facts = session.world_state.get("monster_communication", {}).get(actor, {})
    channel = facts.get(leader)
    if not isinstance(channel, dict) or channel.get("verified") is not True:
        return None
    a, b = attacks.actor_data(session, actor), attacks.actor_data(session, leader)
    if channel.get("kind") == "language":
        if "deafened" in economy.conditions(session, actor):
            return None
        if channel.get("language") not in set(a.get("languages", [])) & set(b.get("languages", [])):
            return None
    elif channel.get("kind") != "telepathy":
        return None
    order = b.get("monster_orders", {}).get("target_id")
    # Orders may prioritize an already perceived target, never reveal a secret one.
    return order if order in {t["id"] for t in snapshot["targets"]} else None