import game
import action_economy
import combat_lifecycle
import copy
import effect_targeting
import talk_mode
import weapon_attack
from api.core_resolution import (
    resolve_death_save,
)
import campaign_time
import initiative
import scheduled_events
import living_world
import re


def long_rest_gap_seconds(world):
    """How long until a new Long Rest may begin: 16 game hours after the last one finished."""
    completed = game._validate_long_rest_history(world)
    if completed is None:
        return 0
    return max(0, completed + 16 * 3600 - world["campaign_time"]["elapsed_seconds"])

def _death_state_defaults():
    return {
        "mode": "NORMAL",
        "successes": 0,
        "failures": 0,
        "stable": False,
        "dead": False,
        "terminal": False,
        "prone": False,
        "last_death_save_turn_key": None,
        "last_death_save_result": None,
        "last_resolution": None,
        "combat_checkpoint": None,
        "recovery": None,
        "noncombat_next_save_at": None,
        "noncombat_episode_id": None,
    }

def ensure_death_state():
    """Load the canonical death state, defaulting old saves to Normal mode."""
    world_state = game._session().world_state
    state = world_state.get("death_state")
    if not isinstance(state, dict):
        state = game._death_state_defaults()
        world_state["death_state"] = state
    for key, value in game._death_state_defaults().items():
        state.setdefault(key, copy.deepcopy(value))
    if state.get("mode") not in game.DEATH_MODES:
        raise ValueError("Campaign death mode is invalid.")
    if (
        type(state.get("successes")) is not int
        or not 0 <= state["successes"] <= 3
        or type(state.get("failures")) is not int
        or not 0 <= state["failures"] <= 3
        or any(
            type(state.get(key)) is not bool
            for key in ("stable", "dead", "terminal", "prone")
        )
        or (
            state.get("combat_checkpoint") is not None
            and not isinstance(state.get("combat_checkpoint"), dict)
        )
        or (
            state.get("last_death_save_turn_key") is not None
            and not isinstance(state.get("last_death_save_turn_key"), str)
        )
        or (
            state.get("last_death_save_result") is not None
            and not isinstance(state.get("last_death_save_result"), dict)
        )
        or (
            state.get("last_resolution") is not None
            and not isinstance(state.get("last_resolution"), dict)
        )
        or (
            state.get("last_call") is not None
            and not isinstance(state.get("last_call"), dict)
        )
    ):
        raise ValueError("Campaign death state is invalid.")

    recovery = state["recovery"]
    if recovery is not None and (
        not isinstance(recovery, dict)
        or set(recovery) != {"hours", "at"}
        or type(recovery.get("hours")) is not int
        or not 1 <= recovery["hours"] <= 4
        or type(recovery.get("at")) is not int or recovery["at"] < 0
        or not state["stable"] or state["dead"]
    ):
        raise ValueError("Stable recovery state is invalid.")
    if state["noncombat_next_save_at"] is not None and (
        type(state["noncombat_next_save_at"]) is not int
        or state["noncombat_next_save_at"] < 0
    ):
        raise ValueError("Noncombat death-save timing is invalid.")
    if state["noncombat_episode_id"] is not None and not isinstance(state["noncombat_episode_id"], str):
        raise ValueError("Noncombat death episode is invalid.")
    character = game._session().character
    status = world_state.get("player_combat_status")
    if status not in ("active", "unconscious", "dead"):
        status = "unconscious" if character.get("current_hp", 1) <= 0 else "active"
        world_state["player_combat_status"] = status
    if state["dead"] or status == "dead":
        if character.get("current_hp", 0) > 0:
            raise ValueError("Dead player state cannot have positive hit points.")
        state["dead"] = True
        world_state["player_combat_status"] = "dead"
        talk_mode.close(world_state, "death")
        if state["mode"] == "IRONMAN":
            state["terminal"] = True
    elif character.get("current_hp", 0) <= 0 and status == "active":
        world_state["player_combat_status"] = "unconscious"
    if state["stable"] and (
        character.get("current_hp", 0) != 0
        or world_state["player_combat_status"] != "unconscious"
        or state["dead"]
    ):
        raise ValueError("Stable player state is inconsistent.")
    if state["dead"] and state["stable"]:
        raise ValueError("Dead player state cannot be stable.")
    return state

class PlayerCannotAct(ValueError):
    """The turn never started; the API answers it with player_cannot_act_turn."""

def require_player_can_act():
    """Reject player-originated mutations while unconscious or dead."""
    state = game.ensure_death_state()
    world_state = game._session().world_state
    if state["dead"] or world_state.get("player_combat_status") == "dead":
        raise game.PlayerCannotAct("Ölü karakter eylem gerçekleştiremez.")
    if (
        game._session().character.get("current_hp", 0) <= 0
        or world_state.get("player_combat_status") == "unconscious"
    ):
        raise game.PlayerCannotAct("Bilinçsiz karakter eylem gerçekleştiremez.")
    return True

def stabilize_player():
    """Consume a verified stabilization outcome; not permission to self-stabilize."""
    state = game.ensure_death_state()
    if state["dead"] or game._session().character["current_hp"] != 0:
        raise ValueError("Yalnız yaşayan ve sıfır canı olan bir yolcu sabitlenebilir.")
    state.update(stable=True, successes=0, failures=0, noncombat_next_save_at=None)
    if state["recovery"] is None:
        game.ensure_campaign_clock()
        hours = game._session().rng.randint(1, 4)
        state["recovery"] = {
            "hours": hours,
            "at": game._session().world_state.get("campaign_time", {}).get("elapsed_seconds", 0) + hours * 3600,
        }
    return {"action": "stabilize", "success": True, "status": "resolved"}

def attempt_player_stabilization(healer_id):
    """Canonical allied NPC Help action, using the existing Medicine resolver."""
    import weapon_attack
    import action_economy
    from api.core_resolution import resolve_skill_check
    session = game._session()
    healer = next((n for n in session.world_state["npcs"]
                   if n.get("id") == healer_id), None)
    if (not healer or healer.get("location") != session.world_state["location"]
            or healer.get("combat_status") != "active" or healer.get("current_hp", 0) <= 0
            or healer.get("hostile") is True
            or weapon_attack.conditions(session, healer_id, healer) & {"incapacitated", "unconscious", "dead"}):
        raise ValueError("Bu kişi ilk yardım uygulayamaz.")
    import item_use
    kit_in_bag = any((i.get("name") if isinstance(i, dict) else i) == item_use.HEALERS_KIT
                     for i in session.world_state.get("inventory", []))
    modifier = healer.get("medicine_bonus")
    if type(modifier) is not int and not kit_in_bag:
        raise ValueError("Bu kişinin Tıp becerisi desteklenmiyor.")
    state = game.ensure_death_state()
    if state["dead"] or session.character["current_hp"] != 0:
        raise ValueError("İlk yardım için uygun bir yolcu yok.")
    combat = game.ensure_combat_state()
    if combat["active"]:
        action_economy.action_slot(session, healer_id, "help")
    if kit_in_bag:  # D-023: 2024 Healer's Kit stabilizes with no Medicine roll
        kit = item_use.spend_healers_kit(session.world_state)
        if combat["active"]:
            game._mark_combat_action_used(healer_id, "help")
        game.stabilize_player()
        return {"action": "stabilize", "status": "resolved", "success": True, "healers_kit": kit}
    result = resolve_skill_check(roll_fn=game.roll_d20, skill="medicine", ability="wisdom",
                                 dc=10, ability_modifier=modifier)
    if combat["active"]:
        game._mark_combat_action_used(healer_id, "help")
    if result["outcome"] == "SUCCESS":
        game.stabilize_player()
    return {"action": "stabilize", "status": "resolved",
            "success": result["outcome"] == "SUCCESS", "resolution": result}

def heal_player(amount):
    """Apply already-resolved real healing; never revive a dead creature."""
    if type(amount) is not int or amount < 0:
        raise ValueError("Healing amount is invalid.")
    state = game.ensure_death_state()
    if state["dead"]:
        raise ValueError("Ölü karakter diriltilmeden can kazanamaz.")
    character = game._session().character
    restored = min(amount, max(0, character["max_hp"] - character["current_hp"]))
    if restored:
        character["current_hp"] += restored
        state.update(stable=False, successes=0, failures=0, recovery=None,
                     noncombat_next_save_at=None, noncombat_episode_id=None)
        game._session().world_state["player_combat_status"] = "active"
    return restored

def set_player_max_hp(maximum):
    """Consume an authoritative maximum-HP change, including instant death at zero."""
    if type(maximum) is not int or maximum < 0:
        raise ValueError("HP maximum is invalid.")
    game.ensure_death_state()
    game._session().character["max_hp"] = maximum
    game._session().character["current_hp"] = min(game._session().character["current_hp"], maximum)
    if maximum == 0:
        return game._finalize_player_death("maximum_hp_zero")
    return None

def apply_npc_damage(npc, damage, *, knock_out=False):
    """Single Policy A handoff for already-resolved damage; no rolls or migration."""
    if not any(npc is n for n in game._session().world_state["npcs"]):
        raise ValueError("Damage target is not canonical.")
    if type(damage) is not int or damage < 0:
        raise ValueError("Damage is invalid.")
    before = npc.get("current_hp", npc.get("max_hp", 1))
    if npc.get("combat_status") == "dead":
        return before
    npc["current_hp"] = max(0, before - damage)
    if damage > 0 and npc["current_hp"] == 0 and knock_out and npc.get("combat_status") != "unconscious":
        import fallen
        fallen.knock_out(game._session(), npc)  # PHB 2024: 1 HP and Unconscious instead of 0
    elif damage > 0 and npc["current_hp"] == 0:
        npc["combat_status"] = "dead"
        import bold_acts
        bold_acts.killed(game._session(), npc)
        import xp  # paid at the kill like a knock-out, so fleeing or standing down loses nothing; the shared receipt stops a second pay (D-016, K8)
        game._session()._forfeit_unrecordable_xp(xp.award_downed, npc, game._session().world_state, game._session().character,
                                            person_kind=game.person_fight_kind(npc))
    return npc["current_hp"]

def _capture_combat_death_checkpoint():
    """Capture gameplay state before initiative without capturing RNG or receipts."""
    session = game._session()
    state = game.ensure_death_state()
    if state["mode"] != "NORMAL":
        state["combat_checkpoint"] = None
        return
    saved_world = copy.deepcopy(session.world_state)
    saved_world.setdefault("death_state", {})["combat_checkpoint"] = None
    checkpoint = {
        "campaign_id": session.world_state.get("campaign_id"),
        "player": copy.deepcopy(session.character),
        "world_state": saved_world,
        "recent_dm_narrations": list(session.recent_dm_narrations),
        "world_metadata": copy.deepcopy(
            getattr(session, "world_metadata", None)
        ),
        # D-113: a level crossing inside the fight moves the save format; the rollback puts it back with the hero.
        "persisted_engine_format": getattr(session, "_persisted_engine_format", game.SAVE_FORMAT_VERSION),
    }
    provider = getattr(session, "death_checkpoint_provider", None)
    if callable(provider):
        external = provider()
        if not isinstance(external, dict):
            raise ValueError("Campaign death checkpoint data is invalid.")
        checkpoint["campaign_state"] = copy.deepcopy(external)
    state["combat_checkpoint"] = checkpoint

