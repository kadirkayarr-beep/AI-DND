"""Immutable project-authored possibilities, never Forgotten Realms lore/history.

Do not change a published catalog in place: add a new catalog ID/version.
Campaigns bind its stable IDs only after the player's explicit choice.
"""
import copy
import math

CATALOG_ID = "stone_trail_local_v1"
SOURCE = "PROJECT_AUTHORED_CAMPAIGN_CONTENT"
KEY = "local_adventure_v1"
CAMP, FORK = "stone_trail_camp", "stone_trail_fork"
ENTRY, HALL, VAULT = "stone_trail_entry", "stone_trail_hall", "stone_trail_vault"
ROOM_IDS = frozenset({ENTRY, HALL, VAULT})

LOCATIONS = {
    CAMP: {"name": "Patika Kampı", "type": "wilderness", "description": "Taş patikanın başında küçük bir dinlenme alanı.", "weather": "clear"},
    FORK: {"name": "Sisli Yol Ayrımı", "type": "wilderness", "description": "Kampa dönen tek patikanın bulunduğu sisli bir yol ayrımı.", "weather": "fog", "visibility": "lightly_obscured"},
    ENTRY: {"name": "Taş Eşik", "type": "dungeon", "description": "Açık avlunun ardında meşe kapılı eski bir giriş.", "weather": "clear"},
    HALL: {"name": "Sessiz Salon", "type": "dungeon", "description": "Mahzen kapısının önünde moloz; yanında taş bir kaldıraç.", "weather": "clear"},
    VAULT: {"name": "Eski Mahzen", "type": "dungeon", "description": "Duvarında yerel maceraya ait bir yol işareti bulunan küçük mahzen.", "weather": "clear"},
}
DOORS = {
    "stone_oak_door": {"name": "Meşe Kapı", "location": ENTRY, "description": "Salon geçidindeki meşe kapı.", "locked": True},
    "stone_vault_door": {"name": "Mahzen Kapısı", "location": HALL, "description": "Molozun ardındaki kapı.", "locked": False},
    "stone_secret_door": {"name": "Gizli Taş Kapı", "location": ENTRY, "description": "Taşların arasına gizlenmiş geçit.", "locked": True},
}
LOCKS = {
    identity: {"unlock_dc": 15, "break_dc": 15, "attempt_seconds": 60, "handle_seconds": 6}
    for identity in DOORS
}
EXITS = {
    "entry_hall": {"from": ENTRY, "to": HALL, "seconds": 30, "door_id": "stone_oak_door", "trap_id": "stone_wire"},
    "hall_entry": {"from": HALL, "to": ENTRY, "seconds": 30, "door_id": "stone_oak_door"},
    "hall_vault": {"from": HALL, "to": VAULT, "seconds": 30, "door_id": "stone_vault_door", "hazard_id": "stone_rubble"},
    "vault_hall": {"from": VAULT, "to": HALL, "seconds": 30, "door_id": "stone_vault_door"},
    "entry_secret": {"from": ENTRY, "to": VAULT, "seconds": 30, "door_id": "stone_secret_door", "discovery_id": "stone_secret"},
    "vault_secret": {"from": VAULT, "to": ENTRY, "seconds": 30, "door_id": "stone_secret_door", "discovery_id": "stone_secret"},
}
DISCOVERIES = {
    "stone_secret": {"location": ENTRY, "name": "Gizli Geçit", "text": "Taş duvarın çizgileri gizli bir kapının kenarlarını ortaya çıkarıyor."},
    "stone_wire": {"location": ENTRY, "name": "Gerili Tel", "text": "Salon eşiğinde bir tuzağa bağlı ince tel fark ettin."},
    "stone_marker": {"location": VAULT, "name": "Yol İşareti", "text": "Duvar işareti bu mahzenin girişe uzanan gizli geçidini gösteriyor."},
}
TRAPS = {
    "stone_wire": {"location": ENTRY, "name": "Gerili Tel", "dc": 15, "damage": 2, "damage_type": "piercing", "rearming": False},
}
HAZARDS = {
    "stone_rubble": {"location": HALL, "name": "Gevşek Moloz", "dc": 15, "damage": 2, "damage_type": "bludgeoning"},
}
INTERACTIONS = {
    "stone_lever": {"location": HALL, "name": "Taş Kaldıraç", "hazard_id": "stone_rubble"},
}
SCOUTING = {"dc": 15, "seconds": 60}


def route(identity, origin, destination, miles, *, navigation=False, lost=()):
    # Daily distances use eight hours of actual travel, without granting a rest.
    return {
        "id": identity, "origin": origin, "destination": destination,
        "distance_miles": miles, "duration_seconds": math.ceil(miles * 1200),
        "stage_distances_miles": [miles / 2, miles / 2],
        "navigation_dc": 15 if navigation else None, "lost_destinations": list(lost),
    }


def locations(origin):
    result = {
        identity: {
            "id": identity, **copy.deepcopy(data), "environment": data["type"],
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "authored_catalog_id": CATALOG_ID, "search_duration_seconds": 360,
            "search_dc": 15,
        }
        for identity, data in LOCATIONS.items()
    }
    result[CAMP]["travel_routes"] = {
        ENTRY: route("stone_camp_ruins", CAMP, ENTRY, 6, navigation=True, lost=(FORK,)),
        FORK: route("stone_camp_fork", CAMP, FORK, 6),
        origin: route("stone_camp_home", CAMP, origin, 6),
    }
    result[FORK]["travel_routes"] = {CAMP: route("stone_fork_camp", FORK, CAMP, 6)}
    # A reverse road is authored independently, not inferred from its outbound leg.
    result[ENTRY]["travel_routes"] = {CAMP: route("stone_ruins_camp", ENTRY, CAMP, 6)}
    return result


def approach(origin):
    return route("stone_home_camp", origin, CAMP, 6)


def initial_state(origin):
    return {
        "catalog_id": CATALOG_ID, "origin": origin, "discoveries": [],
        "trap_states": {identity: "hidden" for identity in TRAPS},
        "hazard_states": {identity: "active" for identity in HAZARDS},
        "interactions": [],
    }
