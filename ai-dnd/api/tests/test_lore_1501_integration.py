"""Offline chain for the staged 1501 candidate. Cities stay disabled."""

from __future__ import annotations

import ast
import hashlib
import json
import time
import unittest
from pathlib import Path

from api.lore_authority.campaign_state import (
    CampaignLoreState,
    EngineActionEvidence,
    record_player_discovery,
)
from api.lore_authority.freeze_admission import admit_public_batch
from api.lore_authority.freeze_mapping import (
    LONG_CLAIM_IDS,
    VERTICAL_SLICE_IDS,
    attach_cities,
    build_mapping_spec,
)
from api.lore_authority.freeze_review import review_staged_pack
from api.lore_authority.freeze_transform import transform_admitted_batch
from api.lore_authority.live_gate import live_verification_status
from api.lore_authority.models import (
    MAX_FACT_VALUE_LENGTH,
    MAX_REFERENCE_LENGTH,
    LORE_PAYLOAD_VERSION,
    OwnerContinuityRecord,
    Relationship,
    SourceTier,
)
from api.lore_authority.pack_loader import load_pack_index
from api.lore_authority.player_knowledge import read_player_knowledge
from api.lore_authority.registry import LoreRegistry
from api.persistence.campaign_store import _DATABASE_SCHEMA_VERSION
from api.persistence.campaign_validation import CAMPAIGN_FORMAT_VERSION
from incidents.profiles import DISABLED