def _restore_combat_death_checkpoint(cause):
    """Restore Normal-mode gameplay state while preserving RNG and save receipts."""
    session = game._session()
    state = game.ensure_death_state()
    checkpoint = state.get("combat_checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("Normal death rollback checkpoint is unavailable.")
    if checkpoint.get("campaign_id") != session.world_state.get("campaign_id"):
        raise ValueError("Normal death rollback checkpoint belongs to another campaign.")
    saved_world = checkpoint.get("world_state")
    saved_player = checkpoint.get("player")
    if not isinstance(saved_world, dict) or not isinstance(saved_player, dict):
        raise ValueError("Normal death rollback checkpoint is invalid.")
    has_format = "persisted_engine_format" in checkpoint  # a checkpoint saved before D-113 has none
    saved_format = checkpoint.get("persisted_engine_format")
    if has_format and (type(saved_format) is not int or saved_format not in game._SUPPORTED_SAVE_VERSIONS):
        raise ValueError("Normal death rollback checkpoint is invalid.")

    mode = state["mode"]
    last_turn_key = state.get("last_death_save_turn_key")
    last_save_result = copy.deepcopy(state.get("last_death_save_result"))
    resolution = {
        "mode": mode,
        "outcome": "rolled_back",
        "cause": cause,
        "rolled_back": True,
        "terminal": False,
    }
    restored_world = copy.deepcopy(saved_world)
    restored_death = restored_world.setdefault(
        "death_state", game._death_state_defaults()
    )
    restored_death["mode"] = mode
    restored_death["dead"] = False
    restored_death["terminal"] = False
    restored_death["combat_checkpoint"] = None
    restored_death["last_death_save_turn_key"] = last_turn_key
    restored_death["last_death_save_result"] = last_save_result
    restored_death["last_resolution"] = resolution

    candidate = game.GameSession()
    candidate.character.clear()
    candidate.character.update(copy.deepcopy(saved_player))
    candidate.world_state.clear()
    candidate.world_state.update(copy.deepcopy(restored_world))
    candidate.recent_dm_narrations[:] = copy.deepcopy(checkpoint.get("recent_dm_narrations", []))
    game._validate_save_payload(candidate.serialize_game_state())
    if has_format:
        # Also admit the restored hero at the format the campaign will be saved in.
        candidate._persisted_engine_format = saved_format
        game._validate_save_payload(candidate.serialize_game_state())
    candidate.ensure_death_state()
    campaign_state = checkpoint.get("campaign_state")
    if campaign_state is not None:
        validator = getattr(session, "death_checkpoint_validator", None)
        restorer = getattr(session, "death_checkpoint_restorer", None)
        if not callable(validator) or not callable(restorer):
            raise ValueError("Campaign death checkpoint cannot be validated.")
        validator(copy.deepcopy(campaign_state))

    session.world_state.clear()
    session.world_state.update(restored_world)
    session.character.clear()
    session.character.update(copy.deepcopy(saved_player))
    session.recent_dm_narrations[:] = copy.deepcopy(
        checkpoint.get("recent_dm_narrations", [])
    )
    session.world_metadata = copy.deepcopy(checkpoint.get("world_metadata"))
    # The XP, level and receipt of an award are back to the checkpoint; so is its pending announcement.
    session._xp_level_up = None
    session._xp_unrecorded = []
    session._xp_unrecorded_awards = []
    if has_format:
        session._persisted_engine_format = saved_format
    campaign_state = checkpoint.get("campaign_state")
    if campaign_state is not None:
        restorer = getattr(session, "death_checkpoint_restorer", None)
        if not callable(restorer):
            raise ValueError("Campaign death checkpoint cannot be restored.")
        restorer(copy.deepcopy(campaign_state))
    return resolution

def _finalize_player_death(cause):
    """Apply the selected death mode once all three failures are recorded."""
    # Finalize the owner's transient fatal transition before validating it.
    pending = game._session().world_state.get("death_state")
    if isinstance(pending, dict):
        pending["recovery"] = None
        pending["noncombat_next_save_at"] = None
    state = game.ensure_death_state()
    state["recovery"] = None
    state["noncombat_next_save_at"] = None
    if state["mode"] == "NORMAL" and state.get("combat_checkpoint"):
        return game._restore_combat_death_checkpoint(cause)
    state["dead"] = True
    state["stable"] = False
    state["terminal"] = state["mode"] == "IRONMAN"
    state["combat_checkpoint"] = None
    game._session().character["current_hp"] = 0
    game._session().world_state["player_combat_status"] = "dead"
    resolution = {
        "mode": state["mode"],
        "outcome": "dead",
        "cause": cause,
        "rolled_back": False,
        "terminal": state["terminal"],
    }
    state["last_resolution"] = resolution
    combat = game._session().world_state.get("combat")
    if isinstance(combat, dict) and combat.get("active") is True:
        game.end_combat("player_dead")
    return resolution

def _apply_player_damage(hp_damage, *, critical=False, took_damage=False, resolved_damage=None):
    """Apply post-mitigation damage and the V1 unconscious/death-save rules."""
    session = game._session()
    world_state = session.world_state
    state = game.ensure_death_state()
    hp_before = max(0, int(session.character.get("current_hp", 0)))
    max_hp = max(1, int(session.character.get("max_hp", 1)))
    hp_damage = max(0, int(hp_damage))
    hp_after = max(0, hp_before - hp_damage)
    death_resolution = None

    if state["dead"]:
        return {
            "hp_before": hp_before,
            "hp_after": hp_before,
            "status": "dead",
            "death_resolution": None,
        }
    if hp_before > 0 and hp_after > 0:
        session.character["current_hp"] = hp_after
        return {
            "hp_before": hp_before,
            "hp_after": hp_after,
            "status": "active",
            "death_resolution": None,
        }

    # Terminal Rage ending is part of this existing zero-HP mutation, before
    # any death checkpoint rollback (which owns restoration of prior history).
    import barbarian_rage
    barbarian_rage.end(session)
    import paladin_features
    paladin_features.end_divine_sense(session)
    if hp_before > 0:
        if hp_damage >= hp_before + max_hp:
            state["dead"] = True
            state["stable"] = False
            state["failures"] = 3
            session.character["current_hp"] = 0
            world_state["player_combat_status"] = "dead"
            death_resolution = game._finalize_player_death("massive_damage")
            return {
                "hp_before": hp_before,
                "hp_after": 0,
                "status": "dead",
                "death_resolution": death_resolution,
            }
        session.character["current_hp"] = 0
        world_state["player_combat_status"] = "unconscious"
        state["stable"] = False
        state["successes"] = 0
        state["failures"] = 0
        state["prone"] = True
        state["noncombat_episode_id"] = str(game.uuid4())
        if not world_state.get("combat", {}).get("active"):
            game.ensure_campaign_clock()
            state["noncombat_next_save_at"] = world_state.get("campaign_time", {}).get("elapsed_seconds", 0) + 6
        return {
            "hp_before": hp_before,
            "hp_after": 0,
            "status": "unconscious",
            "death_resolution": None,
        }

    session.character["current_hp"] = 0
    world_state["player_combat_status"] = "unconscious"
    state["prone"] = True
    zero_hp_damage = hp_damage if resolved_damage is None else resolved_damage
    if zero_hp_damage >= max_hp:
        state["dead"] = True
        state["stable"] = False
        state["failures"] = 3
        death_resolution = game._finalize_player_death("massive_damage")
        return {
            "hp_before": 0,
            "hp_after": 0,
            "status": "dead",
            "death_resolution": death_resolution,
        }
    if took_damage:
        state["stable"] = False
        state["recovery"] = None
        state["failures"] = min(3, state["failures"] + (2 if critical else 1))
        if not world_state.get("combat", {}).get("active"):
            game.ensure_campaign_clock()
            state["noncombat_next_save_at"] = world_state.get("campaign_time", {}).get("elapsed_seconds", 0) + 6
        if state["failures"] >= 3:
            state["dead"] = True
            death_resolution = game._finalize_player_death("failed_death_saves")
            return {
                "hp_before": 0,
                "hp_after": 0,
                "status": "dead",
                "death_resolution": death_resolution,
            }
    return {
        "hp_before": 0,
        "hp_after": 0,
        "status": "unconscious",
        "death_resolution": None,
    }

def _combat_defaults(end_reason=None):
    return {
        "schema_version": 3,
        "active": False,
        "status": "ended",
        "combat_id": None,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
        "current_actor_id": None,
        "participants": [],
        "participant_records": [],
        "actions_used": [],
        "target_id": None,
        "end_reason": end_reason,
    }

def _combat_record_for_actor(participant_id, initiative=None, actions_used=()):
    """Build a detached, canonical participant projection for persisted combat."""
    session = game._session()
    if participant_id == "player":
        character = session.character
        current_hp = int(character.get("current_hp", 0))
        max_hp = int(character.get("max_hp", max(1, current_hp)))
        status = session.world_state.get("player_combat_status", "active")
        return {
            "id": "player",
            "kind": "player",
            "name": str(character.get("name", "Player")),
            "initiative": initiative,
            "current_hp": max(0, min(current_hp, max_hp)),
            "max_hp": max(1, max_hp),
            "armor_class": max(0, int(character.get("armor_class", 0))),
            "status": status if status in ("active", "unconscious", "dead") else "active",
            "primary_action_available": participant_id not in actions_used,
        }

    npc = next(
        (item for item in session.world_state.get("npcs", [])
         if isinstance(item, dict) and item.get("id") == participant_id),
        None,
    )
    if npc is None:
        raise ValueError("Active combat participant is missing from the current location.")
    game.ensure_npc_enemy_stats(npc)
    current_hp = int(npc.get("current_hp", 0))
    max_hp = int(npc.get("max_hp", max(1, current_hp)))
    status = npc.get("combat_status", "active")
    if status not in ("active", "unconscious", "defeated", "dead"):
        raise ValueError("Active combat participant has an invalid status.")
    if npc.get("location") != session.world_state.get("location"):
        status = "inactive"  # Real authoritative relocation, not a fabricated turn.
    elif status == "active" and action_economy._surrendered(session, participant_id):
        status = "surrendered"  # the fight's own accepted surrender: out of the fight, no longer an enemy
    return {
        "id": participant_id,
        "kind": "npc",
        "name": str(npc.get("name", participant_id)),
        "initiative": initiative,
        "current_hp": max(0, min(current_hp, max_hp)),
        "max_hp": max(1, max_hp),
        "armor_class": max(0, int(npc.get("armor_class", 0))),
        "status": status,
        "primary_action_available": participant_id not in actions_used,
    }

def _migrate_legacy_combat_state(legacy):
    """Map a known two-participant V1/V2 encounter, rejecting ambiguous active data."""
    if not isinstance(legacy, dict):
        return game._combat_defaults()
    # Native V1/V2 writers omitted this field. Accept only the explicit actor-ID
    # list extension; never infer modern resources or spending from the cursor.
    actions_used = legacy.get("actions_used", [])
    if (
        not isinstance(actions_used, list)
        or any(not isinstance(actor, str) or not actor for actor in actions_used)
        or len(set(actions_used)) != len(actions_used)
    ):
        raise ValueError("Legacy combat actions_used markers are invalid.")
    if legacy.get("active") is not True:
        if actions_used:
            raise ValueError("Inactive legacy combat cannot contain actions_used markers.")
        return game._combat_defaults()
    if legacy.get("schema_version") not in (None, 1, 2):
        raise ValueError("Unsupported legacy combat save version.")

    order = legacy.get("initiative_order")
    index = legacy.get("current_turn_index")
    round_number = legacy.get("round")
    legacy_participants = legacy.get("participants")
    target_id = legacy.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        candidates = [
            item for item in (legacy_participants if isinstance(legacy_participants, list) else [])
            if isinstance(item, str) and item != "player"
        ]
        candidates.extend(
            item for item in (order if isinstance(order, list) else [])
            if isinstance(item, str) and item != "player"
        )
        candidates = list(dict.fromkeys(candidates))
        if len(candidates) == 1:
            target_id = candidates[0]
    if (
        not isinstance(order, list)
        or len(order) != 2
        or any(not isinstance(actor, str) or not actor for actor in order)
        or len(set(order)) != 2
        or set(order) != {"player", target_id}
        or type(index) is not int
        or not 0 <= index < len(order)
        or type(round_number) is not int
        or round_number < 1
        or (
            legacy_participants is not None
            and (
                not isinstance(legacy_participants, list)
                    or any(
                        not isinstance(item, str) or not item
                        for item in legacy_participants
                    )
                or set(legacy_participants) != set(order)
                or len(legacy_participants) != len(order)
            )
        )
    ):
        raise ValueError(
            "Active legacy combat is missing a valid participant identity or turn boundary."
        )
    if not set(actions_used).issubset(set(order)):
        raise ValueError("Legacy combat actions_used contains a nonparticipant.")

    world_state = game._session().world_state
    npc = next(
        (item for item in world_state.get("npcs", [])
         if isinstance(item, dict) and item.get("id") == target_id),
        None,
    )
    if npc is None or npc.get("location") != world_state.get("location"):
        raise ValueError(
            "Active legacy combat target is missing from the saved location."
        )
    state = game._combat_defaults()
    state.update({
        "active": True,
        "status": "active",
        "round": round_number,
        "initiative_order": list(order),
        "current_turn_index": index,
        "current_actor_id": order[index],
        "participants": list(
            legacy_participants if legacy_participants is not None else order
        ),
        "actions_used": list(actions_used),
        "target_id": target_id,
        "end_reason": None,
    })
    state["participant_records"] = [
        game._combat_record_for_actor(
            participant_id,
            initiative=None,
            actions_used=state["actions_used"],
        )
        for participant_id in state["participants"]
    ]
    # Legacy saves predate encounter identity; mint it at the migration boundary,
    # not in the V3 validator, so malformed native V3 saves still fail visibly.
    state["combat_id"] = str(game.uuid4())
    return state

def _sync_combat_participant_records(combat):
    for identity in combat["participants"]:
        if identity != "player" and sum(
            isinstance(n, dict) and n.get("id") == identity for n in game._session().world_state.get("npcs", [])
        ) != 1:
            raise ValueError("Combat participant identity is missing or duplicated.")
    records = []
    initiative_by_id = {
        record.get("id"): record.get("initiative")
        for record in combat.get("participant_records", [])
        if isinstance(record, dict)
    }
    for participant_id in combat["participants"]:
        records.append(game._combat_record_for_actor(
            participant_id,
            initiative=initiative_by_id.get(participant_id),
            actions_used=combat["actions_used"],
        ))
    combat["participant_records"] = records

def ensure_combat_state():
    """Migrate known legacy combat and strictly preserve active scheduler state."""
    world_state = game._session().world_state
    game.ensure_death_state()
    combat = world_state.get("combat")
    if isinstance(combat, dict) and combat.get("schema_version") not in (None, 1, 2, 3):
        raise ValueError("Unsupported combat save version.")
    if not isinstance(combat, dict) or combat.get("schema_version") != 3:
        combat = game._migrate_legacy_combat_state(combat)
        world_state["combat"] = combat
    else:
        if not combat.get("active"):
            combat.setdefault("combat_id", None)
        game._validate_combat_v3_payload(combat)

    if world_state.get("player_combat_status") not in ("active", "unconscious", "dead"):
        world_state["player_combat_status"] = (
            "unconscious"
            if game._session().character.get("current_hp", 1) <= 0
            else "active"
        )
    if combat["active"]:
        action_economy.ensure(game._session())
        game._sync_combat_participant_records(combat)
        game._validate_combat_v3_payload(combat)
    return combat

def person_fight_kind(npc):
    """What a person with no stat block fights as, read from their role: "armed", "strong" or "plain"."""
    role = game._normalize_turkish_typos(f"{npc.get('role', '')}")
    return "armed" if game._ARMED_ROLE.search(role) else "strong" if game._STRONG_ROLE.search(role) else "plain"

def _person_fight(npc):
    """A person fights like what they are; only stats nobody set take these values."""
    kind = game.person_fight_kind(npc)
    armor, hit_points, bonus, die, damage_type = game._PERSON_FIGHT[kind]
    npc.setdefault("armor_class", armor)
    if "max_hp" not in npc:
        npc["max_hp"] = hit_points
        npc["current_hp"] = min(npc.get("current_hp", hit_points), hit_points)
    npc.setdefault("attack_bonus", bonus)
    npc.setdefault("damage_die", die)
    npc.setdefault("attack_damage_type", npc.get("damage_type", damage_type))

def ensure_npc_enemy_stats(npc):
    """Ensure NPC has enemy combat stats with safe defaults for legacy NPCs."""
    game.ensure_npc_combat_stats(npc)
    if "attack_bonus" not in npc:
        npc["attack_bonus"] = 2
    if "damage_die" not in npc:
        npc["damage_die"] = 6
    if "damage_dice" not in npc:
        npc["damage_dice"] = 1
    if "damage_modifier" not in npc:
        npc["damage_modifier"] = 0
    return npc

def ensure_npc_combat_stats(npc):
    """Ensure NPC has combat stats with safe defaults for legacy NPCs."""
    game._person_fight(npc)
    if "max_hp" not in npc:
        npc["max_hp"] = 10
    if "current_hp" not in npc:
        npc["current_hp"] = npc["max_hp"]
    if "armor_class" not in npc:
        npc["armor_class"] = 10
    if "combat_status" not in npc:
        npc["combat_status"] = "active"
    return npc

def resolve_combat_target(player_input, npc_target=None, target_id=None):
    """Resolve the combat target from player input or current NPC target.
    
    Validates that the target is a canonical NPC from world_state["npcs"]
    and is in the current location. Rejects forged/detached NPC dicts.
    """
    world_state = game._session().world_state
    requested_id = target_id
    if requested_id is None and npc_target:
        requested_id = npc_target.get("id")
    if requested_id is not None:
        if not isinstance(requested_id, str) or not requested_id:
            return None
        canonical_npc = next(
            (npc for npc in world_state.get("npcs", [])
             if isinstance(npc, dict) and npc.get("id") == requested_id),
            None
        )
        if not canonical_npc:
            return None  # Not a registered NPC
        if canonical_npc.get("location") != world_state.get("location"):
            return None
        game.ensure_npc_combat_stats(canonical_npc)
        return canonical_npc

    named = combat_lifecycle.pointed_targets(game._session(), player_input) if player_input else []
    if len(named) == 1:
        game.ensure_npc_combat_stats(named[0])
        return named[0]
    resolution = game.resolve_npc_reference(player_input)
    if resolution["status"] == "found":
        game.ensure_npc_combat_stats(resolution["npc"])
        return resolution["npc"]
    elif resolution["status"] == "ambiguous":
        return "ambiguous"
    
    return None

def _set_temporary_hit_points(amount, state=None):
    character = game._session().character
    state = state if isinstance(state, dict) else game._species_trait_state()
    state["temporary_hit_points"] = amount
    if (character.get("species", character.get("race")) not in game.SPECIES_WITH_TRAIT_STATE
            and (amount > 0 or "temporary_hit_points" in character)):
        character["temporary_hit_points"] = amount
    return amount

def grant_temporary_hit_points(amount):
    """Apply externally granted Temporary Hit Points without healing or waking the player."""
    if type(amount) is not int or amount < 0:
        raise ValueError("Temporary Hit Points must be a non-negative integer.")
    state = game._species_trait_state()
    return game._set_temporary_hit_points(
        max(state["temporary_hit_points"], amount),
        state=state,
    )

def _species_bonus_action():
    combat = game.ensure_combat_state()
    if not combat["active"]:
        return None
    if (
        combat["current_actor_id"] != "player"
    ):
        raise ValueError("Bu bonus eylem için sıra sende değil.")
    state = game._species_trait_state()
    if action_economy.ensure(game._session())["player"]["bonus_action_spent"]:
        raise ValueError("Bu tur bonus eylemini zaten kullandın.")
    state["bonus_action_used_round"] = combat["round"]
    action_economy.ensure(game._session())["player"]["bonus_action_spent"] = True
    return combat

def _species_player_turn_id():
    combat = game.ensure_combat_state()
    if combat["active"]:
        return combat["round"]
    return game._session().world_state.get("flags", {}).get("turn_index", 0)

def _apply_species_on_hit_effects(target_npc, *, critical=False, deals_damage):
    character = game._session().character
    state = game._species_trait_state()
    proficiency_bonus = character.get("proficiency_bonus", 2)
    bonus_damage = 0
    effects = []
    active_form = state.get("active_celestial_form")
    turn_id = game._species_player_turn_id()
    if (
        character.get("species") == "Aasimar"
        and active_form
        and deals_damage  # "when you deal damage to it with an attack" (PHB 2024; D-197)
        and state.get("celestial_damage_used_turn") != turn_id
    ):
        damage_type = (
            "necrotic" if active_form == "necrotic_shroud" else "radiant"
        )
        bonus_damage += proficiency_bonus
        state["celestial_damage_used_turn"] = turn_id
        effects.append(
            {
                "trait": "celestial_revelation",
                "damage": proficiency_bonus,
                "damage_type": damage_type,
            }
        )

    ancestry = character.get("giant_ancestry")
    if (
        character.get("species") == "Goliath"
        and ancestry in game.GIANT_ANCESTRY_IDS
        and ancestry not in {"cloud", "stone", "storm"}  # Storm's Thunder is a damage reaction (D-132)
        and deals_damage  # "hit ... and deal damage" (PHB 2024; D-197)
        and state.get("giant_ancestry_armed")
        and state.get("giant_ancestry_uses_remaining", 0) > 0
        # Hill's Tumble reaches only a Large or smaller creature (PHB 2024); a Huge or unknown size spends nothing (D-201).
        and (
            ancestry != "hill"
            or str(target_npc.get("size", "medium")).lower()
            in weapon_attack.SIZES[: weapon_attack.SIZES.index("large") + 1]
        )
    ):
        state["giant_ancestry_uses_remaining"] -= 1
        state["giant_ancestry_armed"] = False
        def bonus_roll(sides):
            rolls = [game._session().rng.randint(1, sides) for _ in range(2 if critical else 1)]
            return sum(rolls), {"damage_die": sides, "raw_rolls": rolls}
        if ancestry == "fire":
            damage, audit = bonus_roll(10)
            bonus_damage += damage
            effects.append(
                {"trait": "fire_giant_ancestry", "damage": damage, "damage_type": "fire", **audit}
            )
        elif ancestry == "frost":
            damage, audit = bonus_roll(6)
            bonus_damage += damage
            # Until the start of the Goliath's next turn: the attack owner's timed effect ends it (D-049).
            weapon_attack.effect(game._session(), "frost_giant_ancestry", "player", target_npc["id"])
            effects.append(
                {
                    "trait": "frost_giant_ancestry",
                    "damage": damage,
                    "damage_type": "cold",
                    "speed_reduction_ft": 10,
                    **audit,
                }
            )
        elif ancestry == "hill":
            # Hill's Tumble (PHB 2024): Prone with no saving throw (D-201).
            target_npc["prone"] = True
            effects.append({"trait": "hill_giant_ancestry", "knocked_prone": True})
    return bonus_damage, effects

def _finish_species_player_turn():
    character = game._session().character
    state = game._species_trait_state()
    effects = []
    if (
        character.get("species") == "Aasimar"
        and state.get("active_celestial_form") == "inner_radiance"
        and state.get("celestial_revelation_turns_remaining", 0) > 0
    ):
        amount = character.get("proficiency_bonus", 2)
        game.ensure_combat_state()
        reachable = effect_targeting.eligible_effect_targets(game._session(), "player", game.INNER_RADIANCE_SPEC)
        for npc in game._session().world_state.get("npcs", []):
            if not isinstance(npc, dict) or npc.get("id") not in reachable:
                continue
            # K02: the shared mitigation owner decides immunity/resistance/vulnerability; apply_npc_damage gets the final value.
            mitigation = weapon_attack.mitigate(game._session(), npc.get("id"), "radiant", amount)
            damage = mitigation["final_damage"]
            after = game.apply_npc_damage(npc, damage)
            effects.append(
                {
                    "trait": "inner_radiance",
                    "target_id": npc.get("id"),
                    "damage": damage,
                    "damage_type": "radiant",
                    "mitigation": mitigation,
                    "target_hp_after": after,
                }
            )
        # The PHB effect includes the Aasimar; its radiant resistance halves this damage.
        self_damage = amount // 2
        damage_result = game._apply_attack_damage_to_player(self_damage, False, True)
        death_resolution = damage_result.get("death_resolution")
        if death_resolution and death_resolution["rolled_back"]:
            return [{"trait": "inner_radiance", "death_resolution": death_resolution}]
        effects.append(
            {
                "trait": "inner_radiance",
                "target_id": "player",
                "damage": self_damage,
                "damage_type": "radiant",
                "target_hp_after": character["current_hp"],
                "death_resolution": death_resolution,
            }
        )

    state["player_turn_counter"] += 1
    if state.get("active_celestial_form"):
        state["celestial_revelation_turns_remaining"] = max(
            0, state["celestial_revelation_turns_remaining"] - 1
        )
        state["celestial_damage_used_turn"] = None
        if state["celestial_revelation_turns_remaining"] == 0:
            state["active_celestial_form"] = None
            effects.append({"trait": "celestial_revelation", "expired": True})
    if state.get("large_form_turns_remaining", 0) > 0:
        state["large_form_turns_remaining"] -= 1
        if state["large_form_turns_remaining"] == 0:
            effects.append({"trait": "large_form", "expired": True})
    if "effect_clock" in state:  # K03: this turn boundary owns the combat decrement; keep the clock seconds in step
        game.effect_lifecycle.sync_from_turns(state)
        for effect in effects:
            if effect.get("expired") and effect.get("trait") in game.effect_lifecycle.TIMED_EFFECTS:
                state["effect_clock"]["remaining_s"].pop(effect["trait"], None)
                state["effect_clock"]["last_event"].pop(effect["trait"], None)
    state["movement_budget_ft"] = 0
    state["movement_effect"] = None
    return effects

def resolve_species_trait_action(action, form=None, ancestry=None, armed=None, elapsed_seconds=None, *, healing_amount=None, remove_poisoned=None,
                                 draconic_ancestry=None, shape=None, target_id=None):
    game.require_player_can_act()
    if action in {"short_rest", "long_rest"}:
        import barbarian_rage
        barbarian_rage.prepare_restore(game._session())
        import character_progression
        character_progression.prepare_rest(game._session())
        if action == "long_rest":
            import sorcery_points
            sorcery_points.prepare_restore(game._session())
        game.ensure_campaign_clock()
        if "campaign_time" not in game._session().world_state:
            raise ValueError("Dinlenmeden önce başlangıç sahnesi belirlenmeli.")
        minimum = 3600 if action == "short_rest" else 8 * 3600
        if elapsed_seconds is not None and (
            type(elapsed_seconds) is not int or not minimum <= elapsed_seconds <= campaign_time.DAY * 365
        ):
            raise ValueError("Dinlenme süresi geçersiz.")
        if game.ensure_combat_state()["active"]:
            raise ValueError("Çatışma sırasında dinlenemezsin.")
        if action == "long_rest":
            if game.long_rest_gap_seconds(game._session().world_state):
                raise ValueError("Yeni uzun dinlenmeye başlamadan önce son tamamlanmadan 16 oyun saati geçmeli.")
        rest_time = game.advance_campaign_time(elapsed_seconds if elapsed_seconds is not None else minimum, action)
        if rest_time.get("condition_death"):
            # D-145: the one result shape every rest answers with, so the panel's contract keeps the death too.
            return {"action": action, "message": "Dinlenme, mevcut ölüm politikasınca kesildi.",
                    "effects": {"time_result": rest_time, "rest_completed": False}}
        if rest_time.get("interrupted"):
            interrupted_effects = {"time_result": rest_time, "rest_completed": False}
            if action == "long_rest" and rest_time.get("elapsed_seconds", 0) >= 3600:
                # PHB 2024 Long Rest (PDF 370): rested at least 1 hour before the interruption -> the benefits of a Short Rest.
                # Only the Hit Point Dice window is given here; species Short Rest features are not (HANDOFF).
                import hit_dice
                interrupted_effects["short_rest_hit_dice"] = True  # only the Hit Dice part of the Short Rest benefits
                interrupted_effects["hit_dice"] = hit_dice.open_window(game._session())
                # Rage has its own source-backed Short Rest recovery. An
                # interrupted Long Rest after an hour grants one, not all uses.
                import barbarian_rage
                barbarian_rage.restore(game._session(), "short_rest")
                character_progression.rest_recovery(game._session(), "short_rest")
            return {
                "action": action, "message": "Dinlenme tamamlanmadı; önce karşılaşma için karar vermelisin.",
                "effects": interrupted_effects,
            }
    character = game._session().character
    species = character.get("species", character.get("race"))
    state = game._species_trait_state()
    combat = game.ensure_combat_state()
    effects = {}

    def require_species(expected):
        if species not in expected:
            raise ValueError("Bu tür yeteneği karakterin için kullanılamaz.")

    def require_action_turn():
        if combat["active"]:
            action_economy.validate_actor(game._session())

    if action == "choose_giant_ancestry":
        require_species({"Goliath"})
        if combat["active"]:
            raise ValueError("Dev Atası çatışma sırasında seçilemez.")
        if ancestry not in game.GIANT_ANCESTRY_IDS:
            raise ValueError("Geçerli bir Dev Atası seç.")
        if character.get("giant_ancestry") is not None:
            raise ValueError("Dev Atası zaten seçilmiş; kampanya içinde değiştirilemez.")
        character["giant_ancestry"] = ancestry
        state["giant_ancestry_uses_remaining"] = character.get("proficiency_bonus", 2)
        message = "Dev Atası seçimi kaydedildi."
        effects = {"giant_ancestry": ancestry}

    elif action == "healing_hands":
        require_species({"Aasimar"})
        require_action_turn()
        if combat["active"]:
            action_economy.action_slot(game._session(), "player", "feature")
        if state["healing_hands_uses_remaining"] <= 0:
            raise ValueError("Şifa Veren Eller uzun dinlenmeye kadar kullanıldı.")
        if character["current_hp"] >= character["max_hp"]:
            raise ValueError("Can puanın zaten en yüksek düzeyde.")
        rolls = [
            game._session().rng.randint(1, 4)
            for _ in range(character.get("proficiency_bonus", 2))
        ]
        healing = min(sum(rolls), character["max_hp"] - character["current_hp"])
        game.heal_player(healing)
        state["healing_hands_uses_remaining"] -= 1
        effects = {"dice": rolls, "healing": healing, "heal_source": "species", "current_hp": character["current_hp"]}
        message = f"Şifa Veren Eller {healing} can puanı yeniledi."
        if combat["active"]:
            game._mark_combat_action_used("player", "feature")
            effects["turn_end"] = [] if action_economy.holding(game._session()) else game._finish_species_player_turn()
            if not action_economy.holding(game._session()) and not game._combat_end_if_decided():
                advanced, _, _ = game.advance_combat_turn()
                if advanced:
                    effects["enemy_actions"] = game._resolve_enemy_turns_until_player()

    elif action == "celestial_revelation":
        require_species({"Aasimar"})
        require_action_turn()
        if character.get("level", 1) < 3:
            raise ValueError("Göksel Tecelli 3. seviyede açılır.")
        if form not in game.CELESTIAL_REVELATION_FORMS:
            raise ValueError("Geçerli bir Göksel Tecelli biçimi seç.")
        if state["celestial_revelation_uses_remaining"] <= 0:
            raise ValueError("Göksel Tecelli uzun dinlenmeye kadar kullanıldı.")
        if state["active_celestial_form"] is not None:
            raise ValueError("Başka bir Göksel Tecelli biçimi zaten etkin.")
        game._species_bonus_action()
        state["celestial_revelation_uses_remaining"] -= 1
        state["active_celestial_form"] = form
        state["celestial_revelation_turns_remaining"] = 10
        game.effect_lifecycle.start_effect(state, "celestial_revelation")
        if form == "heavenly_wings":
            state["movement_effect"] = {
                "kind": "flight",
                "speed_ft": character.get("speed_ft", 30),
            }
        elif form == "necrotic_shroud":
            save_dc = 8 + character.get("proficiency_bonus", 2) + character.get("charisma_mod", 0)
            saves = []
            reachable = effect_targeting.eligible_effect_targets(game._session(), "player", game.NECROTIC_SHROUD_SPEC)
            for npc in game._session().world_state.get("npcs", []):
                if not isinstance(npc, dict) or npc.get("id") not in reachable:
                    continue
                save_bonus = npc.get("charisma_save_bonus", npc.get("charisma_modifier", 0))
                if type(save_bonus) is not int:
                    save_bonus = 0
                resolution = game.resolve_saving_throw(
                    roll_fn=game.roll_d20,
                    ability="charisma",
                    dc=save_dc,
                    ability_modifier=save_bonus,
                )
                save_roll = resolution["selected_roll"]
                frightened = resolution["outcome"] == "FAILURE"
                if frightened:
                    npc["frightened_until_player_turn"] = state["player_turn_counter"] + 2
                saves.append(
                    {
                        "target_id": npc.get("id"),
                        "save_roll": save_roll,
                        "save_bonus": save_bonus,
                        "save_dc": save_dc,
                        "frightened": frightened,
                        "resolution": resolution,
                    }
                )
            effects["saves"] = saves
        effects.update({"form": form, "duration_turns": 10})
        message = "Göksel Tecelli etkinleştirildi."

    elif action == "large_form":
        require_species({"Goliath"})
        require_action_turn()
        if character.get("level", 1) < 5:
            raise ValueError("Büyük Biçim 5. seviyede açılır.")
        if state["large_form_uses_remaining"] <= 0:
            raise ValueError("Büyük Biçim uzun dinlenmeye kadar kullanıldı.")
        if state["large_form_turns_remaining"] > 0:
            raise ValueError("Büyük Biçim zaten etkin.")
        game._species_bonus_action()
        state["large_form_uses_remaining"] -= 1
        state["large_form_turns_remaining"] = 100
        game.effect_lifecycle.start_effect(state, "large_form")
        if combat["active"]:
            resources = action_economy.ensure(game._session())["player"]
            resources["movement_available"] = max(
                resources["movement_used"], action_economy.movement_limit(game._session(), "player"))
        state["movement_effect"] = {
            "kind": "large_form",
            "size": "Large",
            "speed_bonus_ft": 10,
        }
        effects = {
            "size": "Large",
            "speed_ft": character.get("speed_ft", 35) + 10,
            "strength_checks_advantage": True,
            "duration_turns": 100,
            "duration_minutes": 10,
        }
        message = "Büyük Biçim etkinleştirildi."

    elif action == "adrenaline_rush":
        require_species({"Orc"})
        require_action_turn()
        if state["adrenaline_rush_uses_remaining"] <= 0:
            raise ValueError("Adrenalin Patlaması için kullanım kalmadı.")
        game._species_bonus_action()
        state["adrenaline_rush_uses_remaining"] -= 1
        granted_hp = character.get("proficiency_bonus", 2)
        game.grant_temporary_hit_points(granted_hp)
        speed = character.get("speed_ft", 30) + (
            10 if state["large_form_turns_remaining"] > 0 else 0
        )
        state["movement_budget_ft"] = speed * 2
        state["movement_effect"] = {"kind": "dash", "distance_ft": speed * 2}
        if combat["active"]:
            resources = action_economy.ensure(game._session())["player"]
            resources["dash_count"] = resources.get("dash_count", 0) + 1
            resources["movement_available"] = max(
                resources["movement_used"], action_economy.movement_limit(game._session(), "player"))
        effects = {
            "temporary_hit_points": state["temporary_hit_points"],
            "dash_distance_ft": speed * 2,
        }
        message = "Adrenalin Patlaması kullanıldı; Dash hareketi ve geçici can kazanıldı."

    elif action == "cloud_jaunt":
        require_species({"Goliath"})
        require_action_turn()
        if character.get("giant_ancestry") != "cloud":
            raise ValueError("Bulut Devi kökeni seçili değil.")
        if state["giant_ancestry_uses_remaining"] <= 0:
            raise ValueError("Dev Atası kullanımı kalmadı.")
        game._species_bonus_action()
        state["giant_ancestry_uses_remaining"] -= 1
        state["movement_effect"] = {"kind": "teleport", "distance_ft": 30}
        import bounded_encounter
        bounded_encounter.unlocated_move(game._session(), "player")
        effects = {
            "teleport_distance_ft": 30,
            "ancestry_uses_remaining": state["giant_ancestry_uses_remaining"],
        }
        message = "Bulut Devi Işınlanmasıyla 30 fitlik ışınlanma kullanıldı."

    elif action == "arm_giant_ancestry":
        require_species({"Goliath"})
        if armed is not None and type(armed) is not bool:
            raise ValueError("Dev Atası hazır durumu geçersiz.")
        if character.get("giant_ancestry") not in {"fire", "frost", "hill", "stone", "storm"}:
            raise ValueError("Bu Dev Atası saldırı veya hasar tepkisiyle etkinleştirilmiyor.")
        if state["giant_ancestry_uses_remaining"] <= 0:
            raise ValueError("Dev Atası kullanımı kalmadı.")
        state["giant_ancestry_armed"] = (
            not state["giant_ancestry_armed"] if armed is None else armed
        )
        message = (
            "Dev Atası etkisi sonraki uygun durumda kullanılacak."
            if state["giant_ancestry_armed"]
            else "Dev Atası etkisi hazır beklemeden çıkarıldı."
        )
        effects = {
            "armed": state["giant_ancestry_armed"],
            "ancestry": character["giant_ancestry"],
            "uses_remaining": state["giant_ancestry_uses_remaining"],
        }

    elif action == "choose_draconic_ancestry":
        import dragonborn_breath
        message, effects = dragonborn_breath.choose_ancestry(game._session(), draconic_ancestry)

    elif action == "breath_weapon":
        import dragonborn_breath
        message, effects = dragonborn_breath.breathe(game._session(), shape, target_id)

    elif action == "short_rest":
        if combat["active"]:
            raise ValueError("Çatışma sırasında dinlenemezsin.")
        if elapsed_seconds is not None and (type(elapsed_seconds) is not int or elapsed_seconds < 3600):
            raise ValueError("Kısa dinlenme en az bir saat sürer.")
        refreshed = 0
        if species == "Orc":
            maximum = character.get("proficiency_bonus", 2)
            refreshed = max(0, maximum - state["adrenaline_rush_uses_remaining"])
            state["adrenaline_rush_uses_remaining"] = maximum
        state["movement_budget_ft"] = 0
        state["movement_effect"] = None
        effects = {"adrenaline_rush_uses_refreshed": refreshed}
        import hit_dice
        effects["hit_dice"] = hit_dice.open_window(game._session())  # K07: the player spends dice one request at a time
        import barbarian_rage
        barbarian_rage.restore(game._session(), "short_rest")
        character_progression.rest_recovery(game._session(), "short_rest")
        message = (
            "Kısa dinlenme tamamlandı; Adrenalin Patlaması kullanımları yenilendi."
            if species == "Orc"
            else "Kısa dinlenme tamamlandı; bu türün kısa dinlenmeyle yenilenen yeteneği yok."
        )

    elif action == "long_rest":
        if combat["active"]:
            raise ValueError("Çatışma sırasında dinlenemezsin.")
        if elapsed_seconds is not None and (type(elapsed_seconds) is not int or elapsed_seconds < 8 * 3600):
            raise ValueError("Uzun dinlenme en az sekiz saat sürer.")
        old_state = state
        if (not game._session().world_state.get("supplies_policy", {}).get("enabled", False)
                or not game._session().world_state.get("supplies_accounting", {}).get("missing")):
            character["exhaustion"] = max(0, weapon_attack.exhaustion(character) - 1)
        refreshed = {
            "healing_hands": max(0, (1 if species == "Aasimar" else 0) - old_state["healing_hands_uses_remaining"]),
            "celestial_revelation": max(0, (1 if species == "Aasimar" else 0) - old_state["celestial_revelation_uses_remaining"]),
            "giant_ancestry": max(0, (character.get("proficiency_bonus", 2) if species == "Goliath" else 0) - old_state["giant_ancestry_uses_remaining"]),
            "large_form": max(0, (1 if species == "Goliath" else 0) - old_state["large_form_uses_remaining"]),
            "adrenaline_rush": max(0, (character.get("proficiency_bonus", 2) if species == "Orc" else 0) - old_state["adrenaline_rush_uses_remaining"]),
            "relentless_endurance": not old_state["relentless_endurance_available"] and species in {"Orc", "Half-Orc"},
        }
        long_rest_healing = game.heal_player(character["max_hp"] - character["current_hp"])
        import hit_dice
        hit_dice.restore_all(character)  # PHB 2024 Long Rest: ALL spent Hit Point Dice return
        import dragonborn_breath
        dragonborn_breath.long_rest(character)  # Breath Weapon: every use returns (D-233)
        game._session().world_state["player_combat_status"] = "active"
        character["species_trait_state"] = game._new_persisted_species_trait_state(
            species, character.get("proficiency_bonus", 2)
        )
        character.pop("temporary_hit_points", None)
        for npc in game._session().world_state.get("npcs", []):
            if isinstance(npc, dict):
                npc.pop("frightened_until_player_turn", None)
                npc.pop("speed_penalty_ft", None)
                npc.pop("speed_penalty_turns_remaining", None)
                npc.pop("prone", None)
        state = character["species_trait_state"]
        effects = {"refreshed": refreshed, "current_hp": character["current_hp"],
                   "healing": long_rest_healing, "heal_source": "rest"}
        import spell_scope
        spell_scope.restore_slots(game._session())
        import spell_preparation
        spell_preparation.open_window(game._session(), "long_rest")  # 4C.2: Wizard/Cleric choose again after a finished Long Rest
        import sorcery_points
        sorcery_points.restore(game._session())
        import barbarian_rage
        barbarian_rage.restore(game._session(), "long_rest")
        character_progression.rest_recovery(game._session(), "long_rest")
        game._session().world_state["last_long_rest_completed_at"] = game._session().world_state["campaign_time"]["elapsed_seconds"]
        message = "Gözlerini kapatıyorsun; uyandığında yorgunluğun gitmiş, gücün yerine gelmiş."

    elif action == "spend_hit_die":
        import hit_dice
        if combat["active"]:
            raise ValueError("Çatışma sırasında Hit Point Dice harcanamaz.")
        effects = hit_dice.spend(game._session(), game.heal_player)
        message = f"Bir Hit Point Die harcandı; {effects['healing']} can puanı yenilendi."

    elif action == "second_wind":
        import fighter_features
        effects = fighter_features.second_wind_outside_combat(game._session())
        message = f"Second Wind kullanıldı; {effects['healing']} can puanı yenilendi."

    elif action == "lay_on_hands":
        import paladin_features
        effects = paladin_features.lay_on_hands_outside_combat(game._session(), healing_amount, remove_poisoned)
        message = f"Lay On Hands kullanıldı; {effects['healing']} can puanı yenilendi, havuzda {effects['pool_remaining']} kaldı."

    elif action == "divine_sense":
        import paladin_features
        effects = paladin_features.divine_sense_outside_combat(game._session())
        message = f"Divine Sense açıldı; kalan Channel Divinity: {effects['uses_remaining']}."

    else:
        raise ValueError("Bilinmeyen tür yeteneği.")

    if action in {"short_rest", "long_rest"}:
        game.ensure_campaign_clock()
        if "campaign_time" not in game._session().world_state:
            raise ValueError("Dinlenmeden önce başlangıç sahnesi belirlenmeli.")
        effects["time_result"] = rest_time
    return {"action": action, "message": message, "effects": effects}

def resolve_attack(player_input, weapon_name, weapon_data, target_npc, *,
                   attack_choice=None, origin="action"):
    """Compatibility caller; catalog/inventory, never caller stats, are authority."""
    game.ensure_combat_state()
    return weapon_attack.resolve(
        game._session(), "player", target_npc["id"], weapon_name,
        attack_choice, origin=origin,
    )

def register_attack_hook(event, callback):
    return weapon_attack.register_hook(game._session(), event, callback)

def _combat_participant_can_act(combat, participant_id):
    record = next(
        (item for item in combat.get("participant_records", [])
         if item.get("id") == participant_id),
        None,
    )
    if participant_id == "player":
        death = game.ensure_death_state()
        if (
            record
            and record.get("status") == "unconscious"
            and record.get("current_hp") == 0
            and not death["dead"]
        ):
            # Keep an unconscious player's initiative slot so the scheduler
            # can resolve death saves or stop cleanly after they stabilize.
            return True
    elif record and record.get("current_hp") == 0 and record.get("status") in ("active", "unconscious"):
        # Preserve its boundary without inventing NPC death mechanics.
        return True
    return bool(
        record
        and record.get("status") == "active"
        and type(record.get("current_hp")) is int
        and record["current_hp"] > 0
    )

def _mark_combat_action_used(participant_id, action_type="attack"):
    combat = game.ensure_combat_state()
    if participant_id not in combat["participants"]:
        raise ValueError("Combat action actor is not a participant.")
    if not combat["active"] or participant_id != combat["current_actor_id"]:
        raise combat_lifecycle.CombatRequestError("out_of_turn", "Actor is not the current combat participant.")
    if action_economy.can_act(game._session(), participant_id):
        action_economy.consume_action(game._session(), participant_id, action_type)
    else:
        action_economy.ensure(game._session())[participant_id]["base_action_spent"] = True
    if participant_id not in combat["actions_used"]:
        combat["actions_used"].append(participant_id)
    game._sync_combat_participant_records(combat)
    game._validate_combat_v3_payload(combat)

def _resolve_player_death_turn(*, noncombat_key=None):
    """Resolve one automatic DC 10 death save on the player's scheduled turn."""
    combat = game.ensure_combat_state()
    death = game.ensure_death_state()
    if (
        (noncombat_key is None and (not combat["active"] or combat["current_actor_id"] != "player"))
        or death["stable"]
        or death["dead"]
        or game._session().character.get("current_hp", 0) > 0
        or game._session().world_state.get("player_combat_status") != "unconscious"
    ):
        return None
    if noncombat_key is None and not combat.get("combat_id"):
        combat["combat_id"] = str(game.uuid4())
    turn_key = noncombat_key or f"{combat['combat_id']}:{combat['round']}"
    if (
        death.get("last_death_save_turn_key") == turn_key
        and isinstance(death.get("last_death_save_result"), dict)
    ):
        return copy.deepcopy(death["last_death_save_result"])

    resolution = resolve_death_save(roll_fn=game.roll_d20)
    roll = resolution["selected_roll"]
    outcome = "success" if roll >= 10 else "failure"
    if roll == 1:
        death["failures"] = min(3, death["failures"] + 2)
        outcome = "natural_1"
    elif roll == 20:
        game.heal_player(1)
        death["prone"] = True
        outcome = "revived"
    elif roll >= 10:
        death["successes"] += 1
        if death["successes"] >= 3:
            game.stabilize_player()
            outcome = "stable"
    else:
        death["failures"] = min(3, death["failures"] + 1)

    dead = death["failures"] >= 3
    death_save = {
        "roll": roll,
        "outcome": "dead" if dead else outcome,
        "successes": death["successes"],
        "failures": death["failures"],
        "stable": death["stable"],
        "dead": dead,
        "prone": death["prone"],
        "action_id": resolution.get("action_id"),
        "resolution_id": resolution.get("resolution_id"),
    }
    death["last_death_save_turn_key"] = turn_key
    death["last_death_save_result"] = copy.deepcopy(death_save)
    if dead:
        death["dead"] = True
        death["stable"] = False
        game._session().character["current_hp"] = 0
        game._session().world_state["player_combat_status"] = "dead"
        death_save["death_resolution"] = game._finalize_player_death(
            "failed_death_saves"
        )
        death_save["outcome"] = (
            "rolled_back"
            if death_save["death_resolution"]["rolled_back"]
            else "dead"
        )
    else:
        death["dead"] = False
        if combat["active"]:
            game._sync_combat_participant_records(combat)
            game._validate_combat_v3_payload(combat)
        game._combat_end_if_decided()
    current_death_state = game.ensure_death_state()
    current_death_state["last_death_save_turn_key"] = turn_key
    current_death_state["last_death_save_result"] = copy.deepcopy(death_save)
    return death_save

def _spares_the_fallen(actor_id):
    import monster_combat
    npc = next((n for n in game._session().world_state.get("npcs", [])
                if isinstance(n, dict) and n.get("id") == actor_id), None)
    return isinstance(npc, dict) and monster_combat.spares_the_fallen(npc)

def _combat_end_if_decided(excluded_participant_ids=()):
    combat = game.ensure_combat_state()
    world_state = game._session().world_state
    if not combat["active"]:
        return None
    death = game.ensure_death_state()
    if death["dead"] or world_state.get("player_combat_status") == "dead":
        return game.end_combat("player_dead")
    # Retaining a death boundary is not the same as being able to fight.
    # Preserve the existing lifecycle's no-active-opponents end decision.
    active_enemies = [
        r for r in combat["participant_records"]
        if r["id"] != "player" and r["id"] not in excluded_participant_ids
        and r["status"] == "active" and r["current_hp"] > 0
    ]
    has_active_enemy = bool(active_enemies)
    if death["stable"] and all(game._spares_the_fallen(r["id"]) for r in active_enemies):
        return game.end_combat("player_stable")
    if not has_active_enemy and (
        game._session().character.get("current_hp", 0) <= 0
        or world_state.get("player_combat_status") == "unconscious"
    ):
        combat["status"] = "death_resolution"
        return None
    if not has_active_enemy:
        relocated = any(r.get("status") == "inactive" for r in combat["participant_records"])
        reason = "opponents_relocated" if relocated else "participants_left" if excluded_participant_ids else "target_defeated"
        return game.end_combat(reason)
    combat["status"] = "active"
    return None

def _resolve_enemy_turns_until_player():
    """Run NPC turns until the player's slot; a dying player rolls that turn's save themselves."""
    actions = []
    actions.extend(game._session().world_state.pop("monster_interrupt_results", []))
    combat = game.ensure_combat_state()
    limit = max(64, len(combat["initiative_order"]) * 64)
    steps = 0
    while combat["active"]:
        steps += 1
        if steps > limit:
            raise RuntimeError("Combat scheduler failed to return control to player.")
        actor_id = combat["current_actor_id"]
        if actor_id == "player":
            death = game.ensure_death_state()
            if death["dead"]:
                game.end_combat("player_dead")
                break
            if game._session().character.get("current_hp", 0) > 0:
                break
            if death["stable"]:
                game._combat_end_if_decided()
            break

        if not game._combat_participant_can_act(combat, actor_id):
            advanced, _, _ = game.advance_combat_turn()
            if not advanced:
                break
            combat = game.ensure_combat_state()
            ended = game._combat_end_if_decided()
            if ended:
                break
            continue
        npc = next(
            (item for item in game._session().world_state.get("npcs", [])
             if isinstance(item, dict) and item.get("id") == actor_id),
            None,
        )
        if npc is None:
            raise ValueError("Current combat actor is missing from canonical state.")
        # Historical zero-HP unconscious NPCs remain unconscious. They cannot act,
        # but no longer hold the cursor hostage or acquire player death saves.
        if not action_economy.can_act(game._session(), actor_id):
            game._mark_combat_action_used(actor_id)
            advanced, _, _ = game.advance_combat_turn()
            if not advanced:
                break
            continue
        import monster_combat
        monster_turn = monster_combat.run_turn(game._session(), actor_id)
        actions.extend(monster_turn["outcomes"])
        combat = game.ensure_combat_state()
        if not combat["active"]:
            break
        if not action_economy.ensure(game._session())[actor_id]["base_action_spent"]:
            game._mark_combat_action_used(actor_id)
        if any(action.get("action") == "enemy_attack" for action in monster_turn["outcomes"]):
            action_economy.publish_event(game._session(), "actor_attacks", actor_id)
        actions.extend(game._session().world_state.pop("monster_interrupt_results", []))
        if action_economy.pending_reaction(game._session()):
            break
        ended = game._combat_end_if_decided()
        if ended:
            break
        advanced, _, _ = game.advance_combat_turn()
        actions.extend(game._session().world_state.pop("monster_interrupt_results", []))
        if not advanced:
            break
        combat = game.ensure_combat_state()
    return actions

def find_weapon_in_inventory(weapon_name):
    """Find a specific weapon in inventory by name/aliases."""
    world_state = game._session().world_state
    from weapon_catalog import lookup
    requested = lookup(weapon_name)
    if not requested:
        owned = [item for item in world_state.get("inventory", []) if isinstance(item, dict)
                 and item.get("item_id") == weapon_name]
        if len(owned) == 1:
            requested = lookup(owned[0].get("weapon_id", owned[0].get("name")))
    if requested:
        for item in world_state.get("inventory", []):
            identity = item.get("weapon_id", item.get("name")) if isinstance(item, dict) else item
            found = lookup(identity)
            if found and found["weapon_id"] == requested["weapon_id"]:
                return ("Kılıç" if requested["weapon_id"] == "longsword" else requested["name"]), requested
    return None, None

def start_combat(player_target_npc):
    with initiative.atomic(game._session()), initiative.starting(game._session()):
        return game._start_combat_with_initiative(player_target_npc)

def _start_combat_with_initiative(player_target_npc):
    """Initialize a canonical initiative scheduler for the target and local hostiles."""
    game.require_player_can_act()
    world_state = game._session().world_state
    existing_combat = game.ensure_combat_state()
    if existing_combat["active"]:
        raise ValueError("A combat encounter is already active.")
    target = game.resolve_combat_target("", player_target_npc)
    if not target:
        raise ValueError("Combat target is not a canonical local NPC.")
    target_id = target["id"]

    enemies = []
    for npc in world_state.get("npcs", []):
        if not isinstance(npc, dict) or npc.get("location") != world_state.get("location"):
            continue
        if npc.get("id") != target_id and not (
            npc.get("hostile") is True
            or npc.get("combat_role") in ("enemy", "hostile")
        ):
            continue
        game.ensure_npc_enemy_stats(npc)
        if npc.get("combat_status") == "active" and npc.get("current_hp", 0) > 0:
            enemies.append(npc)
    if not any(npc.get("id") == target_id for npc in enemies):
        raise ValueError("Combat target is not able to fight.")

    participant_npc_ids = [npc.get("id") for npc in enemies]
    if (
        any(
            not isinstance(participant_id, str)
            or not participant_id
            or participant_id == "player"
            for participant_id in participant_npc_ids
        )
        or len(set(participant_npc_ids)) != len(participant_npc_ids)
    ):
        raise ValueError("Combat participants require unique stable IDs.")

    import barbarian_rage
    barbarian_rage.settle(game._session(), combat_active=False)
    game._capture_combat_death_checkpoint()
    participant_ids = ["player", *[npc["id"] for npc in enemies]]
    combat = world_state["combat"]
    combat.clear()
    combat.update({
        "schema_version": 3,
        "active": True,
        "status": "active",
        "combat_id": str(game.uuid4()),
        "round": 1,
        "initiative_order": list(participant_ids),
        "current_turn_index": 0,
        "current_actor_id": "player",
        "participants": participant_ids,
        "participant_records": [],
        "actions_used": [],
        "target_id": target_id,
        "end_reason": None,
    })
    import spell_preparation
    spell_preparation.close_window(game._session())  # 4C.2: a fight ends the preparation window for good
    game._clear_active_interlocutor("combat")
    for npc in enemies:
        # People in one room see the one who just hit them; no scenario has to say so.
        facts = world_state.setdefault("monster_perception", {}).setdefault(npc["id"], {})
        facts.setdefault("player", {"visible": True, "source": "same_scene"})
        npc.setdefault("distance_ft", 5)
    combat["participant_records"] = [
        game._combat_record_for_actor(
            participant_id,
            initiative=None,
            actions_used=combat["actions_used"],
        )
        for participant_id in participant_ids
    ]
    metadata = initiative.initialize(game._session(), participant_ids)
    effects = metadata.pop("effects_to_apply")
    combat.update(metadata)
    for record in combat["participant_records"]:
        record["initiative"] = combat["initiative_results"][record["id"]]["final_total"]
    initiative.apply_effects(game._session(), combat, effects)
    initiative.after_order(game._session(), combat, participant_ids)
    initiative_order = combat["initiative_order"]
    combat["current_actor_id"] = initiative_order[0]
    initiatives = {r["id"]: r["initiative"] for r in combat["participant_records"]}
    action_economy.ensure(game._session())
    action_economy.begin_turn(game._session(), combat["current_actor_id"])
    game._sync_combat_participant_records(combat)
    game._validate_combat_v3_payload(combat)

    # Preserve legacy summary keys while the API/UI adopt the scheduler projection.
    npc_initiative = initiatives.get(target_id, 0)
    player_init = initiatives["player"]
    return {
        "combat_started": True,
        "combat_id": combat["combat_id"],
        "round": 1,
        "initiative_order": initiative_order,
        "player_initiative": player_init,
        "npc_initiative": npc_initiative,
        "current_actor_id": combat["current_actor_id"],
        "turn_owner": combat["current_actor_id"],
        "target_id": target_id,
    }

def resolve_enemy_attack(target_npc):
    """Resolve one canonical local enemy attack, retaining exact HP values."""
    world_state = game._session().world_state
    combat = game.ensure_combat_state()
    if combat.get("combat_id") and not combat["active"]:
        raise combat_lifecycle.CombatRequestError("combat_closed", "Combat is closed.")
    canonical = game.resolve_combat_target("", target_npc)
    if (
        not canonical
        or canonical == "ambiguous"
        or (combat["active"] and canonical["id"] not in combat["participants"])
    ):
        if combat["active"]:
            raise combat_lifecycle.CombatRequestError("invalid_combat_target", "Enemy is not a participant.", 400)
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "invalid_target", "damage": 0}
    target_npc = game.ensure_npc_enemy_stats(canonical)
    if combat["active"]:
        action_economy.attack_permission(game._session(), target_npc["id"])
    if target_npc["combat_status"] != "active" or target_npc["current_hp"] <= 0:
        if combat["active"]:
            raise combat_lifecycle.CombatRequestError("invalid_combat_target", "Enemy cannot act.", 400)
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "invalid_target", "damage": 0}
    death = game.ensure_death_state()
    if death["dead"] or world_state["player_combat_status"] == "dead":
        return {"action": "enemy_attack", "status": "resolved", "success": False,
                "outcome": "player_dead", "damage": 0}
    if target_npc.get("weapon_id"):
        return weapon_attack.resolve(game._session(), target_npc["id"], "player", target_npc["weapon_id"])
    profile = {
        "weapon_id": "stat_block_attack", "name": "Stat-block attack",
        "kind": "melee", "category": None, "properties": [], "mastery": None,
        "damage_die": target_npc["damage_die"], "damage_dice": target_npc["damage_dice"],
        "damage_modifier": target_npc["damage_modifier"], "attack_bonus": target_npc["attack_bonus"],
        "damage_type": target_npc.get("attack_damage_type", target_npc.get("damage_type")),
        "magic_attack_bonus": 0, "magic_damage_bonus": 0,
    }
    return weapon_attack.resolve(game._session(), target_npc["id"], "player", profile=profile)

