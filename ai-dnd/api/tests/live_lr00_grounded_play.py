"""Opt-in LIVE play run for the LR00 grounded-action fix. NOT a gate, not acceptance.

Plays multi-turn scripts against fresh temporary campaigns through the real HTTP
API and the real local Ollama model (qwen3:8b), with first-person NPC speech on
(as in the owner's P6 run). Nothing is injected into the campaigns: no Marek,
no Sera, no pre-made inn. Records facts only: what the player saw, wall time,
every real model call and its duration, the turn receipt and what changed in
the saved world. It never retries and never grades.

Two sources of scripts:
  * AI_DND_UNSEEN_SCRIPTS: a JSON file written by someone who did not see the
    solution ({"scripts": [{"id", "theme", "turns": [{"input", "expect"}]}]}).
    The expectations are copied into the report for a human reader only.
  * "owner_replay": the owner's own P6 lines, replayed on the owner's saved
    state (api/tests/fixtures/lr00_p6_human_world.json).

Run from ai-dnd (Ollama up, qwen3:8b pulled):

    set AI_DND_LIVE_PLAY=1
    set AI_DND_NPC_SPEECH=1
    set AI_DND_UNSEEN_SCRIPTS=C:\\path\\to\\unseen_scenarios.json
    set AI_DND_LIVE_EVIDENCE_DIR=C:\\path\\to\\out
    python -m unittest api.tests.live_lr00_grounded_play -v

Optional: AI_DND_PLAY_ONLY=s1,s3,owner_replay; AI_DND_PROBE_CAP (default 260).
"""

from __future__ import annotations

import copy
import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from api.tests import live_npc_p2_sample as sample
from api.tests import test_campaign_api

CITY = "fr:city:neverwinter"
FIXTURE = Path(__file__).parent / "fixtures" / "lr00_p6_human_world.json"
OWNER_REPLAY = [
    "garick hanına doğru yaklaşıyorum",
    "Garrick Hanı",
    "Garrick Hanı Kapısı’nı kırmayacağım, sadece kilidine bakıyorum.",
    "kilidi inceliyorum",
    "kilidi açmaya çalışıyorum",
    "Şehirde kızılhanı arıyorum",
    "Açık olan başka han varmı diye şehirde geziyorum",
    "Şehirde geziniyorum farklı sokakları geziyorum. tabelalara dikkat ediyorum.",
    "Quarion ile konuşmak istiyorum.",
    "bana kılıç vereceğini söylemiştin",
    "beni hana götüreceğini söylemiştin",
]


def _cap():
    try:
        return int(os.environ.get("AI_DND_PROBE_CAP", "260"))
    except ValueError:
        return 260


def _state(world):
    locations = world.get("locations") or {}
    return {
        "location": world.get("location"),
        "location_name": (locations.get(world.get("location")) or {}).get("name"),
        "doors": {d["id"]: {k: d.get(k) for k in ("name", "open", "locked", "broken")}
                  for d in world.get("doors", []) if isinstance(d, dict) and d.get("id")},
        "locations": {k: v.get("name") for k, v in locations.items() if isinstance(v, dict)},
        "features": {f.get("id"): f.get("name") for f in world.get("features", []) if isinstance(f, dict)},
        "npcs": {n.get("id"): {"name": n.get("name"), "location": n.get("location")}
                 for n in world.get("npcs", []) if isinstance(n, dict)},
        "inventory": [i.get("name") if isinstance(i, dict) else i for i in world.get("inventory", [])],
        "quests": copy.deepcopy(world.get("quests")),
        "references": [
            {k: r.get(k) for k in ("id", "name", "said_by", "status", "location_id", "claims")}
            for r in ((world.get("npc_statements") or {}).get("references") or [])
        ],
        "commitments": [
            {k: c.get(k) for k in ("id", "npc_id", "kind", "status", "quote")}
            for c in ((world.get("npc_statements") or {}).get("commitments") or [])
        ],
        "clock": (world.get("campaign_time") or {}).get("elapsed_seconds"),
    }


def _changes(before, after):
    out = {}
    if before["location"] != after["location"]:
        out["location"] = [before["location_name"], after["location_name"]]
    doors = {k: [before["doors"].get(k), v] for k, v in after["doors"].items() if before["doors"].get(k) != v}
    if doors:
        out["doors"] = doors
    for key in ("locations", "features"):
        added = {k: v for k, v in after[key].items() if k not in before[key]}
        if added:
            out[f"new_{key}"] = added
    new_npcs = {k: v for k, v in after["npcs"].items() if k not in before["npcs"]}
    if new_npcs:
        out["new_npcs"] = new_npcs
    moved = {k: [before["npcs"][k]["location"], v["location"]] for k, v in after["npcs"].items()
             if k in before["npcs"] and before["npcs"][k]["location"] != v["location"]}
    if moved:
        out["npcs_moved"] = moved
    if before["inventory"] != after["inventory"]:
        out["inventory"] = [before["inventory"], after["inventory"]]
    if before["quests"] != after["quests"]:
        out["quests_changed"] = True
    new_refs = [r for r in after["references"] if r not in before["references"]]
    if new_refs:
        out["npc_place_references"] = new_refs
    new_commitments = [c for c in after["commitments"] if c not in before["commitments"]]
    if new_commitments:
        out["npc_commitments"] = new_commitments
    if before["clock"] is not None and after["clock"] is not None and after["clock"] != before["clock"]:
        out["minutes_passed"] = round((after["clock"] - before["clock"]) / 60, 1)
    return out


