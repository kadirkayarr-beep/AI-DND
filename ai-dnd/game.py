if __name__ == "__main__":
    import game
    from game_parts import terminal
    raise SystemExit(terminal.run(input_fn=input, print_fn=print))
import ollama
import random
import json
import re
import unicodedata
import collections
import copy
import equipment_economy
import refusals
import tr_case
import tr_names
from pathlib import Path
import hashlib
import os
import tempfile
import contextlib
import contextvars
import functools
import sys
import types
from uuid import uuid4
from quest_catalog import catalog as quest_catalog, find_quest
import adventure
import adventure.director as adventure_director
import adventure.play as adventure_play
import incidents.hooks as incident_hooks
import incidents.projection as incident_projection
import living_world
import local_dialogue
import local_exploration
import held_weapon
import monster_sense
import name_catalog
import campaign_time
import scheduled_events
import timed_gameplay
import combat_lifecycle
import action_economy
import initiative
import weapon_attack
import effect_targeting
import attributed_claims
import effect_lifecycle
import event_order
import interaction_adventure
import money_owner
import talk_front
import npc_statements
import talk_mode
from weapon_catalog import WEAPONS
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from api.dnd_2024_rules import get_expertise_choice_count
from api.core_resolution import (
    resolution_action_scope,
    resolve_attack_roll,
    resolve_death_save,
    resolve_saving_throw,
    resolve_skill_check,
)

from game_parts.turn import ResolvedTurn, DEBUG_MODE, TurnResolved, turn_source_key, run_player_turn, _run_player_turn_owned, _run_player_turn, _run_player_turn_keyed, _dispatch_player_turn, _dispatch_turn_body, _spoken_rest_of_turn, _current_procedural_entity_ids, _keep_town_portrait


from game_parts.text_rules_a import ollama_response_content, ollama_reply_was_cut, _ASKS_SOMETHING, _just_served, _THIRD_PERSON_REPORT, _SECOND_PERSON_SAID, _SAID_IT_AGAIN, _ENDS_IN_SPEECH, is_ordinary_environment_look, npc_ambiguity_response, _NEGATED_VERB_SUFFIX, _affirmative_door_verb, _SKILL_CHECK_WORD, _SKILL_ENDING, _ABILITY_WORD, _OPEN_SCARE, _COVER_WORD, _COVER, _OWN_THING_HIDDEN, _READING_CHECKS, _COMMON_SENTENCE_OPENERS, _QUESTION_CUE_RE, clean_dm_response, _hand_names_something, _ARMED_ROLE, _STRONG_ROLE, _PERSON_FIGHT, _clean_world_text, _scene_texts_for_referents, _ENGLISH_STOP_WORDS, _reads_english, _SAVE_ABILITY_TR, _unarmed_save_text, _FALL_LINE, _REWOUND_LINE, _PROPOSAL_MARKER_RE, _INTERNAL_MARK_RE, _strip_proposal_markers, _normalize_interaction_mode, _GUARD_ROLE, _GUARD_WORD, _GENERIC_PERSON, _is_guard, _serves_at_a_counter, _topic_place_name, _LOCATED_PERSON, _IN_REACH_WORDS, _COUNTER_WORDS, _COUNTER_ROLE, _drop_repeated_sentences


# ---------------------------------------------------------
# ZAR SİSTEMİ
# ---------------------------------------------------------

from game_parts.character_rules import roll_d20


from game_parts.character_rules import get_modifier, roll_stat, choose_option, create_random_character, assign_stats, choose_skill_proficiencies, calculate_hp, calculate_ac, _perform_skill_check, _new_species_trait_state, _new_persisted_species_trait_state, initialize_species_trait_state, calculate_attack_bonus, roll_attack, roll_damage, _species_trait_state, roll_initiative, roll_initiative_npc, roll_initiative_player


# ---------------------------------------------------------
# IRKLAR
# ---------------------------------------------------------

from game_parts.tables import RACES, RACE_FEATURES, CLASSES, CLASS_FEATURES, CLASS_HIT_DICE, SKILLS, CLASS_SKILL_OPTIONS, DIFFICULTY_DC, RANDOM_NAMES, GIANT_ANCESTRY_IDS, CELESTIAL_REVELATION_FORMS, INNER_RADIANCE_SPEC, NECROTIC_SHROUD_SPEC, SPECIES_WITH_TRAIT_STATE, _ABILITY_NAMES, _ORIGIN_TEXT_KEYS, _ORIGIN_LIST_KEYS, _ORIGIN_SCORE_KEYS, DEATH_MODES, CHECK_FEATURES


# ---------------------------------------------------------
# IRK ÖZELLİKLERİ
# ---------------------------------------------------------


# ---------------------------------------------------------
# SINIFLAR
# ---------------------------------------------------------


# ---------------------------------------------------------
# SINIF ÖZELLİKLERİ
# ---------------------------------------------------------


# ---------------------------------------------------------
# HIT DICE
# ---------------------------------------------------------


# ---------------------------------------------------------
# SILAHLAR
# ---------------------------------------------------------

# ---------------------------------------------------------
# SKILLER
# ---------------------------------------------------------


# ---------------------------------------------------------
# SINIF SKILL SEÇENEKLERİ
# ---------------------------------------------------------


# ---------------------------------------------------------
# ZORLUKLAR
# ---------------------------------------------------------


# ---------------------------------------------------------
# SEÇİM FONKSİYONU
# ---------------------------------------------------------


# ---------------------------------------------------------
# RANDOM KARAKTER İSİMLERİ
# ---------------------------------------------------------


# ---------------------------------------------------------
# STAT DAĞITIMI
# ---------------------------------------------------------


# ---------------------------------------------------------
# SKILL PROFICIENCY SEÇİMİ
# ---------------------------------------------------------


# ---------------------------------------------------------
# HP
# ---------------------------------------------------------


# ---------------------------------------------------------
# AC
# ---------------------------------------------------------


# ---------------------------------------------------------
# SKILL CHECK
# ---------------------------------------------------------

from game_parts.character_rules import perform_skill_check


# ---------------------------------------------------------
# AI EYLEM ANALİZİ
# ---------------------------------------------------------

from game_parts.intent import is_dialogue_or_emotion, _is_negated_dialogue_action, _reads_as_question, _people_speak_for_themselves, _asked_of_the_one_at_hand, is_npc_dialogue_input, _is_conversation_start_input, _is_local_place_question, _unverified_past_event_assertion, _report_of_someone_else, is_npc_historical_claim, _reported_npc_claim_followed_by_player_inspection, named_skill, open_scare_try, _stealth_skill, _word_check_for_action, known_player_action_narration, known_character_answer, _model_query_type_is_plausible, _detect_query_type, _detect_explore_type, _query_location_candidates, resolve_python_world_action, analyze_player_action, _travel_destination_reference_in_text, _intent_scene_npc_candidates, _recent_player_visible_narration, _validated_scene_npc_id, _named_word_of, _validated_local_person_proposal, _scene_detail_proposals_allowed, _scene_observation_proposal_turn, _local_person_request_key, _experimental_speech_final_line, _local_place_recommendation_guidance, IntentInfrastructureError, _has_travel_language, _travel_completion, _normalize_turkish_location


from game_parts.dialogue import _claimed_completed_outcome, _conversation_npcs, _active_interlocutor, _clear_active_interlocutor, _is_end_conversation_request, _without_place_names, _words_fit_person, most_plausible_addressee, _absent_described_person, _absent_person_text, _settle_address, _word_for_nobody_here, resolve_npc_reference, _interaction_proposal_applies, _grounded_item_request_proposal, _explicit_addressee, _is_spoken_to, _is_short_conversation_continuation, _is_object_inspection, _is_door_inspection_request, record_npc_interaction, _remember_owner_locked_tavern_focus, _remember_accepted_profile_focus, npc_memory_supports_claim, npc_memory_supporting_entry, _STOCK_SAID, _stock_said, _stock, _is_stock, _only_stock, _without_lines_already_said, historical_claim_denial, named_by_sight, _npc_speech_enabled, _experimental_recent_exchanges, _speech_answer_rules, _remember_experimental_npc_speech, _clean_npc_speech, _render_experimental_npc_speech, _npc_speech_is_claim_refusal, _npc_name_stance, _town_note, _has_spoken_to_player, _job_talk_with, _offer_terms_shown, _nobody_here, _thread_person, _physical_line, _job_gate, _town_in_play, _named_elsewhere_line, _town_fallback, _person_fallback, _experimental_npc_dialogue_context


