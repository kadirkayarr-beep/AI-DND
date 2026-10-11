"""Real network acceptance against running production handlers, no injections.

Uses the normal public campaign/turn/save/resume routes. A second running
process can supply --resume-base to demonstrate disk-backed restoration.
Leaves the disposable campaign available for inspection. Existing owner
campaigns are never listed, selected, modified or deleted.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import sys
import traceback
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_regression_evidence as suite_evidence

DEFAULT_ARCHIVE = ROOT / "docs/evidence/http-runs"
SUITE_ARCHIVE = ROOT / "docs/evidence/suite-runs"
HISTORICAL = ROOT / "docs/evidence/bounded-encounter-http.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def capture_verifier_source(archive_root, output):
    """Reuse suite hashes; generated HTTP records are not verifier source.

    This identifies only the local checkout. It cannot identify a server,
    even if that server happens to use a localhost URL.
    """
    excluded = [DEFAULT_ARCHIVE]
    if output is not None:
        excluded.append(Path(output))
    snapshot = suite_evidence.source_snapshot(archive_root, excluded_paths=excluded)
    return {
        **snapshot, "captured_at": now(), "algorithm": "sha256",
        "fingerprint": snapshot["working_tree_sha256"],
        "identity_scope": "local_verifier_checkout_only",
    }


def require_http_path(path):
    resolved = Path(path).resolve()
    if resolved == HISTORICAL.resolve() or resolved.is_relative_to(SUITE_ARCHIVE.resolve()):
        raise ValueError("HTTP evidence must not use historical evidence or suite archives")
    return resolved


class Terminated(BaseException):
    pass


def run(base, resume_base, output=None, archive_root=DEFAULT_ARCHIVE):
    """Retain every attempt before HTTP; an optional output is an exclusive export."""
    root = require_http_path(archive_root)
    root.mkdir(parents=True, exist_ok=True)
    started = now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
    directory = root / run_id
    directory.mkdir()  # Exclusive, even if the generated ID collides.
    record_path = directory / "run.json"
    argv = list(sys.orig_argv)
    evidence = {
        "schema_version": 1, "evidence_kind": "http_acceptance",
        "run_label": "NEW RUN", "historical_certification": False,
        "run_id": run_id, "archive_path": str(record_path),
        "command": {"argv": argv, "shell": shlex.join(argv)},
        "cwd": str(Path.cwd()), "started_at": started,
        "ended_at": None, "exit_status": None, "status": "RUNNING",
        "transport": "real HTTP", "fixture_injection": False,
        "base": base, "resume_base": resume_base, "turns": [],
        "requests": [], "requested_output": str(output) if output else None,
        "verifier_source": {"before": None, "after": None, "capture_errors": {}},
        "source_change_detection": {
            "changed": None, "status": "unverified", "unchanged_verifier_source": False,
        },
        "server_source_identity": {
            role: {
                "endpoint": endpoint, "status": "unverified", "revision": None,
                "fingerprint": None,
                "basis": "No independent server source identity captured; "
                         "the local verifier fingerprint does not identify this server.",
            }
            for role, endpoint in (("acceptance", base), ("resume", resume_base))
        },
    }

    def checkpoint():
        temporary = directory / "run.json.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(record_path)

    checkpoint()
    print("NEW RUN HTTP acceptance archive:", record_path, flush=True)
    export = None
    previous_handler = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise Terminated("SIGTERM")

    code = 2
    try:
        signal.signal(signal.SIGTERM, terminate)
        try:
            evidence["verifier_source"]["before"] = capture_verifier_source(root, output)
        except Exception as error:
            evidence["verifier_source"]["capture_errors"]["before"] = {
                "type": type(error).__name__, "message": str(error),
            }
            raise
        checkpoint()
        if output is not None:
            destination = require_http_path(output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            export = destination.open("x", encoding="utf-8")
            # A hard kill still leaves an identifiable, incomplete export.
            json.dump(evidence, export, ensure_ascii=False, indent=2)
            export.write("\n")
            export.flush()
            os.fsync(export.fileno())
        execute(base, resume_base, evidence, checkpoint)
        evidence["status"], code = "PASS", 0
    except (KeyboardInterrupt, Terminated) as error:
        evidence["status"] = "INTERRUPTED"
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        code = 143 if isinstance(error, Terminated) else 130
    except Exception as error:
        evidence["status"] = "FAIL"
        evidence["error"] = {
            "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(),
        }
        code = 1 if isinstance(error, AssertionError) else 2
    finally:
        # Do not let another SIGTERM interrupt final evidence retention.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            try:
                after = capture_verifier_source(root, output)
                evidence["verifier_source"]["after"] = after
                before = evidence["verifier_source"]["before"]
                if before is not None:
                    changed = (before["fingerprint"] != after["fingerprint"]
                               or before["revision"] != after["revision"])
                    evidence["source_change_detection"].update(
                        changed=changed, status="changed" if changed else "unchanged",
                        unchanged_verifier_source=not changed,
                    )
            except Exception as error:
                evidence["verifier_source"]["capture_errors"]["after"] = {
                    "type": type(error).__name__, "message": str(error),
                }
                # Retain the original failed/interrupted result. A successful
                # acceptance without a final source capture is not certified.
                if code == 0:
                    evidence["status"], code = "FAIL", 2
            evidence["ended_at"], evidence["exit_status"] = now(), code
            for event in evidence["requests"]:
                if event["status"] == "RUNNING":
                    event.update(status=evidence["status"], ended_at=evidence["ended_at"])
            checkpoint()
            if export is not None:
                try:
                    export.seek(0)
                    json.dump(evidence, export, ensure_ascii=False, indent=2)
                    export.write("\n")
                    export.truncate()
                    export.flush()
                    os.fsync(export.fileno())
                except Exception as error:
                    evidence["status"], code = "FAIL", 2
                    evidence["exit_status"] = code
                    evidence["ended_at"] = now()
                    evidence["export_error"] = {
                        "type": type(error).__name__, "message": str(error),
                    }
                    checkpoint()
        finally:
            if export is not None:
                export.close()
            signal.signal(signal.SIGTERM, previous_handler)
    print(f"NEW RUN HTTP acceptance: {evidence['status']} (exit {code}); {record_path}")
    return code


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from dictionaries(item)
    elif isinstance(value, list):
        for item in value:
            yield from dictionaries(item)


def execute(base, resume_base, evidence, checkpoint):
    def request(method, path, body=None, server=base):
        event = {"method": method, "path": path, "server": server, "started_at": now(),
                 "ended_at": None, "status": "RUNNING"}
        evidence["requests"].append(event)
        checkpoint()
        data = json.dumps(body).encode() if body is not None else None
        req = Request(server.rstrip("/") + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            event["http_status"] = response.status
            assert response.status == 200, response.status
            result = json.load(response)
        event.update(ended_at=now(), status="PASS")
        checkpoint()
        return result

    option = request("GET", "/api/game/campaign-start-options")["settings"][0]
    region = option["regions"][0]
    creation = request("POST", "/api/game/campaigns", {
        "name": "Disposable native courtyard acceptance",
        "campaign_start": {
            "setting_id": option["setting_id"], "region_pack_id": region["region_pack_id"],
            "region_id": region["region_id"],
            "starting_location_id": region["starting_locations"][0]["entity_id"],
        },
    })
    campaign_id, sid = creation["campaign_id"], creation["session_id"]
    evidence.update(campaign_id=campaign_id, session_id=sid)
    checkpoint()
    turns = evidence["turns"]
    try:
        def turn(message, steps=None):
            body = {"message": message, "action_id": str(uuid4())}
            if steps is not None:
                state = request("GET", f"/api/game/sessions/{sid}/state")
                combat = state["combat"]
                body.update(combat_action={"steps": steps}, combat_id=combat["combat_id"],
                            combat_round=combat["round"], combat_turn_index=combat["current_turn_index"])
            result = request("POST", f"/api/game/sessions/{sid}/turn", body)
            turns.append({"request": body, "response": result})
            checkpoint()
            return body, result

        _, entered = turn("Avlu karşılaşmasına gir")
        assert not entered["state"]["combat"]["active"]
        seen = entered["state"]["bounded_encounter"]["visible_opponent"]
        assert seen["statblock_id"] == "mm2024.commoner"
        assert seen["distance_ft"] == 60
        assert "printed p.77" in seen["source"]
        _, started = turn("Avlu çatışmasını başlat")
        dash_result = started
        if not any(d.get("action") == "monster_dash" for d in dictionaries(started)):
            _, dash_result = turn("Turumu bitiriyorum", [{"kind": "end_turn"}])
        dash = next(d for d in dictionaries(dash_result) if d.get("action") == "monster_dash")
        state_after_dash = dash_result["state"]
        seen_after_dash = state_after_dash["bounded_encounter"]["visible_opponent"]
        assert seen_after_dash["distance_ft"] == 5
        assert seen_after_dash["node_id"] == "courtyard_near"
        budget = state_after_dash["combat"]["action_economy"]["actors"][seen["npc_id"]]
        # The response is returned after the monster turn has completed, so
        # its per-turn base-action flag has already reset. The reported
        # monster_dash event above is the authoritative action-use evidence.
        assert budget["movement_used"] == 55 and budget["dash_count"] == 1
        assert dash["status"] == "resolved" and dash["outcome"] == "dash"
        body, attacked = turn("Turumu bitiriyorum", [{"kind": "end_turn"}])
        attack = next(d for d in dictionaries(attacked) if d.get("action") == "enemy_attack")
        assert attack["target_id"] == "player"
        assert attack["weapon_id"] == "commoner_club" and attack["attack_bonus"] == 2
        assert attack["damage_type"] == "bludgeoning"
        request("POST", f"/api/game/campaigns/{campaign_id}/save")
        resumed = request("POST", f"/api/game/campaigns/{campaign_id}/resume", server=resume_base)
        assert resumed["state"] == attacked["state"]
        resumed_sid = resumed["session_id"]
        history_before = request("GET", f"/api/game/campaigns/{campaign_id}", server=resume_base)["history"]
        replay = request("POST", f"/api/game/sessions/{resumed_sid}/turn", body, server=resume_base)
        expected = dict(attacked, session_id=resumed_sid)
        assert replay == expected
        assert request("GET", f"/api/game/sessions/{resumed_sid}/state", server=resume_base) == attacked["state"]
        assert request("GET", f"/api/game/campaigns/{campaign_id}", server=resume_base)["history"] == history_before
        evidence.update({
            "campaign_id": campaign_id,
            "second_process_resume": base.rstrip("/") != resume_base.rstrip("/"),
            "scenario": entered["state"]["bounded_encounter"],
            "movement": {"result": dash, "budget": budget, "distance_after_ft": 5},
            "attack": attack, "save": "PASS", "resume": "PASS", "replay": "PASS",
            "replay_state_unchanged": True, "replay_history_unchanged": True,
            "turns": turns, "replay_response": replay,
        })
    finally:
        print("Disposable acceptance campaign retained for review:", campaign_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--resume-base")
    parser.add_argument("--output", help="Optional new export filename; existing files are refused")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE,
                        help="Durable HTTP archive directory (never a suite archive)")
    args = parser.parse_args()
    sys.exit(run(args.base, args.resume_base or args.base, args.output, args.archive_root))