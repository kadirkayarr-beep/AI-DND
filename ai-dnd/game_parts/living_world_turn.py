import game
import campaign_time
import interaction_adventure
import json
import living_world
import adventure.play as adventure_play
import event_order
import local_dialogue
import re
import scheduled_events
import talk_front
import timed_gameplay


def ensure_campaign_clock():
    """Initialize only after Python has a registered current world scene."""
    world = game._session().world_state
    if world.get("location") in world.get("locations", {}):
        return campaign_time.initialize(world)
    return None

def _living_world_prompt_context(scene_plan=None, npc_target=None, player_input=None):
    world_state = game._session().world_state
    location_id = world_state.get("location")
    if location_id not in world_state.get("locations", {}):
        return ""
    turn_index = world_state.get("flags", {}).get("turn_index", 0)
    scene = living_world.ensure_scene_record(
        world_state, location_id, turn_index
    )
    state = living_world.ensure_scene_state(world_state)
    references = [
        {
            "id": item.get("id"),
            "lifecycle": item.get("lifecycle"),
            "description": item.get("description"),
        }
        for item in scene.get("referents", [])
        if isinstance(item, dict)
        and item.get("lifecycle") == "presented"
    ]
    conversation_focus = (
        interaction_adventure.current_conversation_focus(
            world_state, npc_target
        )
        if isinstance(npc_target, dict)
        else None
    )
    accepted_profile = None
    content = {
        "where_now": living_world.place_in_plain_words(world_state),
        "location_id": location_id,
        "location_name": game.location_display_name(location_id),
        "lore_anchor_id": (
            scene_plan.get("lore_location_id")
            if isinstance(scene_plan, dict)
            else living_world.location_anchor_id(world_state, location_id)
        ),
        "revision": scene.get("revision", 0),
        "player_position": state.get("player_position", {}),
        "active_npc_target": (
            {
                "id": npc_target.get("id"),
                "name": living_world.public_npc_name(npc_target),
                "role": living_world.public_npc_role(npc_target),
            }
            if isinstance(npc_target, dict)
            else None
        ),
        "conversation_focus": conversation_focus,
        "accepted_npc_profile": accepted_profile,
        "visible_npcs": [
            {
                "id": npc.get("id"),
                "name": living_world.public_npc_name(npc),
                "role": living_world.public_npc_role(npc),
            }
            for npc in game._scene_names(location_id)[:6]
        ],
        "features": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "kind": item.get("kind"),
                "description": item.get("description"),
                "aliases": item.get("aliases", []),
            }
            for item in living_world.visible_features(world_state, location_id)[:16]
            if isinstance(item, dict)
        ],
        "background_referents": references[:4],
        "recent_beat": scene.get("last_beat"),
    }
    if scene.get("last_beat"):
        content["recent_beat_actors"] = (
            "recent_beat içindekiler adsız yabancılar; bu olayı visible_npcs listesindeki kimseye yükleme."
        )
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))

def _observe_anchored_structure(player_input, interaction_mode=None):
    """Report a known building from stored records. Do not invent a part."""
    if not living_world.affirmative_structure_inspection(
        player_input, interaction_mode
    ):
        return None
    world_state = game._session().world_state
    current = world_state.get("location")
    current_location = world_state.get("locations", {}).get(current)
    if (
        isinstance(current_location, dict)
        and current_location.get("scene_kind") == "tavern"
        and isinstance(current_location.get("parent_location_id"), str)
    ):
        tavern = current_location
        feature_location = current_location["parent_location_id"]
    else:
        tavern = game._resolve_explicit_local_scene_parent(current, player_input)
        feature_location = current
    if not isinstance(tavern, dict):
        if living_world.affirmative_structure_inspection(
            player_input, interaction_mode
        ):
            return None
        return {
            "action": "inspect",
            "status": "not_detailed",
            "success": True,
            "state_changes": [],
            "direct_response": "Yakında inceleyebileceğin belirgin bir bina görünmüyor.",
        }
    visible, hidden = game._anchored_structure_features(
        player_input, feature_location, tavern.get("id")
    )
    if len(visible) == 1:
        feature = visible[0]
        return {
            "action": "inspect",
            "status": "observed",
            "success": True,
            "target_id": feature.get("id"),
            "state_changes": [],
            "direct_response": (
                f"{feature.get('name', 'Bu ayrıntı')}: "
                f"{feature.get('description', 'belirgin bir değişiklik yok.')}"
            ),
        }
    if len(visible) > 1:
        return {
            "action": "inspect",
            "status": "clarification",
            "success": False,
            "target_id": tavern.get("id"),
            "state_changes": [],
            "direct_response": "Hangi parçayı incelemek istediğini belirtir misin?",
        }
    if hidden:
        return {
            "action": "inspect",
            "status": "not_visible",
            "success": False,
            "target_id": tavern.get("id"),
            "state_changes": [],
            "direct_response": "Bu bakış görünür bir parça seçmiyor.",
        }
    if game._scene_detail_proposals_allowed(player_input, world_state, interaction_mode):
        return None
    door = game._venue_door_for(tavern.get("id"))
    sentences = [f"{tavern.get('name', 'Bina')} binasına bakıyorsun."]
    if isinstance(door, dict) and door.get("hidden") is not True:
        sentences.append(game._tavern_door_notice(tavern["id"]))
        sentences.append("Bu bakışın seçtiği diğer parça henüz ayrıntılandırılmamış.")
    else:
        sentences.append("Bu bakışın seçtiği parça henüz ayrıntılandırılmamış.")
    return {
        "action": "inspect",
        "status": "not_detailed",
        "success": True,
        "target_id": tavern.get("id"),
        "state_changes": [],
        "direct_response": " ".join(sentences),
    }

