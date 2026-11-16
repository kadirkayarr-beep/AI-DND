"""D-258 (D-039): a real format-3 save file, loaded and saved by today's code.

`fixtures/f3_wizard_save.json` was written by the format-3 writer itself: the code of commit 26c653e7^ (the last commit
before save format 4), `game.create_session(seed=7)` then `game.save_game(path)`. One edit was made before the save: the
class string of the generated character (a Fighter, the old random creation) was set to "Wizard"; no field was added or
hand-written. A format-3 file has no spell fields and no `spellcasting_v1` at all (spell state came with format 4)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import game
import spell_preparation

FIXTURE = Path(__file__).parent / "fixtures" / "f3_wizard_save.json"


class RealFormatThreeSave(unittest.TestCase):
    def setUp(self):
        self.original = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_the_fixture_is_a_format_three_file_without_spell_fields(self):
        self.assertEqual((self.original["format"], self.original["version"]), ("ai-dnd-save", 3))
        self.assertEqual(self.original["player"]["class"], "Wizard")
        for field in ("cantrips", "spells", "spell_slots_remaining"):
            self.assertNotIn(field, self.original["player"])
        self.assertNotIn("spellcasting_v1", self.original["world_state"])

    def test_it_loads_keeps_format_three_and_saves_back_the_same_player(self):
        session = game.GameSession()
        session.load_game(FIXTURE)
        self.assertEqual(session._persisted_engine_format, 3)
        self.assertEqual((session.character["class"], session.character["spells"]), ("Wizard", []))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "again.json"
            session.save_game(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 3)  # the file's own format is written back
            # every field of the old file comes back equal; the only new ones are the empty identity fields
            self.assertEqual({key: saved["player"][key] for key in self.original["player"]}, self.original["player"])
            self.assertEqual({key: value for key, value in saved["player"].items() if key not in self.original["player"]},
                             {"origin": None, "appearance": None, "personality": None, "backstory": None})
            self.assertNotIn("spellcasting_v1", saved["world_state"])
            again = game.GameSession()
            again.load_game(path)
            self.assertEqual((again.character, again.world_state), (session.character, session.world_state))

    def test_the_spellbook_window_does_not_see_a_real_format_three_wizard(self):
        # Observed 2026-11-16 and pinned here, see debt register D-281: a real format-3 file has no spell state, so the
        # one-time spellbook choice of D-039 (made for a version-1 state) is not offered to it; the window says
        # "not_preparing_class". The synthetic `bookless()` helper of test_d039_spellbook_choice builds a version-1 state.
        session = game.GameSession()
        session.load_game(FIXTURE)
        before = copy.deepcopy((session.world_state, session.character))
        view = spell_preparation.view(session)
        self.assertEqual((view["supported"], view["blocked_reason"], view["spellbook_options"]),
                         (False, "not_preparing_class", []))
        self.assertEqual((session.world_state, session.character), before)


if __name__ == "__main__":
    unittest.main()
