from __future__ import annotations

import json
import unittest
from unittest import mock

from api.lore_authority import (
    BindingStatus,
    CampaignCanonOverride,
    CampaignLoreState,
    ClaimType,
    EngineActionEvidence,
    EntityType,
    LoreEdge,
    LoreEntity,
    LoreFact,
    LoreLayer,
    LoreRegistry,
    PRODUCTION_REGISTRY,
    Relationship,
    ResolutionStatus,
    ReviewStatus,
    SourceManifest,
    SourceTier,
    VisibilityScope,
    apply_campaign_override,
    apply_committed_world_canon,
    bind_campaign,
    build_reviewed_registry,
    default_lore_registry,
    get_player_known_lore,
    grant_npc_knowledge,
    record_player_discovery,
    review_item,
    validate_ingestion_pack,
)


def source(source_id: str = "source:current", tier: str = "TIER_1_CURRENT_CORE") -> dict:
    return {
        "source_id": source_id,
        "title": "Synthetic test source",
        "publisher": "Test fixture",
        "publication_year": 2026,
        "edition_family": "test",
        "source_tier": tier,
        "setting": "test-setting",
        "region_scope": None,
        "authority_status": "VERIFIED",
        "owner_access_status": "AUTHORIZED",
        "notes": "Synthetic data for isolated unit tests.",
    }


def entity(
    entity_id: str,
    name: str,
    *,
    entity_type: str = "WORLD",
    source_id: str = "source:current",
    tier: str = "TIER_1_CURRENT_CORE",
    aliases: list[str] | None = None,
) -> dict:
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "canonical_name": name,
        "aliases": aliases or [],
        "setting": "test-setting",
        "region_scope": None,
        "source_id": source_id,
        "source_reference": "Test source, section A",
        "authority_tier": tier,
        "review_status": "VERIFIED_CANON",
        "valid_from": None,
        "valid_until": None,
        "notes": "",
    }


def fact(
    fact_id: str,
    subject_id: str,
    predicate: str,
    value: str,
    *,
    source_id: str = "source:current",
    tier: str = "TIER_1_CURRENT_CORE",
    visibility: str = "COMMON_KNOWLEDGE",
    region_scope: str | None = None,
    claim_type: str = "OBJECTIVE_CANON_FACT",
    temporal_scope: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
) -> dict:
    return {
        "fact_id": fact_id,
        "subject_id": subject_id,
        "predicate": predicate,
        "object_id_or_value": value,
        "claim_type": claim_type,
        "authority_tier": tier,
        "source_id": source_id,
        "source_reference": "Test source, section A",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "temporal_scope": temporal_scope,
        "visibility": visibility,
        "region_scope": region_scope,
        "notes": "",
        "reality_layer": "OFFICIAL_SETTING_CANON",
        "review_status": "VERIFIED_CANON",
    }


def verified_registry(
    *,
    sources: list[dict] | None = None,
    entities: list[dict] | None = None,
    edges: list[dict] | None = None,
    facts: list[dict] | None = None,
) -> LoreRegistry:
    source_rows = sources or [source()]
    entity_rows = entities or [entity("world:test", "Test World")]
    return LoreRegistry(
        sources=[SourceManifest.from_mapping(row) for row in source_rows],
        entities=[LoreEntity.from_mapping(row) for row in entity_rows],
        edges=[LoreEdge.from_mapping(row) for row in edges or []],
        facts=[LoreFact.from_mapping(row) for row in facts or []],
    )


