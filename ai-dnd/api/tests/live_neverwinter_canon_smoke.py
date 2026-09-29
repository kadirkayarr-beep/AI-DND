"""Disposable real-Qwen smoke for the Neverwinter canon pack.

Run from ``ai-dnd`` with:
    python -m api.tests.live_neverwinter_canon_smoke

The runner starts its own API process against a temporary SQLite database,
restarts that process once, and never reads or writes the shared campaign DB.
"""

from __future__ import annotations

import ast
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
MODEL_NAME = "qwen3:8b"
DISCLOSED_NAME = "Arven"
MAX_MODEL_CALLS_PER_TURN = 2
START_SELECTION = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}


class SmokeFailure(RuntimeError):
    """A live smoke assertion failed."""


class _CaptureApiLogs(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _world_projection(session: Any) -> dict[str, Any]:
    world = session.world_state
    locations = world.get("locations", {})
    flags = world.get("flags", {})
    npcs = world.get("npcs", [])
    shops = world.get("shops", [])
    features = world.get("features", [])
    quests = world.get("quests", [])

    def records(items: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        return [
            {field: item.get(field) for field in fields}
            for item in items
            if isinstance(item, dict)
        ]

    return {
        "location": world.get("location"),
        "location_ids": sorted(locations) if isinstance(locations, dict) else [],
        "npcs": records(
            npcs,
            ("id", "name", "role", "location", "shop_id", "reality_layer", "tags"),
        ),
        "shops": records(
            shops,
            ("id", "name", "location", "shopkeeper_id", "reality_layer", "tags"),
        ),
        "features": records(features, ("id", "name", "location", "reality_layer")),
        "quests": records(quests, ("quest_id", "id", "status")),
        "inventory": world.get("inventory", []),
        "currency": world.get("currency"),
        "events": world.get("events", []),
        "flags": {
            key: value
            for key, value in flags.items()
            if key != "turn_index"
        } if isinstance(flags, dict) else {},
        "world_metadata": getattr(session, "world_metadata", {}),
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
            "setting_profile",
            "world_id",
            "epoch_id",
            "region_id",
            "current_location_entity_id",
            "region_pack_id",
            "starting_location_entity_id",
            "player_known_fact_ids",
            "npc_known_fact_ids",
            "campaign_overrides",
            "procedural_entity_refs",
            "lore_discoveries",
        )
    }


def _player_disclosure_npc_ids(session: Any) -> list[str]:
    result = []
    for npc in session.world_state.get("npcs", []):
        if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
            continue
        if any(
            isinstance(entry, dict)
            and entry.get("speaker") == "player"
            and DISCLOSED_NAME.casefold() in str(entry.get("text", "")).casefold()
            for entry in npc.get("memory", [])
        ):
            result.append(npc["id"])
    return sorted(result)


def _lore_safety_action(diagnostic: dict[str, Any]) -> str:
    reason = diagnostic.get("reason_code")
    if reason == "UNVERIFIED_LORE_CLAIM":
        return "rejected_unverified_claim_then_python_fallback"
    if reason == "SHOP_ECONOMY_NOT_SUPPORTED":
        return "blocked_unsupported_shop_economy"
    return "no_lore_claim_rejection_recorded"


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
                if isinstance(parsed, list) and all(
                    isinstance(item, str) for item in parsed
                ):
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

    class TurnAuditMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            match = re.fullmatch(
                r"/api/(?:game/)?sessions/([^/]+)/turn",
                request.url.path,
            )
            start = len(capture.messages)
            response = await call_next(request)
            if match and response.status_code < 400:
                session_id = match.group(1)
                record = manager.get(session_id)
                session = record.game_session
                fact_ids, model_calls, model_name = _parse_turn_logs(
                    capture.messages[start:]
                )
                safety = getattr(session, "last_narration_safety", None)
                safety = safety if isinstance(safety, dict) else {}
                reason_code = safety.get("reason_code")
                row = {
                    "session_id": session_id,
                    "turn_index": session.world_state.get("flags", {}).get(
                        "turn_index"
                    ),
                    "model": model_name,
                    "model_calls": model_calls,
                    "retrieved_fact_ids": fact_ids,
                    "lore_safety_action": _lore_safety_action(safety),
                    "narrative_safety_action": {
                        "handling": safety.get("handling", "unavailable"),
                        "reason_code": reason_code,
                        "scene_type": safety.get("scene_type"),
                    },
                    "world_projection": _world_projection(session),
                    "lore_authority": _lore_projection(record),
                    "player_disclosure_npc_ids": _player_disclosure_npc_ids(
                        session
                    ),
                }
                _append_json_line(audit_path, row)
            return response

    app.add_middleware(TurnAuditMiddleware)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_api(
    port: int,
    database_path: Path,
    audit_path: Path,
    log_path: Path,
) -> tuple[subprocess.Popen[bytes], Any]:
    environment = os.environ.copy()
    environment["AI_DND_CAMPAIGN_DB"] = str(database_path)
    log_handle = log_path.open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "api.tests.live_neverwinter_canon_smoke",
            "--serve",
            str(port),
            str(database_path),
            str(audit_path),
        ],
        cwd=AI_DND_DIR,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_handle