def _reduce_attack_damage_to_player(damage):
    """Existing Stone reaction; flat reduction precedes typed mitigation."""
    combat = game.ensure_combat_state()
    trait_state = game._species_trait_state()
    species_effects = []
    if damage > 0:
        if (
            game._session().character.get("species") == "Goliath"
            and game._session().character.get("giant_ancestry") == "stone"
            and trait_state.get("giant_ancestry_armed")
            and trait_state.get("giant_ancestry_uses_remaining", 0) > 0
            and damage > 0
            and (not combat["active"] or (
                action_economy.can_act(game._session(), "player")
                and not action_economy.ensure(game._session())["player"]["reaction_spent"]
            ))
        ):
            reduction = max(
                0,
                game._session().rng.randint(1, 12)
                + game._session().character.get("constitution_mod", 0),
            )
            damage = max(0, damage - reduction)
            if combat["active"]:
                action_economy.ensure(game._session())["player"]["reaction_spent"] = True
            trait_state["giant_ancestry_uses_remaining"] -= 1
            trait_state["giant_ancestry_armed"] = False
            species_effects.append(
                {
                    "trait": "stone_giant_ancestry",
                    "damage_reduced": reduction,
                    "damage_remaining": damage,
                }
            )
    return damage, species_effects

def _storm_thunder_reaction(attacker_npc, damage_taken, distance_ft):
    """Storm's Thunder (PHB 2024 PDF 191): damage taken from a creature within 60 ft; Reaction, 1d8 Thunder to it (D-132)."""
    combat = game.ensure_combat_state()
    trait_state = game._species_trait_state()
    if not (
        damage_taken > 0
        and game._session().character.get("species") == "Goliath"
        and game._session().character.get("giant_ancestry") == "storm"
        and trait_state.get("giant_ancestry_armed")
        and trait_state.get("giant_ancestry_uses_remaining", 0) > 0
        and distance_ft <= 60
        and game._session().character.get("current_hp", 0) > 0
        and (not combat["active"] or (
            action_economy.can_act(game._session(), "player")
            and not action_economy.ensure(game._session())["player"]["reaction_spent"]
        ))
    ):
        return []
    if combat["active"]:
        action_economy.ensure(game._session())["player"]["reaction_spent"] = True
    trait_state["giant_ancestry_uses_remaining"] -= 1
    trait_state["giant_ancestry_armed"] = False
    roll = game._session().rng.randint(1, 8)
    mitigation = weapon_attack.mitigate(game._session(), attacker_npc["id"], "thunder", roll)
    after = game.apply_npc_damage(attacker_npc, mitigation["final_damage"])
    return [
        {
            "trait": "storm_giant_ancestry",
            "target_id": attacker_npc["id"],
            "damage": mitigation["final_damage"],
            "damage_type": "thunder",
            "damage_die": 8,
            "raw_rolls": [roll],
            "mitigation": mitigation,
            "target_hp_after": after,
        }
    ]

