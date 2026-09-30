from __future__ import annotations

import unittest
from types import SimpleNamespace

import game
from api.lore_authority import BindingStatus, CampaignLoreState
from api.main import _lore_context_for_turn, _stage_engine_lore_state
from api.session_manager import SessionManager


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

if __name__ == "__main__":
    unittest.main()
