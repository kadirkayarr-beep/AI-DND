import timed_gameplay
import scheduled_events
import campaign_time
import re
import living_world
import game


def _lw_presence_look(*, action, action_input, combat, current, direct, player_input, resolved_npc, target_id, turn_index, world_state):
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
    return direct


def _lw_scene_answer(*, action, action_input, combat, deferred_referent_id, direct, interaction_mode, resolved_npc, scene_exploration_question, target_id, world_subject_question):
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
    return direct, resolved_npc


def _lw_scene_referent(*, action, action_input, combat, current, deferred_referent_id, direct, resolved_npc, scene_intent, turn_index, world_state):
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
    return deferred_referent_id, direct, resolved_npc


def _lw_merchant_direct(*, combat, current, direct, merchant_search, turn_index, world_state):
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
    return direct


def _lw_attention_direct(*, action, combat, current, interaction_mode, merchant_search, scene_attention, scene_intent, targetless_entry_reference, turn_index, world_state):
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


def _lw_time_gate(*, current, player_input, procedural_before, world_state):
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
    return game._TURN_FALL_THROUGH


def _lw_targetless_entry(*, action, current, entry_text, target_id, targetless_entry_reference, turn_index, world_state):
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
    return targetless_entry_reference


def _lw_scene_attention(*, action, merchant_search, player_input, tavern_search):
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
    return scene_attention


def _lw_tavern_search(*, addressed_local_dialogue, current, interaction_mode, normalized_input, player_input, shop_request):
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
    return tavern_search


def _lw_addressed_dialogue(*, explicit_local_npc_reference, interaction_mode, normalized_input, player_input, target_id):
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
    return addressed_local_dialogue


def _lw_explicit_npc_ref(*, current, player_input):
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
    return explicit_local_npc_reference


def _lw_anchored_exit(*, affirmative_anchored_inspection, anchored_structure, exploratory_structure_question, interaction_mode):
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
    return game._TURN_FALL_THROUGH
