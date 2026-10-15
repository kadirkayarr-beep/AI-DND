"""Synthetic F03 faults: isolated subprocess, test auth, no real model calls.

No fault HTTP routes are installed. A private file selects test-only faults.
"""
import copy
from contextlib import closing
import dataclasses
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import httpx


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(value, default=str), encoding="utf-8")
    pending.replace(path)


def serve(folder, port):
    import game
    import uvicorn
    from api.auth import FixedAuthenticator
    from api.tests.auth_fixture import TEST_PLAYER
    from api.main import create_app
    from api.ollama_adapter import AuthenticatedOllamaAdapter
    from api.persistence.campaign_store import CampaignStore
    from api.session_manager import SessionManager

    control = lambda: read(folder / "control.json")
    counts = {"synthetic_model_attempts": 0, "real_model_calls": 0}

    class FailedProvider:
        def list(self):
            return {"models": [{"model": "qwen3:8b"}]}

        def chat(self, *args, **kwargs):
            counts["synthetic_model_attempts"] += 1
            raise RuntimeError("synthetic disconnected provider")

    adapter = AuthenticatedOllamaAdapter(FailedProvider())
    adapter.install_for_engine()
    store = CampaignStore(folder / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
    manager = SessionManager(campaign_store=store)
    if (folder / "campaign.json").exists():
        cid = read(folder / "campaign.json")["campaign_id"]
        sid, record, *_ = manager.resume_campaign(cid)
    else:
        cid, sid, record, *_ = manager.create_campaign(name="Synthetic F03 fault chain")
        session = record.game_session
        session.commit_location_change("tavern")
        session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
        session.initialize_species_trait_state()
        session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
        manager.save_campaign(cid)
        write(folder / "campaign.json", {"campaign_id": cid})
    session = record.game_session
    original_restore = session._restore_runtime_snapshot

    def restore(snapshot):
        if control()["mode"] == "restore_failure":
            raise RuntimeError("synthetic failed runtime restoration")
        return original_restore(snapshot)

    session._restore_runtime_snapshot = restore

    def snapshot():
        with closing(sqlite3.connect(f"file:{store.path.as_posix()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = {table: [dict(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
                    for table in ("campaign_turn_actions", "campaign_emergence_attempts")}
        return json.loads(json.dumps({
            "engine_save": session.serialize_game_state(), "rng": session.rng.getstate(),
            "messages": session.messages, "world_metadata": session.world_metadata,
            "journal": record.journal, "narrative_memory": record.narrative_memory,
            "lore": record.lore_authority.to_dict(), "combat_history": record.combat_history,
            "receipts": record.turn_action_receipts,
            "persisted": dataclasses.asdict(store.get_campaign(cid)), "sql_rows": rows,
        }, default=str))

    app = create_app(session_manager=manager, ollama_adapter=adapter,
                     authenticator=FixedAuthenticator(TEST_PLAYER))

    @app.middleware("http")
    async def audit(request, call_next):
        response = await call_next(request)
        if request.url.path != "/api/health":
            state = control()
            observation = {
                "pid": os.getpid(), "usable": record.usable,
                "status": response.status_code, "counts": counts, "snapshot": snapshot()}
            # A stage can contain several requests (read, retry, receipt replay).
            # Keep every observation immutable and retain the first stage image.
            # Exclusive creation fails closed instead of replacing old evidence.
            observation_path = folder / f"{state['stage']}-{os.getpid()}-{uuid4().hex}.json"
            with observation_path.open("x", encoding="utf-8") as output:
                json.dump(observation, output, default=str)
            try:
                with (folder / (state["stage"] + ".json")).open("x", encoding="utf-8") as output:
                    json.dump(observation, output, default=str)
            except FileExistsError:
                pass  # The named stage is its first observation, never the latest.

        return response

    write(folder / "boot.json", {"pid": os.getpid(), "session_id": sid,
                                "campaign_id": cid, "snapshot": snapshot()})
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error", access_log=False)


class F03FaultChains(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-dnd-f03-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.client = httpx.Client(trust_env=False, timeout=15)
        self.addCleanup(self.client.close)
        self.process = None
        self.logs = []
        self.addCleanup(self.stop)
        self.control("normal", "baseline")
        self.start()

    def control(self, mode, stage):
        write(self.folder / "control.json", {"mode": mode, "stage": stage})

    def start(self):
        log = (self.folder / f"process-{len(self.logs)}.log").open("w", encoding="utf-8")
        self.logs.append(log)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("OLLAMA_", "AI_DND_", "REPLIT_")):
                env.pop(key)
        env["PYTHONUTF8"] = "1"
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--serve", str(self.folder), str(self.port)],
            cwd=ROOT, env=env, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(100):
            self.assertIsNone(self.process.poll(), "isolated child exited")
            try:
                if self.client.get(self.url + "/api/health").status_code == 200:
                    self.boot = read(self.folder / "boot.json")
                    self.sid, self.cid = self.boot["session_id"], self.boot["campaign_id"]
                    self.assertEqual(self.boot["pid"], self.process.pid)
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        self.fail("isolated child readiness timeout")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)
        for log in self.logs:
            log.close()

    def state(self, stage):
        self.control("normal", stage)
        response = self.client.get(f"{self.url}/api/sessions/{self.sid}/state")
        self.assertEqual(response.status_code, 200, response.text)
        return read(self.folder / f"{stage}.json")["snapshot"]

    def receipt_fault(self, enabled):
        with closing(sqlite3.connect(self.folder / "campaigns.sqlite3")) as db:
            db.execute("CREATE TRIGGER synthetic_f03_receipt BEFORE INSERT ON campaign_turn_actions BEGIN SELECT RAISE(ABORT, 'synthetic receipt failure'); END" if enabled
                       else "DROP TRIGGER synthetic_f03_receipt")

    def rest(self, body):
        return self.client.post(f"{self.url}/api/game/sessions/{self.sid}/species-actions", json=body)

    def evidence(self, name, result):
        destination = os.environ.get("F03_EVIDENCE_DIR")
        if destination:
            import hashlib
            result.update(synthetic=True, auth="FixedAuthenticator(TEST_PLAYER), not real auth",
                          api_port=self.port, real_model_calls=0)
            write(Path(destination) / (name + ".json"), result)
            for path in self.folder.glob("*.json"):
                # Synthetic-only raw snapshots support full comparisons, not live provenance.
                target = Path(destination) / (name + "-" + path.name)
                target.write_bytes(path.read_bytes())

    def test_save_rollback_component_recovery_retry_once(self):
        before = self.state("save-before")
        self.receipt_fault(True)
        config = {"url": self.url, "sid": self.sid, "cid": self.cid,
                  "folder": str(self.folder), "python": sys.executable, "action": "long_rest"}
        write(self.folder / "ui-config.json", config)
        env = os.environ.copy()
        env["F03_FAULT_UI_CONFIG"] = str(self.folder / "ui-config.json")
        node = os.environ.get("F03_NODE", "node")
        completed = subprocess.run([node, "--experimental-strip-types", "--test",
                                    "--test-name-pattern=F03 synthetic real HTTP", "tests/turn-reconciliation.test.mjs"],
                                   cwd=ROOT.parent / "artifacts/ai-dnd-experience", env=env,
                                   capture_output=True, text=True, timeout=40)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        failed = read(self.folder / "ui-save-failed.json")
        self.assertEqual(failed["snapshot"], before)
        self.assertTrue(failed["usable"])
        self.assertEqual(failed["counts"]["synthetic_model_attempts"], 0)
        ui = read(self.folder / "ui-result.json")
        self.assertEqual(ui["failed_status"], 503)
        self.assertEqual(ui["retry_status"], 200)
        committed = self.state("save-committed")
        self.assertEqual(len(committed["sql_rows"]["campaign_turn_actions"]), 1)
        self.assertEqual(len(committed["persisted"]["history"]), len(before["persisted"]["history"]) + 1)
        replay = self.rest(ui["request"])
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), ui["response"])
        self.assertEqual(self.state("save-replayed"), committed)
        self.evidence("F03-AC004-save-ui-retry", {"ui": ui, "full_rollback_equal": True,
                      "full_replay_equal": True, "receipt_count": 1, "component_stdout": completed.stdout})

    def test_restore_failure_real_restart_and_precommit_outage(self):
        before = self.state("restore-before")
        command = {"action": "long_rest", "action_id": str(uuid4())}
        self.receipt_fault(True)
        self.control("restore_failure", "restore-failed")
        failure = self.rest(command)
        self.assertEqual(failure.status_code, 409, failure.text)
        self.assertEqual(failure.json()["detail"]["code"], "session_restore_failed")
        failed = read(self.folder / "restore-failed.json")
        self.assertFalse(failed["usable"])
        self.assertEqual(failed["snapshot"]["persisted"], before["persisted"])
        self.assertEqual(failed["snapshot"]["sql_rows"], before["sql_rows"])
        self.assertEqual(self.rest(command).status_code, 409)
        old_pid = self.process.pid
        self.stop()
        self.receipt_fault(False)
        # No server is listening: an uncommitted request cannot mutate storage.
        db_before = (self.folder / "campaigns.sqlite3").read_bytes()
        with self.assertRaises(httpx.TransportError):
            self.rest(command)
        self.assertEqual((self.folder / "campaigns.sqlite3").read_bytes(), db_before)
        self.control("normal", "restarted")
        self.start()
        self.assertNotEqual(self.process.pid, old_pid)
        recovered = self.state("restore-recovered")
        # resume_campaign intentionally updates only last_played_at metadata.
        # Preserve and report it separately; all other values must match exactly.
        previous_played = before["persisted"]["metadata"]["last_played_at"]
        resumed_played = recovered["persisted"]["metadata"]["last_played_at"]
        self.assertGreaterEqual(resumed_played, previous_played)
        expected_recovered = copy.deepcopy(before)
        expected_recovered["persisted"]["metadata"]["last_played_at"] = resumed_played
        self.assertEqual(recovered, expected_recovered)
        accepted = self.rest(command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        committed = self.state("restore-committed")
        self.assertEqual(len(committed["sql_rows"]["campaign_turn_actions"]), 1)
        self.assertEqual(self.rest(command).json(), accepted.json())
        self.assertEqual(self.state("restore-replayed"), committed)
        self.assertEqual(read(self.folder / "restore-recovered.json")["snapshot"], recovered)
        self.assertEqual(recovered["engine_save"]["player"]["current_hp"], 1)
        self.assertEqual(recovered["sql_rows"]["campaign_turn_actions"], [])
        self.assertEqual(committed["engine_save"]["player"]["current_hp"], 20)
        self.assertNotEqual(read(self.folder / "restore-recovered.json")["snapshot"], committed)
        self.evidence("F03-AC004-AC006-restore-restart-outage", {"old_pid": old_pid,
                      "new_pid": self.process.pid, "durable_unchanged_on_restore_failure": True,
                      "outage_db_bytes_equal": True, "recovered_all_values_except_documented_last_played_equal": True,
                      "last_played_before": previous_played, "last_played_after": resumed_played,
                      "retry_action_id": command["action_id"], "receipt_count": 1,
                      "replay_full_snapshot_equal": True})

    def test_healthy_precommit_api_outage_separate_from_restore_failure(self):
        before = self.state("outage-before")
        command = {"action": "long_rest", "action_id": str(uuid4())}
        old_pid = self.process.pid
        self.stop()
        # API absent before POST, rather than a lost response after commit.
        db_before = (self.folder / "campaigns.sqlite3").read_bytes()
        with self.assertRaises(httpx.TransportError):
            self.rest(command)
        self.assertEqual((self.folder / "campaigns.sqlite3").read_bytes(), db_before)
        self.control("normal", "outage-restarted")
        self.start()
        self.assertNotEqual(self.process.pid, old_pid)
        recovered = self.state("outage-recovered")
        expected = copy.deepcopy(before)
        played = recovered["persisted"]["metadata"]["last_played_at"]
        self.assertGreaterEqual(played, before["persisted"]["metadata"]["last_played_at"])
        expected["persisted"]["metadata"]["last_played_at"] = played
        self.assertEqual(recovered, expected)
        self.assertEqual(recovered["sql_rows"]["campaign_turn_actions"], [])
        accepted = self.rest(command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        committed = self.state("outage-committed")
        self.assertEqual(len(committed["sql_rows"]["campaign_turn_actions"]), 1)
        self.assertEqual(self.rest(command).json(), accepted.json())
        self.assertEqual(self.state("outage-replayed"), committed)
        self.assertEqual(read(self.folder / "outage-recovered.json")["snapshot"], recovered)
        self.assertEqual(recovered["engine_save"]["player"]["current_hp"], 1)
        self.assertEqual(recovered["sql_rows"]["campaign_turn_actions"], [])
        self.assertEqual(committed["engine_save"]["player"]["current_hp"], 20)
        self.assertNotEqual(read(self.folder / "outage-recovered.json")["snapshot"], committed)
        self.evidence("F03-AC006-precommit-api-outage", {
            "old_pid": old_pid, "new_pid": self.process.pid,
            "outage_db_bytes_equal": True, "receipt_before_retry": 0,
            "recovered_all_values_except_last_played_equal": True,
            "same_id_retry": command["action_id"], "receipt_after_retry": 1,
            "full_replay_equal": True})

    def test_model_failure_full_invariance(self):
        before = self.state("model-before")
        self.control("normal", "model-failed")
        body = {"message": "Mor bir düşünceyi yüksek sesle kuruyorum.", "interaction_mode": "do", "action_id": str(uuid4())}
        response = self.client.post(f"{self.url}/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(response.status_code, 503, response.text)
        failed = read(self.folder / "model-failed.json")
        self.assertGreater(failed["counts"]["synthetic_model_attempts"], 0)
        self.assertEqual(failed["snapshot"], before)
        self.assertEqual(self.state("model-after"), before)
        self.control("normal", "model-retry-failed")
        retried = self.client.post(f"{self.url}/api/sessions/{self.sid}/turn", json=body)
        self.assertEqual(retried.status_code, 503, retried.text)
        self.assertEqual(read(self.folder / "model-retry-failed.json")["snapshot"], before)
        self.evidence("F03-AC006-model-failure", {"status": response.status_code,
                      "full_snapshot_equal": True, "same_id_failed_retry_unchanged": True, "counts": failed["counts"],
                      "receipt_count": len(before["sql_rows"]["campaign_turn_actions"])})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]), int(sys.argv[3]))
    else:
        unittest.main()
