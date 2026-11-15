"""D-072: a fight question asked before a load does not stay open over the loaded game.

The surrendered-foe question ("Yine de vuruyor musun?") and the "kavga mı başlatıyorsun?" question live for one sitting
only and are never saved. Undo already takes them back with the turn (D-115); a load replaces the game in place (the
CLI "/yükle" and a stale campaign cache replaced by durable truth on resume), so a later "evet" must not answer a
question the loaded game never asked.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api.tests.test_species_traits import make_session


class LoadClosesSittingQuestionsTests(unittest.TestCase):
    def test_load_forgets_open_fight_questions(self):
        session = make_session("Human")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before-question.json"
            session.save_game(path)
            session._surrender_strike_asked = {"ids": ["npc-1"], "blow": ["attack"], "said": "vur", "command": None}
            session._attack_asked, session._blow_asked, session._blow_asked_line = True, "npc-1", "vur"
            session.load_game(path)
        self.assertIsNone(session._surrender_strike_asked)
        self.assertFalse(session._attack_asked)
        self.assertIsNone(session._blow_asked)
        self.assertIsNone(session._blow_asked_line)

    def test_failed_load_keeps_the_questions_of_the_game_still_running(self):
        session = make_session("Human")
        asked = {"ids": ["npc-1"], "blow": ["attack"], "said": "vur", "command": None}
        session._surrender_strike_asked = dict(asked)
        session._attack_asked, session._blow_asked, session._blow_asked_line = True, "npc-1", "vur"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(Exception):
                session.load_game(path)
        self.assertEqual(session._surrender_strike_asked, asked)
        self.assertEqual((session._attack_asked, session._blow_asked, session._blow_asked_line), (True, "npc-1", "vur"))


if __name__ == "__main__":
    unittest.main()
