"""End-to-end player flow against the real local model, built the way production builds it.

Quenna -> end conversation -> ask about the inn -> go to the inn -> door / lockpick ->
save -> resume -> continue. The adapter comes from the environment with no model
variable, so this also proves the production default. Loopback port, temporary sqlite.
Usage: live_flow_run.py <out.json>
"""
import asyncio
import copy
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

AI_DND = Path(os.environ.get("AI_DND_DIR", r"C:\Users\Kadir\Desktop\AI - DND\ai-dnd"))
sys.path.insert(0, str(AI_DND))
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
os.environ.setdefault("OLLAMA_PROXY_TOKEN", "loopback")
os.environ.pop("AI_DND_OLLAMA_MODEL", None)  # exercise the production default

import httpx
import uvicorn

import game
import living_world
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import create_city_with_locked_tavern

PORT = 8119
OUT = Path(sys.argv[1])
GENERIC = ("hiçbir söz sağlam görünmüyor", "çevrede şimdilik belirgin bir değişiklik olmuyor", "bulunduğun yer:")
VOLATILE = ("session_id", "action_id", "updated_at", "created_at", "saved_at", "last_saved")


class Spy:
    def __init__(self, real):
        self._real = real
        self.log = []

    def chat(self, *args, **kwargs):
        started = time.perf_counter()
        response = self._real.chat(*args, **kwargs)
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        user = next((m.get("content", "") for m in reversed(kwargs.get("messages", []))
                     if m.get("role") == "user"), "")
        self.log.append({
            "kind": "narration" if "narration" in properties else "intent",
            "model": kwargs.get("model"),
            "seconds": round(time.perf_counter() - started, 1),
            "raw": game.ollama_response_content(response),
            "prompt": user,
        })
        return response

    def __getattr__(self, name):
        return getattr(self._real, name)


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], str):
            return obj[key]
        for value in obj.values():
            found = find_key(value, key)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_key(value, key)
            if found:
                return found
    return None


