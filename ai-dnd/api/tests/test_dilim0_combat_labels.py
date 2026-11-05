# ai-dnd/api/tests/test_dilim0_combat_labels.py
"""Dilim 0 (20): the sentence sent with a structured combat step is a label; the engine result is the same."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.c10_reckless_external_fixture_runtime import _seed_reckless_attack
from combat_lifecycle import CombatRequestError

ACTION_ID = "6f1c2a3e-1b2c-4d3e-8f4a-5b6c7d8e9f01"  # one fixed uuid4 for both runs


class TheSentenceIsALabel(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        store = CampaignStore(root / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        manager = SessionManager(campaign_store=store)
        self.seed = _seed_reckless_attack(manager, store, root)  # player's turn, Commoner at 5 ft
        self.session_id, record, *_ = manager.resume_campaign(self.seed["campaign_id"])
        self.session = record.game_session

    def run_with(self, message, step):
        """One engine turn from the same captured runtime (world, character, RNG); returns what is compared."""
        result = self.session.run_player_turn(
            message, target_id=self.seed["combat_target_id"], combat_action={"steps": [step]},
            interaction_mode="do", action_id=ACTION_ID, session_id=self.session_id)
        after = self.session._capture_runtime_snapshot()
        action = {k: v for k, v in (result.get("action_result") or {}).items() if k not in {"narration", "direct_response"}}
        world = after["world_state"]
        return action, after["character"], after["rng_state"], world.get("combat"), world.get("currency"), world.get("inventory")

    def test_the_sent_sentence_does_not_change_the_combat_result(self):
        target = self.seed["combat_target_id"]
        before = self.session._capture_runtime_snapshot()
        for old, new, step in (("Saldırı Action kullanıyorum.", "Saldırıyorum.", {"kind": "attack", "target_id": target}),
                               ("Dash Action kullanıyorum.", "Koşuyorum.", {"kind": "dash"}),
                               ("5 feet hareket ediyorum.", "5 fit hareket ediyorum.", {"kind": "move", "distance_ft": 5})):
            with self.subTest(step=step["kind"]):
                self.session._restore_runtime_snapshot(before)
                try:
                    a = self.run_with(old, step)
                except CombatRequestError as first:
                    # A refused step must be refused the same way with the new sentence; it is not dropped.
                    self.session._restore_runtime_snapshot(before)
                    with self.assertRaises(CombatRequestError) as second:
                        self.run_with(new, step)
                    self.assertEqual(first.code, second.exception.code)
                    continue
                self.session._restore_runtime_snapshot(before)
                b = self.run_with(new, step)
                self.assertEqual(a, b)
