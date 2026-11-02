"""A passed check shows a concrete detail of the real thing looked at, and that thing keeps it.

Real app, real engine; lines are typed the way the owner types them.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import bound_text
import grounded_action
import world_threads
from api.tests.test_front_proposal import FrontTable


class Catalog(FrontTable):
    def test_all_rows_arrived_in_the_repo(self):
        self.assertEqual(len(bound_text.items("scene_details")), 150)
        self.assertEqual(len(bound_text.items("written_texts")), 80)
        self.assertEqual(len(bound_text.items("work_lines")), 60)

    def test_a_kind_of_place_and_a_kind_of_thing_are_read_from_the_record(self):
        world = {"locations": {"a": {"place_kind": "harbor"}, "b": {"scene_kind": "tavern"}, "c": {"scene_kind": "city"}}}
        self.assertEqual(bound_text.place_tags(world, "a"), ["liman"])
        self.assertEqual(bound_text.place_tags(world, "b"), ["han"])
        self.assertEqual(bound_text.place_tags(world, "c"), ["sokak"])
        self.assertEqual(bound_text.object_tag("Harita masası", "harita"), "masa")
        self.assertEqual(bound_text.object_tag("sandığı"), "sandik")
        self.assertIsNone(bound_text.object_tag("çeşme"))


class Passed(FrontTable):
    def tavern(self):
        place = self.world["locations"][self.world["location"]]
        place.update(scene_kind="tavern")
        place.pop("place_kind", None)

    def table(self):
        self.session.create_local_feature({"location": self.world["location"], "name": "Meşe masa",
                                           "description": "Çizik dolu bir masa.", "aliases": ["masa"]})

    def roll(self, line, outcome="success", word="", found=""):
        self.session._front_found = (found, word)
        return self.session._inspection_findings(line, outcome)

    def rows(self):
        return {row["id"]: row for row in bound_text.items("scene_details")}

    def plain_rows(self, tag, place):
        return {row["text"] for row in bound_text.items("scene_details")
                if tag in row["object_tags"] and place in row["place_tags"] and not row["slots"]}

    async def a_public_thread(self, place_name="Ay Sofrası Atölyesi"):
        await self.begin()
        self.thread["place_id"] = "location_bound"
        self.world["locations"]["location_bound"] = {
            "id": "location_bound", "name": place_name, "place_kind": "workshop", "scene_kind": "building",
            "parent_location_id": self.world["location"]}
        return self.thread

    async def test_a_pass_on_a_saved_table_shows_a_table_row_of_this_kind_of_place(self):
        await self.begin()
        self.tavern()
        self.table()
        found = self.roll("mese masaya egilip iyice bakiyom")
        self.assertIs(found["found"], True)
        self.assertTrue(any(row in found["text"] for row in self.plain_rows("masa", "han")), found["text"])
        self.assertIn("Çizik dolu bir masa.", found["text"])

    async def test_a_second_look_says_the_same_and_a_failed_look_remembers_it(self):
        await self.begin()
        self.tavern()
        self.table()
        first = self.roll("mese masaya egilip bakiyom")
        self.assertEqual(self.roll("mese masaya bi daha bakiyim")["text"], first["text"])
        self.assertEqual(self.roll("mese masaya bi daha bakiyim", "failure")["text"], first["text"])

    async def test_a_failed_first_look_binds_nothing(self):
        await self.begin()
        self.tavern()
        self.table()
        self.roll("mese masaya bakiyom", "failure")
        self.assertIsNone(self.world.get(bound_text.KEY))

    async def test_a_kind_of_thing_no_row_has_keeps_the_reading(self):
        await self.begin()
        found = self.roll("cesmeye yakindan bakiyom", word="çeşme", found="Çeşmenin taşında ince bir çatlak duruyor.")
        self.assertEqual(found["text"], "Çeşmenin taşında ince bir çatlak duruyor.")

    async def test_a_thing_only_the_reader_named_is_saved_and_then_holds_its_words(self):
        await self.begin()
        first = self.roll("kirik kutuyu yokluyom", word="kutu", found="Bambaşka bir cümle burada duruyor.")
        self.assertTrue(first["found"])
        self.assertIn(first["text"], {row["text"] for row in self.rows().values() if "kutu" in row["object_tags"]})
        saved = [row for row in self.world["features"] if row.get("id") == first["target_id"]]
        self.assertEqual(saved[0]["description"], first["text"])
        count = len(self.world["features"])
        again = self.roll("kutuya bi daha bakiyom", word="kutu", found="Başka bir şey daha burada duruyor.")
        self.assertIn(first["text"], again["text"])
        self.assertEqual(len(self.world["features"]), count)

    async def test_the_line_names_the_thing_when_the_reader_named_a_crack_in_it(self):
        await self.begin()
        found = self.roll("yerdeki zemini inceliyom catlak var mi", word="çatlak")
        self.assertIs(found["found"], True)
        self.assertIn(found["text"], self.plain_rows("zemin", "sokak"))
        self.assertEqual(next(row for row in self.world["features"] if row["id"] == found["target_id"])["name"], "Zemin")

    async def test_a_saved_finding_of_the_reader_stands_on_a_second_look_too(self):
        await self.begin()
        first = self.roll("cesmeye yakindan bakiyom", word="çeşme", found="Çeşmenin taşında ince bir çatlak duruyor.")
        count = len(self.world["features"])
        again = self.roll("cesmeyi tekrardan inceliyorum dikkatlice", word="çeşme", found="Oluğun dibinde yeşil bir yosun görünüyor.")
        self.assertIn(first["text"], again["text"])
        self.assertEqual(len(self.world["features"]), count)

    async def test_choosing_writes_nothing(self):
        thread = await self.a_public_thread()
        before = copy.deepcopy(self.world)
        for tag in ("duvar", "kapi", "kutu", "sandik"):
            bound_text.choose_detail(self.world, f"t:{tag}", ["sokak"], tag)
        self.assertEqual(self.world, before)
        self.assertEqual(thread["status"], "open")

    async def test_a_row_with_a_slot_needs_a_real_public_thread(self):
        await self.begin()
        world_threads.view(self.world)["threads"].clear()
        for number in range(40):
            choice = bound_text.choose_detail(self.world, f"thing{number}", ["sokak"], "duvar")
            self.assertTrue(choice is None or "{" not in choice["text"])
            self.assertFalse(choice and choice.get("thread_id"))

    async def test_a_lead_names_the_real_place_and_the_player_can_walk_there(self):
        thread = await self.a_public_thread()
        self.session.create_local_feature({"location": self.world["location"], "name": "Harap duvar",
                                           "description": "Sıvası dökülmüş bir duvar.", "aliases": ["duvar"]})
        found = self.roll("harap duvari inceliyom")
        self.assertIn("Ay Sofrası Atölyesi", found["text"])
        self.assertEqual(thread["status"], "heard")
        self.assertEqual(bound_text.seen(self.world, f"feature:{found['target_id']}")["thread_id"], thread["thread_id"])

    async def test_a_lead_is_given_once_and_looking_again_gives_nothing_new(self):
        thread = await self.a_public_thread()
        for name in ("Harap duvar", "Kuru duvar"):
            self.session.create_local_feature({"location": self.world["location"], "name": name,
                                               "description": "Sıvası dökülmüş.", "aliases": []})
        first = self.roll("harap duvari inceliyom")
        heard_turn = thread.get("heard_turn")
        self.world["flags"]["turn_index"] += 3
        self.assertEqual(self.roll("harap duvari inceliyom")["text"], first["text"])
        self.assertEqual(thread.get("heard_turn"), heard_turn)
        self.assertNotIn("Ay Sofrası Atölyesi", self.roll("kuru duvari inceliyom")["text"])

    async def test_a_comparison_with_a_boot_never_seen_is_never_shown(self):
        await self.begin()
        for row_id in ("SD004", "SD026", "SD038", "SD080"):
            self.assertIn(row_id, bound_text.rules()["needs_a_seen_sample"])
        for number in range(30):
            choice = bound_text.choose_detail(self.world, f"s{number}", ["sokak", "han", "pazar", "soylu_konagi"], "ayak_izi")
            self.assertFalse(choice and choice["id"] in bound_text.rules()["needs_a_seen_sample"])

    async def test_a_name_the_player_does_not_know_is_not_read_off_a_wall(self):
        thread = await self.a_public_thread()
        owner = self.npc
        thread["owner_npc_id"] = owner["id"]
        owner.update(name="Umerişa", name_known_to_player=False, location="location_bound")
        for number in range(40):
            choice = bound_text.choose_detail(self.world, f"k{number}", ["pazar"], "kutu")
            self.assertNotIn("Umerişa", (choice or {}).get("text", ""))

    async def test_a_passed_door_look_adds_what_the_door_shows_and_keeps_it(self):
        import game
        await self.begin()
        self.tavern()
        door = {"id": "door_bound", "name": "Arka kapı", "location": self.world["location"], "locked": True}
        original = game._current_door
        game._current_door = lambda: door
        self.addCleanup(setattr, game, "_current_door", original)
        first = self.roll("kapiyi inceliyom dikkatlice")
        self.assertTrue(any(row in first["text"] for row in self.plain_rows("kapi", "han")), first["text"])
        self.assertEqual(self.roll("kapiyi inceliyom")["text"], first["text"])

    async def test_the_tracks_of_a_place_with_rows_hold_their_words(self):
        await self.begin()
        self.world["locations"][self.world["location"]].update(place_kind="barracks")
        first = self.roll("yerdeki izleri inceliyom")
        self.assertEqual(first["text"], self.rows()["SD100"]["text"])
        self.assertEqual(self.roll("izlere bi daha bakiyom", "failure")["text"], first["text"])

    async def test_nothing_of_the_catalog_but_the_shown_words_reaches_the_narrator(self):
        await self.begin()
        self.tavern()
        self.table()
        found = self.roll("mese masaya egilip bakiyom")
        self.client.front = {"kind": "attempt"}
        await self.line("masanin ustunde parmaklarimla tempo tutuyom")
        said = json.dumps(self.client.message_batches, ensure_ascii=False)
        kept = bound_text.seen(self.world, f"feature:{found['target_id']}")
        for row in bound_text.items("scene_details"):
            if row["id"] != kept["id"]:
                self.assertNotIn(row["text"], said)
        self.assertNotIn(bound_text.KEY, said)
        self.assertNotIn("binding_rules", said)

    async def test_a_locked_door_read_closely_on_a_pass_shows_it_and_says_it_again(self):
        await self.begin()
        self.tavern()
        door = {"id": "door_bound", "name": "Arka kapı", "location": self.world["location"], "locked": True}
        target = {"id": door["id"], "kind": "door", "label": door["name"], "record": door}
        run = SimpleNamespace(world=self.world, here=self.world["location"], memory={"observations": {}}, inspections=[],
                              near=lambda _: None)
        step = {"verb": "inspect", "tokens": ["kapiyi", "inceliyorum"]}
        with patch.object(grounded_action, "_check", return_value={"success": True}), \
                patch.object(grounded_action, "_check_public", return_value={}):
            first = grounded_action._inspect_door(run, step, target)
        self.assertTrue(any(row in first["text"] for row in self.plain_rows("kapi", "han")), first["text"])
        again = grounded_action._inspect_door(run, step, target)
        self.assertEqual(bound_text.seen(self.world, "door:door_bound")["text"] in again["text"], True)

    async def test_a_save_keeps_the_words(self):
        await self.begin()
        self.tavern()
        self.table()
        first = self.roll("mese masaya egilip bakiyom")
        reloaded = json.loads(json.dumps(self.world, ensure_ascii=False))
        self.assertEqual(bound_text.seen(reloaded, f"feature:{first['target_id']}"),
                         bound_text.seen(self.world, f"feature:{first['target_id']}"))
