"""Legacy offline entry-point ownership, including cold imports and failures."""

from contextlib import redirect_stdout
import importlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

import game
from api.ollama_adapter import AuthenticatedOllamaAdapter
from offline_test_support import offline_model


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = (
    "test_combat", "test_npc_query", "test_door_enter", "test_self_query",
    "test_query", "test_migration", "test_migration_harden", "test_actual_logic",
)


class LegacyScriptIsolationTests(unittest.TestCase):
    def run_entry_point(self, name):
        module = importlib.import_module(name)
        output = io.StringIO()
        with redirect_stdout(output):
            module.run_tests()
        if name == "test_combat":
            self.assertIn("=== ALL COMBAT TESTS PASSED ===", output.getvalue())

    def run_python(self, code):
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT,
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cold_imports_in_both_orders_do_not_bind_or_call_a_mock(self):
        for names in (SCRIPTS, SCRIPTS[::-1]):
            for engine_first in (False, True):
                with self.subTest(names=names, engine_first=engine_first):
                    self.run_python(f"""
import importlib
import sys
from unittest.mock import patch
import ollama
original_module = ollama
original_chat, original_list = ollama.chat, ollama.list
with patch.object(ollama, 'chat', side_effect=AssertionError('live chat forbidden')) as chat, \\
     patch.object(ollama, 'list', side_effect=AssertionError('live list forbidden')) as listing:
    if {engine_first!r}:
        import game
    for name in {names!r}:
        importlib.import_module(name)
        import game
        assert game.ollama is original_module
        assert sys.modules['ollama'] is original_module
        assert game.ollama.chat is chat
        assert game.ollama.list is listing
    chat.assert_not_called()
    listing.assert_not_called()
assert ollama.chat is original_chat
assert ollama.list is original_list
""")

    def test_direct_main_entry_points_succeed_and_restore_bindings(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                # Fresh process per script, with real-client calls forbidden.
                self.run_python(f"""
import runpy
import sys
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import ollama
with patch.object(ollama, 'chat', side_effect=AssertionError('live chat forbidden')) as chat, \\
     patch.object(ollama, 'list', side_effect=AssertionError('live list forbidden')) as listing:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_path({str(ROOT)!r} + '/{name}.py', run_name='__main__')
    if {name!r} == 'test_combat':
        assert '=== ALL COMBAT TESTS PASSED ===' in output.getvalue()
    import game
    assert game.ollama is ollama
    assert sys.modules['ollama'] is ollama
    assert ollama.chat is chat and ollama.list is listing
    chat.assert_not_called()
    listing.assert_not_called()
""")

    def test_mixed_entry_points_preserve_an_active_api_adapter(self):
        for names in (SCRIPTS, SCRIPTS[::-1]):
            with self.subTest(order=names):
                target, module_target, client = MagicMock(), MagicMock(), MagicMock()
                adapter = AuthenticatedOllamaAdapter(client)
                with patch.object(game, "ollama", target), \
                     patch.dict(sys.modules, {"ollama": module_target}), \
                     adapter.engine_binding(), redirect_stdout(io.StringIO()):
                    active_list, active_chat = target.list, target.chat
                    for name in names:
                        self.run_entry_point(name)
                        self.assertIs(game.ollama, target)
                        self.assertIs(sys.modules["ollama"], module_target)
                        self.assertIs(target.list, active_list)
                        self.assertIs(target.chat, active_chat)
                    client.chat.assert_not_called()
                    client.list.assert_not_called()

    def test_each_script_restores_on_failure_and_owns_a_fresh_mock(self):
        for name in SCRIPTS:
            module = importlib.import_module(name)
            if name == "test_combat":
                owner, method = module, "find_weapon_in_inventory"
            elif name in ("test_npc_query", "test_actual_logic"):
                owner, method = module.session, "active_npcs"
            elif name in ("test_migration", "test_migration_harden"):
                owner, method = module.session, "_normalize_ground_items"
            else:
                owner, method = module.session, "run_player_turn"
            models = []

            def fail(*args, **kwargs):
                models.append(game.ollama)
                self.assertIs(game.ollama, sys.modules["ollama"])
                self.assertEqual(game.ollama.chat.call_count, 0)
                self.assertIsNone(game.ollama.chat.side_effect)
                game.ollama.chat.side_effect = RuntimeError("poisoned mock")
                raise RuntimeError("script failed")

            with self.subTest(script=name):
                target, module_target = MagicMock(), MagicMock()
                original_chat, original_list = target.chat, target.list
                with patch.object(game, "ollama", target), \
                     patch.dict(sys.modules, {"ollama": module_target}), \
                     patch.object(owner, method, side_effect=fail), \
                     redirect_stdout(io.StringIO()):
                    for _ in range(2):
                        with self.assertRaisesRegex(RuntimeError, "script failed"):
                            module.run_tests()
                        self.assertIs(game.ollama, target)
                        self.assertIs(sys.modules["ollama"], module_target)
                        self.assertIs(target.chat, original_chat)
                        self.assertIs(target.list, original_list)
                self.assertIsNot(models[0], models[1])

    def test_nested_scopes_restore_absent_module_on_interruption(self):
        models = []

        @offline_model(game)
        def inner():
            models.append(game.ollama)
            self.assertIs(sys.modules["ollama"], game.ollama)
            raise KeyboardInterrupt()

        @offline_model(game)
        def outer():
            models.append(game.ollama)
            with self.assertRaises(KeyboardInterrupt):
                inner()
            self.assertIs(game.ollama, models[0])
            self.assertIs(sys.modules["ollama"], models[0])

        target = game.ollama
        with patch.dict(sys.modules):
            sys.modules.pop("ollama", None)
            outer()
            self.assertNotIn("ollama", sys.modules)
            self.assertIs(game.ollama, target)
        self.assertIsNot(models[0], models[1])


if __name__ == "__main__":
    unittest.main()