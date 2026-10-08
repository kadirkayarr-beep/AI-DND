"""Session door for dynamic adventures.

GameSession calls this module. It does not own XP, gold, time, lore, or combat.
"""

from __future__ import annotations

import copy

import adventure.deadlines as deadlines
import adventure.director as director
import adventure.dungeon as dungeon
import adventure.encounters as encounters
import adventure.followup as followup
import adventure.rewards as rewards
from adventure.transitions import TransitionError

_WORK_TOKENS = ("iş var", "is var", "söylenti", "soylenti", "görev", "gorev", "duydun")
_FACTION_THRESHOLD = 1


def accept(session, quest_id):
    quest = _dynamic(session, quest_id)
    if quest.get("status") == "ACTIVE":
        return {"transition": None, "quest": copy.deepcopy(quest)}
    if quest.get("status") not in {"DISCOVERED", "BLOCKED"}:
        raise ValueError("Quest is not available.")
    try:
        accepted = director.accept_dynamic(session.world_state, quest_id)
    except TransitionError as error:
        raise ValueError("Quest is not available.") from error
    deadlines.arm(session.world_state, accepted)
    return {
        "transition": _transition(session, "accepted", quest_id),
        "quest": copy.deepcopy(accepted),
    }


def abandon(session, quest_id):
    quest = _dynamic(session, quest_id)
    if quest.get("status") in {"ABANDONED", "COMPLETED", "FAILED"}:
        return {"transition": None, "quest": copy.deepcopy(quest)}
    if quest.get("status") not in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
        raise ValueError("Quest is not available.")
    try:
        left = director.abandon_dynamic(session.world_state, quest_id)
    except TransitionError as error:
        raise ValueError("Quest is not available.") from error
    return {
        "transition": _transition(session, "cancelled", quest_id),
        "quest": copy.deepcopy(left),
    }


def hear(session, quest_id):
    """The player hears one offer. AVAILABLE stays unknown until this write."""
    quest = _dynamic(session, quest_id)
    if quest.get("status") == "DISCOVERED":
        return quest
    lore = getattr(session, "campaign_lore_state", None)
    turn = _turn(session.world_state)
    if turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    from api.lore_authority.models import BindingStatus

    if lore is not None and lore.binding_status is BindingStatus.BOUND:
        from api.lore_authority.campaign_state import (
            EngineActionEvidence,
            record_adventure_possibility,
        )

        action_id = f"discover:{quest_id}"
        session.campaign_lore_state = record_adventure_possibility(
            lore,
            quest_id,
            quest.get("description") or "",
            evidence=EngineActionEvidence(action_id, turn, "python_engine"),
            source_action_id=action_id,
            turn_index=turn,
        )
    heard = director.discover(session.world_state, quest_id)
    deadlines.arm(session.world_state, heard)
    return heard


def after_turn(session, before_world, action_result):
    world = session.world_state
    _note_played_category(world, action_result)
    text = getattr(session, "_adventure_player_text", "")
    if not isinstance(text, str):
        text = ""
    _refresh_from_turn(world, before_world, action_result, text)
    if _asks_for_work(text):
        _hear_available(session, action_result)
    settle_session(session)


def close_due(world):
    """Close adventures whose scheduler window is already MISSED."""
    if not isinstance(world, dict):
        return []
    closed = []
    for quest in list(world.get("quests", [])):
        if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
            continue
        if deadlines.close_missed(world, quest):
            closed.append(quest["quest_id"])
    return closed


def settle_session(session):
    world = session.world_state
    close_due(world)
    lore = getattr(session, "campaign_lore_state", None)
    for quest in world.get("quests", []):
        if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
            continue
        if quest.get("status") in {"DISCOVERED", "ACTIVE"}:
            deadlines.arm(world, quest)
        if quest.get("status") not in {"COMPLETED", "FAILED"}:
            continue
        if quest.get("reward_application_id") is None:
            paid = rewards.apply_plan(session.character, world, quest, lore_state=lore)
            if isinstance(paid, dict) and paid.get("lore_state") is not None:
                session.campaign_lore_state = paid["lore_state"]
                lore = paid["lore_state"]
        _follow(session, quest, lore)


