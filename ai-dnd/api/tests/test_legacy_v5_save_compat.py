"""Regression tests for lossless historic engine-save v5 resume.

No live model, no player data, no shared campaign database.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


class HistoricalV5SaveCompatibilityTests(unittest.TestCase):
    def test_legacy_v5_fields_survive_engine_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            manager = SessionManager(campaign_store=CampaignStore(Path(td) / "test.sqlite3"))
            _, _, record, _ = manager.create_campaign("Legacy fixture")
            session = record.game_session
            initial = session.serialize_game_state()
            self.assertEqual(initial["version"], 4)

            legacy = copy.deepcopy(initial)
            legacy["version"] = 5
            legacy["player"]["class"] = "Wizard"
            legacy["player"]["cantrips"] = ["Fire Bolt"]
            legacy["player"]["spells"] = ["Magic Missile"]
            legacy["player"]["spell_slots_remaining"] = {"1": 1}
            legacy["player"]["origin_feat"] = "Tough"
            legacy["world_state"]["xp_awarded_event_ids"] = []

            game._validate_save_payload(legacy)
            path = Path(td) / "v5-fixture.json"
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            resumed = game.GameSession()
            resumed.load_game(path)
            after = resumed.serialize_game_state()
            self.assertEqual(after["version"], 5)
            for key, value in legacy["player"].items():
                self.assertEqual(after["player"].get(key), value, key)
            for key, value in legacy["world_state"].items():
                self.assertIn(key, after["world_state"])
                if key in ("scene_state", "combat"):
                    for nested, nested_value in value.items():
                        self.assertEqual(after["world_state"][key].get(nested), nested_value)
                else:
                    self.assertEqual(after["world_state"][key], value, key)

            # Session-local version provenance; no leak into fresh campaigns.
            _, _, fresh, _ = manager.create_campaign("New fixture")
            self.assertEqual(fresh.game_session.serialize_game_state()["version"], 4)

    def test_invalid_v5_spell_record_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manager = SessionManager(campaign_store=CampaignStore(Path(td) / "test.sqlite3"))
            _, _, record, _ = manager.create_campaign("Corrupt fixture")
            legacy = copy.deepcopy(record.game_session.serialize_game_state())
            legacy["version"] = 5
            legacy["player"]["cantrips"] = ["Fire Bolt", "Fire Bolt"]
            legacy["player"]["spells"] = []
            legacy["player"]["spell_slots_remaining"] = {"1": 1}
            legacy["world_state"]["xp_awarded_event_ids"] = []
            with self.assertRaises(ValueError):
                game._validate_save_payload(legacy)


if __name__ == "__main__":
    unittest.main()