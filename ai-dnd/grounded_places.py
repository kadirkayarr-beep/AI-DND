"""D-331: walking to a place the town lists or to a place kind it has not shown yet (moved out of grounded_action).

grounded_action imports this module at the top; this module imports grounded_action only inside functions."""
from __future__ import annotations

from typing import Any


def _settlement(world: dict[str, Any]) -> str | None:
    import npc_statements
    return npc_statements._settlement(world)


def _town_places(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The settlement's own places the player can walk to: not hidden, not outdoors, not a room behind a door."""
    settlement = _settlement(world)
    return {key: rec for key, rec in (world.get("locations") or {}).items()
            if isinstance(rec, dict) and settlement and rec.get("parent_location_id") == settlement
            and not rec.get("hidden") and not rec.get("outdoors") and not rec.get("inner_of")}


def searchable_kinds(session) -> list[dict[str, str]]:
    """D-331: the place kinds a player can walk to by their name that the town has not shown yet, as world knowledge
    for the front list (``kind:<kind>``). A kind the town already holds is a real place on the list instead."""
    import local_places
    world = session.world_state
    held = {value for rec in (world.get("locations") or {}).values()
            if isinstance(rec, dict) and rec.get("parent_location_id") == _settlement(world)
            for value in (rec.get("scene_kind"), rec.get("place_kind"))}
    kinds = [("tavern", "han"), *((key, spec["noun"]) for key, spec in local_places.PLACE_KINDS.items()
                                 if spec.get("stems") and not spec.get("outdoors"))]
    return [{"id": f"kind:{kind}", "name": f"{noun} (kasabada henüz görmediğin bir {noun})"}
            for kind, noun in kinds if kind not in held] if _settlement(world) else []


def known_places_question(session) -> str | None:
    """D-331: a walk that names nothing the town has asks which of the places the player can see."""
    names = [rec.get("name") for rec in _town_places(session.world_state).values() if rec.get("name")][:4]
    if not names:
        return None
    joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} ve {names[-1]}"
    return f"Nereye gitmek istediğin belli değil. Bildiğin yerler: {joined}. Hangisine gidiyorsun?"


def _kind_walk_step(noun: str, kind: str) -> dict[str, Any]:
    """The step the old chain makes of "<noun>a gidiyorum" when no place of that kind is named (probe, seed 4401)."""
    from grounded_action import fold
    word = fold(noun)
    return {"verb": "go", "to_talk": False, "method": None, "negated": False, "attempt": False, "question": False,
            "reported": False, "condition": None, "condition_target": None, "manner_negated": [],
            "tokens": [word, "gidiyorum"], "goal_tokens": [word], "target": None, "named": False,
            "via_pronoun": False, "part": None, "ambiguous": [], "other": False, "detail": None,
            "place_noun": (noun, kind), "requires_open_place": False, "not_now": False, "outside": False,
            "foreign_object": None}


def _decide_listed_walk(session, player_input: str, place_id: str, inside: bool, *, whole_line: bool = False):
    """The front step chose a listed place; the walk itself is the one a named place gets."""
    from grounded_action import (
        _DOOR_NOUNS, _RELATIONAL, _SAID_AT_THE_END, _Run, _a_better_named_place, _decide_way_out, _line_names_place,
        _walk_to_offer, candidates, fold, plan, spoken_request)
    import front_proposal
    defer = ("defer", None)
    if place_id == front_proposal.WAY_OUT:
        return _decide_way_out(session, player_input)
    offered = _walk_to_offer(session, player_input)
    if offered is not None:
        offered[1][0].model_calls = 1  # the front reading was spent on this line
        return offered
    p = plan(session, player_input)
    steps = [s for s in p["steps"] if not s.get("reported") and not s.get("not_now")]
    if not whole_line and (p["speech"] or any(s.get("question") for s in p["steps"]) or (p["steps"] and not steps)
                           or _SAID_AT_THE_END.search(fold(player_input))):
        return defer  # "hana nasıl giderim?": whatever the model read, Python's own reading says this is no walk
    import timed_gameplay
    if (steps and all(s.get("negated") or s.get("condition") for s in steps)) or timed_gameplay.says_no(player_input):
        return defer  # "hana gitmiyorum": the words themselves say this is no walk
    if not whole_line and (len(steps) > 1 or spoken_request(player_input)):
        return defer  # "hana gidip bira istiyorum": the chain that keeps the rest of the line takes it
    if place_id.startswith(front_proposal.KIND_PREFIX):
        # D-331: a kind the town has not shown yet; the old chain's search-by-kind walks to one that exists or makes one.
        known = next((row for row in searchable_kinds(session) if row["id"] == place_id), None)
        if known is None:
            return defer
        step = _kind_walk_step(known["name"].split(" (")[0], place_id[len(front_proposal.KIND_PREFIX):])
        run = _Run(session, player_input)
        run.model_calls = 1  # the front reading chose this walk
        return "execute", (run, [step], {"steps": [step]})
    target = next((c for c in candidates(session) if c["id"] == place_id and c["kind"] in {"place", "reference", "outside"}),
                  None)
    if target is None or (target["record"].get("inner_of") and any(s.get("outside") or (s.get("target") or {}).get("kind") == "outside" for s in steps)):
        return defer  # 'sokağa çıkıyorum' at a house: a small model can take the first room on the list for it
    here = (session.world_state.get("locations") or {}).get(session.world_state.get("location")) or {}
    if (target["kind"] in {"place", "reference"} and here.get("exit_location_id") != target["id"]
            and not _line_names_place(session.world_state, player_input, target["record"])):
        return defer  # the reading picked a listed place the line never names ("hana giriyorum" went to a workshop)
    if target["kind"] == "place" and _a_better_named_place(session, player_input, target):
        return defer  # "Kanyon Öyküsü Ciltevi'ne": a word shared with the inn is not the library's name
    verb = "enter" if inside and target["kind"] != "outside" else "go"
    tokens = fold(player_input).split()
    if (verb == "go" and not steps and target["kind"] != "outside"
            and any(t.startswith(_DOOR_NOUNS) or t in _RELATIONAL for t in tokens)):
        # "hanın kapısının dışında duruyorum", "önüne geliyorum": no walk in the words, the reading did not say in, and
        # the words put the player at its door or in front of it, so the player comes up to it and stays outside.
        verb = "approach"
    step = {"verb": verb, "target": target, "negated": False}
    run = _Run(session, player_input)
    run.model_calls = 1  # the front reading chose this walk
    return "execute", (run, [step], {"steps": [step]})
