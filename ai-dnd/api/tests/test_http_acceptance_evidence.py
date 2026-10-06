"""Offline archive contracts; never contact a live campaign or model."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify_bounded_encounter_http.py"
spec = importlib.util.spec_from_file_location("http_acceptance_evidence", SCRIPT)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class HttpEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "http-runs"
        # Any unexpected real-network request fails immediately.
        self.network = patch.object(owner, "urlopen", side_effect=RuntimeError("offline sentinel"))
        self.urlopen = self.network.start()
        self.addCleanup(self.network.stop)
        # Hash real temporary files through the shared algorithm, using only
        # read-only Git-command fixtures. Never modify this repository's source.
        (self.root / "verifier.py").write_text("# offline verifier fixture\n")
        self.git = patch.object(owner.suite_evidence.subprocess, "check_output",
                                side_effect=self.fixture_git)
        self.git.start()
        self.addCleanup(self.git.stop)

    def fixture_git(self, argv, **kwargs):
        if "ls-files" in argv:
            paths = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                           if p.is_file() or p.is_symlink())
            return ("\0".join(paths) + "\0").encode()
        if "status" in argv or "diff" in argv:
            return b""
        if argv[-1] == "--show-toplevel":
            return str(self.root).encode()
        if argv[-1] == "HEAD":
            return b"1111111111111111111111111111111111111111"
        raise AssertionError(f"Unexpected Git fixture call: {argv}")

    def run_attempt(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return owner.run("http://offline.invalid", "http://offline.invalid",
                             archive_root=self.archive, **kwargs)

    def records(self):
        return [json.loads(path.read_text()) for path in sorted(self.archive.glob("*/run.json"))]

    def assert_record(self, record, status, code):
        self.assertEqual(record["status"], status)
        self.assertEqual(record["exit_status"], code)
        self.assertEqual(record["run_label"], "NEW RUN")
        self.assertEqual(record["evidence_kind"], "http_acceptance")
        self.assertFalse(record["historical_certification"])
        self.assertEqual(record["command"]["argv"], sys.orig_argv)
        self.assertLessEqual(record["started_at"], record["ended_at"])
        self.assertNotIn("selected_test_ids", record)

    def test_success_and_repeated_runs_are_unique(self):
        with patch.object(owner, "execute") as execute:
            self.assertEqual(self.run_attempt(), 0)
            first_path = next(self.archive.glob("*/run.json"))
            first_bytes = first_path.read_bytes()
            self.assertEqual(self.run_attempt(), 0)
            self.assertEqual(execute.call_count, 2)
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["run_id"], records[1]["run_id"])
        self.assertEqual(first_bytes, first_path.read_bytes())
        for record in records:
            self.assert_record(record, "PASS", 0)
        self.urlopen.assert_not_called()

    def test_network_failure_retained_before_campaign_creation(self):
        self.assertEqual(self.run_attempt(), 2)
        record = self.records()[0]
        self.assert_record(record, "FAIL", 2)
        self.assertEqual(record["error"]["message"], "offline sentinel")
        self.assertNotIn("campaign_id", record)
        self.assertEqual(record["requests"][0]["status"], "FAIL")
        self.assertIsNotNone(record["requests"][0]["ended_at"])

    def test_complete_scenario_success_preserves_acceptance_details(self):
        seen = {"statblock_id": "mm2024.commoner", "distance_ft": 60,
                "source": "printed p.77", "npc_id": "commoner"}
        scenario = {"visible_opponent": seen}
        entered = {"state": {"combat": {"active": False}, "bounded_encounter": scenario}}
        budget = {"movement_used": 55, "dash_count": 1, "base_action_spent": True}
        near = dict(seen, distance_ft=5, node_id="courtyard_near")
        state = {
            "combat": {"active": True, "combat_id": "c", "round": 1,
                       "current_turn_index": 0,
                       "action_economy": {"actors": {"commoner": budget}}},
            "bounded_encounter": {"visible_opponent": near},
        }
        dash = {"action": "monster_dash"}
        started = {"state": state, "events": [dash]}
        attack = {"action": "enemy_attack", "target_id": "player",
                  "weapon_id": "commoner_club", "attack_bonus": 2,
                  "damage_type": "bludgeoning"}
        attacked = {"state": state, "events": [attack], "session_id": "fixture-session"}
        replay = dict(attacked, session_id="resumed-fixture")
        replies = [
            {"settings": [{"setting_id": "s", "regions": [{
                "region_pack_id": "p", "region_id": "r",
                "starting_locations": [{"entity_id": "l"}]}]}]},
            {"campaign_id": "disposable-fixture", "session_id": "fixture-session"},
            entered, started, state, attacked, {},
            {"state": state, "session_id": "resumed-fixture"},
            {"history": ["unchanged"]}, replay, state, {"history": ["unchanged"]},
        ]

        class Response(io.StringIO):
            status = 200

        self.urlopen.side_effect = [Response(json.dumps(reply)) for reply in replies]
        self.assertEqual(self.run_attempt(), 0)
        record = self.records()[0]
        self.assert_record(record, "PASS", 0)
        self.assertEqual(record["scenario"], scenario)
        self.assertEqual(record["movement"]["result"], dash)
        self.assertEqual(record["attack"], attack)
        self.assertEqual(record["replay_response"], replay)
        for field in ("save", "resume", "replay"):
            self.assertEqual(record[field], "PASS")
        self.assertEqual(len(record["turns"]), 3)
        self.assertEqual(len(record["requests"]), len(replies))

    def test_assertion_failure_keeps_campaign_and_turn_response(self):
        replies = [
            {"settings": [{"setting_id": "s", "regions": [{
                "region_pack_id": "p", "region_id": "r",
                "starting_locations": [{"entity_id": "l"}]}]}]},
            {"campaign_id": "disposable-fixture", "session_id": "fixture-session"},
            {"state": {"combat": {"active": True}}},
        ]

        class Response(io.StringIO):
            status = 200

        self.urlopen.side_effect = [Response(json.dumps(reply)) for reply in replies]
        self.assertEqual(self.run_attempt(), 1)
        record = self.records()[0]
        self.assert_record(record, "FAIL", 1)
        self.assertEqual(record["campaign_id"], "disposable-fixture")
        self.assertEqual(record["turns"][0]["response"], replies[-1])
        self.assertEqual(record["error"]["type"], "AssertionError")

    def test_existing_output_refused_before_network_and_preserved(self):
        output = self.root / "old.json"
        output.write_bytes(b"original evidence\n")
        self.assertEqual(self.run_attempt(output=output), 2)
        self.assertEqual(output.read_bytes(), b"original evidence\n")
        self.assert_record(self.records()[0], "FAIL", 2)
        self.assertEqual(self.records()[0]["error"]["type"], "FileExistsError")
        self.urlopen.assert_not_called()

    def test_new_output_is_exclusive_export_and_failed_record_matches(self):
        output = self.root / "new.json"
        self.assertEqual(self.run_attempt(output=output), 2)
        original = output.read_bytes()
        self.assertEqual(json.loads(original), self.records()[0])
        self.assertEqual(self.run_attempt(output=output), 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.urlopen.call_count, 1)

    def test_export_finalization_failure_is_not_reported_as_pass(self):
        output = self.root / "export.json"
        dump = json.dump

        def failing_dump(record, stream, **kwargs):
            if stream.name == str(output) and record["status"] == "PASS":
                raise OSError("offline export write failure")
            return dump(record, stream, **kwargs)

        with patch.object(owner, "execute"), patch.object(owner.json, "dump", failing_dump):
            self.assertEqual(self.run_attempt(output=output), 2)
        record = self.records()[0]
        self.assert_record(record, "FAIL", 2)
        self.assertEqual(record["export_error"]["message"], "offline export write failure")

    def test_historical_and_suite_destinations_are_rejected(self):
        historical_bytes = owner.HISTORICAL.read_bytes()
        for output in (owner.HISTORICAL, owner.SUITE_ARCHIVE / "forbidden.json"):
            self.assertEqual(self.run_attempt(output=output), 2)
        self.assertEqual(owner.HISTORICAL.read_bytes(), historical_bytes)
        self.assertEqual(len(self.records()), 2)
        self.urlopen.assert_not_called()

    def test_symlink_to_suite_directory_is_rejected(self):
        link = self.root / "suite-link"
        link.symlink_to(owner.SUITE_ARCHIVE, target_is_directory=True)
        with self.assertRaises(ValueError):
            owner.run("http://offline.invalid", "http://offline.invalid", archive_root=link)
        self.assertEqual(self.run_attempt(output=link / "forbidden.json"), 2)
        self.urlopen.assert_not_called()

    def test_keyboard_interrupt_retains_partial_attempt(self):
        with patch.object(owner, "execute", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_attempt(), 130)
        self.assert_record(self.records()[0], "INTERRUPTED", 130)
        self.urlopen.assert_not_called()

    def signal_fixture(self, signum):
        code = """