def traverse(session, destination):
    """Move one dungeon step. Combat and checks stay with their owners."""
    campaign_id = str(session.world_state.get("campaign_id") or "")
    return dungeon.move(session.world_state, campaign_id, destination)


def reveal(session, edge_id):
    campaign_id = str(session.world_state.get("campaign_id") or "")
    return dungeon.reveal_hidden(session.world_state, campaign_id, edge_id)


def open_door(session, edge_id):
    campaign_id = str(session.world_state.get("campaign_id") or "")
    return dungeon.open_door(session.world_state, campaign_id, edge_id)


_MOVE_WORDS = (
    "ilerle", "ilerli", "gidiyor", "giriyor", "geciyor", "geçiyor",
    "yuruyor", "yürüyor", "yuruy", "yürüy", "iniyor", "cikiyor", "çıkıyor",
    "vardi", "vardı", "ulast", "ulaşt",
)
_GENERIC_WORDS = {"oda", "odasi", "odası", "gecit", "geçit", "koridor", "giris", "giriş", "yol", "taraf"}
_HAZARD_CHECK = {"loose_beam": ("Acrobatics", 15)}


def inside_hideout(world):
    return _discovery(world) is not None


def resolve_dungeon_turn(session, text, check):
    """Play one hideout action from ordinary player text. None leaves the turn alone."""
    choice = _interpret(session.world_state, text)
    if choice is None:
        return None
    before = copy.deepcopy(session.world_state)
    outcome = _commit_dungeon(session, choice, check)
    flags = session.world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    action_result = {
        "action": outcome["action"],
        "status": "resolved" if outcome["success"] else "no_effect",
        "success": outcome["success"],
        "state_changes": outcome["changes"],
    }
    evidence_result = dict(action_result)
    if outcome.get("skill") and outcome["success"] and isinstance(outcome.get("target"), str):
        evidence_result.update(
            action="skill_check",
            skill=outcome["skill"],
            target=outcome["target"],
            action_id=f"dungeon-check:{flags['turn_index']}:{outcome['skill']}",
        )
    session.evaluate_quest_events(before, evidence_result)
    narration = outcome["narration"]
    session.messages.extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": narration},
    ])
    return {
        "messages": session.messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": action_result,
    }


def known_place(world):
    """Player-safe hideout slice. Hidden edges stay out."""
    state = _discovery(world)
    if state is None:
        return None
    exits = _known_edges(world)
    return {
        "here": _title(state["node"]),
        "exits": [_title(edge["destination"]) for edge in exits if not _door_shut(state, edge)],
        "doors": ["Kapı"] if any(_door_shut(state, edge) for edge in exits) else [],
    }


def dungeon_affordances(world):
    if _discovery(world) is None:
        if _can_enter(world):
            return ["Saklı girişe gir"]
        return []
    labels = []
    state = _discovery(world)
    edges = _known_edges(world)
    open_edges = [edge for edge in edges if not _door_shut(state, edge)]
    if len(open_edges) == 1 and "koridor" in _fold(_title(open_edges[0]["destination"])):
        labels.append("Koridorda ilerle")
    else:
        for edge in open_edges:
            labels.append(f"{_title(edge['destination'])} yönünde ilerle")
    if any(_door_shut(state, edge) for edge in edges):
        labels.append("Kapıyı açmayı dene")
    if _hidden_from_here(world):
        labels.append("Odayı incele")
    if state.get("node") == "captive":
        labels.append("Sessizce yaklaş")
        labels.append("Onu gizlice çıkar")
    return labels


