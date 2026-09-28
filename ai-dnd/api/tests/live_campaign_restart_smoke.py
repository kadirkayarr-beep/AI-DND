"""Manual, real-qwen smoke that stops and restarts a separate FastAPI process.

Run from ai-dnd with:
    python -m api.tests.live_campaign_restart_smoke
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
from typing import Any
import uuid

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.persistence.campaign_store import CampaignStore


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_api(port: int, database_path: Path, log_path: Path):
    environment = os.environ.copy()
    environment["AI_DND_CAMPAIGN_DB"] = str(database_path)
    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=AI_DND_DIR,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_handle


def _wait_ready(process: subprocess.Popen, base_url: str, log_path: Path) -> None:
    deadline = time.monotonic() + 30
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = client.get(f"{base_url}/api/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.25)
                continue
            time.sleep(0.25)
    log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
    raise RuntimeError(f"FastAPI process did not become healthy.\n{log_tail}")


def _stop_api(process: subprocess.Popen, log_handle) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    log_handle.close()


def _post_turn(
    client: httpx.Client,
    base_url: str,
    session_id: str,
    message: str,
) -> dict[str, Any]:
    response = client.post(
        f"{base_url}/api/sessions/{session_id}/turn",
        json={"message": message},
        timeout=240,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Live turn failed with HTTP {response.status_code}: "
            f"{response.json().get('detail', 'No safe error detail.')}"
        )
    return response.json()


def _player_memory_mentions(npc: dict[str, Any], name: str) -> bool:
    return any(
        isinstance(entry, dict)
        and entry.get("speaker") == "player"
        and name.casefold() in str(entry.get("text", "")).casefold()
        for entry in npc.get("memory", [])
    )


def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ai-dnd-campaign-live-") as temporary:
        temporary_path = Path(temporary)
        database_path = temporary_path / "campaigns.sqlite3"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        process, log_handle = _start_api(
            port,
            database_path,
            temporary_path / "api-first.log",
        )
        try:
            _wait_ready(process, base_url, temporary_path / "api-first.log")
            with httpx.Client(timeout=15) as client:
                created_response = client.post(
                    f"{base_url}/api/campaigns",
                    json={"name": f"Live restart smoke {uuid.uuid4().hex[:8]}"},
                )
                if created_response.status_code != 200:
                    raise RuntimeError(
                        f"Campaign creation failed with HTTP "
                        f"{created_response.status_code}: {created_response.text}"
                    )
                created = created_response.json()
                campaign_id = created["campaign_id"]
                session_id = created["session_id"]

                for message in (
                    "tavernaya gidiyorum",
                    "etrafıma bakıyorum",
                    "burda kimler var",
                ):
                    result = _post_turn(client, base_url, session_id, message)

                state = result["state"]
                npcs = state.get("npcs", [])
                if not npcs:
                    raise RuntimeError(
                        "Qwen produced no canonical NPC after the tavern setup turns."
                    )
                npc = next(
                    (
                        candidate
                        for candidate in npcs
                        if candidate.get("location") == state.get("location")
                    ),
                    npcs[0],
                )
                npc_name = str(npc["name"])
                _post_turn(
                    client,
                    base_url,
                    session_id,
                    f"{npc_name}, adım Arven. Kendimi sana tanıtıyorum.",
                )

                persisted_before_restart = CampaignStore(database_path).get_campaign(
                    campaign_id
                )
                saved_engine_state = persisted_before_restart.payload["engine_save"]
                saved_npcs = saved_engine_state["world_state"]["npcs"]
                memory_npc = next(
                    (candidate for candidate in saved_npcs if candidate.get("id") == npc["id"]),
                    None,
                )
                if not memory_npc or not _player_memory_mentions(memory_npc, "Arven"):
                    raise RuntimeError(
                        f"Qwen dialogue did not create player-attributed memory for {npc_name}."
                    )
                state_before_restart = client.get(
                    f"{base_url}/api/campaigns/{campaign_id}"
                ).json()["state"]
                saved_payload_before_restart = copy.deepcopy(
                    persisted_before_restart.payload
                )

            _stop_api(process, log_handle)
            process = None

            process, log_handle = _start_api(
                port,
                database_path,
                temporary_path / "api-after-restart.log",
            )
            _wait_ready(process, base_url, temporary_path / "api-after-restart.log")

            with httpx.Client(timeout=20) as client:
                listed = client.get(f"{base_url}/api/campaigns")
                if listed.status_code != 200:
                    raise RuntimeError(
                        f"Campaign listing after restart failed: {listed.status_code}"
                    )
                if campaign_id not in {
                    item["campaign_id"] for item in listed.json()
                }:
                    raise RuntimeError("Campaign ID disappeared after server restart.")

                resumed_response = client.post(
                    f"{base_url}/api/campaigns/{campaign_id}/resume"
                )
                if resumed_response.status_code != 200:
                    raise RuntimeError(
                        f"Resume after restart failed with HTTP "
                        f"{resumed_response.status_code}: {resumed_response.text}"
                    )
                resumed = resumed_response.json()
                if resumed["campaign_id"] != campaign_id:
                    raise RuntimeError("Resume changed the stable campaign ID.")
                if resumed["state"] != state_before_restart:
                    raise RuntimeError("Public canonical state changed across restart.")

                persisted_after_restart = CampaignStore(database_path).get_campaign(
                    campaign_id
                )
                if persisted_after_restart.payload != saved_payload_before_restart:
                    raise RuntimeError("Stored engine or RNG payload changed on restart.")

                npc_memory = next(
                    (
                        candidate
                        for candidate in persisted_after_restart.payload["engine_save"][
                            "world_state"
                        ]["npcs"]
                        if candidate.get("id") == npc["id"]
                    ),
                    None,
                )
                if not npc_memory or not _player_memory_mentions(npc_memory, "Arven"):
                    raise RuntimeError("NPC memory was not present after server restart.")
                continuity_claim = (
                    f"{npc_name}, daha önce adım Arven demiştim; bunu hatırlıyor musun?"
                )
                if not game.npc_memory_supports_claim(npc_memory, continuity_claim):
                    raise RuntimeError(
                        "Python's canonical NPC-memory guard did not recognize the saved claim."
                    )

                post_restart_turn = _post_turn(
                    client,
                    base_url,
                    resumed["session_id"],
                    continuity_claim,
                )
                updated_payload = CampaignStore(database_path).get_campaign(
                    campaign_id
                ).payload
                updated_npc = next(
                    (
                        candidate
                        for candidate in updated_payload["engine_save"]["world_state"][
                            "npcs"
                        ]
                        if candidate.get("id") == npc["id"]
                    ),
                    None,
                )
                if not updated_npc or not _player_memory_mentions(updated_npc, "Arven"):
                    raise RuntimeError(
                        "NPC memory was lost during the real Qwen post-restart turn."
                    )

                return {
                    "result": "passed",
                    "campaign_id": campaign_id,
                    "character": resumed["state"]["character"]["name"],
                    "hp": resumed["state"]["character"]["current_hp"],
                    "inventory": resumed["state"]["inventory"],
                    "location": resumed["state"]["location"],
                    "npc_name": npc_name,
                    "npc_memory_survived_restart": True,
                    "combat_active": bool(resumed["state"]["combat"].get("active")),
                    "history_entries_after_resume": len(resumed["history"]),
                    "qwen_post_restart_narration": post_restart_turn["narration"],
                }
        finally:
            if process is not None:
                _stop_api(process, log_handle)


if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))