def _apply_attack_damage_to_player(damage, critical, hit):
    """Existing temporary HP/species survival and Death owner handoff."""
    world_state = game._session().world_state
    death = game.ensure_death_state()
    trait_state = game._species_trait_state()
    player_hp_before = game._session().character["current_hp"]
    species_effects = []
    temporary_hp_before = trait_state.get("temporary_hit_points", 0)
    temporary_hp_absorbed = min(temporary_hp_before, damage)
    game._set_temporary_hit_points(
        temporary_hp_before - temporary_hp_absorbed,
        state=trait_state,
    )
    hp_damage = damage - temporary_hp_absorbed
    player_hp_after = max(0, player_hp_before - hp_damage)
    endurance_used = False
    killed_outright = hp_damage >= (
        player_hp_before + game._session().character["max_hp"]
    )
    if (
        player_hp_before > 0
        and
        player_hp_after == 0
        and not killed_outright
        and hp_damage > 0
        and game._session().character.get("species") in {"Orc", "Half-Orc"}
        and trait_state.get("relentless_endurance_available")
    ):
        player_hp_after = 1
        trait_state["relentless_endurance_available"] = False
        endurance_used = True
        species_effects.append(
            {"trait": "relentless_endurance", "current_hp": 1}
        )
    death_resolution = None
    if endurance_used:
        game._session().character["current_hp"] = player_hp_after
        world_state["player_combat_status"] = "active"
        death["stable"] = False
    elif hit:
        damage_result = game._apply_player_damage(
            hp_damage,
            critical=critical,
            took_damage=damage > 0,
            resolved_damage=damage,
        )
        player_hp_after = game._session().character["current_hp"]
        death_resolution = damage_result.get("death_resolution")
        player_status_after = world_state["player_combat_status"]
    else:
        player_status_after = world_state["player_combat_status"]
    if endurance_used:
        player_status_after = "active"
    concentration_check = None
    if endurance_used or hit:
        import spell_concentration
        concentration_check = spell_concentration.after_damage(game._session(), damage)  # one save per damage instance (4C.4b)
    return {"damage": damage, "target_hp_before": player_hp_before,
            "target_hp_after": player_hp_after, "target_status": player_status_after,
            "hp_damage": hp_damage,
            "temporary_hp_before": temporary_hp_before,
            "temporary_hp_absorbed": temporary_hp_absorbed,
            "temporary_hp_after": trait_state["temporary_hit_points"],
            "species_effects": species_effects,
            "death_resolution": death_resolution,
            **({"concentration_check": concentration_check} if concentration_check is not None else {})}

