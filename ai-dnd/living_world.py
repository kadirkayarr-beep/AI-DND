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
import uuid
from typing import Any, Callable

from ambient_event_catalog import select_ambient_event


SCENE_SCHEMA_VERSION = 1
MAX_SCENES = 80
MAX_REFERENTS_PER_SCENE = 6
MAX_REFERENTS_TOTAL = 240
MAX_SCENE_STATE_BYTES = 96 * 1024
MAX_BEAT_TEXT = 240
MAX_AMBIENT_EVENT_HISTORY = 32


def _legacy_ambient_event_instance_id(
    campaign_seed: str,
    location_id: str,
    event_id: str,
    count: int,
    turn_index: int,
) -> str:
    identity = json.dumps(
        [campaign_seed, location_id, event_id, count, turn_index],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai-dnd:ambient-event:{identity}"))

_LOCAL_NAMES = (
    "Aldren", "Brynna", "Cael", "Darian", "Elaris", "Fenra", "Garrick",
    "Ilyra", "Kael", "Liora", "Marek", "Neris", "Orin", "Sylva", "Thalen",
    "Veyra",
)

_LOOK_RE = re.compile(
    r"(?:etraf[ıi]m[ae]?\s*bak\w*|çevrem[ae]?\s*bak\w*|etrafa\s+bak(?:ıyor\w*|ıyorum)|bakınıyorum|"
    r"etraf[ıi]?m?da\s+ne(?:ler)?\s+var|çevre(?:m|de)?(?:de)?\s+ne(?:ler)?\s+var|"
    r"etrafta\s+ne(?:ler)?\s+var|çevrede\s+ne(?:ler)?\s+var|"
    r"etrafa\s+göz\s+at\w*|etrafıma\s+göz\s+at\w*|çevreyi\s+gözle\w*|çevreye\s+göz\s+at\w*|çevreme\s+göz\s+at\w*|"
    r"etraf[ıi]m.{0,30}gözlemle\w*|çevre(?:yi|m).{0,30}gözlemle\w*|"
    r"şehirde\s+dolan\w*.{0,50}(?:bak|gözlemle)\w*|"
    r"look around|look about|take a look|walk around.{0,50}observe)",
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
    r"yakınına git|yakınına gid|yakınına yaklaş|"
    r"approach|walk up to|go over to)",
    re.IGNORECASE,
)
_ENTER_RE = re.compile(
    r"(?:içeri gir|içeriye gir|içine gir|hana gir|tavernaya gir|taverna.{0,12}gir|meyhaneye gir|"
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
_VENUE_RE = re.compile(
    r"(?:taverna|tavern|inn|meyhane|\bhan\b|hanı|hana|"
    r"içecek|içki|drink|ale|"
    r"oturacak.{0,20}yer|dinlenecek.{0,20}yer|"
    r"bir şeyler iç|bir seyler ic)",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"(?:ar(?:a|ı|i)\w*|bul\w*|karşılaş\w*|tanış\w*|find|look for|search for|"
    r"meet|locate|nearby|yakın(?:da|larda|ımda)?|buralarda|civar(?:da|larda)?|"
    r"var\s*m[ıi]|bulunur\s*m[ıi]|bulunuyor\s*m[ıi]|görür\s*m[üu]y[üu]m)",
    re.IGNORECASE,
)
_ROUTE_DISTANCE_QUERY_RE = re.compile(
    r"\b(?:distance|route|road|path|way|miles?|mile|kilometers?|kilometres?|"
    r"meters?|metres?|km|mil|mesafe\w*|uzak\w*|guzergah\w*|rota\w*|yol\w*)\b|"
    r"\b(?:kac|ne kadar)\s+(?:mil|mile|km|kilometre\w*|kilometer\w*|"
    r"kilometre\w*|meter\w*|metre\w*)\b|"
    r"\b(?:ne kadar uzak|how far)\b",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"(?:\b(?:istemiyorum|istemeyelim|bulma|arama|aramıyorum|aramayalım|"
    r"kurma|açma|oluşturma|"
    r"ekleme)\b|don't|do not|never|no need)",
    re.IGNORECASE,
)


def _is_route_distance_query(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and _ROUTE_DISTANCE_QUERY_RE.search(normalize_text(value))
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
        "campaign_seed": "",
        "ambient_context": {
            "environment": "unknown",
            "time_of_day": "day",
            "weather": "clear",
            "background": "",
            "origin": "",
        },
        "ambient_event_history": [],
        "ambient_event_counts": {},
    }


def normalize_text(value: Any) -> str:
    """Normalize Turkish spelling for matching without changing model input."""
    if not isinstance(value, str):
        return ""
    text = value.casefold().replace("İ", "i").replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def npc_name_known_to_player(npc: Any) -> bool:
    """Legacy NPCs remain known; newly-created NPCs opt into hidden-name state."""
    return bool(
        isinstance(npc, dict)
        and npc.get("name_known_to_player", True) is True
    )


def npc_role_known_to_player(npc: Any) -> bool:
    """Legacy saves stay compatible while new NPCs can hide non-obvious roles."""
    return bool(
        isinstance(npc, dict)
        and npc.get("role_known_to_player", True) is True
    )


def role_is_visibly_obvious(role: Any) -> bool:
    """Conservative V1 allow-list for roles readable from nearby visible context."""
    normalized = normalize_text(role)
    return normalized in {
        "barmen", "bartender", "hanci", "innkeeper", "muhafiz", "guard",
        "asker", "soldier", "tuccar", "merchant", "demirci", "blacksmith",
        "garson", "server", "tezgahtar", "shopkeeper",
    }


def public_npc_role(npc: Any) -> str | None:
    if not isinstance(npc, dict) or not npc_role_known_to_player(npc):
        return None
    role = str(npc.get("role") or "").strip()
    return role or None


def public_npc_descriptor(npc: Any) -> str:
    """Describe an unknown NPC from visible cues without exposing canonical identity."""
    if not isinstance(npc, dict):
        return "Yakındaki kişi"
    role = public_npc_role(npc)
    if role:
        lowered = role[:1].lower() + role[1:] if role else "kişi"
        return f"Bir {lowered}"
    appearance = " ".join(str(npc.get("appearance") or "").split()).strip()
    if appearance:
        first = re.split(r"[.!?;]", appearance, maxsplit=1)[0].strip(" ,")
        if first:
            if len(first) > 72:
                first = first[:69].rstrip() + "…"
            return first if normalize_text(first).endswith("kisi") else f"{first} kişi"
    return "Yakındaki kişi"


def public_npc_name(npc: Any) -> str:
    """Return a player-safe display label without mutating canonical NPC identity."""
    if not isinstance(npc, dict):
        return "Yakındaki kişi"
    if npc_name_known_to_player(npc):
        name = str(npc.get("name") or "").strip()
        if name:
            return name
    return public_npc_descriptor(npc)


def public_npc_projection(npc: Any) -> dict[str, Any] | None:
    """Copy one NPC into a player-safe identity projection."""
    if not isinstance(npc, dict):
        return None
    projected = copy.deepcopy(npc)
    projected["name"] = public_npc_name(npc)
    projected["role"] = public_npc_role(npc) or ""
    projected["name_known_to_player"] = npc_name_known_to_player(npc)
    projected["role_known_to_player"] = npc_role_known_to_player(npc)
    return projected



def public_shop_name(world_state: Any, shop: Any) -> str:
    """Hide a shop name only when it directly embeds an unknown keeper identity."""
    if not isinstance(shop, dict):
        return "Yerel dükkân"
    name = str(shop.get("name") or "").strip()
    keeper_id = shop.get("shopkeeper_id")
    keeper = None
    if isinstance(world_state, dict):
        keeper = next((
            npc for npc in world_state.get("npcs", [])
            if isinstance(npc, dict) and npc.get("id") == keeper_id
        ), None)
    if keeper is not None and not npc_name_known_to_player(keeper):
        keeper_name = normalize_text(keeper.get("name"))
        if keeper_name and keeper_name in normalize_text(name):
            lowered = normalize_text(name)
            return "Yerel tezgâh" if "tezgah" in lowered else "Yerel dükkân"
    return name or "Yerel dükkân"


def public_shop_projection(world_state: Any, shop: Any) -> dict[str, Any] | None:
    if not isinstance(shop, dict):
        return None
    projected = copy.deepcopy(shop)
    projected["name"] = public_shop_name(world_state, shop)
    return projected


def classify_scene_action(value: Any) -> str | None:
    """Recognize a small set of high-confidence, harmless scene actions."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if _PRESENCE_RE.search(text):
        return "presence"
    normalized = normalize_text(text)
    semantic_look = bool(
        re.search(
            r"\b(?:etrafim|cevreyi|cevrede|sehirde|kentte|sokaklarda)\b"
            r".{0,90}\b(?:gozlemle\w*|dolan\w*|kesfet\w*|cevreye bak\w*|"
            r"etrafa bak\w*|etrafi kola(can|caan)\w*)\b",
            normalized,
        )
    )
    if _LOOK_RE.search(text) or semantic_look:
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
    if (
        not isinstance(value, str)
        or _NEGATIVE_RE.search(value)
        or _is_route_distance_query(value)
    ):
        return False
    explicit_tavern = bool(
        _TAVERN_RE.search(value)
        and _SEARCH_RE.search(value)
        and not _ENTER_RE.search(value)
    )
    return explicit_tavern or is_local_venue_search(value)


def is_local_venue_search(value: Any) -> bool:
    """Recognize searches by purpose as well as by the word "tavern"."""
    if (
        not isinstance(value, str)
        or _NEGATIVE_RE.search(value)
        or _is_route_distance_query(value)
    ):
        return False
    if _ENTER_RE.search(value):
        return False
    has_search_intent = bool(
        _SEARCH_RE.search(value)
        or re.search(
            r"\b(?:var\s*m[ıi]|bulunur\s*m[ıi]|nerede\s*bulabilirim|"
            r"nereye\s+gidebilirim|bana\s+bir\b)",
            value,
            re.IGNORECASE,
        )
    )
    has_venue_purpose = bool(_VENUE_RE.search(value))
    nearby_context = bool(
        re.search(
            r"\b(?:yakın\w*|buralarda|burada|civar\w*|yakınımda|"
            r"nearby|around here|close by)\b",
            value,
            re.IGNORECASE,
        )
    )
    return has_venue_purpose and (has_search_intent or nearby_context)


def is_merchant_search(value: Any) -> bool:
    if not isinstance(value, str) or _NEGATIVE_RE.search(value):
        return False
    normalized = normalize_text(value)
    merchant_terms = (
        "tuccar", "tacir", "satici", "esnaf", "merchant", "trader", "vendor"
    )

    def one_edit_apart(left: str, right: str) -> bool:
        if abs(len(left) - len(right)) > 1:
            return False
        i = j = edits = 0
        while i < len(left) and j < len(right):
            if left[i] == right[j]:
                i += 1
                j += 1
                continue
            edits += 1
            if edits > 1:
                return False
            if len(left) > len(right):
                i += 1
            elif len(right) > len(left):
                j += 1
            else:
                i += 1
                j += 1
        if i < len(left) or j < len(right):
            edits += 1
        return edits <= 1

    merchant_mention = _MERCHANT_RE.search(value) is not None
    if not merchant_mention:
        tokens = normalized.split()
        merchant_mention = any(
            token.startswith(term)
            or (
                len(token) >= 4
                and one_edit_apart(token, term)
            )
            for token in tokens
            for term in merchant_terms
        )
    discovery_intent = bool(
        _SEARCH_RE.search(value)
        or re.search(
            r"\b(?:var\s*m[ıi]|bulunur\s*m[ıi]|nerede\s*bulabilirim|"
            r"bana\s+bir\b|kim\s+var)\b",
            value,
            re.IGNORECASE,
        )
    )
    nearby = bool(
        re.search(
            r"\b(?:yakın\w*|buralarda|burada|civar\w*|yakınımda|"
            r"nearby|around here|close by)\b",
            value,
            re.IGNORECASE,
        )
    )
    return merchant_mention and (discovery_intent or nearby)


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
    state.setdefault("campaign_seed", "")
    state.setdefault(
        "ambient_context",
        {
            "environment": "unknown",
            "time_of_day": "day",
            "weather": "clear",
            "background": "",
            "origin": "",
        },
    )
    state.setdefault("ambient_event_history", [])
    state.setdefault("ambient_event_counts", {})
    if (
        not isinstance(state.get("campaign_seed"), str)
        or len(state["campaign_seed"]) > 64
        or not isinstance(state.get("ambient_context"), dict)
        or not isinstance(state.get("ambient_event_history"), list)
        or len(state["ambient_event_history"]) > MAX_AMBIENT_EVENT_HISTORY
        or not isinstance(state.get("ambient_event_counts"), dict)
        or len(state["ambient_event_counts"]) > 80
    ):
        raise ValueError("Campaign ambient-event state is invalid.")
    for event_id, count in state["ambient_event_counts"].items():
        if (
            not isinstance(event_id, str)
            or len(event_id) > 96
            or type(count) is not int
            or count < 1
        ):
            raise ValueError("Campaign ambient-event counts are invalid.")
    ambient_context = state["ambient_context"]
    if (
        set(ambient_context) != {
            "environment", "time_of_day", "weather", "background", "origin"
        }
        or any(
            not isinstance(ambient_context.get(key), str)
            for key in (
                "environment", "time_of_day", "weather", "background", "origin"
            )
        )
        or len(ambient_context["background"]) > 96
        or len(ambient_context["origin"]) > 240
    ):
        raise ValueError("Campaign ambient context is invalid.")
    for item in state["ambient_event_history"]:
        if (
            isinstance(item, dict)
            and not item.get("instance_id")
            and isinstance(item.get("event_id"), str)
            and isinstance(item.get("location_id"), str)
            and type(item.get("turn_index")) is int
            and type(item.get("count")) is int
        ):
            item["instance_id"] = _legacy_ambient_event_instance_id(
                state["campaign_seed"],
                item["location_id"],
                item["event_id"],
                item["count"],
                item["turn_index"],
            )
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("event_id"), str)
            or not isinstance(item.get("instance_id"), str)
            or len(item["instance_id"]) > 96
            or not isinstance(item.get("variation_id"), str)
            or not isinstance(item.get("repeat_group"), str)
            or not isinstance(item.get("location_id"), str)
            or type(item.get("turn_index")) is not int
            or type(item.get("last_seen_turn")) is not int
            or type(item.get("count")) is not int
            or item.get("last_seen_turn") != item.get("turn_index")
        ):
            raise ValueError("Campaign ambient-event history is invalid.")
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
        ambient_event = scene.get("ambient_event")
        if isinstance(ambient_event, dict):
            if (
                not ambient_event.get("instance_id")
                and isinstance(ambient_event.get("event_id"), str)
                and type(ambient_event.get("count")) is int
                and ambient_event["count"] > 0
            ):
                history_match = next(
                    (
                        item for item in reversed(state["ambient_event_history"])
                        if item.get("event_id") == ambient_event["event_id"]
                        and item.get("location_id") == location_id
                        and item.get("count") == ambient_event["count"]
                    ),
                    None,
                )
                ambient_event["instance_id"] = (
                    history_match["instance_id"]
                    if history_match is not None
                    else _legacy_ambient_event_instance_id(
                        state["campaign_seed"],
                        location_id,
                        ambient_event["event_id"],
                        ambient_event["count"],
                        0,
                    )
                )
            if (
                ambient_event.get("event_type") == "BLUE"
                and isinstance(ambient_event.get("instance_id"), str)
            ):
                event_instance_id = ambient_event["instance_id"]
                referent = next(
                    (
                        item for item in scene["referents"]
                        if item.get("event_instance_id") == event_instance_id
                    ),
                    None,
                )
                if referent is None:
                    history_match = next(
                        (
                            item for item in reversed(state["ambient_event_history"])
                            if item.get("instance_id") == event_instance_id
                            and item.get("location_id") == location_id
                        ),
                        None,
                    )
                    source_turn = (
                        history_match.get("turn_index")
                        if history_match is not None
                        else None
                    )
                    referent = next(
                        (
                            item for item in scene["referents"]
                            if item.get("event_instance_id") is None
                            and (
                                source_turn is None
                                or item.get("source_turn") == source_turn
                            )
                        ),
                        None,
                    )
                    if referent is not None:
                        referent["event_instance_id"] = event_instance_id
                if referent is not None:
                    ambient_event.setdefault("referent_id", referent.get("id"))
        for referent in scene["referents"]:
            if (
                not isinstance(referent, dict)
                or not isinstance(referent.get("id"), str)
                or not isinstance(referent.get("description"), str)
                or not isinstance(referent.get("aliases"), list)
                or len(referent["aliases"]) > 8
                or referent.get("lifecycle")
                not in ("presented", "promoted", "expired")
                or (
                    referent.get("event_instance_id") is not None
                    and (
                        not isinstance(referent.get("event_instance_id"), str)
                        or len(referent["event_instance_id"]) > 96
                    )
                )
            ):
                raise ValueError("Campaign scene referent is invalid.")
        opening = scene.get("opening")
        if opening is not None and (
            not isinstance(opening, dict)
            or not isinstance(opening.get("text"), str)
            or len(opening["text"]) > 1800
            or not isinstance(opening.get("tone"), str)
            or not isinstance(opening.get("event_id"), str)
            or not isinstance(opening.get("variation_id"), str)
        ):
            raise ValueError("Campaign scene opening is invalid.")
        ambient_event = scene.get("ambient_event")
        if ambient_event is not None and (
            not isinstance(ambient_event, dict)
            or not isinstance(ambient_event.get("event_id"), str)
            or not isinstance(ambient_event.get("instance_id"), str)
            or len(ambient_event["instance_id"]) > 96
            or not isinstance(ambient_event.get("variation_id"), str)
            or ambient_event.get("event_type") not in ("GREEN", "BLUE")
            or not isinstance(ambient_event.get("repeat_group"), str)
            or type(ambient_event.get("count")) is not int
            or ambient_event["count"] < 1
            or (
                ambient_event.get("event_type") == "BLUE"
                and (
                    not isinstance(ambient_event.get("referent_id"), str)
                    or not any(
                        item.get("id") == ambient_event["referent_id"]
                        and item.get("event_instance_id")
                        == ambient_event["instance_id"]
                        for item in scene["referents"]
                        if isinstance(item, dict)
                    )
                )
            )
        ):
            raise ValueError("Campaign scene event is invalid.")
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


def set_ambient_context(
    world_state: dict[str, Any],
    world_metadata: dict[str, Any] | None,
    character: dict[str, Any] | None,
    campaign_id: str,
) -> dict[str, Any]:
    """Persist bounded selector context without promoting it to world canon."""
    state = ensure_scene_state(world_state)
    metadata = world_metadata if isinstance(world_metadata, dict) else {}
    player = character if isinstance(character, dict) else {}
    environments = {
        "tavern", "forest", "city", "village", "road", "wilderness",
        "dungeon", "cave", "castle", "temple", "ruins", "unknown",
    }
    times = {"dawn", "day", "evening", "night"}
    weather = {"clear", "rain", "fog", "snow", "storm", "unknown"}
    environment = metadata.get("environment")
    time_of_day = metadata.get("time_of_day")
    conditions = metadata.get("weather")
    state["ambient_context"] = {
        "environment": (
            environment
            if isinstance(environment, str) and environment in environments
            else "unknown"
        ),
        "time_of_day": (
            time_of_day
            if isinstance(time_of_day, str) and time_of_day in times
            else "day"
        ),
        "weather": (
            conditions
            if isinstance(conditions, str) and conditions in weather
            else "unknown"
        ),
        "background": str(player.get("background") or "")[:96],
        "origin": str(player.get("origin") or "")[:240],
    }
    state["campaign_seed"] = hashlib.sha256(
        campaign_id.encode("utf-8")
    ).hexdigest()[:24]
    return state["ambient_context"]


def select_and_record_ambient_event(
    world_state: dict[str, Any],
    location_id: str,
    turn_index: int,
    *,
    allowed_types: set[str] | None = None,
) -> dict[str, Any] | None:
    """Select and persist one scene event using campaign-local repetition data."""
    state = ensure_scene_state(world_state)
    history = state["ambient_event_history"]
    context = copy.deepcopy(state["ambient_context"])
    context["npc_density"] = sum(
        1
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == location_id
    )
    selected = select_ambient_event(
        scene_kind=scene_kind(world_state, location_id),
        location_id=location_id,
        turn_index=max(0, turn_index),
        context=context,
        history=history,
        campaign_seed=state["campaign_seed"],
        allowed_types=allowed_types,
    )
    if selected is None:
        return None
    event_id = selected["event_id"]
    count = state["ambient_event_counts"].get(event_id, 0) + 1
    state["ambient_event_counts"][event_id] = count
    record = {
        "event_id": event_id,
        "instance_id": str(uuid.uuid4()),
        "variation_id": selected["variation_id"],
        "repeat_group": selected["repeat_group"],
        "location_id": location_id[:128],
        "turn_index": max(0, turn_index),
        "last_seen_turn": max(0, turn_index),
        "count": count,
    }
    history.append(record)
    state["ambient_event_history"] = history[-MAX_AMBIENT_EVENT_HISTORY:]
    selected["count"] = count
    selected["instance_id"] = record["instance_id"]
    return selected


def set_scene_opening(
    world_state: dict[str, Any],
    location_id: str,
    text: str,
    tone: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Store the authored opening with its scene so save/resume cannot reroll it."""
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > 1800
        or not isinstance(tone, str)
        or not isinstance(event.get("event_id"), str)
        or not isinstance(event.get("variation_id"), str)
    ):
        raise ValueError("Campaign opening data is invalid.")
    scene = ensure_scene_record(world_state, location_id, 0)
    scene["opening"] = {
        "text": text.strip(),
        "tone": tone[:32],
        "event_id": event["event_id"][:96],
        "variation_id": event["variation_id"][:32],
    }
    return scene["opening"]


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
    event_instance_id: str | None = None,
) -> dict[str, Any]:
    scene = ensure_scene_record(world_state, location_id, turn_index)
    for existing in scene["referents"]:
        if existing.get("lifecycle") in ("presented", "promoted"):
            if event_instance_id and not existing.get("event_instance_id"):
                existing["event_instance_id"] = event_instance_id
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
        "event_instance_id": event_instance_id,
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
    event = select_and_record_ambient_event(
        world_state,
        location_id,
        turn_index,
    )
    if event is not None:
        ambient_event = {
            "event_id": event["event_id"],
            "instance_id": event["instance_id"],
            "variation_id": event["variation_id"],
            "event_type": event["event_type"],
            "repeat_group": event["repeat_group"],
            "count": event["count"],
        }
        scene["last_beat"] = event["text"][:MAX_BEAT_TEXT]
        if event["event_type"] == "BLUE":
            referent = create_scene_referent(
                world_state,
                location_id,
                turn_index,
                description=event["text"],
                aliases=list(event["aliases"]),
                event_instance_id=event["instance_id"],
            )
            ambient_event["referent_id"] = referent["id"]
        scene["ambient_event"] = ambient_event

    scene["materialized"] = True
    scene["last_activity_turn"] = max(0, turn_index)
    return scene


