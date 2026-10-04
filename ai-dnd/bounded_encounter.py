"""One opt-in authored courtyard, not a geometry/perception/pathfinding engine.

The scenario definition is a possibility. Only explicit gameplay materializes
it. Node measurements are authored encounter data, not MM facts or prose
inferences. Mutable positions stay with the existing NPC/scene owners.
"""
import copy
from contextlib import nullcontext

import action_economy
import campaign_time
import living_world
import weapon_attack
from combat_lifecycle import CombatRequestError

SCENARIO_ID = "open_courtyard_commoner_v1"
ENTER = "avlu karşılaşmasına gir"
START = "avlu çatışmasını başlat"
STATBLOCK_ID = "mm2024.commoner"
SOURCE = "Monster Manual 2024, Commoner, printed p.77, PDF p.80"
NODES = ("courtyard_entry", "courtyard_far", "courtyard_near")
# Separately authored directed facts. No mirrored/inferred visibility.
PAIRS = {
    ("courtyard_entry", "courtyard_far"): (60, True),
    ("courtyard_far", "courtyard_entry"): (60, True),
    ("courtyard_entry", "courtyard_near"): (5, True),
    ("courtyard_near", "courtyard_entry"): (5, True),
}
COMMONER = {
    "statblock_id": STATBLOCK_ID, "source": SOURCE, "identity": "Commoner",
    "armor_class": 10, "hit_points": 4, "hit_dice": "1d8", "speed": 30,
    "initiative_modifier": 0, "size_options": ["medium", "small"],
    "creature_type": "humanoid", "alignment": "neutral", "gear": ["Club"],
    "challenge_rating": "0", "experience_points": 10, "proficiency_bonus": 2,
    "abilities": {s: 10 for s in
                  ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")},
    "ability_modifiers": {s: 0 for s in
                         ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")},
    "passive_perception": 10, "senses": {}, "languages": ["Common"],
    "resistances": [], "immunities": [], "condition_immunities": [],
    "multiattack": None, "limited_resources": [], "recharge_resources": [],
    "traits": {"training": {"chosen_skill": "History", "proficiency_bonus": 2,
                           "advantage_on_that_skill": True,
                           "execution": "no_skill_check_in_this_scenario"}},
    "capabilities": [{
        "capability_id": "commoner_club", "kind": "attack", "action_source": "action",
        "profile": {"weapon_id": "commoner_club", "name": "Club",
                    "kind": "melee", "category": None, "properties": [],
                    "mastery": None, "attack_bonus": 2, "damage_die": 4,
                    "damage_dice": 1, "damage_modifier": 0, "damage_type": "bludgeoning",
                    "magic_attack_bonus": 0, "magic_damage_bonus": 0},
    }],
}


class MechanicalTurnContext:
    """No-model context for this bounded native path; never installs an LLM."""
    def __init__(self, adapter=None):
        self.adapter = adapter

    def ensure_required_model(self):
        pass

    def capture_model_calls(self):
        return self.adapter.capture_model_calls() if self.adapter else nullcontext([])

    def capture_model_failures(self):
        return self.adapter.capture_model_failures() if self.adapter else nullcontext([])


def command(message):
    text = " ".join(campaign_time.normalize(message).split()).rstrip(".!")
    return {campaign_time.normalize(ENTER): ENTER,
            campaign_time.normalize(START): START}.get(text)


def binding(session):
    value = session.world_state.get("bounded_encounter")
    if value is None:
        return None
    if (not isinstance(value, dict) or value.get("scenario_id") != SCENARIO_ID
            or value.get("version") != 1
            or not all(isinstance(value.get(k), str) and value[k] for k in
                       ("location_id", "npc_id", "statblock_id"))):
        raise CombatRequestError("invalid_bounded_scenario", "Bounded encounter binding is invalid.", 409)
    return value


def native_request(session, message, combat_action):
    if command(message):
        return True
    state = session.world_state.get("bounded_encounter")
    return bool(isinstance(state, dict) and state.get("scenario_id") == SCENARIO_ID
                and state.get("version") == 1
                and state.get("location_id") == session.world_state.get("location")
                and session.world_state.get("combat", {}).get("active")
                and combat_action is not None)


def _npc(session, state):
    return next((n for n in session.world_state.get("npcs", [])
                 if n.get("id") == state["npc_id"]), None)


def refresh(session):
    """Derive only this owner's facts; invalid/moved-away nodes stay unknown."""
    state = binding(session)
    if not state:
        return
    world = session.world_state
    actor = state["npc_id"]
    npc = _npc(session, state)
    pairs = world.setdefault("attack_environment", {}).setdefault("pairs", {})
    for key in (f"{actor}|player", f"player|{actor}"):
        pairs.pop(key, None)
    world.setdefault("monster_perception", {}).pop(actor, None)
    world.setdefault("monster_routes", {}).pop(actor, None)
    # Remove legacy fallback too, otherwise pair() could resurrect stale feet.
    if npc:
        npc.pop("distance_ft", None)
    position = world.get("scene_state", {}).get("player_position", {})
    if (not npc or world.get("location") != state["location_id"]
            or npc.get("location") != state["location_id"]
            or position.get("location_id") != state["location_id"]):
        return
    player_node, npc_node = position.get("bounded_node_id"), npc.get("position")
    if (player_node, npc_node) not in PAIRS or (npc_node, player_node) not in PAIRS:
        return
    for observer, target, a, b in (
        (actor, "player", npc_node, player_node),
        ("player", actor, player_node, npc_node),
    ):
        distance, sight = PAIRS[(a, b)]
        # Conditions belong to existing owners; no special sense is granted.
        visible = (sight
                   and "blinded" not in weapon_attack.conditions(session, observer, weapon_attack.actor_data(session, observer))
                   and "invisible" not in weapon_attack.conditions(session, target, weapon_attack.actor_data(session, target))
                   and not weapon_attack.actor_data(session, target).get("hidden", False))
        pairs[f"{observer}|{target}"] = {
            "distance_ft": distance, "attacker_sees_target": visible,
            "target_sees_attacker": False, "source": SCENARIO_ID,
        }
    # target_sees_attacker comes from its separately evaluated reverse fact.
    pairs[f"{actor}|player"]["target_sees_attacker"] = pairs[f"player|{actor}"]["attacker_sees_target"]
    pairs[f"player|{actor}"]["target_sees_attacker"] = pairs[f"{actor}|player"]["attacker_sees_target"]
    visible = pairs[f"{actor}|player"]["attacker_sees_target"]
    world["monster_perception"][actor] = {
        "player": {"visible": visible, "position_known": visible,
                   **({"position": player_node} if visible else {}),
                   "source": SCENARIO_ID},
    }
    # Exactly one authored path, towards the entry from the far anchor.
    # No endpoint facts for extra hostiles are fabricated. #04 rejects omissions.
    if npc_node == "courtyard_far" and player_node == "courtyard_entry" and visible:
        world["monster_routes"][actor] = [{
            "route_id": "courtyard_far_to_near", "start_node": npc_node,
            "destination": "courtyard_near", "end_node": "courtyard_near",
            "known": True, "clear": True, "mode": "walk", "difficult_terrain": False,
            "distance_ft": 55, "start_distances": {"player": 60},
            "target_distances": {"player": 5}, "hostile_participants": ["player"],
            "movement_intent": "CLOSE_DISTANCE", "source": SCENARIO_ID,
        }]


def unlocated_move(session, actor):
    """A budget-only move has no approved endpoint: invalidate, never snap back."""
    state = binding(session)
    if not state:
        return
    if actor == "player":
        session.world_state.get("scene_state", {}).get("player_position", {}).pop("bounded_node_id", None)
    elif actor == state["npc_id"]:
        npc = _npc(session, state)
        if npc:
            npc.pop("position", None)
    refresh(session)


def public_projection(session):
    """Only player-observable encounter provenance/position; no NPC AI secrets."""
    state = binding(session)
    if not state or session.world_state.get("location") != state["location_id"]:
        return None
    world = session.world_state
    node = world.get("scene_state", {}).get("player_position", {}).get("bounded_node_id")
    npc = _npc(session, state)
    opponent = None
    fact = PAIRS.get((node, npc.get("position"))) if npc else None
    if (npc and npc.get("location") == state["location_id"] and fact and fact[1]
            and "blinded" not in weapon_attack.conditions(session, "player", session.character)
            and "invisible" not in weapon_attack.conditions(session, npc["id"], npc)
            and not npc.get("hidden")):
        opponent = {"npc_id": npc["id"], "statblock_id": state["statblock_id"],
                    "source": npc["monster_stat_block"]["source"],
                    "distance_ft": fact[0], "node_id": npc["position"]}
    return {"scenario_id": SCENARIO_ID, "location_id": state["location_id"],
            "player_node_id": node if node in NODES else None, "visible_opponent": opponent}


def _reply(session, message, narration, action, **details):
    session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
    session.messages.extend([{"role": "user", "content": message},
                             {"role": "assistant", "content": narration}])
    return {"messages": session.messages, "narration": narration, "model_calls": 0,
            "action_result": {"action": action, "status": "resolved", "success": True, **details}}


def resolve_command(session, message):
    kind = command(message)
    if not kind:
        return None
    session.require_player_can_act()
    state = binding(session)
    if kind == ENTER:
        if session.world_state.get("combat", {}).get("active"):
            raise CombatRequestError("combat_travel", "Cannot enter a courtyard during combat.", 400)
        if state:
            return _reply(session, message, "Bu karşılaşma zaten gerçekleşti; NPC ve kaynaklar sıfırlanmadı.",
                          "scenario_already_materialized", npc_id=state["npc_id"])
        # This is an explicit opt-in local scene, not a global campaign rewrite.
        location = session.world_state["location"]
        if location not in session.world_state.get("locations", {}):
            raise CombatRequestError("scenario_unavailable", "Select a canonical campaign starting location first.", 400)
        if any(n.get("location") == location and (
            n.get("hostile") or n.get("combat_role") in {"enemy", "hostile"}
        ) for n in session.world_state["npcs"]):
            raise CombatRequestError("scenario_unavailable", "Resolve the existing local threat first.", 400)
        if any(n.get("location") == location
               and n.get("name", "").casefold() == "avlu saldırganı"
               and n.get("role", "").casefold() == "hooligan"
               for n in session.world_state["npcs"]):
            raise CombatRequestError("scenario_unavailable", "An existing NPC must not be rebound to a stat block.", 409)
        npc = session.create_npc_from_ai({
            "name": "Avlu saldırganı", "role": "Hooligan", "location": location,
            "appearance": "Elinde bir sopa taşıyan avlu sakini.",
            "personality": "Saldırgan; oyuncu adına hiçbir karar vermez.",
        })
        if npc is None:
            raise CombatRequestError("scenario_unavailable", "NPC capacity prevents this encounter.", 400)
        npc.update(copy.deepcopy(COMMONER["abilities"]))
        npc.update(
            monster_stat_block=copy.deepcopy(COMMONER), monster_stat_block_id=STATBLOCK_ID,
            armor_class=COMMONER["armor_class"], max_hp=COMMONER["hit_points"],
            current_hp=COMMONER["hit_points"], speed_ft=COMMONER["speed"], dex_mod=0,
            size="medium", hostile=True, combat_role="hostile", combat_status="active",
            position="courtyard_far", senses={}, passive_perception=10, languages=["Common"],
            resistances=[], immunities=[], condition_immunities=[],
            attack_bonus=2, damage_die=4, damage_dice=1, damage_modifier=0,
            attack_damage_type="bludgeoning",
        )
        session.world_state["bounded_encounter"] = {
            "scenario_id": SCENARIO_ID, "version": 1, "location_id": location,
            "node_ids": list(NODES), "npc_id": npc["id"], "statblock_id": STATBLOCK_ID,
        }
        living_world.set_player_position(session.world_state, location, "standing")
        session.world_state["scene_state"]["player_position"]["bounded_node_id"] = "courtyard_entry"
        refresh(session)
        return _reply(session, message,
                      "Açık avludasın. Avlu saldırganı 60 feet ötede sopa taşıyor. "
                      "Çatışma başlamadı; başlatmayı seçersen «Avlu çatışmasını başlat» yaz.",
                      "scenario_enter", npc_id=npc["id"], scenario_id=SCENARIO_ID)
    if not state or state["location_id"] != session.world_state.get("location"):
        raise CombatRequestError("scenario_unavailable", "Enter the bounded courtyard first.", 400)
    if session.world_state.get("combat", {}).get("active"):
        raise CombatRequestError("combat_active", "Combat is already active.", 409)
    npc = _npc(session, state)
    refresh(session)
    if not npc or npc.get("current_hp", 0) <= 0:
        raise CombatRequestError("invalid_combat_target", "This opponent cannot fight.", 400)
    # Do not create a scheduler: use the existing player-selected combat owner.
    session.start_combat(npc)
    enemies = session._resolve_enemy_turns_until_player()
    return _reply(session, message, "Seçiminle çatışma başladı; inisiyatif Python tarafından çözüldü.",
                  "action_economy", outcome="combat_started", combat_started=True,
                  npc_id=npc["id"], enemy_actions=enemies,
                  combat_id=session.world_state["combat"]["combat_id"])