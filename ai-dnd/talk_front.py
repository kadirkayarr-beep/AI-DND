"""Conversation lines and the front reading (BM, Task 1).

The model reads a line said in conversation once (front_proposal); Python checks the ids it names. The old word
routes ask `old_owner_allowed` before they answer, so they are the fallback and not a second reader.
Nothing here writes game state."""

from __future__ import annotations

from typing import Any

# The word owners that answer a say-mode line when the model gave no reading (or a reading that is not plain talk).
OWNERS = ("shop_presence", "unknown_name", "place_name", "name_disclosure", "personal", "small_talk",
          "quest_availability", "unaddressed_work", "lore_gate", "thread_talk", "role_person_list")
TALK_MODES = {"say", "ask_dm"}


def reads_say_line(session, player_input, target_id, interaction_mode, combat_action, check_feature) -> bool:
    """A say or ask_dm line the model reads, with or without a chosen person. Not read: a blow's own words, a slash
    command, a journey not arrived, the hideout, 'konuşmayı bitir' (the engine's command), a fight, a check."""
    import adventure.play as adventure_play
    import game
    if interaction_mode not in TALK_MODES or combat_action is not None or check_feature is not None:
        return False
    if not isinstance(player_input, str) or not player_input.strip() or player_input.strip().startswith("/"):
        return False
    world = session.world_state
    if (world.get("combat") or {}).get("active"):
        return False
    journey = world.get("journey")
    if journey and journey.get("status") != "ARRIVED":
        return False
    if adventure_play.inside_hideout(world) or game._is_end_conversation_request(player_input):
        return False
    return True


def is_plain_talk(front: dict | None) -> bool:
    """The reading says the player only talks: no job, no coin, no accepted or declined offer."""
    if not isinstance(front, dict) or front.get("kind") != "speak_to":
        return False
    job = front.get("job_id")
    coin = front.get("coin_cp")
    return (job in (None, "", "none") and not coin and front.get("answer", "none") in (None, "none"))


def old_owner_allowed(front: dict | None, owner: str) -> bool:
    """May this old word owner answer? Yes when there is no reading, or the reading is not plain talk; for plain
    talk only the shop presence answer stands, and only when the reading itself asks about the shop."""
    if front is None or not is_plain_talk(front):
        return True
    return owner == "shop_presence" and front.get("asks") == "shop"


def current(session) -> dict | None:
    """This turn's repaired reading of a conversation line, or None (flag off, no reading, reading failed)."""
    import front_proposal
    return getattr(session, "_front_talk", None) if front_proposal.enabled() else None


def spoken_to(front: dict | None, people: list) -> dict | None:
    """The listed person a plain-talk reading says the line is for (its `person_id`), else None."""
    if not is_plain_talk(front):
        return None
    return next((npc for npc in people if isinstance(npc, dict) and npc.get("id") == front.get("person_id")), None)


JOB_KINDS = ("work", "offer_answer", "hand_over")


def job_reading(session) -> dict | None:
    """This turn's reading, when it is one the thread gate can decide by: the player talks (`speak_to`) or the model
    read a job act. Any other kind (a walk, a blow, 'unclear') says nothing about a job, so the word reader stays."""
    front = current(session)
    return front if isinstance(front, dict) and front.get("kind") in ("speak_to", *JOB_KINDS) else None


def work_reading(front: dict | None, npc: dict, world: dict) -> dict | None:
    """The job this reading says the line speaks of, else None (BM Task 4, B1). `{"thread_id", "decision": None}`:
    Python's own validators choose the decision (pay, accept, hand over) for that thread and write it.

    The line speaks of work when the reading's kind is a job kind, or it names one of this person's jobs (`job_id` for
    work in hand, `offer_id` for work put to the player), or it asks for work (`asks == "work"`) of someone who has
    jobs. `about_person_id` naming another person never starts this person's job talk."""
    if not isinstance(front, dict) or not isinstance(npc, dict):
        return None
    import world_threads
    # a trouble that comes down to speaking with this person is theirs too (`matter`)
    mine = [*world_threads.jobs_of(world, npc), *world_threads.recent_closed(world, npc),
            *world_threads.matters_with(world, npc)]
    named = {value for value in (front.get("job_id"), front.get("offer_id")) if isinstance(value, str)} - {"", "none"}
    thread = next((t for t in mine if t.get("thread_id") in named), None)
    if thread is None and front.get("kind") == "hand_over":
        thread = next(iter([*world_threads.deliveries_to(world, npc), *world_threads.late_parcels(world, npc)]), None)
    if thread is None and mine and (front.get("kind") in JOB_KINDS or front.get("asks") == "work"):
        thread = mine[0]
    return {"thread_id": thread["thread_id"], "decision": None} if thread is not None else None


def shop_presence_reply(world_state: dict, npc_target: dict | None) -> str:
    """The shop presence sentence (moved from `_run_player_turn_internal`, same sentences). `npc_target` is the
    person asked, if any; the sentence only depends on the place."""
    import game
    import living_world
    import shop_trade
    current_location = world_state.get("location")
    local_shops = [
        shop
        for raw_shop in world_state.get("shops", [])
        if (shop := living_world.public_shop_projection(world_state, raw_shop)) is not None
        and shop.get("location") == current_location
    ]
    local_shopkeepers = [
        npc for npc in world_state.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == current_location and game._runs_a_shop(world_state, npc)
    ]
    if local_shops:
        names = ", ".join(living_world.public_shop_name(world_state, shop) for shop in local_shops)
        return f"Burada {names} adlı dükkânlar var."
    if local_shopkeepers:
        names = ", ".join(living_world.public_npc_name(npc) for npc in local_shopkeepers)
        counter = shop_trade.counter(world_state)
        if counter["status"] == "ready" and counter["vendor"]:
            return f"{counter['vendor']['name']} burada; tezgâhı açık."
        return f"{names} burada, ama şu anda açık bir tezgâhı yok."
    return "Bu çevrede şu an görünür bir dükkân ya da dükkâncı yok."
