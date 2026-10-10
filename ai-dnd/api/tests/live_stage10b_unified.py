"""Isolated Stage 10B continuity run. Disposable SQLite. Real session RNG."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx

from api.tests import live_neverwinter_canon_smoke as smoke

EVIDENCE = Path(os.environ["AI_DND_STAGE10B_EVIDENCE_DIR"]) if os.environ.get("AI_DND_STAGE10B_EVIDENCE_DIR") else Path(__file__).resolve().parents[3] / ".local" / "evidence" / "stage10b-acceptance-v1-20261009"
SHOP_CREATE = "Bu kampanya için burada küçük bir yerel dükkân ve onu işleten tek bir dükkâncı oluştur."
SHOP_FIND = "Buradaki dükkâncıyı bul."
TAVERN = "Tavernaya gidiyorum."
RETURN = "Neverwinter'a geri dönüyorum."
NAME = "Benim adım Arven. Bunu hatırla."
RECALL = "Adımı hatırlıyor musun?"
UNKNOWN = "Elara adımı biliyor mu?"
QUEST = "Bu bölgede bana sunulmuş etkin bir görev var mı?"


def _parent(state: dict[str, Any]) -> Any:
    locations = state.get("locations") or {}
    current = locations.get(state.get("location")) if isinstance(locations, dict) else None
    if isinstance(current, dict):
        return current.get("parent_location_id")
    return None


def _combat(state: dict[str, Any]) -> dict[str, Any]:
    combat = state.get("combat") or {}
    return combat if isinstance(combat, dict) else {}


def _post(client: httpx.Client, base: str, session_id: str, message: str, audit_path: Path, **extra: Any) -> dict[str, Any]:
    payload = {"message": message, **extra}
    response = client.post(f"{base}/api/sessions/{session_id}/turn", json=payload, timeout=240)
    body: dict[str, Any]
    try:
        parsed = response.json()
        body = parsed if isinstance(parsed, dict) else {"raw": parsed}
    except Exception:
        body = {"raw": response.text[:500]}
    audit = None
    if audit_path.exists() and response.status_code == 200:
        lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line]
        if lines:
            audit = json.loads(lines[-1])
    return {"status": response.status_code, "body": body, "audit": audit, "request": payload}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    database = EVIDENCE / "unified-campaign.sqlite3"
    if database.exists():
        database.unlink()
    audit_path = EVIDENCE / "unified-audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    log_path = EVIDENCE / "unified-api.log"
    port = smoke._free_port()
    base = f"http://127.0.0.1:{port}"
    rows: list[dict[str, Any]] = []
    failures: list[str] = []

    def note(step: str, row: dict[str, Any]) -> None:
        recorded = dict(row)
        recorded["step"] = step
        rows.append(recorded)

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    process, log_handle = smoke._start_api(port, database, audit_path, log_path)
    before: dict[str, Any] = {"active": False}
    try:
        health = smoke._wait_ready(process, base, log_path)
        with httpx.Client(timeout=30) as client:
            created = client.post(f"{base}/api/campaigns", json={
                "name": f"S10B unified {uuid.uuid4().hex[:8]}",
                "campaign_start": smoke.START_SELECTION,
            })
            check(created.status_code == 200, f"create HTTP {created.status_code}")
            created_body = created.json()
            session_id = created_body["session_id"]
            campaign_id = created_body["campaign_id"]
            state = created_body["state"]
            check(state.get("location") == "fr:city:neverwinter", "start location")
            note("start", {"campaign_id": campaign_id, "location": state.get("location"), "hp": state["character"]["current_hp"]})

            shop = _post(client, base, session_id, SHOP_CREATE, audit_path, action_id=str(uuid.uuid4()))
            shop_state = (shop["body"].get("state") or {})
            shops = shop_state.get("shops") or []
            note("shop_create", {"status": shop["status"], "shops": len(shops), "calls": (shop["audit"] or {}).get("model_calls")})
            check(shop["status"] == 200 and len(shops) == 1, "shop was not created once")
            found = _post(client, base, session_id, SHOP_FIND, audit_path, action_id=str(uuid.uuid4()))
            found_shops = ((found["body"].get("state") or {}).get("shops") or [])
            note("shop_find", {"status": found["status"], "shops": len(found_shops)})
            check(found["status"] == 200 and len(found_shops) == 1, "find created or lost a shop")

            entered = _post(client, base, session_id, TAVERN, audit_path, action_id=str(uuid.uuid4()))
            tavern_state = entered["body"].get("state") or {}
            tavern_id = tavern_state.get("location")
            note("tavern_enter", {"location": tavern_id, "parent": _parent(tavern_state)})
            check(tavern_id != "fr:city:neverwinter" and _parent(tavern_state) == "fr:city:neverwinter", "tavern parent")
            back = _post(client, base, session_id, RETURN, audit_path, action_id=str(uuid.uuid4()))
            back_state = back["body"].get("state") or {}
            note("tavern_return", {"location": back_state.get("location")})
            check(back_state.get("location") == "fr:city:neverwinter", "return did not restore Neverwinter")
            again = _post(client, base, session_id, TAVERN, audit_path, action_id=str(uuid.uuid4()))
            again_state = again["body"].get("state") or {}
            note("tavern_reentry", {"location": again_state.get("location")})
            check(again_state.get("location") == tavern_id, "reentry opened a different tavern")
            home = _post(client, base, session_id, RETURN, audit_path, action_id=str(uuid.uuid4()))
            check((home["body"].get("state") or {}).get("location") == "fr:city:neverwinter", "second return")

            keeper = next((
                npc.get("id") for npc in (shop_state.get("npcs") or [])
                if isinstance(npc, dict) and (npc.get("shop_id") or str(npc.get("role") or "").casefold() == "shopkeeper")
            ), None)
            check(isinstance(keeper, str), "shopkeeper id was not published")
            named = _post(client, base, session_id, NAME, audit_path, action_id=str(uuid.uuid4()), target_id=keeper)
            note("name", {"status": named["status"], "narration": named["body"].get("narration")})
            check(named["status"] == 200 and "Arven" in str(named["body"].get("narration")), "name disclosure")

        smoke._stop_api(process, log_handle)
        process, log_handle = smoke._start_api(port, database, audit_path, EVIDENCE / "unified-api-restart-name.log")
        smoke._wait_ready(process, base, EVIDENCE / "unified-api-restart-name.log")
        with httpx.Client(timeout=30) as client:
            resumed = client.post(f"{base}/api/campaigns/{campaign_id}/resume")
            check(resumed.status_code == 200, f"name resume HTTP {resumed.status_code}")
            session_id = resumed.json()["session_id"]
            recall = _post(client, base, session_id, RECALL, audit_path, action_id=str(uuid.uuid4()), target_id=keeper)
            note("recall", {"narration": recall["body"].get("narration")})
            check("Arven" in str(recall["body"].get("narration")), "name was not recalled")
            resumed_state = resumed.json()["state"]
            other_npc = next((
                npc.get("id") for npc in (resumed_state.get("npcs") or [])
                if isinstance(npc, dict) and npc.get("id") and npc.get("id") != keeper
            ), None)
            check(isinstance(other_npc, str), "no second NPC was available for isolation")
            unknown = _post(client, base, session_id, RECALL, audit_path, action_id=str(uuid.uuid4()), target_id=other_npc)
            note("unknown_name", {"target": other_npc, "narration": unknown["body"].get("narration")})
            check("Arven" not in str(unknown["body"].get("narration")), "unregistered NPC received the name")
            quest = _post(client, base, session_id, QUEST, audit_path, action_id=str(uuid.uuid4()))
            quest_state = quest["body"].get("state") or {}
            note("quest", {"narration": quest["body"].get("narration"), "quests": quest_state.get("quests"), "calls": (quest["audit"] or {}).get("model_calls")})
            quest_text = str(quest["body"].get("narration") or "")
            check(quest["status"] == 200 and not quest_state.get("quests") and "görev" in quest_text.casefold() and "hangisini" not in quest_text.casefold(), "quest catalog did not answer from empty state")

            action_id = str(uuid.uuid4())
            first = _post(client, base, session_id, "Etrafıma bakıyorum.", audit_path, action_id=action_id)
            replay = _post(client, base, session_id, "Etrafıma bakıyorum.", audit_path, action_id=action_id)
            note("idempotent_replay", {"first": first["status"], "replay": replay["status"], "same_narration": first["body"].get("narration") == replay["body"].get("narration")})
            check(replay["status"] == 200 and first["body"].get("narration") == replay["body"].get("narration"), "identical replay changed the narration")
            conflict = _post(client, base, session_id, "Bambaşka bir cümle", audit_path, action_id=action_id)
            note("idempotent_conflict", {"status": conflict["status"]})
            check(conflict["status"] == 409, "conflicting action id was not rejected")

            shared = str(uuid.uuid4())
            barrier = threading.Barrier(2)
            concurrent: list[dict[str, Any]] = []

            def once() -> None:
                barrier.wait()
                with httpx.Client(timeout=240) as local:
                    concurrent.append(_post(local, base, session_id, "Yakınımdaki kişilere bakıyorum.", audit_path, action_id=shared))

            threads = [threading.Thread(target=once) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            statuses = sorted(item["status"] for item in concurrent)
            narrations = {str(item["body"].get("narration")) for item in concurrent if item["status"] == 200}
            note("idempotent_concurrent", {"statuses": statuses, "narrations": len(narrations)})
            check(statuses.count(200) >= 1 and len(narrations) <= 1, "concurrent duplicate did not share one resolution")

            entered_court = _post(client, base, session_id, smoke_enter(), audit_path, action_id=str(uuid.uuid4()))
            opponent = ((entered_court["body"].get("state") or {}).get("bounded_encounter") or {}).get("visible_opponent") or {}
            npc_id = opponent.get("npc_id")
            started = _post(client, base, session_id, smoke_start(), audit_path, action_id=str(uuid.uuid4()))
            combat_state = started["body"].get("state") or {}
            combat = _combat(combat_state)
            before = {
                "active": combat.get("active"),
                "combat_id": combat.get("combat_id") or combat.get("id"),
                "hp": (combat_state.get("character") or {}).get("current_hp"),
                "location": combat_state.get("location"),
                "round": combat.get("round"),
                "actor": combat.get("current_actor_id"),
                "initiative": combat.get("initiative_order"),
            }
            note("combat_start", before)
            check(before["active"] is True, "combat did not stay active after the legitimate start")

        if before["active"] is True:
            smoke._stop_api(process, log_handle)
            process, log_handle = smoke._start_api(port, database, audit_path, EVIDENCE / "unified-api-restart-combat.log")
            smoke._wait_ready(process, base, EVIDENCE / "unified-api-restart-combat.log")
            with httpx.Client(timeout=30) as client:
                resumed = client.post(f"{base}/api/campaigns/{campaign_id}/resume")
                check(resumed.status_code == 200, "combat resume failed")
                session_id = resumed.json()["session_id"]
                restored = resumed.json()["state"]
                restored_combat = _combat(restored)
                after = {
                    "active": restored_combat.get("active"),
                    "combat_id": restored_combat.get("combat_id") or restored_combat.get("id"),
                    "hp": (restored.get("character") or {}).get("current_hp"),
                    "location": restored.get("location"),
                    "round": restored_combat.get("round"),
                    "actor": restored_combat.get("current_actor_id"),
                    "initiative": restored_combat.get("initiative_order"),
                }
                note("combat_resume", after)
                check(after == before, f"combat resume changed authoritative combat state {before} -> {after}")
                blocked = _post(client, base, session_id, TAVERN, audit_path, action_id=str(uuid.uuid4()))
                blocked_state = blocked["body"].get("state") or restored
                note("combat_travel", {"status": blocked["status"], "location": blocked_state.get("location") if isinstance(blocked_state, dict) else None})
                check(blocked_state.get("location") == before["location"], "prohibited travel left combat")
                attack_state = restored
                distance = ((attack_state.get("bounded_encounter") or {}).get("visible_opponent") or {}).get("distance_ft")
                if distance != 5:
                    closed = _post(client, base, session_id, "Turumu bitiriyorum.", audit_path, action_id=str(uuid.uuid4()))
                    attack_state = closed["body"].get("state") or attack_state
                    distance = ((attack_state.get("bounded_encounter") or {}).get("visible_opponent") or {}).get("distance_ft")
                    note("close_distance", {"status": closed["status"], "distance_ft": distance, "detail": closed["body"].get("detail")})
                if _combat(attack_state).get("current_actor_id") != "player":
                    yielded = _post(client, base, session_id, "Turumu bitiriyorum.", audit_path, action_id=str(uuid.uuid4()))
                    attack_state = yielded["body"].get("state") or attack_state
                    note("yield_turn", {"actor": _combat(attack_state).get("current_actor_id"), "status": yielded["status"]})
                attack_id = str(uuid.uuid4())
                attack = _post(client, base, session_id, "Saldırıyorum.", audit_path, action_id=attack_id, target_id=npc_id)
                attack_replay = _post(client, base, session_id, "Saldırıyorum.", audit_path, action_id=attack_id, target_id=npc_id)
                note("attack", {
                    "status": attack["status"],
                    "replay": attack_replay["status"],
                    "detail": attack["body"].get("detail"),
                    "hp": ((attack["body"].get("state") or {}).get("character") or {}).get("current_hp"),
                    "replay_hp": ((attack_replay["body"].get("state") or {}).get("character") or {}).get("current_hp"),
                    "calls": (attack["audit"] or {}).get("model_calls"),
                })
                def _npc_hp(payload: dict[str, Any]) -> Any:
                    for npc in ((payload.get("state") or {}).get("npcs") or []):
                        if isinstance(npc, dict) and npc.get("id") == npc_id:
                            return npc.get("current_hp")
                    return None

                check(distance == 5, f"commoner did not close to 5 feet, distance={distance}")
                check(attack["status"] == 200 and attack_replay["status"] == 200, "attack replay was not the same receipt")
                check(
                    ((attack["body"].get("state") or {}).get("character") or {}).get("current_hp")
                    == ((attack_replay["body"].get("state") or {}).get("character") or {}).get("current_hp")
                    and _npc_hp(attack["body"]) == _npc_hp(attack_replay["body"]),
                    "replayed attack changed HP",
                )

                calls = [row.get("calls") for row in rows if isinstance(row.get("calls"), int)]
                calls.append((attack["audit"] or {}).get("model_calls"))
                note("qwen", {"observed_calls": calls})
                check(any(isinstance(item, int) and item >= 1 for item in calls), "no legitimate turn invoked Qwen")

                other = client.post(f"{base}/api/campaigns", json={
                    "name": f"S10B other {uuid.uuid4().hex[:8]}",
                    "campaign_start": smoke.START_SELECTION,
                })
                other_state = other.json()["state"]
                note("isolation", {"shops": other_state.get("shops"), "combat": _combat(other_state).get("active"), "npcs": len(other_state.get("npcs") or [])})
                check(not other_state.get("shops") and _combat(other_state).get("active") is not True, "second campaign inherited the first")
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        smoke._stop_api(process, log_handle)

    summary = {"failures": failures, "steps": rows}
    (EVIDENCE / "unified-campaign.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"failures": failures, "steps": [row["step"] for row in rows]}, ensure_ascii=False))
    return 1 if failures else 0


def smoke_enter() -> str:
    from bounded_encounter import ENTER
    return ENTER


def smoke_start() -> str:
    from bounded_encounter import START
    return START


if __name__ == "__main__":
    raise SystemExit(main())
