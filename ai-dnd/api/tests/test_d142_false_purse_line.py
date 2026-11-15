"""D-142 (ORTA-10): the narrator may not tell the player's purse a sum it does not hold.

A sentence of free prose that says what is in the player's purse ('Kesende 90 bakır var.') stays only when its
figure is the engine's real purse; otherwise that one sentence leaves the line (repair, never refusal). No real
model is called.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import game
import pocket

NARRATIVE = {"action": "narrative", "status": "resolved"}


class FalsePurseSentence(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.s.world_state["currency"] = {"player": 7}

    def told(self, narration, action_result=NARRATIVE):
        return self.s.finalize_narration(narration, "etrafa bakıyorum", action_result=dict(action_result))

    def test_a_purse_the_player_does_not_hold_leaves_the_line(self):
        for line in ("Kesende 90 bakır var.", "Kesende doksan bakır kaldı.", "Kesendeki 9 gümüş şıngırdıyor.",
                     "Kesen 2 altınla dolu.", "Toplam 90 bakır paran var.", "Kesende 90 sikke var."):
            with self.subTest(line=line):
                out = self.told("Rüzgâr kapıyı sarsıyor. " + line)
                self.assertIn("Rüzgâr kapıyı sarsıyor.", out)
                self.assertNotIn(line, out)

    def test_a_line_that_was_all_false_purse_is_not_written(self):
        out = self.told("Kesende 90 bakır var.")
        self.assertTrue(out.strip())
        self.assertNotIn("90", out)

    def test_the_real_purse_stays(self):
        for line in ("Kesende 7 bakır var.", "Kesende yedi bakır kaldı."):
            with self.subTest(line=line):
                self.assertIn(line, self.told("Rüzgâr kapıyı sarsıyor. " + line))

    def test_mixed_coin_is_summed_in_copper(self):
        self.s.world_state["currency"] = {"player": 15}
        self.assertIn("Kesende 1 gümüş 5 bakır var.", self.told("Kesende 1 gümüş 5 bakır var."))
        self.assertNotIn("2 gümüş", self.told("Hava serin. Kesende 2 gümüş var."))

    def test_gold_written_in_the_pack_counts_as_purse(self):
        self.s.world_state["inventory"] = [*self.s.world_state.get("inventory", []), {"name": "1 Altın"}]
        self.assertIn("Kesende 107 bakır var.", self.told("Kesende 107 bakır var."))

    def test_any_turn_of_free_prose_is_held_to_the_purse(self):
        for action in ("explore", "interaction", "world_interaction", "skill_check"):
            with self.subTest(action=action):
                out = self.told("Hava serin. Kesende 90 bakır var.", {"action": action, "status": "resolved"})
                self.assertNotIn("90 bakır", out)

    def test_python_own_line_and_a_coin_turn_are_not_touched(self):
        moved = {"action": "narrative", "status": "resolved", "state_changes": ["currency"]}
        self.assertIn("Kesende 90 bakır var.", self.told("Kesende 90 bakır var.", moved))
        python_line = {"action": "query", "status": "resolved", "direct_response": True}
        self.assertIn("Kesende 90 bakır var.", self.told("Kesende 90 bakır var.", python_line))

    def test_a_purse_word_with_no_figure_stays(self):
        self.assertIn("Kesen hafif, birkaç bakır şıngırdıyor.", self.told("Kesen hafif, birkaç bakır şıngırdıyor."))

    def test_a_price_a_demand_or_a_cut_road_is_not_the_purse(self):
        # Review of D-142: only the figure the purse clause names is the purse; a price beside it and the verb
        # 'kesmek' ('yolunu kesen') are story, and stay. Held to the purse check itself: an older pass on free prose
        # already takes an unbacked gold figure ('20 altın') off the whole line.
        for line in ("Yolunu kesen haydut 20 altın istiyor.", "Kılıç 15 altın; paran buna yetmez.",
                     "Kesende 7 bakır var; ekmek 2 bakır.", "Kesende 7 bakır var, ekmek 2 bakır.",
                     "Kesende 7 bakır var ama bira 4 bakır.", "Paran 2 bakırlık ekmeğe yeter."):
            with self.subTest(line=line):
                self.assertEqual(line, pocket.without_false_purse(line, self.s.world_state))
        for line in ("Kesende 7 bakır var; ekmek 2 bakır.", "Kesende 7 bakır var ama bira 4 bakır."):
            with self.subTest(turn=line):
                self.assertIn(line, self.told("Rüzgâr kapıyı sarsıyor. " + line))

    def test_a_purse_listed_coin_by_coin_is_one_sum(self):
        self.s.world_state["currency"] = {"player": 27}
        for line in ("Kesende 2 gümüş ve 7 bakır var.", "Kesende 2 gümüş, 7 bakır var."):
            with self.subTest(line=line):
                self.assertIn(line, self.told("Rüzgâr kapıyı sarsıyor. " + line))

    def test_a_figure_opening_the_next_clause_is_not_the_purse(self):
        # Second review of D-142: a need, a price or a debt that opens with a figure after ',', ':', ';' or 've' is
        # not more coin in the purse; the true purse sentence stays whole.
        for line in ("Kesende 7 bakır kaldı, 3 bakır daha lazım.", "Kesende 7 bakır var: iki ekmek 4 bakır tutar.",
                     "Kesende 7 bakır var, 2 bakır da ekmeğe gider.", "Kesende 7 bakır var ve 3 bakır borcun var."):
            with self.subTest(turn=line):
                self.assertIn(line, self.told("Rüzgâr kapıyı sarsıyor. " + line))
        for line in ("Kesende 7 bakır var; 2 gümüşe ihtiyacın var.", "Kesende 7 bakır var, 15 altınlık kılıca yetmez.",
                     "Tüccar, kesende kaç bakır kaldığını soruyor; 90 bakır istiyor.",
                     "Kesende 7 bakır var; 2 gümüş yok."):
            with self.subTest(line=line):
                self.assertEqual(line, pocket.without_false_purse(line, self.s.world_state))
        # A purse still counted coin by coin across the break is one sum, and a false one still leaves.
        for line in ("Kesende 2 gümüş, 70 bakır var.", "Kesende, 90 bakır var.", "Kesende 2 gümüş ve 5 bakır da var."):
            with self.subTest(lie=line):
                self.assertEqual("", pocket.without_false_purse(line, self.s.world_state))

    def test_a_false_purse_beside_a_price_or_said_as_worth_still_leaves(self):
        for line in ("Kesende 90 bakır var; ekmek 2 bakır.", "Kesende 90 bakır var, ekmek 7 bakır.",
                     "Paranız 50 gümüş eder.", "Yolu kesen haydut bilmiyor ama kesende 90 bakır var."):
            with self.subTest(line=line):
                out = self.told("Rüzgâr kapıyı sarsıyor. " + line)
                self.assertIn("Rüzgâr kapıyı sarsıyor.", out)
                self.assertNotIn(line, out)

    def test_an_english_purse_is_held_to_the_purse_too(self):
        for line in ("Your purse holds 90 copper.", "Your pouch has 3 silver left."):
            with self.subTest(line=line):
                self.assertNotIn(line, self.told("The wind rattles the door. " + line))
        self.assertIn("Your purse holds 7 copper.", self.told("The wind rattles the door. Your purse holds 7 copper."))


class FalsePurseTurn(unittest.TestCase):
    def test_the_turn_written_to_history_holds_no_false_purse(self):
        s = game.create_session(seed=7)
        s.world_state["currency"] = {"player": 7}

        def chat(*args, **kwargs):
            packet = {"narration": "Rüzgâr kapıyı sarsıyor. Kesende 90 bakır var.", "world_updates": {},
                      "lore_claims": []}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=chat):
            out = s.run_player_turn("etrafa bakıyorum")
        self.assertEqual(s.world_state["currency"]["player"], 7)
        self.assertNotIn("90 bakır", out["narration"])
        self.assertIn("Rüzgâr kapıyı sarsıyor.", out["narration"])


if __name__ == "__main__":
    unittest.main()