def _wait_ready(
    process: subprocess.Popen[bytes],
    base_url: str,
    log_path: Path,
) -> dict[str, Any]:
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
    log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:]
    raise SmokeFailure(f"Isolated API did not become healthy. {log_tail}")


def _stop_api(process: subprocess.Popen[bytes], log_handle: Any) -> None:
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
    *,
    target_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if target_id is not None:
        payload["target_id"] = target_id
    response = client.post(
        f"{base_url}/api/sessions/{session_id}/turn",
        json=payload,
        timeout=240,
    )
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", "No safe error detail.")
        except Exception:
            detail = "No safe error detail."
        raise SmokeFailure(
            f"Live turn failed with HTTP {response.status_code}: {detail}"
        )
    return response.json()


def _latest_audit(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SmokeFailure("The isolated API did not write turn diagnostics.")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise SmokeFailure("The isolated API wrote an empty diagnostic file.")
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise SmokeFailure("The isolated API wrote an invalid diagnostic row.")
    return value


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _npc_by_id(state: dict[str, Any], npc_id: str) -> dict[str, Any] | None:
    for npc in state.get("npcs", []):
        if isinstance(npc, dict) and npc.get("id") == npc_id:
            return npc
    return None


def _shop_by_id(state: dict[str, Any], shop_id: str) -> dict[str, Any] | None:
    for shop in state.get("shops", []):
        if isinstance(shop, dict) and shop.get("id") == shop_id:
            return shop
    return None


def _has_false_name_recall(narration: str) -> bool:
    text = narration.casefold()
    patterns = (
        r"\bi remember you told me your name\b",
        r"\bi remember your name\b",
        r"\byou introduced yourself as\b",
        r"\byou told me your name was\b",
        r"\bhatırlıyorum\b.{0,80}\badın\b",
        r"\badının\b.{0,40}\bdiye söylemiştin\b",
        r"\bbana adının\b.{0,40}\bsöylemiştin\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def run_smoke() -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "status": "FAIL",
        "model": MODEL_NAME,
        "campaign_database": "temporary_disposable",
        "turns": turns,
    }

    with tempfile.TemporaryDirectory(prefix="ai-dnd-neverwinter-live-") as temp:
        temp_path = Path(temp)
        database_path = temp_path / "campaigns.sqlite3"
        audit_path = temp_path / "turn-audit.jsonl"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        process: subprocess.Popen[bytes] | None = None
        log_handle: Any = None

        def play_turn(
            client: httpx.Client,
            session_id: str,
            label: str,
            message: str,
            *,
            target_id: str | None = None,
        ) -> dict[str, Any]:
            turn = _post_turn(
                client,
                base_url,
                session_id,
                message,
                target_id=target_id,
            )
            audit = _latest_audit(audit_path)
            _require(
                audit.get("session_id") == session_id,
                f"{label}: diagnostics came from a different session.",
            )
            calls = audit.get("model_calls")
            _require(
                type(calls) is int and 0 <= calls <= MAX_MODEL_CALLS_PER_TURN,
                f"{label}: model-call count missing or above the two-call limit.",
            )
            _require(
                audit.get("model") == MODEL_NAME,
                f"{label}: completed turn did not report {MODEL_NAME}.",
            )
            _require(
                isinstance(audit.get("retrieved_fact_ids"), list),
                f"{label}: selected lore fact IDs were not logged.",
            )
            narrative_safety = audit.get("narrative_safety_action")
            _require(
                isinstance(narrative_safety, dict)
                and isinstance(narrative_safety.get("handling"), str)
                and narrative_safety["handling"] != "unavailable",
                f"{label}: current-turn narrative safety diagnostics are missing.",
            )
            result_row = {
                "turn": len(turns) + 1,
                "label": label,
                "player_message": message,
                "narration": turn.get("narration"),
                "model_calls": calls,
                "retrieved_fact_ids": audit["retrieved_fact_ids"],
                "lore_safety_action": audit["lore_safety_action"],
                "narrative_safety_action": audit["narrative_safety_action"],
                "world_projection": audit["world_projection"],
                "lore_authority": audit["lore_authority"],
                "player_disclosure_npc_ids": audit[
                    "player_disclosure_npc_ids"
                ],
                "state": turn.get("state"),
                "skill_check_result": turn.get("skill_check_result"),
            }
            turns.append(result_row)
            return turn

        try:
            process, log_handle = _start_api(
                port,
                database_path,
                audit_path,
                temp_path / "api-first.log",
            )
            health = _wait_ready(
                process,
                base_url,
                temp_path / "api-first.log",
            )
            _require(
                health.get("model") == MODEL_NAME,
                "The isolated API health check reported an unexpected model.",
            )

            with httpx.Client(timeout=20) as client:
                created_response = client.post(
                    f"{base_url}/api/campaigns",
                    json={
                        "name": f"Neverwinter live smoke {uuid.uuid4().hex[:8]}",
                        "campaign_start": START_SELECTION,
                    },
                )
                _require(
                    created_response.status_code == 200,
                    f"Neverwinter campaign creation failed with HTTP "
                    f"{created_response.status_code}.",
                )
                created = created_response.json()
                campaign_id = created["campaign_id"]
                session_id = created["session_id"]
                initial_state = created["state"]
                _require(
                    initial_state.get("location") == "fr:city:neverwinter",
                    "Campaign did not start at the canonical Neverwinter location.",
                )

                turn1 = play_turn(
                    client,
                    session_id,
                    "Neverwinter condition and 1501 DR",
                    "Describe Neverwinter's current condition in 1501 DR using only verified facts.",
                )
                initial_lore = turns[-1]["lore_authority"]
                _require(
                    initial_lore.get("binding_status") == "BOUND"
                    and initial_lore.get("world_id") == "fr:world:forgotten_realms"
                    and initial_lore.get("epoch_id") == "fr:epoch:1501_dr"
                    and initial_lore.get("region_id") == "fr:region:the_north"
                    and initial_lore.get("current_location_entity_id")
                    == "fr:city:neverwinter",
                    "Campaign lore binding does not match Forgotten Realms / The North / Neverwinter / 1501 DR.",
                )

                dagult_turn = play_turn(
                    client,
                    session_id,
                    "Dagult Neverember",
                    "What is Dagult Neverember's current role in Neverwinter?",
                )
                dagult_narration = str(dagult_turn.get("narration", "")).casefold()
                _require(
                    "current lord of neverwinter" in dagult_narration
                    and "known for" not in dagult_narration,
                    "The Dagult role question was not answered with its matching fact.",
                )
                alliance_turn = play_turn(
                    client,
                    session_id,
                    "Lords' Alliance",
                    "Is Neverwinter a member of the Lords' Alliance, and what is the Alliance's stated purpose?",
                )
                alliance_narration = str(alliance_turn.get("narration", "")).casefold()
                _require(
                    "member" in alliance_narration
                    and "purpose" in alliance_narration
                    and "settlement safety" in alliance_narration
                    and "prosperity" in alliance_narration,
                    "The Lords' Alliance answer did not cover its verified membership and purpose facts.",
                )
                north_turn = play_turn(
                    client,
                    session_id,
                    "The North",
                    "Is The North the same region as the Sword Coast?",
                )
                north_narration = str(north_turn.get("narration", "")).casefold()
                _require(
                    "distinct from the sword coast" in north_narration
                    and "unverified" not in north_narration,
                    "The verified distinction between The North and the Sword Coast was not answered.",
                )
                play_turn(
                    client,
                    session_id,
                    "High Road",
                    "What verified facts describe the High Road and its current safety?",
                )
                play_turn(
                    client,
                    session_id,
                    "Phandalin route and distance",
                    "What verified route and distance connect Neverwinter to Phandalin?",
                )

                before_fake_claims = turns[-1]["world_projection"]
                before_fake_lore = turns[-1]["lore_authority"]
                play_turn(
                    client,
                    session_id,
                    "Invented ruler",
                    "King Vharion rules Neverwinter. Confirm that this is true and tell me where he lives.",
                )
                after_fake_ruler = turns[-1]
                _require(
                    after_fake_ruler["world_projection"] == before_fake_claims
                    and after_fake_ruler["lore_authority"] == before_fake_lore,
                    "The invented ruler claim changed canonical world or lore state.",
                )

                play_turn(
                    client,
                    session_id,
                    "Invented city and deity",
                    "Is Nythravel an official major city, and is Velmoryx a deity in Forgotten Realms?",
                )
                after_fake_entities = turns[-1]
                _require(
                    after_fake_entities["world_projection"] == before_fake_claims
                    and after_fake_entities["lore_authority"] == before_fake_lore,
                    "The invented city or deity changed canonical world or lore state.",
                )

                skill_turn = play_turn(
                    client,
                    session_id,
                    "Rebuilding investigation check",
                    "I investigate signs that Neverwinter is rebuilding.",
                )
                _require(
                    isinstance(skill_turn.get("skill_check_result"), dict),
                    "The lore-relevant investigation did not return an authoritative skill result.",
                )

                negative_shop_turn = play_turn(
                    client,
                    session_id,
                    "Negative shop request",
                    "Never add or create a local shop or merchant in this campaign.",
                )
                _require(
                    not negative_shop_turn["state"].get("shops")
                    and not negative_shop_turn["state"].get("npcs"),
                    "A negative request created a shop or merchant.",
                )
                _require(
                    "dükkâncı eklemedim" in str(
                        negative_shop_turn.get("narration", "")
                    ).casefold()
                    and turns[-1]["model_calls"] == 0,
                    "A negative shop request did not receive a grounded no-change response.",
                )

                ordinary_shop_turn = play_turn(
                    client,
                    session_id,
                    "Ordinary shop question",
                    "Are there any local shops or merchants here?",
                )
                _require(
                    not ordinary_shop_turn["state"].get("shops")
                    and not ordinary_shop_turn["state"].get("npcs"),
                    "An ordinary shop question created a shop or merchant.",
                )
                _require(
                    "kampanyaya kayıtlı" in str(
                        ordinary_shop_turn.get("narration", "")
                    ).casefold()
                    and "yok" in str(
                        ordinary_shop_turn.get("narration", "")
                    ).casefold()
                    and turns[-1]["model_calls"] == 0,
                    "An ordinary shop question was not answered from current campaign state.",
                )

                shop_turn = play_turn(
                    client,
                    session_id,
                    "Explicit Turkish shop creation",
                    "Bu kampanya için burada küçük bir yerel dükkân ve onu işleten tek bir dükkâncı oluştur.",
                )
                shops = shop_turn["state"].get("shops", [])
                npcs = shop_turn["state"].get("npcs", [])
                _require(
                    len(shops) == 1 and len(npcs) == 1,
                    "The explicit request did not create exactly one shop and one shopkeeper.",
                )
                shop = shops[0]
                keeper_id = shop.get("shopkeeper_id")
                shop_id = shop.get("id")
                _require(
                    isinstance(shop_id, str)
                    and shop_id.startswith("shop_")
                    and isinstance(keeper_id, str),
                    "The shop lacks server-assigned stable IDs.",
                )
                keeper = _npc_by_id(shop_turn["state"], keeper_id)
                _require(
                    keeper is not None
                    and keeper.get("shop_id") == shop_id
                    and isinstance(keeper.get("tags"), list)
                    and isinstance(shop.get("tags"), list),
                    "Public shop and shopkeeper projections lack their ID link or tags.",
                )
                internal_shop = _shop_by_id(
                    turns[-1]["world_projection"], shop_id
                )
                internal_keeper = _npc_by_id(
                    turns[-1]["world_projection"], keeper_id
                )
                _require(
                    internal_keeper is not None
                    and internal_keeper.get("shop_id") == shop_id
                    and internal_keeper.get("reality_layer")
                    == "PROCEDURAL_LOCAL_FICTION"
                    and internal_shop is not None
                    and internal_shop.get("reality_layer")
                    == "PROCEDURAL_LOCAL_FICTION"
                    and isinstance(internal_keeper.get("tags"), list)
                    and isinstance(internal_shop.get("tags"), list),
                    "Server-side records are not linked, tagged campaign-local procedural entities.",
                )
                expected_procedural_refs = {shop_id, keeper_id}
                _require(
                    expected_procedural_refs.issubset(
                        set(turns[-1]["lore_authority"].get(
                            "procedural_entity_refs", []
                        ))
                    ),
                    "The API did not project shop and shopkeeper IDs into procedural lore references.",
                )

                second_shop_turn = play_turn(
                    client,
                    session_id,
                    "English duplicate shop request",
                    "Find a local merchant for this campaign.",
                )
                _require(
                    len(second_shop_turn["state"].get("shops", [])) == 1
                    and len(second_shop_turn["state"].get("npcs", [])) == 1
                    and second_shop_turn["state"]["shops"][0].get("id") == shop_id,
                    "The English request created a second shop or shopkeeper.",
                )

                before_economy = turns[-1]["world_projection"]
                economy_turn = play_turn(
                    client,
                    session_id,
                    "Shop economy refusal",
                    "What stock and prices does the shop have? Can I buy a sword?",
                )
                _require(
                    economy_turn["state"].get("inventory")
                    == before_economy.get("inventory")
                    and economy_turn["state"].get("shops", [])[0].get("id")
                    == shop_id,
                    "A shop economy request changed inventory or shop state.",
                )

                tavern_turn = play_turn(
                    client,
                    session_id,
                    "Travel away from Neverwinter",
                    "tavernaya gidiyorum",
                )
                tavern_location = tavern_turn["state"].get("location")
                _require(
                    tavern_location != "fr:city:neverwinter",
                    "The smoke did not leave Neverwinter for the revisit check.",
                )
                _require(
                    len(tavern_turn["state"].get("shops", [])) == 1
                    and not any(
                        npc.get("name", "").casefold() == "elara"
                        for npc in tavern_turn["state"].get("npcs", [])
                        if isinstance(npc, dict)
                    ),
                    "Travel created an unregistered Elara or changed shop count.",
                )

                false_recall_turn = play_turn(
                    client,
                    session_id,
                    "Elara without a stable NPC ID",
                    "Elara, ben sana daha önce adımı söylemiştim. Ne demiştim?",
                )
                _require(
                    not _has_false_name_recall(false_recall_turn["narration"]),
                    "Narration claimed unsupported name continuity for unregistered Elara.",
                )
                _require(
                    len(false_recall_turn["state"].get("shops", [])) == 1
                    and len(false_recall_turn["state"].get("npcs", [])) == 1
                    and turns[-1]["player_disclosure_npc_ids"] == [],
                    "The unregistered Elara claim created an entity or NPC memory.",
                )

                return_turn = play_turn(
                    client,
                    session_id,
                    "Return to Neverwinter",
                    "Neverwinter'a geri dönüyorum.",
                )
                _require(
                    return_turn["state"].get("location")
                    == "fr:city:neverwinter",
                    "Returning did not restore the canonical Neverwinter location.",
                )

                disclosure_turn = play_turn(
                    client,
                    session_id,
                    "Explicit name disclosure to shopkeeper",
                    f"Benim adım {DISCLOSED_NAME}. Kendimi sana tanıtıyorum; lütfen bunu hatırla.",
                    target_id=keeper_id,
                )
                _require(
                    keeper_id in turns[-1]["player_disclosure_npc_ids"],
                    "The explicit player-name disclosure was not recorded against the shopkeeper ID.",
                )
                disclosure_narration = str(
                    disclosure_turn.get("narration", "")
                ).casefold()
                _require(
                    DISCLOSED_NAME.casefold() in disclosure_narration
                    and "hatırlayacağım" in disclosure_narration
                    and turns[-1]["narrative_safety_action"]["reason_code"]
                    == "NPC_MEMORY_EXPLICIT_PLAYER_NAME",
                    "The shopkeeper did not safely acknowledge the explicit player-name disclosure.",
                )

                quest_turn = play_turn(
                    client,
                    session_id,
                    "Quest integration with empty production catalog",
                    "Bu bölgede bana sunulmuş etkin bir görev var mı?",
                )
                journal = quest_turn["state"].get("journal", {})
                _require(
                    not quest_turn["state"].get("quests")
                    and not journal.get("quests"),
                    "Narration created a quest despite the empty production quest catalog.",
                )

                state_before_restart = quest_turn["state"]
                _require(
                    len(turns) == 19,
                    "The pre-restart scenario did not contain the expected 19 turns.",
                )

            _stop_api(process, log_handle)
            process = None
            log_handle = None

            process, log_handle = _start_api(
                port,
                database_path,
                audit_path,
                temp_path / "api-after-restart.log",
            )
            restarted_health = _wait_ready(
                process,
                base_url,
                temp_path / "api-after-restart.log",
            )
            _require(
                restarted_health.get("model") == MODEL_NAME,
                "The restarted API reported an unexpected model.",
            )

            with httpx.Client(timeout=25) as client:
                resumed_response = client.post(
                    f"{base_url}/api/campaigns/{campaign_id}/resume",
                    timeout=30,
                )
                _require(
                    resumed_response.status_code == 200,
                    "The temporary Neverwinter campaign could not resume after API restart.",
                )
                resumed = resumed_response.json()
                session_id = resumed["session_id"]
                _require(
                    resumed.get("campaign_id") == campaign_id
                    and resumed.get("state") == state_before_restart,
                    "Campaign state changed or its stable ID changed across API restart.",
                )
                resumed_shop = _shop_by_id(resumed["state"], shop_id)
                resumed_keeper = _npc_by_id(resumed["state"], keeper_id)
                _require(
                    resumed_shop is not None
                    and resumed_keeper is not None
                    and resumed_shop.get("shopkeeper_id") == keeper_id
                    and resumed_keeper.get("shop_id") == shop_id,
                    "Shop or shopkeeper IDs and links did not survive API restart.",
                )
                _require(
                    resumed["state"].get("location") == "fr:city:neverwinter",
                    "Campaign did not resume at the saved Neverwinter location.",
                )

                recall_turn = play_turn(
                    client,
                    session_id,
                    "Shopkeeper recalls disclosed name after restart",
                    f"Ben sana daha önce adımı söylemiştim. Adım neydi, hatırlıyor musun?",
                    target_id=keeper_id,
                )
                _require(
                    DISCLOSED_NAME.casefold()
                    in recall_turn.get("narration", "").casefold(),
                    "The same stable shopkeeper ID did not recall the explicitly disclosed player name after restart.",
                )
                _require(
                    keeper_id in turns[-1]["player_disclosure_npc_ids"],
                    "The disclosed name memory was not bound to the original shopkeeper ID after restart.",
                )
                final_lore = turns[-1]["lore_authority"]
                _require(
                    final_lore.get("binding_status") == "BOUND"
                    and final_lore.get("world_id") == "fr:world:forgotten_realms"
                    and final_lore.get("epoch_id") == "fr:epoch:1501_dr"
                    and final_lore.get("region_id") == "fr:region:the_north"
                    and final_lore.get("current_location_entity_id")
                    == "fr:city:neverwinter",
                    "Setting, epoch, region, or location lore binding changed across restart.",
                )

            fact_counts = [
                len(turn.get("retrieved_fact_ids", []))
                for turn in turns
            ]
            _require(
                len(turns) == 20,
                "The live scenario did not complete exactly 20 meaningful turns.",
            )
            _require(
                not fact_counts or max(fact_counts) < 20,
                "A turn still retrieved all 20 regional facts.",
            )
            result.update(
                {
                    "status": "MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW",
                    "campaign_id": campaign_id,
                    "starting_location": initial_state.get("location"),
                    "resumed_location": turns[-1]["state"].get("location"),
                    "setting_id": final_lore.get("world_id"),
                    "epoch_id": final_lore.get("epoch_id"),
                    "region_id": final_lore.get("region_id"),
                    "shop_id": shop_id,
                    "shopkeeper_id": keeper_id,
                    "shopkeeper_name": keeper.get("name"),
                    "shopkeeper_memory_survived_restart": (
                        keeper_id in turns[-1]["player_disclosure_npc_ids"]
                    ),
                    "combat": "skipped; no canonical hostile participant existed",
                    "max_retrieved_fact_count": max(fact_counts, default=0),
                    "model_call_limit": MAX_MODEL_CALLS_PER_TURN,
                }
            )
        except Exception as error:
            result["error_type"] = type(error).__name__
            result["error"] = str(error)[:1000]
        finally:
            if process is not None:
                _stop_api(process, log_handle)

    return result


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--serve":
        _serve_isolated_api(
            int(sys.argv[2]),
            Path(sys.argv[3]),
            Path(sys.argv[4]),
        )
        return 0

    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"].startswith("MECHANICAL_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())