def expire_referents(
    world_state: dict[str, Any],
    turn_index: int,
    *,
    location_id: str | None = None,
    referent_ids: set[str] | None = None,
) -> None:
    state = ensure_scene_state(world_state)
    if location_id is None:
        scenes = state["scenes"].values()
    else:
        scene = state["scenes"].get(location_id)
        scenes = (scene,) if isinstance(scene, dict) else ()
    for scene in scenes:
        for referent in scene.get("referents", []):
            if (
                (referent_ids is None or referent.get("id") in referent_ids)
                and referent.get("lifecycle") == "presented"
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
    if candidates:
        candidate_ids = {
            ref["id"] for ref in candidates if isinstance(ref.get("id"), str)
        }
        if candidate_ids:
            expire_referents(
                world_state,
                turn_index,
                location_id=location_id,
                referent_ids=candidate_ids,
            )
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
    npcs = [
        {
            "id": npc.get("id"),
            "name": public_npc_name(npc),
            "role": public_npc_role(npc) or "",
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
    def addressable_alias(ref: dict[str, Any]) -> str | None:
        aliases = ref.get("aliases")
        if not isinstance(aliases, list):
            return None
        return next(
            (
                alias.strip()[:80]
                for alias in aliases
                if isinstance(alias, str) and alias.strip()
            ),
            None,
        )

    referents = [
        {
            "id": ref.get("id"),
            "event_instance_id": ref.get("event_instance_id"),
            "kind": ref.get("kind"),
            "description": ref.get("description"),
            "source_turn": ref.get("source_turn"),
            "lifecycle": ref.get("lifecycle"),
            "promoted_npc_id": ref.get("promoted_npc_id"),
            "addressable_alias": addressable_alias(ref),
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
        "ambient_event": (
            {
                "event_id": scene["ambient_event"].get("event_id"),
                "instance_id": scene["ambient_event"].get("instance_id"),
                "variation_id": scene["ambient_event"].get("variation_id"),
                "event_type": scene["ambient_event"].get("event_type"),
                "repeat_group": scene["ambient_event"].get("repeat_group"),
                "count": scene["ambient_event"].get("count"),
            }
            if isinstance(scene.get("ambient_event"), dict)
            else None
        ),
        "opening": (
            scene.get("opening", {}).get("text")
            if isinstance(scene.get("opening"), dict)
            else None
        ),
        "player_position": copy.deepcopy(
            position if isinstance(position, dict) and position.get("location_id") == location_id
            else {"location_id": location_id, "kind": "standing", "target_id": None}
        ),
        "npcs": npcs[:12],
        "features": features[:24],
        "referents": referents[:MAX_REFERENTS_PER_SCENE],
    }