from game_parts.coin import _SOMEONE_ELSES_PURSE, _SHOP_ECONOMY_PATTERN, _SHOP_TRANSACTION_REQUEST_PATTERN, _SHOP_ENTITY_QUERY_PATTERN, _SHOP_CREATION_ACTION_PATTERN, _is_shopkeeper_role, _runs_a_shop, _campaign_has_shopkeeper, _explicit_campaign_shop_request, _shop_economy_request, _explicit_campaign_shop_negative_request, _shop_presence_question, generate_shop_id, validate_shop_proposal, create_shop_from_proposal, COIN_LEFT_BEHIND


from game_parts.intent import deterministic_check_for_action, _handle_query, parse_player_intent, normalize_intent, update_world_state_from_player, execute_intent


# ---------------------------------------------------------
# AI DUNGEON MASTER CEVABI
# ---------------------------------------------------------


recent_dm_narrations = []
world_state = {
    "campaign_id": None,
    "location": "Henüz belirlenmedi",
    "locations": {
        "tavern": {
            "id": "tavern", "name": "Taverna", "type": "building",
            "aliases": ["taverna", "tavernaya", "tavernada", "meyhane", "meyhaneye", "meyhanede"],
            "description": "",
        },
        "forest": {
            "id": "forest", "name": "Orman", "type": "wilderness",
            "aliases": ["orman", "ormana", "ormanda"],
            "description": "",
        },
        "castle": {
            "id": "castle", "name": "Kale", "type": "building",
            "aliases": ["kale", "kaleye", "kalede"],
            "description": "",
        },
    },
    "next_location_number": 1,
    "heard_rumours": [],
    "npcs": [],
    "shops": [],
    "next_shop_number": 1,
    "inventory": ["Macera çantası", "Kılıç"],
    "equipment": {"main_hand": "longsword", "off_hand": None},
    "ground_items_by_location": {},
    "ground_items": [],
    "doors": [],
    "containers": [],
    "features": [],
    "scene_state": living_world.initial_scene_state(),
    "events": [],
    "flags": {**talk_mode.fresh(), "turn_index": 0, "pending_destination": None},
    "next_npc_number": 1,
    equipment_economy.GEAR_WRITTEN: True,  # D-231: every person of a new world gets their gear when made
    equipment_economy.PURSE_WRITTEN: True,  # D-207: and their purse
    "combat": {
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
        "end_reason": None,
    },
    "player_combat_status": "active",
    "death_state": {
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
    },
    "player_knowledge": [],
    "quests": [],
    "quest_processed_event_ids": [],
}
INITIAL_WORLD_STATE = copy.deepcopy(world_state)
from game_parts.savefile import SAVE_FORMAT_VERSION, _SUPPORTED_SAVE_VERSIONS, _validate_species_trait_state, _origin_choices_valid, _origin_choices_for_save, _PERSISTED_PLAYER_CONDITION_FIELDS, _validate_player_condition_state, _validate_player_weapon_proficiencies, _player_state_for_save, serialize_game_state, _validate_combat_v3_payload, _validate_long_rest_history, _validate_saved_multilevel_slots, _validate_save_payload, save_game, _repair_dilim1_fields, _known_happenings, _repair_dilim2_fields


# K04: the recorded order of simultaneous due items (technical decision record, see event_order.py).
RULE_ORDER = event_order.DEFAULT_RULE_ORDER


from game_parts.combat_flow import long_rest_gap_seconds, _death_state_defaults, ensure_death_state, PlayerCannotAct, require_player_can_act, stabilize_player, attempt_player_stabilization, heal_player, set_player_max_hp, apply_npc_damage, _capture_combat_death_checkpoint, _restore_combat_death_checkpoint, _finalize_player_death, _apply_player_damage, _combat_defaults, _combat_record_for_actor, _migrate_legacy_combat_state, _sync_combat_participant_records, ensure_combat_state, person_fight_kind, _person_fight, ensure_npc_enemy_stats, ensure_npc_combat_stats, resolve_combat_target, _set_temporary_hit_points, grant_temporary_hit_points, _species_bonus_action, _species_player_turn_id, _apply_species_on_hit_effects, _finish_species_player_turn


from game_parts.savefile import load_game


from game_parts.places import _tavern_door_notice, _venue_door_id, _venue_door_for, _venue_entry_door, _locked_door_refusal, _mark_lock_seen, _lock_known_to_player, _current_door, _normalize_ground_items, location_features, feature_descriptions, active_npcs, _clean_world_text_list, _has_unregistered_person_name, validate_npc_proposal, create_local_feature, _valid_local_feature_parent_id, _legacy_hidden_feature_name_collision, _local_detail_claims_unsupported_mechanics, _feature_proposal_conflicts_with_canonical_door, location_display_name, _location_alias_values, _reference_token_matches, _entity_reference_in_text, resolve_location_reference, _location_reference_in_text, normalize_location_id, validate_location_proposal, _local_place_recommendation_options, _local_place_access, _attributed_place_note, _ground_local_place_recommendation_reply, _ground_local_place_recommendation_stage, _explicit_sword_drop, update_inventory_from_player, apply_check_outcome_to_world_state, _names_current_local_exit, _engine_location_parent, _existing_local_tavern, _resolve_explicit_local_scene_parent, _scene_detail_parent, _anchored_structure_features, _ensure_local_tavern


from game_parts.narration import _narration_fact_packet, _repair_internal_marks, _filter_unaccepted_proposal_mentions, _drop_absent_counter_sentences, _narrator_fact_view, create_location_from_proposal, _current_npc_name, _quiet_place_line, _generic_no_change_response, _natural_unresolved_action_response, _unseen_speaker_repaired, should_generate_npcs, should_generate_features, _rejected_lore_narration, _feature_refs_are_visible, _ensure_venue_window, _bound_on_a_named_word, _found_on_a_pass, _inspection_findings, _repair_attributed_speech, _narration_contradicts_supported_name_memory


from game_parts.places import generate_npc_id, create_npc_from_ai, clean_location_description, commit_location_change, _ensure_location_entities, _commit_travel_action, _ensure_local_merchant, _scene_presence_text, _promote_scene_referent, _adventure_travel_reply


from game_parts.combat_flow import resolve_species_trait_action, resolve_attack, register_attack_hook, _combat_participant_can_act, _mark_combat_action_used, _resolve_player_death_turn, _spares_the_fallen, _combat_end_if_decided, _resolve_enemy_turns_until_player, find_weapon_in_inventory, start_combat, _start_combat_with_initiative, resolve_enemy_attack, _reduce_attack_damage_to_player, _storm_thunder_reaction, _apply_attack_damage_to_player, end_combat, _begin_combat_actor_turn, join_combat_participants, remove_combat_participant, register_initiative_hook, advance_combat_turn, _combat_snapshot, _finish_combat_result


from game_parts.combat_flow import _public_combatant_label, _combat_narration, _enemy_exchange_text, _death_closing, _death_save_line, _down_outside_combat_turn, _death_resolution_from_actions


from game_parts.narration import validate_world_updates, _bind_world_update_mentions, merge_world_updates, _narrator_shop_record, build_world_context, _stands_by_their_words, _fallback_narration, _dm_response_schema_for_turn


from game_parts.lore import _filter_unsupported_lore_paragraphs, _empty_lore_authority_context, _prepare_lore_authority_context, _is_registered_lore_name, _has_unregistered_narrative_entity, _stage_within_the_street, _shown_stage_direction, _unverified_lore_response, _names_the_district_here, _narration_has_unsupported_lore_claim, _repair_unsupported_lore_narration, _scene_has_registered_craft_role, _supported_lore_question_response, _player_question_has_unverified_lore_claim


from game_parts.text_rules_a import _is_plain_person_reference, _ADDRESSEE_OPERATIONS, _OFFER_OPERATIONS, _OFFER_MARKER, _fold_keep_punctuation, _ADDRESS_VERB, _SPEAKING_VERB, _CONTINUATION_TERMS, _OBJECT_INSPECTION, _claim_keywords, _format_npc_memory, _CLAIM_DENIAL_LINES, _SPEECH_REPEAT_LINES, _lines_already_said, speech_repeat_line, _NARRATOR_PROFILE_FIELDS, _narrator_visible_profile, _bodies_here_context, _untrusted_player_block, _extract_json_object, _NPC_SPEECH_LOG_KEY, _NPC_SPEECH_KEEP, _MENTIONS_PROMPT_RULE, _VOICED_PROMPT_RULE, _rumour_lane_on, _voiced_keys, _CLAIM_REJECTION_RE, _CLAIM_ACCEPTANCE_RE, _SPEECH_CUT_RE, _SPEECH_META_RE, _strip_pictographs, _REAL_WORLD_FAITH, _without_real_world_faith, _is_explicit_name_led_gesture_line, _clean_npc_stage_direction, _compose_experimental_npc_speech, _without_label_variant, _npc_speech_rejects_claim, _CLAIM_PLAIN_DENIAL_RE, _npc_speech_grants_claim, _spoken_name_answer, _SPEECH_ANSWER_RULES, _job_news_line, _turns_to_someone_else, _elsewhere_line, _overheard_work, _ASKS_WHO_YOU_ARE, _accept_named_job, _REFUSED_MOVE_RULE, _bag_note, _dm_prompt_note, _claim_denial_quotes, _has_private_profile_value, _FOLLOWUP_WORDS, _is_short_followup, _experimental_speech_recap, _normalize_turkish_typos, _mechanical_outcome, _GENERIC_NO_CHANGE_RESPONSE, _GENERIC_NO_CHANGE_RESPONSES, _INTERNAL_PLAYER_FACING_RE, _is_internal_player_facing_text, _narration_scene_type


