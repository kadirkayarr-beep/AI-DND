"""Direct unit tests for api.runtime_recovery: a restore is trusted only when it provably equals the snapshot."""

import unittest
from types import SimpleNamespace

from api import runtime_recovery


class _Session:
    """A stand-in session whose restore either works, lies, or raises."""

    def __init__(self, behaviour="ok", save=None, runtime=None):
        self.behaviour = behaviour
        self.state = {"save": {"hp": 3}, "runtime": {"dice": 1}} if save is None else {"save": save, "runtime": runtime}

    def _restore_runtime_snapshot(self, runtime):
        if self.behaviour == "raise":
            raise RuntimeError("restore failed")
        if self.behaviour == "ok":
            self.state["runtime"] = dict(runtime)
            self.state["save"] = {"hp": 3}

    def serialize_game_state(self):
        return self.state["save"]

    def _capture_runtime_snapshot(self):
        return self.state["runtime"]


def _snapshot():
    return {"save": {"hp": 3}, "runtime": {"dice": 1}}


class DigestTests(unittest.TestCase):
    def test_digest_ignores_key_order_and_detects_change(self):
        self.assertEqual(runtime_recovery.state_digest({"a": 1, "b": 2}), runtime_recovery.state_digest({"b": 2, "a": 1}))
        self.assertNotEqual(runtime_recovery.state_digest({"a": 1}), runtime_recovery.state_digest({"a": 2}))

    def test_digest_handles_non_json_values(self):
        self.assertEqual(len(runtime_recovery.state_digest({"seen": {1, 2}})), 64)


class RestoreTests(unittest.TestCase):
    def _record(self, session):
        return SimpleNamespace(game_session=session, usable=None)

    def test_verified_restore_marks_the_session_usable(self):
        record = self._record(_Session("ok"))
        self.assertTrue(runtime_recovery.restore_trusted_runtime(record, _snapshot()))
        self.assertIs(record.usable, True)

    def test_restore_that_raises_closes_the_session(self):
        record = self._record(_Session("raise"))
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, _snapshot()))
        self.assertIs(record.usable, False)

    def test_restore_that_silently_does_nothing_is_not_trusted(self):
        record = self._record(_Session("lie", save={"hp": 99}, runtime={"dice": 1}))
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, _snapshot()))
        self.assertIs(record.usable, False)

    def test_restore_that_skips_the_runtime_part_is_not_trusted(self):
        record = self._record(_Session("lie", save={"hp": 3}, runtime={"dice": 7}))
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, _snapshot()))

    def test_caller_restore_seam_replaces_the_default_restore(self):
        calls = []

        def restore(session, snapshot):
            calls.append(snapshot)
            session.state = dict(snapshot)

        record = self._record(_Session("lie", save={"hp": 99}, runtime={"dice": 9}))
        self.assertTrue(runtime_recovery.restore_trusted_runtime(record, _snapshot(), restore))
        self.assertEqual(len(calls), 1)

    def test_seam_that_raises_closes_the_session(self):
        def restore(session, snapshot):
            raise OSError("disk")

        record = self._record(_Session("ok"))
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, _snapshot(), restore))
        self.assertIs(record.usable, False)


if __name__ == "__main__":
    unittest.main()
