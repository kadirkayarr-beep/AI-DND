"""Isolated contract tests for the unapproved 1501 DR freeze candidate.

The candidate is not a production pack. Scene packets below are test
fixtures passed through LoreRegistry.retrieve_lore_context. Gap tests
call the same production functions and fail where the runtime does not
enforce the contract yet.
"""

from __future__ import annotations

import unittest

from api.lore_authority import (
    CampaignLoreState,
    EngineActionEvidence,
    LoreEdge,
    LoreEntity,
    LoreFact,
    LoreRegistry,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    Relationship,
    SourceManifest,
    SourceTier,
    fact_is_current,
    get_player_known_lore,
    read_player_knowledge,
    record_player_discovery,
    registry_for_pack,
)
from api.lore_authority.pack_loader import load_pack_index
from api.tests.lore_1501_freeze_view import (
    EXCLUDED_CASTLE_WARD_INFERENCE,
    OWNER_EXISTENCE_SENTENCE,
    PERMITTED_WARD_NAMES,
    FreezeView,
    load_freeze_view,
)
from incidents.profiles import DISABLED, resolve as resolve_profile


SCENE_MESSAGE = "What is known about this city?"
SOURCE_ID = "source:freeze-fixture"
CITY_SUBJECT = {
    "waterdeep": "city:waterdeep",
    "baldurs_gate": "city:baldurs_gate",
    "shared": "world:faerun",
}
CITY_REGION = {
    "waterdeep": "region:waterdeep",
    "baldurs_gate": "region:baldurs_gate",
    "shared": "region:shared",
}


def _source() -> SourceManifest:
    return SourceManifest.from_mapping({
        "source_id": SOURCE_ID,
        "title": "Isolated 1501 freeze contract fixture",
        "publisher": "Test fixture",
        "publication_year": 2026,
        "edition_family": "test",
        "source_tier": "TEST_FIXTURE",
        "setting": "test-setting",
        "region_scope": None,
        "authority_status": "VERIFIED",
        "owner_access_status": "AUTHORIZED",
        "notes": "Not a production pack and not owner approval of the 95.",
    })


def _entity(entity_id: str, name: str, entity_type: str) -> LoreEntity:
    return LoreEntity.from_mapping({
        "entity_id": entity_id,
        "entity_type": entity_type,
        "canonical_name": name,
        "aliases": [],
        "setting": "test-setting",
        "region_scope": None,
        "source_id": SOURCE_ID,
        "source_reference": "fixture",
        "authority_tier": "TEST_FIXTURE",
        "review_status": "TEST_ONLY",
        "valid_from": None,
        "valid_until": None,
        "notes": "",
    })


def _fact(
    fact_id: str,
    subject_id: str,
    value: str,
    *,
    visibility: str = "COMMON_KNOWLEDGE",
    temporal_scope: str | None = "CURRENT_AT_1501_DR",
    region_scope: str | None = None,
) -> LoreFact:
    predicate = fact_id.lower().replace("-", "_")
    return LoreFact.from_mapping({
        "fact_id": fact_id,
        "subject_id": subject_id,
        "predicate": predicate,
        "object_id_or_value": value,
        "claim_type": "OBJECTIVE_CANON_FACT",
        "authority_tier": "TEST_FIXTURE",
        "source_id": SOURCE_ID,
        "source_reference": "fixture",
        "valid_from": None,
        "valid_until": None,
        "temporal_scope": temporal_scope,
        "visibility": visibility,
        "region_scope": region_scope,
        "notes": "",
        "reality_layer": "OFFICIAL_SETTING_CANON",
        "review_status": "TEST_ONLY",
    })


def _registry(*facts: LoreFact) -> LoreRegistry:
    return LoreRegistry(
        sources=[_source()],
        entities=[
            _entity("world:faerun", "Faerun", "WORLD"),
            _entity("city:waterdeep", "Waterdeep", "CITY"),
            _entity("city:baldurs_gate", "Baldur's Gate", "CITY"),
        ],
        facts=list(facts),
        allow_test_fixtures=True,
    )


