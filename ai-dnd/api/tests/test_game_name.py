"""The player-visible game name is Unwritten; internal ids keep their old spelling."""

from __future__ import annotations

import unittest

import game


class SaveFileNameTests(unittest.TestCase):
    def test_foreign_save_file_error_names_unwritten(self):
        with self.assertRaises(ValueError) as caught:
            game._validate_save_payload({"format": "other-game", "version": 1})
        self.assertEqual(str(caught.exception), "Bu dosya bir Unwritten kayıt dosyası değil.")

    def test_own_format_id_is_unchanged(self):
        # the save format id is an internal id, not a player-visible name
        with self.assertRaises(ValueError) as caught:
            game._validate_save_payload({"format": "ai-dnd-save", "version": 999})
        self.assertNotIn("Unwritten kayıt dosyası değil", str(caught.exception))


class TerminalBannerTests(unittest.TestCase):
    def test_terminal_banner_says_unwritten(self):
        import inspect

        source = inspect.getsource(game)
        self.assertIn('print_fn("       UNWRITTEN")', source)
        self.assertNotIn('print_fn("       AI DUNGEON MASTER")', source)


if __name__ == "__main__":
    unittest.main()