def end_combat(reason="combat_ended"):
    """Clear the encounter idempotently; HP and incapacitation are unchanged."""
    combat = game.ensure_combat_state()
    if not combat["active"]:
        return {"combat_ended": True, "reason": combat.get("end_reason"), "combat_id": combat.get("combat_id")}
    game._session()._surrender_strike_asked = None  # a question about a surrendered foe ends with its fight
    if reason in ("target_defeated", "parley_accepted", "opponents_relocated", "player_stable", "participants_left"):
        import xp
        game._session()._forfeit_unrecordable_xp(  # a refused award never keeps the fight going (B1, D-013)
            xp.award_defeated_combat, combat, game._session().world_state, game._session().character,
            person_kind=game.person_fight_kind,
        )
    import barbarian_rage
    barbarian_rage.settle(game._session(), combat_active=True)
    import rogue_features
    rogue_features.combat_ended(game._session())
    import spell_concentration
    spell_concentration.end(game._session(), "combat_ended")  # a first-cut spell belongs to its fight (4C.4b)
    identity = combat["combat_id"]
    combat.clear()
    combat.update(game._combat_defaults(end_reason=reason))
    combat["combat_id"] = identity
    if "attack_effects" in game._session().world_state:
        import monk_features
        for entry in game._session().world_state["attack_effects"]:
            monk_features.effect_ended(game._session(), entry)
        game._session().world_state["attack_effects"] = []
    scheduled_events.combat_finished(game._session().world_state)
    game.ensure_death_state()["combat_checkpoint"] = None
    return {"combat_ended": True, "reason": reason, "combat_id": identity}