def resolve_scene_seating(action_input):
    """Seat the player at one visible seat here, or say why that is not possible.

    Single owner of the sit decision for the direct scene action and for the
    compound grounded action. Hidden or undiscovered features are not
    candidates (``living_world.visible_features`` is the visibility owner) and
    their names are never disclosed.
    """
    world_state = game._session().world_state
    current = world_state.get("location")
    visible = living_world.visible_features(world_state, current)
    visible_ids = {feature.get("id") for feature in visible}
    features = [
        feature for feature in game._scene_feature_match(action_input, current)
        if feature.get("id") in visible_ids
    ]
    seats = [
        feature for feature in visible
        if feature.get("kind") in ("furnishing", "seat", "table", "bench")
    ]
    target = features[0] if len(features) == 1 else (seats[0] if seats else None)
    if len(features) > 1:
        return {
            "action": "sit",
            "status": "clarification",
            "success": False,
            "state_changes": [],
            "direct_response": "Birden fazla uygun yer var; hangi masaya oturmak istediğini belirtir misin?",
        }
    if target:
        living_world.set_player_position(world_state, current, "seated", target.get("id"))
        target_name = str(target.get("name") or "seçtiğin yer").strip()
        return {
            "action": "sit",
            "status": "completed",
            "success": True,
            "target_id": target.get("id"),
            "target_name": target.get("name"),
            "state_changes": [],
            "direct_response": (
                f"“{target_name}” yakınında uygun bir yere oturup "
                "yerleşiyorsun."
            ),
        }
    return {
        "action": "sit",
        "status": "unresolved",
        "success": False,
        "state_changes": [],
        "direct_response": "Oturabileceğin uygun bir yer göremiyorsun.",
    }

