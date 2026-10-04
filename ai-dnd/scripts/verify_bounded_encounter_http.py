"""Real network acceptance against running production handlers, no injections.

Uses the normal public campaign/turn/save/resume routes. A second running
process can supply --resume-base to demonstrate disk-backed restoration.
Leaves the disposable campaign available for inspection. Existing owner
campaigns are never listed, selected, modified or deleted.
"""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from dictionaries(item)
    elif isinstance(value, list):
        for item in value:
            yield from dictionaries(item)


def run(base, resume_base, output):
    def request(method, path, body=None, server=base):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(server.rstrip("/") + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            assert response.status == 200, response.status
            return json.load(response)

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
    turns = []
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
        assert budget["movement_used"] == 55 and budget["dash_count"] == 1 and budget["base_action_spent"]
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
        evidence = {
            "status": "PASS", "transport": "real HTTP", "fixture_injection": False,
            "campaign_id": campaign_id,
            "second_process_resume": base.rstrip("/") != resume_base.rstrip("/"),
            "scenario": entered["state"]["bounded_encounter"],
            "movement": {"result": dash, "budget": budget, "distance_after_ft": 5},
            "attack": attack, "save": "PASS", "resume": "PASS", "replay": "PASS",
            "replay_state_unchanged": True, "replay_history_unchanged": True,
            "turns": turns, "replay_response": replay,
        }
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: v for k, v in evidence.items()
                          if k not in {"turns", "replay_response", "attack", "movement"}},
                         ensure_ascii=False, indent=2))
    finally:
        print("Disposable acceptance campaign retained for review:", campaign_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--resume-base")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.base, args.resume_base or args.base, args.output)