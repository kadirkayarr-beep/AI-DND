"""T3 (2026-11-25): broad catches that keep the game going still say what broke.

Money/save/Undo (class A) catches stay broad and roll back as before; a silent one now logs. A model-call fallback
(class B) stays broad so a turn never crashes, but logs an adapter outage at DEBUG and any other type, a bug,
at WARNING with its trace. Each test raises a type the code never expected.
"""
import logging
import unittest
from types import SimpleNamespace
from unittest import mock

import character_progression as core
import model_phase
from api import runtime_recovery
from class_progression import barbarian, noncaster, paladin, prepared_caster, sorcerer

EXPECTED = (RuntimeError("down"), TimeoutError("slow"), OSError("socket"))


class Unexpected(KeyError):
    """Not an error type the adapter raises: a bug, not an outage."""


class UnexpectedState(RuntimeError):
    """A rollback path meets a type it never named."""


class LogFallback(unittest.TestCase):
    logger = logging.getLogger("t3.fallback")

    def test_an_adapter_outage_logs_at_debug_only(self):
        for error in EXPECTED:
            with self.subTest(type(error).__name__), self.assertLogs(self.logger, "DEBUG") as logged:
                model_phase.log_fallback(self.logger, error, "arrival narration")
            self.assertEqual([r.levelno for r in logged.records], [logging.DEBUG])
            self.assertIn(type(error).__name__, logged.output[0])

    def test_our_own_bugs_under_the_outage_bases_still_warn(self):
        for error in (NotImplementedError("todo"), RecursionError("deep"), FileNotFoundError("x"), PermissionError("x")):
            with self.subTest(type(error).__name__), self.assertLogs(self.logger, "DEBUG") as logged:
                model_phase.log_fallback(self.logger, error, "arrival narration")
            self.assertEqual([r.levelno for r in logged.records], [logging.WARNING])

    def test_a_dropped_connection_is_still_an_outage(self):
        with self.assertLogs(self.logger, "DEBUG") as logged:
            model_phase.log_fallback(self.logger, ConnectionError("reset"), "arrival narration")
        self.assertEqual([r.levelno for r in logged.records], [logging.DEBUG])

    def test_any_other_type_logs_a_warning_with_its_trace(self):
        error = Unexpected("bug")
        with self.assertLogs(self.logger, "WARNING") as logged:
            model_phase.log_fallback(self.logger, error, "arrival narration")
        record = logged.records[0]
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertIs(record.exc_info[1], error)
        self.assertIn("arrival narration", record.getMessage())


CASES = [(error, "DEBUG") for error in EXPECTED] + [(Unexpected("bug"), "WARNING")]


class _Raising:
    def __init__(self, error):
        self.error = error

    def chat(self, **kwargs):
        raise self.error


class ModelFallbacksLog(unittest.TestCase):
    """Each changed module: the same fallback as before for every type, and a log line whose level names the kind."""

    def levels(self, logged):
        return [r.levelname for r in logged.records]

    def test_the_intent_reading_falls_back_to_unknown(self):
        import game
        from api.tests.town_seed import fixed_town
        with fixed_town(self, 20261351):
            session = game.create_session(seed=11)
        for error, level in CASES:
            with self.subTest(type(error).__name__), mock.patch.object(game, "ollama", _Raising(error)), \
                    self.assertLogs("game_parts.intent", "DEBUG") as logged:
                self.assertEqual(game.parse_player_intent("Etrafa bakıyorum.", session=session), {"intent": "unknown"})
            self.assertEqual(self.levels(logged), [level])

    def test_the_grounding_call_falls_back_to_no_steps(self):
        import grounded_action
        for error, level in CASES:
            run = SimpleNamespace(session=SimpleNamespace(), game=SimpleNamespace(ollama=_Raising(error)),
                                  model_calls=0, model_ms=[])
            with self.subTest(type(error).__name__), self.assertLogs("grounded_action", "DEBUG") as logged:
                steps = grounded_action.model_ground(run, "kapıyı aç", [{"id": "door.a", "kind": "door", "label": "Kapı"}])
            self.assertEqual((steps, run.model_calls), ([], 1))
            self.assertEqual(self.levels(logged), [level])

    def test_an_identity_suggestion_job_fails_as_provider_failed(self):
        from api.tests.test_identity_suggestion import SteppedService, request
        for error, level in CASES:
            def provider(prompt, error=error):
                raise error
            service = SteppedService(provider, timeout_seconds=2)
            service.submit(request())
            with self.subTest(type(error).__name__), self.assertLogs("ai_dnd.api.identity_suggestion", "DEBUG") as logged:
                service.run_queued()
            job = service.get("request-1")
            self.assertEqual((job.status, job.code), ("failed", "provider_failed"))
            self.assertEqual(self.levels(logged), [level])


class _LevelSession:
    """The snapshot is taken, then the first read of the character raises a type the step never names."""

    def __init__(self):
        self.taken = False
        self.restored = []

    @property
    def character(self):
        if self.taken:
            raise UnexpectedState("broken mid-step")
        return {}

    def _capture_runtime_snapshot(self):
        self.taken = True
        return "snapshot"

    def _restore_runtime_snapshot(self, snapshot):
        self.restored.append(snapshot)


PROJECTED = {"status": "projected"}
ASI = {"asi": {"increase": {}}}
STEPS = {
    "noncaster.apply_subclass_step": lambda s: noncaster.apply_subclass_step(
        s, {"hit_points": {"already_applied": True}}, 3, "champion"),
    "noncaster.apply_earned_final_step": lambda s: noncaster.apply_earned_final_step(s, {}),
    "noncaster.apply_asi_step": lambda s: noncaster.apply_asi_step(s, {}, ASI),
    "barbarian._apply_barbarian_three": lambda s: barbarian._apply_barbarian_three(s, {}, {}),
    "paladin._apply": lambda s: paladin._apply(s, {"to_level": 2}, {}),
    "prepared_caster.apply_level": lambda s: prepared_caster.PreparedCaster.apply_level(None, s, {"to_level": 2}, {}),
    "sorcerer._apply_selected_level_four": lambda s: sorcerer._apply_selected_level_four(s, {}, ASI),
}


class LevelStepRollbackLogs(unittest.TestCase):
    def test_an_unexpected_type_rolls_back_rejects_and_is_logged(self):
        for name, step in STEPS.items():
            with self.subTest(name):
                session = _LevelSession()
                with mock.patch.object(core, "_project_selected_asi_hp", return_value=PROJECTED), \
                        self.assertLogs("class_progression", "ERROR") as logged:
                    result = step(session)
                self.assertEqual(result, core._reject("resulting_state_invalid"))
                self.assertEqual(session.restored, ["snapshot"])
                self.assertIsInstance(logged.records[0].exc_info[1], UnexpectedState)


class TrustedRestoreLogs(unittest.TestCase):
    def test_a_restore_that_raises_an_unexpected_type_closes_the_session_and_is_logged(self):
        record = SimpleNamespace(game_session=object(), usable=True)

        def restore(session, snapshot):
            raise UnexpectedState("restore broke")
        with self.assertLogs("ai_dnd.api.runtime_recovery", "ERROR") as logged:
            verified = runtime_recovery.restore_trusted_runtime(record, {"save": {}}, restore=restore)
        self.assertFalse(verified)
        self.assertFalse(record.usable)
        self.assertIsInstance(logged.records[0].exc_info[1], UnexpectedState)


if __name__ == "__main__":
    unittest.main()
