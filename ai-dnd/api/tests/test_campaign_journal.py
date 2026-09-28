"""Canonical journal derivation and validation tests."""

from __future__ import annotations

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from api.campaign_journal import (
    create_initial_campaign_journal,
    empty_campaign_journal,
    update_campaign_journal,
    validate_campaign_journal,
)
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError
from api.persistence.campaign_validation import ensure_no_configured_secrets


def world(
    location: str = "tavern",
    *,
    turn: int = 0,
    npcs: list[dict] | None = None,
    inventory: list[str] | None = None,
    combat_active: bool = False,
    player_status: str = "active",
) -> dict:
    return {
        "location": location,
        "locations": {
            "tavern": {"id": "tavern", "name": "Taverna", "type": "building"},
            "forest": {"id": "forest", "name": "Orman", "type": "wilderness"},
            "castle": {"id": "castle", "name": "Kale", "type": "building"},
        },
        "npcs": deepcopy(npcs or []),
        "inventory": list(inventory or []),
        "flags": {"turn_index": turn},
        "combat": {"active": combat_active},
        "player_combat_status": player_status,
        "events": [],
    }


def save(world_state: dict, current_hp: int = 10) -> dict:
    return {"world_state": deepcopy(world_state), "player": {"current_hp": current_hp}}