def deep_diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key in VOLATILE:
                continue
            out += deep_diff(a.get(key), b.get(key), f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += deep_diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append({"path": path, "before": str(a)[:90], "after": str(b)[:90]})
    return out


async def main():
    tmp = tempfile.TemporaryDirectory()
    store = CampaignStore(Path(tmp.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
    manager = SessionManager(campaign_store=store)
    adapter = AuthenticatedOllamaAdapter.from_environment()
    assert adapter is not None, "adapter was not built from the environment"
    spy = Spy(adapter._client)
    adapter._client = spy
    app = create_app(session_manager=manager, ollama_adapter=adapter,
                     authenticator=FixedAuthenticator(TEST_PLAYER))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    print(f"server 127.0.0.1:{PORT} adapter model={adapter.model_name}", flush=True)

    shim = unittest.TestCase()
    shim.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=600)
    shim.manager = manager
    steps = []
    ctx = {}

    async def turn(label, message, mode="do", expect=None):
        session, url = ctx["session"], ctx["url"]
        before = len(spy.log)
        captured = {}
        real = session.run_player_turn

        def capture(*a, **k):
            r = real(*a, **k)
            captured["r"] = copy.deepcopy(r)
            return r

        started = time.perf_counter()
        with patch.object(session, "run_player_turn", new=capture):
            response = await shim.http.post(url, json={
                "message": message, "interaction_mode": mode, "action_id": str(uuid.uuid4())})
        body = response.json() if response.status_code == 200 else {}
        telemetry = ((captured.get("r") or {}).get("_engine_event_evidence") or {}).get("telemetry") or {}
        outcome = body.get("turn_outcome") or {}
        shown = body.get("narration", "")
        rec = {
            "step": label, "input": message, "mode": mode, "http": response.status_code,
            "shown": shown, "model_calls": len(spy.log) - before,
            "seconds": round(time.perf_counter() - started, 1),
            "fallback_reason": telemetry.get("fallback_reason"),
            "narration_source": telemetry.get("narration_source"),
            "action": outcome.get("action"), "status": outcome.get("status"),
        }
        problems = []
        if response.status_code != 200:
            problems.append(f"http {response.status_code}")
        if not shown.strip():
            problems.append("empty narration")
        if any(g in shown.casefold() for g in GENERIC):
            problems.append("generic/misrouted line")
        if steps and shown and shown == steps[-1]["shown"]:
            problems.append("identical to previous turn")
        if expect:
            reason = expect(rec, session)
            if reason:
                problems.append(reason)
        rec["problems"] = problems
        steps.append(rec)
        mark = "OK " if not problems else "!! "
        print(f"{mark}{label:<28}{rec['seconds']:>6}s calls={rec['model_calls']} {rec['action']}/{rec['status']} | "
              f"{shown[:70].replace(chr(10), ' ')}" + (f"  <== {problems}" if problems else ""), flush=True)
        return rec

    def started(rec, session):
        return None if rec["status"] == "conversation_started" else f"expected conversation_started, got {rec['status']}"

    state_diff = []
    with adapter.engine_binding():
        _city, session_id, session, url, tavern, door = await create_city_with_locked_tavern(shim)
        listing = (await shim.http.get("/api/game/campaigns")).json()
        campaign_id = find_key(listing, "campaign_id")
        ctx.update(session=session, url=url)
        inn = session.world_state["locations"][tavern].get("name", "Han")
        door_name = door.get("name") or f"{inn} Kapısı"
        print(f"campaign={campaign_id} inn={inn}", flush=True)

        await turn("F01 look around", "Çevreyi gözlemliyorum.")
        person = next(n for n in session.world_state["npcs"]
                      if isinstance(n, dict) and living_world.public_npc_name(n) == "Yakındaki kişi")
        person["name"] = "Quenna"
        await turn("F02 talk to nearby person", "Yakındaki kişi ile konuşmak istiyorum.", expect=started)
        await turn("F03 ask the name", "Selamlar, ismin nedir?", "say",
                   expect=lambda r, s: None if "Quenna" in r["shown"] else "name not given")
        await turn("F04 end conversation", "Konuşmayı bitiriyorum.",
                   expect=lambda r, s: None if r["status"] == "conversation_ended" else f"got {r['status']}")
        await turn("F05 reopen by name", "Quenna ile konuşmak istiyorum.", expect=started)
        await turn("M1 free chat (model)", "Günaydın, bugün hava güzel.", "say")
        await turn("M2 family question", "Ailen var mı?", "say")
        await turn("M3 how long here", "Burada uzun zamandır mı yaşıyorsun?", "say")
        await turn("F06 ask about an inn", "Buralarda han var mı?", "say",
                   expect=lambda r, s: None if "Hanı" in r["shown"] else "no inn named")
        await turn("F07 end conversation", "Konuşmayı bitiriyorum.")
        await turn("F08 go to the inn", f"{inn} yoluna çıkıp oraya gidiyorum")
        await turn("F09 knock", f"{inn} kapısını tıklatıyorum belki açarlar")
        await turn("F10 inspect door", "Kapıyı dikkatlice inceliyorum")
        await turn("F11 lockpick (vague)", "Kilidi maymuncukla açmayı deniyorum",
                   expect=lambda r, s: None if re.search("alet|maymuncuk", r["shown"], re.I) else "no tool explanation")
        await turn("F12 lockpick (exact)", f"{door_name} kilidini maymuncukla açmayı deniyorum")
        await turn("M6 free action (model)", "Kapının önünde durup sokağı izliyorum.")

        # ---- save and resume ----
        before = (await shim.http.get(f"/api/game/sessions/{session_id}/state")).json()
        saved = await shim.http.post(f"/api/game/campaigns/{campaign_id}/save")
        print(f"save -> {saved.status_code}", flush=True)
        resumed = await shim.http.post(f"/api/game/campaigns/{campaign_id}/resume")
        print(f"resume -> {resumed.status_code}", flush=True)
        new_sid = resumed.json().get("session_id")
        after = (await shim.http.get(f"/api/game/sessions/{new_sid}/state")).json()
        state_diff = deep_diff(before, after)
        print(f"state diff entries after save/resume: {len(state_diff)}", flush=True)
        for entry in state_diff[:12]:
            print(f"   {entry}", flush=True)
        ctx.update(session=manager.get(new_sid).game_session, url=f"/api/game/sessions/{new_sid}/turn")

        await turn("F13 look after resume", "Çevreyi gözlemliyorum.")
        await turn("F14 reopen Quenna by name", "Quenna ile konuşmak istiyorum.")
        await turn("F15 small talk", "Günün nasıl geçiyor?", "say")
        await turn("M4 family again", "Ailen var mı?", "say")
        await turn("M5 what did I ask", "Az önce sana ne sormuştum?", "say")
        await turn("F16 end conversation", "Konuşmayı bitiriyorum.")

    results = {
        "adapter_model": adapter.model_name, "campaign_id": campaign_id,
        "save_status": saved.status_code, "resume_status": resumed.status_code,
        "steps": steps, "state_diff": state_diff,
        "raw_model_log": spy.log,
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    await shim.http.aclose()
    server.should_exit = True
    tmp.cleanup()
    bad = [s["step"] for s in steps if s["problems"]]
    print(f"done: {len(steps)} steps, {len(bad)} with problems: {bad}", flush=True)


asyncio.run(main())