AI_DND = Path(__file__).resolve().parents[2]
PACKS = AI_DND / "api" / "lore_authority" / "packs"
NEVERWINTER_HASHES = {
    "pack_index.json": "3ba99717976aa25f154fdd97cc4ce6e5e7d5bf59bd175bc037cd7c537ebcacd5",
    "neverwinter_the_north_v1.extraction.json": "51b1ce206d8be080de855aff79348a05578a99ca5c5b69c7fee912063d5c64c5",
    "neverwinter_the_north_v1.review.json": "0438e805ba26c345af6b7b0078770e45a33f71fb0b5e9cab404cfe7571de703e",
    "installed_region_catalog.json": "2c20d3841a6fe3eb7566fb97b3cc07cc9aa5e65585e481c531a820c7d94d1936",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Lore1501IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = admit_public_batch()
        from api.lore_authority.freeze_transform import _cities_from_snapshot

        cls.spec = attach_cities(build_mapping_spec(cls.batch), _cities_from_snapshot(cls.batch))

    def test_snapshot_keeps_neverwinter_hashes_and_save_versions(self):
        for name, expected in NEVERWINTER_HASHES.items():
            self.assertEqual(_sha(PACKS / name), expected)
        self.assertEqual(LORE_PAYLOAD_VERSION, 2)
        self.assertEqual(CAMPAIGN_FORMAT_VERSION, 1)
        self.assertEqual(_DATABASE_SCHEMA_VERSION, 5)
        import game

        self.assertEqual(game.SAVE_FORMAT_VERSION, 3)
        indexed = {row["pack_id"]: row["coverage_status"] for row in load_pack_index()}
        self.assertEqual(indexed["fr:pack:the_north:neverwinter:v1"], "VERIFIED_PARTIAL")
        self.assertEqual(indexed["fr:pack:waterdeep:v1"], "INCOMPLETE")
        self.assertEqual(indexed["fr:pack:baldurs_gate:v1"], "INCOMPLETE")
        self.assertEqual(DISABLED, {"waterdeep.v1", "baldurs_gate.v1"})

    def test_mapping_dispositions_do_not_invent_entities(self):
        rows = {row["extraction_id"]: row for row in self.spec["records"]}
        self.assertEqual(len(rows), 95)
        self.assertTrue(all(row["disposition"] != "runtime_entity" for row in rows.values()))
        self.assertTrue(all(row["entity_type"] is None for row in rows.values()))
        self.assertGreater(sum(row["disposition"] == "mention_only" for row in rows.values()), 0)
        self.assertTrue(all(not row["lossy"] for row in rows.values()))
        stored = json.loads((AI_DND / "docs" / "evidence" / "phase8-expansion" / "lore-integration-staging" / "mapping_spec_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["mapping_digest"], self.spec["mapping_digest"])
        self.assertEqual(len(stored["records"]), 95)
        for record_id in LONG_CLAIM_IDS:
            claim = rows[record_id]["permitted_claim"]
            self.assertGreater(len(claim), MAX_REFERENCE_LENGTH)
            self.assertLessEqual(len(claim), MAX_FACT_VALUE_LENGTH)

    def test_vertical_slice_then_full_transform_is_deterministic(self):
        first = transform_admitted_batch(self.batch, self.spec, only_ids=VERTICAL_SLICE_IDS)
        again = transform_admitted_batch(self.batch, self.spec, only_ids=VERTICAL_SLICE_IDS)
        full = transform_admitted_batch(self.batch, self.spec)
        self.assertEqual(
            [item.payload_digest for item in first.facts],
            [item.payload_digest for item in again.facts],
        )
        withheld = {item.extraction_id: item.reason for item in first.withheld}
        self.assertEqual(withheld["WD22-E-001"], "name_mention_is_not_a_runtime_entity")
        self.assertEqual(withheld["WD22-X-002"], "endpoint_is_not_a_runtime_entity")
        claims = {item.extraction_id: item.fact.object_id_or_value for item in full.facts}
        self.assertNotIn("Castle Ward", claims["WD22-F-015"])
        self.assertGreater(len(claims["BG22-F-005"]), MAX_REFERENCE_LENGTH)
        self.assertEqual(len(full.facts) + len(full.withheld), 95)
        self.assertFalse(full.production_authorized)

    def test_review_is_bound_to_the_payload_digest(self):
        staged = transform_admitted_batch(self.batch, self.spec, only_ids=("WD22-F-001",))
        staged_fact = staged.facts[0]
        decision = {
            staged_fact.extraction_id: {
                "item_payload_digest": staged_fact.payload_digest,
                "evidence_bundle_digest": staged.evidence_bundle_digest,
                "mapping_spec_digest": staged.mapping_digest,
                "reviewer_id": "test-reviewer",
                "review_note": "test-owned review is not production approval",
                "decision": "accept",
            }
        }
        reviewed = review_staged_pack(staged, decision)
        self.assertFalse(reviewed.production_authorized)
        decision[staged_fact.extraction_id]["item_payload_digest"] = "0" * 64
        with self.assertRaises(ValueError):
            review_staged_pack(staged, decision)

    def test_staged_fact_cannot_become_player_knowledge_or_turkish_surface(self):
        staged = transform_admitted_batch(self.batch, self.spec, only_ids=("WD22-F-001",))
        fact = staged.facts[0].fact
        with self.assertRaises(ValueError):
            record_player_discovery(
                CampaignLoreState.from_mapping({
                    "binding_status": "BOUND",
                    "setting_profile": "TEST_SETTING",
                    "world_id": "world:faerun",
                    "epoch_id": "epoch:1501",
                    "region_id": "region:waterdeep",
                    "current_location_entity_id": "city:waterdeep",
                    "player_known_fact_ids": [],
                    "npc_known_fact_ids": {},
                    "campaign_overrides": [],
                    "procedural_entity_refs": [],
                    "lore_discoveries": [],
                }),
                fact.fact_id,
                registry=LoreRegistry(),
                evidence=EngineActionEvidence(action_id="a", turn_index=1, authority="python_engine"),
                source_action_id="a",
                turn_index=1,
            )
        forced = CampaignLoreState.from_mapping({
            "binding_status": "BOUND",
            "setting_profile": "TEST_SETTING",
            "world_id": "world:faerun",
            "epoch_id": "epoch:1501",
            "region_id": "region:waterdeep",
            "current_location_entity_id": "city:waterdeep",
            "player_known_fact_ids": [fact.fact_id],
            "npc_known_fact_ids": {},
            "campaign_overrides": [],
            "procedural_entity_refs": [],
            "lore_discoveries": [],
        })
        projection = read_player_knowledge(forced, {}, LoreRegistry())
        self.assertEqual(projection["known_facts"], [])
        self.assertEqual(projection["presentation_gaps"][0]["reason"], "turkish_rendering_missing")
        self.assertNotIn(fact.object_id_or_value, str(projection["known_facts"]))

    def test_owner_tier_is_rejected_by_pack_parsing_and_rank(self):
        with self.assertRaises(ValueError):
            SourceTier.OWNER_APPROVED_CONTINUITY.rank
        from api.lore_authority.models import SourceManifest

        with self.assertRaises(ValueError):
            SourceManifest.from_mapping({
                "source_id": "source:owner",
                "title": "Owner",
                "publisher": "Owner",
                "publication_year": 2026,
                "edition_family": "owner",
                "source_tier": "OWNER_APPROVED_CONTINUITY",
                "setting": "forgotten_realms",
                "region_scope": None,
                "authority_status": "VERIFIED",
                "owner_access_status": "AUTHORIZED",
                "notes": "",
            })
        record = OwnerContinuityRecord(
            decision_id="owner:waterdeep:castle_ward:1501:v1",
            provenance_kind="OWNER_APPROVED_CONTINUITY",
            approved_statement="Castle Ward continues to exist as a ward of Waterdeep in 1501 DR, the Year of the Shining Mythal.",
            subject="waterdeep",
            predicate="exists_as_ward",
            year=1501,
            scope="ward existence only",
            decision_document_digest="be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a",
        )
        self.assertFalse(record.runtime_enabled)
        self.assertFalse(record.official_source_fact)

    def test_new_predicates_do_not_enter_geography(self):
        from api.tests.test_lore_1501_freeze_contract import _entity, _source

        from api.lore_authority.models import LoreEdge

        edge = LoreEdge.from_mapping({
            "edge_id": "edge:holds",
            "subject_id": "city:waterdeep",
            "predicate": Relationship.HOLDS_OFFICE.value,
            "object_id": "city:baldurs_gate",
            "source_id": "source:freeze-fixture",
            "source_reference": "fixture",
            "authority_tier": "TEST_FIXTURE",
            "review_status": "TEST_ONLY",
            "valid_from": None,
            "valid_until": None,
        })
        registry = LoreRegistry(
            sources=[_source()],
            entities=[
                _entity("city:waterdeep", "Waterdeep", "CITY"),
                _entity("city:baldurs_gate", "Baldur's Gate", "CITY"),
            ],
            edges=[edge],
            allow_test_fixtures=True,
        )
        self.assertEqual(
            registry.geography_ancestors({"city:waterdeep"}),
            frozenset({"city:waterdeep"}),
        )

    def test_neverwinter_ruler_query_is_unchanged(self):
        from api.lore_authority import PRODUCTION_REGISTRY

        started = time.perf_counter()
        packet = None
        for _ in range(20):
            packet = PRODUCTION_REGISTRY.retrieve_lore_context(
                current_location_id="fr:city:neverwinter",
                player_message="Bu şehrin hükümdarı kim?",
                mentioned_entity_ids=set(),
                campaign_state=CampaignLoreState.legacy_unbound(),
            )
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)
        self.assertEqual(
            packet["diagnostics"]["selected_fact_ids"],
            ["fr:fact:dagult_neverember_current_lord"],
        )
        encoded = str(packet).encode("utf-8")
        self.assertLess(len(encoded), 12 * 1024)

    def test_authorization_modules_do_not_import_the_production_loader(self):
        root = Path(__file__).resolve().parents[1] / "lore_authority"
        for name in ("freeze_transform.py", "claim_authorization.py", "freeze_eligibility.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
            self.assertFalse(any("pack_loader" in item for item in imported))

    def test_live_gate_stays_closed(self):
        self.assertEqual(live_verification_status(), "NOT_RUN")

    def test_campaign_state_is_unchanged_by_staging(self):
        before = {
            "player_known_fact_ids": [],
            "lore_payload_version": LORE_PAYLOAD_VERSION,
        }
        transform_admitted_batch(self.batch, self.spec, only_ids=("FR22-F-001",))
        after = {
            "player_known_fact_ids": [],
            "lore_payload_version": LORE_PAYLOAD_VERSION,
        }
        self.assertEqual(before, after)
