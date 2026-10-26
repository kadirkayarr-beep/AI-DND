"""Phase 7 short A-H loops against the local Ollama, off the player port.

Isolated temporary SQLite and a free loopback port. The only outbound call is
127.0.0.1:11434. The model name is taken from each Ollama response, not from
the source constant. This run does not claim the older live incident is fixed.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx
import ollama
import uvicorn

import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.local_model_config import PRODUCTION_LOCAL_MODEL
from api.ollama_adapter import PROVIDER_TIMEOUT_SECONDS, AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER

OUT = Path(__file__).with_name("faz7-ah-qwen35-9b.jsonl")
HOST = "http://127.0.0.1:11434"
MODEL = PRODUCTION_LOCAL_MODEL


class Spy:
    def __init__(self, real):
        self._real = real
        self.calls = []

    def chat(self, *args, **kwargs):
        started = time.perf_counter()
        response = self._real.chat(*args, **kwargs)
        if isinstance(response, dict):
            seen = response.get("model")
        else:
            seen = getattr(response, "model", None)
            dump = getattr(response, "model_dump", None)
            if not isinstance(seen, str) and callable(dump):
                data = dump()
                seen = data.get("model") if isinstance(data, dict) else None
        schema = kwargs.get("format") or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        self.calls.append({
            "kind": "intent" if "intent" in properties else "narration",
            "model_sent": kwargs.get("model"),
            "model_seen": seen,
            "seconds": round(time.perf_counter() - started, 1),
        })
        return response

    def __getattr__(self, name):
        return getattr(self._real, name)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fingerprint(session):
    world = session.world_state
    combat = world.get("combat") if isinstance(world.get("combat"), dict) else {}
    marks = {
        feature_id: [mark.get("text") for mark in rows if isinstance(mark, dict)]
        for feature_id, rows in (world.get("feature_marks") or {}).items()
    }
    return {
        "location": world.get("location"),
        "hp": session.character.get("current_hp"),
        "combat": bool(combat.get("active")),
        "marks": marks,
        "npc_hp": {
            npc.get("id"): npc.get("current_hp")
            for npc in (world.get("npcs") or [])
            if isinstance(npc, dict)
        },
        "absence": [
            event.get("event_id")
            for event in (world.get("scheduled_events") or [])
            if isinstance(event, dict) and event.get("status") == "PENDING"
            and isinstance(event.get("effect"), dict)
            and event["effect"].get("kind") == "table_absence"
        ],
    }


def main() -> int:
    listed = ollama.Client(host=HOST, timeout=10).list()
    names = []
    models = listed.get("models") if isinstance(listed, dict) else getattr(listed, "models", [])
    for model in models or []:
        if isinstance(model, dict):
            name = model.get("name") or model.get("model")
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)
        if isinstance(name, str):
            names.append(name)
    if MODEL not in names:
        print(f"BLOCKED: {MODEL} is not in the local Ollama tags", flush=True)
        return 2
    port = free_port()
    if port == 8008:
        port = free_port()
    tmp = tempfile.TemporaryDirectory()
    store = CampaignStore(Path(tmp.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
    manager = SessionManager(campaign_store=store)
    spy = Spy(ollama.Client(host=HOST, timeout=PROVIDER_TIMEOUT_SECONDS))
    adapter = AuthenticatedOllamaAdapter(spy, model_name=MODEL)
    app = create_app(
        session_manager=manager, ollama_adapter=adapter,
        authenticator=FixedAuthenticator(TEST_PLAYER),
    )
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    rows = []

    def campaign(http, *, npc=True):
        created = http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": "fr:city:neverwinter",
        }})
        created.raise_for_status()
        body = created.json()
        session = manager.get(body["session_id"]).game_session
        if npc:
            created_npc = session.create_npc_from_ai({
                "name": "Hlin", "role": "Han görevlisi",
                "location": session.world_state["location"],
                "appearance": "Tezgâhın yanında duran görevli.",
            }, session=session)
            created_npc.update(name_known_to_player=True, role_known_to_player=True, current_hp=12, max_hp=12)
        return body["session_id"], session

    def prepare_attack(session):
        npc = next(item for item in session.world_state["npcs"] if item.get("name") == "Hlin")
        npc["distance_ft"] = 5
        npc["armor_class"] = 10
        npc["current_hp"] = 20
        npc["max_hp"] = 20
        session.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        session.world_state.setdefault("flags", {})["active_npc_id"] = npc["id"]
        hands = session.world_state.get("equipment")
        if not isinstance(hands, dict) or set(hands) != {"main_hand", "off_hand"}:
            hands = {"main_hand": None, "off_hand": None}
            session.world_state["equipment"] = hands
        if not (hands.get("main_hand") or hands.get("off_hand")):
            import weapon_attack
            owned = None
            for item in session.world_state.get("inventory") or []:
                name = item.get("name") if isinstance(item, dict) else item
                if isinstance(name, str) and weapon_attack.lookup(name):
                    owned = name
                    break
            if owned is None:
                owned = "longsword"
                session.world_state.setdefault("inventory", []).append(owned)
            hands["main_hand"] = owned
        return {"hands": dict(hands), "distance_ft": npc.get("distance_ft"), "npc_id": npc["id"]}

    def seed_han(session):
        import grounded_action
        import living_world
        world = session.world_state
        city = world["location"]
        living_world.materialize_scene(
            world, city, 0,
            create_npc=session.create_npc_from_ai,
            create_feature=session.create_local_feature,
        )
        place = grounded_action._create_venue(
            grounded_action._Run(session, "faz7 diagnose"), city,
            name="Kanıt Hanı", kind="tavern", noun="han",
            provenance={"kind": "faz7_diagnose"},
        )
        if not isinstance(place, dict):
            return None, None
        door = next(item for item in world.get("doors", []) if item.get("id") == "venue-door:" + place["id"])
        door.update(open=False, locked=False, broken=False)
        world["location"] = place["id"]
        try:
            table = session.create_local_feature({
                "name": "Boş masa", "location": place["id"], "kind": "table",
                "description": "Kimsenin oturmadığı sade bir masa.",
            }, session=session)
            npc = session.create_npc_from_ai({
                "name": "Hlin", "role": "Han görevlisi", "location": place["id"],
                "appearance": "Tezgâhın yanında duran görevli.",
            }, session=session)
            if isinstance(npc, dict):
                npc.update(name_known_to_player=True, role_known_to_player=True, current_hp=12, max_hp=12)
        finally:
            world["location"] = city
            world.setdefault("scene_state", {}).pop("entry_target_reference", None)
            world.setdefault("flags", {}).pop("active_npc_id", None)
        return place, table

    def turn(http, case, session_id, session, message, mode):
        before_calls = len(spy.calls)
        before = fingerprint(session)
        started = time.perf_counter()
        response = http.post(
            f"/api/game/sessions/{session_id}/turn",
            json={"message": message, "interaction_mode": mode, "action_id": str(uuid.uuid4())},
        )
        elapsed = round(time.perf_counter() - started, 1)
        payload = response.json() if "json" in response.headers.get("content-type", "") else {}
        session_now = manager.get(session_id).game_session
        after = fingerprint(session_now)
        calls = spy.calls[before_calls:]
        outcome = payload.get("turn_outcome") if isinstance(payload, dict) else None
        row = {
            "case": case, "mode": mode, "input": message,
            "http": response.status_code,
            "seconds": elapsed,
            "shown": payload.get("narration") if isinstance(payload, dict) else None,
            "action": (outcome or {}).get("action") if isinstance(outcome, dict) else None,
            "status": (outcome or {}).get("status") if isinstance(outcome, dict) else None,
            "model_sent": [call["model_sent"] for call in calls],
            "model_seen": [call["model_seen"] for call in calls],
            "model_calls": len(calls),
            "before": before, "after": after,
            "detail": None if response.status_code == 200 else payload,
        }
        rows.append(row)
        print(
            f"{case:<8} {response.status_code} {elapsed:>6}s calls={len(calls)} "
            f"seen={row['model_seen']} | {str(row['shown'] or row['detail'])[:90]}",
            flush=True,
        )
        return row

    adapter.install_for_engine()
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    if not server.started:
        print("BLOCKED: isolated API did not start", flush=True)
        return 2
    print(f"isolated API 127.0.0.1:{port}", flush=True)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=240) as http:
            health = http.get("/api/health")
            print(f"health {health.status_code} {health.text[:180]}", flush=True)
            diagnose = "diagnose" in sys.argv
            rerun = any(flag in sys.argv for flag in ("rerun", "rerun2", "rerun3", "rerun4", "rerun5", "rerun6", "rerun7"))
            if rerun:
                session_id, session = campaign(http)
                dialogue = (
                    ("A", "Nasılsın dostum?", "say"),
                    ("B", "Eğlenmiş görünerek bir şaka yapıyorum.", "do"),
                    ("G", "O espriye neden öyle tepki verdin?", "say"),
                    ("C1", "Kitaplar bile kimlik gösteriyor mu?", "say"),
                    ("C2", "Gülümseyip 'Kitaplar bile kimlik gösteriyor mu?' diyorum.", "do"),
                    ("E1", "Sana saldıracağım.", "say"),
                    ("E2", "'Ona saldırıyorum' diye yazan notu okuyorum.", "do"),
                    ("E3", "O bana saldırırsa kendimi savunacağım.", "do"),
                    ("E4", "Sinirliyim ama ona saldırmıyorum.", "do"),
                    ("E5", "Ona saldırsam ne olur?", "ask_dm"),
                    ("F", "Tezgâhın altını sistemli inceliyorum.", "do"),
                )
                for case, message, mode in dialogue:
                    turn(http, case, session_id, session, message, mode)
                attack_id, attack_session = campaign(http)
                rows.append({"case": "D-fixture", **prepare_attack(attack_session)})
                turn(http, "D", attack_id, attack_session, "Sinirlenip ona saldırıyorum.", "do")
                room_id, room = campaign(http, npc=False)
                place, table = seed_han(room)
                if not isinstance(place, dict) or not isinstance(table, dict):
                    rows.append({"case": "H0", "detail": "han or table was not created"})
                else:
                    turn(http, "H-approach", room_id, room, "Kanıt Hanı kapısına yaklaşıyorum.", "do")
                    turn(http, "H-enter", room_id, room, "İçeri giriyorum.", "do")
                    turn(http, "H-sit", room_id, room, "Boş masaya oturuyorum.", "do")
                    turn(http, "H-barman", room_id, room, "Barmene günün nasıl geçtiğini soruyorum.", "say")
                    turn(http, "H-search", room_id, room, "Masada gizli bir çekmece arıyorum.", "do")
                    turn(http, "H-look", room_id, room, "Boş masaya bakıyorum.", "do")
                    turn(http, "H-mark", room_id, room, f'/item mark {table["id"]} "eski iz"', "do")
                    turn(http, "H-leave", room_id, room, "Dışarı çıkıyorum.", "do")
                    turn(http, "H-approach-2", room_id, room, "Kanıt Hanı kapısına yaklaşıyorum.", "do")
                    turn(http, "H-return", room_id, room, "İçeri giriyorum.", "do")
            elif diagnose:
                quote_id, quote = campaign(http)
                turn(http, "E2", quote_id, quote, "'Ona saldırıyorum' diye yazan notu okuyorum.", "do")
                turn(http, "E3", quote_id, quote, "O bana saldırırsa kendimi savunacağım.", "do")
                attack_id, attack_session = campaign(http)
                rows.append({"case": "D-fixture", **prepare_attack(attack_session)})
                turn(http, "D", attack_id, attack_session, "Sinirlenip ona saldırıyorum.", "do")
                room_id, room = campaign(http, npc=False)
                place, table = seed_han(room)
                if not isinstance(place, dict) or not isinstance(table, dict):
                    rows.append({"case": "H0", "detail": "han or table was not created"})
                else:
                    turn(http, "H-approach", room_id, room, "Kanıt Hanı kapısına yaklaşıyorum.", "do")
                    turn(http, "H-enter", room_id, room, "İçeri giriyorum.", "do")
                    turn(http, "H-mark", room_id, room, f'/item mark {table["id"]} "eski iz"', "do")
                    turn(http, "H-leave", room_id, room, "Dışarı çıkıyorum.", "do")
                    turn(http, "H-approach-2", room_id, room, "Kanıt Hanı kapısına yaklaşıyorum.", "do")
                    turn(http, "H-return", room_id, room, "İçeri giriyorum.", "do")
            else:
                session_id, session = campaign(http)
                dialogue = (
                    ("A", "Nasılsın dostum?", "say"),
                    ("B", "Eğlenmiş görünerek bir şaka yapıyorum.", "do"),
                    ("G", "O espriye neden öyle tepki verdin?", "say"),
                    ("C1", "Kitaplar bile kimlik gösteriyor mu?", "say"),
                    ("C2", "Gülümseyip 'Kitaplar bile kimlik gösteriyor mu?' diyorum.", "do"),
                    ("E1", "Sana saldıracağım.", "say"),
                    ("E2", "'Ona saldırıyorum' diye yazan notu okuyorum.", "do"),
                    ("E3", "O bana saldırırsa kendimi savunacağım.", "do"),
                    ("E4", "Sinirliyim ama ona saldırmıyorum.", "do"),
                    ("E5", "Ona saldırsam ne olur?", "ask_dm"),
                )
                for case, message, mode in dialogue:
                    turn(http, case, session_id, session, message, mode)
                attack_id, attack_session = campaign(http)
                turn(http, "D", attack_id, attack_session, "Sinirlenip ona saldırıyorum.", "do")
                scene_id, scene = campaign(http)
                table = scene.create_local_feature({
                    "name": "Boş masa", "location": scene.world_state["location"],
                    "kind": "table", "description": "Kimsenin oturmadığı sade bir masa.",
                }, session=scene)
                if table is None:
                    rows.append({"case": "H0", "http": None, "shown": None, "detail": "table was not created"})
                else:
                    turn(http, "H-look", scene_id, scene, "Etrafıma bakıyorum.", "do")
                    turn(http, "H-mark", scene_id, scene, f'/item mark {table["id"]} "eski iz"', "do")
                    turn(http, "H-sit", scene_id, scene, "Boş masaya oturuyorum.", "do")
                    turn(http, "H-leave", scene_id, scene, "Dışarı çıkıyorum.", "do")
            out = Path(__file__).with_name(
                "faz7-rerun7-qwen35-9b.jsonl" if "rerun7" in sys.argv
                else "faz7-rerun6-qwen35-9b.jsonl" if "rerun6" in sys.argv
                else "faz7-rerun5-qwen35-9b.jsonl" if "rerun5" in sys.argv
                else "faz7-rerun4-qwen35-9b.jsonl" if "rerun4" in sys.argv
                else "faz7-rerun3-qwen35-9b.jsonl" if "rerun3" in sys.argv
                else "faz7-rerun2-qwen35-9b.jsonl" if "rerun2" in sys.argv
                else "faz7-rerun-qwen35-9b.jsonl" if rerun
                else "faz7-diagnose-qwen35-9b.jsonl" if diagnose
                else "faz7-ah-qwen35-9b.jsonl"
            )
        header = {
            "case": "META", "ollama_tags": names, "model": MODEL,
            "port": port, "player_port_8008": "not used",
        }
        out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in [header, *rows]) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out}", flush=True)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