def _interpret(world, text):
    folded = _fold(text if isinstance(text, str) else "")
    if not folded or folded.endswith("?"):
        return None
    inside = _discovery(world) is not None
    if not inside:
        if _can_enter(world) and any(phrase in folded for phrase in ("sakli giris", "saklı giriş", "siginak", "sığınak")):
            return {"kind": "enter"}
        return None
    if _is_open(folded) and "incel" not in folded:
        return {"kind": "open"}
    if _discovery(world).get("node") == "captive" and _is_stealth_rescue(folded):
        return {"kind": "rescue"}
    if _is_persuade(folded) and _discovery(world).get("node") == "captive":
        return {"kind": "persuade"}
    known = _known_edges(world)
    hidden_known = [edge for edge in known if edge.get("hidden")]
    if any(word in folded for word in _MOVE_WORDS) and "gizli" in folded:
        if hidden_known:
            return {"kind": "traverse", "edge": hidden_known[0]}
        return {"kind": "refuse"}
    if _is_search(folded) and not _title_match(folded, known):
        return {"kind": "search"}
    if any(word in folded for word in _MOVE_WORDS) or _title_match(folded, known):
        if _title_match(folded, known) is None and _names_unknown_place(folded, known):
            return {"kind": "refuse"}
        return {"kind": "traverse", "edge": _choose_exit(folded, world)}
    return None


def _commit_dungeon(session, choice, check):
    world = session.world_state
    campaign_id = str(world.get("campaign_id") or "")
    kind = choice["kind"]
    if kind == "enter":
        dungeon.ensure(world, campaign_id)
        return {"action": "dungeon_enter", "success": True, "changes": ["dungeon"], "narration": "Saklı girişin içindesin. İleride bir koridor var."}
    if kind == "refuse":
        return {"action": "dungeon_traverse", "success": False, "changes": [], "narration": "Oraya açılan bilinen bir yol yok."}
    if kind == "search":
        hidden = _hidden_from_here(world)
        if hidden is None or not check("Investigation", 15):
            return {"action": "dungeon_search", "success": False, "changes": [], "narration": "Duvar sağlam duruyor."}
        dungeon.reveal_hidden(world, campaign_id, hidden["edge_id"])
        title = _title(hidden["destination"])
        return {
            "action": "dungeon_search",
            "success": True,
            "changes": ["dungeon"],
            "skill": "Investigation",
            "narration": f"{title} ortaya çıktı.",
        }
    if kind == "open":
        door = _closed_door(world)
        if door is None or not check("Athletics", 15):
            return {"action": "dungeon_open", "success": False, "changes": [], "narration": "Kapı yerinden oynamıyor."}
        dungeon.open_door(world, campaign_id, door["edge_id"])
        return {"action": "dungeon_open", "success": True, "changes": ["dungeon"], "skill": "Athletics", "narration": "Kapı açıldı."}
    if kind == "persuade":
        bindings = _active_bindings(world)
        target = bindings.get("target_npc_id") if isinstance(bindings, dict) else None
        if not isinstance(target, str) or not check("Persuasion", 15):
            return {"action": "dungeon_persuade", "success": False, "changes": [], "narration": "Karşı taraf ikna olmadı."}
        return {
            "action": "dungeon_persuade",
            "success": True,
            "changes": [],
            "skill": "Persuasion",
            "target": target,
            "narration": "Sözlerin karşılık buldu.",
        }
    if kind == "rescue":
        bindings = _active_bindings(world)
        target = bindings.get("target_npc_id") if isinstance(bindings, dict) else None
        if not isinstance(target, str) or not check("Stealth", 15):
            return {"action": "dungeon_rescue", "success": False, "changes": [], "narration": "Kaçırma girişimi boşa çıktı."}
        return {
            "action": "dungeon_rescue",
            "success": True,
            "changes": [],
            "skill": "Stealth",
            "target": target,
            "narration": "Kayıp kişiyi oda dışına aldın. Tehdit hâlâ içeride.",
        }
    edge = choice.get("edge")
    if edge is None:
        return {"action": "dungeon_traverse", "success": False, "changes": [], "narration": "Bilinen bir geçit oraya açılmıyor."}
    state = _discovery(world)
    if _door_shut(state, edge):
        return {"action": "dungeon_traverse", "success": False, "changes": [], "narration": "Kapı kapalı."}
    hazard = _HAZARD_CHECK.get(edge.get("hazard"))
    if hazard is not None and not check(*hazard):
        return {"action": "dungeon_traverse", "success": False, "changes": [], "narration": "Geçit hâlâ tehlikeli; olduğun yerde kaldın."}
    dungeon.move(world, campaign_id, edge["destination"])
    _bind_room_encounter(world, edge["destination"])
    return {
        "action": "dungeon_traverse",
        "success": True,
        "changes": ["dungeon"],
        "narration": f"{_title(edge['destination'])} içindesin.",
    }