def advance_campaign_time(seconds, reason, source=None, observation=None):
    world = game._session().world_state
    if type(seconds) is not int or not 0 <= seconds <= campaign_time.DAY * 365:
        raise ValueError("Resolved gameplay duration is invalid.")
    source = source or f"turn:{world.get('flags', {}).get('turn_index', 0)}"
    if "campaign_time" not in world:
        return campaign_time.advance(world, seconds, reason, source, observation=observation)
    before = campaign_time.public_time(world)
    event_order.require_complete(game.RULE_ORDER)  # K04: never discover a gap after the clock has already moved
    remaining, elapsed, known, death_results, effect_events = seconds, 0, [], [], []
    while True:
        death = game.ensure_death_state()
        now = world["campaign_time"]["elapsed_seconds"]
        zero = game._session().character["current_hp"] == 0 and not death["dead"]
        if zero and death["stable"] and death["recovery"] is None and remaining:
            game.stabilize_player()
        noncombat = zero and not death["stable"] and not world.get("combat", {}).get("active")
        if noncombat and death["noncombat_next_save_at"] is None and remaining:
            death["noncombat_next_save_at"] = now + 6
        if noncombat and death["noncombat_episode_id"] is None and remaining:
            death["noncombat_episode_id"] = str(game.uuid4())
        deadline = (death["recovery"]["at"] if zero and death["stable"] and death["recovery"]
                    else death["noncombat_next_save_at"] if noncombat else None)
        step = remaining if deadline is None else min(remaining, max(0, deadline - now))
        supplies = world.get("supplies_policy", {}).get("enabled", False)
        if supplies:
            midnight = campaign_time.DAY - (world["campaign_time"]["start_second"] + now) % campaign_time.DAY
            step = min(step, midnight)
        result = campaign_time.advance(
            world, step, reason, source,
            observation=None if zero or world.get("player_combat_status") == "unconscious" else observation,
        )
        elapsed += result["elapsed_seconds"]
        remaining -= result["elapsed_seconds"]
        known.extend(result["player_known_events"])
        # K03: timed effects consume the ACTUAL elapsed seconds of this step, once per (source, step start).
        def settle_effects(elapsed_step=result["elapsed_seconds"], step_start=now):
            effect_events.extend(game.effect_lifecycle.advance_effects(
                game._session(), elapsed_step, f"{source}@{step_start}",
                "round" if reason == "combat_round" else "clock"))

        # K04: when the death/recovery timer is due at the same moment, the recorded rule order decides which runs first.
        step_end = world["campaign_time"]["elapsed_seconds"]
        due_kind = (None if deadline is None or step_end < deadline
                    else "regeneration" if death["stable"] else "death")
        effects_first = due_kind is None or event_order.order_due_events(
            [{"event_id": "effects", "kind": "effect_expiry", "at": step_end},
             {"event_id": "death-timer", "kind": due_kind, "at": step_end}], game.RULE_ORDER,
        )[0]["event_id"] == "effects"
        if effects_first:
            settle_effects()
        if supplies:
            import equipment_economy
            condition_death = equipment_economy.process_supply_days(game._session(), now)
            if condition_death:
                death_results.extend(condition_death["death_results"])
                if not effects_first:
                    settle_effects()  # the step's time has passed; deferred effects must still consume it
                return dict(result, elapsed_seconds=elapsed, requested_seconds=seconds,
                            remaining_seconds=remaining, player_known_events=known,
                            death_results=death_results, condition_death=True, interrupted=True,
                            effect_events=effect_events)
        now = world["campaign_time"]["elapsed_seconds"]
        if deadline is not None and now >= deadline:
            if death["stable"]:
                game.heal_player(1)
                death_results.append({"action": "stable_recovery", "current_hp": 1})
            else:
                save = game._resolve_player_death_turn(
                    noncombat_key=f"noncombat:{death['noncombat_episode_id']}:{deadline}"
                )
                death_results.append({"action": "death_save", "death_save": save})
                death = game.ensure_death_state()
                if save and save.get("death_resolution", {}).get("rolled_back"):
                    return dict(result, elapsed_seconds=0, requested_seconds=seconds,
                                remaining_seconds=seconds, death_results=death_results,
                                player_known_events=[], after=campaign_time.public_time(world),
                                effect_events=effect_events)
                if game._session().character["current_hp"] == 0 and not death["dead"] and not death["stable"]:
                    death["noncombat_next_save_at"] = deadline + 6
        if not effects_first:
            settle_effects()
        if remaining == 0 or result["interrupted"] or game.ensure_death_state()["dead"]:
            break
    adventure_play.settle_session(game._session())
    return dict(result, elapsed_seconds=elapsed, requested_seconds=seconds,
                remaining_seconds=remaining, before=before, player_known_events=known,
                death_results=death_results, effect_events=effect_events)