def _bound(location_id: str, region_id: str) -> CampaignLoreState:
    return CampaignLoreState.from_mapping({
        "binding_status": "BOUND",
        "setting_profile": "TEST_SETTING",
        "world_id": "world:faerun",
        "epoch_id": "epoch:1501",
        "region_id": region_id,
        "current_location_entity_id": location_id,
        "player_known_fact_ids": [],
        "npc_known_fact_ids": {},
        "campaign_overrides": [],
        "procedural_entity_refs": [],
        "lore_discoveries": [],
    })


def _scene_registry(view: FreezeView) -> LoreRegistry:
    """Public candidate facts plus the five restricted facts as DM secrets.

    Review status stays TEST_ONLY. This does not approve the candidate.
    """
    facts = []
    for record_id in view.public_ids:
        row = view.record(record_id)
        if row["kind"] != "fact":
            continue
        manifest = next(item for item in view.inclusion["records"] if item["id"] == record_id)
        value = manifest["included_scope"] if manifest["inclusion_status"] == "included_partial" else row["claim"]
        facts.append(_fact(
            record_id,
            CITY_SUBJECT[row["city"]],
            value,
            region_scope=CITY_REGION[row["city"]],
        ))
    for record_id in view.restricted_ids:
        row = view.record(record_id)
        facts.append(_fact(
            record_id,
            CITY_SUBJECT[row["city"]],
            "restricted candidate",
            visibility="DM_SECRET",
        ))
    return _registry(*facts)


def _selected(registry: LoreRegistry, *, location_id: str, region_id: str, year: int = 1501) -> set[str]:
    packet = registry.retrieve_lore_context(
        current_location_id=location_id,
        player_message=SCENE_MESSAGE,
        campaign_state=_bound(location_id, region_id),
        include_dm_secrets=False,
        campaign_year=year,
    )
    return set(packet["diagnostics"]["selected_fact_ids"])


