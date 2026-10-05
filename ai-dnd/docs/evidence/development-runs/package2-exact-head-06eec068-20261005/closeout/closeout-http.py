"""Disposable real-development HTTP acceptance; no fixture or model substitution."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import time
import traceback
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

OUT = Path(os.environ.get("CLOSEOUT_OUT", "/tmp/package2-http-first"))
OUT.mkdir(parents=True, exist_ok=False)
BASE = "https://" + os.environ["REPLIT_DEV_DOMAIN"] + "/api/game"
DB = Path("ai-dnd/saves/campaigns.sqlite3").resolve()
record = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "kind": "real development HTTP / real configured Qwen", "steps": [],
          "status": "RUNNING", "campaigns_created": [], "cleanup": []}
review = []

def checkpoint():
    (OUT / "live-http.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    (OUT / "narration-review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False))

def request(method, path, body=None, expect=200):
    entry = {"method": method, "path": path, "expected": expect, "start": time.time()}
    record["steps"].append(entry)
    checkpoint()
    req = Request(BASE + path, method=method,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=180, context=ssl.create_default_context()) as response:
            status, raw = response.status, response.read()
    except HTTPError as error:
        status, raw = error.code, error.read()
    entry.update(status=status, end=time.time(), response_sha256=hashlib.sha256(raw).hexdigest())
    result = json.loads(raw) if raw else {}
    if isinstance(result, dict) and "narration" in result:
        review.append({"action_id": result.get("action_id"), "input": (body or {}).get("message"),
                       "narration": result["narration"]})
    checkpoint()
    assert status == expect, (path, status, result)
    return result

def world(cid):
    assert cid in record["campaigns_created"]
    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT payload_json FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
    assert row
    payload = json.loads(row[0])
    return payload["engine_save"]["world_state"]

def snap(cid):
    w = world(cid)
    return {k: w.get(k) for k in ("inventory", "currency", "equipment", "item_rewards",
                                 "claimed_item_rewards", "npcs", "shops",
                                 "interaction_adventure_v1")}

def create(selection):
    result = request("POST", "/campaigns", {
        "name": "Disposable Package2 exact-HEAD closeout",
        "campaign_start": selection,
        "character": {"mode": "custom", "name": "Closeout", "species": "Dwarf",
                      "class": "Fighter", "background": "Acolyte",
                      "alignment": "Neutral Good", "languages": ["Dwarvish", "Elvish"],
                      "ability_score_method": "standard_array",
                      "ability_scores": {"strength": 15, "dexterity": 14, "constitution": 13,
                                         "intelligence": 12, "wisdom": 10, "charisma": 8},
                      "background_ability_bonuses": {"intelligence": 2, "wisdom": 1},
                      "proficient_skills": ["Insight", "Religion", "Athletics", "Perception"],
                      "fighting_style": "Defense", "equipment_package": "A",
                      "background_equipment_option": "A"},
    })
    record["campaigns_created"].append(result["campaign_id"])
    checkpoint()
    return result

def turn(sid, message, **kw):
    return request("POST", f"/sessions/{sid}/turn",
                   {"message": message, "action_id": str(uuid4()), **kw})

def replay(cid, sid, message, **kw):
    body = {"message": message, "action_id": str(uuid4()), **kw}
    before = snap(cid)
    accepted = request("POST", f"/sessions/{sid}/turn", body)
    saved = snap(cid)
    if message.startswith(("/item buy ", "/item sell ")):
        assert "atomik olarak tamamlandı" in accepted["narration"], accepted["narration"]
        verb, identity, shop_id = message.split()[1:]
        merchant = next(s["shopkeeper_id"] for s in saved["shops"] if s["id"] == shop_id)
        seller = next(n for n in saved["npcs"] if n["id"] == merchant)
        if verb == "buy":
            assert sum(i["item_id"] == identity for i in saved["inventory"]) == 1
            assert not any(i["item_id"] == identity for i in seller["inventory"])
            assert saved["currency"]["player"] < before["currency"]["player"]
        else:
            assert not any(i["item_id"] == identity for i in saved["inventory"])
            assert sum(i["item_id"] == identity for i in seller["inventory"]) == 1
            assert saved["currency"]["player"] > before["currency"]["player"]
        assert sum(saved["currency"].values()) == sum(before["currency"].values())
    record.setdefault("transactions", []).append(
        {"action_id": body["action_id"], "message": message,
         "before": before["currency"], "after": saved["currency"]})
    assert request("POST", f"/sessions/{sid}/turn", body) == accepted
    assert snap(cid) == saved
    request("POST", f"/sessions/{sid}/turn", {**body, "message": "/item list"}, expect=409)
    assert snap(cid) == saved
    return accepted, body

try:
    options = request("GET", "/campaign-start-options")["settings"][0]
    region = options["regions"][0]
    selection = {"setting_id": options["setting_id"], "region_pack_id": region["region_pack_id"],
                 "region_id": region["region_id"],
                 "starting_location_id": region["starting_locations"][0]["entity_id"]}
    c = create(selection)
    cid, sid = c["campaign_id"], c["session_id"]
    turn(sid, "/item market")
    w = world(cid)
    shop = next(s for s in w["shops"] if s.get("economy_origin") == "native_equipment_counter_v1")
    npc = next(n for n in w["npcs"] if n["id"] == shop["shopkeeper_id"])
    club = next(i for i in npc["inventory"] if i.get("weapon_id") == "club")
    dagger = next(i for i in npc["inventory"] if i.get("weapon_id") == "dagger")
    record["native_before"] = snap(cid)
    before = snap(cid)
    turn(sid, "/item market")
    assert snap(cid) == before, "repeated market minted state"
    # Denied ownership/consent, including a real natural-language refusal path.
    denied = turn(sid, f'/item request {dagger["item_id"]} {npc["id"]}')
    assert "npc_consent_required" in denied["narration"]
    assert snap(cid) == before
    turn(sid, "Elindeki Dagger adlı eşyayı ücretsiz bana vermeni istiyorum.", target_id=npc["id"])
    assert not any(i.get("item_id") == dagger["item_id"] for i in world(cid)["inventory"])
    # One real Qwen interpretation, not a fabricated proposal.
    body = {"message": "Elindeki Club'ı bana ver.",
            "target_id": npc["id"], "action_id": str(uuid4())}
    record["natural_request"] = body
    accepted = request("POST", f"/sessions/{sid}/turn", body)
    w = world(cid)
    actual_npc = next(n for n in w["npcs"] if n["id"] == npc["id"])
    assert sum(i.get("item_id") == club["item_id"] for i in w["inventory"]) == 1
    assert not any(i.get("item_id") == club["item_id"] for i in actual_npc["inventory"])
    assert actual_npc["equipment"]["main_hand"] is None
    assert club["item_id"] not in actual_npc.get("item_release_policy", {})
    assert club["item_id"] not in actual_npc.get("item_consents", {})
    assert any(e["kind"] == "item_consent" for e in w["interaction_adventure_v1"]["events"])
    record["native_after"] = snap(cid)
    before = snap(cid)
    assert request("POST", f"/sessions/{sid}/turn", body) == accepted
    assert snap(cid) == before
    request("POST", f"/sessions/{sid}/turn", {**body, "message": "/item list"}, expect=409)
    assert snap(cid) == before
    denied = turn(sid, f'/item request {club["item_id"]} {npc["id"]}')
    assert snap(cid) == before
    # Native market economics, same-instance movement and replay.
    for operation, item in (("sell", club), ("buy", dagger), ("sell", dagger)):
        replay(cid, sid, f'/item {operation} {item["item_id"]} {shop["id"]}')
    w = world(cid)
    balance = w["currency"]["player"]
    total = sum(w["currency"].values())
    turn(sid, f'/item work {npc["id"]}')
    thread = next(iter(world(cid)["item_rewards"]))
    before = world(cid)["currency"]["player"]
    turn(sid, f'/item reward {thread}')
    assert world(cid)["currency"]["player"] == before, "unfinished reward paid"
    turn(sid, f'/item talk {npc["id"]} Merhaba')
    paid, reward_body = replay(cid, sid, f'/item reward {thread}')
    assert world(cid)["currency"]["player"] == balance + 100
    assert sum(world(cid)["currency"].values()) == total
    before = snap(cid)
    turn(sid, f'/item reward {thread}')
    assert snap(cid) == before
    resumed = request("POST", f"/campaigns/{cid}/resume")
    rsid = resumed["session_id"]
    r = request("POST", f"/sessions/{rsid}/turn", reward_body)
    assert r == dict(paid, session_id=rsid)
    assert snap(cid) == before
    other = create(selection)
    other_before = snap(other["campaign_id"])
    turn(other["session_id"], f'/item receive {club["item_id"]} {npc["id"]}')
    assert snap(other["campaign_id"]) == other_before
    record.update(status="PASS", final_wallet=world(cid)["currency"],
                  conserved_wallet_total=total, item_id=club["item_id"])
except Exception as error:
    record.update(status="FAIL", error={"type": type(error).__name__,
                                      "detail": str(error), "traceback": traceback.format_exc()})
    if record["campaigns_created"]:
        record["failure_state"] = snap(record["campaigns_created"][0])
finally:
    for cid in record["campaigns_created"]:
        try:
            request("DELETE", f"/campaigns/{cid}", expect=200)
            record["cleanup"].append({"campaign_id": cid, "status": "PASS"})
        except Exception as error:
            record["cleanup"].append({"campaign_id": cid, "status": "FAIL", "type": type(error).__name__})
    checkpoint()
    print(json.dumps({"status": record["status"], "out": str(OUT), "error": record.get("error"),
                      "cleanup": record["cleanup"]}, ensure_ascii=False), flush=True)
    raise SystemExit(0 if record["status"] == "PASS" else 1)
