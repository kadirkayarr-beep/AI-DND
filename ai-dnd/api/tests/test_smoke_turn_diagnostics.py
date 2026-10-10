"""Offline checks for smoke timeout diagnostics. No live model calls."""

from __future__ import annotations

import contextvars
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import game
from api.campaign_journal import empty_campaign_journal
from api.lore_authority.models import CampaignLoreState
from api.narrative_memory import empty_narrative_memory
from api.tests import live_playable_living_world_v1_smoke as telemetry


class _Engine:
    _playable_v1_telemetry_installed = False
    _ACTIVE_SESSION = contextvars.ContextVar("diag_session", default=None)

    def __init__(self, chat):
        self.ollama = SimpleNamespace(chat=chat)

    @staticmethod
    def validate_world_updates(*_args, **_kwargs):
        return {}

    @staticmethod
    def _bind_world_update_mentions(*_args, **_kwargs):
        return (set(), {})

    @staticmethod
    def run_player_turn(*_args, **_kwargs):
        return {}

    class GameSession:
        def run_player_turn(self, *_args, **_kwargs):
            return {}


class DiagnosticHookTests(unittest.TestCase):
    def test_attempt_is_recorded_before_the_provider_call_and_counts_failures(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "diagnostic-events.jsonl"
        telemetry._SMOKE_DIAGNOSTIC_PATH = path
        self.addCleanup(lambda: setattr(telemetry, "_SMOKE_DIAGNOSTIC_PATH", None))
        seen: list[str] = []

        def original(*_args, **_kwargs):
            seen.append(path.read_text(encoding="utf-8"))
            raise TimeoutError("timed out")

        engine = _Engine(original)
        telemetry._install_telemetry(engine)
        token = telemetry._REQUEST_TELEMETRY.set([])
        self.addCleanup(lambda: telemetry._REQUEST_TELEMETRY.reset(token))
        with self.assertRaises(TimeoutError):
            engine.ollama.chat(messages=[{
                "role": "system",
                "content": "You are a small D&D intent parser. Return JSON only.",
            }])
        self.assertEqual(len(seen), 1)
        self.assertIn('"phase": "started"', seen[0])
        rows = telemetry._REQUEST_TELEMETRY.get()
        self.assertEqual(sum(1 for row in rows if row.get("kind") == "model_attempt"), 1)
        self.assertEqual(sum(1 for row in rows if row.get("kind") == "model"), 0)
        failed = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(failed["phase"], "failed")
        self.assertEqual(failed["error_type"], "TimeoutError")
        self.assertEqual(failed["attempt_index"], 1)

    def test_hook_invokes_the_provider_once(self):
        original_calls = []

        def original(*_args, **_kwargs):
            original_calls.append(1)
            return {"prompt_eval_count": 3, "eval_count": 1}

        fresh = _Engine(original)
        telemetry._install_telemetry(fresh)
        token = telemetry._REQUEST_TELEMETRY.set([])
        self.addCleanup(lambda: telemetry._REQUEST_TELEMETRY.reset(token))
        fresh.ollama.chat(messages=[{"role": "system", "content": "DM"}])
        self.assertEqual(original_calls, [1])

    def test_secret_text_is_not_kept_in_shareable_diagnostics(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "diagnostic-events.jsonl"
        telemetry._SMOKE_DIAGNOSTIC_PATH = path
        self.addCleanup(lambda: setattr(telemetry, "_SMOKE_DIAGNOSTIC_PATH", None))
        telemetry._flush_diagnostic({
            "event": "parent_http",
            "phase": "failed",
            "detail": "Authorization: Bearer local-dev token=secret",
        })
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("Bearer", text)
        self.assertNotIn("token=", text)
        self.assertIn("sensitive detail redacted", text)


class ReplayCheckpointTests(unittest.TestCase):
    def _record(self):
        session = game.create_session(seed=3)
        session.messages.append({"role": "user", "content": "İçeriye bakıyorum."})
        session.world_state["flags"]["turn_index"] = 18
        return SimpleNamespace(
            game_session=session,
            journal=empty_campaign_journal(),
            narrative_memory=empty_narrative_memory(),
            lore_authority=CampaignLoreState.legacy_unbound(),
            combat_history=[],
        )

    def test_replay_uses_a_copy_and_refuses_canonical_saves(self):
        record = self._record()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = telemetry.write_replay_checkpoint(record, Path(directory.name))
        before = path.read_bytes()
        checkpoint = json.loads(before.decode("utf-8"))
        payload = checkpoint["campaign_payload"]
        self.assertEqual(checkpoint["format"], "ai-dnd-smoke-replay-checkpoint")
        for field in ("rng_state", "journal", "narrative_memory", "lore_authority", "engine_save"):
            self.assertIn(field, payload)
        self.assertIn("messages", checkpoint)
        loaded, copy_path = telemetry.load_replay_checkpoint_copy(path)
        self.addCleanup(copy_path.unlink, missing_ok=True)
        restored = game.create_session(seed=9)
        restored_state = telemetry.restore_replay_checkpoint(restored, loaded)
        self.assertEqual(restored.messages, checkpoint["messages"])
        self.assertEqual(restored.rng.getstate(), _tuple_state(payload["rng_state"]))
        self.assertEqual(restored_state["journal"], record.journal)
        self.assertEqual(restored_state["narrative_memory"], payload["narrative_memory"])
        self.assertEqual(restored_state["lore_authority"], payload["lore_authority"])
        self.assertEqual(restored_state["combat_history"], [])
        self.assertIn("world_metadata", payload)
        restored.world_state["flags"]["turn_index"] = 99
        self.assertEqual(path.read_bytes(), before)
        self.assertNotEqual(copy_path, path)
        report = Path(directory.name) / "playable-living-world-v1-1-smokes" / "run"
        private = telemetry.private_replay_directory(report)
        self.assertNotIn("playable-living-world-v1-1-smokes", private.parts)
        canonical = Path(directory.name) / "canonical.json"
        canonical.write_text(json.dumps({"format": "ai-dnd-save", "version": 3}), encoding="utf-8")
        with self.assertRaises(telemetry.SmokeReplayError):
            telemetry.load_replay_checkpoint_copy(canonical)
        campaign = Path(directory.name) / "campaign.json"
        campaign.write_text(json.dumps({"format": "ai-dnd-campaign", "version": 1}), encoding="utf-8")
        with self.assertRaises(telemetry.SmokeReplayError):
            telemetry.load_replay_checkpoint_copy(campaign)

    def test_later_failure_note_keeps_the_original_stage(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        telemetry.write_failure_evidence(root, {
            "event": "parent_http",
            "phase": "failed",
            "error_type": "TimeoutError",
            "rollback": "rollback doğrulanamadı",
        })
        telemetry.write_failure_evidence(root, {
            "event": "isolated_log",
            "phase": "unavailable",
            "detail": "Authorization: Bearer local-dev token=secret",
            "rollback": "rollback doğrulanamadı",
        })
        text = (root / "failure-evidence.json").read_text(encoding="utf-8")
        saved = json.loads(text)
        self.assertEqual(saved["event"], "parent_http")
        self.assertEqual(saved["error_type"], "TimeoutError")
        self.assertEqual(saved["rollback"], "rollback doğrulanamadı")
        self.assertNotIn("Bearer", text)
        self.assertNotIn("token=", text)

    def test_unresponsive_api_leaves_rollback_unverified(self):
        result = telemetry.probe_rollback_status(
            "http://127.0.0.1:9", "missing-session", 18,
        )
        self.assertEqual(result, {"rollback": "rollback doğrulanamadı"})


def _tuple_state(value):
    if isinstance(value, list):
        return tuple(_tuple_state(item) for item in value)
    return value


if __name__ == "__main__":
    unittest.main()
