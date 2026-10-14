"""Offline-model real-process restart proof; synthetic identity, disposable store.

This exercises actual HTTP and API process replacement, not browser or Clerk auth.
Run: python -B -m unittest api.tests.test_lr00_process_restart -v
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4

import httpx


def _serve(port: int, database: Path, instance: str) -> None:
    # This is a fresh child; set storage before importing the API application.
    os.environ["AI_DND_CAMPAIGN_DB"] = str(database)
    import game
    from api.main import create_app
    from api.auth import FixedAuthenticator
    from api.tests.auth_fixture import TEST_PLAYER
    from api.session_manager import SessionManager
    from api.persistence.campaign_store import CampaignStore
    import uvicorn

    model_attempts = []

    def forbidden_model(*_args, **_kwargs):
        model_attempts.append(1)
        raise AssertionError("No model permitted in LR-00 process test")

    game.ollama.chat = forbidden_model
    game.ask_dungeon_master = forbidden_model
    app = create_app(
        session_manager=SessionManager(
            campaign_store=CampaignStore(database, bound_principal=TEST_PLAYER)),
        ollama_adapter=None,
        authenticator=FixedAuthenticator(TEST_PLAYER),
    )

    @app.get("/__lr00_process")
    def process_identity():
        return {"instance": instance, "pid": os.getpid(),
                "model_attempts": len(model_attempts)}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


class LR00ProcessRestartTests(unittest.TestCase):
    def test_spent_action_survives_actual_process_restart_and_resume(self):
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        import bounded_encounter

        with tempfile.TemporaryDirectory(prefix="ai-dnd-lr00-process-") as temporary:
            root = Path(temporary)
            database = root / "campaigns.sqlite3"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            children = []

            def stop(process):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

            def start():
                instance = uuid4().hex
                env = os.environ.copy()
                env["AI_DND_CAMPAIGN_DB"] = str(database)
                env["PYTHONUTF8"] = "1"
                # No live model/credential is needed or passed to this child.
                for key in list(env):
                    if key.startswith(("OLLAMA_", "AI_DND_CLERK_", "AI_DND_OIDC_")):
                        env.pop(key)
                process = subprocess.Popen(
                    [sys.executable, "-B", "-m", "api.tests.test_lr00_process_restart",
                     "--serve", str(port), str(database), instance],
                    cwd=Path(__file__).resolve().parents[2], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                children.append(process)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        observed = client.get(base + "/__lr00_process").json()
                        if observed.get("instance") == instance:
                            self.assertEqual(observed["pid"], process.pid)
                            return process, observed
                    except (httpx.HTTPError, ValueError):
                        pass
                    time.sleep(0.1)
                self.fail("Owned isolated API did not start; no foreign process used")

            with httpx.Client(timeout=5, trust_env=False) as client:
                try:
                    first, first_identity = start()
                    settings = client.get(base + "/api/campaign-start-options").json()["settings"][0]
                    region = settings["regions"][0]
                    response = client.post(base + "/api/campaigns", json={
                        "name": "Synthetic LR-00 process test",
                        "campaign_start": {
                            "setting_id": settings["setting_id"],
                            "region_pack_id": region["region_pack_id"],
                            "region_id": region["region_id"],
                            "starting_location_id": region["starting_locations"][0]["entity_id"],
                        },
                    })
                    self.assertEqual(response.status_code, 200)
                    created = response.json()
                    campaign_id, sid = created["campaign_id"], created["session_id"]

                    def state():
                        response = client.get(f"{base}/api/sessions/{sid}/state")
                        self.assertEqual(response.status_code, 200)
                        return response.json()

                    def turn(message, steps=None):
                        body = {"message": message, "action_id": str(uuid4())}
                        if steps is not None:
                            combat = state()["combat"]
                            body.update(combat_action={"steps": steps}, combat_id=combat["combat_id"],
                                        combat_round=combat["round"], combat_turn_index=combat["current_turn_index"])
                        response = client.post(f"{base}/api/sessions/{sid}/turn", json=body)
                        self.assertEqual(response.status_code, 200)
                        return body, response.json()

                    turn(bounded_encounter.ENTER)
                    turn(bounded_encounter.START)
                    self.assertTrue(state()["combat"]["active"])
                    self.assertEqual(state()["combat"]["current_actor_id"], "player")
                    command, accepted = turn("Hamle.", [{"kind": "dash"}])
                    before = state()
                    self.assertTrue(before["combat"]["active"])
                    self.assertTrue(before["combat"]["action_economy"]["actors"]["player"]["base_action_spent"])
                    self.assertFalse(before["combat"]["action_economy"]["actors"]["player"]["action_available"])
                    store = CampaignStore(database, bound_principal=TEST_PLAYER)
                    saved = store.get_campaign(campaign_id)
                    payload_before = copy.deepcopy(saved.payload)
                    history_before = copy.deepcopy(saved.history)
                    combat_history_before = copy.deepcopy(saved.combat_history)
                    self.assertEqual(client.get(base + "/__lr00_process").json()["model_attempts"], 0)
                    stop(first)
                    self.assertIsNotNone(first.poll())

                    second, second_identity = start()
                    self.assertNotEqual(first_identity["instance"], second_identity["instance"])
                    resumed = client.post(f"{base}/api/campaigns/{campaign_id}/resume")
                    self.assertEqual(resumed.status_code, 200)
                    sid = resumed.json()["session_id"]
                    self.assertNotEqual(sid, created["session_id"])
                    after = state()
                    self.assertEqual(after["combat"], before["combat"])
                    self.assertEqual(after["turn_index"], before["turn_index"])
                    restored = store.get_campaign(campaign_id)
                    self.assertEqual(restored.payload, payload_before)
                    self.assertEqual(restored.history, history_before)
                    self.assertEqual(restored.combat_history, combat_history_before)
                    replay = client.post(f"{base}/api/sessions/{sid}/turn", json=command)
                    self.assertEqual(replay.status_code, 200)
                    self.assertEqual(replay.json(), dict(accepted, session_id=sid))
                    self.assertEqual(state(), after)
                    duplicate_action = {**command, "action_id": str(uuid4())}
                    rejected = client.post(f"{base}/api/sessions/{sid}/turn", json=duplicate_action)
                    self.assertEqual(rejected.status_code, 400)
                    self.assertEqual(state(), after)
                    final = store.get_campaign(campaign_id)
                    self.assertEqual(final.payload, payload_before)
                    self.assertEqual(final.history, history_before)
                    self.assertEqual(final.combat_history, combat_history_before)
                    self.assertEqual(client.get(base + "/__lr00_process").json()["model_attempts"], 0)
                    print(json.dumps({
                        "scope": "synthetic-auth real HTTP/process restart; no browser acceptance",
                        "first_pid": first.pid, "first_exit_observed": first.poll() is not None,
                        "second_pid": second.pid, "port": port,
                        "active_combat": True, "base_action_spent": True,
                        "payload_rng_history_equal": True, "receipt_replayed_once": True,
                        "second_action_rejected": True, "model_attempts": 0,
                    }))
                finally:
                    for child in children:
                        stop(child)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--serve":
        _serve(int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        unittest.main()