def _begin_combat_actor_turn(participant_id):
    combat = game._session().world_state["combat"]
    combat["current_turn_index"] = combat["initiative_order"].index(participant_id)
    combat["current_actor_id"] = participant_id
    action_economy.begin_turn(game._session(), participant_id)
    import spell_concentration
    spell_concentration.settle(game._session())  # Incapacitated or its minute is over (4C.4b)
    import monster_combat
    monster_combat.begin_turn(game._session(), participant_id)
    game._sync_combat_participant_records(combat)
    game._validate_combat_v3_payload(combat)

def join_combat_participants(actor_ids):
    return initiative.join(game._session(), actor_ids)

def remove_combat_participant(actor_id):
    return initiative.leave(game._session(), actor_id)

def register_initiative_hook(event, callback):
    return initiative.register_hook(game._session(), event, callback)

def advance_combat_turn():
    """Advance initiative to the next living actor and roll over completed rounds."""
    combat = game.ensure_combat_state()
    if combat["active"]:
        if combat["current_actor_id"] == "player":
            import barbarian_rage
            barbarian_rage.end_player_turn(game._session(), combat["combat_id"],
                combat.get("turn_resources", {}).get("player", {}).get("attack_turn_counter", 0))
        weapon_attack.boundary(game._session(), combat["current_actor_id"], "end")
        action_economy.monster_event(game._session(), "after_turn", combat["current_actor_id"])
    order = combat["initiative_order"]
    if not combat["active"] or not order:
        return False, None, False
    if game._combat_end_if_decided():
        return False, None, False
    start_index = combat["current_turn_index"]
    round_changed = False
    for step in range(1, len(order) * 2 + 1):
        index = (start_index + step) % len(order)
        if index == 0:
            combat["round"] += 1
            action_economy.begin_round(game._session())
            round_changed = True
            game.ensure_campaign_clock()
            if "campaign_time" in game._session().world_state:
                game.advance_campaign_time(
                    6, "combat_round",
                    source=f"combat:{combat.get('combat_id')}:{combat['round'] - 1}",
                )
                game._sync_combat_participant_records(combat)
                if game._combat_end_if_decided():
                    return False, None, round_changed
        participant_id = order[index]
        if participant_id in combat["actions_used"]:
            continue
        if not game._combat_participant_can_act(combat, participant_id):
            continue
        game._begin_combat_actor_turn(participant_id)
        return True, participant_id, round_changed
    return False, None, round_changed

