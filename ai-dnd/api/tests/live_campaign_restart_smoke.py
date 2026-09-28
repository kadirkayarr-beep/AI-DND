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
from api.persistence.campaign_serializer import restore_stored_campaign
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
                initial_state = created["state"]
                initial_journal = initial_state.get("journal", {})
                if set(initial_journal) != {
                    "schema_version",
                    "discovered_locations",
                    "known_npcs",
                    "notable_events",
                    "quests",
                }:
                    raise RuntimeError("New campaign journal has an invalid public shape.")
                if initial_state.get("location") == "Henüz belirlenmedi" and (
                    initial_journal.get("discovered_locations")
                    or initial_journal.get("notable_events")
                ):
                    raise RuntimeError(
                        "An unresolved starting location was incorrectly journaled."
                    )

                starting_location = initial_state["location"]
                first_travel_result = _post_turn(
                    client,
                    base_url,
                    session_id,
                    "tavernaya gidiyorum",
                )
                first_travel_location = first_travel_result["state"]["location"]
                travel_result = first_travel_result
                fallback_used = False
                if first_travel_location == starting_location:
                    fallback_used = True
                    travel_result = _post_turn(
                        client,
                        base_url,
                        session_id,
                        "Taverna'ya doğru yürüyorum.",
                    )
                travel_state = travel_result["state"]
                travel_changed = travel_state["location"] != starting_location
                if travel_changed and not any(
                    entry.get("location_id") == travel_state["location"]
                    for entry in travel_state["journal"]["discovered_locations"]
                ):
                    raise RuntimeError(
                        "Canonical travel changed location without updating the journal."
                    )

                _post_turn(client, base_url, session_id, "etrafıma bakıyorum")
                result = _post_turn(
                    client,
                    base_url,
                    session_id,
                    "burada kimler var?",
                )

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
                # Seed one safe synthetic result in this temporary smoke database.
                # This makes the process-restart assertion independent of Qwen's
                # choice to route the preceding natural-language turns to combat.
                turn_index = persisted_before_restart.payload["engine_save"][
                    "world_state"
                ].get("flags", {}).get("turn_index", 0)
                combat_history_entry = {
                    "event_id": str(uuid.uuid4()),
                    "turn_index": turn_index,
                    "result": {
                        "action": "attack",
                        "status": "resolved",
                        "success": True,
                        "outcome": "hit",
                        "attack_roll": 12,
                        "attack_bonus": 2,
                        "attack_total": 14,
                        "target_ac": 12,
                        "damage": 2,
                    },
                }
                restored_session = game.create_session()
                restored_journal = restore_stored_campaign(
                    restored_session,
                    persisted_before_restart,
                )
                CampaignStore(database_path).save_campaign(
                    campaign_id,
                    restored_session,
                    journal=restored_journal,
                    combat_history_entry=combat_history_entry,
                )
                persisted_before_restart = CampaignStore(database_path).get_campaign(
                    campaign_id
                )
                if persisted_before_restart.combat_history != [combat_history_entry]:
                    raise RuntimeError(
                        "The temporary campaign database did not retain the "
                        "structured combat history fixture."
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
                detail_before_restart = client.get(
                    f"{base_url}/api/campaigns/{campaign_id}"
                ).json()
                state_before_restart = detail_before_restart["state"]
                combat_history_before_restart = detail_before_restart["combat_history"]
                if (
                    len(combat_history_before_restart) != 1
                    or combat_history_before_restart[0].get("event_id")
                    != combat_history_entry["event_id"]
                    or combat_history_before_restart[0].get("turn_index")
                    != combat_history_entry["turn_index"]
                    or combat_history_before_restart[0].get("result", {}).get(
                        "attack_roll"
                    )
                    != combat_history_entry["result"]["attack_roll"]
                ):
                    raise RuntimeError(
                        "The API did not expose the stored structured combat history."
                    )
                if state_before_restart["journal"]["quests"]:
                    raise RuntimeError(
                        "Narration unexpectedly populated the unsupported quest ledger."
                    )
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
                if resumed["combat_history"] != combat_history_before_restart:
                    raise RuntimeError(
                        "Structured combat history changed across API restart."
                    )

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
                remembered_player_text = next(
                    (
                        entry["text"]
                        for entry in npc_memory.get("memory", [])
                        if isinstance(entry, dict)
                        and entry.get("speaker") == "player"
                        and "Arven" in str(entry.get("text", ""))
                    ),
                    None,
                )
                if not remembered_player_text:
                    raise RuntimeError(
                        "The saved player utterance could not be selected for continuity."
                    )
                continuity_claim = (
                    f"{npc_name}, ben sana daha önce şunu söylemiştim: "
                    f"{remembered_player_text}; hatırlıyor musun?"
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
                if post_restart_turn["state"]["journal"]["quests"]:
                    raise RuntimeError(
                        "A real Qwen narration populated the unsupported quest ledger."
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
                    "environment": resumed["state"]["world"]["environment"],
                    "travel_first_location": first_travel_location,
                    "travel_fallback_used": fallback_used,
                    "travel_final_location": travel_state["location"],
                    "travel_changed_location": travel_changed,
                    "travel_metadata_changed": (
                        travel_state.get("world") != initial_state.get("world")
                    ),
                    "travel_environment": travel_state.get("world", {}).get(
                        "environment"
                    ),
                    "discovered_location_ids": [
                        entry["location_id"]
                        for entry in resumed["state"]["journal"]["discovered_locations"]
                    ],
                    "journal_event_count": len(
                        resumed["state"]["journal"]["notable_events"]
                    ),
                    "quest_count": len(resumed["state"]["journal"]["quests"]),
                    "npc_name": npc_name,
                    "npc_memory_survived_restart": True,
                    "combat_active": bool(resumed["state"]["combat"].get("active")),
                    "combat_history_count": len(resumed["combat_history"]),
                    "history_entries_after_resume": len(resumed["history"]),
                }
        finally:
            if process is not None:
                _stop_api(process, log_handle)


if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))