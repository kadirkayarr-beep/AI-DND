"""Disposable browser fixture through real owners; never changes production odds.

Run from ai-dnd. Only this explicitly named campaign is created/seeded.
"""
import json
import random
from uuid import uuid4

from fastapi.testclient import TestClient
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
import local_adventure_catalog as catalog


def seed_for_walkthrough():
    for seed in range(10000):
        rng = random.Random(seed)
        if all(rng.randint(1, 20) >= n for n in (12, 15, 13, 13, 12)):
            return seed
    raise RuntimeError("No fixture seed found.")


def prepare(store=None, *, complete=False):
    manager = SessionManager(campaign_store=store or CampaignStore())
    with TestClient(create_app(session_manager=manager, ollama_adapter=None)) as client:
        setting = client.get("/api/campaign-start-options").json()["settings"][0]
        region = setting["regions"][0]
        response = client.post("/api/campaigns", json={
            "name": "Package 3 deterministic browser — disposable",
            "campaign_start": {"setting_id": setting["setting_id"], "region_pack_id": region["region_pack_id"],
                              "region_id": region["region_id"], "starting_location_id": region["starting_locations"][0]["entity_id"]},
        })
        response.raise_for_status()
        campaign = response.json()
        sid = campaign["session_id"]
        session = manager.get(sid).game_session
        session.rng.seed(12345)

        def call(message):
            r = client.post(f"/api/sessions/{sid}/turn", json={"message": message, "action_id": str(uuid4())})
            r.raise_for_status()
            return r.json()

        def travel(destination):
            call("/travel go " + destination)
            for _ in range(48):
                if session.world_state["journey"]["status"] == "ARRIVED":
                    return
                if any(e.get("decision_status") == "PENDING" for e in session.world_state.get("scheduled_events", [])):
                    call("/explore decision continue")
                else:
                    call("/travel continue")
            raise RuntimeError("Bounded journey did not arrive.")

        call("/explore begin")
        if complete:
            world = session.world_state
            world["campaign_time"]["start_second"] = 0
            world["campaign_time"]["elapsed_seconds"] = 8 * 3600
            world["travel_effort"] = {"day": 0, "walking_seconds": 8 * 3600, "checks": []}
            world["features"].append({
                "id": "package3_fixture_trail", "name": "Bilinen test ayak izleri",
                "description": "Açıkça adlandırılmış disposable test izi.",
                "location": world["location"], "trail_policy": {"confined": True, "dc": 10}})
            world["doors"].append({
                "id": "package3_fixture_lock", "name": "Standart test kilidi",
                "description": "Disposable standard-policy test kapısı.",
                "location": world["location"], "locked": True, "open": False, "broken": False,
                "lock_policy": {"quality": "good", "complexity": "simple"}})
            world["inventory"].extend(["Thieves' Tools"] + ["Rations (1 day)", "Water (1 gallon)"] * 3)
            world.setdefault("ground_items_by_location", {})[world["location"]] = ["Rations (1 day)", "Water (1 gallon)"]
            session.rng.seed(11)
            call("/explore look")
            return {"campaign_id": campaign["campaign_id"], "session_id": sid,
                    "name": "Package 3 deterministic browser — disposable",
                    "fixture_seed": 11, "location": world["location"],
                    "phase": "extended_travel_tracking_tools_supplies",
                    "production_odds_changed": False}
        travel(catalog.CAMP)
        for _ in range(16):
            travel(catalog.ENTRY)
            if session.world_state["location"] == catalog.ENTRY:
                break
            travel(catalog.CAMP)
        if session.world_state["location"] != catalog.ENTRY:
            raise RuntimeError("Authored navigation did not reach the dungeon.")
        seed = seed_for_walkthrough()
        session.rng.seed(seed)
        call("/explore look")  # Existing atomic save owner persists this fixture's RNG.
        return {"campaign_id": campaign["campaign_id"], "session_id": sid,
                "name": "Package 3 deterministic browser — disposable",
                "fixture_seed": seed, "location": session.world_state["location"],
                "hp": session.character["current_hp"], "production_odds_changed": False}


if __name__ == "__main__":
    import sys
    print(json.dumps(prepare(complete="--complete" in sys.argv), ensure_ascii=False))
