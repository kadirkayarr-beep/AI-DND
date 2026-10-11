"""Deterministic Quest Outcomes V1 engine coverage."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import quest_catalog


def _definition(objectives=None, **extra):
    quest = {
        "quest_id": "quest.test",
        "title": "Test",
        "description": "Test quest",
        "giver_npc_id": "npc.giver",
        "objectives": objectives or [
            {
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            },
            {
                "objective_id": "defeat",
                "description": "Defeat the foe",
                "type": "defeat_entity",
                "target": "npc.foe",
            },
        ],
    }
    quest.update(extra)
    return quest


class QuestOutcomeTests(unittest.TestCase):
    def install(self, definition=None):
        patcher = patch.object(
            quest_catalog, "CATALOG", (definition or _definition(),)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_production_catalog_is_empty(self):
        self.assertEqual(quest_catalog.CATALOG, ())
        self.assertEqual(quest_catalog.catalog(), ())

    def test_catalog_validation_rejects_duplicates_and_unsupported_items(self):
        definition = _definition()
        with self.assertRaises(ValueError):
            quest_catalog.validate_catalog((definition, definition))
        with self.assertRaises(ValueError):
            quest_catalog.validate_catalog((_definition([{
                "objective_id": "item",
                "description": "Find a shield",
                "type": "acquire_item",
                "target": "Kalkan",
            }]),))

    def test_typed_offer_condition_is_respected_before_acceptance(self):
        definition = _definition(
            [{"objective_id": "visit", "description": "Visit forest",
              "type": "visit_location", "target": "forest"}],
            offer_condition={"type": "location_is", "target": "forest"},
        )
        self.install(definition)
        session = game.create_session(seed=7)
        self.assertEqual(session.quest_offers(), [])
        with self.assertRaises(ValueError):
            session.accept_quest("quest.test")

        session.world_state["location"] = "forest"
        self.assertEqual(
            [offer["quest_id"] for offer in session.quest_offers()],
            ["quest.test"],
        )
        self.assertEqual(
            session.accept_quest("quest.test")["quest"]["status"], "accepted"
        )

    def test_acceptance_is_explicit_and_repeated_commands_are_idempotent(self):
        self.install()
        session = game.create_session(seed=7)
        self.assertEqual(len(session.quest_offers()), 1)
        accepted = session.accept_quest("quest.test")
        self.assertEqual(accepted["transition"]["transition"], "accepted")
        self.assertEqual(accepted["quest"]["status"], "accepted")
        self.assertEqual(accepted["quest"]["giver_npc_id"], "npc.giver")
        self.assertIsNone(session.accept_quest("quest.test")["transition"])
        self.assertEqual(len(session.quest_offers()), 0)

    def test_cancel_offer_persists_and_repeated_cancel_does_not_emit(self):
        self.install()
        session = game.create_session(seed=7)
        cancelled = session.cancel_quest("quest.test")
        self.assertEqual(cancelled["transition"]["transition"], "cancelled")
        self.assertEqual(cancelled["quest"]["status"], "cancelled")
        self.assertIsNone(session.cancel_quest("quest.test")["transition"])
        self.assertIsNone(session.accept_quest("quest.test")["transition"])
        self.assertEqual(session.world_state["quests"][0]["status"], "cancelled")
        self.assertEqual(session.quest_offers(), [])

    def test_location_evidence_requires_registered_matching_location(self):
        self.install(_definition([{
            "objective_id": "visit",
            "description": "Visit the forest",
            "type": "visit_location",
            "target": "forest",
        }]))
        session = game.create_session(seed=7)
        session.accept_quest("quest.test")

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 1
        session.world_state["location"] = "castle"
        self.assertEqual(
            session.evaluate_quest_events(before, {"action": "travel"}), []
        )
        self.assertEqual(session.world_state["quests"][0]["objectives"][0]["progress"], 0)

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 2
        session.world_state["location"] = "forest"
        outcomes = session.evaluate_quest_events(before, {"action": "travel"})
        self.assertEqual(
            [item["transition"] for item in outcomes],
            ["objective_completed", "completed"],
        )
        self.assertEqual(session.world_state["quests"][0]["status"], "completed")

    def test_defeat_evidence_matches_stable_entity_id_not_name(self):
        self.install(_definition([{
            "objective_id": "defeat",
            "description": "Defeat the foe",
            "type": "defeat_entity",
            "target": "npc.foe",
        }]))
        session = game.create_session(seed=7)
        session.accept_quest("quest.test")
        session.world_state["npcs"] = [{
            "id": "npc.other",
            "name": "Foe",
            "location": session.world_state["location"],
            "current_hp": 0,
            "combat_status": "dead",
        }]
        before = copy.deepcopy(session.world_state)
        self.assertEqual(
            session.evaluate_quest_events(before, {"action": "attack"}), []
        )

        session.world_state["npcs"][0]["id"] = "npc.foe"
        session.world_state["npcs"][0]["current_hp"] = 5
        session.world_state["npcs"][0]["combat_status"] = "active"
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 1
        session.world_state["npcs"][0]["current_hp"] = 0
        session.world_state["npcs"][0]["combat_status"] = "dead"
        outcomes = session.evaluate_quest_events(before, {"action": "attack"})
        self.assertEqual(outcomes[0]["transition"], "objective_completed")
        self.assertEqual(outcomes[-1]["transition"], "completed")

    def test_supported_item_evidence_and_count_progress_are_deduplicated(self):
        definition = _definition([
            {
                "objective_id": "item",
                "description": "Acquire the sword",
                "type": "acquire_item",
                "target": "Kılıç",
            },
            {
                "objective_id": "visits",
                "description": "Visit the forest twice",
                "type": "visit_location",
                "target": "forest",
                "required_count": 2,
            },
        ])
        self.install(definition)
        session = game.create_session(seed=7)
        session.world_state["inventory"] = []
        session.accept_quest("quest.test")

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 1
        session.world_state["inventory"].append("Kalkan")
        self.assertEqual(
            session.evaluate_quest_events(before, {"action": "pickup"}), []
        )

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 2
        session.world_state["inventory"].append("Kılıç")
        item_outcomes = session.evaluate_quest_events(before, {"action": "pickup"})
        self.assertEqual(item_outcomes[0]["transition"], "objective_completed")

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 3
        session.world_state["location"] = "forest"
        first_visit = session.evaluate_quest_events(before, {"action": "travel"})
        self.assertEqual(first_visit[0]["transition"], "objective_progress")
        self.assertEqual(session.world_state["quests"][0]["updated_turn"], 3)
        self.assertEqual(session.evaluate_quest_events(before, {"action": "travel"}), [])

        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 4
        session.world_state["location"] = "tavern"
        session.evaluate_quest_events(before, {"action": "travel"})
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 5
        session.world_state["location"] = "forest"
        final_visit = session.evaluate_quest_events(before, {"action": "travel"})
        self.assertEqual(
            [item["transition"] for item in final_visit],
            ["objective_completed", "completed"],
        )

    def test_narration_never_creates_progress_and_sessions_are_isolated(self):
        self.install()
        first = game.create_session(seed=1)
        second = game.create_session(seed=1)
        first.accept_quest("quest.test")
        before = copy.deepcopy(first.world_state)
        self.assertEqual(
            first.evaluate_quest_events(
                before,
                {"narration": "The quest is accepted and the objective is complete."},
            ),
            [],
        )
        self.assertEqual(first.world_state["quests"][0]["objectives"][0]["progress"], 0)
        self.assertEqual(second.world_state["quests"], [])

    def test_v1_save_migrates_without_replacing_held_state_or_rng(self):
        session = game.create_session(seed=123)
        held_world = session.world_state
        held_character = session.character
        held_rng = session.rng
        rng_state = held_rng.getstate()
        payload = session.serialize_game_state()
        payload["version"] = 1
        payload["world_state"].pop("quests")
        payload["world_state"].pop("quest_processed_event_ids")
        expected_world = copy.deepcopy(payload["world_state"])
        expected_world["quests"] = []
        expected_world["quest_processed_event_ids"] = []

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-v1.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            session.load_game(path)

        self.assertIs(session.world_state, held_world)
        self.assertIs(session.character, held_character)
        self.assertIs(session.rng, held_rng)
        self.assertEqual(session.rng.getstate(), rng_state)
        self.assertEqual(session.world_state, expected_world)
        self.assertEqual(session.serialize_game_state()["version"], game.SAVE_FORMAT_VERSION)

    def test_malformed_v2_quest_records_are_rejected(self):
        session = game.create_session(seed=2)
        payload = session.serialize_game_state()
        payload["world_state"]["quests"] = [{
            "quest_id": "quest.bad",
            "status": "failed",
            "objectives": [],
        }]
        with self.assertRaises(ValueError):
            game._validate_save_payload(payload)


if __name__ == "__main__":
    unittest.main()