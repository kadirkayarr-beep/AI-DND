"""50-turn and 100-turn live smokes.

Missing qwen3:8b is BLOCKED, not FAIL. REVIEW_PENDING is not PASS.

    python -m api.tests.live_incident_long_smoke
    python -m api.tests.live_incident_long_smoke 50
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"
LINES = (
    "etrafa bakıyorum",
    "bir saat dinleniyorum",
    "Neverwinter sokaklarında yürüyorum.",
    "Hana doğru yürüyorum.",
    "Burada biraz bekliyorum.",
)


def _emit(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _blocked(reason, **extra):
    return _emit({
        "final_gate_status": "BLOCKED",
        "live_generation": "unverified",
        "reason": reason,
        "model": MODEL_NAME,
        "review_pending_is_pass": False,
        "turns": {"planned": [50, 100], "executed": 0},
        **extra,
    })


def _quest_ids(state):
    quests = state.get("quests") if isinstance(state, dict) else None
    if not isinstance(quests, list):
        return []
    found = []
    for quest in quests:
        if isinstance(quest, dict):
            found.append(quest.get("quest_id") or quest.get("id"))
        else:
            found.append(quest)
    return found


def _run_count(count, canon):
    os.environ["AI_DND_EMERGENCE_LIVE"] = "1"
    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    # The player API refuses turns until both variables exist. A local Ollama
    # has no proxy, so the smoke supplies a non-secret marker only for loopback.
    if not os.environ.get("OLLAMA_PROXY_TOKEN"):
        host = os.environ["OLLAMA_HOST"]
        if not host.startswith("http://127.0.0.1") and not host.startswith("http://localhost"):
            raise canon.SmokeFailure("OLLAMA_PROXY_TOKEN is required away from loopback.")
        os.environ["OLLAMA_PROXY_TOKEN"] = "loopback"
    with tempfile.TemporaryDirectory(prefix="ai-dnd-long-smoke-") as temp:
        temp_path = Path(temp)
        database_path = temp_path / "campaigns.sqlite3"
        audit_path = temp_path / "turn-audit.jsonl"
        port = canon._free_port()
        base_url = f"http://127.0.0.1:{port}"
        process, log_handle = canon._start_api(
            port, database_path, audit_path, temp_path / "api.log",
        )
        rows = []
        try:
            canon._wait_ready(process, base_url, temp_path / "api.log")
            import httpx
            with httpx.Client(timeout=20) as client:
                created = client.post(
                    f"{base_url}/api/campaigns",
                    json={
                        "name": f"Neverwinter long smoke {uuid.uuid4().hex[:8]}",
                        "campaign_start": canon.START_SELECTION,
                    },
                )
                if created.status_code != 200:
                    raise canon.SmokeFailure(
                        f"Campaign creation failed with HTTP {created.status_code}."
                    )
                body = created.json()
                campaign_id = body["campaign_id"]
                session_id = body["session_id"]
                if body.get("state", {}).get("location") != "fr:city:neverwinter":
                    raise canon.SmokeFailure("Campaign did not start in Neverwinter.")
                quests = _quest_ids(body.get("state", {}))
                seen_incidents = []
                for index in range(count):
                    message = LINES[index % len(LINES)]
                    turn = canon._post_turn(client, base_url, session_id, message)
                    audit = canon._latest_audit(audit_path)
                    calls = audit.get("model_calls")
                    if type(calls) is not int or calls > canon.MAX_MODEL_CALLS_PER_TURN:
                        raise canon.SmokeFailure(
                            f"Turn {index + 1} used {calls} model calls."
                        )
                    if calls > 0 and audit.get("model") != MODEL_NAME:
                        raise canon.SmokeFailure(
                            f"Turn {index + 1} did not use {MODEL_NAME}."
                        )
                    state = turn.get("state") if isinstance(turn.get("state"), dict) else {}
                    location = state.get("location")
                    if isinstance(location, str) and (
                        "waterdeep" in location.casefold() or "baldur" in location.casefold()
                    ):
                        raise canon.SmokeFailure(
                            f"Turn {index + 1} entered an unreviewed city: {location}."
                        )
                    narration = turn.get("narration") if isinstance(turn.get("narration"), str) else ""
                    folded = narration.casefold()
                    if "neverember" in folded and any(
                        word in folded for word in ("öldü", "ölür", "dead", "killed")
                    ):
                        raise canon.SmokeFailure("Protected identity was killed in narration.")
                    incidents = state.get("scene_incidents") or []
                    if not isinstance(incidents, list):
                        raise canon.SmokeFailure("scene_incidents is not a list.")
                    for incident in incidents:
                        if isinstance(incident, dict) and "hidden_facts" in incident:
                            raise canon.SmokeFailure("Hidden facts reached the player packet.")
                        ref = incident.get("ref") if isinstance(incident, dict) else None
                        if isinstance(ref, str) and ref not in seen_incidents:
                            seen_incidents.append(ref)
                    current_quests = _quest_ids(state)
                    if current_quests != quests:
                        raise canon.SmokeFailure(
                            f"Turn {index + 1} changed the quest list."
                        )
                    rows.append({
                        "turn": index + 1,
                        "model_calls": calls,
                        "location": location,
                        "scene_incidents": [item.get("ref") for item in incidents if isinstance(item, dict)],
                    })
                    if index + 1 == min(5, count):
                        resumed = client.post(f"{base_url}/api/campaigns/{campaign_id}/resume")
                        if resumed.status_code != 200:
                            raise canon.SmokeFailure(
                                f"Resume failed with HTTP {resumed.status_code}."
                            )
                        session_id = resumed.json()["session_id"]
                        resumed_refs = [
                            item.get("ref") for item in (resumed.json().get("state", {}).get("scene_incidents") or [])
                            if isinstance(item, dict)
                        ]
                        if resumed_refs != rows[-1]["scene_incidents"]:
                            raise canon.SmokeFailure("Resume dropped scene incidents.")
            calls_seen = [row["model_calls"] for row in rows]
            if count >= 1 and max(calls_seen, default=0) < 1:
                raise canon.SmokeFailure("No turn called the model.")
            return {
                "executed": count,
                "max_model_calls": max(calls_seen, default=0),
                "turns_with_model": sum(1 for item in calls_seen if item),
                "scene_incident_refs": seen_incidents,
                "quests_unchanged": True,
                "resume_checked": True,
            }
        finally:
            canon._stop_api(process, log_handle)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import game
        from incidents import profiles
        from api.tests import live_neverwinter_canon_smoke as canon
    except Exception as error:
        return _blocked(f"import failed: {error}")

    loaded = profiles.load("neverwinter.v1")
    waterdeep = profiles.load("waterdeep.v1")
    baldurs_gate = profiles.load("baldurs_gate.v1")
    if waterdeep is not None or baldurs_gate is not None:
        return _emit({
            "final_gate_status": "FAIL",
            "reason": "An unreviewed city profile loaded.",
            "review_pending_is_pass": False,
        }, 1)
    if loaded is None:
        return _blocked("Neverwinter profile did not load.")
    try:
        game.ollama.list()
    except Exception as error:
        return _blocked(f"Ollama is unreachable: {error}")

    counts = [int(item) for item in argv] if argv else [50, 100]
    runs = []
    try:
        for count in counts:
            runs.append(_run_count(count, canon))
    except Exception as error:
        return _emit({
            "final_gate_status": "FAIL",
            "live_generation": "failed",
            "reason": str(error)[:1000],
            "neverwinter_profile": loaded["review_status"],
            "waterdeep_profile": "UNREVIEWED_DISABLED",
            "baldurs_gate_profile": "UNREVIEWED_DISABLED",
            "review_pending_is_pass": False,
            "model": MODEL_NAME,
            "runs": runs,
        }, 1)

    return _emit({
        "final_gate_status": "PASS",
        "live_generation": "verified",
        "neverwinter_profile": loaded["review_status"],
        "waterdeep_profile": "UNREVIEWED_DISABLED",
        "baldurs_gate_profile": "UNREVIEWED_DISABLED",
        "review_pending_is_pass": False,
        "model": MODEL_NAME,
        "turns": {"planned": counts, "executed": sum(item["executed"] for item in runs)},
        "runs": runs,
        "note": "Look, rest, and local movement lines use the existing triggers. This run checks call budget, quest isolation, resume, scene incidents, and unreviewed cities. It is not a release PASS.",
    })


if __name__ == "__main__":
    raise SystemExit(main())