from game_parts.dialogue import _npc_answers_to, _offer_talk_with, _job_fallback, _coin_persuasion, _show_coin_roll, _settle_spoken_commitment, _with_only_backed_money, _experimental_speech_note, _speech_after_check


from game_parts.living_world_turn import ensure_campaign_clock, _living_world_prompt_context, _observe_anchored_structure, resolve_scene_seating


from game_parts.living_world_turn import advance_campaign_time, plan_living_world_turn


from game_parts.schemas import INTENT_TYPES, SKILL_INTENT_TO_SKILL, INTENT_SCHEMA, SCENE_DETAIL_KIND_ALLOWLIST, NPC_SCHEMA, LOCATION_SCHEMA, WORLD_UPDATE_SCHEMA, DM_RESPONSE_SCHEMA, NARRATOR_VOICE, system_prompt


# SECURITY: LLM01/LLM07 (Prompt Injection, prompt-construction layer; System Prompt Leakage)
# Level: B (Moderate) | Pattern: system_prompt_template (untrusted delimiter)
# Applied by: llm-secure-patterns v1.0.0 / System Prompt Design | 2026-10-22
# Behavioral hint to the model, not an enforced boundary. The player's text is
# shown verbatim (never edited), so a faithful quote of it still equals the
# original input that interaction_adventure.resolve_conversation compares with.
# The boundary id is a digest of that exact text, so the text cannot contain its
# own matching closing tag; look-alike tags inside it stay inert text.


from game_parts.schemas import _EXPERIMENTAL_NPC_SPEECH_SCHEMA
from game_parts.schemas import _EXPERIMENTAL_NPC_SPEECH_OPTIONS


def _speech_debug_trail(record):
    """Append one JSON line per speech turn to the file named by AI_DND_SPEECH_DEBUG.

    Off unless the variable is set. It exists because a saved turn keeps only the
    shown text: when a stock line appears, this trail says what the model really
    returned and which rule replaced it. Local file only; never raises into a turn.
    """
    path = os.environ.get("AI_DND_SPEECH_DEBUG", "").strip()
    if not path or path.lower() in ("0", "off"):
        return
    try:
        import datetime as _datetime
        entry = {"at": _datetime.datetime.now(_datetime.timezone.utc).isoformat(), **record}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        return


from game_parts.turn_front import _has_session, _carry_out_thread_turn, _thread_gate, _world_snapshot, _changed_state_fields, _execute_intent_internal, _hideout_check, _adventure_scene_turn, _adventure_check_reply, _everyday_action_turn, _local_place_turn, _intent_infrastructure_result, _clear_turn_transients


from game_parts.intent import validate_intent, _names_present_creature, _has_explicit_attack_verb, _is_explicitly_negated_attack, primal_knowledge_check_admission


from game_parts.text_rules_b import _NARRATION_PERSISTENT_OBJECT_HEADS, _NARRATION_PERSISTENT_OBJECT_STATE, _registered_persistent_object_names, _HELD_SKIP, _PLAYER_MENTAL_STATE_PREFIXES, _PLAYER_MENTAL_STATE_CONTEXT_RE, _PLAYER_MENTAL_STATE_COPULA_RE, _PLAYER_MENTAL_STATE_EXPLICIT_SUBJECT_RE, _PLAYER_MENTAL_STATE_AFFECT_RE, _PLAYER_FEELING_RE, _is_figurative_key_transfer, _NARRATED_NAME_PATTERNS, _unseen_registered_names, _SPEAKING_NAME_PATTERNS, _unseen_speakers, _lore_claims_are_supported, _lore_guard_text, _lore_fact_records, _LORE_ENTITY_TITLE_RE, _LORE_PROPER_NAME_RE, _LORE_ENTITY_FOLLOWING_CUE_RE, _LORE_SENTENCE_START_WORDS, _GENERIC_SPEAKER_LABEL_RE, _is_generic_speaker_label, _LORE_UNSUPPORTED_DETAIL_PATTERNS, _LORE_RULER_TITLE_RE, _LORE_ENTITY_RELATION_RE, _LORE_ROUTE_DISTANCE_QUERY_RE, _UNVERIFIED_LORE_RESPONSE, _UNVERIFIED_DISTANCE_RESPONSE, _UNVERIFIED_RULER_RESPONSE, _INDOOR_DETAIL, _ASKS_DISTANCE, _salvage_plain_speech, _TERMINATOR_MASK, _split_sentences_keep_speech, _spoken_lore_fact_ids, _has_active_local_npc_focus_for_place_request


from game_parts.narration_safety import _unregistered_persistent_object_claim, _unregistered_held_object, _resolve_campaign_npc_reference, _unsupported_npc_history_or_relationship_claim, _unverified_player_mental_state_trigger, _authorized_item_transfer_matches, _is_explicitly_negated_transfer, _experimental_private_npc_disclosure, _unseen_self_introductions, _narration_is_unsafe, is_player_world_assertion, _record_narration_safety, _remove_trigger_sentence, _unsupported_available_quest_claim


from game_parts.text_rules_a import _inside_speech, _SPEECH_SPAN_RE


from game_parts.narration_safety import _narration_safety_decision


from game_parts.lore import _lore_entity_names


from game_parts.text_rules_b import _validated_player_line, _WINDOW_WORDS, _LOCK_WORDS, _TRACK_WORDS, _resolved_skill_result_narration, _TELLS_FAILURE, _UNMOVED, _QUOTE_CLOSER_RE, _QUOTE_OPENER_RE, _trim_dangling_quote, _dialogue_repair_has_attributed_answer, _skill_result_category, _print_skill_result, _ATTACK_VERB_PATTERN, _ATTACK_BLOW_PHRASE, _CHARGING_IN, _ATTACK_LOOKALIKE_TOKEN, _ATTACK_INSTRUMENT_TOKENS, _INANIMATE_HIT_OBJECT, _CREATURE_REFERENCE, _attack_verb_tokens, _immediate_check_refusal, _turkish_genitive_form, _asks_what_is_going_on, _is_bare_greeting, _is_scene_referent_activity_observation, _public_scene_person_text, _LOOK_OPENINGS, _CONVERSATION_OPENINGS, _OWN_ACTS, _WALKED_UP, _said_after_approach, _SAY_VERBS, _SAY_ENGLISH, _HAIL_FILLERS, _line_addresses, _PLANNER_STAYS_OUT, _NO_BLOW_NOW, _BLOW_WORDS, _word_root, _NOT_A_LOCAL_PLACE, _NARRATOR_PRONOUNS, _NARRATOR_PLURAL, _singular_narrator


from game_parts.narration import ask_dungeon_master, _finding_says_too_much, _states_the_failed_check, _fallback_for_action_result, _narrated_money_can_lie, finalize_narration


from game_parts.dialogue import _is_player_name_inquiry_to_npc, _is_historical_player_name_query, _hero_first_name, _explicit_player_name_disclosure, _known_player_name, _historical_player_name_from_npc_memory, _historical_player_name_from_claims, _direct_npc_smalltalk_response, _conversation_opening_line, _stock_hearer, _said_to_someone_here


# ---------------------------------------------------------
# OYUN BAŞLANGICI
# ---------------------------------------------------------

from game_parts.new_game import initialize_game


# ---------------------------------------------------------
# AI DUNGEON MASTER
# ---------------------------------------------------------


messages = [
    {
        "role": "system",
        "content": system_prompt
    }
]


from game_parts.places import _scene_feature_match, _scene_names, _variation_index, _look_opening, _scene_look_text, _look_scene_changed, _keep_people_in_look, _set_scene_active_npc, _reopen_public_doors, _a_walk, _walked_there, _may_propose_local_place, _accepted_local_place, _settle_local_place, _is_canonical_city_id


