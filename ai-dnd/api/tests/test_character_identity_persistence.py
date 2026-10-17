"""Prove whether origin, appearance, personality, and backstory survive a real save.

The contract under test is exact equality on the active character and the API
character projection after a new process loads the same temporary SQLite file.
A red result is the finding. This file does not change production code, and it
does not treat a death-rollback checkpoint as the save path.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"
AI_DND_ROOT = Path(__file__).resolve().parents[2]
if str(AI_DND_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_DND_ROOT))

import httpx
import game
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.auth import FixedAuthenticator

PROTECTED_DATABASES = {
    Path(r"C:\Users\Kadir\Desktop\AI - DND\ai-dnd\saves\campaigns.sqlite3").resolve(),
    Path(
        r"C:\Users\Kadir\Desktop\AI - DND\ai-dnd\docs\evidence"
        r"\door-live-231b6cd-20261016\isolated-campaigns.sqlite3"
    ).resolve(),
}
IDENTITY_FIELDS = ("origin", "appearance", "personality", "backstory")
SENTINELS = {
    "origin": "ORIGIN-SENTINEL-kuzey-koyu-7f3a",
    "appearance": "APPEARANCE-SENTINEL-gri-goz-sol-yanak",
    "personality": "PERSONALITY-SENTINEL-sakin-ve-olculu",
    "backstory": "BACKSTORY-SENTINEL-sehir-nobetinden-ayrildi",
}
CONTRACT_INPUT = {
    "origin": "  Kuzey köyü, şığüöçİ  ",
    "appearance": "",
    "personality": None,
    "backstory": "Şehir nöbetinden ayrıldı; yağmurda yürüdü.",
}
CONTRACT_STORED = {
    "origin": "Kuzey köyü, şığüöçİ",
    "appearance": "",
    "personality": None,
    "backstory": "Şehir nöbetinden ayrıldı; yağmurda yürüdü.",
}
MECHANICAL_FIELDS = (
    "name",
    "race",
    "species",
    "class",
    "level",
    "current_hp",
    "max_hp",
    "armor_class",
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)


class FakeProvider:
    """Stand-in provider. Character creation must not call it."""

    def __init__(self):
        self.calls = 0

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Character identity persistence must not call a model")


def character_body(
    *,
    include_identity: bool,
    name: str,
    identity: dict | None = None,
) -> dict:
    body = {
        "mode": "custom",
        "name": name,
        "species": "Human",
        "class": "Fighter",
        "background": "Soldier",
        "alignment": "Lawful Good",
        "ability_score_method": "standard_array",
        "ability_scores": {
            "strength": 15,
            "constitution": 14,
            "dexterity": 13,
            "wisdom": 12,
            "intelligence": 10,
            "charisma": 8,
        },
        "background_ability_bonuses": {"strength": 2, "constitution": 1},
        "proficient_skills": [
            "Athletics",
            "Intimidation",
            "Acrobatics",
            "Perception",
            "History",
        ],
        "species_bonus_skills": ["History"],
        "species_bonus_feat": "Tough",
        "fighting_style": "Defense",
        "equipment_package": "A",
        "background_equipment_option": "A",
        "languages": ["Common", "Dwarvish", "Giant"],
    }
    if identity is not None:
        body.update(identity)
    elif include_identity:
        body.update(SENTINELS)
    return body


def selected_fields(character: dict | None) -> dict:
    source = character if isinstance(character, dict) else {}
    return {
        field: source[field] if field in source else None
        for field in IDENTITY_FIELDS
    }


def selected_mechanical(character: dict | None) -> dict:
    source = character if isinstance(character, dict) else {}
    return {field: source.get(field) for field in MECHANICAL_FIELDS}


def sentinel_paths(value, prefix="$"):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(sentinel_paths(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(sentinel_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str):
        for field, sentinel in SENTINELS.items():
            if sentinel in value:
                found.append({
                    "field": field,
                    "path": prefix,
                    "exact": value == sentinel,
                })
    return found


def read_campaign_payload(database: Path, campaign_id: str | None = None) -> dict:
    connection = sqlite3.connect(database)
    try:
        if campaign_id is None:
            row = connection.execute("SELECT payload_json FROM campaigns").fetchone()
        else:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AssertionError("Temporary campaign database has no campaign row")
    return json.loads(row[0])


def refuse_protected_database(database: Path) -> None:
    resolved = database.resolve()
    if resolved in PROTECTED_DATABASES or resolved.name == "campaigns.sqlite3" and "saves" in resolved.parts:
        raise SystemExit(f"refusing protected database {resolved}")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def create_campaign(
    root: Path,
    *,
    include_identity: bool,
    name: str,
    identity: dict | None = None,
) -> None:
    database = root / "campaigns.sqlite3"
    refuse_protected_database(database)
    store = CampaignStore(database, bound_principal=TEST_PLAYER)
    manager = SessionManager(
        session_factory=lambda: game.create_session(seed=17017),
        campaign_store=store,
    )
    provider = FakeProvider()
    adapter = AuthenticatedOllamaAdapter(provider)
    with adapter.engine_binding():
        app = create_app(
            session_manager=manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created = await client.post("/api/game/campaigns", json={
                "name": name,
                "character": character_body(
                    include_identity=include_identity,
                    name=name,
                    identity=identity,
                ),
            })
            created_body = created.json() if created.headers.get("content-type", "").startswith("application/json") else {"raw": created.text}
            if created.status_code != 200:
                write_json(root / "create.json", {
                    "pid": os.getpid(),
                    "create_status": created.status_code,
                    "create_body": created_body,
                    "provider_calls": provider.calls,
                })
                raise SystemExit(f"create failed: {created.status_code} {created.text[:1000]}")
            campaign_id = created_body["campaign_id"]
            state = created_body["state"]
            live = manager.get(created_body["session_id"]).game_session.character
            saved = await client.post(f"/api/game/campaigns/{campaign_id}/save")
            save_body = saved.json() if saved.headers.get("content-type", "").startswith("application/json") else {"raw": saved.text}
    payload = read_campaign_payload(database)
    player = payload.get("engine_save", {}).get("player", {})
    paths = sentinel_paths(payload)
    checkpoint = (
        payload.get("engine_save", {})
        .get("world_state", {})
        .get("death_state", {})
        .get("combat_checkpoint")
    )
    write_json(root / "create.json", {
        "pid": os.getpid(),
        "create_status": created.status_code,
        "save_status": saved.status_code,
        "save_body_keys": sorted(save_body) if isinstance(save_body, dict) else [],
        "campaign_id": campaign_id,
        "session_id": created_body["session_id"],
        "provider_calls": provider.calls,
        "live_after_create": selected_fields(live),
        "live_after_create_has_field": {
            field: field in live for field in IDENTITY_FIELDS
        },
        "create_projection": selected_fields(state.get("character")),
        "mechanical": selected_mechanical(state.get("character")),
        "location": state.get("location"),
        "sqlite_player": selected_fields(player),
        "sqlite_player_has_field": {
            field: field in player for field in IDENTITY_FIELDS
        },
        "sentinel_paths": paths,
        "combat_checkpoint_present": isinstance(checkpoint, dict),
        "combat_checkpoint_player": selected_fields(
            checkpoint.get("player") if isinstance(checkpoint, dict) else None
        ),
    })
    write_json(root / "campaign.json", {"campaign_id": campaign_id})


async def resume_campaign(root: Path) -> None:
    database = root / "campaigns.sqlite3"
    refuse_protected_database(database)
    campaign_id = json.loads((root / "campaign.json").read_text(encoding="utf-8"))["campaign_id"]
    store = CampaignStore(database, bound_principal=TEST_PLAYER)
    manager = SessionManager(
        session_factory=lambda: game.create_session(seed=17018),
        campaign_store=store,
    )
    provider = FakeProvider()
    adapter = AuthenticatedOllamaAdapter(provider)
    with adapter.engine_binding():
        app = create_app(
            session_manager=manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            body = resumed.json() if resumed.headers.get("content-type", "").startswith("application/json") else {"raw": resumed.text}
            if resumed.status_code != 200:
                write_json(root / "resume.json", {
                    "pid": os.getpid(),
                    "resume_status": resumed.status_code,
                    "resume_body": body,
                    "provider_calls": provider.calls,
                })
                raise SystemExit(f"resume failed: {resumed.status_code} {resumed.text[:1000]}")
    session_id = body["session_id"]
    active = manager.get(session_id).game_session.character
    state = body["state"]
    write_json(root / "resume.json", {
        "pid": os.getpid(),
        "resume_status": resumed.status_code,
        "session_id": session_id,
        "provider_calls": provider.calls,
        "projection": selected_fields(state.get("character")),
        "active_character": selected_fields(active),
        "mechanical": selected_mechanical(state.get("character")),
        "active_mechanical": selected_mechanical(active),
        "location": state.get("location"),
        "active_location": manager.get(session_id).game_session.world_state.get("location"),
    })


async def clear_previous_identity(root: Path) -> None:
    """Load a field-less save into the character that already holds the sentinels."""
    database = root / "campaigns.sqlite3"
    refuse_protected_database(database)
    store = CampaignStore(database, bound_principal=TEST_PLAYER)
    manager = SessionManager(
        session_factory=lambda: game.create_session(seed=17019),
        campaign_store=store,
    )
    provider = FakeProvider()
    adapter = AuthenticatedOllamaAdapter(provider)
    with adapter.engine_binding():
        app = create_app(
            session_manager=manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            identity = await client.post("/api/game/campaigns", json={
                "name": "Kimlik Yolcu",
                "character": character_body(
                    include_identity=True,
                    name="Kimlik Yolcu",
                ),
            })
            legacy = await client.post("/api/game/campaigns", json={
                "name": "Eski Kayit",
                "character": character_body(
                    include_identity=False,
                    name="Eski Kayit",
                ),
            })
            identity_body = identity.json()
            legacy_body = legacy.json()
            if identity.status_code != 200 or legacy.status_code != 200:
                write_json(root / "clear.json", {
                    "identity_status": identity.status_code,
                    "legacy_status": legacy.status_code,
                    "identity_body": identity_body,
                    "legacy_body": legacy_body,
                })
                raise SystemExit("clear setup failed")
            await client.post(
                f"/api/game/campaigns/{identity_body['campaign_id']}/save"
            )
            await client.post(
                f"/api/game/campaigns/{legacy_body['campaign_id']}/save"
            )
    session = manager.get(identity_body["session_id"]).game_session
    character = session.character
    before = selected_fields(character)
    character_id = id(character)
    engine_save = read_campaign_payload(
        database, legacy_body["campaign_id"],
    )["engine_save"]
    for field in IDENTITY_FIELDS:
        engine_save["player"].pop(field, None)
    omitted = root / "legacy-omitted.json"
    omitted.write_text(
        json.dumps(engine_save, ensure_ascii=False),
        encoding="utf-8",
    )
    session.load_game(omitted)
    write_json(root / "clear.json", {
        "pid": os.getpid(),
        "provider_calls": provider.calls,
        "before": before,
        "after": selected_fields(character),
        "same_character_object": id(session.character) == character_id,
        "mechanical": selected_mechanical(session.character),
        "legacy_mechanical": selected_mechanical(
            legacy_body["state"]["character"]
        ),
        "location": session.world_state.get("location"),
        "legacy_location": legacy_body["state"].get("location"),
        "omitted_keys": [field for field in IDENTITY_FIELDS if field not in engine_save["player"]],
    })


def run_phase(phase: str, root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AI_DND_DISABLE_DEFAULT_APP"] = "1"
    env["PYTHONUTF8"] = "1"
    env["AI_DND_CAMPAIGN_DB"] = str(root / "campaigns.sqlite3")
    env.pop("AI_DND_CLERK_SECRET_KEY", None)
    env.pop("CLERK_SECRET_KEY", None)
    return subprocess.run(
        [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", phase, str(root)],
        cwd=str(AI_DND_ROOT),
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )


def load_trace(root: Path, name: str) -> dict:
    path = root / name
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class CharacterIdentityPersistenceTests(unittest.TestCase):
    def test_identity_fields_survive_new_process_resume(self):
        with tempfile.TemporaryDirectory(prefix="character-identity-proof-") as temporary:
            root = Path(temporary)
            created = run_phase("create", root)
            create_trace = load_trace(root, "create.json")
            self.assertEqual(
                created.returncode,
                0,
                (created.stderr or created.stdout or "")[-3000:],
            )
            resumed = run_phase("resume", root)
            resume_trace = load_trace(root, "resume.json")
            trace = {"create": create_trace, "resume": resume_trace}
            print("IDENTITY_TRACE=" + json.dumps(trace, ensure_ascii=False))
            self.assertEqual(resumed.returncode, 0, (resumed.stderr or resumed.stdout or "")[-3000:])
            self.assertNotEqual(create_trace.get("pid"), resume_trace.get("pid"))
            self.assertNotEqual(create_trace.get("session_id"), resume_trace.get("session_id"))
            self.assertEqual(create_trace.get("provider_calls"), 0)
            self.assertEqual(resume_trace.get("provider_calls"), 0)
            self.assertFalse(create_trace.get("combat_checkpoint_present"))
            problems = []
            if create_trace.get("live_after_create") != SENTINELS:
                problems.append(
                    "live character immediately after create "
                    + json.dumps({
                        "values": create_trace.get("live_after_create"),
                        "present": create_trace.get("live_after_create_has_field"),
                    }, ensure_ascii=False)
                )
            if create_trace.get("create_projection") != SENTINELS:
                problems.append(
                    "create API projection "
                    + json.dumps(create_trace.get("create_projection"), ensure_ascii=False)
                )
            if create_trace.get("sqlite_player") != SENTINELS:
                problems.append(
                    "sqlite engine_save.player "
                    + json.dumps({
                        "values": create_trace.get("sqlite_player"),
                        "present": create_trace.get("sqlite_player_has_field"),
                        "other_paths": create_trace.get("sentinel_paths"),
                    }, ensure_ascii=False)
                )
            if resume_trace.get("projection") != SENTINELS:
                problems.append(
                    "resume API projection "
                    + json.dumps(resume_trace.get("projection"), ensure_ascii=False)
                )
            if resume_trace.get("active_character") != SENTINELS:
                problems.append(
                    "resumed active character "
                    + json.dumps(resume_trace.get("active_character"), ensure_ascii=False)
                )
            if resume_trace.get("mechanical") != create_trace.get("mechanical"):
                problems.append(
                    "mechanical projection changed "
                    + json.dumps({
                        "created": create_trace.get("mechanical"),
                        "resumed": resume_trace.get("mechanical"),
                    }, ensure_ascii=False)
                )
            if resume_trace.get("active_mechanical") != create_trace.get("mechanical"):
                problems.append("active mechanical character changed")
            if resume_trace.get("location") != create_trace.get("location"):
                problems.append(
                    f"location {create_trace.get('location')!r} -> {resume_trace.get('location')!r}"
                )
            self.assertFalse(problems, "\n".join(problems))

    def test_save_without_identity_fields_still_loads(self):
        with tempfile.TemporaryDirectory(prefix="character-identity-legacy-") as temporary:
            root = Path(temporary)
            created = run_phase("legacy-create", root)
            self.assertEqual(
                created.returncode,
                0,
                (created.stderr or created.stdout or "")[-3000:],
            )
            resumed = run_phase("legacy-resume", root)
            create_trace = load_trace(root, "create.json")
            resume_trace = load_trace(root, "resume.json")
            print("LEGACY_TRACE=" + json.dumps({
                "create_status": create_trace.get("create_status"),
                "resume_status": resume_trace.get("resume_status"),
                "sqlite_player_has_field": create_trace.get("sqlite_player_has_field"),
                "resume_projection": resume_trace.get("projection"),
                "mechanical_match": resume_trace.get("mechanical") == create_trace.get("mechanical"),
                "location_match": resume_trace.get("location") == create_trace.get("location"),
            }, ensure_ascii=False))
            self.assertEqual(resumed.returncode, 0, (resumed.stderr or resumed.stdout or "")[-3000:])
            self.assertNotEqual(create_trace.get("pid"), resume_trace.get("pid"))
            self.assertEqual(create_trace.get("create_status"), 200)
            self.assertEqual(resume_trace.get("resume_status"), 200)
            empty = {field: None for field in IDENTITY_FIELDS}
            self.assertEqual(create_trace["live_after_create"], empty)
            self.assertEqual(create_trace["create_projection"], empty)
            self.assertEqual(create_trace["sqlite_player"], empty)
            for field in IDENTITY_FIELDS:
                self.assertIsNone(resume_trace["projection"][field])
                self.assertIsNone(resume_trace["active_character"][field])
            self.assertEqual(resume_trace["mechanical"], create_trace["mechanical"])
            self.assertEqual(resume_trace["active_mechanical"], create_trace["mechanical"])
            self.assertEqual(resume_trace["location"], create_trace["location"])
            self.assertEqual(
                resume_trace["active_location"],
                create_trace["location"],
            )

    def test_omitted_save_clears_identity_on_the_same_character(self):
        with tempfile.TemporaryDirectory(prefix="character-identity-clear-") as temporary:
            root = Path(temporary)
            completed = run_phase("clear", root)
            trace = load_trace(root, "clear.json")
            print("CLEAR_TRACE=" + json.dumps(trace, ensure_ascii=False))
            self.assertEqual(
                completed.returncode,
                0,
                (completed.stderr or completed.stdout or "")[-3000:],
            )
            self.assertEqual(trace["provider_calls"], 0)
            self.assertEqual(trace["before"], SENTINELS)
            self.assertTrue(trace["same_character_object"])
            self.assertEqual(trace["omitted_keys"], list(IDENTITY_FIELDS))
            for field in IDENTITY_FIELDS:
                self.assertIsNone(trace["after"][field])
            self.assertEqual(trace["mechanical"], trace["legacy_mechanical"])
            self.assertEqual(trace["location"], trace["legacy_location"])
            self.assertNotEqual(trace["mechanical"]["name"], "Kimlik Yolcu")

    def test_turkish_empty_and_null_follow_the_input_contract(self):
        with tempfile.TemporaryDirectory(prefix="character-identity-contract-") as temporary:
            root = Path(temporary)
            created = run_phase("contract-create", root)
            self.assertEqual(
                created.returncode,
                0,
                (created.stderr or created.stdout or "")[-3000:],
            )
            resumed = run_phase("contract-resume", root)
            create_trace = load_trace(root, "create.json")
            resume_trace = load_trace(root, "resume.json")
            print("CONTRACT_TRACE=" + json.dumps({
                "create_projection": create_trace.get("create_projection"),
                "sqlite_player": create_trace.get("sqlite_player"),
                "resume_projection": resume_trace.get("projection"),
                "active_character": resume_trace.get("active_character"),
            }, ensure_ascii=False))
            self.assertEqual(resumed.returncode, 0, (resumed.stderr or resumed.stdout or "")[-3000:])
            self.assertNotEqual(create_trace.get("pid"), resume_trace.get("pid"))
            self.assertNotEqual(create_trace.get("session_id"), resume_trace.get("session_id"))
            self.assertEqual(create_trace.get("provider_calls"), 0)
            self.assertEqual(resume_trace.get("provider_calls"), 0)
            self.assertEqual(create_trace["live_after_create"], CONTRACT_STORED)
            self.assertEqual(create_trace["create_projection"], CONTRACT_STORED)
            self.assertEqual(create_trace["sqlite_player"], CONTRACT_STORED)
            self.assertEqual(resume_trace["projection"], CONTRACT_STORED)
            self.assertEqual(resume_trace["active_character"], CONTRACT_STORED)
            self.assertEqual(resume_trace["mechanical"], create_trace["mechanical"])
            self.assertEqual(resume_trace["active_mechanical"], create_trace["mechanical"])
            self.assertEqual(resume_trace["location"], create_trace["location"])

    def test_save_keeps_text_exactly_and_rejects_non_text(self):
        session = game.create_session(seed=17020)
        session.character["origin"] = "  şığüöçİ  "
        session.character["appearance"] = ""
        session.character["personality"] = None
        session.character["backstory"] = "Yağmurda yürüdü."
        saved = session.serialize_game_state()["player"]
        self.assertEqual(saved["origin"], "  şığüöçİ  ")
        self.assertEqual(saved["appearance"], "")
        self.assertIsNone(saved["personality"])
        self.assertEqual(saved["backstory"], "Yağmurda yürüdü.")
        session.character["appearance"] = ["gri", "göz"]
        with self.assertRaises(ValueError):
            session.serialize_game_state()
        self.assertEqual(session.character["appearance"], ["gri", "göz"])
        session.character["appearance"] = "Görünüş"
        with tempfile.TemporaryDirectory(prefix="character-identity-reject-") as temporary:
            path = Path(temporary) / "identity.json"
            session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["player"]["origin"] = {"text": "sözlük"}
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                session.load_game(path)
        self.assertEqual(session.character["origin"], "  şığüöçİ  ")
        self.assertEqual(session.character["appearance"], "Görünüş")
        self.assertIsNone(session.character["personality"])
        self.assertEqual(session.character["backstory"], "Yağmurda yürüdü.")

    def test_rejected_identity_load_restores_the_whole_session(self):
        session = game.create_session(seed=17021)
        session.character["origin"] = SENTINELS["origin"]
        session.character["appearance"] = SENTINELS["appearance"]
        session.character["personality"] = SENTINELS["personality"]
        session.character["backstory"] = SENTINELS["backstory"]
        session.world_state["inventory"].append("CANLI-KILIC")
        session.recent_dm_narrations.append("Canlı geçmiş")
        session.messages.append({"role": "user", "content": "canlı mesaj"})
        session.roll_d20()
        with tempfile.TemporaryDirectory(prefix="character-identity-atomic-") as temporary:
            path = Path(temporary) / "identity.json"
            session.save_game(path)
            original = json.loads(path.read_text(encoding="utf-8"))
            before = _session_snapshot(session)
            invalid = {
                "origin": ["MARKER-ORIGIN-LIST"],
                "appearance": {"marker": "MARKER-APPEARANCE-DICT"},
                "personality": ["MARKER-PERSONALITY-LIST"],
                "backstory": {"marker": "MARKER-BACKSTORY-DICT"},
            }
            for field, bad in invalid.items():
                with self.subTest(field=field):
                    payload = _diverged_identity_payload(original, field, bad)
                    path.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError) as caught:
                        session.load_game(path)
                    self.assertEqual(str(caught.exception), "Kayıt kimlik metni geçersiz.")
                    self.assertNotIn("MARKER", str(caught.exception))
                    self.assertEqual(_session_snapshot(session), before)

    def test_api_rejects_corrupt_identity_and_keeps_the_active_campaign(self):
        with tempfile.TemporaryDirectory(prefix="character-identity-api-atomic-") as temporary:
            root = Path(temporary)
            database = root / "campaigns.sqlite3"
            refuse_protected_database(database)
            store = CampaignStore(database, bound_principal=TEST_PLAYER)
            manager = SessionManager(
                session_factory=lambda: game.create_session(seed=17022),
                campaign_store=store,
            )
            provider = FakeProvider()
            adapter = AuthenticatedOllamaAdapter(provider)
            with adapter.engine_binding():
                app = create_app(
                    session_manager=manager,
                    ollama_adapter=adapter,
                    authenticator=FixedAuthenticator(TEST_PLAYER),
                )
                created = asyncio.run(_post_json(app, "/api/game/campaigns", {
                    "name": "Kimlik Yolcu",
                    "character": character_body(
                        include_identity=True,
                        name="Kimlik Yolcu",
                    ),
                }))
                self.assertEqual(created.status_code, 200, created.text[:500])
                created_body = created.json()
                campaign_id = created_body["campaign_id"]
                session_id = created_body["session_id"]
                saved = asyncio.run(_post_json(
                    app, f"/api/game/campaigns/{campaign_id}/save", None,
                ))
                self.assertEqual(saved.status_code, 200, saved.text[:500])
                record = manager.get(session_id)
                session = record.game_session
                session.world_state["inventory"].append("CANLI-KILIC")
                session.recent_dm_narrations.append("Canlı geçmiş")
                session.messages.append({"role": "user", "content": "canlı mesaj"})
                session.roll_d20()
                before = _session_snapshot(session)
                journal = copy.deepcopy(record.journal)
                persistence = getattr(session, "_campaign_persistence_version", None)
                _corrupt_stored_identity(
                    database,
                    campaign_id,
                    "backstory",
                    {"marker": "MARKER-BACKSTORY-DICT"},
                )
                other = SessionManager(
                    session_factory=lambda: game.create_session(seed=17023),
                    campaign_store=CampaignStore(database, bound_principal=TEST_PLAYER),
                )
                other_provider = FakeProvider()
                other_adapter = AuthenticatedOllamaAdapter(other_provider)
                with other_adapter.engine_binding():
                    other_app = create_app(
                        session_manager=other,
                        ollama_adapter=other_adapter,
                        authenticator=FixedAuthenticator(TEST_PLAYER),
                    )
                    rejected = asyncio.run(_post_json(
                        other_app,
                        f"/api/game/campaigns/{campaign_id}/resume",
                        None,
                    ))
                self.assertEqual(rejected.status_code, 409, rejected.text[:500])
                detail = rejected.json()["detail"]
                self.assertEqual(detail["code"], "campaign_unavailable")
                self.assertEqual(
                    detail["message"],
                    "Bu macera kaydı güvenli biçimde yüklenemedi.",
                )
                self.assertNotIn("MARKER", rejected.text)
                self.assertNotIn("BOZUK", rejected.text)
                self.assertEqual(other_provider.calls, 0)
                state = asyncio.run(_get_json(
                    app, f"/api/game/sessions/{session_id}/state",
                ))
                self.assertEqual(state.status_code, 200, state.text[:500])
                projected = state.json()
                self.assertEqual(selected_fields(projected["character"]), SENTINELS)
                self.assertIn("CANLI-KILIC", projected["inventory"])
                self.assertEqual(_session_snapshot(session), before)
                self.assertEqual(record.journal, journal)
                self.assertTrue(record.usable)
                self.assertEqual(record.campaign_id, campaign_id)
                self.assertIs(manager.get(session_id), record)
                self.assertEqual(
                    getattr(session, "_campaign_persistence_version", None),
                    persistence,
                )
                rewritten = asyncio.run(_post_json(
                    app, f"/api/game/campaigns/{campaign_id}/save", None,
                ))
                self.assertEqual(rewritten.status_code, 200, rewritten.text[:500])
                stored = read_campaign_payload(database, campaign_id)
                self.assertEqual(selected_fields(stored["engine_save"]["player"]), SENTINELS)
                self.assertNotIn("MARKER", json.dumps(stored, ensure_ascii=False))
                self.assertEqual(provider.calls, 0)


def _session_snapshot(session) -> dict:
    return {
        "character_id": id(session.character),
        "world_id": id(session.world_state),
        "narration_id": id(session.recent_dm_narrations),
        "message_id": id(session.messages),
        "rng_id": id(session.rng),
        "character": copy.deepcopy(session.character),
        "world": copy.deepcopy(session.world_state),
        "narrations": list(session.recent_dm_narrations),
        "messages": copy.deepcopy(session.messages),
        "rng": session.rng.getstate(),
        "format": session._persisted_engine_format,
    }


def _diverged_identity_payload(original: dict, field: str, bad) -> dict:
    payload = copy.deepcopy(original)
    player = payload["player"]
    world = payload["world_state"]
    player["class"] = "Wizard"
    player["current_hp"] = 1
    player["max_hp"] = max(int(player["max_hp"]), 30)
    player["armor_class"] = 3
    player["strength"] = 8
    current = world.get("location")
    locations = world.setdefault("locations", {})
    if isinstance(locations, dict) and isinstance(locations.get(current), dict):
        moved = copy.deepcopy(locations[current])
        moved["name"] = "Bozuk Yer"
        locations["loc-bozuk"] = moved
        world["location"] = "loc-bozuk"
    inventory = world.setdefault("inventory", [])
    if isinstance(inventory, list):
        inventory.append("BOZUK-KILIC")
    payload["recent_dm_narrations"] = ["BOZUK GECMIS"]
    player["origin"] = "FARKLI-KOKEN"
    player["appearance"] = "FARKLI-GORUNUS"
    player["personality"] = "FARKLI-KISILIK"
    player["backstory"] = "FARKLI-GECMIS"
    player[field] = bad
    return payload


def _corrupt_stored_identity(database: Path, campaign_id: str, field: str, bad) -> None:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        payload = json.loads(row[0])
        diverged = _diverged_identity_payload(payload["engine_save"], field, bad)
        payload["engine_save"] = diverged
        player = diverged["player"]
        world = diverged["world_state"]
        connection.execute(
            """
            UPDATE campaigns
            SET payload_json = ?, character_class = ?, character_level = ?, location = ?
            WHERE campaign_id = ?
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                str(player["class"]),
                int(player["level"]),
                str(world["location"]),
                campaign_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


async def _post_json(app, path: str, body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        if body is None:
            return await client.post(path)
        return await client.post(path, json=body)


async def _get_json(app, path: str):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        phase = sys.argv[2]
        root = Path(sys.argv[3])
        if phase == "create":
            asyncio.run(create_campaign(
                root, include_identity=True, name="Kimlik Yolcu",
            ))
        elif phase == "resume":
            asyncio.run(resume_campaign(root))
        elif phase == "legacy-create":
            asyncio.run(create_campaign(
                root, include_identity=False, name="Eski Kayit",
            ))
        elif phase == "legacy-resume":
            asyncio.run(resume_campaign(root))
        elif phase == "contract-create":
            asyncio.run(create_campaign(
                root,
                include_identity=False,
                name="Sözleşme Yolcu",
                identity=CONTRACT_INPUT,
            ))
        elif phase == "contract-resume":
            asyncio.run(resume_campaign(root))
        elif phase == "clear":
            asyncio.run(clear_previous_identity(root))
        else:
            raise SystemExit(f"unknown phase {phase}")
    else:
        unittest.main()
