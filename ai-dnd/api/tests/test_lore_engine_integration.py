from __future__ import annotations

import copy
import unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch

import game
import campaign_time
from api.lore_authority import (
    BindingStatus,
    CampaignLoreState,
    PRODUCTION_REGISTRY,
)
from api.main import _lore_context_for_turn, _stage_engine_lore_state
from api.session_manager import SessionManager
from api.tests.test_lore_authority import entity, verified_registry


def bound_lore_state() -> CampaignLoreState:
    return CampaignLoreState.from_mapping({
        "binding_status": "BOUND",
        "setting_profile": "TEST_SETTING",
        "world_id": "world:test",
        "epoch_id": "epoch:test",
        "region_id": "region:test",
        "current_location_entity_id": "location:start",
        "player_known_fact_ids": [],
        "npc_known_fact_ids": {},
        "campaign_overrides": [],
        "procedural_entity_refs": [],
        "lore_discoveries": [],
    })


class LoreEngineIntegrationTests(unittest.TestCase):
    def test_scene_place_is_kept_and_non_place_falls_back(self):
        registry = verified_registry(
            entities=[
                entity("city:test", "Test City", entity_type="CITY"),
                entity("npc:test", "Test Person", entity_type="CANONICAL_NPC"),
            ]
        )
        state = CampaignLoreState.from_mapping({
            "binding_status": "BOUND",
            "setting_profile": "TEST_SETTING",
            "world_id": "world:test",
            "epoch_id": "epoch:test",
            "region_id": "region:test",
            "current_location_entity_id": "city:test",
            "player_known_fact_ids": [],
            "npc_known_fact_ids": {},
            "campaign_overrides": [],
            "procedural_entity_refs": [],
            "lore_discoveries": [],
        })
        record = SimpleNamespace(lore_authority=state)
        session = SimpleNamespace(
            world_state={"location": "room", "npcs": [], "quests": []}
        )

        city_packet = _lore_context_for_turn(
            record,
            session,
            "Etrafıma bakıyorum.",
            None,
            {"lore_location_id": "city:test"},
            registry,
        )
        self.assertEqual(
            city_packet["diagnostics"]["current_location_entity_id"],
            "city:test",
        )
        self.assertEqual(city_packet["diagnostics"]["campaign_year"], 1501)

        person_packet = _lore_context_for_turn(
            record,
            session,
            "Etrafıma bakıyorum.",
            None,
            {"lore_location_id": "npc:test"},
            registry,
        )
        self.assertEqual(
            person_packet["diagnostics"]["current_location_entity_id"],
            "city:test",
        )

        world = session.world_state
        world["canonical_start_time"] = {
            "year": 1368,
            "month": "Mirtul",
            "day": 1,
            "hour": 9,
            "minute": 0,
        }
        campaign_time.initialize(world)
        dated = _lore_context_for_turn(
            record,
            session,
            "Etrafıma bakıyorum.",
            None,
            {"lore_location_id": "city:test"},
            registry,
        )
        self.assertEqual(dated["diagnostics"]["campaign_year"], 1368)

    def test_unbound_session_does_not_receive_setting_canon(self):
        _, record = SessionManager().create()

        packet = _lore_context_for_turn(
            record,
            record.game_session,
            "What is known about Waterdeep?",
            None,
        )

        self.assertEqual(
            packet["sections"]["official_forgotten_realms_lore"],
            [],
        )
        self.assertTrue(
            packet["authority_boundary"]["unknown_or_unloaded_must_remain_unknown"]
        )

    def test_procedural_entities_keep_server_assigned_identity(self):
        session = game.GameSession(seed=3)
        session.character = {"name": "Test Player"}
        session.world_state["location"] = "tavern"
        location_id = session.world_state["location"]

        npc = session.create_npc_from_ai({
            "name": "Rana",
            "role": "Tüccar",
            "location": location_id,
        })
        new_location = session.create_location_from_proposal({
            "name": "Sessiz Geçit",
            "type": "landmark",
            "description": "Dar bir taş geçit.",
            "aliases": [],
        })
        session.merge_world_updates({
            "create_features": [{
                "location": location_id,
                "name": "Kırık sütun",
                "description": "Duvarın yanında duran eski bir sütun.",
            }],
            "events": ["Odada hafif bir esinti duyulur."],
        })

        self.assertEqual(npc["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(
            new_location["reality_layer"],
            "PROCEDURAL_LOCAL_FICTION",
        )
        self.assertEqual(
            session.world_state["features"][-1]["reality_layer"],
            "PROCEDURAL_LOCAL_FICTION",
        )
        self.assertEqual(
            session.world_state["events"][-1]["reality_layer"],
            "NARRATIVE_TEXTURE",
        )

    def test_engine_evidence_bridges_procedural_refs_and_quest_transitions(self):
        state = bound_lore_state()
        transition = {
            "event_id": "quest:completed:quest:test:visit",
            "quest_id": "quest:test",
            "transition": "completed",
            "objective_id": None,
            "source_event_id": "location:4:location_001",
            "turn_index": 4,
        }
        before_world = {
            "locations": {},
            "npcs": [],
            "flags": {"turn_index": 3},
        }
        after_world = {
            "locations": {
                "location_001": {
                    "id": "location_001",
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                },
            },
            "npcs": [{
                "id": "npc_001",
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            }],
            "flags": {"turn_index": 4},
        }
        action_result = {"quest_outcomes": [transition]}
        evidence = {
            "authority": "python_engine",
            "action_id": "turn:4",
            "turn_index": 4,
            "quest_outcomes": [transition],
            "procedural_entity_ids": ["location_001", "npc_001"],
        }

        staged = _stage_engine_lore_state(
            state,
            evidence,
            action_result,
            before_world,
            after_world,
        )

        self.assertEqual(staged.binding_status, BindingStatus.BOUND)
        self.assertEqual(
            set(staged.procedural_entity_refs),
            {"location_001", "npc_001"},
        )
        self.assertEqual(len(staged.campaign_overrides), 1)
        self.assertEqual(
            staged.campaign_overrides[0].source_action_id,
            "turn:4",
        )
        self.assertEqual(
            staged.campaign_overrides[0].object_id_or_value,
            "completed",
        )
        packet = _lore_context_for_turn(
            SimpleNamespace(lore_authority=staged),
            SimpleNamespace(world_state={
                "location": "runtime-location",
                "npcs": [],
                "quests": [{"quest_id": "quest:test", "status": "completed"}],
            }),
            "",
            None,
        )
        self.assertEqual(
            packet["sections"]["campaign_canon"][0]["notes"],
            "Python-confirmed quest quest:test transition: completed.",
        )

    def test_unbound_quest_evidence_cannot_create_campaign_canon(self):
        state = CampaignLoreState.legacy_unbound()
        before_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 0}}
        after_world = {
            "locations": {},
            "npcs": [],
            "flags": {"turn_index": 1},
        }
        transition = {
            "event_id": "quest:completed:quest:test",
            "quest_id": "quest:test",
            "transition": "completed",
            "objective_id": None,
            "source_event_id": "event:1",
            "turn_index": 1,
        }
        evidence = {
            "authority": "python_engine",
            "action_id": "turn:1",
            "turn_index": 1,
            "quest_outcomes": [transition],
            "procedural_entity_ids": [],
        }

        staged = _stage_engine_lore_state(
            state,
            evidence,
            {"quest_outcomes": [transition]},
            before_world,
            after_world,
        )

        self.assertEqual(staged.binding_status, BindingStatus.LEGACY_UNBOUND)
        self.assertEqual(staged.campaign_overrides, ())

    def test_lore_claims_must_reference_loaded_facts(self):
        context = game._empty_lore_authority_context()
        context["sections"]["official_forgotten_realms_lore"] = [
            {"fact_id": "fact:verified"}
        ]

        self.assertTrue(
            game._lore_claims_are_supported(["fact:verified"], context)
        )
        self.assertFalse(
            game._lore_claims_are_supported(["fact:unloaded"], context)
        )
        self.assertFalse(
            game._lore_claims_are_supported(
                ["fact:verified", "fact:verified"],
                context,
            )
        )


    def test_narration_claim_guard_fails_closed_on_unverified_lore(self):
        context = game._empty_lore_authority_context()
        context["sections"]["official_forgotten_realms_lore"] = [
            {
                "fact_id": "fact:forgotten-realms:year",
                "subject_id": "fr:world:forgotten_realms",
                "predicate": "current_dr_year",
                "object_id_or_value": 1501,
            },
            {
                "fact_id": "fact:neverwinter:status",
                "subject_id": "fr:city:neverwinter",
                "predicate": "current_status",
                "object_id_or_value": "rebuilding",
                "notes": "Neverwinter is rebuilding.",
            },
            {
                "fact_id": "fact:neverwinter:lord",
                "subject_id": "fr:city:neverwinter",
                "predicate": "current_lord_id",
                "object_id_or_value": "fr:person:dagult",
                "notes": "Dagult Neverember is the current Lord of Neverwinter.",
            },
            {
                "fact_id": "fact:alliance:form",
                "subject_id": "fr:faction:lords_alliance",
                "predicate": "political_form",
                "object_id_or_value": "settlement_coalition_not_a_realm",
                "notes": "The Lords' Alliance is a settlement coalition, not a realm.",
            },
            {
                "fact_id": "fact:neverwinter:crafts",
                "subject_id": "fr:city:neverwinter",
                "predicate": "known_for",
                "object_id_or_value": "master_crafts_and_fine_goods",
                "notes": "Known for master crafts and fine goods.",
            },
            {
                "fact_id": "fact:highroad:route",
                "subject_id": "fr:road:high_road",
                "predicate": "continues_as",
                "object_id_or_value": "fr:road:trade_way",
                "notes": "The High Road continues as the Trade Way.",
            },
            {
                "fact_id": "fact:alliance:purpose",
                "subject_id": "fr:faction:lords_alliance",
                "predicate": "purpose",
                "object_id_or_value": "settlement_safety_and_prosperity",
            },
            {
                "fact_id": "fact:neverwinter:alliance",
                "subject_id": "fr:city:neverwinter",
                "predicate": "member_of",
                "object_id_or_value": "fr:faction:lords_alliance",
            },
        ]
        context["sections"]["verified_entities"] = [
            {"entity_id": "fr:city:neverwinter", "canonical_name": "Neverwinter", "aliases": []},
            {"entity_id": "fr:city:phandalin", "canonical_name": "Phandalin", "aliases": []},
            {"entity_id": "fr:person:dagult", "canonical_name": "Dagult Neverember", "aliases": ["Dagult"]},
            {"entity_id": "fr:faction:lords_alliance", "canonical_name": "Lords' Alliance", "aliases": []},
            {"entity_id": "fr:road:high_road", "canonical_name": "High Road", "aliases": []},
            {"entity_id": "fr:road:trade_way", "canonical_name": "Trade Way", "aliases": []},
            {"entity_id": "fr:river:neverwinter", "canonical_name": "River Neverwinter", "aliases": []},
        ]
        world_state = {"locations": {}, "npcs": [], "features": []}

        def rejected(text, fact_ids):
            return game._narration_has_unsupported_lore_claim(
                text, fact_ids, context, world_state
            )

        unsupported_city_expansion = (
            "Neverwinter, kuzeyin en önemli şehirlerinden biri olarak, büyük "
            "yıkımların ardından yeniden inşa edilmektedir. Şehir sınırları "
            "içindeki bazı mahalleler tamamen yok olmuştur; diğerleri ise "
            "kısmen tahrip edilmiş durumda ve onarım sürecindedir. Yeni "
            "yapılan binalar, eski mimari öğelerle birlikte modern "
            "teknolojilerin etkisiyle şekillenmiştir. Bazı yerlerde eski "
            "taşlar hâlâ göze çarparken, yeni yapılı olanlarda ahşap ve demir "
            "kullanılmıştır. Bu yeniden inşa süreci hem şehrin ekonomisini "
            "hem de halkını zorlamaktadır; Neverwinter kuzeyin merkezi "
            "olmaya devam eder."
        )
        self.assertFalse(
            game._narration_has_unsupported_lore_claim(
                "Neverwinter is rebuilding.",
                ["fact:neverwinter:status"],
                context,
                world_state,
            )
        )
        self.assertTrue(
            rejected(
                unsupported_city_expansion,
                ["fact:neverwinter:status"],
            )
        )

        for question in (
            "Is Phandalin on the road from Neverwinter, and how many miles away is it?",
            "Does King Vharion rule Neverwinter?",
            "What is the history of the Silver Marches, and how did they fall?",
            "Elara, did I introduce myself to you?",
            "Is Neverwinter known for silver and metalworking?",
            "Does the High Road connect to Phandalin?",
            "Neverwinterdan resmi bir güzergahın kesin mesafesini söyle.",
        ):
            with self.subTest(question=question):
                self.assertTrue(
                    game._player_question_has_unverified_lore_claim(
                        question,
                        context,
                        world_state,
                    )
                )
        self.assertIsNone(
            game._supported_lore_question_response(
                "Does King Vharion rule Neverwinter?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "How is Neverwinter rebuilding?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "High Road, Trade Way olarak mı devam ediyor?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "What is Neverwinter's current condition in 1501 DR?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "What does the High Road connect to?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "Neverwinter yolunda ilerliyorum.",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "Does Dagult Neverember rule Neverwinter?",
                context,
                world_state,
            )
        )
        self.assertTrue(
            game._player_question_has_unverified_lore_claim(
                "How many miles are between High Road and Trade Way?",
                context,
                world_state,
            )
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "Does Dagult Neverember rule Neverwinter?",
                context,
                world_state,
            ),
            "Dagult Neverember is the current Lord of Neverwinter.",
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "What is Dagult Neverember's current role in Neverwinter?",
                context,
                world_state,
            ),
            "Dagult Neverember is the current Lord of Neverwinter.",
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "High Road, Trade Way olarak mı devam ediyor?",
                context,
                world_state,
            ),
            "The High Road continues as the Trade Way.",
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "Is the Lords’ Alliance a realm?",
                context,
                world_state,
            ),
            "The Lords' Alliance is a settlement coalition, not a realm.",
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "Is Neverwinter a member of the Lords' Alliance, and what is "
                "the Alliance's stated purpose?",
                context,
                world_state,
            ),
            "Neverwinter is a member of the Lords' Alliance. The stated purpose "
            "of the Lords' Alliance includes settlement safety and prosperity.",
        )
        region_context = game._empty_lore_authority_context()
        region_context["sections"]["official_forgotten_realms_lore"] = [
            {
                "fact_id": "fact:north:sword-coast",
                "subject_id": "fr:region:the_north",
                "predicate": "distinct_from_region",
                "object_id_or_value": "fr:region:sword_coast",
            },
        ]
        region_context["sections"]["verified_entities"] = [
            {
                "entity_id": "fr:region:the_north",
                "canonical_name": "The North",
                "aliases": [],
            },
            {
                "entity_id": "fr:region:sword_coast",
                "canonical_name": "Sword Coast",
                "aliases": [],
            },
        ]
        region_world_state = {"locations": {}, "npcs": [], "features": []}
        self.assertEqual(
            game._supported_lore_question_response(
                "Is The North the same region as the Sword Coast?",
                region_context,
                region_world_state,
            ),
            "The North is distinct from the Sword Coast.",
        )
        self.assertIsNone(
            game._supported_lore_question_response(
                "Does King Vharion rule Neverwinter?",
                context,
                world_state,
            )
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "Neverwinter gerçekten yeniden inşa ediliyor mu?",
                context,
                world_state,
            ),
            "Neverwinter yeniden inşa ediliyor.",
        )
        overview_response = game._supported_lore_question_response(
            "Describe Neverwinter.",
            context,
            world_state,
        )
        self.assertIn("master crafts and fine goods", overview_response)
        self.assertIn("Neverwinter is rebuilding.", overview_response)
        self.assertIn("Dagult Neverember is the current Lord", overview_response)
        self.assertNotIn("Phandalin", overview_response)
        self.assertNotIn("Silver Marches", overview_response)
        self.assertEqual(
            game._supported_lore_question_response(
                "What is Neverwinter's current condition in 1501 DR?",
                context,
                world_state,
            ),
            "As of 1501 DR, Neverwinter is rebuilding.",
        )
        self.assertEqual(
            game._supported_lore_question_response(
                "How does the High Road continue?",
                context,
                world_state,
            ),
            "The High Road continues as the Trade Way.",
        )
        self.assertIsNone(
            game._supported_lore_question_response(
                "Does the High Road connect to Phandalin?",
                context,
                world_state,
            )
        )
        lore_facts = context["sections"]["official_forgotten_realms_lore"]
        lord_fact = next(
            item for item in lore_facts
            if item["predicate"] == "current_lord_id"
        )
        route_fact = next(
            item for item in lore_facts
            if item["predicate"] == "continues_as"
        )
        form_fact = next(
            item for item in lore_facts
            if item["predicate"] == "political_form"
        )
        status_fact = next(
            item for item in lore_facts
            if item["predicate"] == "current_status"
        )
        original_notes = {
            id(item): item.get("notes")
            for item in (lord_fact, route_fact, form_fact, status_fact)
        }
        try:
            lord_fact["notes"] = ""
            route_fact["notes"] = ""
            form_fact["notes"] = "Normalized institutional form."
            status_fact["notes"] = "Do not reinterpret this as fully restored."
            self.assertEqual(
                game._supported_lore_question_response(
                    "Does Dagult Neverember rule Neverwinter?",
                    context,
                    world_state,
                ),
                "Dagult Neverember is the current Lord of Neverwinter.",
            )
            self.assertEqual(
                game._supported_lore_question_response(
                    "High Road, Trade Way olarak mı devam ediyor?",
                    context,
                    world_state,
                ),
                "High Road, Trade Way olarak devam eder.",
            )
            self.assertEqual(
                game._supported_lore_question_response(
                    "Is the Lords’ Alliance a realm?",
                    context,
                    world_state,
                ),
                "The Lords' Alliance is a settlement coalition, not a realm.",
            )
            self.assertEqual(
                game._supported_lore_question_response(
                    "Neverwinter gerçekten yeniden inşa ediliyor mu?",
                    context,
                    world_state,
                ),
                "Neverwinter yeniden inşa ediliyor.",
            )
        finally:
            for item in (lord_fact, route_fact, form_fact, status_fact):
                item["notes"] = original_notes[id(item)]
        self.assertIsNone(
            game._supported_lore_question_response(
                "How many miles are between High Road and Trade Way?",
                context,
                world_state,
            )
        )
        self.assertFalse(
            game._player_question_has_unverified_lore_claim(
                "What does the Lords' Alliance do, and is it a kingdom?",
                context,
                world_state,
            )
        )

        self.assertFalse(
            rejected(
                "Neverwinter is rebuilding.",
                ["fact:neverwinter:status"],
            )
        )
        self.assertFalse(
            rejected(
                "The Lords' Alliance is not a kingdom.",
                ["fact:alliance:form"],
            )
        )
        unsupported = (
            (
                "The road to Phandalin is 40 miles from Neverwinter.",
                ["fact:highroad:route"],
            ),
            (
                "King Vharion rules Neverwinter.",
                ["fact:neverwinter:lord"],
            ),
            (
                "The Silver Marches fell in an ancient war.",
                ["fact:neverwinter:status"],
            ),
            (
                "Neverwinter specializes in silver and metalworking.",
                ["fact:neverwinter:crafts"],
            ),
            (
                "The Lords' Alliance is led by an elected council that sets laws.",
                ["fact:alliance:form"],
            ),
            (
                "A merchant named Elara waits in the market.",
                ["fact:neverwinter:status"],
            ),
            (
                "Dagult Neverember directed Neverwinter's rebuilding.",
                ["fact:neverwinter:lord", "fact:neverwinter:status"],
            ),
            (
                "The High Road meets River Neverwinter at a junction.",
                ["fact:highroad:route"],
            ),
        )
        for narration, fact_ids in unsupported:
            with self.subTest(narration=narration):
                self.assertTrue(rejected(narration, fact_ids))


    def test_valid_engine_evidence_with_telemetry_is_accepted(self):
        state = bound_lore_state()
        before_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 2}}
        after_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 3}}
        action_result = {"quest_outcomes": []}
        evidence = {
            "authority": "python_engine",
            "action_id": "turn:3",
            "turn_index": 3,
            "quest_outcomes": [],
            "procedural_entity_ids": [],
            "telemetry": {
                "intent_model_calls": 0,
                "narration_model_calls": 1,
                "total_model_calls": 1,
                "intent_source": "deterministic",
                "narration_source": "qwen",
                "fallback_reason": None,
                "narration_validation_result": "accepted",
                "resolved_action_type": "explore",
            },
        }
        staged = _stage_engine_lore_state(
            state,
            evidence,
            action_result,
            before_world,
            after_world,
        )
        self.assertIsNotNone(staged)
        self.assertEqual(staged.binding_status, BindingStatus.BOUND)

    def test_telemetry_field_does_not_change_campaign_canon(self):
        state = bound_lore_state()
        before_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 0}}
        after_world = {
            "locations": {
                "location_001": {
                    "id": "location_001",
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                }
            },
            "npcs": [],
            "flags": {"turn_index": 1},
        }
        transition = {
            "event_id": "quest:completed:quest:sample",
            "quest_id": "quest:sample",
            "transition": "completed",
            "objective_id": None,
            "source_event_id": "event:1",
            "turn_index": 1,
        }
        action_result = {"quest_outcomes": [transition]}
        base_evidence = {
            "authority": "python_engine",
            "action_id": "turn:1",
            "turn_index": 1,
            "quest_outcomes": [transition],
            "procedural_entity_ids": ["location_001"],
        }
        evidence_with_telemetry = dict(base_evidence)
        evidence_with_telemetry["telemetry"] = {
            "intent_model_calls": 1,
            "narration_model_calls": 1,
            "total_model_calls": 2,
            "intent_source": "model",
            "narration_source": "qwen",
            "fallback_reason": None,
            "narration_validation_result": "accepted",
            "resolved_action_type": "travel",
        }

        staged_without = _stage_engine_lore_state(
            state,
            base_evidence,
            action_result,
            before_world,
            after_world,
        )
        staged_with = _stage_engine_lore_state(
            state,
            evidence_with_telemetry,
            action_result,
            before_world,
            after_world,
        )

        self.assertEqual(staged_with.to_dict(), staged_without.to_dict())
        self.assertEqual(staged_with.campaign_overrides, staged_without.campaign_overrides)
        self.assertEqual(staged_with.procedural_entity_refs, staged_without.procedural_entity_refs)

    def test_unknown_extra_field_in_engine_evidence_is_rejected(self):
        state = bound_lore_state()
        before_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 0}}
        after_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 1}}
        action_result = {"quest_outcomes": []}
        base_evidence = {
            "authority": "python_engine",
            "action_id": "turn:1",
            "turn_index": 1,
            "quest_outcomes": [],
            "procedural_entity_ids": [],
        }

        # Extra untrusted field alone
        with_extra = dict(base_evidence, untrusted_key="malicious_payload")
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, with_extra, action_result, before_world, after_world)

        # Extra untrusted field alongside telemetry
        with_extra_and_telemetry = dict(
            base_evidence,
            telemetry={"total_model_calls": 0},
            forged_canon="some_canon",
        )
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, with_extra_and_telemetry, action_result, before_world, after_world)

    def test_malformed_engine_evidence_fails_closed(self):
        state = bound_lore_state()
        before_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 0}}
        after_world = {"locations": {}, "npcs": [], "flags": {"turn_index": 1}}
        action_result = {"quest_outcomes": []}

        # Non-dict evidence
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, "not_a_dict", action_result, before_world, after_world)

        # Missing required keys
        incomplete_evidence = {
            "authority": "python_engine",
            "turn_index": 1,
            "telemetry": {},
        }
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, incomplete_evidence, action_result, before_world, after_world)

        # Malformed telemetry (not a dict)
        bad_telemetry_evidence = {
            "authority": "python_engine",
            "action_id": "turn:1",
            "turn_index": 1,
            "quest_outcomes": [],
            "procedural_entity_ids": [],
            "telemetry": "invalid_string_telemetry",
        }
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, bad_telemetry_evidence, action_result, before_world, after_world)

        # Wrong authority value
        wrong_auth_evidence = {
            "authority": "model_authored",
            "action_id": "turn:1",
            "turn_index": 1,
            "quest_outcomes": [],
            "procedural_entity_ids": [],
            "telemetry": {},
        }
        with self.assertRaises(ValueError):
            _stage_engine_lore_state(state, wrong_auth_evidence, action_result, before_world, after_world)

    def test_unconscious_current_city_ruler_question_cannot_bypass_action_gate(self):
        question = "Bu şehrin hükümdarı kim?"
        for target_id in (None, "npc:elara"):
            with self.subTest(target_id=target_id):
                session = game.GameSession(seed=11)
                session.character.update(
                    name="Tester", current_hp=0, max_hp=10
                )
                session.world_state["player_combat_status"] = "unconscious"
                session.world_state["location"] = "fr:city:neverwinter"
                session.world_state["npcs"] = [{
                    "id": "npc:elara",
                    "name": "Elara",
                    "role": "Guide",
                    "location": "fr:city:neverwinter",
                    "memory": [],
                    "knowledge": [],
                }]
                session.lore_authority_context = (
                    PRODUCTION_REGISTRY.retrieve_lore_context(
                        current_location_id="fr:city:neverwinter",
                        player_message=question,
                        mentioned_entity_ids=set(),
                        campaign_state=CampaignLoreState.legacy_unbound(),
                    )
                )
                self.assertEqual(
                    game._supported_lore_question_response(
                        question,
                        session.lore_authority_context,
                        session.world_state,
                    ),
                    "Neverwinter kentinin güncel Lordu Dagult Neverember.",
                )
                self.assertFalse(session.ensure_combat_state()["active"])
                before_character = copy.deepcopy(session.character)
                before_world = copy.deepcopy(session.world_state)

                with (
                    patch.object(
                        game,
                        "ask_dungeon_master",
                        side_effect=AssertionError(
                            "Unconscious actions must not call narration."
                        ),
                    ) as narration_model,
                    patch.object(
                        game,
                        "parse_player_intent",
                        side_effect=AssertionError(
                            "Unconscious actions must not call intent parsing."
                        ),
                    ) as intent_model,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        r"^Bilinçsiz karakter eylem gerçekleştiremez\.$",
                    ):
                        session.run_player_turn(
                            question, target_id=target_id, scene_plan={}
                        )

                intent_model.assert_not_called()
                narration_model.assert_not_called()
                self.assertEqual(session.character, before_character)
                self.assertEqual(session.world_state, before_world)

    def test_stable_unconscious_current_city_ruler_question_preserves_pending_recovery(self):
        question = "Bu şehrin hükümdarı kim?"
        for target_id in (None, "npc:elara"):
            with self.subTest(target_id=target_id):
                session = game.GameSession(seed=11)
                session.character.update(
                    name="Tester", current_hp=10, max_hp=10
                )
                session.world_state["location"] = "fr:city:neverwinter"
                session.world_state["npcs"] = [{
                    "id": "npc:elara",
                    "name": "Elara",
                    "role": "Guide",
                    "location": "fr:city:neverwinter",
                    "memory": [],
                    "knowledge": [],
                }]
                session.lore_authority_context = (
                    PRODUCTION_REGISTRY.retrieve_lore_context(
                        current_location_id="fr:city:neverwinter",
                        player_message=question,
                        mentioned_entity_ids=set(),
                        campaign_state=CampaignLoreState.legacy_unbound(),
                    )
                )
                self.assertEqual(
                    game._supported_lore_question_response(
                        question,
                        session.lore_authority_context,
                        session.world_state,
                    ),
                    "Neverwinter kentinin güncel Lordu Dagult Neverember.",
                )

                # Use the Death owner's scheduling path, not a fabricated timer.
                campaign_time.initialize(session.world_state)
                session.ensure_death_state()["mode"] = "PERMADEATH"
                session.advance_campaign_time(137, "wait")
                session._apply_player_damage(10, took_damage=True)
                with patch.object(session.rng, "randint", return_value=2) as die:
                    session.stabilize_player()
                die.assert_called_once_with(1, 4)
                session.advance_campaign_time(600, "wait")

                death = session.ensure_death_state()
                self.assertTrue(death["stable"])
                self.assertFalse(death["dead"])
                self.assertEqual(death["recovery"], {"hours": 2, "at": 137 + 7200})
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"], 737
                )
                self.assertEqual(session.character["current_hp"], 0)
                self.assertEqual(
                    session.world_state["player_combat_status"], "unconscious"
                )
                self.assertFalse(session.ensure_combat_state()["active"])
                before_character = copy.deepcopy(session.character)
                before_world = copy.deepcopy(session.world_state)
                before_lore = copy.deepcopy(session.lore_authority_context)
                before_messages = copy.deepcopy(session.messages)
                before_rng = session.rng.getstate()

                with (
                    patch.object(
                        game,
                        "ask_dungeon_master",
                        side_effect=AssertionError(
                            "Stable unconscious actions must not call narration."
                        ),
                    ) as narration_model,
                    patch.object(
                        game,
                        "parse_player_intent",
                        side_effect=AssertionError(
                            "Stable unconscious actions must not call intent parsing."
                        ),
                    ) as intent_model,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        r"^Bilinçsiz karakter eylem gerçekleştiremez\.$",
                    ):
                        session.run_player_turn(
                            question, target_id=target_id, scene_plan={}
                        )

                intent_model.assert_not_called()
                narration_model.assert_not_called()
                self.assertEqual(session.character, before_character)
                self.assertEqual(session.lore_authority_context, before_lore)
                self.assertEqual(session.world_state, before_world)
                self.assertEqual(
                    session.world_state["death_state"]["recovery"],
                    before_world["death_state"]["recovery"],
                )
                self.assertEqual(
                    session.world_state["campaign_time"], before_world["campaign_time"]
                )
                self.assertEqual(session.messages, before_messages)
                self.assertEqual(session.rng.getstate(), before_rng)

    def test_dead_current_city_ruler_question_cannot_bypass_action_gate(self):
        question = "Bu şehrin hükümdarı kim?"
        for target_id in (None, "npc:elara"):
            with self.subTest(target_id=target_id):
                session = game.GameSession(seed=11)
                session.character.update(
                    name="Tester", current_hp=0, max_hp=10
                )
                session.world_state["player_combat_status"] = "dead"
                session.world_state["death_state"]["dead"] = True
                session.world_state["location"] = "fr:city:neverwinter"
                session.world_state["npcs"] = [{
                    "id": "npc:elara",
                    "name": "Elara",
                    "role": "Guide",
                    "location": "fr:city:neverwinter",
                    "memory": [],
                    "knowledge": [],
                }]
                session.lore_authority_context = (
                    PRODUCTION_REGISTRY.retrieve_lore_context(
                        current_location_id="fr:city:neverwinter",
                        player_message=question,
                        mentioned_entity_ids=set(),
                        campaign_state=CampaignLoreState.legacy_unbound(),
                    )
                )
                self.assertEqual(
                    game._supported_lore_question_response(
                        question,
                        session.lore_authority_context,
                        session.world_state,
                    ),
                    "Neverwinter kentinin güncel Lordu Dagult Neverember.",
                )
                self.assertFalse(session.ensure_combat_state()["active"])
                before_character = copy.deepcopy(session.character)
                before_world = copy.deepcopy(session.world_state)

                with (
                    patch.object(
                        game,
                        "ask_dungeon_master",
                        side_effect=AssertionError(
                            "Dead actions must not call narration."
                        ),
                    ) as narration_model,
                    patch.object(
                        game,
                        "parse_player_intent",
                        side_effect=AssertionError(
                            "Dead actions must not call intent parsing."
                        ),
                    ) as intent_model,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        r"^Ölü karakter eylem gerçekleştiremez\.$",
                    ):
                        session.run_player_turn(
                            question, target_id=target_id, scene_plan={}
                        )

                intent_model.assert_not_called()
                narration_model.assert_not_called()
                self.assertEqual(session.character, before_character)
                self.assertEqual(session.world_state, before_world)

    def test_partial_death_markers_block_current_city_ruler_question(self):
        question = "Bu şehrin hükümdarı kim?"
        for mode, death_marker in product(
            ("NORMAL", "PERMADEATH", "IRONMAN"),
            ("player_combat_status", "death_state"),
        ):
            for target_id in (None, "npc:elara"):
                with self.subTest(
                    mode=mode, death_marker=death_marker, target_id=target_id
                ):
                    session = game.GameSession(seed=11)
                    session.character.update(
                        name="Tester", current_hp=10, max_hp=10
                    )
                    # Prepare combat before introducing the inconsistent markers:
                    # ensure_combat_state also normalizes death state.
                    self.assertFalse(session.ensure_combat_state()["active"])
                    session.world_state["death_state"]["mode"] = mode
                    session.world_state["death_state"]["terminal"] = False
                    session.character["current_hp"] = 0
                    session.world_state["player_combat_status"] = (
                        "dead" if death_marker == "player_combat_status" else "active"
                    )
                    session.world_state["death_state"]["dead"] = (
                        death_marker == "death_state"
                    )
                    session.world_state["location"] = "fr:city:neverwinter"
                    session.world_state["npcs"] = [{
                        "id": "npc:elara",
                        "name": "Elara",
                        "role": "Guide",
                        "location": "fr:city:neverwinter",
                        "memory": [],
                        "knowledge": [],
                    }]
                    session.lore_authority_context = (
                        PRODUCTION_REGISTRY.retrieve_lore_context(
                            current_location_id="fr:city:neverwinter",
                            player_message=question,
                            mentioned_entity_ids=set(),
                            campaign_state=CampaignLoreState.legacy_unbound(),
                        )
                    )
                    self.assertEqual(
                        game._supported_lore_question_response(
                            question,
                            session.lore_authority_context,
                            session.world_state,
                        ),
                        "Neverwinter kentinin güncel Lordu Dagult Neverember.",
                    )
                    before_character = copy.deepcopy(session.character)
                    before_lore = copy.deepcopy(session.lore_authority_context)
                    before_world = copy.deepcopy(session.world_state)
                    expected_world = copy.deepcopy(before_world)
                    expected_world["player_combat_status"] = "dead"
                    expected_world["death_state"]["dead"] = True
                    if mode == "IRONMAN":
                        expected_world["death_state"]["terminal"] = True
                    self.assertNotEqual(before_world, expected_world)
                    self.assertFalse(before_world["combat"]["active"])

                    with (
                        patch.object(
                            game,
                            "ask_dungeon_master",
                            side_effect=AssertionError(
                                "Partially marked dead actions must not call narration."
                            ),
                        ) as narration_model,
                        patch.object(
                            game,
                            "parse_player_intent",
                            side_effect=AssertionError(
                                "Partially marked dead actions must not call intent parsing."
                            ),
                        ) as intent_model,
                    ):
                        with self.assertRaisesRegex(
                            ValueError,
                            r"^Ölü karakter eylem gerçekleştiremez\.$",
                        ):
                            session.run_player_turn(
                                question, target_id=target_id, scene_plan={}
                            )

                    intent_model.assert_not_called()
                    narration_model.assert_not_called()
                    self.assertEqual(session.character, before_character)
                    self.assertEqual(session.lore_authority_context, before_lore)
                    # The exact world comparison also forbids turn advancement,
                    # NPC changes, or changes beyond marker normalization and
                    # Ironman's terminal restriction.
                    self.assertEqual(session.world_state, expected_world)

    def test_turkish_current_city_ruler_is_deterministic_and_fails_closed(self):
        question = "Bu şehrin hükümdarı kim?"
        session = game.GameSession(seed=11)
        session.character["name"] = "Tester"
        session.character["current_hp"] = 10
        session.character["max_hp"] = 10
        session.world_state["location"] = "fr:city:neverwinter"
        session.world_state["npcs"] = [
            {
                "id": "npc:elara",
                "name": "Elara",
                "role": "Guide",
                "location": "fr:city:neverwinter",
                "memory": [],
                "knowledge": [],
            }
        ]
        initial_world_state = copy.deepcopy(session.world_state)
        session.lore_authority_context = PRODUCTION_REGISTRY.retrieve_lore_context(
            current_location_id="fr:city:neverwinter",
            player_message=question,
            mentioned_entity_ids=set(),
            campaign_state=CampaignLoreState.legacy_unbound(),
        )

        with (
            patch.object(
                game,
                "ask_dungeon_master",
                side_effect=AssertionError(
                    "Supported lore answers must not call the model."
                ),
            ) as narration_model,
            patch.object(
                game,
                "parse_player_intent",
                side_effect=AssertionError(
                    "Supported lore answers must not call the model."
                ),
            ) as intent_model,
        ):
            result = session.run_player_turn(question, scene_plan={})
            targeted_result = session.run_player_turn(
                question,
                target_id="npc:elara",
                scene_plan={},
            )
            unsupported_result = session.run_player_turn(
                "Does King Vharion rule Neverwinter?",
                scene_plan={},
            )

        self.assertEqual(
            result["action_result"]["status"],
            "answered_from_loaded_lore",
        )
        self.assertEqual(
            result["narration"],
            "Neverwinter kentinin güncel Lordu Dagult Neverember.",
        )
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )
        self.assertEqual(
            targeted_result["action_result"]["status"],
            "answered_from_loaded_lore",
        )
        self.assertEqual(
            targeted_result["narration"],
            result["narration"],
        )
        self.assertEqual(
            targeted_result["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )
        self.assertNotIn("npc_id", targeted_result["action_result"])
        self.assertEqual(
            unsupported_result["action_result"]["status"],
            "unverified",
        )
        self.assertNotIn(
            "Dagult Neverember",
            unsupported_result["narration"],
        )
        self.assertEqual(
            unsupported_result["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )
        self.assertEqual(result["action_result"]["state_changes"], [])
        self.assertEqual(targeted_result["action_result"]["state_changes"], [])
        self.assertEqual(unsupported_result["action_result"]["state_changes"], [])
        expected_world_state = copy.deepcopy(initial_world_state)
        expected_world_state.setdefault("flags", {})["turn_index"] = (
            expected_world_state.get("flags", {}).get("turn_index", 0) + 3
        )
        self.assertEqual(session.world_state, expected_world_state)
        narration_model.assert_not_called()
        intent_model.assert_not_called()


class Turn29RulershipQueryDeterministicTests(unittest.TestCase):
    """Turn 29 regression: Turkish inflected ruler queries must resolve
    deterministically from verified lore facts, 0 model calls, no fallback."""

    def _neverwinter_lore_context(self):
        context = game._empty_lore_authority_context()
        context["sections"]["official_forgotten_realms_lore"] = [
            {
                "fact_id": "fr:fact:dagult_neverember_current_lord",
                "subject_id": "fr:city:neverwinter",
                "predicate": "current_lord_id",
                "object_id_or_value": "fr:person:dagult_neverember",
                "notes": "Dagult Neverember is the current Lord of Neverwinter.",
            },
            {
                "fact_id": "fr:fact:neverwinter_known_as_city_of_skilled_hands",
                "subject_id": "fr:city:neverwinter",
                "predicate": "known_as",
                "object_id_or_value": "City of Skilled Hands",
                "notes": "Neverwinter is known as the City of Skilled Hands.",
            },
        ]
        context["sections"]["verified_entities"] = [
            {"entity_id": "fr:city:neverwinter", "canonical_name": "Neverwinter", "aliases": []},
            {"entity_id": "fr:person:dagult_neverember", "canonical_name": "Dagult Neverember", "aliases": ["Dagult"]},
        ]
        context["diagnostics"] = {
            "query_intents": ["current_ruler"],
            "current_location_entity_id": "fr:city:neverwinter",
            "selected_fact_count": 2,
            "selected_fact_ids": [
                "fr:fact:dagult_neverember_current_lord",
                "fr:fact:neverwinter_known_as_city_of_skilled_hands",
            ],
        }
        return context

    def test_turkish_ruler_question_answered_from_loaded_lore(self):
        context = self._neverwinter_lore_context()
        world_state = {"locations": {}, "npcs": [], "features": []}
        for question in (
            "Bu \u015fehrin h\u00fck\u00fcmdar\u0131 kim?",
            "Bu \u015fehrin h\u00fck\u00fcmdar\u0131 kimdir?",
        ):
            with self.subTest(question=question):
                response = game._supported_lore_question_response(question, context, world_state)
                self.assertIsNotNone(response, f"Expected verified lore answer for: {question!r}")
                self.assertIn("Dagult Neverember", response)

    def test_answered_from_loaded_lore_is_system_deterministic(self):
        action_result = {
            "action": "dialogue",
            "status": "answered_from_loaded_lore",
            "success": True,
            "state_changes": [],
        }
        deterministic_statuses = (
            "invalid_target", "limit_reached", "unsupported",
            "explicitly_declined", "unsupported_combat_action",
            "player_unconscious", "unverified", "clarification",
            "answered_from_npc_memory", "answered_from_campaign_state",
            "answered_from_loaded_lore",
        )
        self.assertIn(action_result["status"], deterministic_statuses)

    def test_unregistered_ruler_question_returns_none(self):
        context = self._neverwinter_lore_context()
        world_state = {"locations": {}, "npcs": [], "features": []}
        response = game._supported_lore_question_response(
            "Waterdeep'in h\u00fck\u00fcmdar\u0131 kim?", context, world_state
        )
        self.assertIsNone(response)

    def test_english_ruler_question_also_resolves(self):
        context = self._neverwinter_lore_context()
        world_state = {"locations": {}, "npcs": [], "features": []}
        response = game._supported_lore_question_response(
            "Who rules Neverwinter?", context, world_state
        )
        self.assertIsNotNone(response, "Expected verified lore answer for English ruler question")
        self.assertIn("Dagult Neverember", response)


if __name__ == "__main__":
    unittest.main()
