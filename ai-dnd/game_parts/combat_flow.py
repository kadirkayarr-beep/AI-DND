import game
import action_economy
import combat_lifecycle
import copy
import effect_targeting
import talk_mode
import weapon_attack


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
    # Ensure base combat stats
    game.ensure_npc_combat_stats(npc)
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
        combat = game.ensure_combat_state()
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