class Lore1501FreezeContractTests(unittest.TestCase):
    view: FreezeView

    @classmethod
    def setUpClass(cls):
        cls.view = load_freeze_view()

    def test_01_public_ids_match_the_freeze_manifest(self):
        view = self.view
        self.assertEqual(view.patch_errors, ())
        self.assertEqual(view.patch_count, 47)
        self.assertEqual(view.patched_record_count, 38)
        self.assertEqual(view.inclusion["status"], "FREEZE_CANDIDATE_NOT_APPROVED")
        self.assertTrue(view.inclusion["do_not_load_as_pack"])
        self.assertEqual(view.inclusion["included_total"], 95)
        self.assertEqual(view.inclusion["included_full"], 94)
        self.assertEqual(view.inclusion["included_partial"], 1)
        self.assertEqual(len(view.public_ids), 95)
        self.assertEqual(len(set(view.public_ids)), 95)
        full_ids = {
            row["id"]
            for row in view.inclusion["records"]
            if row["inclusion_status"] == "included_full"
        }
        partial_ids = {
            row["id"]
            for row in view.inclusion["records"]
            if row["inclusion_status"] == "included_partial"
        }
        ledger_public = {
            record_id
            for record_id, row in view.ledger.items()
            if row["verdict"] == "verified_public"
        }
        self.assertEqual(full_ids, ledger_public)
        self.assertEqual(partial_ids, {"WD22-F-015"})
        self.assertEqual(
            view.ledger["WD22-F-015"]["verdict"],
            "verified_clause_excluded",
        )
        self.assertFalse(view.ledger["WD22-F-015"]["in_public_baseline"])
        self.assertTrue(set(view.public_ids).isdisjoint(view.restricted_ids))
        self.assertTrue(set(view.public_ids).isdisjoint(view.supplemental_ids))
        for record_id in view.public_ids:
            row = view.record(record_id)
            manifest = next(
                item for item in view.inclusion["records"] if item["id"] == record_id
            )
            self.assertEqual(row["knowledge"], "public")
            self.assertEqual(manifest["knowledge"], "public")
            self.assertEqual(manifest["player_knowledge"], "not_granted")
            self.assertEqual(manifest["public_narration_grant"], "not_granted")
            self.assertEqual(row["applicability_1501"], "current_1501_candidate")
            self.assertIsNone(PRODUCTION_REGISTRY.fact(record_id))

    def test_02_restricted_ids_stay_out_of_an_ordinary_packet(self):
        view = self.view
        self.assertEqual(view.restricted_manifest["count"], 5)
        self.assertEqual(
            set(view.restricted_ids),
            {
                "WD22-F-067",
                "WD22-F-068",
                "BG22-F-007",
                "BG22-F-013-3",
                "BG22-F-024",
            },
        )
        ledger_restricted = {
            record_id
            for record_id, row in view.ledger.items()
            if row["verdict"] == "verified_restricted"
        }
        self.assertEqual(set(view.restricted_ids), ledger_restricted)
        for record_id in view.restricted_ids:
            self.assertEqual(view.record(record_id)["knowledge"], "restricted")
            self.assertIsNone(PRODUCTION_REGISTRY.fact(record_id))
        selected = _selected(
            _scene_registry(view),
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        selected.update(_selected(
            _scene_registry(view),
            location_id="city:baldurs_gate",
            region_id="region:baldurs_gate",
        ))
        self.assertTrue(selected.isdisjoint(view.restricted_ids))

    def test_02_gap_common_visibility_still_admits_a_restricted_id(self):
        registry = _registry(_fact(
            "WD22-F-067",
            "city:waterdeep",
            "restricted candidate",
            visibility="COMMON_KNOWLEDGE",
        ))
        selected = _selected(
            registry,
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        self.assertNotIn(
            "WD22-F-067",
            selected,
            "retrieve_lore_context admits a restricted record once it is "
            "stored as COMMON_KNOWLEDGE. Future change: a loader must keep "
            "the five restricted IDs at DM_SECRET or DISCOVERABLE_SECRET "
            "and must not classify them as public setting facts.",
        )

    def test_03_supplemental_ids_are_outside_the_public_manifest(self):
        view = self.view
        self.assertEqual(len(view.supplemental_ids), 68)
        self.assertTrue(set(view.supplemental_ids).isdisjoint(view.public_ids))
        self.assertTrue(set(view.supplemental_ids).isdisjoint(view.ledger))
        for record_id in view.supplemental_ids:
            self.assertIsNone(PRODUCTION_REGISTRY.fact(record_id))

    def test_03_gap_unscoped_supplemental_fact_is_excluded_at_1501(self):
        record_id = self.view.supplemental_ids[0]
        registry = _registry(_fact(
            record_id,
            "city:waterdeep",
            "supplemental",
            temporal_scope=None,
        ))
        selected = _selected(
            registry,
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        self.assertNotIn(
            record_id,
            selected,
            "fact_is_current treats a missing temporal scope as current, so "
            "an unscoped supplemental record enters a 1501 packet. Future "
            "change: supplemental_unconfirmed_1501 must not use an empty "
            "scope; retrieval must reject that applicability.",
        )

    def test_04_f015_permitted_scope_is_only_the_printed_ward_list(self):
        view = self.view
        manifest = next(
            row for row in view.inclusion["records"] if row["id"] == "WD22-F-015"
        )
        claim = view.record("WD22-F-015")["claim"]
        scope = manifest["included_scope"]
        self.assertEqual(manifest["inclusion_status"], "included_partial")
        self.assertIn(EXCLUDED_CASTLE_WARD_INFERENCE, claim)
        for name in PERMITTED_WARD_NAMES:
            self.assertIn(name, scope)
        self.assertNotIn("Castle Ward", scope)
        self.assertNotIn("abolish", scope.casefold())
        self.assertIn("Castle Ward", manifest["excluded_scope"])
        self.assertNotIn(OWNER_EXISTENCE_SENTENCE, claim)
        self.assertNotIn(OWNER_EXISTENCE_SENTENCE, scope)

    def test_05_manifest_still_excludes_the_castle_ward_inference(self):
        manifest = next(
            row for row in self.view.inclusion["records"] if row["id"] == "WD22-F-015"
        )
        self.assertNotIn(EXCLUDED_CASTLE_WARD_INFERENCE, manifest["included_scope"])
        self.assertNotIn("Castle Ward", manifest["included_scope"])

    def test_05_gap_retrieval_rejects_reintroduced_castle_ward_inference(self):
        registry = _registry(_fact(
            "WD22-F-015",
            "city:waterdeep",
            EXCLUDED_CASTLE_WARD_INFERENCE,
        ))
        selected = _selected(
            registry,
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        self.assertNotIn(
            "WD22-F-015",
            selected,
            "retrieve_lore_context accepted the excluded Castle Ward "
            "inference as WD22-F-015. Future change: reject that sentence "
            "inside WD22-F-015 before it can enter a lore packet. Do not "
            "rewrite the 2025 record into the owner existence decision.",
        )

    def test_06_owner_decision_text_is_separate_from_the_2025_record(self):
        text = self.view.owner_decision_text
        claim = self.view.record("WD22-F-015")["claim"]
        self.assertIn("OWNER-APPROVED CONTINUITY DECISION", text)
        self.assertIn("not a direct 2025 source verification", text)
        self.assertIn(OWNER_EXISTENCE_SENTENCE, text)
        self.assertIn("WD22-F-015", text)
        self.assertNotIn(OWNER_EXISTENCE_SENTENCE, claim)
        self.assertNotIn("OWNER-APPROVED CONTINUITY DECISION", claim)

    def test_06_gap_source_tier_can_distinguish_owner_continuity(self):
        names = {item.name for item in SourceTier}
        self.assertIn(
            "OWNER_APPROVED_CONTINUITY",
            names,
            "SourceTier has no owner-continuity provenance. Future change: "
            "add a tier that cannot be stored as TIER_1_CURRENT_CORE and "
            "cannot replace the printed WD22-F-015 ward list. The Castle "
            "Ward existence sentence belongs on that tier alone.",
        )

    def test_07_waterdeep_scene_returns_only_relevant_public_facts(self):
        view = self.view
        allowed = view.ids_for(city="waterdeep", kind="fact")
        self.assertIn("WD22-F-015", allowed)
        selected = _selected(
            _scene_registry(view),
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        other_year = _selected(
            _scene_registry(view),
            location_id="city:waterdeep",
            region_id="region:waterdeep",
            year=1492,
        )
        self.assertTrue(selected)
        self.assertLessEqual(len(selected), 4)
        self.assertTrue(selected <= allowed)
        self.assertTrue(selected.isdisjoint(view.ids_for(city="baldurs_gate", kind="fact")))
        self.assertTrue(selected.isdisjoint(view.restricted_ids))
        self.assertTrue(selected.isdisjoint(view.supplemental_ids))
        self.assertNotIn("FR22-F-001", selected)
        self.assertEqual(other_year, set())

    def test_08_baldurs_gate_scene_returns_only_relevant_public_facts(self):
        view = self.view
        allowed = view.ids_for(city="baldurs_gate", kind="fact")
        selected = _selected(
            _scene_registry(view),
            location_id="city:baldurs_gate",
            region_id="region:baldurs_gate",
        )
        self.assertTrue(selected)
        self.assertLessEqual(len(selected), 4)
        self.assertTrue(selected <= allowed)
        self.assertTrue(selected.isdisjoint(view.ids_for(city="waterdeep", kind="fact")))
        self.assertTrue(selected.isdisjoint(view.restricted_ids))
        self.assertTrue(selected.isdisjoint(view.supplemental_ids))
        self.assertNotIn("FR22-F-001", selected)

    def test_09_public_classification_does_not_grant_character_knowledge(self):
        view = self.view
        registry = _scene_registry(view)
        state = _bound("city:waterdeep", "region:waterdeep")
        packet = registry.retrieve_lore_context(
            current_location_id="city:waterdeep",
            player_message=SCENE_MESSAGE,
            campaign_state=state,
            include_dm_secrets=False,
            campaign_year=1501,
        )
        self.assertTrue(packet["sections"]["official_forgotten_realms_lore"])
        self.assertEqual(packet["sections"]["player_known_lore"], [])
        self.assertEqual(get_player_known_lore(registry, state.player_known_fact_ids), ())
        self.assertEqual(
            read_player_knowledge(state, {}, registry)["known_facts"],
            [],
        )
        for row in view.inclusion["records"]:
            self.assertEqual(row["player_knowledge"], "not_granted")

    def test_10_explicit_historical_scope_is_not_current(self):
        historical = _fact(
            self.view.historical_ids[0],
            "city:waterdeep",
            "historical",
            temporal_scope="HISTORICAL_DATE_UNSPECIFIED",
        )
        self.assertFalse(fact_is_current(historical, 1501))
        selected = _selected(
            _registry(historical),
            location_id="city:waterdeep",
            region_id="region:waterdeep",
        )
        self.assertEqual(selected, set())

    def test_10_gap_unscoped_historical_claim_is_not_promoted(self):
        record_id = self.view.historical_ids[0]
        historical = _fact(
            record_id,
            "city:waterdeep",
            "historical",
            temporal_scope=None,
        )
        self.assertFalse(
            fact_is_current(historical, 1501),
            "fact_is_current promotes an unscoped historical record to the "
            "current year. Future change: historical_setting records need "
            "HISTORICAL_DATE_UNSPECIFIED, and an empty scope must not count "
            "as a verified 1501 candidate.",
        )

    def test_11_support_and_endpoints_match_the_patched_records(self):
        view = self.view
        public = set(view.public_ids)
        for manifest in view.inclusion["records"]:
            row = view.record(manifest["id"])
            self.assertEqual(manifest["dependencies"]["supported_by"], row["supported_by"])
            for support_id in row["supported_by"]:
                self.assertIn(support_id, view.records)
                self.assertEqual(view.record(support_id)["knowledge"], "public")
                self.assertIn(support_id, public)
            if row["kind"] == "edge":
                endpoints = manifest["dependencies"]["endpoints"]
                self.assertEqual(
                    endpoints,
                    [
                        {"role": "source", "id": row["source_entity_id"]},
                        {"role": "target", "id": row["target_entity_id"]},
                    ],
                )
                self.assertIn(row["source_entity_id"], public)
                self.assertIn(row["target_entity_id"], public)
            else:
                self.assertEqual(manifest["dependencies"]["endpoints"], [])

    def test_11_gap_relationship_enum_stores_candidate_edge_predicates(self):
        predicates = {
            self.view.record(record_id)["relationship_type"]
            for record_id in self.view.public_ids
            if self.view.record(record_id)["kind"] == "edge"
        }
        accepted = {item.value for item in Relationship}
        missing = sorted(predicates - accepted)
        self.assertEqual(
            missing,
            [],
            "LoreEdge cannot store the freeze edge predicates. "
            f"Missing: {missing}",
        )
        for predicate in sorted(predicates):
            edge = LoreEdge.from_mapping({
                "edge_id": "edge:freeze:" + predicate,
                "subject_id": "city:waterdeep",
                "predicate": predicate,
                "object_id": "city:baldurs_gate",
                "source_id": SOURCE_ID,
                "source_reference": "fixture",
                "authority_tier": "TEST_FIXTURE",
                "review_status": "TEST_ONLY",
                "valid_from": None,
                "valid_until": None,
            })
            self.assertEqual(edge.to_dict()["predicate"], predicate)
            self.assertEqual(edge.subject_id, "city:waterdeep")
            self.assertEqual(edge.object_id, "city:baldurs_gate")

    def test_11_gap_unknown_predicate_is_rejected(self):
        with self.assertRaises(ValueError):
            LoreEdge.from_mapping({
                "edge_id": "WD22-X-002",
                "subject_id": "city:waterdeep",
                "predicate": "not_a_real_relationship",
                "object_id": "city:baldurs_gate",
                "source_id": SOURCE_ID,
                "source_reference": "fixture",
                "authority_tier": "TEST_FIXTURE",
                "review_status": "TEST_ONLY",
                "valid_from": None,
                "valid_until": None,
            })

    def test_12_unknown_and_withheld_claims_are_not_authorized(self):
        import game

        view = self.view
        registry = _scene_registry(view)
        packet = registry.retrieve_lore_context(
            current_location_id="city:waterdeep",
            player_message=SCENE_MESSAGE,
            campaign_state=_bound("city:waterdeep", "region:waterdeep"),
            include_dm_secrets=False,
            campaign_year=1501,
        )
        selected = packet["diagnostics"]["selected_fact_ids"]
        self.assertTrue(selected)
        self.assertTrue(game._lore_claims_are_supported(selected[:1], packet))
        self.assertFalse(game._lore_claims_are_supported(["WD22-NO-SUCH"], packet))
        for record_id in view.restricted_ids:
            self.assertNotIn(record_id, selected)
            self.assertFalse(game._lore_claims_are_supported([record_id], packet))

    def test_12_gap_restricted_claim_is_rejected_even_when_packed_as_common(self):
        import game

        registry = _registry(_fact(
            "WD22-F-067",
            "city:waterdeep",
            "restricted candidate",
            visibility="COMMON_KNOWLEDGE",
        ))
        packet = registry.retrieve_lore_context(
            current_location_id="city:waterdeep",
            player_message=SCENE_MESSAGE,
            campaign_state=_bound("city:waterdeep", "region:waterdeep"),
            include_dm_secrets=False,
            campaign_year=1501,
        )
        self.assertFalse(
            game._lore_claims_are_supported(["WD22-F-067"], packet),
            "_lore_claims_are_supported accepts any fact ID already in the "
            "packet. Future change: reject the five restricted IDs even if "
            "a packet contains them, and keep unknown IDs rejected.",
        )

    def test_13_production_registry_and_start_catalog_stay_neverwinter_only(self):
        pack_ids = [pack.region_pack_id for pack in PRODUCTION_START_CATALOG.packs]
        self.assertEqual(pack_ids, ["fr:pack:the_north:neverwinter:v1"])
        pack = PRODUCTION_START_CATALOG.packs[0]
        self.assertEqual(pack.epoch_id, "fr:epoch:1501_dr")
        self.assertEqual(
            [item.entity_id for item in pack.starting_locations],
            ["fr:city:neverwinter"],
        )
        indexed = {row["pack_id"]: row["coverage_status"] for row in load_pack_index()}
        self.assertEqual(indexed["fr:pack:the_north:neverwinter:v1"], "VERIFIED_PARTIAL")
        self.assertEqual(indexed["fr:pack:waterdeep:v1"], "INCOMPLETE")
        self.assertEqual(indexed["fr:pack:baldurs_gate:v1"], "INCOMPLETE")
        self.assertEqual(registry_for_pack("fr:pack:waterdeep:v1").fact_count, 0)
        self.assertEqual(registry_for_pack("fr:pack:baldurs_gate:v1").fact_count, 0)
        self.assertGreater(PRODUCTION_REGISTRY.fact_count, 0)
        self.assertIn("waterdeep.v1", DISABLED)
        self.assertIn("baldurs_gate.v1", DISABLED)
        self.assertIsNone(resolve_profile({}, "fr:city:waterdeep"))
        self.assertIsNone(resolve_profile({}, "baldurs_gate"))
        for record_id in (*self.view.public_ids, *self.view.restricted_ids):
            self.assertIsNone(PRODUCTION_REGISTRY.fact(record_id))

    def test_14_fixtures_and_knowledge_grants_stay_campaign_local(self):
        left = _registry(
            _fact("WD22-F-001", "city:waterdeep", "public candidate"),
            _fact("factlocalnote", "city:waterdeep", "a local note"),
        )
        right = _registry(_fact("BG22-F-001", "city:baldurs_gate", "public candidate"))
        self.assertIsNone(left.fact("BG22-F-001"))
        self.assertIsNone(right.fact("WD22-F-001"))
        waterdeep = _bound("city:waterdeep", "region:waterdeep")
        baldurs = _bound("city:baldurs_gate", "region:baldurs_gate")
        with self.assertRaises(ValueError):
            record_player_discovery(
                waterdeep,
                "WD22-F-001",
                registry=left,
                evidence=EngineActionEvidence("action-a", 0, "python_engine"),
                source_action_id="action-a",
                turn_index=0,
            )
        self.assertEqual(waterdeep.player_known_fact_ids, ())
        granted = record_player_discovery(
            waterdeep,
            "factlocalnote",
            registry=left,
            evidence=EngineActionEvidence("action-b", 1, "python_engine"),
            source_action_id="action-b",
            turn_index=1,
        )
        self.assertIn("factlocalnote", granted.player_known_fact_ids)
        self.assertNotIn("WD22-F-001", granted.player_known_fact_ids)
        self.assertEqual(baldurs.player_known_fact_ids, ())
        self.assertEqual(
            tuple(fact.fact_id for fact in get_player_known_lore(
                right,
                granted.player_known_fact_ids,
            )),
            (),
        )
        self.assertEqual(
            tuple(fact.fact_id for fact in get_player_known_lore(
                left,
                granted.player_known_fact_ids,
            )),
            ("factlocalnote",),
        )


if __name__ == "__main__":
    unittest.main()
