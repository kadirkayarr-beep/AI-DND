"""New campaigns draw their people, places, first lines and role knowledge from the catalog; old saves keep theirs."""
import copy
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import campaign_time
import game
import grounded_action
import living_world
import local_places
import name_catalog
import npc_statements
import town_knowledge
from api import opening_narrative
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

    def test_a_person_recommending_a_real_place_is_not_corrected_to_another(self):
        for name in ("Lavanta Avlusu Hanı", "Kızıl Örs Ocağı", "Yedi Kadeh Hanı", "Tilki Heybesi Bakkalı"):
            line = f"{name} şehir merkezinde, uğrayabileceğin sakin bir yerdir."
            options = [{"name": "Başka Yer", "location_id": "b", "access": "available"},
                       {"name": name, "location_id": "a", "access": "available"}]
            with patch.object(game, "_local_place_recommendation_options", lambda *a, **k: options):
                self.assertEqual(game._ground_local_place_recommendation_reply(
                    line, {"id": "npc"}, {"locations": {}}, "Şehirde gidebileceğim sakin bir yer önerir misin?"), line)

    def test_a_generated_name_is_read_back_whole_from_a_persons_line(self):
        pools = name_catalog._pools()["pools"]["yuva_sözlüğü"]
        cut = []
        for kind, templates in name_catalog.place_templates().items():
            for template in templates:
                names = [template]
                for slot, entry in pools.items():
                    names = [n.replace("{" + slot + "}", value) for n in names for value in (
                        entry["örnek_değerler"] if "{" + slot + "}" in n else [""])]
                for name in names:
                    if name_catalog._reads_as_something_else(name, kind):
                        continue
                    read = [found[0] for found in npc_statements._named_places(f"{name} sakin bir yerdir.")]
                    if read and read != [name]:
                        cut.append((name, read))
        self.assertEqual(cut, [])

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


class OpeningTests(unittest.TestCase):
    def world(self, hour, kind="city", **place):
        world = {"location": "yer", "locations": {"yer": {"name": "Neverwinter", "scene_kind": kind, **place}},
                 "scene_state": {"campaign_seed": "tohum1"}}
        campaign_time.initialize(world)
        world["campaign_time"]["start_second"] = hour * 3600
        return world

    def lines(self, hour, weather="clear", **kwargs):
        texts = set()
        for seed in range(40):
            world = self.world(hour, **kwargs)
            world["scene_state"]["campaign_seed"] = f"tohum{seed}"
            texts.add(opening_narrative.catalog_line(world, "yer", weather))
        return texts

    def test_the_line_fits_the_hour_and_varies_by_seed(self):
        morning, noon, evening, night = (self.lines(hour) for hour in (8, 13, 18, 22))
        self.assertTrue(all(len(lines) >= 1 for lines in (morning, noon, evening, night)))
        self.assertGreaterEqual(len(noon | evening), 3)
        self.assertFalse(morning & noon or noon & evening or evening & night)
        self.assertTrue(all("Sabah" in line or "Kepenk" in line for line in morning), morning)

    def test_the_same_seed_gives_the_same_line(self):
        self.assertEqual(*(opening_narrative.catalog_line(self.world(13), "yer", "clear") for _ in range(2)))

    def test_no_street_name_is_invented_for_a_city(self):
        for hour in (8, 13, 18, 22):
            for line in self.lines(hour):
                self.assertNotIn("{", line)
                self.assertNotIn("Neverwinter boyunca", line)

    def test_a_line_of_sunlight_does_not_open_a_rainy_day(self):
        for weather in ("rain", "fog", "snow", "storm"):
            for hour in (8, 13, 18):
                lines = self.lines(hour, weather)
                self.assertTrue(lines, (weather, hour))
                for line in lines:
                    self.assertNotRegex(line, "güneş|Sabah ışığı|son ışık", (weather, hour))

    def test_an_inn_opens_as_an_inn_with_its_name_filled_in(self):
        lines = self.lines(18, kind="tavern")
        self.assertTrue(lines)
        self.assertTrue(all(("Han" in line or "Neverwinter" in line) and "sokak" not in line for line in lines), lines)

    def test_a_place_with_no_lines_has_none(self):
        self.assertIsNone(opening_narrative.catalog_line(self.world(13, kind="dungeon"), "yer", "clear"))

    def test_a_catalog_line_is_only_what_can_be_seen(self):
        for hour in (8, 13, 18, 22):
            for line in self.lines(hour):
                self.assertNotRegex(line.casefold(), "görev|sen |senin|hissed|görüyorsun")


