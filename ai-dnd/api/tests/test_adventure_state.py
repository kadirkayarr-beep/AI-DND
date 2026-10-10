"""Phase 8 adventure state, legal transitions, and versioned records."""

import copy
import json
import tempfile
import typing
import unittest
from pathlib import Path
from unittest.mock import patch

import adventure
import game
import quest_catalog
from api.schemas import QuestState


def _objective():
    return {
        "objective_id": "visit",
        "description": "Visit the square",
        "type": "visit_location",
        "target": "square",
        "status": "active",
        "required_count": 1,
        "progress": 0,
    }


def _dynamic(**overrides):
    record = adventure.new_dynamic_quest(
        quest_id="adv.missing",
        title="Kayıp muhafız",
        description="Bir muhafız kayıp.",
        turn=1,
        template_id="MISSING_PERSON",
        template_version=1,
        binding_version=1,
        opportunity_key="campaign:missing:npc.source",
        creation_evidence="event:rumor:1",
        objectives=[_objective()],
        bindings={
            "source_npc_id": "npc.source",
            "target_npc_id": "npc.missing",
            "location_ids": ["square"],
            "faction_ids": [],
            "encounter_recipe_ids": [],
        },
        giver_npc_id="npc.source",
    )
    record.update(overrides)
    return record


class AdventureStateTests(unittest.TestCase):
    def test_legal_path_and_terminal_outcomes(self):
        row = _dynamic()
        discovered = adventure.transition(row, "DISCOVERED", 2)
        self.assertEqual(discovered["status"], "DISCOVERED")
        self.assertIsNone(discovered["deadline"])
        self.assertIsNone(discovered["accepted_turn"])
        self.assertEqual(row["status"], "AVAILABLE")

        active = adventure.transition(discovered, "ACTIVE", 3)
        self.assertEqual(active["accepted_turn"], 3)
        blocked = adventure.transition(active, "BLOCKED", 4)
        resumed = adventure.transition(blocked, "ACTIVE", 5)
        self.assertEqual(resumed["accepted_turn"], 3)

        completed = adventure.transition(resumed, "COMPLETED", 6, outcome="partial_success")
        self.assertEqual(completed["outcome"], "partial_success")
        failed = adventure.transition(resumed, "FAILED", 6, outcome="missed")
        self.assertEqual(failed["outcome"], "missed")
        abandoned = adventure.transition(discovered, "ABANDONED", 4, outcome="abandoned")
        self.assertIsNone(abandoned["accepted_turn"])

    def test_illegal_transitions_fail_closed(self):
        row = _dynamic()
        for state, turn, outcome in (
            ("COMPLETED", 2, "success"),
            ("ACTIVE", 2, None),
            ("FAILED", 2, "failed"),
        ):
            with self.assertRaises(adventure.TransitionError):
                adventure.transition(row, state, turn, outcome=outcome)
        self.assertEqual(row["status"], "AVAILABLE")

        failed = adventure.transition(
            adventure.transition(adventure.transition(row, "DISCOVERED", 2), "ACTIVE", 3),
            "FAILED",
            4,
            outcome="failed",
        )
        with self.assertRaises(adventure.TransitionError):
            adventure.transition(failed, "ACTIVE", 5)
        completed = adventure.transition(
            adventure.transition(adventure.transition(row, "DISCOVERED", 2), "ACTIVE", 3),
            "COMPLETED",
            4,
            outcome="success",
        )
        with self.assertRaises(adventure.TransitionError):
            adventure.transition(completed, "DISCOVERED", 5)

    def test_legacy_view_does_not_promote_the_row(self):
        definition = {
            "quest_id": "quest.test",
            "title": "Test",
            "description": "Test quest",
            "giver_npc_id": "npc.giver",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            session = game.create_session(seed=7)
            accepted = session.accept_quest("quest.test")["quest"]
            before = copy.deepcopy(accepted)
            self.assertTrue(adventure.is_legacy_quest(accepted))
            self.assertEqual(adventure.runtime_state(accepted), "ACTIVE")
            self.assertEqual(accepted, before)
            with self.assertRaises(adventure.TransitionError):
                adventure.transition(accepted, "DISCOVERED", 2)
            self.assertEqual(accepted, before)
            self.assertNotIn("template_version", accepted)
            self.assertNotIn("record_kind", accepted)

            session.cancel_quest("quest.test")
            cancelled = session.world_state["quests"][0]
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(adventure.runtime_state(cancelled), "ABANDONED")
            self.assertTrue(adventure.is_legacy_quest(cancelled))

    def test_available_deadline_and_corrupt_binding_fail_closed(self):
        dated = _dynamic()
        dated["deadline"] = "scheduled:adventure:1"
        with self.assertRaises(ValueError):
            adventure.validate_dynamic_saved_quest(dated, set())
        invented = _dynamic()
        invented["bindings"]["invented_npc"] = "npc.new"
        with self.assertRaises(ValueError):
            adventure.validate_dynamic_saved_quest(invented, set())
        legacy_status = _dynamic(status="accepted")
        with self.assertRaises(ValueError):
            adventure.validate_dynamic_saved_quest(legacy_status, set())

    def test_save_round_trip_keeps_versions_and_legacy_shape(self):
        definition = {
            "quest_id": "quest.test",
            "title": "Test",
            "description": "Test quest",
            "giver_npc_id": "npc.giver",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            session = game.create_session(seed=3)
            session.accept_quest("quest.test")
            dynamic = _dynamic()
            session.world_state["quests"].append(dynamic)
            payload = session.serialize_game_state()
            game._validate_save_payload(payload)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "adventure.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                session.load_game(path)
            loaded = session.world_state["quests"]
            self.assertTrue(adventure.is_legacy_quest(loaded[0]))
            self.assertEqual(loaded[0]["status"], "accepted")
            self.assertEqual(loaded[1]["template_id"], "MISSING_PERSON")
            self.assertEqual(loaded[1]["template_version"], 1)
            self.assertEqual(loaded[1]["binding_version"], 1)
            self.assertEqual(loaded[1]["bindings"]["target_npc_id"], "npc.missing")

            promoted = copy.deepcopy(loaded[0])
            promoted["template_version"] = 1
            bad = session.serialize_game_state()
            bad["world_state"]["quests"] = [promoted]
            with self.assertRaises(ValueError):
                game._validate_save_payload(bad)

    def test_corrupt_dynamic_row_does_not_load_or_spawn_a_replacement(self):
        session = game.create_session(seed=5)
        legacy = {
            "quest_id": "quest.legacy",
            "title": "Eski iş",
            "description": "Eski kayıt",
            "giver_npc_id": "npc.giver",
            "status": "accepted",
            "objectives": [],
            "created_turn": 1,
            "accepted_turn": 1,
            "updated_turn": 1,
        }
        session.world_state["quests"] = [legacy]
        payload = session.serialize_game_state()
        broken = copy.deepcopy(payload)
        broken["world_state"]["quests"] = [{
            "record_kind": "dynamic",
            "quest_id": "adv.broken",
            "title": "Bozuk",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                session.load_game(path)
        self.assertEqual(session.world_state["quests"], [legacy])
        self.assertTrue(adventure.is_legacy_quest(session.world_state["quests"][0]))
        self.assertFalse(any(item.get("quest_id") == "adv.broken" for item in session.world_state["quests"]))

    def test_public_quest_enum_stays_legacy(self):
        self.assertEqual(
            set(typing.get_args(QuestState.model_fields["status"].annotation)),
            {"accepted", "completed", "cancelled"},
        )


if __name__ == "__main__":
    unittest.main()
