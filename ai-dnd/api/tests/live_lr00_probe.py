"""Opt-in LR00 blocker probe with unseen Turkish inputs. NOT a gate.

Plays short scripted scenarios against fresh temporary campaigns through the
real HTTP API and the real local Ollama model. Every model call is counted and
logged; there are no retries. It records facts (what the player saw, what the
receipt says, what state changed). It does not grade quality: acceptance is a
human decision.

Run from ai-dnd (Ollama up, qwen3:8b pulled):

    set AI_DND_LIVE_PROBE=1
    set AI_DND_NPC_SPEECH=1
    python -m unittest api.tests.live_lr00_probe -v

Optional: AI_DND_PROBE_SCENARIOS=door,npc,free (subset), AI_DND_PROBE_CAP (total
real call cap, default 60), AI_DND_LIVE_EVIDENCE_DIR, AI_DND_LIVE_P2_DRY=1.
The phrases below were written fresh for this probe; once a phrase is used to
repair behaviour it belongs in a regression test and a new phrase replaces it.
"""

from __future__ import annotations

import copy
import json
import os
import time
import unittest
import uuid
from pathlib import Path

from api.tests import live_npc_p2_sample as sample
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

# (text, mode, target) - mode None mirrors the UI default 'do' path without a
# chip; target "npc" uses the scenario NPC's id as the UI chip would.
SCENARIOS = {
    "door": [
        ("Hanın kapısına iki kez hafifçe vurup içeriden ses gelip gelmediğini dinliyorum.", None, None),
        ("Kapıyı açmaya kalkmıyorum; sadece kilidin nasıl bir şey olduğuna bakıyorum.", None, None),
        ("Eğer kapı açıksa içeri süzülürüm, değilse beklerim.", None, None),
        ("Hanın sokağa bakan penceresinden içeriyi görmeye çalışıyorum.", None, None),
        ("Pencerenin sürgüsünü parmaklarımla yokluyorum.", None, None),
    ],
    "npc": [
        ("Marek'in yanına gidip başımla selam veriyorum.", None, None),
        ("Arşivde seni en çok ne yoruyor?", "say", "npc"),
        ("Neden öyle?", "say", "npc"),
        ("Bunu geç; bu şehirde güvenilir bir demirci bilir misin?", "say", "npc"),
        ("Oraya buradan nasıl giderim?", "say", "npc"),
        ("Geçen hafta bana bedava bir kılıç sözü vermiştin, unuttun mu?", "say", "npc"),
    ],
    # P3 pilot probe: a place an NPC mentions becomes somewhere you can go,
    # and it is the same place when you come back.
    "p3": [
        ("Marek, çalıştığın arşiv nerede? Nasıl bir yer orası?", "say", "npc"),
        ("Marek'in bahsettiği arşive gidiyorum.", None, None),
        ("Etrafa dikkatlice bakıyorum.", None, None),
        ("Arşivciye selam verip burada bir sorun olup olmadığını soruyorum.", None, None),
        ("Raflara yakından bakıyorum.", None, None),
        ("Buradan çıkıp sokağa dönüyorum.", None, None),
        ("Arşive geri gidiyorum.", None, None),
    ],
    "free": [
        ("Meydandaki çanı birkaç kez çalıyorum.", None, None),
        ("Çantamdaki eski kitabı açıp birkaç sayfa okuyorum.", None, None),
        ("Biraz şehrin sokaklarında amaçsızca dolaşıyorum.", None, None),
        ("Yerdeki çamurlu ayak izlerini dikkatle inceliyorum.", None, None),
        ("Az önce gördüğüm adamın peşine takılıyorum.", None, None),
    ],
}


_UNSEEN = json.loads(
    (Path(__file__).with_name("live_lr00_unseen_phrases.json")).read_text(encoding="utf-8")
)
_NEEDS_CONVERSATION = {"topic_change", "short_followup", "fake_memory"}
for _category, _phrases in _UNSEEN.items():
    if _category == "source":
        continue
    _opening = ([("Merhaba Marek, biraz konuşabilir miyiz?", "say", "npc")]
                if _category in _NEEDS_CONVERSATION else [])
    SCENARIOS[f"unseen_{_category}"] = _opening + [(text, None, None) for text in _phrases]


def _cap():
    try:
        return int(os.environ.get("AI_DND_PROBE_CAP", "60"))
    except ValueError:
        return 60