def _can_enter(world):
    location = world.get("location")
    for quest in world.get("quests", []):
        if not isinstance(quest, dict) or quest.get("record_kind") != "dynamic":
            continue
        if quest.get("status") not in {"ACTIVE", "BLOCKED"}:
            continue
        if not any(
            isinstance(item.get("target"), str) and item["target"].startswith(f"{dungeon.HIDEOUT_ID}:")
            for item in quest.get("objectives", [])
            if isinstance(item, dict)
        ):
            continue
        places = quest.get("bindings", {}).get("location_ids") if isinstance(quest.get("bindings"), dict) else None
        if isinstance(places, list) and location in places:
            return True
    return False


def _active_bindings(world):
    for quest in world.get("quests", []):
        if isinstance(quest, dict) and quest.get("record_kind") == "dynamic" and quest.get("status") == "ACTIVE":
            bindings = quest.get("bindings")
            if isinstance(bindings, dict):
                return bindings
    return {}


def _discovery(world):
    found = world.get("dungeon_discovery")
    if not isinstance(found, dict):
        return None
    state = found.get(dungeon.HIDEOUT_ID)
    if not isinstance(state, dict) or state.get("campaign_id") != world.get("campaign_id"):
        return None
    return state


def _known_edges(world):
    state = _discovery(world)
    if state is None:
        return []
    edges = []
    for edge in dungeon.HIDEOUT["edges"]:
        if edge["source"] != state.get("node"):
            continue
        if edge["hidden"] and edge["edge_id"] not in state.get("discovered_edges", []):
            continue
        edges.append(edge)
    return edges


def _hidden_from_here(world):
    state = _discovery(world)
    if state is None:
        return None
    for edge in dungeon.HIDEOUT["edges"]:
        if edge["source"] == state.get("node") and edge["hidden"] and edge["edge_id"] not in state.get("discovered_edges", []):
            return edge
    return None


def _closed_door(world):
    state = _discovery(world)
    for edge in _known_edges(world):
        if _door_shut(state, edge):
            return edge
    return None


def _door_shut(state, edge):
    return bool(edge.get("door")) and edge["edge_id"] not in state.get("opened_doors", [])


def _choose_exit(folded, world):
    edges = _known_edges(world)
    matched = _title_match(folded, edges)
    if matched is not None:
        return matched
    state = _discovery(world)
    open_edges = [edge for edge in edges if not _door_shut(state, edge)]
    if len(open_edges) == 1 and any(word in folded for word in _MOVE_WORDS):
        return open_edges[0]
    if len(edges) == 1 and any(word in folded for word in _MOVE_WORDS):
        return edges[0]
    return None


def _names_unknown_place(folded, edges):
    titles = " ".join(_fold(_title(edge["destination"])) for edge in edges)
    allowed = set(_GENERIC_WORDS) | {
        "sagdaki", "sağdaki", "soldaki", "ileri", "geri", "dogru", "doğru",
        "buradan", "oradan", "olan", "oldugu", "olduğu", "icin", "için",
        "kadar", "tarafa", "yonunde", "yönünde", "gecitten", "geçitten",
        "koridorda", "odaya", "odanin", "odanın",
    }
    for word in folded.replace("'", " ").split():
        word = word.strip(".,!")
        if len(word) < 5 or word in allowed or word in titles:
            continue
        if any(word.startswith(move) or move.startswith(word) for move in _MOVE_WORDS):
            continue
        return True
    return False


def _title_match(folded, edges):
    found = None
    for edge in edges:
        words = [word for word in _fold(_title(edge["destination"])).split() if word not in _GENERIC_WORDS and len(word) >= 4]
        if any(word in folded for word in words):
            if found is not None:
                return None
            found = edge
    return found