from game_parts.turn_front import _tell_the_coin, _the_rest_of_the_line, _person_answers_stock, _last_call, combat_refusal_turn, _approach_turn, player_cannot_act_turn, _reads_as_address, _addressed_in, _front_recovery, _front_step, _defer_spoken_coin_offer, _record_spoken_coin_response, _economic_listing, _front_economic_offer, _purchase_refused, _hand_over_coin, _coin_without_a_reading, _blow_stands, _blow_in_the_words, _ask_about_the_blow, _heavy_allowed, _ask_before_the_heavy, _answered_heavy_question, _ask_which_move, _narrated_person, front_read_ahead, _front_offer_gate, _line_gives, _front_consume


from game_parts.turn_front import _front_wield, _coin_not_parcel, _names_no_parcel, _front_hand_over, _front_work, _take_names_a_job, _front_take, _sleep_after_walk, _front_route_turn


def _narrate_resolved_turn(resolved_turn: ResolvedTurn, player_input, messages, target_id):
    if messages is None:
        messages = resolved_turn.messages or _session().messages

    npc_target = resolved_turn.npc_target
    if npc_target is None and isinstance(resolved_turn.action_result, dict):
        npc_id = resolved_turn.action_result.get("npc_id")
        if npc_id:
            for npc in _session().world_state.get("npcs", []):
                if isinstance(npc, dict) and npc.get("id") == npc_id:
                    npc_target = npc
                    break

    lore_context = resolved_turn.lore_context
    if lore_context is None:
        injected = getattr(_session(), "lore_authority_context", None)
        lore_context = _prepare_lore_authority_context(injected)

    narration_only = not (
        resolved_turn.allow_new_npcs
        or resolved_turn.allow_new_features
        or resolved_turn.allow_new_shops
        or resolved_turn.allow_new_locations
    )
    emergence = incident_hooks.before_narration(
        _session(), action_result=resolved_turn.action_result, player_text=player_input,
        location_changed=bool(resolved_turn.expected_location_change),
    )
    narration_model_calls = 1
    from api.model_phase import resolved_narration_scope
    proposes_place = _may_propose_local_place(resolved_turn, player_input)
    with resolved_narration_scope(narration_only):
        packet = ask_dungeon_master(
            messages,
            player_input,
            allow_new_npcs=resolved_turn.allow_new_npcs and not proposes_place,
            allow_new_features=resolved_turn.allow_new_features and not proposes_place,
            npc_target=npc_target,
            world_entry=resolved_turn.expected_location_change,
            action_result=resolved_turn.action_result,
            allow_new_locations=resolved_turn.allow_new_locations,
            return_details=True,
            allow_new_shops=resolved_turn.allow_new_shops,
            narration_only=not proposes_place,
            lore_context=lore_context,
            scene_plan=resolved_turn.scene_plan,
        )
    packet = packet if isinstance(packet, dict) else {}
    if proposes_place:
        resolved_turn.action_result["verified_world_updates"] = {
            "create_locations": _accepted_local_place(packet, resolved_turn.action_result),
        }
        packet["world_updates"] = {}

    rejected_scene_detail_proposal = False
    if isinstance(resolved_turn.action_result, dict):
        verified_updates = resolved_turn.action_result.get(
            "verified_world_updates", {}
        )
        verified_features = (
            verified_updates.get("create_features", [])
            if isinstance(verified_updates, dict)
            else []
        )
        if (
            resolved_turn.action_result.get("scene_detail_proposal_submitted")
            and not verified_features
        ):
            rejected_scene_detail_proposal = True
            packet["valid_response"] = False
            packet["narration"] = resolved_turn.fallback_response
            packet["fallback_reason_code"] = "UNVERIFIED_SCENE_DETAIL_PROPOSAL"

    proposal_snapshot = _world_snapshot()
    if packet.get("valid_response") and any((packet.get("world_updates") or {}).values()):
        packet["valid_response"] = False
        packet["narration"] = resolved_turn.fallback_response
        packet["fallback_reason_code"] = "MODEL_WORLD_PROPOSAL_REJECTED"
    if not narration_only:
        # Rejected narrator proposals must never become canonical world state.
        # Only updates verified by the action resolver may enter this path.
        raw_updates = (
            resolved_turn.action_result.get("verified_world_updates", {})
            if isinstance(resolved_turn.action_result.get("verified_world_updates"), dict)
            else {}
        )
        if resolved_turn.allow_new_shops:
            raw_updates = {"create_shops": raw_updates.get("create_shops", [])}
        is_assertion = is_player_world_assertion(player_input) and not resolved_turn.allow_new_shops

        # Location proposals are validated and committed before the player location changes.
        location_updates = validate_world_updates(
            raw_updates,
            allow_new_locations=resolved_turn.allow_new_locations and not is_assertion,
        )
        if resolved_turn.allow_new_locations and location_updates.get("create_locations"):
            import heard_rumours
            expected = heard_rumours.base_name(resolved_turn.action_result.get("target_reference", "")).casefold().strip(" .,!?:;\"'")
            expected_words = re.findall(r"[a-z0-9çğıöşü]+", expected)
            matching = []
            for proposal in location_updates["create_locations"]:
                candidates = [proposal.get("name", ""), *proposal.get("aliases", [])]
                candidate_words = [re.findall(r"[a-z0-9çğıöşü]+", candidate.casefold()) for candidate in candidates]
                exact_or_contained = any(
                    expected == " ".join(words)
                    or bool(expected_words and any(
                        words[index:index + len(expected_words)] == expected_words
                        for index in range(max(0, len(words) - len(expected_words) + 1))
                    ))
                    for words in candidate_words
                )
                if exact_or_contained:
                    original_name = proposal.get("name", "")
                    if original_name.casefold() != expected:
                        aliases = list(proposal.get("aliases", []))
                        if original_name and original_name not in aliases:
                            aliases.append(original_name)
                        proposal["aliases"] = aliases[:8]
                        proposal["name"] = resolved_turn.action_result.get("target_reference", original_name)
                    matching.append(proposal)
            location_updates["create_locations"] = matching[:1]
        if location_updates.get("create_locations"):
            merge_world_updates({"create_locations": location_updates["create_locations"]})
            if proposes_place:
                _settle_local_place(resolved_turn.action_result)
        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "awaiting_proposal":
            _commit_travel_action(resolved_turn.action_result)
            if (
                proposes_place
                and resolved_turn.action_result.get("status") not in ("failed", "intended")
                and _session().world_state.get("location") != resolved_turn.action_result.get("target")
                and resolved_turn.action_result.get("direct_response")
            ):
                # Stopped on the way: the narrator wrote before the walk, so its arrival is untrue.
                packet["narration"] = resolved_turn.action_result["direct_response"]

        # Validate NPC/feature/shop proposals only after any accepted location exists.
        validated_updates = validate_world_updates(
            raw_updates,
            allow_new_npcs=resolved_turn.allow_new_npcs and not is_assertion,
            allow_new_features=resolved_turn.allow_new_features and not is_assertion,
            allow_new_shops=resolved_turn.allow_new_shops and not is_assertion,
        )
        if resolved_turn.allow_new_shops and not validated_updates.get("create_shops"):
            resolved_turn.action_result.update(
                success=False,
                status="proposal_rejected",
                direct_response=(
                    "Etrafına bakınıyorsun ama şu an kapısı açık bir dükkân "
                    "göremiyorsun."
                ),
            )
            packet["valid_response"] = False
            packet["narration"] = resolved_turn.action_result["direct_response"]
        else:
            created_npcs = merge_world_updates(validated_updates) if not is_assertion else []
            if resolved_turn.allow_new_shops and validated_updates.get("create_shops"):
                resolved_turn.action_result.update(success=True, status="created")
                resolved_turn.action_result.setdefault("state_changes", []).append("world.shops")
                packet["narration"] = (
                    "Bu kampanyada mevcut konumda tek bir yerel dükkân ve onu işleten "
                    "bir dükkâncı kaydedildi."
                )
                packet["lore_claims"] = []
            flags = _session().world_state.setdefault("flags", {})
            if len(created_npcs) == 1:
                talk_mode.open(_session().world_state, created_npcs[0].get("id"), turn=flags.get("turn_index", 0))

            accepted_proposal_keys, rejected_proposal_names = _bind_world_update_mentions(
                raw_updates,
                location_updates,
                validated_updates,
                _session().world_state,
            )
            if isinstance(packet.get("narration"), str):
                packet["narration"] = _filter_unaccepted_proposal_mentions(
                    packet["narration"],
                    accepted_proposal_keys,
                    rejected_proposal_names,
                )

        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "failed":
            packet["valid_response"] = False
            packet["narration"] = _fallback_for_action_result(player_input, resolved_turn.action_result)

        proposal_changes = _changed_state_fields(proposal_snapshot)
        resolved_turn.action_result["state_changes"] = list(dict.fromkeys(
            resolved_turn.action_result.get("state_changes", []) + proposal_changes
        ))

        if resolved_turn.quest_world_before and resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "completed":
            post_travel_quests = _session().evaluate_quest_events(
                resolved_turn.quest_world_before, resolved_turn.action_result
            )
            if post_travel_quests:
                resolved_turn.action_result["quest_outcomes"] = post_travel_quests

    # A narration-only turn cannot propose, so a marker there names nothing new;
    # the sentence stays and only the marker goes.
    packet["narration"] = _repair_internal_marks(packet.get("narration"))
    claims = packet.get("lore_claims", [])
    if (narration_only and not claims and resolved_turn.npc_target is None
            and isinstance(packet.get("narration"), str)):
        # The narration-only prompt asks for no citations; a narration that only
        # restates public official facts is bound to them here instead.
        from api.lore_authority.claim_authorization import exact_narration_evidence_ids
        exact_ids = exact_narration_evidence_ids(packet["narration"], lore_context)
        if exact_ids:
            claims = exact_ids
            packet["lore_claims"] = exact_ids
    lore_unsupported = not _lore_claims_are_supported(claims, lore_context)
    if not lore_unsupported and _narration_has_unsupported_lore_claim(
        packet.get("narration"), claims, lore_context, _session().world_state,
    ):
        # Repair before replacing: keep every sentence the guard accepts.
        repaired_lore = _repair_unsupported_lore_narration(
            packet.get("narration"), claims, lore_context, _session().world_state,
        )
        if repaired_lore:
            packet["narration"] = repaired_lore
        else:
            lore_unsupported = True
    if lore_unsupported:
        packet["valid_response"] = False
        packet["fallback_reason_code"] = "UNVERIFIED_LORE_CLAIM"

    if (resolved_turn.action_result.get("action") == "shop_setup"
            and resolved_turn.action_result.get("status") == "created"
            and packet.get("narration") != resolved_turn.action_result.get("direct_response")):
        packet["valid_response"] = False
        packet["fallback_reason_code"] = packet.get("fallback_reason_code") or "UNGROUNDED_SHOP_SCENE"
        packet["narration"] = resolved_turn.action_result["direct_response"]

    import resolved_presentation
    bounded_check = resolved_presentation.bounded_rebuilding_check(
        resolved_turn.action_result, player_input, lore_context
    )
    if bounded_check and packet.get("narration") != bounded_check:
        packet["valid_response"] = False
        packet["fallback_reason_code"] = packet.get("fallback_reason_code") or "UNGROUNDED_RESOLVED_CHECK"
        packet["narration"] = bounded_check
        resolved_turn.fallback_response = bounded_check

    fallback_code = packet.get("fallback_reason_code") or resolved_turn.safety_reason_code
    finalized_narration = finalize_narration(
        packet.get("narration"),
        player_input,
        npc_target=npc_target,
        action_result=resolved_turn.action_result,
        fallback_reason_code=fallback_code,
        target_id=target_id or resolved_turn.target_id,
        resolved_fallback_response=(
            resolved_turn.fallback_response if narration_only else None
        ),
    )
    if resolved_turn.action_result.get("action") == "narrative_spell" and isinstance(packet.get("item_claims"), list):
        # D-067: the cast moved nothing, so a thing the narrator says changed hands is never committed: its sentence
        # leaves first (the rest of the line stays), and a line that was all claim is the Python line.
        import pocket
        for claim in packet["item_claims"]:
            finalized_narration = pocket.without_claim(_session().world_state, claim, finalized_narration)
        finalized_narration = finalized_narration or resolved_turn.fallback_response
    import spell_effects
    if (resolved_turn.action_result.get("action") == "narrative_spell"
            and spell_effects.claims_state_change(finalized_narration)):
        # 4C.5: the engine wrote only the spell fact; a line claiming coin, an item, healing or damage is not shown.
        packet["valid_response"] = False
        packet["fallback_reason_code"] = "NARRATIVE_SPELL_STATE_CLAIM"
        finalized_narration = resolved_turn.fallback_response
    if _narrated_money_can_lie(resolved_turn.action_result) and isinstance(packet.get("item_claims"), list):
        # Settled on the line the player will read: a sentence the safety pass took leaves no item behind.
        import pocket
        import town_knowledge
        try:
            for claim in packet["item_claims"][:2]:
                finalized_narration = pocket.settle_claim(_session(), claim, finalized_narration, npc_target,
                                                          line=player_input)[0]
        except Exception:
            town_knowledge.log_failure()
        finalized_narration = finalized_narration or pocket.EMPTY_HANDED
    if rejected_scene_detail_proposal:
        finalized_narration = resolved_turn.fallback_response
    if (
        resolved_turn.action_result.get("scene_look")
        and getattr(_session(), "last_narration_safety", {}).get("handling") not in ("accepted", "repaired")
    ):
        finalized_narration = resolved_turn.fallback_response
    finalized_narration = _keep_people_in_look(finalized_narration, resolved_turn.action_result)
    finalized_narration = _states_the_failed_check(finalized_narration, resolved_turn.action_result, player_input)
    if _narration_scene_type(resolved_turn.action_result) != "conversation":
        finalized_narration = _singular_narrator(finalized_narration)

    final_dict = resolved_turn.raw_result
    final_dict["narration"] = finalized_narration

    safety_diag = getattr(_session(), "last_narration_safety", {}) or {}
    validation_result = safety_diag.get("handling", "accepted")
    fallback_reason = safety_diag.get("reason_code") or packet.get("fallback_reason_code")

    shown_player_line = packet.get("player_line")
    if (
        shown_player_line
        and packet.get("valid_response")
        and packet.get("narration")
        and not rejected_scene_detail_proposal
        and validation_result in ("accepted", "repaired")
    ):
        # The player's own words are a separate, attributed segment, never NPC speech.
        import npc_speech_boundary
        body = npc_speech_boundary.strip_player_quote(
            final_dict["narration"], player_input
        )
        final_dict["narration"] = (
            f"Sen: “{shown_player_line}”\n\n{body}".strip()
            if body else f"Sen: “{shown_player_line}”"
        )

    if validation_result in ("python_memory_response", "python_memory_fallback"):
        narration_source = "python_memory_response"
    elif validation_result in ("accepted", "repaired") and packet.get("valid_response", True) and packet.get("narration"):
        narration_source = "qwen"
    else:
        narration_source = "deterministic_fallback"

    if narration_source == "qwen":
        _keep_town_portrait(resolved_turn.action_result, finalized_narration)

    intent_calls = resolved_turn.intent_model_calls
    total_calls = intent_calls + narration_model_calls + emergence["model_calls"]

    if "_engine_event_evidence" in final_dict:
        before_set = final_dict["_engine_event_evidence"].pop("_procedural_ids_before", set())
        final_dict["_engine_event_evidence"]["procedural_entity_ids"] = sorted(
            _current_procedural_entity_ids() - before_set
        )
        final_dict["_engine_event_evidence"]["telemetry"] = {
            "intent_model_calls": intent_calls,
            "narration_model_calls": narration_model_calls,
            "total_model_calls": total_calls,
            "intent_source": resolved_turn.intent_source,
            "narration_source": narration_source,
            "fallback_reason": fallback_reason,
            "narration_validation_result": validation_result,
            "resolved_action_type": (
                resolved_turn.action_result.get("action", "unknown")
                if isinstance(resolved_turn.action_result, dict)
                else "unknown"
            ),
        }

    return final_dict


