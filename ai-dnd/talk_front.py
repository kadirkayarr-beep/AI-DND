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