def _combat_snapshot():
    """Detached snapshot of committed encounter and player combat state."""
    world_state = game._session().world_state
    combat = game.ensure_combat_state()
    snapshot = dict(combat)
    snapshot.update(
        player_current_hp=game._session().character["current_hp"],
        player_max_hp=game._session().character["max_hp"],
        player_combat_status=world_state["player_combat_status"]
    )
    return copy.deepcopy(snapshot)

def _finish_combat_result(result, before):
    result["combat"] = game._combat_snapshot()
    result["state_changes"] = game._changed_state_fields(before)
    return result

def _public_combatant_label(identity, *, player_fallback=None, fallback=None):
    if identity == "player":
        return player_fallback or game._session().character.get("name") or "Sen"
    if isinstance(identity, str):
        npc = next((
            item for item in game._session().world_state.get("npcs", [])
            if isinstance(item, dict) and item.get("id") == identity
        ), None)
        if npc is not None:
            return living_world.public_npc_name(npc)
    if isinstance(fallback, str):
        npc = next((item for item in game._session().world_state.get("npcs", [])
                    if isinstance(item, dict) and item.get("name") == fallback), None)
        if npc is not None:
            return living_world.public_npc_name(npc)
        return fallback
    return "Rakip"

def _combat_narration(result):
    """Render mechanical outcomes in natural language without another model call."""
    if result.get("weapon_line"):  # which weapon was drawn, or which one is missing (gear), comes first
        return f"{result['weapon_line']} {game._combat_narration({k: v for k, v in result.items() if k != 'weapon_line'})}"
    if result.get("direct_response"):
        return result["direct_response"]
    target = game._public_combatant_label(result.get("target_id") or result.get("target"), fallback=result.get("target_name"))
    outcome = result.get("outcome")
    save = result.get("resolution") if result.get("unarmed_option") in ("shove", "grapple") else None
    if isinstance(save, dict) and outcome in ("hit", "miss"):
        text = game._unarmed_save_text(target, result, save)
    elif outcome == "miss":
        text = "Saldırın hedefi ıskalar."
    elif outcome in ("hit", "critical_hit"):
        kind = "kritik bir darbe" if outcome == "critical_hit" else "bir darbe"
        text = f"{target}, {kind} alır: {result.get('damage', 0)} hasar."
    elif outcome == "end_turn":
        text = "Turunu bitirirsin."
    elif outcome == "react":
        text = "Hazırladığın tepkiyi uygularsın."
        response = result.get("response")
        if isinstance(response, dict) and response.get("kind") == "move":
            text += f" {response.get('distance_ft')} fit ilerlersin."
        elif isinstance(response, dict) and response.get("outcome"):  # the readied attack's own roll and result
            text += " " + game._combat_narration({k: v for k, v in response.items()
                                             if k not in {"enemy_action", "enemy_actions", "combat"}})
    elif outcome == "decline_reaction":
        text = "Bu tepki fırsatını kullanmazsın."
    else:
        return "Bu saldırı gerçekleşmez."
    if result.get("target_status") == "dead":
        text += f" {target} ölür."
    elif result.get("target_status") == "unconscious":
        text += f" {target} bilincini kaybeder."
    # The singular field is a compatibility alias, not the complete exchange.
    enemies = result.get("enemy_actions")
    if enemies is None:
        enemies = [result.get("enemy_action") or {}]
    first = [enemy for enemy in enemies if enemy.get("before_player")]
    if first:  # an enemy who won initiative acted before the player's move: told before it
        named = len(enemies) > 1
        text = f"{game._enemy_exchange_text(first, named=named).strip()} {text}"
        text += game._enemy_exchange_text([enemy for enemy in enemies if not enemy.get("before_player")], named=named)
    else:
        text += game._enemy_exchange_text(enemies)
    resolution = game._death_resolution_from_actions(enemies)
    if resolution and resolution.get("rolled_back"):
        text += f" {game._REWOUND_LINE}"
    elif result.get("combat", {}).get("player_combat_status") == "dead":
        text += f" Ölürsün. {game._death_closing()}"
    elif result.get("combat", {}).get("player_combat_status") == "unconscious":
        text += f" {game._FALL_LINE}"
    elif outcome in ("end_turn", "react", "decline_reaction") and result.get("combat", {}).get("player_combat_status") == "active":
        combat = result["combat"]
        text += f" Bilincin açık; {combat['player_current_hp']}/{combat['player_max_hp']} canın kaldı."
    return text