def _snapshot(session):
    world = session.world_state
    return {
        "location": copy.deepcopy(world.get("current_location") or world.get("location")),
        "doors": copy.deepcopy(world.get("doors")),
        "npc_ids": sorted(
            str(n.get("id")) for n in world.get("npcs", []) if isinstance(n, dict)
        ),
        "location_ids": sorted(str(k) for k in (world.get("locations") or {})),
        "feature_count": len(world.get("features", []) or []),
        "inventory": copy.deepcopy(world.get("inventory")),
        "gold": copy.deepcopy(world.get("gold")),
        "quests": copy.deepcopy(world.get("quests")),
    }


def _diff(before, after):
    return sorted(key for key in before if before[key] != after[key])


@unittest.skipUnless(
    os.environ.get("AI_DND_LIVE_PROBE") == "1",
    "live probe is opt-in: set AI_DND_LIVE_PROBE=1",
)
class LiveLr00Probe(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    campaign_with_npc = harness.ExperimentalNpcDialogueTests.campaign_with_npc

    async def test_probe(self):
        sample.MAX_REAL_CALLS = _cap()
        stamp = time.strftime("%Y%m%dT%H%M%S")
        out = Path(os.environ.get("AI_DND_LIVE_EVIDENCE_DIR") or f"live-lr00-probe-{stamp}")
        out.mkdir(parents=True, exist_ok=False)
        wanted = [s for s in os.environ.get("AI_DND_PROBE_SCENARIOS", ",".join(SCENARIOS)).split(",") if s]
        log: list = []
        client = sample.CountingClient(sample._build_inner_client(), log)
        report = []
        import game
        from unittest.mock import patch
        dispatched: list = []
        original_dispatch = game._dispatch_player_turn

        def recording_dispatch(*args, **kwargs):
            outcome = original_dispatch(*args, **kwargs)
            dispatched.append(outcome.get("action_result") if isinstance(outcome, dict) else None)
            return outcome

        self.enterContext(patch.object(game, "_dispatch_player_turn", recording_dispatch))
        for name in wanted:
            _, _, session, turn_url, npc = await self.campaign_with_npc(
                experimental=os.environ.get("AI_DND_NPC_SPEECH") == "1"
            )
            with sample.unittest_patch(self.app.state.ollama_adapter, client):
                for index, (text, mode, target) in enumerate(SCENARIOS[name], start=1):
                    before = _snapshot(session)
                    dispatched.clear()
                    calls_before = client.calls
                    body = {"message": text, "action_id": str(uuid.uuid4())}
                    if mode:
                        body["interaction_mode"] = mode
                    if target == "npc":
                        body["target_id"] = npc["id"]
                    started = time.time()
                    try:
                        response = await self.http.post(turn_url, json=body)
                        status = response.status_code
                        data = response.json() if status == 200 else {"error": response.text[:600]}
                    except AssertionError as error:  # call cap reached
                        status, data = "CAP", {"error": str(error)}
                    after = _snapshot(session)
                    result = dispatched[-1] if dispatched else None
                    report.append({
                        "scenario": name,
                        "turn": index,
                        "player": text,
                        "mode": mode,
                        "target": target,
                        "http_status": status,
                        "shown": data.get("narration") if isinstance(data, dict) else None,
                        "receipt": {
                            k: (result or {}).get(k)
                            for k in ("action", "status", "success", "skill", "npc_id",
                                      "target_reference", "fallback_reason_code", "state_changes")
                        } if isinstance(result, dict) else None,
                        "skill_check": data.get("skill_check_result") if isinstance(data, dict) else None,
                        "error": data.get("error") if isinstance(data, dict) else None,
                        "real_calls_this_turn": client.calls - calls_before,
                        "seconds": round(time.time() - started, 1),
                        "state_changed": _diff(before, after),
                        "where": {
                            "id": session.world_state.get("location"),
                            "name": (session.world_state.get("locations", {}).get(
                                session.world_state.get("location"), {}) or {}).get("name"),
                        },
                    })
                    if status == "CAP":
                        break
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "raw-calls.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nEvidence written to: {out.resolve()}  real calls: {client.calls}")
        self.assertLessEqual(client.calls, sample.MAX_REAL_CALLS)


if __name__ == "__main__":
    unittest.main()