from game_parts.turn import _owner_module_reply


from game_parts.turn import _run_player_turn_internal


DEFAULT_SAVE_PATH = Path(__file__).resolve().parent / "saves" / "adventure.json"


def start_terminal_game(input_fn=input, print_fn=print, save_path=DEFAULT_SAVE_PATH):
    """Resume a default save, or start a new character when none is chosen."""
    save_path = Path(save_path).expanduser()
    if save_path.is_file():
        print_fn("Kayıtlı macera bulundu.")
        print_fn("1. Yeni karakter oluştur")
        print_fn("2. Kayıtlı maceraya devam et")
        while True:
            choice = input_fn("Seçimin: ").strip()
            if choice == "1":
                break
            if choice == "2":
                try:
                    load_game(save_path)
                except (OSError, ValueError, TypeError) as error:
                    print_fn(f"Kayıt yüklenemedi: {error}")
                    print_fn("Yeni karakter oluşturabilir veya oyundan çıkabilirsin.")
                    continue
                print_fn(f"Oyun yüklendi: {save_path}")
                return True
            if choice.casefold() in ("çık", "exit"):
                return False
            print_fn("Lütfen 1 veya 2 seç.")
    initialize_game(input_fn=input_fn, print_fn=print_fn)
    return True


# All mutable engine references above resolve through _session(). The wrapper
# below provides an explicit session= argument and propagates it to nested calls.
_PART_MODULES = ("game_parts.character_rules", "game_parts.coin", "game_parts.combat_flow", "game_parts.dialogue", "game_parts.intent", "game_parts.living_world_turn", "game_parts.lore", "game_parts.narration", "game_parts.narration_safety", "game_parts.new_game", "game_parts.places", "game_parts.savefile", "game_parts.text_rules_a", "game_parts.text_rules_b", "game_parts.turn", "game_parts.turn_front")
_ENGINE_FUNCTIONS = tuple(name for name, value in globals().items()
                          if isinstance(value, types.FunctionType)
                          and (value.__module__ == __name__ or value.__module__ in _PART_MODULES))