def _enemy_exchange_text(enemies, named=None):
    """What the other side did; player-visible labels come from the canonical knowledge projection. An attack marked
    ``before_player`` came before the player's move and is not called a counter-attack."""
    if named is None:
        named = len(enemies) > 1
    monster_text = {
        "dodge": " Rakibin savunmaya geçer.",
        "parley_proposed": " Rakibin konuşmayı önerir; yanıtını bekler.",
        "surrender_proposed": " Rakibin teslim olmayı önerir; yanıtını bekler.",
        "flee_declared": " Rakibin bildiği çıkışa doğru çekilir.",
    }
    text = ""
    announced = set()
    for enemy in enemies:
        subject = "Rakibinin"
        first = "Rakibin"
        if named and (enemy.get("actor_id") or enemy.get("actor")):
            actor = enemy.get("actor_id") or enemy.get("actor")
            public_actor = game._public_combatant_label(actor)
            npc = next((item for item in game._session().world_state.get("npcs", [])
                        if isinstance(item, dict) and item.get("id") == actor), None)
            # Only a known name is "X adlı"; an unknown rival is told by what is seen ("Bir kervancı").
            subject = (f"{public_actor} adlı rakibinin"
                       if npc is not None and living_world.npc_name_known_to_player(npc) else None)
            first = public_actor
        if enemy.get("before_player") and enemy.get("outcome") == "miss":
            text += f" {first} senden önce davranıp saldırır; seni ıskalar."
        elif enemy.get("before_player") and enemy.get("outcome") in ("hit", "critical_hit"):
            kind = "kritik bir vuruşla " if enemy["outcome"] == "critical_hit" else ""
            text += f" {first} senden önce davranıp saldırır; {kind}sana isabet eder; {enemy['damage']} hasar alırsın."
        elif enemy.get("outcome") == "miss":
            text += (f" {subject} karşı saldırısı seni ıskalar." if subject
                     else f" {first} karşı saldırıya geçer; seni ıskalar.")
        elif enemy.get("outcome") in ("hit", "critical_hit"):
            kind = "kritik " if enemy["outcome"] == "critical_hit" else ""
            text += (f" {subject} {kind}karşı saldırısı sana isabet eder; {enemy['damage']} hasar alırsın." if subject
                     else f" {first} karşı saldırıya geçer; {kind and 'kritik bir vuruşla '}sana isabet eder; "
                          f"{enemy['damage']} hasar alırsın.")
        check = enemy.get("concentration_check")  # 4C.4b: the engine's Constitution save, told as it fell
        if isinstance(check, dict) and check.get("kept"):
            text += (f" Konsantrasyonunu korursun ({check['spell_id']}; Dayanıklılık kurtarması "
                     f"{check['total']}, ZS {check['dc']}).")
        elif isinstance(check, dict):
            text += f" Konsantrasyonun bozulur; {check['spell_id']} sona erer."
        said = (enemy.get("actor_id") or enemy.get("actor"), enemy.get("outcome"))
        if said not in announced:
            announced.add(said)
            text += monster_text.get(enemy.get("outcome"), "")
        if enemy.get("outcome") == "dash":
            import bounded_encounter
            text += bounded_encounter.visible_dash_narration(game._session(), enemy)
    return text

def _death_closing():
    """What is left after the last breath, said plainly."""
    state = game.ensure_death_state()
    start_over = "Yeni bir karakterle yeni bir maceraya başlayabilirsin."
    if state["terminal"]:
        return f"Bu kampanya burada kapandı. {start_over}"
    if state.get("last_call") is None:
        return f"Karanlığa son bir kez seslenebilirsin; duyan olur mu, kimse bilemez. Ya da {start_over[0].lower()}{start_over[1:]}"
    return start_over

def _death_save_line(save_result, enemy_actions=(), resolution=None):
    """One breath of the fight for your life, in the fiction, with the count that matters."""
    death = game.ensure_death_state()
    parts = [f"Ölüm kurtarma zarın: {save_result['roll']}."]
    blows = game._enemy_exchange_text([a for a in enemy_actions if a.get("outcome") != "dodge"]).strip()
    if (resolution or {}).get("rolled_back"):
        parts += [blows, game._REWOUND_LINE]
    elif death["dead"]:
        parts += [blows, "Son nefesin göğsünden çekiliyor, ses de ışık da uzaklaşıyor. Öldün.", game._death_closing()]
    elif save_result["outcome"] == "revived":
        parts += ["Bir anda ciğerlerine hava doluyor; gözlerini açıyorsun, canın az da olsa geri döndü.", blows]
    elif death["stable"]:
        parts += ["Kanın yavaşlıyor; bilincin kapalı ama artık ölmüyorsun.", blows]
    else:
        held = "hayata tutunuyorsun" if save_result["outcome"] == "success" else "hayat elinden kayıyor"
        parts += [f"Karanlıkta yatıyorsun, bedenin sana uymuyor; {held}.", blows,
                  f"Ölüm kurtarma: {death['successes']} başarı, {death['failures']} başarısızlık."]
    return " ".join(part for part in parts if part)

def _down_outside_combat_turn(player_input):
    """No fight is left: a dying body gets one save per turn, a stable one sleeps until it wakes."""
    game.ensure_campaign_clock()
    death = game.ensure_death_state()
    world = game._session().world_state
    waits = re.search(r"\b(?:bekl\w*|wait)\b", campaign_time.normalize(player_input))
    if death["stable"] and not (waits and "campaign_time" in world):
        raise game.PlayerCannotAct("Bilinçsiz karakter eylem gerçekleştiremez.")
    if "campaign_time" not in world:
        # A save from before the campaign clock: the turn itself is the only time there is.
        save = game._resolve_player_death_turn(noncombat_key=f"noncombat:{game.uuid4()}")
        time_result = {"death_results": [{"action": "death_save", "death_save": save}]}
    else:
        now = world["campaign_time"]["elapsed_seconds"]
        if death["stable"]:
            recovery = death["recovery"]
            try:
                asked = campaign_time.requested_duration(player_input)
            except campaign_time.DurationConflict:
                asked = None  # two lengths said: the body sleeps until it wakes, as when none is said
            seconds = asked or (max(1, recovery["at"] - now) if recovery else 3600)
        else:
            due = death["noncombat_next_save_at"]
            seconds = 6 if due is None else max(1, due - now)
        time_result = game.advance_campaign_time(seconds, "wait")
    status = world["player_combat_status"]
    saves = [item["death_save"] for item in time_result.get("death_results", [])
             if item.get("action") == "death_save" and item.get("death_save")]
    if saves:
        narration = game._death_save_line(saves[-1], resolution=saves[-1].get("death_resolution"))
    elif status == "dead":
        narration = f"Son nefesin göğsünden çekiliyor, ses de ışık da uzaklaşıyor. Öldün. {game._death_closing()}"
    elif status == "active":
        narration = "Canın bir nebze geri döndü; hâlâ yerde yatıyorsun."
    else:
        narration = "Zaman geçiyor; hâlâ bilinçsizsin."
    action_result = {"action": "death_save", "status": "resolved", "success": status == "active",
                     "outcome": status, "time": time_result}
    if saves:
        action_result["death_save"] = saves[-1]
    if game.ensure_death_state().get("last_resolution"):
        action_result["death_resolution"] = game.ensure_death_state()["last_resolution"]
    return {"narration": narration, "action_result": action_result,
            "model_calls": 0, "intent_model_calls": 0, "narrator_model_calls": 0}

def _death_resolution_from_actions(actions):
    for action in actions:
        if not isinstance(action, dict):
            continue
        resolution = action.get("death_resolution")
        if isinstance(resolution, dict):
            return copy.deepcopy(resolution)
        death_save = action.get("death_save")
        if isinstance(death_save, dict) and isinstance(
            death_save.get("death_resolution"), dict
        ):
            return copy.deepcopy(death_save["death_resolution"])
    return None
