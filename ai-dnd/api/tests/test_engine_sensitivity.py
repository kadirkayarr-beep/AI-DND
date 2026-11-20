"""Tests for the N8 sensitivity scan (scripts/engine_split/sensitivity.py) and its lock."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from api.tests.engine_sources import engine_source_files  # noqa: E402
from engine_split.sensitivity import classify, is_sensitive, main  # noqa: E402

LOCK = Path(__file__).parent / "engine_split_locks" / "sensitive.json"
GAME = ROOT / "game.py"


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, src: str, name: str = "game.py") -> Path:
        path = self.tmp / name
        path.write_text(src, encoding="utf-8")
        return path

    def test_the_known_names_are_listed(self):
        # spec section 5: six measured snapshot functions, plus two found by the money word (F8)
        lock = json.loads(LOCK.read_text(encoding="utf-8"))["functions"]
        for name in ("perform_skill_check", "execute_intent", "_thread_gate", "_run_player_turn_owned",
                     "_run_player_turn_keyed", "_person_answers_stock", "_front_step", "finalize_narration"):
            self.assertIn(name, lock)

    def test_every_flagged_function_is_in_the_lock_or_removed_with_a_reason(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        removed = {row["name"] for row in lock["removed"]}
        for name in classify(GAME):
            self.assertTrue(name in lock["functions"] or name in removed, name)
        for row in lock["removed"]:
            self.assertTrue(row["name"] and row["reason"] and row["reviewer"], row)

    def test_every_flagged_function_in_every_engine_file_is_in_the_lock_or_removed(self):
        # D-355: game.py and every game_parts/*.py; a moved sensitive name stays visible to N8
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        removed = {row["name"] for row in lock["removed"]}
        for path in engine_source_files(ROOT):
            for name in classify(path):
                with self.subTest(file=path.name, name=name):
                    self.assertTrue(name in lock["functions"] or name in removed, f"{path.name}: {name}")

    def test_reasons_by_content_not_by_name(self):
        src = ("def tidy(world):\n    world['currency'] -= 1\n"
               "def note(s):\n    return s._capture_runtime_snapshot()\n"
               "def put(p, t):\n    p.write_text(t)\n"
               "def keep():\n    return save_game('x')\n"
               "def plain():\n    return 1\n")
        self.assertEqual(classify(self.write(src)), {"tidy": ["money"], "note": ["snapshot"],
                                                     "put": ["file_write"], "keep": ["save"]})

    def test_every_file_write_form_is_seen_and_reads_are_not(self):
        src = ("def a(p):\n    open(p, 'w')\n"
               "def b(p):\n    open(p, mode='ab')\n"
               "def c(p):\n    p.write_bytes(b'')\n"
               "def d(p, q):\n    os.replace(p, q)\n"
               "def e(x, h):\n    json.dump(x, h)\n"
               "def f():\n    return tempfile.mkdtemp()\n"
               "def g(p):\n    return open(p)\n"
               "def h(p):\n    return open(p, 'r', encoding='utf-8')\n"
               "def i(s):\n    return s.replace('a', 'b')\n")
        self.assertEqual(classify(self.write(src)), {name: ["file_write"] for name in "abcdef"})

    def test_several_reasons_are_sorted_and_only_top_level_functions_count(self):
        src = ("def both(p, s):\n    p.write_text('x')\n    return s._restore_runtime_snapshot(1)\n"
               "class C:\n    def gold(self):\n        return 1\n"
               "GOLD = 1\n")
        self.assertEqual(classify(self.write(src)), {"both": ["file_write", "snapshot"]})

    def test_a_function_named_in_the_sets_carries_its_own_reason(self):
        src = ("def save_game():\n    pass\n"
               "def _restore_in_place():\n    pass\n"
               "def _validate_save_payload():\n    pass\n")
        self.assertEqual(classify(self.write(src)), {"save_game": ["save"], "_restore_in_place": ["snapshot"],
                                                     "_validate_save_payload": ["save"]})

    def test_the_wider_money_words_count(self):
        src = ("def a(x):\n    return x.shop\n"
               "def b():\n    price = 1\n"
               "def c(x):\n    return x.merchant\n"
               "def d(x):\n    return x.money\n")
        self.assertEqual(classify(self.write(src)), {name: ["money"] for name in "abcd"})

    def test_the_review_round_1_names_are_listed(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))["functions"]
        for name in ("_player_state_for_save", "_validate_save_payload", "_validate_combat_v3_payload",
                     "_validate_saved_multilevel_slots", "_origin_choices_for_save", "_migrate_legacy_combat_state",
                     "_capture_combat_death_checkpoint", "_finalize_player_death", "_start_combat_with_initiative",
                     "_restore_in_place", "_restore_combat_death_checkpoint", "_with_only_backed_money",
                     "create_shop_from_proposal", "validate_shop_proposal", "_ensure_local_merchant"):
            self.assertIn(name, lock)

    def test_write_refuses_once_game_parts_exists(self):  # F20: a rebuild from game.py alone drops moved names
        game = self.write("def pay():\n    return 'gold'\n")
        (self.tmp / "game_parts").mkdir()
        lock = self.tmp / "sensitive.json"
        before = json.dumps({"functions": {"moved": ["money"]}, "removed": []})
        lock.write_text(before, encoding="utf-8")
        self.assertEqual(main(["--write", "--game", str(game), "--lock", str(lock)]), 1)
        self.assertEqual(lock.read_text(encoding="utf-8"), before)

    def test_write_keeps_the_removed_rows(self):
        game = self.write("def pay():\n    return 'gold'\n\ndef tip():\n    return 'coin'\n")
        lock = self.tmp / "sensitive.json"
        row = {"name": "tip", "reason": "false alarm", "reviewer": "strong"}
        lock.write_text(json.dumps({"functions": {}, "removed": [row]}), encoding="utf-8")
        self.assertEqual(main(["--write", "--game", str(game), "--lock", str(lock)]), 0)
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8")), {"functions": {"pay": ["money"]}, "removed": [row]})

    def test_is_sensitive_reads_the_functions_table(self):
        lock = {"functions": {"a": ["money"]}, "removed": [{"name": "b", "reason": "x", "reviewer": "y"}]}
        self.assertTrue(is_sensitive("a", lock))
        self.assertFalse(is_sensitive("b", lock))
        self.assertFalse(is_sensitive("c", lock))


if __name__ == "__main__":
    unittest.main()
