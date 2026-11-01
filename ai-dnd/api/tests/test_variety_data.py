"""New campaigns draw their people, places, first lines and role knowledge from the catalog; old saves keep theirs."""
import copy
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import game
import grounded_action
import living_world
import local_places
import name_catalog
from api.tests import test_campaign_api as api
from api.tests.test_natural_addressing import TownClient

CITY = "fr:city:neverwinter"
START = {"campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": CITY,
}}


def marked_world(seed, **extra):
    return {"scene_state": {"campaign_seed": seed, "name_pool": name_catalog.VERSION}, "npcs": [],
            "next_npc_number": 1, "locations": {}, **extra}


class PeopleTests(unittest.TestCase):
    def test_a_marked_campaign_draws_people_from_the_catalog_only(self):
        people = set(name_catalog.people())
        self.assertGreaterEqual(len(people), 250)
        names = {living_world.stable_local_name(marked_world(f"tohum{n}"), "han", "Barmen") for n in range(60)}
        self.assertLessEqual(names, people)
        self.assertGreater(len(names), 30)

    def test_a_save_without_the_mark_keeps_its_old_pool(self):
        old = {"scene_state": {"campaign_seed": "tohum1"}, "npcs": [], "next_npc_number": 1}
        before = copy.deepcopy(old)
        self.assertIn(living_world.stable_local_name(old, "han", "Barmen"), living_world._LOCAL_NAMES)
        self.assertEqual(old, before)

    def test_no_seed_stays_the_legacy_name_even_with_the_mark(self):
        world = {"scene_state": {"campaign_seed": "", "name_pool": name_catalog.VERSION}, "npcs": [], "next_npc_number": 1}
        self.assertEqual(living_world.stable_local_name(world, "tavern", "Barmen"), "Elaris")

    def test_a_name_is_not_handed_out_twice(self):
        world = marked_world("tohum2")
        for _ in range(40):
            world["npcs"].append({"name": living_world.stable_local_name(world, "han", "Barmen")})
        self.assertEqual(len({npc["name"] for npc in world["npcs"]}), 40)

    def test_no_person_name_reads_as_an_attack(self):
        for name in name_catalog.people():
            self.assertEqual(game._attack_verb_tokens(game._normalize_turkish_typos(name)), [], name)

    def test_no_person_name_is_the_start_of_another(self):
        folded = [living_world.normalize_text(name) for name in name_catalog.people()]
        self.assertEqual(len(set(folded)), len(folded))
        self.assertEqual([(a, b) for a in folded for b in folded if a != b and b.startswith(a)], [])


class PlaceTests(unittest.TestCase):
    def test_a_name_comes_from_the_kind_table_and_never_reads_as_another_place(self):
        table = name_catalog.place_templates()
        self.assertTrue({"tavern", "smithy", "market", "workshop", "library", "dukkan"} <= set(table))
        for kind in table:
            names = {name_catalog.place_name(marked_world(f"tohum{n}"), kind, "kent") for n in range(40)}
            self.assertNotIn(None, names)
            self.assertGreater(len(names), 8, kind)
            for name in names:
                self.assertNotIn("{", name)
                self.assertNotRegex(living_world.normalize_text(name), r"\bkapi")
                visited = local_places.is_local_place_visit(f"{name} yerine gidiyorum")
                self.assertIn(visited, {None, kind}, name)

    def test_two_trades_of_one_town_do_not_share_a_word(self):
        shared = 0
        for seed in range(30):
            world = marked_world(f"tohum{seed}")
            words = [set(name_catalog.place_name(world, kind, "kent").split()[:1]) for kind in ("smithy", "workshop")]
            shared += bool(words[0] & words[1])
        self.assertLess(shared, 6)

    def test_a_place_is_reached_by_its_name_with_no_trade_word_and_by_two_of_its_words(self):
        world = marked_world("tohum8", locations={
            "kent": {"id": "kent", "scene_kind": "city", "type": "city"},
            "a": {"id": "a", "name": "Kızıl Örs Ocağı", "place_kind": "smithy", "parent_location_id": "kent"},
            "b": {"id": "b", "name": "Kızıl Kavanoz Baharatçısı", "place_kind": "market", "parent_location_id": "kent"},
        })
        for line in ("Kızıl Örs Ocağına gidiyorum.", "Tamam Örs Ocağına uğruyorum."):
            self.assertEqual(local_places.visit_by_name(world, "kent", line)["id"], "a", line)
        for line in ("Kızıl Örs Ocağı nerede?", "Kızıl Örs Ocağına gitmiyorum.", "Kızıl dükkâna gidiyorum."):
            self.assertIsNone(local_places.visit_by_name(world, "kent", line), line)

    def test_a_taken_name_is_not_given_again(self):
        world = marked_world("tohum3")
        names = set()
        for number in range(1, 12):
            name = name_catalog.place_name(world, "tavern", "kent")
            self.assertNotIn(name, names)
            names.add(name)
            world["locations"][f"location_{number:03d}"] = {"id": f"location_{number:03d}", "name": name}

    def test_a_saved_place_keeps_its_name_when_the_table_changes(self):
        world = marked_world("tohum4", locations={"kent": {"id": "kent", "scene_kind": "city", "type": "city"}})
        record = local_places.create_local_place(world, "kent", "smithy")
        with patch.object(name_catalog, "place_templates", lambda: {}):
            self.assertEqual(local_places.create_local_place(world, "kent", "smithy")["name"], record["name"])

    def test_a_kind_with_no_table_is_a_catalog_person_and_its_word(self):
        world = marked_world("tohum5", locations={"kent": {"id": "kent", "scene_kind": "city", "type": "city"}})
        record = local_places.create_local_place(world, "kent", "temple")
        first, last = record["name"].rsplit(" ", 1)
        self.assertIn(first, name_catalog.people())
        self.assertEqual(last, "Tapınağı")

    def test_an_old_save_still_builds_the_old_kind_of_name(self):
        world = {"scene_state": {"campaign_seed": "tohum6"}, "npcs": [], "next_npc_number": 1,
                 "locations": {"kent": {"id": "kent", "scene_kind": "city", "type": "city"}}}
        record = local_places.create_local_place(world, "kent", "smithy")
        first, last = record["name"].rsplit(" ", 1)
        self.assertIn(first, living_world._LOCAL_NAMES)
        self.assertEqual(last, "Demirhanesi")

    def test_a_shop_found_on_the_street_is_named_from_the_table_too(self):
        world = marked_world("tohum7", locations={"kent": {"id": "kent", "scene_kind": "city", "type": "city"}})
        with patch.object(grounded_action, "public_door_state", lambda *a, **k: {"open": True, "locked": False}):
            record = grounded_action._create_venue(
                SimpleNamespace(world=world), "kent", name=None, kind="generic", provenance={}, noun="dukkan")
        self.assertNotIn(record["name"].split()[0], name_catalog.people())
        self.assertIn(record["name"], [door["name"].rsplit(" ", 1)[0] for door in world["doors"]])


