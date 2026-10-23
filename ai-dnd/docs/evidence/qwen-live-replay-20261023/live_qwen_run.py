"""Drive the replay scenarios and the benign sweep against real Qwen over a real loopback port.

Isolated: temporary sqlite, the app listens on 127.0.0.1:PORT only, the only
outbound call is to the local Ollama. Usage: live_qwen_run.py <out.json> <scenarios> [sweep_n]
scenarios: comma list of quenna,door,sweep
"""
import asyncio
import copy
import json
import os
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
os.environ.setdefault("PYTHONUTF8", "1")

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
from api.tests.test_npc_transcript_replay_baseline import (
    CLARIFICATION_MARKER, LORE_REFUSAL_MARKER, NO_CHANGE_MARKER, SWEEP_INPUTS,
)

PORT = 8118
OUT = Path(sys.argv[1])
SCENARIOS = sys.argv[2].split(",")
SWEEP_N = int(sys.argv[3]) if len(sys.argv) > 3 else 12


class Spy:
    """Wraps the real Ollama client; records every raw model reply."""

    def __init__(self, real):
        self._real = real
        self.log = []

    def chat(self, *args, **kwargs):
        started = time.perf_counter()
        response = self._real.chat(*args, **kwargs)
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        raw = game.ollama_response_content(response)
        self.log.append({
            "kind": "narration" if "narration" in properties else "intent",
            "seconds": round(time.perf_counter() - started, 1),
            "raw": raw,
        })
        return response

    def __getattr__(self, name):
        return getattr(self._real, name)


def model_text(raw):
    try:
        packet = json.loads(raw)
        return packet.get("narration")
    except Exception:
        return None


async def main():
    tmp = tempfile.TemporaryDirectory()
    store = CampaignStore(Path(tmp.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
    manager = SessionManager(campaign_store=store)
    import ollama
    from api.ollama_adapter import PROVIDER_TIMEOUT_SECONDS
    real_client = ollama.Client(host="http://127.0.0.1:11434", timeout=PROVIDER_TIMEOUT_SECONDS)
    spy = Spy(real_client)
    adapter = AuthenticatedOllamaAdapter(spy, model_name=os.environ.get("AI_DND_OLLAMA_MODEL", "qwen3:8b"))
    app = create_app(session_manager=manager, ollama_adapter=adapter,
                     authenticator=FixedAuthenticator(TEST_PLAYER))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    print(f"server on 127.0.0.1:{PORT} model={os.environ.get('AI_DND_OLLAMA_MODEL', 'qwen3:8b')}", flush=True)

    shim = unittest.TestCase()
    shim.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=600)
    shim.manager = manager
    results = {}

    async def turn(records, label, session, url, message, mode="do"):
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
        evidence = (captured.get("r") or {}).get("_engine_event_evidence") or {}
        telemetry = evidence.get("telemetry") or {}
        calls = spy.log[before:]
        shown = body.get("narration", "")
        folded = shown.casefold()
        record = {
            "step": label, "input": message, "mode": mode, "http": response.status_code,
            "shown": shown,
            "model_narration": next((model_text(c["raw"]) for c in reversed(calls) if c["kind"] == "narration"), None),
            "model_calls": len(calls),
            "seconds": round(time.perf_counter() - started, 1),
            "fallback_reason": telemetry.get("fallback_reason"),
            "narration_source": telemetry.get("narration_source"),
            "action": (body.get("turn_outcome") or {}).get("action"),
            "status": (body.get("turn_outcome") or {}).get("status"),
            "generic": LORE_REFUSAL_MARKER in folded or NO_CHANGE_MARKER in folded or bool(telemetry.get("fallback_reason")),
            "clarification": CLARIFICATION_MARKER in folded or (body.get("turn_outcome") or {}).get("status") == "clarification",
        }
        records.append(record)
        print(f"  {label:<34} {record['seconds']:>5}s calls={record['model_calls']} reason={record['fallback_reason']} | {shown[:80]}", flush=True)
        return record

    async def fresh():
        _c, _s, session, url, tavern, door = await create_city_with_locked_tavern(shim)
        return session, url, tavern, door

    def hidden_person(session):
        return next(n for n in session.world_state["npcs"]
                    if isinstance(n, dict) and living_world.public_npc_name(n) == "Yakındaki kişi")

    with adapter.engine_binding():
        if "quenna" in SCENARIOS:
            print("== quenna", flush=True)
            records = []
            session, url, tavern, door = await fresh()
            await turn(records, "Q1 look around", session, url, "Çevreyi gözlemliyorum.")
            hidden_person(session)["name"] = "Quenna"
            for label, msg, mode in (
                ("Q2 talk to the nearby person", "Yakındaki kişi ile konuşmak istiyorum.", "do"),
                ("Q3 ask the name", "Selamlar, ismin nedir?", "say"),
                ("Q4 end conversation", "Konuşmayı bitiriyorum.", "do"),
                ("Q5 reopen by name", "Quenna ile konuşmak istiyorum.", "do"),
                ("Q6 how is your day", "Günün nasıl geçiyor?", "do"),
                ("Q7 is there an inn", "Buralarda han varmı?", "say"),
                ("Q8 where is the nearest inn", "En yakın han nerede?", "say"),
            ):
                await turn(records, label, session, url, msg, mode)
            results["quenna"] = records
        if "door" in SCENARIOS:
            print("== door", flush=True)
            records = []
            session, url, tavern, door = await fresh()
            inn = session.world_state["locations"][tavern].get("name", "Han")
            door_name = door.get("name") or f"{inn} Kapısı"
            for label, msg in (
                ("D1 look around", "Çevreyi gözlemliyorum."),
                ("D3b go to the inn by name", f"{inn} yoluna çıkıp oraya gidiyorum"),
                ("D4 knock", f"{inn} kapısını tıklatıyorum belki açarlar"),
                ("D7 try to open", f"{inn} kapısını açmaya çalışıyorum"),
                ("D8 inspect door", "Kapıyı dikkatlice inceliyorum"),
                ("D10 lockpick vague", "Kilidi maymuncukla açmayı deniyorum"),
                ("D13 lockpick exact name", f"{door_name} kilidini maymuncukla açmayı deniyorum"),
            ):
                await turn(records, label, session, url, msg)
            results["door"] = records
        if "sweep" in SCENARIOS:
            print("== sweep", flush=True)
            records = []
            session, url, tavern, door = await fresh()
            await turn(records, "S00 look", session, url, "Çevreyi gözlemliyorum.")
            person = hidden_person(session)
            flags = session.world_state["flags"]
            for index, message in enumerate(SWEEP_INPUTS[:SWEEP_N], start=1):
                flags["active_npc_id"] = person["id"]
                flags["last_npc_id"] = person["id"]
                flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 8
                await turn(records, f"S{index:02d} {message[:22]}", session, url, message, "say")
            results["sweep"] = records

    results["raw_model_log"] = spy.log
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    await shim.http.aclose()
    server.should_exit = True
    tmp.cleanup()
    print("done", flush=True)


asyncio.run(main())