@unittest.skipUnless(os.environ.get("AI_DND_LIVE_PLAY") == "1", "live play is opt-in: set AI_DND_LIVE_PLAY=1")
class LiveLr00GroundedPlay(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def fresh_campaign(self, *, owner_state=False):
        created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": CITY,
        }})
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        if owner_state:
            campaign_id = session.world_state.get("campaign_id")
            session.world_state.clear()
            session.world_state.update(json.loads(FIXTURE.read_text(encoding="utf-8"))["world_state"])
            session.world_state["campaign_id"] = campaign_id
        if os.environ.get("AI_DND_NPC_SPEECH") == "1":
            session._experimental_npc_dialogue_enabled = True
        return session_id, session, f"/api/game/sessions/{session_id}/turn", created.json()

    async def test_play(self):
        sample.MAX_REAL_CALLS = _cap()
        out = Path(os.environ.get("AI_DND_LIVE_EVIDENCE_DIR") or f"live-lr00-play-{time.strftime('%Y%m%dT%H%M%S')}")
        out.mkdir(parents=True, exist_ok=True)
        scripts = []
        source = os.environ.get("AI_DND_UNSEEN_SCRIPTS")
        if source:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
            scripts.extend(data.get("scripts", []))
        scripts.append({"id": "owner_replay", "theme": "owner's own P6 lines on the owner's saved state",
                        "turns": [{"input": text, "expect": ""} for text in OWNER_REPLAY]})
        only = [s for s in os.environ.get("AI_DND_PLAY_ONLY", "").split(",") if s]
        if only:
            scripts = [s for s in scripts if s["id"] in only]
        log: list = []
        client = sample.CountingClient(sample._build_inner_client(), log)
        import game
        receipts: list = []
        original = game._dispatch_player_turn

        def recording(*args, **kwargs):
            outcome = original(*args, **kwargs)
            receipts.append(outcome.get("action_result") if isinstance(outcome, dict) else None)
            return outcome

        self.enterContext(patch.object(game, "_dispatch_player_turn", recording))
        report = []
        for script in scripts:
            session_id, session, turn_url, created = await self.fresh_campaign(
                owner_state=script["id"] == "owner_replay")
            opening = created.get("narration") or created.get("opening") or ""
            report.append({"script": script["id"], "theme": script.get("theme"), "opening": opening})
            with sample.unittest_patch(self.app.state.ollama_adapter, client):
                for index, turn in enumerate(script.get("turns", []), start=1):
                    text = turn["input"]
                    world = self.manager.get(session_id).game_session.world_state
                    before = _state(world)
                    receipts.clear()
                    first_call = len(log)
                    started = time.time()
                    try:
                        response = await self.http.post(turn_url, json={"message": text, "action_id": str(uuid.uuid4())})
                        status = response.status_code
                        body = response.json() if status == 200 else {"error": response.text[:600]}
                    except AssertionError as error:
                        status, body = "CAP", {"error": str(error)}
                    seconds = round(time.time() - started, 2)
                    world = self.manager.get(session_id).game_session.world_state
                    after = _state(world)
                    receipt = receipts[-1] if receipts else None
                    calls = log[first_call:]
                    report.append({
                        "script": script["id"], "turn": index, "player": text,
                        "expect_written_blind": turn.get("expect"),
                        "http_status": status, "shown": body.get("narration") if isinstance(body, dict) else None,
                        "error": body.get("error") if isinstance(body, dict) else None,
                        "seconds": seconds,
                        "model_calls": len(calls),
                        "model_call_seconds": [c.get("duration_seconds") for c in calls],
                        "receipt": {k: (receipt or {}).get(k) for k in (
                            "action", "status", "success", "reason", "target_name", "skill", "dice", "total",
                            "dc", "outcome", "npc_id")} if isinstance(receipt, dict) else None,
                        "steps": [{k: s.get(k) for k in ("verb", "status", "reason", "target_name")}
                                  for s in (receipt or {}).get("steps", [])] if isinstance(receipt, dict) else [],
                        "grounding": (receipt or {}).get("grounding") if isinstance(receipt, dict) else None,
                        "changes": _changes(before, after),
                        "where": after["location_name"],
                    })
                    if status == "CAP":
                        break
            (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "raw-calls.json").write_text(json.dumps(log, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nEvidence: {out.resolve()} real calls: {client.calls}")


if __name__ == "__main__":
    unittest.main()