class NewCampaignTests(unittest.IsolatedAsyncioTestCase):
    seeded_street = True
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown

    async def start(self):
        created = await self.http.post("/api/game/campaigns", json=START)
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["session_id"], self.manager.get(created.json()["session_id"]).game_session

    async def post(self, sid, message):
        with patch.object(self.app.state.ollama_adapter, "_client", TownClient()):
            turn = await self.http.post(f"/api/game/sessions/{sid}/turn", json={
                "message": message, "action_id": str(uuid.uuid4()),
            })
        self.assertEqual(turn.status_code, 200, turn.text)
        return turn.json()["narration"]

    async def test_a_new_campaign_is_marked_once_and_the_mark_is_saved(self):
        sid, session = await self.start()
        self.assertTrue(name_catalog.in_use(session.world_state))
        self.assertEqual(session.world_state["scene_state"]["name_pool"], name_catalog.VERSION)
        await self.post(sid, "Çevremi gözlemliyorum.")
        self.assertTrue(name_catalog.in_use(session.world_state))

    async def test_the_street_and_the_inn_use_the_catalog_and_the_door_still_answers(self):
        sid, session = await self.start()
        shown = [await self.post(sid, line) for line in (
            "Çevremi gözlemliyorum.", "Bu çevrede bir han var mı?", "Tamam, oraya gidiyorum.",
            "Kapıyı açmaya çalışıyorum.",
        )]
        world = session.world_state
        people = set(name_catalog.people())
        self.assertTrue({npc["name"] for npc in world["npcs"]} <= people, world["npcs"])
        inn = next(place for place in world["locations"].values() if place.get("scene_kind") == "tavern")
        self.assertEqual(inn["name"].split()[-1], "Hanı")
        self.assertNotIn(inn["name"].split()[0], people)
        self.assertIn(inn["name"], shown[1])
        self.assertEqual(world["location"], inn["id"], shown)

    async def test_going_to_a_place_by_its_name_arrives_and_meets_its_person(self):
        for attempt in range(6):
            sid, session = await self.start()
            world = session.world_state
            await self.post(sid, "Çevremi gözlemliyorum.")
            city = local_places.settlement_of(world, world["location"])
            place = local_places.create_local_place(world, city, "smithy")
            if place["name"].split()[-1] != "Demircisi":
                break
        shown = await self.post(sid, f"{place['name']}na gidiyorum.")
        self.assertEqual(world["location"], place["id"], shown)
        self.assertTrue(place.get("visited"))
        self.assertIsNotNone(local_places.resident_of(world, place["id"]), shown)


if __name__ == "__main__":
    unittest.main()