class CampaignJournalTests(unittest.TestCase):
    def test_new_journal_has_all_sections_and_empty_quest_ledger(self):
        journal = empty_campaign_journal()
        validate_campaign_journal(journal)
        self.assertEqual(journal["schema_version"], 1)
        self.assertEqual(journal["discovered_locations"], [])
        self.assertEqual(journal["known_npcs"], [])
        self.assertEqual(journal["notable_events"], [])
        self.assertEqual(journal["quests"], [])

    def test_unresolved_starting_location_is_not_discovered(self):
        journal = create_initial_campaign_journal(
            world("Henüz belirlenmedi"),
            {"environment": "unknown"},
        )
        self.assertEqual(journal["discovered_locations"], [])
        self.assertEqual(journal["notable_events"], [])

    def test_canonical_starting_location_is_recorded(self):
        journal = create_initial_campaign_journal(
            world("tavern"),
            {"environment": "tavern"},
        )
        self.assertEqual(
            [(item["location_id"], item["name"], item["environment"])
             for item in journal["discovered_locations"]],
            [("tavern", "Taverna", "tavern")],
        )
        self.assertEqual(journal["discovered_locations"][0]["visit_count"], 1)
        self.assertEqual(
            [event["event_type"] for event in journal["notable_events"]],
            ["location_discovered"],
        )

    def test_canonical_travel_records_only_the_engine_location(self):
        journal = empty_campaign_journal()
        result = update_campaign_journal(
            journal,
            save(world("tavern", turn=1)),
            save(world("forest", turn=2)),
            {"action": "travel", "status": "completed", "success": True},
            {"environment": "forest"},
        )
        self.assertEqual(
            [entry["location_id"] for entry in result["discovered_locations"]],
            ["forest"],
        )
        self.assertEqual(result["notable_events"][0]["summary"], "Orman keşfedildi.")

    def test_failed_travel_does_not_discover_target(self):
        result = update_campaign_journal(
            empty_campaign_journal(),
            save(world("tavern", turn=2)),
            save(world("tavern", turn=3)),
            {"action": "travel", "status": "failed", "success": False, "target": "forest"},
            {"environment": "tavern"},
        )
        self.assertEqual(result["discovered_locations"], [])
        self.assertEqual(result["notable_events"], [])

    def test_unregistered_changed_location_is_not_discovered(self):
        result = update_campaign_journal(
            empty_campaign_journal(),
            save(world("tavern", turn=1)),
            save(world("player-typed-city", turn=2)),
            {"action": "travel", "status": "completed", "success": True},
            {"environment": "unknown"},
        )
        self.assertEqual(result["discovered_locations"], [])

    def test_revisit_updates_visit_metadata_without_duplicate_discovery(self):
        journal = create_initial_campaign_journal(
            world("tavern"),
            {"environment": "tavern"},
        )
        result = update_campaign_journal(
            journal,
            save(world("forest", turn=4)),
            save(world("tavern", turn=5)),
            {"action": "travel", "status": "completed", "success": True},
            {"environment": "tavern"},
        )
        self.assertEqual(len(result["discovered_locations"]), 1)
        self.assertEqual(result["discovered_locations"][0]["visit_count"], 2)
        self.assertEqual(result["discovered_locations"][0]["last_visited_turn"], 5)
        self.assertEqual(
            [event["event_type"] for event in result["notable_events"]],
            ["location_discovered"],
        )

    def test_npc_meeting_uses_canonical_id_and_memory_without_copying_memory(self):
        npc = {
            "id": "npc_001",
            "name": "Kasım",
            "role": "Barmen",
            "location": "tavern",
            "memory": [{"speaker": "player", "text": "private memory text"}],
        }
        before = save(world("tavern", turn=1))
        after = save(world("tavern", turn=2, npcs=[npc]))
        result = update_campaign_journal(
            empty_campaign_journal(),
            before,
            after,
            {"action": "dialogue", "npc_id": "npc_001"},
            {"environment": "tavern"},
        )
        self.assertEqual(len(result["known_npcs"]), 1)
        self.assertEqual(result["known_npcs"][0]["npc_id"], "npc_001")
        self.assertEqual(result["known_npcs"][0]["name"], "Kasım")
        self.assertNotIn("private memory text", str(result))
        self.assertEqual(result["notable_events"][0]["event_type"], "npc_met")

    def test_same_npc_id_is_not_duplicated_and_name_is_not_used_as_identity(self):
        first = {"id": "npc_001", "name": "Kasım", "role": "Barmen", "location": "tavern", "memory": []}
        second = {"id": "npc_002", "name": "Kasım", "role": "Barmen", "location": "tavern", "memory": []}
        journal = empty_campaign_journal()
        first_result = update_campaign_journal(
            journal,
            save(world("tavern", turn=1)),
            save(world("tavern", turn=2, npcs=[first, second])),
            {"action": "dialogue", "npc_id": "npc_001"},
            {"environment": "tavern"},
        )
        second_result = update_campaign_journal(
            first_result,
            save(world("tavern", turn=2, npcs=[first, second])),
            save(world("tavern", turn=3, npcs=[first, second])),
            {"action": "dialogue", "npc_id": "npc_001"},
            {"environment": "tavern"},
        )
        self.assertEqual(len(second_result["known_npcs"]), 1)
        self.assertEqual(second_result["known_npcs"][0]["npc_id"], "npc_001")
        self.assertEqual(
            [event["event_type"] for event in second_result["notable_events"]],
            ["npc_met"],
        )
        other_npc = update_campaign_journal(
            second_result,
            save(world("tavern", turn=3, npcs=[first, second])),
            save(world("tavern", turn=4, npcs=[first, second])),
            {"action": "dialogue", "npc_id": "npc_002"},
            {"environment": "tavern"},
        )
        self.assertEqual(
            {entry["npc_id"] for entry in other_npc["known_npcs"]},
            {"npc_001", "npc_002"},
        )

    def test_presence_query_records_only_active_npcs_at_the_current_location(self):
        npcs = [
            {"id": "npc_001", "name": "Kasım", "role": "Barmen", "location": "tavern", "combat_status": "active"},
            {"id": "npc_002", "name": "Lina", "role": "Gezgin", "location": "forest", "combat_status": "active"},
            {"id": "npc_003", "name": "Gromm", "role": "Muhafız", "location": "tavern", "combat_status": "defeated"},
        ]
        result = update_campaign_journal(
            empty_campaign_journal(),
            save(world("tavern", turn=1, npcs=npcs)),
            save(world("tavern", turn=2, npcs=npcs)),
            {"action": "query", "query_type": "presence"},
            {"environment": "tavern"},
            presence_location_id="tavern",
        )
        self.assertEqual(
            [entry["npc_id"] for entry in result["known_npcs"]],
            ["npc_001"],
        )

    def test_journal_records_structured_events_not_engine_prose(self):
        before_world = world("tavern", turn=4, inventory=["Kılıç"])
        after_world = world(
            "forest",
            turn=5,
            inventory=["Kılıç", "Fener"],
            combat_active=True,
        )
        before_world["events"] = [{"location": "tavern", "description": "untrusted narration"}]
        after_world["events"] = [{"location": "forest", "description": "quest completed"}]
        result = update_campaign_journal(
            empty_campaign_journal(),
            save(before_world),
            save(after_world),
            {"action": "travel", "status": "completed"},
            {"environment": "forest"},
        )
        self.assertEqual(
            [event["event_type"] for event in result["notable_events"]],
            ["location_discovered", "combat_started", "item_gained"],
        )
        self.assertNotIn("untrusted narration", str(result))
        self.assertNotIn("quest completed", str(result))

    def test_combat_end_enemy_defeat_and_unconsciousness_are_canonical_events(self):
        npc_before = {"id": "npc_001", "name": "Gromm", "role": "Rakip", "location": "tavern", "combat_status": "active", "current_hp": 4, "memory": []}
        npc_after = {**npc_before, "combat_status": "unconscious", "current_hp": 0}
        journal = create_initial_campaign_journal(
            world("tavern"),
            {"environment": "tavern"},
        )
        journal["known_npcs"] = [{
            "npc_id": "npc_001",
            "name": "Gromm",
            "role": "Rakip",
            "first_met_at": "2026-09-28T10:00:00+00:00",
            "last_seen_at": "2026-09-28T10:00:00+00:00",
            "first_met_turn": 1,
            "last_seen_turn": 1,
            "last_known_location_id": None,
            "last_known_location": None,
        }]
        before_world = world("tavern", turn=1, npcs=[npc_before], combat_active=True)
        after_world = world("tavern", turn=2, npcs=[npc_after], combat_active=False, player_status="unconscious")
        result = update_campaign_journal(
            journal,
            save(before_world, current_hp=5),
            save(after_world, current_hp=0),
            {"action": "attack", "target_id": "npc_001"},
            {"environment": "tavern"},
        )
        self.assertEqual(
            [event["event_type"] for event in result["notable_events"]],
            [
                "location_discovered",
                "combat_ended",
                "enemy_defeated",
                "player_unconscious",
            ],
        )

    def test_configured_secrets_and_npc_memory_are_not_copied_to_journal(self):
        secret = "journal-secret-test-value"
        npc = {
            "id": "npc_001",
            "name": "Kasım",
            "role": "Barmen",
            "location": "tavern",
            "memory": [{"speaker": "player", "text": secret}],
        }
        result = update_campaign_journal(
            empty_campaign_journal(),
            save(world("tavern", turn=1)),
            save(world("tavern", turn=2, npcs=[npc])),
            {"action": "dialogue", "npc_id": "npc_001"},
            {"environment": "tavern"},
        )
        with patch.dict(os.environ, {"SESSION_SECRET": secret}):
            ensure_no_configured_secrets(result)
        self.assertNotIn(secret, str(result))

    def test_invalid_quest_or_event_data_is_rejected_safely(self):
        journal = empty_campaign_journal()
        journal["quests"].append({"title": "forged"})
        with self.assertRaises(CampaignValidationError):
            validate_campaign_journal(journal, CampaignValidationError)
        with self.assertRaises(CampaignCorruptError):
            validate_campaign_journal({"event_type": []}, CampaignCorruptError)


if __name__ == "__main__":
    unittest.main()