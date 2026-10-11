"""Live Phase 7 smoke for canon, knowledge, and a hidden local event.

Run from ``ai-dnd``:

    python -m api.tests.live_phase7_lore_smoke

The runner starts its own API on a free port and a temporary SQLite file.
It does not read or write the shared campaign database.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
PACK_FILES = (
    AI_DND_DIR / "api" / "lore_authority" / "packs" / "neverwinter_the_north_v1.extraction.json",
    AI_DND_DIR / "api" / "lore_authority" / "packs" / "neverwinter_the_north_v1.review.json",
)
MODEL_NAME = "qwen3:8b"
MAX_MODEL_CALLS_PER_TURN = 2
HIDDEN_SUMMARY = "Gizli bir hareket başladı."
AFTERMATH = "Mavi tebeşirle çizilmiş küçük bir daire kaldı."
FLAG_KEY = "scheduled:phase7-mark"
EVENT_ID = "phase7:hidden-flag"
START_SELECTION = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}


class SmokeFailure(RuntimeError):
    """A live Phase 7 assertion failed."""


class _CaptureApiLogs(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _pack_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACK_FILES
    }


def _lore_projection(record: Any) -> dict[str, Any]:
    state = getattr(record, "lore_authority", None)
    if state is None:
        return {}
    data = state.to_dict()
    return {
        key: data.get(key)
        for key in (
            "binding_status",
            "world_id",
            "epoch_id",
            "region_id",
            "current_location_entity_id",
            "player_known_fact_ids",
            "campaign_overrides",
            "faction_standings",
        )
    }


def _parse_turn_logs(messages: list[str]) -> tuple[list[str] | None, int | None, str | None]:
    fact_ids: list[str] | None = None
    model_calls: int | None = None
    model_name: str | None = None
    for message in messages:
        if "Lore retrieval " in message:
            match = re.search(r"selected_fact_ids=(\[[^\]]*\])", message)
            if match:
                try:
                    parsed = ast.literal_eval(match.group(1))
                except (SyntaxError, ValueError):
                    parsed = None
                if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                    fact_ids = parsed
        if "Game turn completed (" in message:
            calls_match = re.search(r"model_calls=(\d+)", message)
            name_match = re.search(r"model=([^, )]+)", message)
            if calls_match:
                model_calls = int(calls_match.group(1))
            if name_match:
                model_name = name_match.group(1)
    return fact_ids, model_calls, model_name


def _append_json_line(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()


def _arm_hidden_event(world: dict[str, Any]) -> None:
    import scheduled_events

    if any(
        isinstance(event, dict) and event.get("event_id") == EVENT_ID
        for event in world.get("scheduled_events", [])
    ):
        return
    scheduled_events.register_event(
        world,
        event_id=EVENT_ID,
        window_start=30,
        window_end=90,
        location_id=world.get("location"),
        effects=[{"kind": "flag", "key": FLAG_KEY, "value": True}],
        summary=HIDDEN_SUMMARY,
        aftermath=AFTERMATH,
        visibility="hidden",
        aftermath_visible=True,
    )


def _serve_isolated_api(port: int, database_path: Path, audit_path: Path) -> None:
    os.environ["AI_DND_CAMPAIGN_DB"] = str(database_path)
    from api.main import app
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware

    capture = _CaptureApiLogs()
    api_logger = logging.getLogger("ai_dnd.api")
    api_logger.setLevel(logging.INFO)
    api_logger.addHandler(capture)
    manager = app.state.session_manager
    armed: set[str] = set()

    class TurnAuditMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            match = re.fullmatch(r"/api/(?:game/)?sessions/([^/]+)/turn", request.url.path)
            if match and match.group(1) not in armed:
                record = manager.get(match.group(1))
                _arm_hidden_event(record.game_session.world_state)
                armed.add(match.group(1))
            start = len(capture.messages)
            response = await call_next(request)
            if match and response.status_code < 400:
                session_id = match.group(1)
                record = manager.get(session_id)
                session = record.game_session
                fact_ids, model_calls, model_name = _parse_turn_logs(capture.messages[start:])
                safety = getattr(session, "last_narration_safety", None)
                safety = safety if isinstance(safety, dict) else {}
                _append_json_line(audit_path, {
                    "session_id": session_id,
                    "turn_index": session.world_state.get("flags", {}).get("turn_index"),
                    "model": model_name,
                    "model_calls": model_calls,
                    "retrieved_fact_ids": fact_ids,
                    "narrative_safety_action": {
                        "handling": safety.get("handling", "unavailable"),
                        "reason_code": safety.get("reason_code"),
                    },
                    "lore_authority": _lore_projection(record),
                    "elapsed_seconds": session.world_state.get("campaign_time", {}).get("elapsed_seconds"),
                    "flag": (session.world_state.get("flags") or {}).get(FLAG_KEY),
                    "npc_names": [
                        {"id": npc.get("id"), "name": npc.get("name"), "known": npc.get("name_known_to_player")}
                        for npc in session.world_state.get("npcs", [])
                        if isinstance(npc, dict)
                    ],
                })
            return response

    app.add_middleware(TurnAuditMiddleware)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_api(port: int, database_path: Path, audit_path: Path, log_path: Path):
    environment = os.environ.copy()
    environment["AI_DND_CAMPAIGN_DB"] = str(database_path)
    environment["PYTHONUTF8"] = "1"
    log_handle = log_path.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "api.tests.live_phase7_lore_smoke", "--serve", str(port), str(database_path), str(audit_path)],
        cwd=AI_DND_DIR,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_handle


def _wait_ready(process: subprocess.Popen, base_url: str, log_path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = client.get(f"{base_url}/api/health")
                if response.status_code == 200:
                    return response.json()
            except httpx.HTTPError:
                time.sleep(0.25)
                continue
            time.sleep(0.25)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:]
    raise SmokeFailure(f"Isolated API did not become healthy. {tail}")


def _stop_api(process: subprocess.Popen, log_handle: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    log_handle.close()


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _latest_audit(path: Path) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise SmokeFailure("The isolated API wrote no turn diagnostics.")
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise SmokeFailure("The isolated API wrote an invalid diagnostic row.")
    return value


def _post_turn(client: httpx.Client, base_url: str, session_id: str, message: str, *, target_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if target_id is not None:
        payload["target_id"] = target_id
    response = client.post(f"{base_url}/api/sessions/{session_id}/turn", json=payload, timeout=240)
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", "No safe error detail.")
        except Exception:
            detail = "No safe error detail."
        raise SmokeFailure(f"Live turn failed with HTTP {response.status_code}: {detail}")
    return response.json()


def _public_blob(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False)


def _adventure_possibility_is_not_death() -> None:
    from api.lore_authority import CampaignLoreState, ClaimType, EngineActionEvidence, apply_committed_world_canon
    from api.lore_authority.models import LoreFact
    from api.tests.test_lore_authority import entity, fact, verified_registry

    registry = verified_registry(
        entities=[entity("npc:module", "Module NPC", entity_type="CANONICAL_NPC")],
        facts=[fact("fact:module-death", "npc:module", "life_status", "dead", claim_type="ADVENTURE_POSSIBILITY")],
    )
    stored = registry.fact("fact:module-death")
    if not isinstance(stored, LoreFact) or stored.claim_type is not ClaimType.ADVENTURE_POSSIBILITY:
        raise SmokeFailure("The adventure-possibility fixture was not stored as a possibility.")
    state = CampaignLoreState.from_mapping({
        "binding_status": "BOUND",
        "setting_profile": "TEST_SETTING",
        "world_id": "world:test",
        "epoch_id": "epoch:test",
        "region_id": "region:test",
        "current_location_entity_id": "city:test",
        "player_known_fact_ids": [],
        "npc_known_fact_ids": {},
        "campaign_overrides": [],
        "procedural_entity_refs": [],
        "lore_discoveries": [],
    })
    world = {"npcs": [{"id": "npc:module", "status": "alive"}]}
    committed = apply_committed_world_canon(
        state,
        evidence=EngineActionEvidence("turn:1", 1, "python_engine"),
        before_world=world,
        after_world=world,
        action_result={"narration": "The module says this person died."},
        registry=registry,
    )
    if committed.campaign_overrides or world["npcs"][0]["status"] != "alive":
        raise SmokeFailure("Adventure-possibility prose created a campaign death.")


def run_smoke(report_dir: Path | None = None) -> dict[str, Any]:
    _adventure_possibility_is_not_death()
    pack_before = _pack_hashes()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    turns: list[dict[str, Any]] = []
    result: dict[str, Any] = {"status": "FAILED", "port": port, "turns": turns}
    process = None
    log_handle = None
    with tempfile.TemporaryDirectory() as folder:
        temp_path = Path(folder)
        database_path = temp_path / "phase7.sqlite3"
        audit_path = temp_path / "audit.jsonl"
        try:
            process, log_handle = _start_api(port, database_path, audit_path, temp_path / "api.log")
            health = _wait_ready(process, base_url, temp_path / "api.log")
            _require(health.get("model") == MODEL_NAME, "Isolated API health reported an unexpected model.")

            def play(client: httpx.Client, session_id: str, label: str, message: str, *, target_id: str | None = None) -> dict[str, Any]:
                turn = _post_turn(client, base_url, session_id, message, target_id=target_id)
                audit = _latest_audit(audit_path)
                calls = audit.get("model_calls")
                _require(type(calls) is int and 0 <= calls <= MAX_MODEL_CALLS_PER_TURN, f"{label}: model calls were {calls}.")
                _require(audit.get("model") == MODEL_NAME, f"{label}: model name was not recorded.")
                row = {
                    "label": label,
                    "player_message": message,
                    "narration": turn.get("narration"),
                    "model_calls": calls,
                    "retrieved_fact_ids": audit.get("retrieved_fact_ids"),
                    "state": turn.get("state"),
                    "lore_authority": audit.get("lore_authority"),
                    "elapsed_seconds": audit.get("elapsed_seconds"),
                    "flag": audit.get("flag"),
                    "npc_names": audit.get("npc_names"),
                }
                turns.append(row)
                return turn

            with httpx.Client(timeout=30) as client:
                created_response = client.post(f"{base_url}/api/campaigns", json={
                    "name": f"Phase 7 smoke {uuid.uuid4().hex[:8]}",
                    "campaign_start": START_SELECTION,
                })
                _require(created_response.status_code == 200, f"Campaign creation failed with HTTP {created_response.status_code}.")
                created = created_response.json()
                campaign_id = created["campaign_id"]
                session_id = created["session_id"]
                _require(created["state"].get("location") == "fr:city:neverwinter", "The campaign did not start in Neverwinter.")
                _require(created["state"].get("campaign_time", {}).get("year") == 1501, "The campaign clock did not start at 1501.")

                presence = play(client, session_id, "Procedural locals", "Burada kim var?")
                raw_npcs = turns[-1]["npc_names"]
                _require(isinstance(raw_npcs, list) and raw_npcs, "The scene did not materialize a procedural local.")
                public_npcs = presence["state"].get("npcs", [])
                hidden = next(
                    (npc for npc in raw_npcs if npc.get("known") is False and isinstance(npc.get("name"), str)),
                    None,
                )
                _require(hidden is not None, "No procedural NPC still had an unknown name.")
                public = next((npc for npc in public_npcs if npc.get("id") == hidden["id"]), None)
                _require(public is not None, "The public NPC list dropped the procedural id.")
                _require(
                    public.get("name") != hidden["name"] and hidden["name"] not in _public_blob(presence["state"]),
                    "The unknown true name was visible in the public state.",
                )
                npc_id = hidden["id"]

                named = play(client, session_id, "Learn the name", "Adın ne?", target_id=npc_id)
                learned = next((npc for npc in named["state"].get("npcs", []) if npc.get("id") == npc_id), None)
                _require(
                    learned is not None and learned.get("name") == hidden["name"],
                    "Asking the name did not reveal that same NPC id.",
                )

                lord = play(client, session_id, "Current lord", "Who is the current lord of Neverwinter?")
                lord_text = str(lord.get("narration", "")).casefold()
                _require(turns[-1]["model_calls"] == 0, "The verified lord question used a model call.")
                _require("neverember" in lord_text and "current lord" in lord_text, "The lord answer was not the verified 1501 fact.")
                _require(any("dagult" in fact_id or "lord" in fact_id for fact_id in (turns[-1]["lore_authority"].get("player_known_fact_ids") or [])), "The lord answer did not record a player discovery.")

                waited = play(client, session_id, "Hidden local event", "3 dakika bekliyorum")
                waited_blob = _public_blob(waited["state"])
                _require(turns[-1]["flag"] is True, "The local engine event did not change the flag.")
                _require(HIDDEN_SUMMARY not in waited_blob and AFTERMATH not in waited_blob, "The hidden event was visible before observation.")
                _require(not waited["state"].get("known_scheduled_events"), "The journal projection listed the hidden event.")
                _require(FLAG_KEY not in waited_blob, "The engine flag key was copied into the public state.")

                narrated = play(
                    client,
                    session_id,
                    "Narration before observation",
                    "Yağmurun sesini ve sokaktaki sıradan hareketi betimle. Yeni bir isim veya gizli bir işaret ekleme.",
                )
                narrated_text = str(narrated.get("narration", ""))
                _require(HIDDEN_SUMMARY not in narrated_text and AFTERMATH not in narrated_text, "Narration leaked the hidden aftermath.")
                _require(turns[-1]["model_calls"] <= MAX_MODEL_CALLS_PER_TURN, "The narration turn exceeded two model calls.")

                revealed = play(client, session_id, "Observe the aftermath", "Etrafıma bakıyorum.")
                revealed_summaries = [event.get("summary") for event in revealed["state"].get("known_scheduled_events", [])]
                _require(AFTERMATH in revealed_summaries or AFTERMATH in str(revealed.get("narration", "")), "Observation did not reveal the aftermath.")
                _require(HIDDEN_SUMMARY not in _public_blob(revealed["state"]), "Observation published the hidden pre-event summary.")

                first_lore = turns[-2]["lore_authority"]
                first_npcs = {npc["id"] for npc in revealed["state"].get("npcs", [])}
                second_response = client.post(f"{base_url}/api/campaigns", json={
                    "name": f"Phase 7 other {uuid.uuid4().hex[:8]}",
                    "campaign_start": START_SELECTION,
                })
                _require(second_response.status_code == 200, "The second campaign could not be created.")
                second = second_response.json()
                second_turn = play(client, second["session_id"], "Second campaign", "Burada kim var?")
                second_lore = turns[-1]["lore_authority"]
                second_known = [
                    npc for npc in (turns[-1]["npc_names"] or [])
                    if npc.get("id") in first_npcs and npc.get("known") is True
                ]
                _require(not second_known, "The second campaign inherited a learned NPC name.")
                _require(hidden["name"] not in _public_blob(second_turn["state"]), "The second campaign displayed the first campaign's learned name.")
                _require(not second_lore.get("player_known_fact_ids"), "The second campaign inherited player knowledge.")
                _require(not second_lore.get("campaign_overrides"), "The second campaign inherited canon overrides.")
                _require(turns[-1]["flag"] is not True, "The second campaign inherited the local flag.")
                _require(second["campaign_id"] != campaign_id, "The second campaign reused the first campaign id.")

            saved_elapsed = next(row["elapsed_seconds"] for row in reversed(turns) if row["label"] == "Observe the aftermath")
            saved_name = hidden["name"]
            _stop_api(process, log_handle)
            process = None
            log_handle = None
            process, log_handle = _start_api(port, database_path, audit_path, temp_path / "api-resume.log")
            _wait_ready(process, base_url, temp_path / "api-resume.log")
            with httpx.Client(timeout=30) as client:
                resumed_response = client.post(f"{base_url}/api/campaigns/{campaign_id}/resume", timeout=30)
                _require(resumed_response.status_code == 200, "The campaign did not resume.")
                resumed = resumed_response.json()
                resumed_npc = next((npc for npc in resumed["state"].get("npcs", []) if npc.get("id") == npc_id), None)
                _require(resumed_npc is not None and resumed_npc.get("name") == saved_name, "The known NPC id or name changed across resume.")
                _require(resumed["state"].get("campaign_time", {}).get("year") == 1501, "The resumed clock left 1501.")
                summaries = [event.get("summary") for event in resumed["state"].get("known_scheduled_events", [])]
                _require(AFTERMATH in summaries, "The observed aftermath did not survive resume.")
                play(client, resumed["session_id"], "Resume continuity", "Burada kim var?")
                _require(turns[-1]["elapsed_seconds"] == saved_elapsed, "Resume changed the campaign clock.")
                _require(turns[-1]["flag"] is True, "Resume lost the engine flag.")
                _require(first_lore.get("player_known_fact_ids") == turns[-1]["lore_authority"].get("player_known_fact_ids"), "Resume changed player knowledge.")

            _require(_pack_hashes() == pack_before, "The global pack files changed during play.")
            result.update({
                "status": "MECHANICAL_PASS_NEEDS_NARRATION_REVIEW",
                "campaign_id": campaign_id,
                "npc_id": npc_id,
                "model_call_limit": MAX_MODEL_CALLS_PER_TURN,
                "pack_hashes": pack_before,
                "adventure_possibility": "still_alive",
            })
        except Exception as error:
            result["error_type"] = type(error).__name__
            result["error"] = str(error)[:1000]
            if process is not None and log_handle is not None:
                log_path = temp_path / "api.log"
                if log_path.exists():
                    result["log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
        finally:
            if process is not None and log_handle is not None:
                _stop_api(process, log_handle)
            if report_dir is not None:
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / "summary.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    return result


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--serve":
        _serve_isolated_api(int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
        return 0
    report_dir = AI_DND_DIR / "reports" / "phase7-package-04-smoke"
    result = run_smoke(report_dir)
    print(json.dumps({key: value for key, value in result.items() if key != "turns"}, ensure_ascii=False, indent=2))
    return 0 if str(result.get("status", "")).startswith("MECHANICAL_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