import importlib.util, os, signal, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("http_fixture", sys.argv[1])
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
def offline(base, resume_base, record, checkpoint):
    record["campaign_id"] = "offline-signal-fixture"
    checkpoint()
    os.kill(os.getpid(), int(sys.argv[3]))
owner.execute = offline
sys.exit(owner.run("http://offline.invalid", "http://offline.invalid",
                   archive_root=Path(sys.argv[2])))
"""
        command = [sys.executable, "-c", code, str(SCRIPT), str(self.archive), str(signum)]
        # Include fresh interpreter startup and both full-tree source fingerprints.
        # The assertion still requires an actual signal, never a timeout/PASS repair.
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        record = self.records()[0]
        self.assertEqual(record["command"]["argv"], command)
        self.assertEqual(record["campaign_id"], "offline-signal-fixture")
        return process, record

    def test_sigterm_has_end_time_and_actual_exit_status(self):
        process, record = self.signal_fixture(signal.SIGTERM)
        self.assertEqual(process.returncode, 143, process.stderr)
        self.assertEqual(record["status"], "INTERRUPTED")
        self.assertEqual(record["exit_status"], process.returncode)
        self.assertIsNotNone(record["ended_at"])

    def test_hard_kill_leaves_identifiable_incomplete_record_never_pass(self):
        process, record = self.signal_fixture(signal.SIGKILL)
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertEqual(record["status"], "RUNNING")
        self.assertIsNone(record["exit_status"])
        self.assertIsNone(record["ended_at"])
        self.assertEqual(record["run_label"], "NEW RUN")
        self.assertIsNotNone(record["verifier_source"]["before"])
        self.assertIsNone(record["verifier_source"]["after"])
        self.assertIsNone(record["source_change_detection"]["changed"])
        self.assertFalse(record["source_change_detection"]["unchanged_verifier_source"])

    def test_shared_verifier_fingerprint_manifest_is_deterministic(self):
        before = owner.capture_verifier_source(self.archive, None)
        after = owner.capture_verifier_source(self.archive, None)
        self.assertEqual(before["algorithm"], "sha256")
        self.assertEqual(before["fingerprint"], after["fingerprint"])
        self.assertEqual(before["fingerprint"], before["working_tree_sha256"])
        self.assertEqual(before["identity_scope"], "local_verifier_checkout_only")
        self.assertEqual([f["path"] for f in before["files"]], ["verifier.py"])
        self.assertEqual(before["files"][0]["sha256"],
                         hashlib.sha256((self.root / "verifier.py").read_bytes()).hexdigest())
        canonical = {"files": before["files"], "index_diff_sha256": before["index_diff_sha256"]}
        self.assertEqual(before["fingerprint"], hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest())

    def test_before_after_are_checkpointed_and_unchanged_is_explicit(self):
        def offline(base, resume, record, checkpoint):
            stored = self.records()[0]
            self.assertIsNotNone(stored["verifier_source"]["before"])
            self.assertIsNone(stored["verifier_source"]["after"])
            self.assertFalse(stored["source_change_detection"]["unchanged_verifier_source"])
        with patch.object(owner, "execute", side_effect=offline):
            self.assertEqual(self.run_attempt(), 0)
        record = self.records()[0]
        before, after = record["verifier_source"]["before"], record["verifier_source"]["after"]
        self.assertEqual(before["fingerprint"], after["fingerprint"])
        self.assertLessEqual(before["captured_at"], after["captured_at"])
        self.assertEqual(record["source_change_detection"],
                         {"changed": False, "status": "unchanged", "unchanged_verifier_source": True})

    def test_source_modification_during_acceptance_preserves_both_fingerprints(self):
        def offline(*args):
            (self.root / "verifier.py").write_text("# modified offline source\n")
        with patch.object(owner, "execute", side_effect=offline):
            self.assertEqual(self.run_attempt(), 0)
        record = self.records()[0]
        self.assertNotEqual(record["verifier_source"]["before"]["fingerprint"],
                            record["verifier_source"]["after"]["fingerprint"])
        self.assertEqual(record["status"], "PASS")  # Acceptance is retained, not source certification.
        self.assertEqual(record["source_change_detection"],
                         {"changed": True, "status": "changed", "unchanged_verifier_source": False})

    def test_server_identity_is_unverified_even_for_localhost(self):
        with patch.object(owner, "execute"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(owner.run("http://localhost:8000", "http://localhost:8008",
                                       archive_root=self.archive), 0)
        record = self.records()[0]
        for role, endpoint in (("acceptance", "http://localhost:8000"),
                               ("resume", "http://localhost:8008")):
            server = record["server_source_identity"][role]
            self.assertEqual(server["endpoint"], endpoint)
            self.assertEqual(server["status"], "unverified")
            self.assertIsNone(server["revision"])
            self.assertIsNone(server["fingerprint"])
            self.assertNotEqual(server["revision"], record["verifier_source"]["before"]["revision"])
        self.urlopen.assert_not_called()

    def test_generated_archives_and_export_do_not_change_fingerprint(self):
        default = self.root / "default-http-runs"
        default.mkdir()
        (default / "old.json").write_text('{"historical": true}\n')
        export = self.root / "export.json"
        with patch.object(owner, "DEFAULT_ARCHIVE", default), patch.object(owner, "execute"):
            self.assertEqual(self.run_attempt(output=export), 0)
        record = self.records()[0]
        self.assertFalse(record["source_change_detection"]["changed"])
        self.assertEqual([f["path"] for f in record["verifier_source"]["before"]["files"]],
                         ["verifier.py"])
        self.assertEqual(json.loads(export.read_text()), record)

    def test_failure_and_interrupt_preserve_source_and_unknown_server_identity(self):
        for failure, code in ((RuntimeError("offline failure"), 2), (KeyboardInterrupt(), 130)):
            with patch.object(owner, "execute", side_effect=failure):
                self.assertEqual(self.run_attempt(), code)
        for record in self.records():
            self.assertIsNotNone(record["verifier_source"]["before"])
            self.assertIsNotNone(record["verifier_source"]["after"])
            self.assertFalse(record["source_change_detection"]["changed"])
            self.assertEqual(record["server_source_identity"]["acceptance"]["status"], "unverified")
        self.urlopen.assert_not_called()

    def test_capture_failure_never_claims_unchanged_or_success(self):
        actual = owner.capture_verifier_source
        with patch.object(owner, "execute") as execute, patch.object(
            owner, "capture_verifier_source",
            side_effect=[RuntimeError("before unavailable"), actual(self.archive, None)],
        ):
            self.assertEqual(self.run_attempt(), 2)
            execute.assert_not_called()
        first = self.records()[0]
        self.assertIn("before", first["verifier_source"]["capture_errors"])
        self.assertFalse(first["source_change_detection"]["unchanged_verifier_source"])
        with patch.object(owner, "execute"), patch.object(
            owner, "capture_verifier_source",
            side_effect=[actual(self.archive, None), RuntimeError("after unavailable")],
        ):
            self.assertEqual(self.run_attempt(), 2)
        after_failure = next(r for r in self.records()
                             if "after" in r["verifier_source"]["capture_errors"])
        self.assertIsNone(after_failure["source_change_detection"]["changed"])
        self.assertFalse(after_failure["source_change_detection"]["unchanged_verifier_source"])


if __name__ == "__main__":
    unittest.main()