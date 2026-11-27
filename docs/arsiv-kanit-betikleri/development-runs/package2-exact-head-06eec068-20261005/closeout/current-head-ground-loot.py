"""Real HTTP ground-loot proof using only existing native owners and commands."""
from pathlib import Path

helpers = Path(".local/closeout-http.py").read_text().split("\ntry:\n", 1)[0]
exec(compile(helpers, ".local/closeout-http.py:helpers", "exec"))
record["kind"] = "real development HTTP / existing native ground-loot producer and consumer"
record["model_use"] = "none requested; confirm zero adapter calls in server logs"

def loot_snapshot(cid):
    w = world(cid)
    return {k: w.get(k) for k in (
        "inventory", "equipment", "currency", "npcs", "shops",
        "ground_items", "ground_items_by_location", "flags")}

try:
    options = request("GET", "/campaign-start-options")["settings"][0]
    region = options["regions"][0]
    selection = {
        "setting_id": options["setting_id"], "region_pack_id": region["region_pack_id"],
        "region_id": region["region_id"],
        "starting_location_id": region["starting_locations"][0]["entity_id"],
    }
    c = create(selection)
    cid, sid = c["campaign_id"], c["session_id"]
    turn(sid, "/item market")
    w = world(cid)
    shop = next(s for s in w["shops"] if s.get("economy_origin") == "native_equipment_counter_v1")
    npc = next(n for n in w["npcs"] if n["id"] == shop["shopkeeper_id"])
    identity = npc["equipment"]["main_hand"]
    turn(sid, f'/item request {identity} {npc["id"]}')
    w = world(cid)
    assert sum(i["item_id"] == identity for i in w["inventory"]) == 1
    baseline_wallets = w["currency"]
    record["before"] = loot_snapshot(cid)
    for verb in ("drop", "take"):
        body = {"message": f"/item {verb} {identity}", "action_id": str(uuid4())}
        accepted = request("POST", f"/sessions/{sid}/turn", body)
        w = world(cid)
        player_count = sum(i["item_id"] == identity for i in w["inventory"])
        ground = w["ground_items_by_location"].get(w["location"], [])
        ground_count = sum(i["item_id"] == identity for i in ground)
        assert (player_count, ground_count) == ((0, 1) if verb == "drop" else (1, 0))
        assert w["currency"] == baseline_wallets
        owned = {i["item_id"] for i in w["inventory"]}
        assert all(ref is None or ref in owned for ref in w["equipment"].values())
        saved = loot_snapshot(cid)
        assert request("POST", f"/sessions/{sid}/turn", body) == accepted
        assert loot_snapshot(cid) == saved
        request("POST", f"/sessions/{sid}/turn", {**body, "message": "/item list"}, expect=409)
        assert loot_snapshot(cid) == saved
        record.setdefault("operations", []).append({
            "verb": verb, "item_id": identity, "action_id": body["action_id"],
            "player_count": player_count, "local_ground_count": ground_count,
            "wallets": w["currency"], "exact_replay": True, "changed_body_conflict": 409})
    record.update(status="PASS", item_id=identity, after=loot_snapshot(cid),
                  exclusions="No combat defeat or arbitrary container producer is claimed.")
except Exception as error:
    record.update(status="FAIL", error={
        "type": type(error).__name__, "detail": str(error),
        "traceback": traceback.format_exc()})
    if record["campaigns_created"]:
        record["failure_state"] = loot_snapshot(record["campaigns_created"][0])
finally:
    for cid in record["campaigns_created"]:
        try:
            request("DELETE", f"/campaigns/{cid}", expect=200)
            record["cleanup"].append({"campaign_id": cid, "status": "PASS"})
        except Exception as error:
            record["cleanup"].append({"campaign_id": cid, "status": "FAIL", "type": type(error).__name__})
    checkpoint()
    print(json.dumps({"status": record["status"], "out": str(OUT),
                      "error": record.get("error")}, ensure_ascii=False))
    raise SystemExit(0 if record["status"] == "PASS" else 1)
