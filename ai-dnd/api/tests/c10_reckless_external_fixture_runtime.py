"""Disposable synthetic C10 Reckless ASGI fixture. Importing this module starts nothing.

The caller must verify its source bundle before importing it and supply the
bundle's static manifest. This validates containment/provenance assertions, not
a kernel sandbox. No TCP-serving or browser-launching path is implemented here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import UUID


ENTRY_PATH = "/tests/r02-live-fixture/index.html"
OWNED_MARKER = ".c06-manual-owned.json"
PURPOSE = "ai-dnd-c06-manual-fixture-v1"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "font-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
MAX_BODY_BYTES = 65536
MAX_TRACE_BYTES = 4 * 1024 * 1024
MAX_STATIC_BYTES = 32 * 1024 * 1024
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
_PREFIX = r"/api(?:/game)?"
_GET = re.compile(_PREFIX + rf"/(?:health|character-options|character-creation-catalog|campaign-start-options|campaigns(?:/{_UUID})?|sessions/{_UUID}/state)\Z")
_UNRESOLVED = re.compile(rf"/api/game/sessions/{_UUID}/actions/unresolved\Z")
_ATTACK_TURN = re.compile(_PREFIX + rf"/sessions/{_UUID}/turn\Z")
_ACTION_STATUS = re.compile(rf"/api/game/sessions/{_UUID}/actions/{_UUID}\Z")
_ABANDON = re.compile(rf"/api/game/sessions/{_UUID}/actions/{_UUID}/abandon\Z")
_CREATE = re.compile(_PREFIX + r"/campaigns\Z")
_SAVE_RESUME = re.compile(_PREFIX + rf"/campaigns/{_UUID}/(?:save|resume)\Z")
_MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
         ".webp": "image/webp", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2"}


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _plain_path(path: Path, *, exists: bool = True, directory: bool = False) -> Path:
    """Reject every symlink/reparse component before a resolve or file read."""
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("Fixture paths must be absolute and canonical")
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Fixture symlinks and reparse points are forbidden")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Fixture parent is not a directory")
    try:
        info = path.lstat()
    except FileNotFoundError:
        if exists:
            raise ValueError("Required fixture path is missing") from None
        return path
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Fixture directory is not a directory")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Fixture files must be ordinary, singly linked files")
    return path


def _safe_member(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
        raise ValueError("Unsafe static manifest path")
    parts = name.split("/")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(not p or p in {".", ".."} or p.startswith(".") or p.endswith(".")
           or p.split(".")[0].casefold() in reserved for p in parts):
        raise ValueError("Unsafe static manifest component")
    suffix = PurePosixPath(name).suffix
    if suffix not in _MIME or (suffix == ".html" and "/" + name != ENTRY_PATH):
        raise ValueError("Only prebuilt browser assets may be served")
    if suffix in {".js", ".css"} and not name.startswith("assets/"):
        raise ValueError("Scripts and styles must be prebuilt assets")


def _validate_manifest(manifest):
    if type(manifest) is not dict or not manifest or len(manifest) > 2048:
        raise ValueError("A bounded static manifest is required")
    seen = set()
    for name, metadata in manifest.items():
        _safe_member(name)
        if name.casefold() in seen:
            raise ValueError("Case-colliding static names")
        seen.add(name.casefold())
        if (type(metadata) is not dict or set(metadata) != {"sha256", "size"}
                or not isinstance(metadata["sha256"], str) or not _HEX.fullmatch(metadata["sha256"])
                or type(metadata["size"]) is not int or not 0 <= metadata["size"] <= MAX_STATIC_BYTES):
            raise ValueError("Invalid static manifest metadata")
    if ENTRY_PATH[1:] not in manifest or sum(m["size"] for m in manifest.values()) > MAX_STATIC_BYTES:
        raise ValueError("Static manifest lacks the fixture entry or exceeds its bound")


def _verify_marker(run_root, static_root, bundle_sha256, static_manifest):
    _plain_path(run_root, directory=True)
    marker_path = _plain_path(run_root / OWNED_MARKER)
    if marker_path.stat().st_size > 16384:
        raise ValueError("Owned marker is too large")
    try:
        marker = json.loads(marker_path.read_bytes())
    except (ValueError, UnicodeError):
        raise ValueError("Invalid owned fixture marker") from None
    expected = {"purpose": PURPOSE, "run_root": str(run_root), "static_root": str(static_root),
                "bundle_sha256": bundle_sha256,
                "static_manifest_sha256": hashlib.sha256(_canonical_json(static_manifest)).hexdigest()}
    if marker != expected:
        raise ValueError("Owned fixture marker does not match this bundle/run")


def _check_runtime(run_root):
    _plain_path(run_root, directory=True)
    db_dir = run_root / "db"
    _plain_path(db_dir, exists=False, directory=True)
    allowed = {"campaigns.sqlite3", "campaigns.sqlite3-journal", "campaigns.sqlite3-wal", "campaigns.sqlite3-shm"}
    if db_dir.exists():
        if {p.name for p in db_dir.iterdir()} - allowed:
            raise ValueError("Unexpected file in fixture database directory")
        for name in allowed:
            _plain_path(db_dir / name, exists=False)


def _static_bytes(static_root, manifest):
    _plain_path(static_root, directory=True)
    found = set()
    case_paths = set()
    for directory, directories, files in os.walk(static_root, followlinks=False):
        for name in [*directories, *files]:
            path = Path(directory) / name
            _plain_path(path, directory=name in directories)
            relative = path.relative_to(static_root).as_posix()
            if relative.casefold() in case_paths:
                raise ValueError("Case-colliding static paths")
            case_paths.add(relative.casefold())
        found.update((Path(directory) / name).relative_to(static_root).as_posix() for name in files)
    if found != set(manifest):
        raise ValueError("Static files do not exactly match the manifest")
    result = {}
    for name, metadata in manifest.items():
        path = _plain_path(static_root / name)
        if path.stat().st_size != metadata["size"]:
            raise ValueError("Static file size mismatch")
        content = path.read_bytes()
        if len(content) != metadata["size"] or hashlib.sha256(content).hexdigest() != metadata["sha256"]:
            raise ValueError("Static file digest mismatch")
        result["/" + name] = (content, _MIME[PurePosixPath(name).suffix])
    return result


def _owned_fd(path, flags):
    _plain_path(path.parent, directory=True)
    _plain_path(path, exists=False)
    fd = os.open(path, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise ValueError("Unsafe fixture trace file")
    return fd


def _append_trace(run_root, record):
    data = _canonical_json(record) + b"\n"
    fd = _owned_fd(run_root / "requests.jsonl", os.O_WRONLY | os.O_APPEND)
    try:
        if len(data) > MAX_BODY_BYTES or os.fstat(fd).st_size + len(data) > MAX_TRACE_BYTES:
            raise ValueError("Fixture trace bound exceeded")
        if os.write(fd, data) != len(data):
            raise OSError("Incomplete fixture trace write")
    finally:
        os.close(fd)


def _write_trace_failure(run_root, evidence):
    # Never include an exception string, submitted payload or path in this file.
    data = _canonical_json(evidence) + b"\n"
    fd = _owned_fd(run_root / "trace-failures.json", os.O_WRONLY)
    try:
        if os.write(fd, data) != len(data):
            raise OSError("Incomplete fixture trace status write")
        os.ftruncate(fd, len(data))
    finally:
        os.close(fd)


def _mark_trace_failure(run_root, evidence, reason):
    evidence.update(incomplete=True, trace_failures=min(1000, evidence["trace_failures"] + 1), reason=reason)
    try:
        _write_trace_failure(run_root, evidence)
    except Exception:
        pass  # In-memory incomplete flag remains authoritative for this app.


def _load_trace_evidence(run_root):
    evidence = {"incomplete": False, "trace_failures": 0, "reason": None}
    status_path = run_root / "trace-failures.json"
    if not status_path.exists():
        return evidence
    try:
        _plain_path(status_path)
        with status_path.open("rb") as source:
            data = source.read(4097)
        if len(data) > 4096:
            raise ValueError("Oversized fixture trace status")
        previous = json.loads(data)
        if (type(previous) is not dict or set(previous) != set(evidence)
                or previous["incomplete"] is not True or type(previous["trace_failures"]) is not int
                or not 1 <= previous["trace_failures"] <= 1000
                or previous["reason"] not in {"trace_unavailable", "creation_trace_incomplete", "prior_trace_status_invalid"}):
            raise ValueError("Invalid fixture trace status")
        return previous
    except Exception:
        _mark_trace_failure(run_root, evidence, "prior_trace_status_invalid")
        return evidence


def _record_trace(run_root, evidence, record):
    try:
        _append_trace(run_root, record)
    except Exception:
        _mark_trace_failure(run_root, evidence, "trace_unavailable")


class _StaticBundle:
    def __init__(self, assets):
        self.assets = assets

    async def __call__(self, scope, receive, send):
        from starlette.responses import Response
        asset = self.assets.get(scope["path"])
        response = Response(asset[0], media_type=asset[1]) if asset else Response(status_code=404)
        await response(scope, receive, send)


class _FixtureBoundary:
    def __init__(self, app, *, authority, generation, run_root, assets, evidence):
        self.app, self.authority, self.generation = app, authority, generation
        self.run_root, self.assets, self.evidence = run_root, assets, evidence

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return
        from starlette.responses import JSONResponse
        method, path = scope["method"], scope["path"]
        raw_path = scope.get("raw_path", path.encode("utf-8"))
        api_get = bool(_GET.fullmatch(path) or _UNRESOLVED.fullmatch(path) or _ACTION_STATUS.fullmatch(path))
        attack_turn = method == "POST" and bool(_ATTACK_TURN.fullmatch(path))
        abandon = method == "POST" and bool(_ABANDON.fullmatch(path))
        create = method == "POST" and bool(_CREATE.fullmatch(path))
        save_resume = method == "POST" and bool(_SAVE_RESUME.fullmatch(path))
        known = api_get or bool(_CREATE.fullmatch(path) or _SAVE_RESUME.fullmatch(path) or _ATTACK_TURN.fullmatch(path) or _ABANDON.fullmatch(path)) or path in self.assets
        record = {"method": method if method in {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT"} else "<other>",
                  "path": path if known else "<unlisted>", "status": 500}
        headers = {}
        for name, value in scope["headers"]:
            headers.setdefault(name.lower(), []).append(value)
        origin = ("http://" + self.authority).encode("ascii")
        supplied_origin = headers.get(b"origin", [])
        isolated = (scope.get("scheme") == "http"
                    and headers.get(b"host") == [self.authority.encode("ascii")]
                    and (supplied_origin == [origin] or (not supplied_origin and method != "POST"))
                    and headers.get(b"sec-fetch-site", []) in ([], [b"same-origin"], [b"none"]))
        captured = bytearray()
        request_body = b""
        status_started = False

        async def guarded_send(message):
            nonlocal status_started
            if message["type"] == "http.response.start":
                status_started = True
                record["status"] = message["status"]
                safe_headers = [(k, v) for k, v in message.get("headers", [])
                                if k.lower() not in {b"content-security-policy", b"cache-control"}]
                message = {**message, "headers": [*safe_headers,
                    (b"content-security-policy", CSP.encode("ascii")), (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff")]}
            elif message["type"] == "http.response.body" and (create or attack_turn) and record["status"] == 200:
                if len(captured) + len(message.get("body", b"")) <= MAX_STATIC_BYTES:
                    captured.extend(message.get("body", b""))
            await send(message)

        async def reject(status):
            await JSONResponse({"detail": "manual_fixture_request_rejected"}, status_code=status)(scope, receive, guarded_send)

        try:
            if not isolated:
                await reject(403)
                return
            allowed = ((method == "GET" and (api_get or path in self.assets)) or create or save_resume or attack_turn or abandon)
            if not allowed or b"%" in raw_path or b"\\" in raw_path:
                await reject(404)
                return
            if create or save_resume or attack_turn or abandon:
                chunks = bytearray()
                while True:
                    chunk = await receive()
                    if chunk["type"] != "http.request":
                        await reject(400)
                        return
                    chunks.extend(chunk.get("body", b""))
                    if len(chunks) > MAX_BODY_BYTES:
                        await reject(413)
                        return
                    if not chunk.get("more_body", False):
                        break
                request_body = bytes(chunks)
                if create or attack_turn:
                    content_types = headers.get(b"content-type", [])
                    if len(content_types) != 1 or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json":
                        await reject(415)
                        return
                    try:
                        submitted = json.loads(request_body)
                    except (ValueError, UnicodeError):
                        await reject(400)
                        return
                    if attack_turn:
                        seed = json.loads(_plain_path(self.run_root / "synthetic-seed.json").read_bytes())
                        target = seed["combat_target_id"]
                        allowed = {"message", "interaction_mode", "target_id", "action_id", "combat_action", "combat_id", "combat_round", "combat_turn_index"}
                        command = submitted.get("combat_action") if isinstance(submitted, dict) else None
                        steps = command.get("steps") if isinstance(command, dict) and set(command) == {"steps"} else None
                        step = steps[0] if isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict) else {}
                        labels = {"attack": "Saldırı Action kullanıyorum.", "continue_attack": "Aynı Attack Action içindeki saldırıya devam ediyorum."}
                        if (not isinstance(submitted, dict) or set(submitted) - allowed
                            or step.get("kind") not in labels
                            or set(step) - {"kind", "target_id", "reckless_attack"}
                            or step.get("target_id") != target
                            or ("reckless_attack" in step and type(step["reckless_attack"]) is not bool)
                            or submitted.get("message") != labels[step["kind"]]
                            or submitted.get("interaction_mode") not in (None, "do")
                            or submitted.get("target_id") not in (None, target)
                            or not re.fullmatch(_UUID, str(submitted.get("action_id", "")))
                            or not re.fullmatch(_UUID, str(submitted.get("combat_id", "")))
                            or type(submitted.get("combat_round")) is not int or submitted["combat_round"] < 1
                            or type(submitted.get("combat_turn_index")) is not int or submitted["combat_turn_index"] < 0):
                            await reject(400)
                            return
                elif request_body:
                    await reject(400)
                    return
            if path.startswith("/api/"):
                _check_runtime(self.run_root)
            received = False

            async def replay_receive():
                nonlocal received
                if (create or save_resume or attack_turn or abandon) and not received:
                    received = True
                    return {"type": "http.request", "body": request_body, "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, guarded_send)
            if attack_turn and record["status"] == 200:
                response = json.loads(captured)
                record.update(generation=self.generation, action_id=response["action_id"],
                              submitted_step=submitted["combat_action"]["steps"][0],
                              combat_result=response.get("combat_result"), combat=response["state"].get("combat"),
                              character={k: response["state"]["character"].get(k) for k in ("level", "progression_level", "xp", "current_hp", "max_hp")})
            if create and record["status"] == 200:
                try:
                    response = json.loads(captured)
                    campaign_id = response["campaign_id"]
                    if not re.fullmatch(_UUID, campaign_id):
                        raise ValueError("Invalid synthetic campaign identifier")
                    record.update(campaign_id=campaign_id, generation=self.generation)
                    character = submitted.get("character") if isinstance(submitted, dict) else None
                    if isinstance(character, dict):
                        record["character"] = {key: character[key] for key in
                            ("mode", "class", "starting_level", "spells", "level_choices") if key in character}
                except Exception:
                    _mark_trace_failure(self.run_root, self.evidence, "creation_trace_incomplete")
        except Exception:
            if status_started:
                raise
            await reject(500)
        finally:
            # A logging failure cannot change a committed mutation's response.
            _record_trace(self.run_root, self.evidence, record)


def _seed_reckless_attack(manager, store, run_root):
    """Canonical Barbarian package + accepted core2; no weapon/stat/roll overrides."""
    path = _plain_path(run_root / "synthetic-seed.json", exists=False)
    if path.exists():
        seed = json.loads(path.read_bytes())
        if type(seed) is not dict or not re.fullmatch(_UUID, seed.get("campaign_id", "")):
            raise ValueError("Invalid synthetic fixture seed identity")
        store.get_campaign(seed["campaign_id"])
        return seed
    from api.lore_authority import PRODUCTION_START_CATALOG
    import character_progression, bounded_encounter, action_economy, equipment_economy, weapon_attack
    setting = PRODUCTION_START_CATALOG.to_response()["settings"][0]
    region = setting["regions"][0]
    campaign_start = {"setting_id": setting["setting_id"], "region_pack_id": region["region_pack_id"],
                      "region_id": region["region_id"], "starting_location_id": region["starting_locations"][0]["entity_id"]}
    character = {
        "mode": "custom", "name": "C10 Synthetic Barbarian", "race": "Human", "species": "Human",
        "class": "Barbarian", "background": "Criminal", "alignment": "Neutral Good",
        "ability_score_method": "standard_array",
        "ability_scores": {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 10, "wisdom": 12, "charisma": 8},
        "background_ability_bonuses": {"dexterity": 2, "constitution": 1},
        "proficient_skills": ["Athletics", "Perception", "Persuasion", "Sleight of Hand", "Stealth"],
        "equipment_package": "A", "background_equipment_option": "A", "languages": ["Common", "Dwarvish", "Giant"],
        "cantrips": [], "spells": [], "starting_level": 1,
    }
    campaign_id, session_id, record, metadata = manager.create_campaign(
        name="Synthetic natural Reckless Attack acceptance", character=character, campaign_start=campaign_start)
    session = record.game_session
    core_spec = {key: value for key, value in character.items() if key not in {"mode", "class", "starting_level"}}
    core_spec["character_class"] = character["class"]
    character_progression.create_at_level(session, core_spec, 2, {"2": {}})
    if (session.character["level"], session.character["progression_level"], session.character["xp"]) != (2, 2, 300):
        raise ValueError("Accepted core Barbarian2 creation failed")
    equipment_economy.materialize(session.world_state)
    axes = [item for item in session.world_state["inventory"] if item.get("weapon_id") == "greataxe"]
    if len(axes) != 1 or session.world_state.get("equipment", {}).get("main_hand") != axes[0]["item_id"]:
        raise ValueError("Natural starting Greataxe is not equipped by a canonical owner; fixture must not substitute or override it")
    entered = bounded_encounter.resolve_command(session, bounded_encounter.ENTER)
    started = bounded_encounter.resolve_command(session, bounded_encounter.START)
    target_id = bounded_encounter.binding(session)["npc_id"]
    # A player-first initiative begins at authored60ft. Passing one real turn
    # lets the authored Commoner dash along its55ft route; do not invent geometry.
    setup_turn = None
    if weapon_attack.pair(session, "player", target_id)["distance_ft"] > 5:
        setup_turn = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]})
    if session.world_state["combat"]["current_actor_id"] != "player" or weapon_attack.pair(session, "player", target_id)["distance_ft"] != 5:
        raise ValueError("Natural authored encounter did not establish reachable player-turn target")
    projection = action_economy.projection(session)["actors"]["player"]["reckless_attack"]
    if projection != {"available": True, "active": False, "reason": None}:
        raise ValueError("Reckless decision is not naturally available before first player attack")
    manager.save_campaign(campaign_id)
    seed = {"synthetic": True, "principal": "test-issuer/test-player", "campaign_id": campaign_id,
            "campaign_start": campaign_start, "creation_owner": "SessionManager.create_campaign1 then character_progression.create_at_level2",
            "combat_owner": "bounded_encounter ENTER/START and natural action_economy end_turn if out of reach",
            "combat_target_id": target_id, "weapon_item_id": axes[0]["item_id"], "weapon_id": "greataxe",
            "post_encounter": {k: session.character.get(k) for k in ("level", "progression_level", "xp", "current_hp", "max_hp", "strength")},
            "reckless_projection": projection, "setup_passed_player_turn": setup_turn is not None,
            "combat_start_result": started["action_result"]}
    fd = _owned_fd(path, os.O_WRONLY | os.O_EXCL)
    try:
        data = _canonical_json(seed)
        if os.write(fd, data) != len(data): raise OSError("Incomplete synthetic seed record")
    finally:
        os.close(fd)
    return seed


def create_manual_fixture(run_root: Path, static_root: Path, *, authority: str,
                          generation: str, bundle_sha256: str, static_manifest: dict):
    """Build the real API with a synthetic store, verified static bytes and narrow gate.

    ``authority`` is the exact already-bound loopback host:port, not a hostname.
    Source-bundle verification and socket ownership belong to the future launcher.
    The marker and immutable bundle must live outside one another. Neither this
    function nor its module binds sockets, imports the old R02 server, installs
    packages, or patches engine turn methods.
    """
    if os.environ.get("AI_DND_DISABLE_DEFAULT_APP") != "1":
        raise RuntimeError("AI_DND_DISABLE_DEFAULT_APP=1 is required before importing api.main")
    if not isinstance(authority, str) or not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}", authority):
        raise ValueError("Explicit loopback authority required")
    port = int(authority.rsplit(":", 1)[1])
    if port > 65535 or port in {8008, 11434}:
        raise ValueError("Invalid or protected fixture port")
    try:
        parsed_generation = UUID(generation)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Canonical launch UUID required") from None
    if str(parsed_generation) != generation or parsed_generation.version != 4:
        raise ValueError("Canonical launch UUID4 required")
    if not isinstance(bundle_sha256, str) or not _HEX.fullmatch(bundle_sha256):
        raise ValueError("Bundle SHA256 required")
    _validate_manifest(static_manifest)
    _plain_path(run_root, directory=True)
    _plain_path(static_root, directory=True)
    if run_root == static_root or run_root in static_root.parents or static_root in run_root.parents:
        raise ValueError("Immutable static bundle and runtime must not overlap")
    _verify_marker(run_root, static_root, bundle_sha256, static_manifest)
    _check_runtime(run_root)
    for name in ("requests.jsonl", "trace-failures.json"):
        _plain_path(run_root / name, exists=False)
    assets = _static_bytes(static_root, static_manifest)
    evidence = _load_trace_evidence(run_root)

    # Lazy imports keep module import safe and default-app creation disabled.
    from api.auth import FixedAuthenticator, Principal
    from api.main import create_app
    from api.persistence.campaign_store import CampaignStore
    from api.session_manager import SessionManager

    test_player = Principal("test-issuer", "test-player")
    store = CampaignStore(run_root / "db" / "campaigns.sqlite3", bound_principal=test_player)
    manager = SessionManager(campaign_store=store)
    seed = _seed_reckless_attack(manager, store, run_root)
    application = create_app(session_manager=manager, ollama_adapter=None,
                             authenticator=FixedAuthenticator(test_player))
    application.router.routes[:] = [route for route in application.router.routes
                                   if getattr(route, "path", None) not in {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}]
    application.docs_url = application.redoc_url = application.openapi_url = None
    application.state.manual_fixture_evidence = evidence
    application.state.manual_fixture_seed = seed
    application.state.manual_fixture_generation = generation
    application.state.manual_fixture_authority = authority
    application.mount("/", _StaticBundle(assets), name="verified-c06-static")
    application.add_middleware(_FixtureBoundary, authority=authority, generation=generation,
                               run_root=run_root, assets=assets, evidence=evidence)
    return application
