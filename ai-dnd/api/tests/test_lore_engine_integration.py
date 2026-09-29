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


if __name__ == "__main__":
    unittest.main()