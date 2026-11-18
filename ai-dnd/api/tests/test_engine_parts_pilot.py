"""The bound-session wrapper filter reads an explicit list of part modules (game.py split, T2.1)."""
import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game  # noqa: E402
from api.tests.engine_sources import engine_source_files  # noqa: E402
from api.tests.guard_bound import CHILD_PROCESS, guard_bound  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402


class WrapperFilter(unittest.TestCase):
    def test_the_wrapper_filter_reads_an_explicit_part_list(self):
        self.assertEqual(game._PART_MODULES, ("game_parts.character_rules",))  # Task 18 (pilot a)
        tree = ast.parse(engine_source_files()[0].read_text(encoding="utf-8"))
        assign = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_ENGINE_FUNCTIONS")
        self.assertIn("_PART_MODULES", {n.id for n in ast.walk(assign) if isinstance(n, ast.Name)})


class PilotRollD20(unittest.TestCase):
    """Pilot (a): roll_d20 lives in game_parts/character_rules.py and still behaves as an engine function."""

    def test_a_moved_function_still_binds_the_session_it_is_given(self):
        with fixed_town(self, 20261120):
            s = game.create_session(seed=5)
            default_state = game._session().rng.getstate()
            before = s.rng.getstate()
            value = game.roll_d20(session=s)
            self.assertIn(value, range(1, 21))
            self.assertNotEqual(s.rng.getstate(), before)
            self.assertEqual(game._session().rng.getstate(), default_state)
        self.assertTrue(game.roll_d20._session_bound)
        self.assertEqual(game.roll_d20.__module__, "game_parts.character_rules")

    def test_a_part_reads_engine_names_through_game(self):
        fake = MagicMock()
        fake.rng.randint.return_value = 7
        with patch.object(game, "_session", return_value=fake):
            self.assertEqual(game.roll_d20.__wrapped__(), 7)  # the part's own function, without the session wrapper
        fake.rng.randint.assert_called_once_with(1, 20)

    def test_a_patch_on_game_roll_d20_reaches_engine_callers(self):
        with fixed_town(self, 20261121):
            character = game._session().character
            with patch.object(game, "roll_d20", return_value=20) as rolled:
                result = game.perform_skill_check("Perception", 12, character["modifiers"],
                                                  character["proficient_skills"], character["proficiency_bonus"])
        rolled.assert_called()
        self.assertEqual(result["dice"], 20)

    @guard_bound(CHILD_PROCESS)
    def test_both_import_orders_work_in_a_fresh_interpreter(self):
        for code in ("import game, game_parts; print(game.roll_d20.__module__)",
                     "import game_parts, game; print(game.roll_d20.__module__)"):
            done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, "game_parts.character_rules"), done.stderr)


if __name__ == "__main__":
    unittest.main()
