"""Bounded, persistent campaign-local scene state.

This module owns only local scene continuity.  It does not read lore packs,
resolve mechanics, or derive facts from narration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from typing import Any, Callable


SCENE_SCHEMA_VERSION = 1
MAX_SCENES = 80
MAX_REFERENTS_PER_SCENE = 6
MAX_REFERENTS_TOTAL = 240
MAX_SCENE_STATE_BYTES = 96 * 1024
MAX_BEAT_TEXT = 240

_LOCAL_NAMES = (
    "Aylin", "Baran", "Duru", "Ece", "Emre", "Narin", "Sema", "Tuna",
    "Yasemin", "Arda", "Melis", "Bora", "Elif", "Deniz", "Rana", "Onur",
)

_LOOK_RE = re.compile(
    r"(?:etraf(?:ı|i)m[ae]? bak|çevrem[ae]? bak|bakınıyorum|"
    r"etrafa göz at|çevreyi gözle|look around|look about|take a look)",
    re.IGNORECASE,
)
_PRESENCE_RE = re.compile(
    r"(?:kim(?:ler)? var|kimler burada|burada kim|etrafta kim|"
    r"who(?:'s| is) here|who is around|anyone here)",
    re.IGNORECASE,
)
_WAIT_RE = re.compile(
    r"(?:biraz bekle|kısa süre bekle|bekliyorum|bekleyeyim|"
    r"bir süre oyalan|wait a (?:bit|while)|wait briefly)",
    re.IGNORECASE,
)
_EXIT_RE = re.compile(
    r"(?:dışarı çık|dışarıya çık|buradan çık|han(?:dan|dan|dan|dan)? çık|"
    r"tavernadan çık|meyhaneden çık|leave (?:here|the tavern|the inn)|exit)",
    re.IGNORECASE,
)
_SIT_RE = re.compile(
    r"(?:otur(?:uyorum|ayım|alım|mak)?|masaya geç|yerime otur|"
    r"sit(?:ting)? down|take a seat)",
    re.IGNORECASE,
)
_STAND_RE = re.compile(
    r"(?:ayağa kalk|kalkıyorum|yerimden kalk|stand up|get up)",
    re.IGNORECASE,
)
_APPROACH_RE = re.compile(
    r"(?:yaklaş(?:ıyorum|ayım|alım|mak)?|yanına git|yanına yaklaşı|"
    r"approach|walk up to|go over to)",
    re.IGNORECASE,
)
_ENTER_RE = re.compile(
    r"(?:içeri gir|içeriye gir|hana gir|tavernaya gir|taverna.{0,12}gir|meyhaneye gir|"
    r"enter|go inside|head inside)",
    re.IGNORECASE,
)
_TAVERN_RE = re.compile(
    r"(?:taverna|tavern|inn|meyhane|\bhan\b|hanı|hana)",
    re.IGNORECASE,
)
_MERCHANT_RE = re.compile(
    r"(?:tüccar|tacir|satıcı|esnaf|merchant|trader|vendor)", re.IGNORECASE
)
_SEARCH_RE = re.compile(
    r"(?:ara\w*|bul\w*|karşılaş\w*|tanış\w*|find|look for|search for|"
    r"meet|locate|nearby|yakın(?:da|larda|ımda)?)",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"(?:\b(?:istemiyorum|istemeyelim|bulma|arama|kurma|açma|oluşturma|"
    r"ekleme)\b|don't|do not|never|no need)",
    re.IGNORECASE,
)


def initial_scene_state() -> dict[str, Any]:
    return {
        "schema_version": SCENE_SCHEMA_VERSION,
        "next_referent_number": 1,
        "next_feature_number": 1,
        "scenes": {},
        "active_referent_id": None,
        "player_position": {"location_id": None, "kind": "standing", "target_id": None},
        "proposal_references": [],
    }


def normalize_text(value: Any) -> str:
    """Normalize Turkish spelling for matching without changing model input."""
    if not isinstance(value, str):
        return ""
    text = value.casefold().replace("İ", "i").replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def classify_scene_action(value: Any) -> str | None:
    """Recognize a small set of high-confidence, harmless scene actions."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if _PRESENCE_RE.search(text):
        return "presence"
    if _LOOK_RE.search(text):
        return "look"
    if _WAIT_RE.search(text):
        return "wait"
    if _EXIT_RE.search(text):
        return "exit"
    if _SIT_RE.search(text):
        return "sit"
    if _STAND_RE.search(text):
        return "stand"
    if _APPROACH_RE.search(text):
        return "approach"
    if _ENTER_RE.search(text):
        return "enter"
    return None