class LoreAuthorityTests(unittest.TestCase):
    def test_production_registry_is_empty_until_authorized_data_is_loaded(self):
        registry = default_lore_registry()

        self.assertEqual(registry.source_count, 0)
        self.assertEqual(registry.entity_count, 0)
        self.assertEqual(registry.fact_count, 0)
        self.assertEqual(
            registry.source_coverage()["status"],
            "SOURCE_INGESTION_REQUIRED_FOR_FULL_COVERAGE",
        )
        self.assertFalse(registry.source_coverage()["model_memory_used_as_source"])

    def test_source_precedence_selects_newer_higher_tier(self):
        older = source("source:older", "TIER_3_OLDER_OFFICIAL")
        current = source("source:current", "TIER_1_CURRENT_CORE")
        entities = [
            entity("world:test", "Test World"),
        ]
        facts = [
            fact(
                "fact:older",
                "world:test",
                "capital",
                "Old City",
                source_id="source:older",
                tier="TIER_3_OLDER_OFFICIAL",
            ),
            fact("fact:current", "world:test", "capital", "New City"),
        ]
        registry = verified_registry(
            sources=[older, current],
            entities=entities,
            facts=facts,
        )

        result = registry.validate_lore_claim(
            subject_id="world:test",
            predicate="capital",
            object_id_or_value="New City",
        )

        self.assertEqual(result.status, ResolutionStatus.RESOLVED)
        self.assertEqual(result.matching_fact_ids, ("fact:current",))

    def test_same_tier_conflict_fails_closed(self):
        rows = [
            fact("fact:a", "world:test", "capital", "City A"),
            fact("fact:b", "world:test", "capital", "City B"),
        ]
        registry = verified_registry(facts=rows)

        result = registry.validate_lore_claim(
            subject_id="world:test",
            predicate="capital",
            object_id_or_value="City A",
        )

        self.assertEqual(result.status, ResolutionStatus.CANON_CONFLICT_UNRESOLVED)
        self.assertEqual(result.expected_values, ())

    def test_alias_resolution_reports_same_name_ambiguity(self):
        registry = verified_registry(
            entities=[
                entity(
                    "city:a",
                    "Shared Name",
                    entity_type="CITY",
                    aliases=["Twin City"],
                ),
                entity(
                    "city:b",
                    "Another City",
                    entity_type="CITY",
                    aliases=["Twin City"],
                ),
            ]
        )

        result = registry.resolve_entity("twin city")

        self.assertEqual(result.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(result.entity_ids, ("city:a", "city:b"))

    def test_mentioned_entity_ids_extracts_only_registered_aliases(self):
        registry = verified_registry(
            entities=[
                entity(
                    "city:waterdeep",
                    "Waterdeep",
                    entity_type="CITY",
                    aliases=["City of Splendors"],
                    source_id="source:current",
                ),
                entity(
                    "city:outside",
                    "Outside City",
                    entity_type="CITY",
                    aliases=["Waterdeep"],
                    source_id="source:current",
                ),
            ]
        )

        self.assertEqual(
            registry.mentioned_entity_ids("What is known of Waterdeep?"),
            ("city:outside", "city:waterdeep"),
        )
        self.assertEqual(
            registry.mentioned_entity_ids("I heard of the City of Splendors."),
            ("city:waterdeep",),
        )
        self.assertEqual(registry.mentioned_entity_ids("Waterdeepish"), ())

    def test_region_display_names_match_bound_region_ids(self):
        north = entity(
            "region:north",
            "The North",
            entity_type="REGION",
        )
        neverwinter = entity(
            "city:neverwinter",
            "Neverwinter",
            entity_type="CITY",
        )
        neverwinter["region_scope"] = "The North"
        registry = verified_registry(
            entities=[
                entity("world:test", "Test World"),
                north,
                neverwinter,
            ],
            facts=[
                fact(
                    "fact:neverwinter_status",
                    "city:neverwinter",
                    "city_status",
                    "Rebuilding",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="The North",
                )
            ],
        )
        state = CampaignLoreState.from_mapping(
            {
                "binding_status": "BOUND",
                "setting_profile": "TEST_SETTING",
                "world_id": "world:test",
                "epoch_id": "epoch:test",
                "region_id": "region:north",
                "current_location_entity_id": "city:neverwinter",
                "starting_location_entity_id": "city:neverwinter",
                "region_pack_id": "test:pack",
                "player_known_fact_ids": [],
                "npc_known_fact_ids": {},
                "campaign_overrides": [],
                "procedural_entity_refs": [],
                "lore_discoveries": [],
            }
        )

        self.assertEqual(
            registry.mentioned_entity_ids(
                "What is known about Neverwinter?",
                region_scope="region:north",
            ),
            ("city:neverwinter",),
        )
        packet = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            mentioned_entity_ids={"city:neverwinter"},
            campaign_state=state,
        )
        self.assertIn(
            "fact:neverwinter_status",
            {
                item["fact_id"]
                for item in packet["sections"]["official_forgotten_realms_lore"]
            },
        )
        self.assertEqual(
            registry.validate_lore_claim(
                subject_id="city:neverwinter",
                predicate="city_status",
                object_id_or_value="Rebuilding",
                region_ids={"region:north"},
            ).status,
            ResolutionStatus.RESOLVED,
        )
        self.assertEqual(
            tuple(
                item.fact_id
                for item in registry.get_player_known_lore(
                    ["fact:neverwinter_status"],
                    region_ids={"region:north"},
                )
            ),
            ("fact:neverwinter_status",),
        )

    def test_player_knowledge_filters_secrets_and_respects_regions(self):
        facts = [
            fact("fact:common", "world:test", "common_custom", "Known"),
            fact(
                "fact:regional",
                "world:test",
                "regional_custom",
                "Local",
                visibility="REGIONAL_KNOWLEDGE",
                region_scope="region:test",
            ),
            fact(
                "fact:specialist",
                "world:test",
                "specialist_custom",
                "Specialist",
                visibility="SPECIALIST_KNOWLEDGE",
            ),
            fact(
                "fact:secret",
                "world:test",
                "secret_custom",
                "Hidden",
                visibility="DISCOVERABLE_SECRET",
            ),
            fact(
                "fact:dm",
                "world:test",
                "dm_custom",
                "DM only",
                visibility="DM_SECRET",
            ),
        ]
        registry = verified_registry(facts=facts)

        known = get_player_known_lore(
            registry,
            ["fact:common", "fact:specialist", "fact:secret", "fact:dm"],
            region_ids={"region:test"},
        )

        self.assertEqual(
            {item.fact_id for item in known},
            {"fact:common", "fact:specialist", "fact:secret"},
        )
        packet = registry.retrieve_lore_context(
            mentioned_entity_ids={"world:test"},
            campaign_state=CampaignLoreState.from_mapping(
                {
                    "binding_status": "BOUND",
                    "setting_profile": "TEST_SETTING",
                    "world_id": "world:test",
                    "epoch_id": "epoch:test",
                    "region_id": "region:test",
                    "current_location_entity_id": "location:test",
                    "player_known_fact_ids": ["fact:secret"],
                    "npc_known_fact_ids": {},
                    "campaign_overrides": [],
                    "procedural_entity_refs": [],
                    "lore_discoveries": ["fact:secret"],
                }
            ),
        )
        context_ids = {
            row["fact_id"]
            for row in packet["sections"]["official_forgotten_realms_lore"]
        }
        self.assertNotIn("fact:dm", context_ids)
        self.assertIn("fact:secret", context_ids)

    def test_legacy_campaign_defaults_to_unbound_and_rejects_silent_binding(self):
        state = CampaignLoreState.from_mapping(None)

        self.assertEqual(state.binding_status, BindingStatus.LEGACY_UNBOUND)
        self.assertIsNone(state.region_id)
        self.assertEqual(
            CampaignLoreState.from_mapping(state.to_dict()).to_dict(),
            state.to_dict(),
        )
        malformed = state.to_dict()
        malformed["region_id"] = "region:guessed"
        with self.assertRaises(ValueError):
            CampaignLoreState.from_mapping(malformed)

    def test_ingestion_requires_provenance_and_never_self_promotes(self):
        raw = {
            "schema_version": 1,
            "sources": [source()],
            "entities": [
                {
                    **entity("world:test", "Test World"),
                    "review_status": "UNREVIEWED_EXTRACTED",
                }
            ],
            "edges": [],
            "facts": [
                {
                    **fact("fact:test", "world:test", "color", "Blue"),
                    "review_status": "UNREVIEWED_EXTRACTED",
                }
            ],
        }
        imported = validate_ingestion_pack(raw)
        self.assertEqual(
            imported.facts[0].review_status,
            ReviewStatus.UNREVIEWED_EXTRACTED,
        )
        self.assertEqual(build_reviewed_registry(imported).fact_count, 0)
        reviewed = review_item(
            imported,
            item_type="entity",
            item_id="world:test",
            reviewer_id="owner",
            review_note="Verified against authorized source.",
        )
        reviewed = review_item(
            reviewed,
            item_type="fact",
            item_id="fact:test",
            reviewer_id="owner",
            review_note="Verified against authorized source.",
        )
        self.assertEqual(build_reviewed_registry(reviewed).fact_count, 1)

        raw["facts"][0]["review_status"] = "VERIFIED_CANON"
        with self.assertRaises(ValueError):
            validate_ingestion_pack(raw)

    def test_ingestion_rejects_provenance_free_and_procedural_as_official(self):
        raw = {
            "schema_version": 1,
            "sources": [source()],
            "entities": [
                {
                    **entity("world:test", "Test World"),
                    "review_status": "UNREVIEWED_EXTRACTED",
                }
            ],
            "edges": [],
            "facts": [
                {
                    **fact("fact:test", "world:test", "custom", "Invented"),
                    "source_id": "source:missing",
                    "review_status": "UNREVIEWED_EXTRACTED",
                }
            ],
        }
        with self.assertRaises(ValueError):
            validate_ingestion_pack(raw)

        procedural = fact("fact:procedural", "world:test", "custom", "Invented")
        procedural["reality_layer"] = "PROCEDURAL_LOCAL_FICTION"
        raw["facts"] = [{**procedural, "review_status": "UNREVIEWED_EXTRACTED"}]
        with self.assertRaises(ValueError):
            validate_ingestion_pack(raw)

    def test_campaign_override_requires_matching_engine_evidence(self):
        state = CampaignLoreState.legacy_unbound()
        override = CampaignCanonOverride(
            "override:event-1",
            "city:test",
            "status",
            "changed",
            "action:1",
            4,
        )
        with self.assertRaises(ValueError):
            apply_campaign_override(
                state,
                override,
                evidence=EngineActionEvidence("action:1", 4, "python_engine"),
            )

    def test_npc_knowledge_is_scoped_by_stable_npc_id(self):
        registry = verified_registry(
            facts=[fact("fact:secret", "world:test", "password", "Not a real secret")]
        )
        state = CampaignLoreState.from_mapping(
            {
                "binding_status": "BOUND",
                "setting_profile": "TEST_SETTING",
                "world_id": "world:test",
                "epoch_id": "epoch:test",
                "region_id": "region:test",
                "current_location_entity_id": "location:test",
                "player_known_fact_ids": [],
                "npc_known_fact_ids": {},
                "campaign_overrides": [],
                "procedural_entity_refs": [],
                "lore_discoveries": [],
            }
        )
        evidence = EngineActionEvidence("action:knowledge", 3, "python_engine")
        state = grant_npc_knowledge(
            state,
            "npc:001",
            ["fact:secret"],
            registry=registry,
            evidence=evidence,
            source_action_id="action:knowledge",
            turn_index=3,
        )

        self.assertEqual(dict(state.npc_known_fact_ids)["npc:001"], ("fact:secret",))
        self.assertNotIn("npc:002", dict(state.npc_known_fact_ids))

    def test_lore_context_is_partitioned_bounded_and_does_not_invent_unknowns(self):
        registry = default_lore_registry()
        packet = registry.retrieve_lore_context(
            current_location_id="location:dynamic-1",
            mentioned_entity_ids={"unknown:place"},
            max_bytes=2_048,
        )

        self.assertIn("official_forgotten_realms_lore", packet["sections"])
        self.assertIn("campaign_canon", packet["sections"])
        self.assertEqual(
            packet["diagnostics"]["coverage_status"],
            "SOURCE_INGESTION_REQUIRED_FOR_FULL_COVERAGE",
        )
        self.assertEqual(
            {row["entity_id"] for row in packet["sections"]["unknown_or_unloaded"]},
            {"location:dynamic-1", "unknown:place"},
        )
        self.assertLessEqual(
            len(json.dumps(packet, ensure_ascii=False).encode("utf-8")),
            2_048,
        )


    def test_lore_retrieval_is_query_relevant_and_reports_selected_fact_ids(self):
        city_facts = [
            fact(
                f"fact:city:{index}",
                "city:neverwinter",
                predicate,
                value,
                visibility="REGIONAL_KNOWLEDGE",
                region_scope="region:north",
            )
            for index, (predicate, value) in enumerate([
                ("current_status", "Rebuilding"),
                ("known_as", "City of Skilled Hands"),
                ("known_for", "master crafts and fine goods"),
                ("nearby_landmark", "Mount Hotenow"),
                ("river", "River Neverwinter"),
                ("current_lord", "Dagult Neverember"),
                ("history", "a chasm opened to the Underdark"),
                ("trade", "northern trade"),
            ])
        ]
        road_safety = fact(
            "fact:high-road:safety",
            "road:high",
            "safety_status",
            "restored",
            visibility="REGIONAL_KNOWLEDGE",
            region_scope="region:north",
        )
        road_safety["notes"] = "High Road safety was restored near Neverwinter."
        current_year = fact(
            "fact:world:current-year",
            "world:test",
            "current_dr_year",
            1501,
            visibility="REGIONAL_KNOWLEDGE",
            region_scope="region:north",
        )
        registry = verified_registry(
            entities=[
                entity("world:test", "Forgotten Realms"),
                entity("region:north", "The North"),
                entity("region:sword-coast", "Sword Coast"),
                entity("city:neverwinter", "Neverwinter"),
                entity("road:high", "High Road"),
                entity("road:trade", "Trade Way"),
                entity("faction:alliance", "Lords' Alliance"),
            ],
            facts=city_facts + [road_safety, current_year] + [
                fact(
                    "fact:north:sword-coast",
                    "region:north",
                    "distinct_from_region",
                    "region:sword-coast",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
                fact(
                    "fact:high-road",
                    "road:high",
                    "route_role",
                    "major trade route",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
                fact(
                    "fact:high-road:continues",
                    "road:high",
                    "continues_as",
                    "road:trade",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
                fact(
                    "fact:alliance",
                    "faction:alliance",
                    "purpose",
                    "safety and prosperity",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
                fact(
                    "fact:city:alliance",
                    "city:neverwinter",
                    "member_of",
                    "faction:alliance",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
            ],
        )
        state = CampaignLoreState.from_mapping({
            "binding_status": "BOUND",
            "setting_profile": "TEST_SETTING",
            "world_id": "world:test",
            "epoch_id": "epoch:test",
            "region_id": "region:north",
            "current_location_entity_id": "city:neverwinter",
            "starting_location_entity_id": "city:neverwinter",
            "region_pack_id": "test:pack",
            "player_known_fact_ids": [],
            "npc_known_fact_ids": {},
            "campaign_overrides": [],
            "procedural_entity_refs": [],
            "lore_discoveries": [],
        })

        focused = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="How is Neverwinter rebuilding?",
            mentioned_entity_ids={"city:neverwinter"},
            campaign_state=state,
        )
        focused_ids = focused["diagnostics"]["selected_fact_ids"]
        self.assertEqual(focused_ids, ["fact:city:0"])
        self.assertEqual(focused["diagnostics"]["selected_fact_count"], 1)

        lord_query = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="Does Dagult Neverember rule Neverwinter?",
            mentioned_entity_ids={"city:neverwinter"},
            campaign_state=state,
        )
        self.assertEqual(
            lord_query["diagnostics"]["selected_fact_ids"],
            ["fact:city:5"],
        )

        route_query = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="How does the High Road continue as the Trade Way?",
            mentioned_entity_ids={"road:high"},
            campaign_state=state,
        )
        self.assertIn(
            "fact:high-road:continues",
            route_query["diagnostics"]["selected_fact_ids"],
        )
        for wording in (
            "What road does the High Road connect to?",
            "Does the High Road become the Trade Way?",
        ):
            with self.subTest(wording=wording):
                variant = registry.retrieve_lore_context(
                    current_location_id="city:neverwinter",
                    player_message=wording,
                    mentioned_entity_ids={"road:high"},
                    campaign_state=state,
                )
                self.assertIn(
                    "fact:high-road:continues",
                    variant["diagnostics"]["selected_fact_ids"],
                )

        alliance_query = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message=(
                "Is Neverwinter a member of the Lords' Alliance, and what is "
                "the Alliance's stated purpose?"
            ),
            mentioned_entity_ids={"city:neverwinter", "faction:alliance"},
            campaign_state=state,
        )
        alliance_fact_ids = set(alliance_query["diagnostics"]["selected_fact_ids"])
        self.assertIn("fact:city:alliance", alliance_fact_ids)
        self.assertIn("fact:alliance", alliance_fact_ids)
        self.assertIn(
            "membership",
            alliance_query["diagnostics"]["query_intents"],
        )
        self.assertIn("purpose", alliance_query["diagnostics"]["query_intents"])

        region_relation_query = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="Is The North the same region as the Sword Coast?",
            mentioned_entity_ids={"region:north", "region:sword-coast"},
            campaign_state=state,
        )
        self.assertIn(
            "fact:north:sword-coast",
            region_relation_query["diagnostics"]["selected_fact_ids"],
        )
        self.assertIn(
            "distinct_relation",
            region_relation_query["diagnostics"]["query_intents"],
        )

        status_variant = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="What was Neverwinter's condition in 1501 DR?",
            mentioned_entity_ids={"city:neverwinter"},
            campaign_state=state,
        )
        self.assertIn(
            "fact:city:0",
            status_variant["diagnostics"]["selected_fact_ids"],
        )
        self.assertIn(
            "fact:world:current-year",
            status_variant["diagnostics"]["selected_fact_ids"],
        )
        self.assertIn(
            "current_status",
            status_variant["diagnostics"]["query_intents"],
        )

        region_overview = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="What is The North?",
            mentioned_entity_ids={"region:north"},
            campaign_state=state,
        )
        self.assertEqual(
            region_overview["diagnostics"]["selected_fact_ids"],
            ["fact:north:sword-coast"],
        )
        self.assertEqual(
            region_overview["diagnostics"]["query_intents"],
            ["overview"],
        )

        broad = registry.retrieve_lore_context(
            current_location_id="city:neverwinter",
            player_message="What is known about Neverwinter?",
            mentioned_entity_ids={"city:neverwinter"},
            campaign_state=state,
        )
        broad_ids = broad["diagnostics"]["selected_fact_ids"]
        self.assertLessEqual(len(broad_ids), 4)
        self.assertTrue(all(fact_id.startswith("fact:city:") for fact_id in broad_ids))
        self.assertIn("fact:city:1", broad_ids)
        self.assertIn("fact:city:0", broad_ids)
        self.assertNotIn("fact:city:6", broad_ids)
        self.assertEqual(
            set(broad_ids),
            {
                item["fact_id"]
                for item in broad["sections"]["official_forgotten_realms_lore"]
            },
        )
        self.assertIn(
            "Neverwinter",
            {
                item["canonical_name"]
                for item in broad["sections"]["verified_entities"]
            },
        )

    def test_turkish_current_city_ruler_queries_use_bound_location_only(self):
        for wording in (
            "Bu şehrin hükümdarı kim?",
            "Bu şehirde hükümdar kim?",
        ):
            with self.subTest(wording=wording):
                packet = PRODUCTION_REGISTRY.retrieve_lore_context(
                    current_location_id="fr:city:neverwinter",
                    player_message=wording,
                    mentioned_entity_ids=set(),
                    campaign_state=CampaignLoreState.legacy_unbound(),
                )
                self.assertEqual(
                    packet["diagnostics"]["selected_fact_ids"],
                    ["fr:fact:dagult_neverember_current_lord"],
                )
                self.assertIn(
                    "current_ruler",
                    packet["diagnostics"]["query_intents"],
                )
                self.assertEqual(
                    packet["diagnostics"]["current_location_entity_id"],
                    "fr:city:neverwinter",
                )

        two_city_registry = verified_registry(
            entities=[
                entity("world:test", "Forgotten Realms"),
                entity("region:north", "The North"),
                entity("city:neverwinter", "Neverwinter"),
                entity("city:waterdeep", "Waterdeep"),
                entity("person:dagult", "Dagult Neverember"),
                entity("person:laeral", "Laeral Silverhand"),
            ],
            facts=[
                fact(
                    "fact:neverwinter:current-lord",
                    "city:neverwinter",
                    "current_lord_id",
                    "person:dagult",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
                fact(
                    "fact:waterdeep:current-lord",
                    "city:waterdeep",
                    "current_lord_id",
                    "person:laeral",
                    visibility="REGIONAL_KNOWLEDGE",
                    region_scope="region:north",
                ),
            ],
        )
        waterdeep_state = CampaignLoreState.from_mapping({
            "binding_status": "BOUND",
            "setting_profile": "TEST_SETTING",
            "world_id": "world:test",
            "epoch_id": "epoch:test",
            "region_id": "region:north",
            "current_location_entity_id": "city:waterdeep",
            "starting_location_entity_id": "city:waterdeep",
            "region_pack_id": "test:pack",
            "player_known_fact_ids": [],
            "npc_known_fact_ids": {},
            "campaign_overrides": [],
            "procedural_entity_refs": [],
            "lore_discoveries": [],
        })
        waterdeep_packet = two_city_registry.retrieve_lore_context(
            current_location_id="city:waterdeep",
            player_message="Bu şehrin hükümdarı kim?",
            mentioned_entity_ids=set(),
            campaign_state=waterdeep_state,
        )
        self.assertEqual(
            waterdeep_packet["diagnostics"]["selected_fact_ids"],
            ["fact:waterdeep:current-lord"],
        )
        self.assertNotIn(
            "fact:neverwinter:current-lord",
            waterdeep_packet["diagnostics"]["selected_fact_ids"],
        )

    def test_year_name_spelling_is_mythal_and_unreviewed_facts_stay_out(self):
        year_name = PRODUCTION_REGISTRY.fact("fr:fact:present_year_name")
        self.assertIsNotNone(year_name)
        self.assertEqual(year_name.object_id_or_value, "Year of the Shining Mythal")
        self.assertNotIn("Mythral", str(year_name.object_id_or_value))
        self.assertIn("Mythal", year_name.notes)
        self.assertIn("Mythral", year_name.notes)
        epoch = PRODUCTION_REGISTRY.entity("fr:epoch:1501_dr")
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.canonical_name, "1501 DR")

        from api.lore_authority.pack_loader import REVIEW_FILE, _read_json, load_production_pack

        original = _read_json

        def missing_decision(path):
            payload = original(path)
            if path == REVIEW_FILE:
                payload = {
                    **payload,
                    "items": [
                        item
                        for item in payload["items"]
                        if item.get("item_id") != "fr:fact:present_year_name"
                    ],
                }
            return payload

        with mock.patch(
            "api.lore_authority.pack_loader._read_json",
            side_effect=missing_decision,
        ):
            with self.assertRaises(ValueError):
                load_production_pack()

    def test_campaign_year_keeps_only_current_facts(self):
        current = PRODUCTION_REGISTRY.retrieve_lore_context(
            current_location_id="fr:city:neverwinter",
            player_message="Bu şehrin hükümdarı kim?",
            mentioned_entity_ids=set(),
            campaign_state=CampaignLoreState.legacy_unbound(),
            campaign_year=1501,
        )
        self.assertEqual(
            current["diagnostics"]["selected_fact_ids"],
            ["fr:fact:dagult_neverember_current_lord"],
        )

        other_year = PRODUCTION_REGISTRY.retrieve_lore_context(
            current_location_id="fr:city:neverwinter",
            player_message="Bu şehrin hükümdarı kim?",
            mentioned_entity_ids=set(),
            campaign_state=CampaignLoreState.legacy_unbound(),
            campaign_year=1491,
        )
        self.assertNotIn(
            "fr:fact:dagult_neverember_current_lord",
            other_year["diagnostics"]["selected_fact_ids"],
        )
        self.assertEqual(other_year["sections"]["official_forgotten_realms_lore"], [])
        self.assertIn(
            "fr:city:neverwinter",
            {row["entity_id"] for row in other_year["sections"]["unknown_or_unloaded"]},
        )

        historical = verified_registry(
            entities=[entity("city:old", "Old City", entity_type="CITY")],
            facts=[
                fact(
                    "fact:old-lord",
                    "city:old",
                    "current_lord_id",
                    "person:past",
                    temporal_scope="HISTORICAL_DATE_UNSPECIFIED",
                )
            ],
        )
        historical_packet = historical.retrieve_lore_context(
            current_location_id="city:old",
            player_message="Bu şehrin hükümdarı kim?",
            campaign_year=1501,
        )
        self.assertEqual(historical_packet["diagnostics"]["selected_fact_ids"], [])
        self.assertIn(
            "city:old",
            {
                row["entity_id"]
                for row in historical_packet["sections"]["unknown_or_unloaded"]
            },
        )

        ranged = verified_registry(
            entities=[entity("city:later", "Later City", entity_type="CITY")],
            facts=[
                fact(
                    "fact:later-lord",
                    "city:later",
                    "current_lord_id",
                    "person:future",
                    temporal_scope="STATIC_SETTING_FACT",
                    valid_from="1600 DR",
                    valid_until="1610 DR",
                )
            ],
        )
        ranged_packet = ranged.retrieve_lore_context(
            current_location_id="city:later",
            player_message="Bu şehrin hükümdarı kim?",
            campaign_year=1501,
        )
        self.assertEqual(ranged_packet["diagnostics"]["selected_fact_ids"], [])

    def test_same_tier_current_facts_stay_unresolved(self):
        registry = verified_registry(
            facts=[
                fact(
                    "fact:a",
                    "world:test",
                    "capital",
                    "City A",
                    temporal_scope="CURRENT_AT_1501_DR",
                ),
                fact(
                    "fact:b",
                    "world:test",
                    "capital",
                    "City B",
                    temporal_scope="CURRENT_AT_1501_DR",
                ),
            ]
        )
        packet = registry.retrieve_lore_context(
            current_location_id="world:test",
            campaign_year=1501,
        )
        self.assertEqual(packet["diagnostics"]["selected_fact_ids"], [])
        self.assertEqual(
            packet["diagnostics"]["unresolved_conflicts"],
            [{
                "subject_id": "world:test",
                "predicate": "capital",
                "fact_ids": ["fact:a", "fact:b"],
            }],
        )

    def test_engine_events_write_canon_once_and_prose_does_not(self):
        registry = verified_registry(
            entities=[entity("city:test", "Test City", entity_type="CITY")],
            facts=[fact("fact:lord", "city:test", "current_lord_id", "person:ada")],
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
        evidence = EngineActionEvidence("turn:2", 2, "python_engine")
        before = {
            "npcs": [{"id": "npc_001", "status": "alive"}],
            "blocked_travel_routes": {},
        }
        after = {
            "npcs": [{"id": "npc_001", "status": "dead"}],
            "blocked_travel_routes": {"location_001": {"location_002": True}},
        }
        prose = apply_committed_world_canon(
            state,
            evidence=evidence,
            before_world=before,
            after_world=before,
            action_result={"narration": "The lord died and the road closed."},
            registry=registry,
        )
        self.assertEqual(prose.campaign_overrides, ())
        self.assertEqual(prose.player_known_fact_ids, ())
        self.assertEqual(state.campaign_overrides, ())

        committed = apply_committed_world_canon(
            state,
            evidence=evidence,
            before_world=before,
            after_world=after,
            action_result={"discovered_fact_ids": ["fact:lord"]},
            registry=registry,
        )
        self.assertEqual(
            [item.predicate for item in committed.campaign_overrides],
            ["life_status", "route_status"],
        )
        self.assertEqual(committed.player_known_fact_ids, ("fact:lord",))
        replay = apply_committed_world_canon(
            committed,
            evidence=evidence,
            before_world=before,
            after_world=after,
            action_result={"discovered_fact_ids": ["fact:lord"]},
            registry=registry,
        )
        self.assertEqual(replay.to_dict(), committed.to_dict())


if __name__ == "__main__":
    unittest.main()