class RoleKnowledgeTests(unittest.TestCase):
    def note(self, role, seed="tohum1", npc_id="npc_001"):
        world = {"scene_state": {"campaign_seed": seed}}
        return town_knowledge.role_note(world, {"id": npc_id, "role": role})

    def test_a_smith_is_told_what_a_smith_knows_and_does_not(self):
        note = self.note("Demirci")
        self.assertIn("metal işlerinin", note)
        self.assertIn("gizli ya da büyülü", note)
        self.assertIn("bilmediğini söyle", note)

    def test_a_role_with_no_profile_gets_nothing(self):
        self.assertEqual(self.note("Hamal"), "")
        self.assertEqual(self.note(""), "")

    def test_each_person_of_a_role_keeps_one_profile_and_people_differ(self):
        self.assertEqual(self.note("Rahip"), self.note("Rahip"))
        self.assertGreater(len({self.note("Rahip", npc_id=f"npc_{n}") for n in range(30)}), 1)

    def test_no_stock_line_or_visible_sign_goes_to_the_model(self):
        roles = json.loads((name_catalog.CATALOG_DIR / "npc_roles.json").read_text(encoding="utf-8"))["items"]
        notes = {self.note(key, npc_id=f"npc_{n}") for n in range(8)
                 for key in ("Demirci", "Rahip", "Muhafız", "Barmen", "Kâhya", "Liman işçisi", "Usta", "Gezgin")}
        for note in notes:
            self.assertLess(len(note.encode("utf-8")), 520)
            for item in roles:
                self.assertNotIn(item["example_line"], note)
                self.assertNotIn(item["typical_attitude"], note)
                self.assertFalse(set(item["visible_signs"]) & set(note.split("; ")))

    def test_every_table_entry_is_a_real_role_of_the_catalog(self):
        ids = {item["id"] for item in json.loads(
            (name_catalog.CATALOG_DIR / "npc_roles.json").read_text(encoding="utf-8"))["items"]}
        mapping = json.loads((name_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))
        for chosen in mapping["role_profiles"]["roles"].values():
            self.assertLessEqual(set(chosen), ids)

    def test_the_note_reaches_a_persons_prompt_even_when_they_keep_the_town_to_themselves(self):
        world = {"scene_state": {"campaign_seed": "tohum1"}}
        npc = {"id": "npc_001", "role": "Demirci"}
        with (patch.object(town_knowledge.world_threads, "view", lambda w: {"threads": [], "history": []}),
              patch.object(town_knowledge, "_settlement", lambda w: "kent"),
              patch.object(town_knowledge, "_job_note", lambda *a: ""),
              patch.object(town_knowledge, "public_knowledge", lambda *a: [])):
            self.assertIn("metal işlerinin", town_knowledge.speech_note(world, npc))
            with patch.object(town_knowledge, "is_closed_mouthed", lambda *a: True):
                self.assertIn("metal işlerinin", town_knowledge.speech_note(world, npc))


class NewCampaignOpeningTests(unittest.IsolatedAsyncioTestCase):
    seeded_street = True
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown

    async def test_campaigns_no_longer_open_on_the_same_fixed_words_and_a_reload_keeps_theirs(self):
        openings = set()
        for _ in range(10):
            created = await self.http.post("/api/game/campaigns", json=START)
            self.assertEqual(created.status_code, 200, created.text)
            world = self.manager.get(created.json()["session_id"]).game_session.world_state
            text = living_world.public_scene_projection(copy.deepcopy(world), 0)["opening"]
            self.assertTrue(text.startswith("Neverwinter."), text)
            for fixed in ("Şafak sökerken", "Gün ışığı altında", "Akşam yaklaşırken", "Gece çökmüşken",
                          "Gökyüzü açık; çevrenin çizgileri belirgin."):
                self.assertNotIn(fixed, text)
            openings.add(text)
        self.assertGreaterEqual(len(openings), 4, openings)


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
