"""D-209 (ORTA): on a turn that moved no coin, the narrator may not tell coin going into or out of the player's purse.

D-142 holds a sentence that says where the purse stands ('Kesende 90 bakır var.'); this holds a sentence that says
coin entered or left it ('Kesene 20 bakır giriyor.'). Python moved no coin, so that one sentence leaves the line
(repair, never refusal). A turn whose coin Python moved keeps it. No real model is called.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import game
import pocket

NARRATIVE = {"action": "narrative", "status": "resolved"}


class PurseMoveSentence(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.s.world_state["currency"] = {"player": 7}

    def told(self, narration, action_result=NARRATIVE):
        return self.s.finalize_narration(narration, "etrafa bakıyorum", action_result=dict(action_result))

    def test_coin_going_in_or_out_of_the_purse_leaves_the_line(self):
        for line in ("Kesene 20 bakır giriyor.", "Kesenden 5 gümüş çıkıyor.", "Kesenize 3 altın giriyor.",
                     "Kesenden iki gümüş eksiliyor.", "Kesene birkaç bakır ekleniyor.",
                     "Kesenin içine 20 bakır düşüyor.", "Kesenden 5 gümüş çıkarıp tezgâha bırakıyorsun.",
                     "Kesene 10 bakır koyuyorsun.", "20 copper goes into your purse.",
                     "Three silver leave your pouch.", "Kesene 20 bakır ekliyorsun.", "Kesenden 3 gümüş ödüyorsun.",
                     "Kesene 20 bakır atıyorsun.", "Kesene 20 bakır doluyor.", "Kesenden 3 gümüş alıyorsun.",
                     "Kesenden 3 gümüş ödedin."):
            with self.subTest(line=line):
                out = self.told("Rüzgâr kapıyı sarsıyor. " + line)
                self.assertIn("Rüzgâr kapıyı sarsıyor.", out)
                self.assertNotIn(line, out)

    def test_any_turn_of_free_prose_is_held(self):
        for action in ("explore", "interaction", "world_interaction", "skill_check"):
            with self.subTest(action=action):
                out = self.told("Hava serin. Kesene 20 bakır giriyor.", {"action": action, "status": "resolved"})
                self.assertNotIn("20 bakır", out)

    def test_a_turn_that_moved_coin_and_python_own_line_are_not_touched(self):
        moved = {"action": "narrative", "status": "resolved", "state_changes": ["currency"]}
        self.assertIn("Kesene 20 bakır giriyor.", self.told("Kesene 20 bakır giriyor.", moved))
        python_line = {"action": "query", "status": "resolved", "direct_response": True}
        self.assertIn("Kesene 20 bakır giriyor.", self.told("Kesene 20 bakır giriyor.", python_line))

    def test_a_purse_with_no_coin_moving_stays(self):
        # The purse named with no coin, coin named with no purse, and a road cut by 'kesen' are story.
        for line in ("Elini kesene atıyorsun.", "Kesenden bir ip sarkıyor.", "Kapıdan bakır fenerli bir adam giriyor.",
                     "Yolunu kesen haydut içeri giriyor.", "Kesene bakıyorsun.", "Kesende 7 bakır var."):
            with self.subTest(line=line):
                self.assertEqual(line, pocket.without_false_purse(line, self.s.world_state))
                self.assertIn(line, self.told("Rüzgâr kapıyı sarsıyor. " + line))

    def test_under_it_is_not_gold(self):
        # Review: 'altına' is 'under it'. Only this gate is held here; the older money gate in town_knowledge reads it
        # too (logged as a new bug in the ledger).
        line = "Kesenden bir ip sarkıyor, ucu masanın altına düşüyor."
        self.assertEqual(line, pocket.without_false_purse(line, self.s.world_state))
        self.assertEqual("", pocket.without_false_purse("Kesenden 3 altın düşüyor.", self.s.world_state))


class PurseMoveTurn(unittest.TestCase):
    def test_the_turn_written_to_history_holds_no_coin_that_did_not_move(self):
        s = game.create_session(seed=7)
        s.world_state["currency"] = {"player": 7}

        def chat(*args, **kwargs):
            packet = {"narration": "Rüzgâr kapıyı sarsıyor. Kesene 20 bakır giriyor.", "world_updates": {},
                      "lore_claims": []}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=chat):
            out = s.run_player_turn("etrafa bakıyorum")
        self.assertEqual(s.world_state["currency"]["player"], 7)
        self.assertNotIn("20 bakır", out["narration"])
        self.assertIn("Rüzgâr kapıyı sarsıyor.", out["narration"])


if __name__ == "__main__":
    unittest.main()