_CHARACTER_GLOBALS = {
    "character_name": "name", "character_race": "race",
    "character_class": "class",
    **{key: key for key in (
        "strength", "dexterity", "constitution", "intelligence", "wisdom",
        "charisma", "proficient_skills", "level", "proficiency_bonus",
        "max_hp", "current_hp", "armor_class", "strength_mod",
        "dexterity_mod", "constitution_mod", "intelligence_mod",
        "wisdom_mod", "charisma_mod", "modifiers",
    )},
}
_ACTIVE_SESSION = contextvars.ContextVar("ai_dnd_active_session", default=None)
_DEFAULT_SESSION = None
_ENGINE_NAMESPACE = globals()


def _restore_in_place(live, saved):
    """Make ``live`` equal ``saved`` while keeping every container both still hold the live object (B1 forfeit).

    ``saved`` is a private deep copy the caller gives up. Dicts lose keys ``saved`` lacks; lists are matched by position
    (surplus items dropped, missing ones appended); a value of another type is replaced.
    """
    if isinstance(live, dict):
        for key in [key for key in live if key not in saved]:
            del live[key]
        for key, value in saved.items():
            current = live.get(key)
            if key in live and type(current) is type(value) and isinstance(value, (dict, list)):
                _restore_in_place(current, value)
            else:
                live[key] = value
    else:
        del live[len(saved):]
        for index, value in enumerate(saved):
            if index >= len(live):
                live.append(value)
            elif type(live[index]) is type(value) and isinstance(value, (dict, list)):
                _restore_in_place(live[index], value)
            else:
                live[index] = value