def is_tavern_search(value: Any) -> bool:
    if not isinstance(value, str) or _NEGATIVE_RE.search(value):
        return False
    return bool(
        _TAVERN_RE.search(value)
        and _SEARCH_RE.search(value)
        and not _ENTER_RE.search(value)
    )


def is_merchant_search(value: Any) -> bool:
    if not isinstance(value, str) or _NEGATIVE_RE.search(value):
        return False
    return bool(_MERCHANT_RE.search(value) and _SEARCH_RE.search(value))


def ensure_scene_state(world_state: dict[str, Any]) -> dict[str, Any]:
    """Install and validate bounded scene state; migrate legacy feature IDs."""
    state = world_state.get("scene_state")
    if state is None:
        state = initial_scene_state()
        world_state["scene_state"] = state
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCENE_SCHEMA_VERSION
        or not isinstance(state.get("scenes"), dict)
        or len(state["scenes"]) > MAX_SCENES
    ):
        raise ValueError("Campaign scene state is invalid.")
    for key in ("next_referent_number", "next_feature_number"):
        if type(state.get(key)) is not int or state[key] < 1:
            raise ValueError("Campaign scene counters are invalid.")
    if not isinstance(state.get("proposal_references"), list):
        raise ValueError("Campaign scene references are invalid.")
    if len(state["proposal_references"]) > 24:
        raise ValueError("Campaign scene references exceed the limit.")
    features = world_state.setdefault("features", [])
    if not isinstance(features, list) or len(features) > 1280:
        raise ValueError("Campaign feature list exceeds the limit.")
    used_ids: set[str] = set()
    max_number = 0
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError("Campaign feature data is invalid.")
        feature_id = feature.get("id")
        if not isinstance(feature_id, str) or not feature_id:
            fingerprint = json.dumps(
                [
                    feature.get("location"),
                    feature.get("name"),
                    feature.get("description"),
                    index,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            feature_id = "feature_legacy_" + hashlib.sha256(
                fingerprint.encode("utf-8")
            ).hexdigest()[:16]
            feature["id"] = feature_id
        if feature_id in used_ids:
            raise ValueError("Campaign feature IDs are duplicated.")
        used_ids.add(feature_id)
        match = re.fullmatch(r"feature_(\d+)", feature_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    state["next_feature_number"] = max(state["next_feature_number"], max_number + 1)
    referent_total = 0
    for location_id, scene in state["scenes"].items():
        if (
            not isinstance(location_id, str)
            or not isinstance(scene, dict)
            or scene.get("location_id") != location_id
            or not isinstance(scene.get("id"), str)
            or not isinstance(scene.get("referents"), list)
            or len(scene["referents"]) > MAX_REFERENTS_PER_SCENE
        ):
            raise ValueError("Campaign scene record is invalid.")
        referent_total += len(scene["referents"])
        for referent in scene["referents"]:
            if (
                not isinstance(referent, dict)
                or not isinstance(referent.get("id"), str)
                or not isinstance(referent.get("description"), str)
                or not isinstance(referent.get("aliases"), list)
                or len(referent["aliases"]) > 8
                or referent.get("lifecycle")
                not in ("presented", "promoted", "expired")
            ):
                raise ValueError("Campaign scene referent is invalid.")
    if referent_total > MAX_REFERENTS_TOTAL:
        raise ValueError("Campaign scene referents exceed the limit.")
    try:
        serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ValueError("Campaign scene state is invalid.") from None
    if len(serialized.encode("utf-8")) > MAX_SCENE_STATE_BYTES:
        raise ValueError("Campaign scene state exceeds the limit.")
    return state


def location_anchor_id(world_state: dict[str, Any], location_id: Any) -> str | None:
    """Resolve a local place to its nearest canonical/parent anchor."""
    if not isinstance(location_id, str):
        return None
    locations = world_state.get("locations", {})
    seen: set[str] = set()
    current = location_id
    while current not in seen:
        seen.add(current)
        record = locations.get(current) if isinstance(locations, dict) else None
        if not isinstance(record, dict):
            return current
        for key in ("lore_entity_id", "canonical_entity_id"):
            value = record.get(key)
            if isinstance(value, str) and value:
                return value
        parent = record.get("parent_location_id")
        if not isinstance(parent, str) or not parent:
            return current
        current = parent
    return None


def scene_kind(world_state: dict[str, Any], location_id: str) -> str:
    record = world_state.get("locations", {}).get(location_id, {})
    if not isinstance(record, dict):
        return "quiet"
    declared = record.get("scene_kind")
    if declared in ("tavern", "city", "wilderness", "building"):
        return declared
    location_type = str(record.get("type", "")).casefold()
    if location_type in ("wilderness", "forest", "mountain", "landmark"):
        return "wilderness"
    if location_type in ("city", "town", "village", "settlement", "şehir", "kasaba", "köy"):
        return "city"
    if _TAVERN_RE.search(str(record.get("name", ""))):
        return "tavern"
    if location_type in ("building", "bina"):
        return "building"
    return "quiet"


def ensure_scene_record(
    world_state: dict[str, Any],
    location_id: str,
    turn_index: int,
) -> dict[str, Any]:
    state = ensure_scene_state(world_state)
    scene = state["scenes"].get(location_id)
    if scene is None:
        location = world_state.get("locations", {}).get(location_id, {})
        parent = location.get("parent_location_id") if isinstance(location, dict) else None
        scene = {
            "id": f"scene:{location_id}",
            "location_id": location_id,
            "parent_location_id": parent,
            "kind": scene_kind(world_state, location_id),
            "materialized": False,
            "visit_revision": 0,
            "activity_revision": 0,
            "first_seen_turn": max(0, turn_index),
            "last_visit_turn": None,
            "last_activity_turn": None,
            "last_beat": None,
            "referents": [],
        }
        state["scenes"][location_id] = scene
    return scene


def record_scene_visit(
    world_state: dict[str, Any],
    location_id: str,
    turn_index: int,
) -> dict[str, Any]:
    scene = ensure_scene_record(world_state, location_id, turn_index)
    if scene.get("last_visit_turn") != turn_index:
        scene["visit_revision"] = int(scene.get("visit_revision", 0)) + 1
        scene["last_visit_turn"] = max(0, turn_index)
    scene["parent_location_id"] = (
        world_state.get("locations", {}).get(location_id, {}).get("parent_location_id")
    )
    state = ensure_scene_state(world_state)
    position = state.get("player_position", {})
    if not isinstance(position, dict) or position.get("location_id") != location_id:
        state["player_position"] = {
            "location_id": location_id,
            "kind": "standing",
            "target_id": None,
        }
    return scene


def _stable_name(world_state: dict[str, Any], location_id: str, role: str) -> str:
    digest = hashlib.sha256(
        f"{location_id}\x00{role}\x00{world_state.get('next_npc_number', 1)}".encode()
    ).digest()
    start = int.from_bytes(digest[:4], "big") % len(_LOCAL_NAMES)
    used = {
        str(npc.get("name", "")).casefold()
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
    }
    for offset in range(len(_LOCAL_NAMES)):
        name = _LOCAL_NAMES[(start + offset) % len(_LOCAL_NAMES)]
        if name.casefold() not in used:
            return name
    suffix = 1 + len(used)
    return f"{_LOCAL_NAMES[start]} {suffix}"


def stable_local_name(world_state: dict[str, Any], location_id: str, role: str) -> str:
    return _stable_name(world_state, location_id, role)


def create_scene_referent(
    world_state: dict[str, Any],
    location_id: str,
    turn_index: int,
    *,
    description: str,
    aliases: list[str],
    kind: str = "person",
) -> dict[str, Any]:
    scene = ensure_scene_record(world_state, location_id, turn_index)
    for existing in scene["referents"]:
        if existing.get("lifecycle") in ("presented", "promoted"):
            return existing
    state = ensure_scene_state(world_state)
    number = max(1, state["next_referent_number"])
    ref_id = f"scene_ref_{number:04d}"
    state["next_referent_number"] = number + 1
    referent = {
        "id": ref_id,
        "scene_id": scene["id"],
        "location_id": location_id,
        "kind": kind,
        "description": str(description)[:240],
        "aliases": [str(alias)[:80] for alias in aliases[:8] if isinstance(alias, str)],
        "source_turn": max(0, turn_index),
        "expires_after_turn": max(0, turn_index) + 12,
        "lifecycle": "presented",
        "promoted_npc_id": None,
    }
    scene["referents"].append(referent)
    scene["referents"] = scene["referents"][-MAX_REFERENTS_PER_SCENE:]
    return referent


def materialize_scene(
    world_state: dict[str, Any],
    location_id: str,
    turn_index: int,
    *,
    create_npc: Callable[[dict[str, Any]], dict[str, Any] | None],
    create_feature: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Create one small location-appropriate scene once, reusing saved actors."""
    scene = ensure_scene_record(world_state, location_id, turn_index)
    if scene.get("materialized"):
        expire_referents(world_state, turn_index)
        return scene

    kind = scene.get("kind")
    if kind == "city":
        for role, appearance, personality in (
            ("Kent sakini", "Yol kenarında duran, sade bir pelerin giymiş.", "Sakin ve dikkatli."),
            ("Muhafız", "Kapı yakınında nöbet tutan, düzenli giyimli.", "Ölçülü ve nazik."),
        ):
            create_npc({
                "name": _stable_name(world_state, location_id, role),
                "role": role,
                "location": location_id,
                "appearance": appearance,
                "personality": personality,
                "relationship": "neutral",
            })
        create_scene_referent(
            world_state,
            location_id,
            turn_index,
            description="Sokağın kıyısında bir yolcu, çantasının gevşeyen kayışını düzeltiyor.",
            aliases=["yolcu", "çantasıyla uğraşan kişi", "sokak kenarındaki kişi"],
        )
    elif kind == "tavern":
        create_npc({
            "name": _stable_name(world_state, location_id, "Barmen"),
            "role": "Barmen",
            "location": location_id,
            "appearance": "Tezgâhın arkasında, işini sakin bir dikkatle sürdürüyor.",
            "personality": "Sıcakkanlı, konuşmadan önce dinliyor.",
            "relationship": "neutral",
        })
        create_feature({
            "location": location_id,
            "name": "Ahşap masa",
            "description": "Kenarında sıradan bir kil bardak duran sağlam bir masa.",
            "kind": "furnishing",
            "aliases": ["masa", "ahşap masa", "bardak", "kil bardak"],
        })
        create_scene_referent(
            world_state,
            location_id,
            turn_index,
            description="Girişe yakın bir ziyaretçi, omzundaki çanta kayışını düzeltiyor.",
            aliases=["ziyaretçi", "kapıdaki kişi", "girişteki yolcu", "kapıdaki adam"],
        )
    elif kind == "wilderness":
        scene["last_beat"] = "Çevre sessiz; yalnızca doğal sesler duyuluyor."

    scene["materialized"] = True
    scene["last_activity_turn"] = max(0, turn_index)
    expire_referents(world_state, turn_index)
    return scene


def expire_referents(world_state: dict[str, Any], turn_index: int) -> None:
    state = ensure_scene_state(world_state)
    for scene in state["scenes"].values():
        for referent in scene.get("referents", []):
            if (
                referent.get("lifecycle") == "presented"
                and type(referent.get("expires_after_turn")) is int
                and turn_index > referent["expires_after_turn"]
            ):
                referent["lifecycle"] = "expired"
    active = state.get("active_referent_id")
    if active and not any(
        ref.get("id") == active and ref.get("lifecycle") in ("presented", "promoted")
        for scene in state["scenes"].values()
        for ref in scene.get("referents", [])
    ):
        state["active_referent_id"] = None


def _alias_in_text(alias: Any, text: Any) -> bool:
    normalized_alias = normalize_text(alias)
    normalized_text = normalize_text(text)
    if not normalized_alias or not normalized_text:
        return False
    if re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", normalized_text):
        return True
    if " " not in normalized_alias:
        return any(
            token.startswith(normalized_alias) and len(token) <= len(normalized_alias) + 8
            for token in normalized_text.split()
        )
    return False


def resolve_scene_referent(
    world_state: dict[str, Any],
    player_input: str,
    turn_index: int,
) -> dict[str, Any]:
    """Resolve only a handle presented in this scene; never mine old prose."""
    state = ensure_scene_state(world_state)
    location_id = world_state.get("location")
    scene = state["scenes"].get(location_id)
    if not isinstance(scene, dict):
        return {"status": "missing", "referent": None}
    expire_referents(world_state, turn_index)
    candidates = [
        ref
        for ref in scene.get("referents", [])
        if ref.get("lifecycle") in ("presented", "promoted", "expired")
        and any(_alias_in_text(alias, player_input) for alias in ref.get("aliases", []))
    ]
    if not candidates and re.search(
        r"\b(?:ona|onu|onunla|aynı kişi|that person|them|him|her)\b",
        normalize_text(player_input),
    ):
        active_id = state.get("active_referent_id")
        candidates = [
            ref for ref in scene.get("referents", [])
            if ref.get("id") == active_id
        ]
    unique = {ref["id"]: ref for ref in candidates}
    if len(unique) > 1:
        return {"status": "ambiguous", "referent": None}
    if not unique:
        return {"status": "missing", "referent": None}
    referent = next(iter(unique.values()))
    if referent.get("lifecycle") == "expired":
        return {"status": "expired", "referent": referent}
    state["active_referent_id"] = referent["id"]
    referent["expires_after_turn"] = max(
        int(referent.get("expires_after_turn", turn_index)),
        turn_index + 6,
    )
    return {
        "status": "promoted" if referent.get("lifecycle") == "promoted" else "found",
        "referent": referent,
    }


def promote_referent(
    world_state: dict[str, Any],
    referent: dict[str, Any],
    npc_id: str,
) -> None:
    if referent.get("lifecycle") == "promoted":
        if referent.get("promoted_npc_id") != npc_id:
            raise ValueError("Scene referent promotion is inconsistent.")
        return
    if referent.get("lifecycle") != "presented":
        raise ValueError("Only a presented scene referent can be promoted.")
    referent["lifecycle"] = "promoted"
    referent["promoted_npc_id"] = npc_id
    ensure_scene_state(world_state)["active_referent_id"] = referent["id"]


def note_wait(world_state: dict[str, Any], location_id: str, turn_index: int) -> str:
    scene = ensure_scene_record(world_state, location_id, turn_index)
    scene["activity_revision"] = int(scene.get("activity_revision", 0)) + 1
    scene["last_activity_turn"] = max(0, turn_index)
    if scene.get("kind") == "tavern":
        beat = "Kısa bir sessizlikten sonra sohbetler alçak sesle yeniden sürüyor."
    elif scene.get("kind") == "city":
        beat = "Yakından geçenlerin ayak sesleri seyrelip yeniden çoğalıyor."
    elif scene.get("kind") == "wilderness":
        beat = "Rüzgârın sesi bir süre yükselip sonra hafifliyor."
    else:
        beat = "Ortamda küçük bir hareketlilik oluyor; belirgin bir şey değişmiyor."
    scene["last_beat"] = beat[:MAX_BEAT_TEXT]
    state = ensure_scene_state(world_state)
    state["player_position"] = {
        "location_id": location_id,
        "kind": "standing",
        "target_id": None,
    }
    return scene["last_beat"]


def set_player_position(
    world_state: dict[str, Any],
    location_id: str,
    kind: str,
    target_id: str | None = None,
) -> None:
    if kind not in ("standing", "seated"):
        raise ValueError("Invalid local player position.")
    ensure_scene_state(world_state)["player_position"] = {
        "location_id": location_id,
        "kind": kind,
        "target_id": target_id if kind == "seated" else None,
    }


def add_proposal_references(
    world_state: dict[str, Any],
    turn_index: int,
    references: list[dict[str, Any]],
) -> None:
    state = ensure_scene_state(world_state)
    clean = []
    for reference in references[:8]:
        if (
            isinstance(reference, dict)
            and isinstance(reference.get("key"), str)
            and isinstance(reference.get("entity_id"), str)
            and isinstance(reference.get("kind"), str)
        ):
            clean.append({
                "key": reference["key"][:16],
                "entity_id": reference["entity_id"][:128],
                "kind": reference["kind"][:24],
                "location_id": str(reference.get("location_id", ""))[:128],
                "source_turn": max(0, turn_index),
            })
    state["proposal_references"] = (
        state["proposal_references"] + clean
    )[-24:]


def public_scene_projection(
    world_state: dict[str, Any],
    turn_index: int,
) -> dict[str, Any] | None:
    location_id = world_state.get("location")
    state = ensure_scene_state(world_state)
    scene = state["scenes"].get(location_id)
    if not isinstance(scene, dict):
        return None
    expire_referents(world_state, turn_index)
    npcs = [
        {
            "id": npc.get("id"),
            "name": npc.get("name"),
            "role": npc.get("role"),
            "appearance": npc.get("appearance", ""),
        }
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == location_id
    ]
    features = [
        {
            "id": feature.get("id"),
            "name": feature.get("name"),
            "description": feature.get("description", ""),
        }
        for feature in world_state.get("features", [])
        if isinstance(feature, dict) and feature.get("location") == location_id
    ]
    referents = [
        {
            "id": ref.get("id"),
            "kind": ref.get("kind"),
            "description": ref.get("description"),
            "source_turn": ref.get("source_turn"),
            "lifecycle": ref.get("lifecycle"),
            "promoted_npc_id": ref.get("promoted_npc_id"),
        }
        for ref in scene.get("referents", [])
        if ref.get("lifecycle") in ("presented", "promoted")
    ]
    position = state.get("player_position", {})
    return {
        "id": scene.get("id"),
        "location_id": location_id,
        "parent_location_id": scene.get("parent_location_id"),
        "kind": scene.get("kind"),
        "visit_revision": scene.get("visit_revision", 0),
        "activity_revision": scene.get("activity_revision", 0),
        "last_activity": scene.get("last_beat"),
        "player_position": copy.deepcopy(
            position if isinstance(position, dict) and position.get("location_id") == location_id
            else {"location_id": location_id, "kind": "standing", "target_id": None}
        ),
        "npcs": npcs[:12],
        "features": features[:24],
        "referents": referents[:MAX_REFERENTS_PER_SCENE],
    }