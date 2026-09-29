from __future__ import annotations

import json
import unittest

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
    Relationship,
    ResolutionStatus,
    ReviewStatus,
    SourceManifest,
    SourceTier,
    VisibilityScope,
    apply_campaign_override,
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
        "valid_from": None,
        "valid_until": None,
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


if __name__ == "__main__":
    unittest.main()