class GameSession:
    """Independent player, world, narration history, conversation and dice."""

    def __init__(self, seed=None):
        self.character = {}
        self.world_state = copy.deepcopy(INITIAL_WORLD_STATE)
        self.recent_dm_narrations = []
        self.messages = [{"role": "system", "content": system_prompt}]
        self.rng = random.Random(seed)
        # Injected by the API for one request; never included in engine saves.
        self.lore_authority_context = None
        # Ephemeral diagnostics only; these are deliberately outside canonical
        # world state and are never returned in the player-facing turn payload.
        self.last_narration_safety = None
        self.last_arrival_narration = None
        self.narration_safety_history = []
        self._xp_level_up = None
        self._xp_unrecorded = []
        self._xp_unrecorded_awards = []  # this turn's forfeited awards: (receipt ids, amount shown) — one line each
        self._persisted_engine_format = SAVE_FORMAT_VERSION

    def _receive_xp_award(self, award_owner, *args, **kwargs):
        """Session adoption of an existing XP owner; no new reward or receipt policy.

        Sessionless callers may use xp.apply_xp for detached numeric work, but
        persistent sessions must use this boundary to atomically adopt format6.
        A campaign still on save format 1..3 moves to format 6 here too (its live
        spell fields are the canonical empty ones load_game set); the real save
        validator admits the result or the whole award is put back.
        """
        snapshot = self._capture_runtime_snapshot()
        had_format = "_persisted_engine_format" in self.__dict__
        old_format = copy.deepcopy(self.__dict__.get("_persisted_engine_format"))
        try:
            return self._admit_xp_award(award_owner, *args, **kwargs)
        except Exception:
            self._restore_runtime_snapshot(snapshot)
            if had_format:
                self._persisted_engine_format = old_format
            else:
                self.__dict__.pop("_persisted_engine_format", None)
            raise

    def _admit_xp_award(self, award_owner, *args, **kwargs):
        held = self.world_state.get("xp_awarded_event_ids")
        held = set(held) if isinstance(held, list) else set()
        format_before = getattr(self, "_persisted_engine_format", SAVE_FORMAT_VERSION)
        summary = award_owner(*args, **kwargs)
        crossing = (isinstance(summary, dict) and summary.get("xp_gained", 0) > 0
                    and summary.get("previous_level", 5) < 5 <= summary.get("new_level", 0))
        if crossing:
            written = [event_id for event_id in self.world_state.get("xp_awarded_event_ids", [])
                       if event_id not in held]  # this award's receipts: a retry of it is the same award (D-061)
        if crossing and format_before not in _SUPPORTED_SAVE_VERSIONS:
            import xp
            raise xp.UnrecordableXp(summary["xp_gained"], xp.REASON_OLD_SAVE, written)
        self._remember_xp_award(summary)
        if crossing:
            # Read through the real production admission owner before commit.
            try:
                self._validate_save_payload(self.serialize_game_state())
            except ValueError as error:
                import xp
                # D-061: the forfeit boundary checks the record before the award, so a refusal the award did not
                # cause is raised, not forfeited (``__cause__`` carries the admission's own error). Only a record
                # still on an older format is told it is an old save.
                reason = xp.REASON_CROSSING if format_before == 6 else xp.REASON_OLD_SAVE
                raise xp.UnrecordableXp(summary["xp_gained"], reason, written) from error
        return summary

    def _forfeit_unrecordable_xp(self, award_owner, *args, **kwargs):
        """B1 (D-001, D-013): the product's XP boundary. An award that cannot be recorded (a full receipt list, the XP
        cap, an unknown class at a level step, a level-5 crossing the save admission refuses) is put back and logged,
        and play goes on without it instead of being refused on every later turn. Returns the summary, or None.

        Character and world are put back to their exact earlier values *in place* (`_restore_in_place`): every nested
        container a caller holds (the fight being ended, the creature just knocked out, ``saving_throw_mods``) stays
        the live object, and whatever the award or the save check wrote (receipts, level, the save check's
        ``scene_state`` default-fill) is undone. The pending announcement and the save format are put back too. The RNG
        and the narration history are not touched by an award and are not restored.

        D-061: only a known refusal (``xp.UnrecordableXp``) is forfeited; it leaves one player line for this turn
        (``_take_xp_unrecorded``). Any other error is a bug: put back, raised, and the turn falls back whole. A level-5
        admission refusal counts as known only when the record before the award passes the same admission.
        """
        import xp
        character = copy.deepcopy(self.character)
        world = copy.deepcopy(self.world_state)
        pending = copy.deepcopy(self._xp_level_up)
        had_format = "_persisted_engine_format" in self.__dict__
        old_format = copy.deepcopy(self.__dict__.get("_persisted_engine_format"))

        def put_back(saved_character, saved_world):
            _restore_in_place(self.character, saved_character)
            _restore_in_place(self.world_state, saved_world)
            self._xp_level_up = copy.deepcopy(pending)
            if had_format:
                self._persisted_engine_format = old_format
            else:
                self.__dict__.pop("_persisted_engine_format", None)

        try:
            return self._admit_xp_award(award_owner, *args, **kwargs)
        except Exception as error:
            put_back(copy.deepcopy(character), copy.deepcopy(world))
            if not isinstance(error, xp.UnrecordableXp):
                raise
            if isinstance(error.__cause__, ValueError):
                try:
                    self._validate_save_payload(self.serialize_game_state())
                except ValueError:
                    put_back(character, world)
                    raise error.__cause__  # the record was refused before the award: not the award's doing
                put_back(character, world)  # the check's own default-fill (``scene_state``) goes back too
            import logging
            logging.getLogger(__name__).warning("An experience award could not be recorded and is forfeited (B1): %s",
                                                error)
            self._note_unrecorded_xp(error)
            return None

    def _note_unrecorded_xp(self, error):
        """One line per forfeited award this turn (D-061). An award tried again in the same turn (a creature knocked
        out, then counted again when the fight ends) adds no second line; a retry that also holds new receipts shows
        only the amount not shown yet."""
        import xp
        ids = set(error.event_ids)
        shown = list(getattr(self, "_xp_unrecorded_awards", []))
        if ids and ids <= {event_id for earlier, _ in shown for event_id in earlier}:
            return
        amount = error.amount - sum(earlier_amount for earlier, earlier_amount in shown if ids and set(earlier) <= ids)
        self._xp_unrecorded_awards = [*shown, (sorted(ids), amount)]
        self._xp_unrecorded = [*getattr(self, "_xp_unrecorded", []), str(xp.UnrecordableXp(amount, error.reason))]

    def _take_xp_unrecorded(self):
        """This turn's lines for forfeited awards ("<X> XP kaydedilemedi: <neden>."), then forget them (D-061)."""
        lines = list(getattr(self, "_xp_unrecorded", []))
        self._xp_unrecorded = []
        self._xp_unrecorded_awards = []
        return lines

    def _remember_xp_award(self, summary):
        """Fold another award into the single announcement for this turn."""
        if not isinstance(summary, dict):
            return
        if (type(summary.get("xp_gained")) is int and summary["xp_gained"] > 0
                and summary.get("previous_level", 5) < 5 <= summary.get("new_level", 0)):
            self._persisted_engine_format = 6
        pending = self._xp_level_up
        if not isinstance(pending, dict):
            self._xp_level_up = copy.deepcopy(summary)
            return
        self._xp_level_up = {
            "previous_level": pending["previous_level"],
            "new_level": summary["new_level"],
            "xp_gained": pending["xp_gained"] + summary["xp_gained"],
            "hit_points_gained": pending["hit_points_gained"] + summary["hit_points_gained"],
        }

    def _publish_level_up(self, result):
        """Move one pending level-up onto a turn result, then forget it."""
        pending = self._xp_level_up
        if not isinstance(result, dict) or not isinstance(pending, dict):
            return result
        result["level_up"] = copy.deepcopy(pending)
        self._xp_level_up = None
        return result

    def __getattr__(self, name):
        helper = _ENGINE_NAMESPACE.get(name)
        if callable(helper) and getattr(helper, "_session_bound", False):
            return functools.partial(helper, session=self)
        raise AttributeError(name)

    def _capture_runtime_snapshot(self):
        """Capture owned runtime state for rollback, not for save-file loading."""
        return {
            "character": copy.deepcopy(self.character),
            "world_state": copy.deepcopy(self.world_state),
            "recent_dm_narrations": copy.deepcopy(self.recent_dm_narrations),
            "messages": copy.deepcopy(self.messages),
            "rng_state": self.rng.getstate(),
            "xp_level_up": copy.deepcopy(self._xp_level_up),
            "xp_unrecorded": list(getattr(self, "_xp_unrecorded", [])),
            "xp_unrecorded_awards": copy.deepcopy(getattr(self, "_xp_unrecorded_awards", [])),
            "persisted_engine_format_present": "_persisted_engine_format" in self.__dict__,
            "persisted_engine_format": copy.deepcopy(self.__dict__.get("_persisted_engine_format")),
            # D-115: the open "kavga mı başlatıyorsun?" question goes back with the turn that asked it.
            "attack_question": (getattr(self, "_attack_asked", False), copy.deepcopy(getattr(self, "_blow_asked", None)),
                                copy.deepcopy(getattr(self, "_blow_asked_line", None))),
            # D-115: so does the surrendered-foe question ("Yine de vuruyor musun?").
            "surrender_question": copy.deepcopy(getattr(self, "_surrender_strike_asked", None)),
            # D-109: and the crime/threat question ("Gerçekten çalıyor musun?").
            "heavy_question": copy.deepcopy(getattr(self, "_heavy_asked", None)),
            "heavy_yes": copy.deepcopy(getattr(self, "_heavy_confirmed", None)),
        }

    def _restore_runtime_snapshot(self, snapshot):
        """Restore a trusted in-process capture exactly, without save migrations.

        A rejected request can start with inconsistent runtime markers. Rollback
        must preserve those markers, not validate or repair them. External JSON
        continues to enter exclusively through the validated load_game boundary.
        Keep containers in place for callers holding world/character references.
        """
        restored = copy.deepcopy(snapshot)
        self.rng.setstate(restored["rng_state"])
        self.character.clear()
        self.character.update(restored["character"])
        self.world_state.clear()
        self.world_state.update(restored["world_state"])
        self.recent_dm_narrations[:] = restored["recent_dm_narrations"]
        self.messages[:] = restored["messages"]
        self._xp_level_up = restored.get("xp_level_up")
        self._xp_unrecorded = restored.get("xp_unrecorded", [])
        self._xp_unrecorded_awards = restored.get("xp_unrecorded_awards", [])
        if restored.get("persisted_engine_format_present", False):
            self._persisted_engine_format = restored["persisted_engine_format"]
        else:
            self.__dict__.pop("_persisted_engine_format", None)
        self._attack_asked, self._blow_asked, self._blow_asked_line = restored.get("attack_question", (False, None, None))
        self._surrender_strike_asked = restored.get("surrender_question")
        self._heavy_asked = restored.get("heavy_question")
        self._heavy_confirmed = restored.get("heavy_yes")

    def resolve_ambient_event_action(
        self,
        event_instance_id: str,
        action_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Resolve a click on the scene's ambient event (the rule and the click live in `ambient_actions`)."""
        import ambient_actions
        return ambient_actions.resolve(self, event_instance_id, action_id, action)

    def quest_offers(self):
        world = self.world_state
        known_quests = {item.get("quest_id") for item in world.get("quests", [])}
        current_location = world.get("location")
        offers = []
        for definition in quest_catalog():
            if definition["quest_id"] in known_quests:
                continue
            condition = definition.get("offer_condition")
            if condition:
                if condition["type"] == "location_is":
                    if (
                        condition["target"] != current_location
                        or condition["target"] not in world.get("locations", {})
                    ):
                        continue
                elif condition["type"] == "npc_present":
                    if not any(
                        npc.get("id") == condition["target"]
                        and npc.get("location") == current_location
                        for npc in world.get("npcs", [])
                        if isinstance(npc, dict)
                    ):
                        continue
            offers.append({
                "quest_id": definition["quest_id"],
                "title": definition["title"],
                "description": definition["description"],
                "giver_npc_id": definition.get("giver_npc_id"),
                "objectives": [dict(item) for item in definition["objectives"]],
            })
        return offers

    def _quest_record(self, definition, turn_index, status="accepted"):
        return {
            "quest_id": definition["quest_id"],
            "title": definition["title"],
            "description": definition["description"],
            "giver_npc_id": definition.get("giver_npc_id"),
            "status": status,
            "objectives": [
                {
                    "objective_id": item["objective_id"],
                    "description": item["description"],
                    "type": item["type"],
                    "target": item["target"],
                    "status": "active" if status == "accepted" else "cancelled",
                    "required_count": item.get("required_count", 1),
                    "progress": 0,
                }
                for item in definition["objectives"]
            ],
            "created_turn": turn_index,
            "accepted_turn": turn_index if status == "accepted" else None,
            "updated_turn": turn_index,
        }

    def accept_quest(self, quest_id):
        self.require_player_can_act()
        existing = next((item for item in self.world_state["quests"]
                         if item.get("quest_id") == quest_id), None)
        if existing is not None and existing.get("record_kind") == "dynamic":
            return adventure_play.accept(self, quest_id)
        if existing is not None:
            return {"transition": None, "quest": copy.deepcopy(existing)}
        definition = next(
            (item for item in self.quest_offers() if item["quest_id"] == quest_id),
            None,
        )
        if definition is None:
            raise ValueError("Quest is not available.")
        turn = self.world_state.get("flags", {}).get("turn_index", 0)
        record = self._quest_record(definition, turn)
        self.world_state["quests"].append(record)
        return {"transition": self._quest_transition(
            "accepted", quest_id, None, f"command:accept:{quest_id}:{turn}", turn
        ), "quest": copy.deepcopy(record)}

    def cancel_quest(self, quest_id):
        self.require_player_can_act()
        existing = next((item for item in self.world_state["quests"]
                         if item.get("quest_id") == quest_id), None)
        if existing is not None and existing.get("record_kind") == "dynamic":
            from adventure import dialogue_jobs
            return dialogue_jobs.cancel_job(self, existing)
        if existing is None:
            definition = next(
                (item for item in self.quest_offers() if item["quest_id"] == quest_id),
                None,
            )
            if definition is None:
                raise ValueError("Quest is not available.")
            turn = self.world_state.get("flags", {}).get("turn_index", 0)
            preview = self._quest_record(definition, turn, status="cancelled")
            self.world_state["quests"].append(preview)
            return {"transition": self._quest_transition(
                "cancelled", quest_id, None, f"command:cancel:{quest_id}:{turn}", turn
            ), "quest": preview}
        if existing.get("status") == "cancelled":
            return {"transition": None, "quest": copy.deepcopy(existing)}
        if existing.get("status") == "completed":
            return {"transition": None, "quest": copy.deepcopy(existing)}
        turn = self.world_state.get("flags", {}).get("turn_index", 0)
        existing["status"] = "cancelled"
        existing["updated_turn"] = turn
        for objective in existing.get("objectives", []):
            if objective.get("status") == "active":
                objective["status"] = "cancelled"
        return {"transition": self._quest_transition(
            "cancelled", quest_id, None, f"command:cancel:{quest_id}:{turn}", turn
        ), "quest": copy.deepcopy(existing)}

    @staticmethod
    def _quest_transition(kind, quest_id, objective_id, source_id, turn):
        return {
            "event_id": f"quest:{kind}:{quest_id}:{source_id}",
            "quest_id": quest_id,
            "transition": kind,
            "objective_id": objective_id,
            "source_event_id": source_id,
            "turn_index": turn,
        }

    def evaluate_quest_events(self, before_world, action_result):
        """Consume only canonical before/after evidence; never narration."""
        if not isinstance(action_result, dict):
            return []
        world = self.world_state
        turn = world.get("flags", {}).get("turn_index", 0)
        events = []
        if (
            before_world.get("location") != world.get("location")
            and world.get("location") in world.get("locations", {})
        ):
            events.append(("visit_location", world.get("location"),
                           f"location:{turn}:{world.get('location')}"))
        before_npcs = {n.get("id"): n for n in before_world.get("npcs", [])
                       if isinstance(n, dict)}
        for npc in world.get("npcs", []):
            npc_id = npc.get("id")
            if not npc_id or npc_id not in before_npcs:
                continue
            was = before_npcs[npc_id]
            defeated = (npc.get("combat_status") in {"unconscious", "defeated", "dead"}
                        or npc.get("current_hp", 1) <= 0)
            previously = (was.get("combat_status") in {"unconscious", "defeated", "dead"}
                          or was.get("current_hp", 1) <= 0)
            if defeated and not previously:
                events.append(("defeat_entity", npc_id,
                               f"defeat:{turn}:{npc_id}"))
        before_items = equipment_economy.labels(before_world.get("inventory", []))
        after_items = equipment_economy.labels(world.get("inventory", []))
        for item in sorted(set(after_items) - set(before_items), key=str.casefold):
            if item == "Kılıç":
                events.append(("acquire_item", item, f"item:{turn}:{item}"))
        transitions = []
        processed = world.setdefault("quest_processed_event_ids", [])
        for kind, target, source_id in events:
            if source_id in processed:
                continue
            event_matched = False
            for quest in world.get("quests", []):
                if quest.get("status") != "accepted":
                    continue
                for objective in quest.get("objectives", []):
                    if objective.get("status") != "active" or objective.get("type") != kind:
                        continue
                    if objective.get("target") != target:
                        continue
                    required = objective.get("required_count", 1)
                    progress = objective.get("progress", 0) + 1
                    objective["progress"] = min(required, progress)
                    quest["updated_turn"] = turn
                    event_matched = True
                    if progress < required:
                        transitions.append(self._quest_transition(
                            "objective_progress", quest["quest_id"],
                            objective["objective_id"], source_id, turn
                        ))
                        continue
                    objective["status"] = "completed"
                    transitions.append(self._quest_transition(
                        "objective_completed", quest["quest_id"],
                        objective["objective_id"], source_id, turn
                    ))
                    if all(item.get("status") == "completed"
                           for item in quest["objectives"]):
                        quest["status"] = "completed"
                        import xp
                        self._forfeit_unrecordable_xp(  # D-060: a refused award is forfeited with a line, not a rejected turn
                            xp.award_completed_quest, world, self.character, quest["quest_id"]
                        )
                        transitions.append(self._quest_transition(
                            "completed", quest["quest_id"], None, source_id, turn
                        ))
            if event_matched:
                processed.append(source_id)
        transitions.extend(_dynamic_engine_transitions(
            adventure.apply_dynamic_evidence(world, before_world, action_result),
            world,
            before_world,
        ))
        adventure_play.after_turn(self, before_world, action_result)
        incident_hooks.after_turn(self, before_world, action_result)
        return transitions


def _dynamic_engine_transitions(notes, world, before_world=None):
    """Shape dynamic completions for the existing engine-evidence contract."""
    turn = world.get("flags", {}).get("turn_index", 0) if isinstance(world, dict) else 0
    if type(turn) is not int:
        turn = 0
    shaped = []
    touched = []
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        quest_id = note.get("quest_id")
        objective_id = note.get("objective_id")
        if not isinstance(quest_id, str) or not isinstance(objective_id, str):
            continue
        shaped.append({
            "event_id": f"quest:objective_completed:{quest_id}:{objective_id}:{turn}",
            "quest_id": quest_id,
            "transition": "objective_completed",
            "objective_id": objective_id,
            "source_event_id": f"dynamic:{quest_id}:{objective_id}:{turn}",
            "turn_index": turn,
        })
        if quest_id not in touched:
            touched.append(quest_id)
    quests = world.get("quests", []) if isinstance(world, dict) else []
    before_status = {
        item.get("quest_id"): item.get("status")
        for item in (before_world.get("quests", []) if isinstance(before_world, dict) else [])
        if isinstance(item, dict)
    }
    for quest in quests:  # a job closed with no new step this turn (steps kept before acceptance, D-203)
        quest_id = quest.get("quest_id") if isinstance(quest, dict) else None
        if (isinstance(quest_id, str) and quest_id not in touched and quest.get("status") == "COMPLETED"
                and before_status.get(quest_id) not in {None, "COMPLETED"}):
            touched.append(quest_id)
    for quest_id in touched:
        quest = next(
            (
                item for item in quests
                if isinstance(item, dict) and item.get("quest_id") == quest_id
            ),
            None,
        )
        if not isinstance(quest, dict) or quest.get("status") != "COMPLETED":
            continue
        shaped.append({
            "event_id": f"quest:completed:{quest_id}:{turn}",
            "quest_id": quest_id,
            "transition": "completed",
            "objective_id": None,
            "source_event_id": f"dynamic:{quest_id}:completed:{turn}",
            "turn_index": turn,
        })
    return shaped


def _session():
    return _ACTIVE_SESSION.get() or _DEFAULT_SESSION


def _bind_session_engine():
    for name in _ENGINE_FUNCTIONS:
        implementation = _ENGINE_NAMESPACE[name]

        @functools.wraps(implementation)
        def bound(*args, __implementation=implementation, session=None, **kwargs):
            selected = session if session is not None else _session()
            if not isinstance(selected, GameSession):
                raise TypeError("session must be a GameSession")
            token = _ACTIVE_SESSION.set(selected)
            try:
                return __implementation(*args, **kwargs)
            finally:
                _ACTIVE_SESSION.reset(token)

        bound._session_bound = True
        _ENGINE_NAMESPACE[name] = bound


_DEFAULT_SESSION = GameSession()
_DEFAULT_SESSION.world_state = world_state
_DEFAULT_SESSION.recent_dm_narrations = recent_dm_narrations
_DEFAULT_SESSION.messages = messages
_bind_session_engine()
initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None)


def create_session(seed=None):
    """Create an initialized, independent adventure; seed controls its dice."""
    session = GameSession(seed=seed)
    token = _ACTIVE_SESSION.set(session)
    try:
        initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None)
    finally:
        _ACTIVE_SESSION.reset(token)
    return session


if __name__ != "__main__":
    class _GameModule(types.ModuleType):
        pass

    for _alias_name, _alias_key in _CHARACTER_GLOBALS.items():
        setattr(_GameModule, _alias_name, property(
            lambda module, key=_alias_key: _DEFAULT_SESSION.character[key],
            lambda module, value, key=_alias_key: _DEFAULT_SESSION.character.__setitem__(key, value)))
    del _alias_name, _alias_key

    # Imported modules retain live character aliases. The engine file is never
    # run as a second copy (exec, runpy); the terminal entry delegates here.
    if isinstance(sys.modules.get(__name__), types.ModuleType) and sys.modules[__name__].__dict__ is globals():
        sys.modules[__name__].__class__ = _GameModule


# ---------------------------------------------------------
# MACERA
# ---------------------------------------------------------