def _title(node_id):
    node = dungeon.HIDEOUT["nodes"].get(node_id, {})
    title = node.get("title")
    return title if isinstance(title, str) else ""


def _is_open(folded):
    return ("kapi" in folded or "kapı" in folded) and ("ac" in folded or "aç" in folded)


def _is_search(folded):
    return any(word in folded for word in ("incele", "arastir", "araştır", "duvar"))


def _is_persuade(folded):
    return any(word in folded for word in ("ikna", "sessizce yaklas", "sessizce yaklaş"))


def _is_stealth_rescue(folded):
    return any(word in folded for word in ("gizlice", "kacir", "kaçır"))


def _bind_room_encounter(world, node_id):
    recipe_id = dungeon.HIDEOUT["nodes"].get(node_id, {}).get("encounter_recipe_id")
    if not isinstance(recipe_id, str):
        return
    bindings = _active_bindings(world)
    target = bindings.get("target_npc_id") if isinstance(bindings, dict) else None
    known = {npc.get("id") for npc in world.get("npcs", []) if isinstance(npc, dict)}
    entities = [target] if isinstance(target, str) and target in known else []
    bound = encounters.bind(
        recipe_id,
        entities=entities,
        location=f"{dungeon.HIDEOUT_ID}:{node_id}",
    )
    state = _discovery(world)
    if bound is None or state is None:
        return
    state["active_encounter"] = bound
    recipes = bindings.get("encounter_recipe_ids") if isinstance(bindings, dict) else None
    if isinstance(recipes, list) and recipe_id not in recipes and len(recipes) < 8:
        recipes.append(recipe_id)


def _note_played_category(world, action_result):
    if not isinstance(action_result, dict):
        return
    action = action_result.get("action")
    if action_result.get("combat_ended") is True or action in {"attack", "weapon_attack"}:
        director.note_category(world, "combat")
        return
    if isinstance(action, str) and action.startswith("dungeon_"):
        director.note_category(world, "dungeon")
        return
    if action == "skill_check":
        skill = str(action_result.get("skill") or "").casefold()
        if skill == "investigation":
            director.note_category(world, "investigation")
        elif skill in {"persuasion", "intimidation"}:
            director.note_category(world, "social")
        return
    if action in {"travel", "move"}:
        director.note_category(world, "travel")


def _fold(text):
    return text.translate(str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})).casefold()


def _refresh_from_turn(world, before_world, action_result, text):
    director.maybe_refresh_on_arrival(
        world, before_world, campaign_id=str(world.get("campaign_id") or ""),
    )
    if not isinstance(action_result, dict):
        return
    action = action_result.get("action")
    if action in {"attack", "death_save"} and not action_result.get("combat_ended"):
        return
    campaign_id = str(world.get("campaign_id") or "")
    location = world.get("location") if isinstance(world.get("location"), str) else ""
    npc_id = action_result.get("npc_id") or action_result.get("target_id")
    if action == "dialogue" and isinstance(npc_id, str) and action_result.get("success") is True:
        _offer(
            world,
            reason="npc_conversation",
            trigger="talk",
            source_id=npc_id,
            evidence_id=f"talk:{location}:{npc_id}",
            campaign_id=campaign_id,
        )
    if _asks_for_work(text):
        source = npc_id if isinstance(npc_id, str) else _present_id(world)
        if isinstance(source, str):
            _offer(
                world,
                reason="ask_rumors",
                trigger="ask",
                source_id=source,
                evidence_id=f"ask:{location}:{source}",
                campaign_id=campaign_id,
            )
    if action_result.get("combat_ended") is True:
        _offer(
            world,
            reason="aftermath",
            trigger="aftermath",
            source_id=_present_id(world),
            evidence_id=f"aftermath:{location}",
            campaign_id=campaign_id,
        )
    if action == "local_search" and action_result.get("status") == "found":
        found = action_result.get("target_id")
        if isinstance(found, str):
            _offer(
                world,
                reason="meaningful_discovery",
                trigger="found",
                source_id=_present_id(world),
                evidence_id=f"found:{found}",
                campaign_id=campaign_id,
            )