def plan_living_world_turn(player_input, target_id=None, interaction_mode=None):
    """Resolve ordinary local actions and materialize before scoped lore lookup."""
    game._reopen_public_doors()
    world_state = game._session().world_state
    interaction_mode = game._normalize_interaction_mode(interaction_mode)
    if (getattr(game._session(), "_front_read", None) or {}).get("kind") in game._PLANNER_STAYS_OUT:
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": game._current_procedural_entity_ids()}
    anchored_structure = living_world.is_anchored_structure_inquiry(player_input)
    affirmative_anchored_inspection = (
        anchored_structure
        and living_world.affirmative_structure_inspection(
            player_input, interaction_mode
        )
    )
    # LR00 fix: a turn the grounded owner will take must not get this planner's
    # side effects first (a tavern created by a tavern search, a person made
    # the active interlocutor by an approach). The dry run writes nothing.
    import grounded_action
    if not affirmative_anchored_inspection and grounded_action.resolve_turn(
        game._session(), player_input, interaction_mode=interaction_mode, target_id=target_id, dry_run=True,
    ):
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": game._current_procedural_entity_ids()}
    exploratory_structure_question = living_world.is_exploratory_structure_question(
        player_input, interaction_mode
    )
    if anchored_structure and (
        interaction_mode in {"say", "ask_dm"}
        or (
            not exploratory_structure_question
            and not affirmative_anchored_inspection
        )
    ):
        return {
            "direct_result": {
                "action": "narrative",
                "status": "no_effect",
                "success": False,
                "state_changes": [],
                "direct_response": "Bu mesaj oyuncu tarafından açık bir inceleme olarak verilmedi; çevre ayrıntısı değiştirilmedi.",
            },
            "state_changes": [],
            "procedural_entity_ids_before": game._current_procedural_entity_ids(),
        }
    if (not world_state.get("combat", {}).get("active")
            and interaction_adventure.hint(player_input) == "plan"):
        # Planning is not a scene visit, merchant discovery or clock consumer.
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": game._current_procedural_entity_ids()}
    flags = world_state.setdefault("flags", {})
    turn_index = int(flags.get("turn_index", 0)) + 1
    before = game._world_snapshot()
    procedural_before = {
        str(entity.get("id", key))
        for key, entity in world_state.get("locations", {}).items()
        if isinstance(entity, dict)
        and entity.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
    }
    procedural_before.update(
        npc["id"] for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(npc.get("id"), str)
    )
    procedural_before.update(
        shop["id"] for shop in world_state.get("shops", [])
        if isinstance(shop, dict)
        and shop.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(shop.get("id"), str)
    )

    current = world_state.get("location")
    game.ensure_campaign_clock()
    scene_intent = living_world.affirmative_scene_intent(player_input, interaction_mode)
    scene_exploration_question = exploratory_structure_question
    suppress_anchored_action = False
    if anchored_structure:
        if affirmative_anchored_inspection:
            scene_intent = ("inspect", player_input)
        elif not scene_exploration_question:
            scene_intent = None
            suppress_anchored_action = True
    # Keep action authority and target resolution in the same clause. A question
    # or declined verb elsewhere in the turn cannot authorize another actor.
    action_input = scene_intent[1] if scene_intent else player_input
    action = scene_intent[0] if scene_intent else living_world.classify_scene_action(player_input)
    if action == "sit" and (getattr(game._session(), "_front_read", None) or {"kind": "sit"})["kind"] != "sit":
        action = None  # a line read as something else only has the word otur in it
    if scene_intent is None and action == "enter":
        action = None
    if interaction_mode == "say":
        action = None
    elif interaction_mode == "ask_dm" and action not in {"presence", "look"}:
        action = None
    if (action == "presence" and interaction_mode == "ask_dm"
            and (_front_say := talk_front.current(game._session())) is not None
            and _front_say.get("asks") == "person" and talk_front.spoken_to(_front_say, game.active_npcs()) is not None):
        action = None  # D-326: "Çavuş, bu gece kim var?" is asked of the person the reading names, not a scene list
    if (
        action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not world_state.get("combat", {}).get("active")
        and game._names_current_local_exit(action_input)
    ):
        action = "exit"
    inspect_action = bool(
        not suppress_anchored_action
        and
        interaction_mode not in {"say", "ask_dm"}
        and isinstance(action_input, str)
        and re.search(r"(?:incel\w*|gözden geçir\w*|inspect|examine)", action_input, re.IGNORECASE)
        and not re.search(r"(?:perception|investigation|algı kontrolü|araştırma kontrolü)", action_input, re.IGNORECASE)
    )
    if inspect_action:
        action = "inspect"
    elif suppress_anchored_action:
        action = None
    shop_request = (
        interaction_mode not in {"say", "ask_dm"}
        and target_id is None
        and game._explicit_campaign_shop_request(player_input)
    )
    normalized_input = game._normalize_turkish_typos(str(player_input))
    explicit_local_npc_reference = any(
        isinstance(npc, dict)
        and (
            (
                living_world.npc_name_known_to_player(npc)
                and game._entity_reference_in_text(npc.get("name", ""), player_input)
            )
            or (
                living_world.npc_role_known_to_player(npc)
                and game._entity_reference_in_text(npc.get("role", ""), player_input)
            )
        )
        for npc in game.active_npcs(current)
    )
    addressed_local_dialogue = bool(
        (
            interaction_mode == "say"
            and (target_id is not None or explicit_local_npc_reference)
        )
        or (
            (target_id is not None or explicit_local_npc_reference)
            and (
                game.is_npc_dialogue_input(player_input)
                or re.search(
                    r"\b(?:sor\w*|konus\w*|soyle\w*|de\w*|seslen\w*|hitap\s+et\w*)\b",
                    normalized_input,
                )
            )
        )
    )
    tavern_search = (
        interaction_mode not in {"say", "ask_dm"}
        and not shop_request
        and not addressed_local_dialogue
        and living_world.is_tavern_search(player_input)
        # LR00 fix: "başka bir han biliyor musun?" asks a person, it is not the
        # player searching the streets (the P6-style answer was always the
        # same inn).
        and not re.search(r"\b(?:biliyor|bilir|tanir|tanirsin|onerir|gosterir)\s*m[iu]s[iu]n\b", normalized_input)
        # "Bu çevrede bir han var mı?" with someone here is asked of them.
        and not (game._reads_as_question(player_input) and game.active_npcs(current))
    )
    merchant_search = (
        interaction_mode not in {"say", "ask_dm"}
        and not shop_request
        and not addressed_local_dialogue
        and living_world.is_merchant_search(player_input)
    )
    scene_attention = bool(
        action
        or tavern_search
        or merchant_search
        or re.search(
            r"(?:barmen|muhafız|guard|bartender|kapıdaki|yolcu|ziyaretçi|"
            r"masa|bardak|ona|onunla|same table)",
            str(player_input),
            re.IGNORECASE,
        )
    )
    targetless_entry_reference = None
    entry_text = living_world._text_outside_quotes(action_input)
    if (
        action == "enter"
        and target_id is None
        and game.resolve_location_reference(entry_text) is None
        and not living_world.has_tavern_reference(entry_text)
    ):
        targetless_entry_reference = living_world.resolve_entry_target_reference(
            world_state,
            current_location_id=current,
            next_turn_index=turn_index,
        )
    combat = game.ensure_combat_state()
    if current in world_state.get("locations", {}) and (
        scheduled_events.pending_events(world_state)
        or
        campaign_time.names_duration(player_input)
        or timed_gameplay.explicit_wait_request(player_input)
        or timed_gameplay.clock.normalize(player_input).startswith(
            ("sabaha kadar", "yola devam", "yolculuga devam", "geri don")
        )
    ):
        # Do not perform an instant scene inspection before a bounded task.
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": procedural_before}
    if (
        scene_attention
        and action in {"look", "wait", "enter", "exit", "sit", "stand", "approach", "inspect"}
        and interaction_mode not in {"say", "ask_dm"}
        and scene_intent
        and not (merchant_search and any(
            isinstance(shop, dict) and shop.get("location") == current
            for shop in world_state.get("shops", [])
        ))
        and not combat.get("active")
        and current in world_state.get("locations", {})
        and not (
            targetless_entry_reference
            and game._venue_entry_door(
                world_state, current, targetless_entry_reference["location_id"]
            )
        )
    ):
        scene = living_world.ensure_scene_record(world_state, current, turn_index)
        if scene.get("last_visit_turn") is None:
            living_world.record_scene_visit(world_state, current, turn_index)
        living_world.materialize_scene(
            world_state,
            current,
            turn_index,
            create_npc=game.create_npc_from_ai,
            create_feature=game.create_local_feature,
        )

    direct = None
    resolved_npc = None
    deferred_referent_id = None
    if (
        not combat.get("active")
        and living_world.is_anchored_structure_inquiry(action_input)
    ):
        direct = game._observe_anchored_structure(action_input, interaction_mode)
    if not combat.get("active") and direct is None and tavern_search:
        root_location = current
        while game._engine_location_parent(root_location):
            root_location = game._engine_location_parent(root_location)
        tavern = game._ensure_local_tavern(root_location)
        if tavern:
            grounded_action.note_last(world_state, tavern["id"])
            direct = {
                "action": "local_search",
                "status": "found",
                "success": True,
                "target_id": tavern["id"],
                "target_name": tavern["name"],
                "state_changes": [],
                "direct_response": (
                    f"Yakınlarda {tavern['name']} adlı küçük bir han buluyorsun. "
                    + game._tavern_door_notice(tavern["id"])
                ),
            }

    if (
        not combat.get("active")
        and current in world_state.get("locations", {})
        and merchant_search
    ):
        merchant, shop = game._ensure_local_merchant(current, create=False)
        if merchant and shop:
            game._set_scene_active_npc(merchant, turn_index)
            direct = {
                "action": "local_search",
                "status": "found",
                "success": True,
                "target_id": merchant["id"],
                "shop_id": shop["id"],
                "state_changes": [],
                "direct_response": (
                    f"Yakında {living_world.public_shop_name(world_state, shop)} var. "
                    f"{living_world.public_npc_name(merchant)} başında duruyor."
                ),
            }
        elif direct is None:
            direct = {
                "action": "local_search",
                "status": "unavailable",
                "success": False,
                "state_changes": [],
                "direct_response": "Yakınlarda tüccara benzer kimseyi görmüyorsun.",
            }

    if not combat.get("active") and action == "enter":
        text = str(entry_text)
        candidate = None
        explicit_tavern_target = living_world.has_tavern_reference(text)
        named_candidate = game.resolve_location_reference(text)
        named_record = world_state.get("locations", {}).get(named_candidate, {})
        if target_id is not None:
            candidate = target_id
        elif (isinstance(named_record, dict)
              and named_record.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"):
            # An existing canonical destination wins over a generic venue noun.
            # Never substitute/create another inn for a named shop or locked door.
            candidate = named_candidate
        elif explicit_tavern_target:
            root_location = current
            while game._engine_location_parent(root_location):
                root_location = game._engine_location_parent(root_location)
            existing_tavern = game._ensure_local_tavern(
                root_location, open_for_entry=True
            )
            candidate = existing_tavern.get("id") if existing_tavern else None
        if candidate is None:
            candidate = named_candidate
        if (
            candidate is None
            and target_id is None
            and not explicit_tavern_target
            and targetless_entry_reference
        ):
            candidate = targetless_entry_reference["location_id"]
        candidate_record = world_state.get("locations", {}).get(candidate, {})
        if (
            candidate
            and candidate != current
            and isinstance(candidate_record, dict)
            and candidate_record.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            and candidate_record.get("parent_location_id") == current
        ):
            entry = grounded_action.enter_existing_place(game._session(), candidate, player_input)
            direct = {
                "action": "enter",
                "status": entry["status"],
                "success": entry["status"] == "completed",
                "target_id": candidate,
                "state_changes": [],
                "direct_response": entry["text"],
                **({"arrival_narration": entry["arrival_narration"]} if entry.get("arrival_narration") else {}),
            }
        elif (
            candidate == current
            and isinstance(candidate_record, dict)
            and direct is None
        ):
            direct = {
                "action": "enter",
                "status": "already_inside",
                "success": True,
                "target_id": candidate,
                "state_changes": [],
                "direct_response": (
                    "Zaten buradasın. "
                    + game._scene_presence_text(candidate)
                ),
            }
        elif (
            direct is None
            and isinstance(world_state.get("locations", {}).get(current), dict)
            and world_state["locations"][current].get("scene_kind") == "tavern"
        ):
            current_record = world_state["locations"][current]
            direct = {
                "action": "enter",
                "status": "already_inside",
                "success": True,
                "target_id": current,
                "state_changes": [],
                "direct_response": (
                    "Zaten içeridesin. "
                    + game._scene_presence_text(current)
                ),
            }
        elif direct is None and explicit_tavern_target:
            direct = {
                "action": "enter",
                "status": "unresolved",
                "success": False,
                "state_changes": [],
                "direct_response": "Girebileceğin belirgin bir yer göremiyorsun.",
            }

    if not combat.get("active") and action == "exit":
        current_record = world_state.get("locations", {}).get(current, {})
        parent = (
            current_record.get("exit_location_id")
            or current_record.get("parent_location_id")
            if isinstance(current_record, dict)
            else None
        )
        if isinstance(parent, str) and parent in world_state.get("locations", {}):
            game.commit_location_change(parent, turn_index=turn_index)
            direct = {
                "action": "exit",
                "status": "completed",
                "success": True,
                "target_id": parent,
                "state_changes": [],
                "direct_response": (
                    f"{game.location_display_name(parent)} tarafına çıkıyorsun. "
                    + game._scene_presence_text(parent)
                ),
            }
        elif direct is None:
            direct = {
                "action": "exit",
                "status": "unresolved",
                "success": False,
                "state_changes": [],
                "direct_response": "Zaten dışarıdasın; sokak önünde uzanıyor.",
            }

    if not combat.get("active") and not direct:
        ref_resolution = living_world.resolve_scene_referent(
            world_state, str(action_input), turn_index
        )
        referent = ref_resolution.get("referent")
        if ref_resolution["status"] == "expired" and game._active_interlocutor() is None:
            direct = {
                "action": "referent",
                "status": "expired",
                "success": False,
                "state_changes": [],
                "direct_response": (
                    "Az önce gördüğün kişi ortalıkta yok artık."
                ),
            }
        elif ref_resolution["status"] == "ambiguous":
            if game._has_explicit_attack_verb(action_input):
                direct = {
                    "action": "attack",
                    "status": "clarification",
                    "success": False,
                    "outcome": "ambiguous_target",
                    "state_changes": [],
                    "direct_response": "Birden fazla kişi bu tarife uyuyor. Kime saldırmak istiyorsun?",
                }
            else:
                direct = {
                    "action": "referent",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    "direct_response": "Birden fazla kişi bu tarife uyuyor. Hangisini kastettiğini biraz daha tarif eder misin?",
                }
        elif ref_resolution["status"] in ("found", "promoted") and referent and not any(
            game._words_fit_person(npc, game._normalize_turkish_typos(str(action_input))) for npc in game.active_npcs()
        ):
            # "Tezgâhtaki adam" is the barkeep who stands there, not a passer-by of the moment.
            if game._is_scene_referent_activity_observation(action_input):
                description = referent.get("description")
                direct = {
                    "action": "explore",
                    "explore_type": "observe",
                    "status": "observed",
                    "success": True,
                    "target_id": referent.get("id"),
                    "state_changes": [],
                    "direct_response": (
                        description.strip()
                        if isinstance(description, str) and description.strip()
                        else "Belirgin bir değişiklik fark etmiyorsun."
                    ),
                }
            elif scene_intent and (
                action == "approach" or game._has_explicit_attack_verb(action_input)
                or re.search(r"\b(?:konus\w*|seslen\w*|selam\w*|sor\w*|talk|speak|greet)\b", game._normalize_turkish_typos(str(action_input)))
            ):
                if (
                    ref_resolution["status"] == "found"
                    and action != "approach"
                    and not game._has_explicit_attack_verb(action_input)
                    and game.active_npcs()
                ):
                    # Greeting with someone visible here: the model's checked pick of
                    # that person wins over a word of the happening; the turn creates
                    # the happening's person only if the model names nobody.
                    deferred_referent_id = referent.get("id")
                else:
                    resolved_npc = game._promote_scene_referent(referent, current)
                if resolved_npc:
                    game._set_scene_active_npc(resolved_npc, turn_index)
                elif action == "approach" and not game.is_npc_dialogue_input(action_input):
                    direct = {
                        "action": "approach",
                        "status": "unavailable",
                        "success": False,
                        "state_changes": [],
                        "direct_response": "Kalabalıkta o kişiye yaklaşacak yer bulamıyorsun.",
                    }

    world_subject_question = (
        True if interaction_mode == "ask_dm"
        else False if interaction_mode == "say"
        else local_dialogue.is_world_subject_question(action_input)
    )
    if (
        not combat.get("active")
        and not direct
        and action != "presence"
        and action != "look"
        and not world_subject_question
        and not scene_exploration_question
        # A character-sheet question has no NPC subject to disambiguate.
        and not game.known_character_answer(action_input)
    ):
        if target_id is not None:
            resolved_npc = next(
                (
                    npc for npc in (game._conversation_npcs() if interaction_mode == "say" else game.active_npcs())
                    if isinstance(npc, dict) and npc.get("id") == target_id
                ),
                None,
            )
        if resolved_npc is None and interaction_mode == "say" and target_id is not None:
            direct = {
                "action": "dialogue", "status": "clarification", "success": False,
                "state_changes": [],
                "direct_response": "Kiminle konu\u015fmak istiyorsun?",
            }
        # A deferred happening's person is decided by the turn's own resolver and the model.
        if resolved_npc is None and not direct and deferred_referent_id is None:
            npc_resolution = game.resolve_npc_reference(
                action_input, **({"force_dialogue": True} if interaction_mode == "say" else {})
            )
            if npc_resolution.get("status") == "ambiguous":
                if (
                    interaction_mode not in {"say", "ask_dm"}
                    and game._has_explicit_attack_verb(action_input)
                ):
                    direct = {
                        "action": "attack",
                        "status": "clarification",
                        "success": False,
                        "outcome": "ambiguous_target",
                        "state_changes": [],
                        "direct_response": game.npc_ambiguity_response(npc_resolution),
                    }
                else:
                    npc_resolution = game._settle_address(npc_resolution, action_input)
            if npc_resolution.get("status") == "found":
                resolved_npc = npc_resolution.get("npc")
            elif (
                action == "approach"
                and game._GENERIC_PERSON.search(game._normalize_turkish_typos(str(action_input)))
            ):
                # "Yakınımdaki birine yaklaşıyorum": any person will do, so pick one.
                resolved_npc = game.most_plausible_addressee(game.active_npcs(), action_input)
            elif action == "approach" and npc_resolution.get("absent"):
                direct = {
                    "action": "approach",
                    "status": "unavailable",
                    "success": False,
                    "state_changes": [],
                    "direct_response": game._absent_person_text(npc_resolution["absent"]),
                }

    if not combat.get("active") and not direct:
        if action == "presence" and current in world_state.get("locations", {}):
            # "Who is here?" can be the first thing asked in a scene nobody has looked at yet.
            living_world.materialize_scene(
                world_state,
                current,
                turn_index,
                create_npc=game.create_npc_from_ai,
                create_feature=game.create_local_feature,
            )
            direct = {
                "action": "query",
                "query_type": "presence",
                "status": "answered_from_current_scene",
                "success": True,
                "state_changes": [],
                "direct_response": game._scene_presence_text(current),
            }
        elif action == "look":
            look_location = (
                current
                if current in world_state.get("locations", {})
                else (game.resolve_location_reference(current) if isinstance(current, str) else None)
            )
            if look_location and look_location in world_state.get("locations", {}):
                direct = {
                    "action": "explore",
                    "status": "observed",
                    "success": True,
                    "state_changes": [],
                    "direct_response": (
                        living_world.visible_contents_text(world_state)
                        if living_world.is_visible_contents_query(player_input)
                        else game._scene_look_text(look_location)
                    ),
                    **({"explore_type": "observe"}
                       if living_world.is_visible_contents_query(player_input) else {}),
                }
        elif action == "approach":
            import grounded_action
            speech_part = "?" in str(action_input) or grounded_action.spoken_request(
                action_input
            ) or re.search(
                r"\b(?:sor\w*|selam\w*|anlat\w*|soyle\w*|danis\w*)\b",
                game._normalize_turkish_typos(str(action_input)),
            ) or re.search(
                # "Birine yaklaşıyorum. Selamlar, ismin nedir?": the rest speaks to that person.
                r"\b(?:ismin|adin|isminiz|adiniz|kimsin|kimsiniz|nasilsin|nerelisin|misin|musun)\b",
                game._normalize_turkish_typos(str(player_input)),
            )
            if resolved_npc and speech_part:
                # "Marek'e yaklaşıp arşivi soruyorum": walking up is the first
                # half of one compound move; the question must not be dropped.
                game._set_scene_active_npc(resolved_npc, turn_index)
                living_world.set_player_position(
                    world_state, current, "standing", resolved_npc["id"]
                )
                resolved_npc["distance_ft"] = 5
                direct = None
            elif resolved_npc:
                game._set_scene_active_npc(resolved_npc, turn_index)
                # Approaching a visible NPC is a Python-owned local positioning fact.
                # Record conversation/melee proximity explicitly so a later hostile
                # decision can use the existing combat owner without guessing range.
                living_world.set_player_position(
                    world_state, current, "standing", resolved_npc["id"]
                )
                resolved_npc["distance_ft"] = 5
                direct = {
                    "action": "approach",
                    "status": "completed",
                    "success": True,
                    "target_id": resolved_npc["id"],
                    "target_name": living_world.public_npc_name(resolved_npc),
                    "state_changes": [],
                    "direct_response": (
                        f"{living_world.public_npc_name(resolved_npc)} seni fark edip "
                        "sana dönüyor."
                    ),
                }
            else:
                direct = {
                    "action": "approach",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    # LR00 fix: a place, door or detail is as valid a target
                    # as a person; name all of them, not people only.
                    "direct_response": __import__("grounded_action").clarification_text(game._session()),
                }
        elif action == "sit":
            direct = game.resolve_scene_seating(action_input)
        elif action == "stand":
            living_world.set_player_position(world_state, current, "standing")
            direct = {
                "action": "stand",
                "status": "completed",
                "success": True,
                "state_changes": [],
                "direct_response": "Ayağa kalkıyorsun.",
            }
        elif action == "wait":
            beat = living_world.note_wait(world_state, current, turn_index)
            direct = {
                "action": "wait",
                "status": "completed",
                "success": True,
                "state_changes": [],
                "direct_response": beat,
            }
        elif action == "inspect":
            selected_feature = next(
                (
                    feature for feature in world_state.get("features", [])
                    if isinstance(feature, dict)
                    and feature.get("id") == target_id
                    and feature.get("location") == current
                ),
                None,
            )
            features = (
                [selected_feature]
                if selected_feature is not None
                else game._scene_feature_match(action_input, current)
            )
            if len(features) == 1:
                direct = {
                    "action": "inspect",
                    "status": "observed",
                    "success": True,
                    "target_id": features[0].get("id"),
                    "state_changes": [],
                    "direct_response": (
                        f"{features[0].get('name', 'Bu ayrıntı')}: "
                        f"{features[0].get('description', 'belirgin bir değişiklik yok.')}"
                    ),
                }
            elif len(features) > 1:
                direct = {
                    "action": "inspect",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    "direct_response": "Hangi ayrıntıyı incelemek istediğini belirtir misin?",
                }

    current = world_state.get("location")
    lore_location_id = living_world.location_anchor_id(world_state, current)
    lore_state = getattr(game._session(), "lore_authority_context", None)
    if lore_location_id is None and isinstance(lore_state, dict):
        lore_location_id = lore_state.get("current_location_id")
    changes = game._changed_state_fields(before)
    if direct:
        direct["state_changes"] = list(dict.fromkeys(
            direct.get("state_changes", []) + changes
        ))
    return {
        "action": action,
        "direct_result": direct,
        "npc_target_id": resolved_npc.get("id") if isinstance(resolved_npc, dict) else None,
        "deferred_referent_id": deferred_referent_id if resolved_npc is None and not direct else None,
        "lore_location_id": lore_location_id,
        "state_changes": changes,
        "procedural_entity_ids_before": sorted(procedural_before),
    }
