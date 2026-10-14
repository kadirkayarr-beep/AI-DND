"""Offline checks for smoke timeout diagnostics. No live model calls."""

from __future__ import annotations

import contextvars
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

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

    def test_provider_exception_survives_failure_evidence_disk_error(self):
        original_error = TimeoutError("private provider detail")

        def original(**_kwargs):
            raise original_error

        engine = _Engine(original)
        telemetry._install_telemetry(engine)
        with patch.object(telemetry, "_flush_diagnostic", side_effect=[None, OSError("disk")]):
            with self.assertRaises(TimeoutError) as raised:
                engine.ollama.chat(messages=[])
        self.assertIs(raised.exception, original_error)

    def test_completion_disk_error_preserves_success_without_retry(self):
        response = {"eval_count": 1}
        engine = _Engine(lambda **_kwargs: response)
        telemetry._install_telemetry(engine)
        token = telemetry._REQUEST_TELEMETRY.set([])
        self.addCleanup(lambda: telemetry._REQUEST_TELEMETRY.reset(token))
        with patch.object(telemetry, "_flush_diagnostic", side_effect=[None, OSError("disk")]):
            self.assertIs(engine.ollama.chat(messages=[]), response)
        rows = telemetry._REQUEST_TELEMETRY.get()
        self.assertEqual(sum(row["kind"] == "model_attempt" for row in rows), 1)
        self.assertEqual(sum(row["kind"] == "model" for row in rows), 1)
        self.assertFalse(telemetry._diagnostic_evidence_complete(rows))

    def test_arbitrary_prose_and_credentials_are_not_diagnostic_metadata(self):
        row = telemetry._diagnostic_projection({
            "event": "model_attempt", "phase": "failed", "attempt_index": 1,
            "narration": "private narration", "messages": [{"content": "private input"}],
            "unexpected": "Bearer secret", "error_type": "private exception text",
            "detail": "private provider text",
        })
        self.assertEqual(row, {
            "event": "model_attempt", "phase": "failed", "attempt_index": 1,
            "error_type": "Exception", "detail": "sensitive detail redacted",
        })


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
        self.addCleanup(path.parent.rmdir)
        self.addCleanup(path.unlink)
        self.assertNotIn(Path(directory.name), path.parents)
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
        self.addCleanup(private.rmdir)
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
        self.assertEqual(result, {"rollback": "rollback doğrulanamadı", "reason": "unreachable"})

    def test_matching_counter_is_not_full_rollback_evidence(self):
        response = SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"turn_index": 18, "narration": "private narration"},
        )
        with patch.object(telemetry.httpx, "Client") as client:
            client.return_value.__enter__.return_value.get.return_value = response
            result = telemetry.probe_rollback_status("http://127.0.0.1:9", "synthetic", 18)
        self.assertEqual(result, {
            "rollback": "rollback doğrulanamadı", "turn_index_unchanged": True,
        })

    def test_checkpoint_rejects_configured_secret_in_messages(self):
        record = self._record()
        record.game_session.messages.append({"role": "user", "content": "synthetic-secret"})
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"OLLAMA_PROXY_TOKEN": "synthetic-secret"}):
                with self.assertRaises(telemetry.SmokeReplayError):
                    telemetry.write_replay_checkpoint(record, Path(directory))

    def test_capture_roundtrip_is_called_at_the_turn_boundary(self):
        record = self._record()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(telemetry, "private_replay_directory", return_value=Path(directory)):
                engine = _Engine(lambda: None)
                captured = []
                def before_turn(session):
                    self.assertIs(session, record.game_session)
                    captured.append(telemetry._capture_replay_checkpoint(record, Path("unused")))
                telemetry._install_telemetry(engine, before_turn=before_turn)
                original = record.game_session.serialize_game_state()
                engine.GameSession.run_player_turn(record.game_session, "synthetic")
                self.assertEqual(record.game_session.serialize_game_state(), original)
                self.assertEqual(len(captured), 1)
                self.assertFalse(captured[0].exists())

    def test_retention_requires_explicit_caller_ownership(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "owned"
            directory.mkdir()
            sibling = Path(root) / "preserve.txt"
            sibling.write_text("synthetic", encoding="utf-8")
            with patch.object(telemetry, "private_replay_directory", return_value=directory):
                path = telemetry._capture_replay_checkpoint(self._record(), Path(root), retain=True)
            self.assertTrue(path.exists())
            self.assertTrue(telemetry._cleanup_replay_path(path, directory=directory))
            self.assertTrue(sibling.exists())

    def test_cleanup_failure_preserves_original_restore_exception(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "owned"
            directory.mkdir()
            original = ValueError("original restore failure")
            rows = []
            token = telemetry._REQUEST_TELEMETRY.set(rows)
            self.addCleanup(telemetry._REQUEST_TELEMETRY.reset, token)
            with patch.object(telemetry, "private_replay_directory", return_value=directory), \
                 patch.object(telemetry, "restore_replay_checkpoint", side_effect=original), \
                 patch.object(Path, "rmdir", side_effect=PermissionError("cleanup")):
                with self.assertRaises(ValueError) as caught:
                    telemetry._capture_replay_checkpoint(self._record(), Path(root))
            self.assertIs(caught.exception, original)
            self.assertFalse(telemetry._diagnostic_evidence_complete(rows))
            self.assertFalse((directory / "checkpoint.json").exists())

    def test_successful_restore_with_cleanup_failure_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "owned"
            directory.mkdir()
            with patch.object(telemetry, "private_replay_directory", return_value=directory), \
                 patch.object(Path, "rmdir", side_effect=PermissionError("cleanup")):
                with self.assertRaisesRegex(telemetry.SmokeReplayError, "evidence incomplete"):
                    telemetry._capture_replay_checkpoint(self._record(), Path(root))

    def test_checkpoint_serialization_failure_allocates_no_private_directory(self):
        record = self._record()
        record.combat_history = [object()]
        with patch.object(telemetry, "private_replay_directory") as allocate:
            with self.assertRaises(TypeError):
                telemetry.write_replay_checkpoint(record, Path("unused"))
        allocate.assert_not_called()

    def test_checkpoint_disk_failure_removes_only_owned_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "owned"
            directory.mkdir()
            sibling = Path(parent) / "preserve.txt"
            sibling.write_text("synthetic", encoding="utf-8")
            with patch.object(telemetry, "private_replay_directory", return_value=directory):
                with patch.object(Path, "open", side_effect=OSError("synthetic disk failure")):
                    with self.assertRaises(OSError):
                        telemetry.write_replay_checkpoint(self._record(), Path(parent))
            self.assertFalse(directory.exists())
            self.assertEqual(sibling.read_text(encoding="utf-8"), "synthetic")

    def test_checkpoint_copy_disk_failure_removes_created_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(telemetry, "private_replay_directory", return_value=Path(directory)):
                source = telemetry.write_replay_checkpoint(self._record(), Path("unused"))
            before = source.read_bytes()
            created = []
            original = tempfile.NamedTemporaryFile
            def failing_file(**kwargs):
                handle = original(**kwargs, dir=directory)
                created.append(Path(handle.name))
                handle.write = lambda _: (_ for _ in ()).throw(OSError("synthetic disk"))
                return handle
            with patch.object(telemetry.tempfile, "NamedTemporaryFile", side_effect=failing_file):
                with self.assertRaises(OSError):
                    telemetry.load_replay_checkpoint_copy(source)
            self.assertTrue(created)
            self.assertTrue(all(not path.exists() for path in created))
            self.assertEqual(source.read_bytes(), before)


class HarnessIntegrationTests(unittest.TestCase):
    def test_started_fsync_failure_blocks_provider_and_marks_evidence_incomplete(self):
        calls = []
        engine = _Engine(lambda **kwargs: calls.append(kwargs))
        telemetry._install_telemetry(engine)
        token = telemetry._REQUEST_TELEMETRY.set([])
        self.addCleanup(lambda: telemetry._REQUEST_TELEMETRY.reset(token))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(telemetry, "_SMOKE_DIAGNOSTIC_PATH", Path(directory) / "events.jsonl"):
                with patch.object(telemetry.os, "fsync", side_effect=OSError("synthetic fsync")):
                    with self.assertRaises(OSError):
                        engine.ollama.chat(messages=[])
        self.assertEqual(calls, [])
        self.assertEqual(telemetry._attempt_count(telemetry._telemetry()), 0)
        self.assertFalse(telemetry._diagnostic_evidence_complete(telemetry._telemetry()))

    def test_failed_calls_count_and_requests_have_distinct_safe_correlation(self):
        engine = _Engine(lambda **_: (_ for _ in ()).throw(TimeoutError("secret")))
        telemetry._install_telemetry(engine)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            with patch.object(telemetry, "_SMOKE_DIAGNOSTIC_PATH", path):
                for identifier in ("a" * 32, "b" * 32):
                    token = telemetry._REQUEST_TELEMETRY.set([])
                    request = telemetry._REQUEST_DIAGNOSTIC_ID.set(identifier)
                    try:
                        for _ in range(3):
                            with self.assertRaises(TimeoutError):
                                engine.ollama.chat(messages=[])
                        self.assertEqual(telemetry._attempt_count(telemetry._telemetry()), 3)
                        self.assertGreater(telemetry._attempt_count(telemetry._telemetry()), telemetry.MAX_MODEL_CALLS_PER_TURN)
                    finally:
                        telemetry._REQUEST_DIAGNOSTIC_ID.reset(request)
                        telemetry._REQUEST_TELEMETRY.reset(token)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["request_id"] for row in rows}, {"a" * 32, "b" * 32})
            self.assertEqual(len({row["run_id"] for row in rows}), 1)
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    def test_parent_timeout_uses_authorized_client_and_keeps_first_failure(self):
        def transport(request):
            self.assertEqual(request.headers["Authorization"], "Bearer synthetic-test-token")
            return httpx.Response(200, json={"turn_index": 18})
        original = httpx.ReadTimeout("sensitive detail")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(transport), headers={"Authorization": "Bearer synthetic-test-token"}) as client:
                with patch.object(telemetry, "_turn", side_effect=original):
                    with self.assertRaises(httpx.ReadTimeout) as raised:
                        telemetry._turn_with_evidence(client, "http://test", "synthetic", "private input", None, root, root / "audit", 18)
                self.assertIs(raised.exception, original)
                telemetry._record_parent_failure(root, "harness", RuntimeError("later"))
            text = (root / "failure-evidence.json").read_text(encoding="utf-8")
            saved = json.loads(text)
            self.assertEqual(saved["event"], "parent_http")
            self.assertEqual(saved["error_type"], "ReadTimeout")
            self.assertTrue(saved["turn_index_unchanged"])
            self.assertNotIn("synthetic-test-token", text)
            self.assertNotIn("private input", text)

    def test_stale_audit_is_rejected_and_http_correlation_is_not_a_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = root / "audit.jsonl"
            audit.write_text(json.dumps({"request_id": "a" * 32}) + "\n", encoding="utf-8")
            seen = []
            def transport(request):
                if request.method == "POST":
                    seen.append(request.headers["X-AI-DND-Smoke-Request"])
                    return httpx.Response(200, json={})
                return httpx.Response(401)
            with httpx.Client(transport=httpx.MockTransport(transport)) as client:
                with self.assertRaises(telemetry.SmokeFailure):
                    telemetry._turn_with_evidence(client, "http://test", "synthetic", "input", None, root, audit, 0)
            self.assertEqual(len(seen), 1)
            self.assertRegex(seen[0], r"^[0-9a-f]{32}$")
            self.assertNotEqual(seen[0], "a" * 32)

    def test_missing_audit_is_recorded_as_its_own_failure_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401))) as client:
                with patch.object(telemetry, "_turn", return_value={}):
                    with self.assertRaises(FileNotFoundError):
                        telemetry._turn_with_evidence(client, "http://test", "synthetic", "input", None, root, root / "missing", 0)
            row = json.loads((root / "failure-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(row["event"], "isolated_log")
            self.assertEqual(row["reason"], "unauthorized")
            self.assertEqual(row["rollback"], "rollback doğrulanamadı")


class HarnessServerWiringTests(unittest.TestCase):
    def test_real_audit_middleware_captures_checkpoint_before_native_turn(self):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        import logging
        import api.main as main
        import bounded_encounter
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            database = root / "campaign.sqlite3"
            manager = SessionManager(campaign_store=CampaignStore(database))
            app = main.create_app(session_manager=manager, ollama_adapter=None,
                                  authenticator=FixedAuthenticator(TEST_PLAYER))
            stack.enter_context(patch.dict("os.environ", {}))
            stack.enter_context(patch.object(main, "app", app))
            stack.enter_context(patch.object(game, "_playable_v1_telemetry_installed", False, create=True))
            for owner, name in ((game.ollama, "chat"), (game, "validate_world_updates"),
                                (game, "_bind_world_update_mentions"), (game.GameSession, "run_player_turn")):
                stack.enter_context(patch.object(owner, name, getattr(owner, name, None), create=True))
            stack.enter_context(patch.object(game.ollama, "chat", side_effect=AssertionError("No model permitted")))
            stack.enter_context(patch.object(telemetry, "_SMOKE_DIAGNOSTIC_PATH", None))
            stack.enter_context(patch.object(telemetry, "private_replay_directory",
                                             side_effect=lambda _: Path(tempfile.mkdtemp(dir=root))))
            capture = stack.enter_context(patch.object(telemetry, "_capture_replay_checkpoint",
                                                       wraps=telemetry._capture_replay_checkpoint))
            logger = logging.getLogger("ai_dnd.api")
            handlers, level = list(logger.handlers), logger.level
            stack.callback(logger.setLevel, level)
            stack.callback(lambda: setattr(logger, "handlers", handlers))
            with patch("uvicorn.run") as run:
                telemetry._serve(1, database, root / "audit.jsonl")
            self.assertIs(run.call_args.args[0], app)
            with TestClient(app) as client:
                settings = client.get("/api/campaign-start-options").json()["settings"][0]
                region = settings["regions"][0]
                created = client.post("/api/campaigns", json={"name": "Synthetic audit wiring", "campaign_start": {
                    "setting_id": settings["setting_id"], "region_pack_id": region["region_pack_id"],
                    "region_id": region["region_id"], "starting_location_id": region["starting_locations"][0]["entity_id"],
                }})
                self.assertEqual(created.status_code, 200)
                sid = created.json()["session_id"]
                response = client.post(f"/api/sessions/{sid}/turn", json={"message": bounded_encounter.ENTER},
                                       headers={"X-AI-DND-Smoke-Request": "c" * 32})
                self.assertEqual(response.status_code, 200)
                from api.auth import current_principal, Principal
                self.assertIsNone(current_principal())
                for variable in (telemetry._REQUEST_TELEMETRY, telemetry._REQUEST_SESSION_ID,
                                 telemetry._REQUEST_DIAGNOSTIC_ID, telemetry._VALIDATION_OUTPUT_CALLS):
                    self.assertIsNone(variable.get())
                app.state.authenticator = FixedAuthenticator(Principal(issuer="other", subject="other"))
                denied = client.post(f"/api/sessions/{sid}/turn", json={"message": bounded_encounter.ENTER})
                self.assertEqual(denied.status_code, 404)
                app.state.authenticator = FixedAuthenticator(TEST_PLAYER)
                resumed = client.post(f"/api/campaigns/{created.json()['campaign_id']}/resume")
                self.assertEqual(resumed.status_code, 200)
                self.assertIsNone(current_principal())
            self.assertEqual(capture.call_count, 1)
            checkpoints = list(root.glob("*/checkpoint.json"))
            self.assertEqual(checkpoints, [])
            rows = [json.loads(line) for line in (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
            row = next(row for row in rows if row.get("request_id") == "c" * 32)
            self.assertEqual(row["request_id"], "c" * 32)
            self.assertEqual(row["observed_model_calls"], 0)
            self.assertTrue(row["diagnostic_evidence_complete"])



def _tuple_state(value):
    if isinstance(value, list):
        return tuple(_tuple_state(item) for item in value)
    return value


if __name__ == "__main__":
    unittest.main()