def _offer(world, *, reason, trigger, source_id, evidence_id, campaign_id):
    if not isinstance(source_id, str):
        return None
    from adventure.templates import prepared_bindings

    present = [
        npc for npc in world.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == world.get("location") and isinstance(npc.get("id"), str)
    ]
    if len(present) < 2:
        return None
    target = next((npc for npc in present if npc["id"] != source_id), present[0])
    label = target.get("name") if isinstance(target.get("name"), str) and target.get("name").strip() else "biri"
    location = world.get("location")
    return director.refresh(
        world,
        reason=reason,
        trigger=trigger,
        source_id=source_id,
        bindings=prepared_bindings(
            source_npc_id=source_id,
            target_npc_id=target["id"],
            location_ids=[location] if isinstance(location, str) else [],
        ),
        rumor=f"{label} hakkında bir söylenti dolaşıyor.",
        evidence_id=evidence_id,
        campaign_id=campaign_id,
    )


def _hear_available(session, action_result):
    npc_id = None
    if isinstance(action_result, dict):
        npc_id = action_result.get("npc_id") or action_result.get("target_id")
    quests = [
        item for item in session.world_state.get("quests", [])
        if isinstance(item, dict)
        and item.get("record_kind") == "dynamic"
        and item.get("status") == "AVAILABLE"
    ]
    if isinstance(npc_id, str):
        matched = [item for item in quests if item.get("giver_npc_id") == npc_id]
        if matched:
            quests = matched
    if not quests:
        return None
    return hear(session, quests[0]["quest_id"])


def _follow(session, quest, lore):
    bindings = quest.get("bindings") if isinstance(quest.get("bindings"), dict) else {}
    rumor = "Bu işin ardından başka bir iz çıktı."
    campaign_id = str(session.world_state.get("campaign_id") or "")
    followup.maybe_follow_up(
        session.world_state,
        quest,
        bindings=bindings,
        rumor=rumor,
        evidence_id=f"follow:{quest['quest_id']}:{quest.get('outcome')}",
        campaign_id=campaign_id,
    )
    faction_ids = bindings.get("faction_ids") or []
    if not faction_ids or lore is None:
        return
    standing = _standing(lore, faction_ids[0])
    if standing is None:
        return
    followup.faction_gate(
        session.world_state,
        standing,
        threshold=_FACTION_THRESHOLD,
        bindings=bindings,
        rumor="Hizip güveni yeni bir iş açtı.",
        evidence_id=f"faction:{quest['quest_id']}:{faction_ids[0]}",
        campaign_id=campaign_id,
    )


def _standing(lore, faction_id):
    for row in getattr(lore, "faction_standings", ()):
        if row.faction_id == faction_id:
            return row.standing
    return None


def _asks_for_work(text):
    folded = text.casefold()
    return any(token in folded for token in _WORK_TOKENS)


def _present_id(world):
    for npc in world.get("npcs", []):
        if isinstance(npc, dict) and npc.get("location") == world.get("location") and isinstance(npc.get("id"), str):
            return npc["id"]
    return None


def _dynamic(session, quest_id):
    quest = next(
        (
            item for item in session.world_state.get("quests", [])
            if isinstance(item, dict) and item.get("quest_id") == quest_id
        ),
        None,
    )
    if quest is None or quest.get("record_kind") != "dynamic":
        raise ValueError("Quest is not available.")
    return quest


def _transition(session, kind, quest_id):
    turn = _turn(session.world_state)
    return {
        "event_id": f"quest:{kind}:{quest_id}:command:{kind}:{quest_id}:{turn}",
        "quest_id": quest_id,
        "transition": kind,
        "objective_id": None,
        "source_event_id": f"command:{kind}:{quest_id}:{turn}",
        "turn_index": turn,
    }


def _turn(world):
    turn = world.get("flags", {}).get("turn_index", 0)
    return turn if isinstance(turn, int) and turn >= 0 else 0
