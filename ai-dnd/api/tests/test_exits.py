"""One owner for the way out (Dilim 3, Task 4): a building keeps its door, a town opens one side street the first
time someone has to run, a room's outside is the street, and a place with no way out says what is left to do.

The worlds are the journey scenarios' own setups (09a inn, 09b locked cellar, 09c Neverwinter street), built through
the journey harness on the real app; no model call is answered except the scripted ones."""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import combat_lifecycle
import exits
import local_places
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems
from api.tests.journeys.schema import _load_step, load_scenario
from api.tests.test_house_door import stub_feature, stub_npc
from api.tests.town_seed import fixed_town
from incidents import sublocations

CITY = "fr:city:neverwinter"
SIDE = "fr:city:neverwinter:side_street"
SUCCESS = {"result": "BAŞARILI", "roll": 20, "total": 25, "dc": 12}
# A new campaign seeds its town (and opens its places) from its id: pinned, so every run sees the same town.
TOWN_SEED = 3901


class ExitsTests(JourneyCase):
    async def scene(self, name, *, fight=False, extra=()):
        """The scenario's setup through the harness, its attack step played when ``fight``; the live session."""
        scenario = load_scenario(SCENARIO_DIR / f"{name}.json")
        steps = (scenario.steps[:1] if fight else ()) + tuple(
            _load_step(raw, f"{name}, ek adım", False) for raw in extra)
        with fixed_town(self, TOWN_SEED):
            results = await self.run_scenario(dataclasses.replace(scenario, steps=steps))
        self.assertEqual(describe_problems(results), [])
        session = self.manager.get(self.last_session_id).game_session
        if fight:
            self.assertIs(session.world_state["combat"]["active"], True)
            self.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
        return session

    async def inn_world(self):
        return (await self.scene("09a_escape_exit")).world_state

    async def city_world(self):
        world = (await self.scene("09c_escape_start_scene")).world_state
        self.assertEqual(world["location"], CITY)
        return world

    async def house_with_inner_room_world(self):
        world = await self.city_world()
        estate = local_places.create_local_place(world, CITY, "estate")
        local_places.furnish(world, estate, create_npc=stub_npc(world), create_feature=stub_feature(world))
        hall = local_places.inner_room_of(world, estate["id"])
        self.assertIsNotNone(hall)
        self.estate_id, self.hall_id = estate["id"], hall["id"]
        return world

    async def sublocation_world(self):
        world = await self.city_world()
        record = {"incident_id": "incident_test", "location_id": CITY, "lifecycle": "RESOLVED",
                  "details": {"subscene": {"kind": "shed", "label": "Eski Kulübe",
                                           "description": "Tahtaları çürümüş küçük bir kulübe."}}}
        sublocations.promote(world, record)
        return world

    def flee(self, session, roll=SUCCESS):
        with patch.object(session, "perform_skill_check", create=True, return_value=dict(roll)):
            return combat_lifecycle.flee(session)

    async def test_a_building_keeps_todays_way_out(self):
        world = await self.inn_world()
        self.assertEqual(exits.way_out(world, world["location"]), CITY)
        self.assertEqual(exits.way_out(world, world["location"], open_if_needed=True), CITY)
        self.assertNotIn(SIDE, world["locations"])

    async def test_today_both_fields_agree_everywhere_they_are_written(self):
        # V2: grounded_action read parent-first, flee exit-first; one order is safe only if no writer splits them
        worlds = (await self.inn_world(), await self.house_with_inner_room_world(), await self.sublocation_world())
        checked = 0
        for world in worlds:
            for place in world["locations"].values():
                if place.get("exit_location_id") and place.get("parent_location_id"):
                    self.assertEqual(place["exit_location_id"], place["parent_location_id"], place["id"])
                    checked += 1
        self.assertGreaterEqual(checked, 4)

    async def test_the_city_street_gets_a_side_street(self):
        world = await self.city_world()
        self.assertIsNone(exits.way_out(world, CITY))  # reading alone opens nothing
        side = exits.way_out(world, CITY, open_if_needed=True)
        self.assertEqual(side, SIDE)
        self.assertEqual(world["locations"][side], {
            "id": SIDE, "name": "Neverwinter Ara Sokağı", "type": "street", "scene_kind": "city",
            "parent_location_id": CITY, "exit_location_id": CITY, "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "tags": ["campaign_local", "side_street"],
            "description": "Ana caddenin gerisinde, iki duvar arasında dar bir sokak."})
        self.assertNotIn("place_kind", world["locations"][side])
        self.assertEqual(exits.way_out(world, side), CITY)
        self.assertEqual(exits.way_out(world, CITY), SIDE)  # once written, reading finds it

    async def test_the_side_street_opens_once_and_survives_reload(self):
        world = await self.city_world()
        first = exits.side_street(world, CITY)
        count = len(world["locations"])
        self.assertIs(exits.side_street(world, CITY), first)
        self.assertEqual(len(world["locations"]), count)
        reloaded = json.loads(json.dumps(world))
        again = exits.side_street(reloaded, CITY)
        self.assertEqual(first, again)
        self.assertEqual(len(reloaded["locations"]), count)
        self.assertEqual(sum(1 for k in world["locations"] if k.endswith(":side_street")), 1)

    async def test_reading_never_writes(self):
        world = await self.city_world()
        before = json.dumps(world, sort_keys=True)
        self.assertEqual(exits.way_out_name(world, CITY), "Neverwinter Ara Sokağı")
        self.assertIsNone(exits.way_out(world, CITY))
        self.assertIsNone(exits.outside(world, CITY))
        self.assertNotIn(SIDE, world["locations"])
        self.assertEqual(json.dumps(world, sort_keys=True), before)

    async def test_a_full_campaign_still_gets_its_side_street(self):
        world = await self.city_world()
        number = 900
        while len(world["locations"]) < 80:
            world["locations"][f"location_{number}"] = {"id": f"location_{number}", "name": f"Yer {number}",
                                                        "parent_location_id": CITY, "exit_location_id": CITY}
            number += 1
        # The town may already hold some kinds (its own work opens them); a kind it lacks would be a new place.
        kind = next((kind for kind, spec in local_places.PLACE_KINDS.items()
                     if not spec.get("outdoors") and local_places.find_local_place(world, CITY, kind) is None), None)
        self.assertIsNotNone(kind)
        self.assertIsNone(local_places.create_local_place(world, CITY, kind))  # the cap is real
        self.assertEqual(exits.way_out(world, CITY, open_if_needed=True), SIDE)
        self.assertIn(SIDE, world["locations"])

    async def test_outside_from_an_inner_room_is_the_street(self):
        world = await self.house_with_inner_room_world()
        self.assertEqual(exits.outside(world, self.hall_id), CITY)
        self.assertEqual(exits.way_out(world, self.hall_id), self.estate_id)   # flight still goes one door at a time
        self.assertEqual(exits.outside(world, self.estate_id), CITY)
        self.assertIsNone(exits.outside(world, CITY))

    async def test_a_self_or_unknown_way_out_is_none(self):
        world = await self.inn_world()
        here = world["locations"][world["location"]]
        for value in (world["location"], "nowhere"):
            with self.subTest(value=value):
                here.update(exit_location_id=value, parent_location_id=value)
                self.assertIsNone(exits.way_out(world, world["location"], open_if_needed=True))
                self.assertIsNone(exits.way_out_name(world, world["location"]))

    async def test_no_exit_says_why_and_what_is_left(self):
        session = await self.scene("09b_escape_no_exit", fight=True)
        round_before = session.world_state["combat"]["round"]
        count = len(session.world_state["locations"])
        result = self.flee(session)
        self.assertIn("Buradan çıkış yok; dövüşmeye devam edebilirsin.", result["narration"])
        self.assertNotIn("teslim", result["narration"])
        self.assertEqual(result["action_result"]["reason_code"], "no_exit")
        self.assertIsNotNone(self.setup_place_id)   # the locked cellar the setup stood the player in, by its live id
        self.assertEqual(session.world_state["location"], self.setup_place_id)
        self.assertIs(session.world_state["combat"]["active"], True)
        self.assertGreater(session.world_state["combat"]["round"], round_before)
        self.assertEqual(len(session.world_state["locations"]), count)
        self.assertIn("olmadı: Buradan çıkış yok; dövüşmeye devam edebilirsin.",
                      [text for _, text in session._turn_notes])

    async def test_no_exit_offers_surrender_only_when_held(self):
        session = await self.scene("09b_escape_no_exit", fight=True)
        world = session.world_state
        world["npcs"].append({"id": "guard", "name": "Muhafız", "role": "Guard", "location": world["location"],
                              "current_hp": 11, "max_hp": 11})
        world["flags"].setdefault("deeds", []).append(
            {"at": 0, "kind": "murder", "hold": {"guard": "guard", "arrest": True}})
        result = self.flee(session)
        self.assertIn("Buradan çıkış yok; dövüşmeye devam edebilir ya da teslim olabilirsin.", result["narration"])
        self.assertEqual(result["action_result"]["reason_code"], "no_exit")

    async def test_old_save_without_a_side_street_loads_and_flees(self):
        await self.scene("09c_escape_start_scene", fight=True)
        campaign_id = self.manager.get(self.last_session_id).campaign_id
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        session_id, *_ = fresh.resume_campaign(campaign_id)
        session = fresh.get(session_id).game_session
        self.assertNotIn(SIDE, session.world_state["locations"])  # a 4572bfe3-shaped save: no side street
        result = self.flee(session)
        self.assertIs(result["action_result"]["success"], True)
        self.assertEqual(session.world_state["location"], SIDE)
        self.assertIs(session.world_state["combat"]["active"], False)

    async def test_undo_of_a_flight_takes_the_new_side_street_back(self):
        session = await self.scene("09c_escape_start_scene", fight=True, extra=(
            {"say": "kaçıyorum", "expect": {"savas": False, "konum": SIDE}},
            {"undo": True, "expect": {"savas": True, "konum": CITY}}))
        self.assertNotIn(SIDE, session.world_state["locations"])


class OnlyExitsReadsTests(unittest.TestCase):
    def test_only_exits_reads_the_exit_fields(self):
        root = Path(__file__).resolve().parents[2]
        readers = []
        for path in root.glob("*.py"):
            if path.name.startswith("test_") or path.name == "exits.py":
                continue
            text = path.read_text(encoding="utf-8")
            for needle in ('get("exit_location_id") or', 'get("parent_location_id") or',
                           '("exit_location_id", "parent_location_id")'):
                if needle in text:
                    readers.append(f"{path.name}: {needle}")
        self.assertEqual(readers, [])


if __name__ == "__main__":
    unittest.main()
