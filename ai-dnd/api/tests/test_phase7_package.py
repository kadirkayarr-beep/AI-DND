"""Phase 7 knowledge, faction, horizon, and pack-index checks."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import game
import scheduled_events
from api.lore_authority import (
    PRODUCTION_REGISTRY,
    CampaignLoreState,
    ClaimType,
    EngineActionEvidence,
    apply_committed_world_canon,
    apply_faction_standing,
    read_player_knowledge,
    registry_for_pack,
)
from api.lore_authority.models import LoreFact
from api.tests.test_lore_authority import entity, fact, verified_registry


def bound_state() -> CampaignLoreState:
    return CampaignLoreState.from_mapping({
        "binding_status": "BOUND",
        "setting_profile": "TEST_SETTING",
        "world_id": "world:test",
        "epoch_id": "epoch:test",
        "region_id": "region:test",
        "current_location_entity_id": "city:test",
        "player_known_fact_ids": ["fact:lord"],
        "npc_known_fact_ids": {},
        "campaign_overrides": [],
        "procedural_entity_refs": [],
        "lore_discoveries": ["fact:lord"],
    })


class Phase7PackageTests(unittest.TestCase):
    def test_old_lore_payload_migrates_once_and_corrupt_rows_fail(self):
        original = {
            "binding_status": "LEGACY_UNBOUND",
            "setting_profile": None,
            "world_id": None,
            "epoch_id": None,
            "region_id": None,
            "current_location_entity_id": None,
            "player_known_fact_ids": [],
            "npc_known_fact_ids": {},
            "campaign_overrides": [],
            "procedural_entity_refs": [],
            "lore_discoveries": [],
        }
        loaded = CampaignLoreState.from_mapping(original)
        self.assertEqual(loaded.faction_standings, ())
        self.assertEqual(loaded.lore_payload_version, 1)
        migrated = loaded.to_dict()
        again = CampaignLoreState.from_mapping(migrated).to_dict()
        self.assertEqual(again, migrated)
        broken = {**migrated, "faction_standings": [{"faction_id": "fr:faction:lords_alliance"}]}
        with self.assertRaises(ValueError):
            CampaignLoreState.from_mapping(broken)

    def test_facade_hides_unknown_names_and_hidden_factions(self):
        registry = verified_registry(
            entities=[
                entity("city:test", "Test City", entity_type="CITY"),
                entity("person:ada", "Ada", entity_type="CANONICAL_NPC"),
                entity("fr:faction:lords_alliance", "Lords' Alliance", entity_type="FACTION"),
            ],
            facts=[fact("fact:lord", "city:test", "current_lord_id", "person:ada")],
        )
        world = {
            "npcs": [{
                "id": "npc_001",
                "name": "Gizli Ad",
                "role": "tüccar",
                "name_known_to_player": False,
                "role_known_to_player": True,
                "location": "location_001",
            }],
            "player_knowledge": ["a sealed letter"],
        }
        state = bound_state()
        evidence = EngineActionEvidence("turn:3", 3, "python_engine")
        hidden = apply_faction_standing(
            state,
            faction_id="fr:faction:lords_alliance",
            standing=1,
            known_to_player=False,
            local_presence=True,
            evidence=evidence,
            source_action_id="turn:3",
            turn_index=3,
        )
        with self.assertRaises(ValueError):
            apply_faction_standing(
                state,
                faction_id="fr:faction:lords_alliance",
                standing=2,
                known_to_player=True,
                local_presence=True,
                evidence=None,
                source_action_id="turn:3",
                turn_index=3,
            )
        projection = read_player_knowledge(hidden, world, registry)
        self.assertEqual(projection["people"][0]["id"], "npc_001")
        self.assertNotIn("Gizli Ad", projection["people"][0]["label"])
        self.assertEqual(projection["adventure_evidence"], ["a sealed letter"])
        self.assertEqual(projection["known_factions"], [])
        self.assertEqual(projection["known_facts"][0]["fact_id"], "fact:lord")
        known = apply_faction_standing(
            hidden,
            faction_id="fr:faction:lords_alliance",
            standing=1,
            known_to_player=True,
            local_presence=True,
            evidence=EngineActionEvidence("turn:4", 4, "python_engine"),
            source_action_id="turn:4",
            turn_index=4,
        )
        revealed = read_player_knowledge(known, world, registry)
        self.assertEqual(revealed["known_factions"][0]["title"], "Lords' Alliance")
        world["npcs"][0]["name_known_to_player"] = True
        learned = read_player_knowledge(known, world, registry)
        self.assertEqual(learned["people"][0]["label"], "Gizli Ad")

    def test_adventure_possibility_does_not_become_campaign_death(self):
        registry = verified_registry(
            entities=[entity("npc:module", "Module NPC", entity_type="CANONICAL_NPC")],
            facts=[fact(
                "fact:module-death",
                "npc:module",
                "life_status",
                "dead",
                claim_type="ADVENTURE_POSSIBILITY",
            )],
        )
        stored = registry.fact("fact:module-death")
        self.assertIsInstance(stored, LoreFact)
        self.assertIs(stored.claim_type, ClaimType.ADVENTURE_POSSIBILITY)
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
        world = {"npcs": [{"id": "npc:module", "status": "alive"}]}
        committed = apply_committed_world_canon(
            state,
            evidence=EngineActionEvidence("turn:1", 1, "python_engine"),
            before_world=world,
            after_world=world,
            action_result={"narration": "The module says this person died."},
            registry=registry,
        )
        self.assertEqual(committed.campaign_overrides, ())
        self.assertEqual(world["npcs"][0]["status"], "alive")

    def test_incomplete_pack_answers_unknown(self):
        registry = registry_for_pack("fr:pack:incomplete:v1")
        self.assertEqual(registry.fact_count, 0)
        packet = registry.retrieve_lore_context(
            current_location_id="fr:city:waterdeep",
            player_message="Bu şehrin hükümdarı kim?",
        )
        self.assertEqual(packet["sections"]["official_forgotten_realms_lore"], [])
        self.assertTrue(packet["sections"]["unknown_or_unloaded"])
        self.assertGreater(PRODUCTION_REGISTRY.fact_count, 0)

    def test_remote_event_does_not_run_and_hidden_event_stays_unlisted(self):
        world = {
            "location": "location_001",
            "locations": {"location_001": {"name": "Here"}, "location_009": {"name": "Away"}},
            "npcs": [],
            "flags": {},
            "scheduled_events": [],
        }
        scheduled_events.register_event(
            world,
            event_id="event:away",
            window_start=0,
            window_end=30,
            location_id="location_009",
            effects=[{"kind": "flag", "key": "scheduled:away", "value": True}],
            summary="Far away.",
            aftermath="Still far.",
            visibility="hidden",
        )
        scheduled_events.process_events(world, 0, 40)
        self.assertEqual(world["scheduled_events"][0]["status"], "PENDING")
        self.assertNotIn("scheduled:away", world["flags"])
        self.assertEqual(scheduled_events.public_events(world), [])

        scheduled_events.register_event(
            world,
            event_id="event:here",
            window_start=0,
            window_end=30,
            location_id="location_001",
            effects=[{"kind": "flag", "key": "scheduled:here", "value": True}],
            summary="A local change.",
            aftermath="The change remains.",
            visibility="hidden",
        )
        scheduled_events.process_events(world, 0, 40)
        here = next(event for event in world["scheduled_events"] if event["event_id"] == "event:here")
        self.assertEqual(here["status"], "OCCURRED")
        self.assertFalse(here["player_observed"])
        self.assertEqual(scheduled_events.public_events(world), [])
        self.assertTrue(world["flags"]["scheduled:here"])

    def test_hidden_aftermath_appears_only_after_observation(self):
        world = {
            "location": "location_001",
            "locations": {"location_001": {"name": "Here"}},
            "npcs": [],
            "flags": {},
            "scheduled_events": [],
        }
        scheduled_events.register_event(
            world,
            event_id="event:mark",
            window_start=0,
            window_end=30,
            location_id="location_001",
            effects=[{"kind": "flag", "key": "scheduled:mark", "value": True}],
            summary="Gizli hareket.",
            aftermath="Mavi tebeşir izi kaldı.",
            visibility="hidden",
            aftermath_visible=True,
        )
        scheduled_events.process_events(world, 0, 40)
        self.assertTrue(world["flags"]["scheduled:mark"])
        self.assertEqual(scheduled_events.public_events(world), [])
        learned = scheduled_events.process_events(
            world, 40, 40, observation={"kind": "look", "location_id": "location_001"},
        )
        self.assertEqual(learned[0]["summary"], "Mavi tebeşir izi kaldı.")
        self.assertEqual(
            scheduled_events.public_events(world)[0]["summary"],
            "Mavi tebeşir izi kaldı.",
        )
        again = scheduled_events.process_events(
            world, 40, 40, observation={"kind": "look", "location_id": "location_001"},
        )
        self.assertEqual(again, [])
        self.assertEqual(world["flags"]["scheduled:mark"], True)

    def test_prompt_omits_unknown_names_and_private_npc_fields(self):
        session = game.create_session(seed=21)
        session.commit_location_change("tavern")
        npc = session.create_npc_from_ai({
            "name": "Gizli Ad",
            "role": "Gezgin",
            "location": "tavern",
            "appearance": "Sade bir pelerin.",
            "knowledge": ["Gizli bir sır"],
            "backstory": "Gerçek geçmiş",
        })
        self.assertIsNotNone(npc)
        self.assertFalse(npc["name_known_to_player"])
        context = game.build_world_context(session=session)
        blob = json.dumps(context, ensure_ascii=False)
        self.assertNotIn("Gizli Ad", blob)
        self.assertNotIn("Gizli bir sır", blob)
        self.assertNotIn("Gerçek geçmiş", blob)
        for record in context["npcs"]:
            self.assertNotIn("knowledge", record)
            self.assertNotIn("backstory", record)
        self.assertNotIn("CANONICAL_LOCATION", Path(
            Path(__file__).resolve().parents[1] / "main.py"
        ).read_text(encoding="utf-8"))

    def test_npc_status_location_and_known_name_survive_reload(self):
        session = game.create_session(seed=22)
        session.commit_location_change("tavern")
        npc = session.create_npc_from_ai({
            "name": "Ada",
            "role": "Tüccar",
            "location": "tavern",
        })
        npc["status"] = "unconscious"
        npc["name_known_to_player"] = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            session.save_game(path)
            restored = game.create_session(seed=99)
            restored.load_game(path)
        loaded = next(item for item in restored.world_state["npcs"] if item["id"] == npc["id"])
        self.assertEqual(loaded["id"], npc["id"])
        self.assertEqual(loaded["location"], "tavern")
        self.assertEqual(loaded["status"], "unconscious")
        self.assertTrue(loaded["name_known_to_player"])
        self.assertEqual(loaded["name"], "Ada")

    def test_npc_memory_stays_bounded(self):
        npc = {"id": "npc_001", "name": "Ada", "memory": []}
        for index in range(20):
            game.record_npc_interaction(npc, f"Yanıt {index} tamam", f"Merhaba {index} dostum", npc)
        self.assertLessEqual(len(npc["memory"]), 16)
        self.assertGreater(len(npc["memory"]), 0)


if __name__ == "__main__":
    unittest.main()
