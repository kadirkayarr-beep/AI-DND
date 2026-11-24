"""D-331: a walk to a place the front list does not name no longer ends on "oraya çıkan yolu bulamıyorsun".

A place named by its kind ("tavernaya gidiyorum" in a town with no inn yet) is a world-knowledge entry of the list
(`kind:<kind>`) and walks through the old chain's search-by-kind; a walk after a person follows them; a walk that still
finds nothing asks which known place. The town is seed 4401: five places (barracks, market, workshop, harbor, smithy),
no tavern."""
import copy
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import everyday_actions
import front_proposal
import game
import grounded_action
import grounded_places
import living_world
import town_knowledge
import world_threads
from api.tests.test_arrival_wiring import _ArrivalApi

CITY = "fr:city:neverwinter"
FAILED_WALK = "yolu bulamıyorsun"
ASK = "Hangisine gidiyorsun?"


class TravelBeyondTheList(_ArrivalApi):
    TOWN_SEED = 4401

    async def asyncSetUp(self):
        await super().asyncSetUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.route_file = Path(directory.name) / "routes.jsonl"
        self.enterContext(patch.dict(os.environ, {"AI_DND_ROUTE_LOG": str(self.route_file)}))

    def route(self):
        rows = [json.loads(line) for line in self.route_file.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        return rows[-1]["route"]

    def listed(self):
        token = game._ACTIVE_SESSION.set(self.session())
        try:
            return front_proposal.listing(self.session())
        finally:
            game._ACTIVE_SESSION.reset(token)

    def town_places(self):
        world = self.session().world_state
        return {key: rec for key, rec in world["locations"].items()
                if isinstance(rec, dict) and rec.get("parent_location_id") == CITY}

    def taverns(self):
        world = self.session().world_state
        return [key for key in self.town_places() if living_world.scene_kind(world, key) == "tavern"]

    def narration(self, reply):
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()["narration"]

    def present_person(self):
        world = self.session().world_state
        world["npcs"].append({"id": "npc_walker", "name": "Hadrik", "public_name": "Hadrik", "role": "Nöbetçi çavuş",
                              "reality_layer": "PROCEDURAL_LOCAL_FICTION", "relationship": "neutral",
                              "knowledge": [], "combat_status": "active", "current_hp": 12, "status": "active",
                              "memory": [], "location": world["location"]})
        token = game._ACTIVE_SESSION.set(self.session())
        try:
            people = [c for c in grounded_action.candidates(self.session()) if c["kind"] == "npc"]
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertTrue(people, "the street has someone to follow")
        return people[0]

    async def test_the_list_offers_the_kinds_the_town_has_not_shown_yet(self):
        rows = self.listed()["places"]
        ids = [row["id"] for row in rows]
        self.assertIn("kind:tavern", ids)
        first_kind = min(i for i, key in enumerate(ids) if key.startswith("kind:"))
        self.assertTrue(all(key.startswith("kind:") for key in ids[first_kind:]))
        self.assertTrue(any(not key.startswith("kind:") for key in ids[:first_kind]))
        for kind in ("barracks", "market", "workshop", "harbor", "smithy"):
            self.assertNotIn(f"kind:{kind}", ids)

    async def test_a_tavern_by_its_kind_walks_to_a_real_inn(self):
        world = self.session().world_state
        reply = await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        self.assertNotIn(FAILED_WALK, self.narration(reply))
        inn = world["location"]
        self.assertEqual(world["locations"][inn]["parent_location_id"], CITY)
        self.assertEqual(living_world.scene_kind(world, inn), "tavern")
        world["location"] = CITY
        reply = await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": inn})
        self.assertNotIn(FAILED_WALK, self.narration(reply))
        self.assertEqual(world["location"], inn)
        self.assertEqual(self.taverns(), [inn])

    async def test_a_kind_the_town_already_has_is_not_offered_again(self):
        await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        self.assertNotIn("kind:tavern", [row["id"] for row in self.listed()["places"]])

    async def test_a_question_about_a_kind_does_not_walk(self):
        world = self.session().world_state
        for line in ("Tavernaya nasıl giderim?", "Tavernaya gitmiyorum."):
            reply = await self.turn(line, front={"kind": "go_to", "place_id": "kind:tavern"})
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertEqual(world["location"], CITY, line)
            self.assertEqual(self.taverns(), [], line)

    async def test_following_a_listed_person_is_no_failed_walk(self):
        person = self.present_person()
        reply = await self.turn("Onun peşinden gidiyorum.",
                                front={"kind": "go_to", "place_id": "none", "person_id": person["id"]})
        text = self.narration(reply)
        self.assertIn(living_world.public_npc_name(person["record"]), text)
        self.assertNotIn(FAILED_WALK, text)
        self.assertEqual(self.route(), "front:follow")

    async def test_following_a_passing_figure_can_end_at_a_real_place(self):
        world = self.session().world_state
        names = {rec["name"] for rec in self.town_places().values()}
        outcomes = [everyday_actions.follow_route(world, {"kind": "follow", "word": "haberci"}, turn=t)
                    for t in range(10)]
        self.assertTrue(any(o["place_id"] in self.town_places() for o in outcomes))
        for outcome in outcomes:
            self.assertNotIn(FAILED_WALK, outcome["text"])
            if outcome["place_id"]:
                self.assertTrue(any(name in outcome["text"] for name in names))
        reply = await self.turn("Habercinin peşinden gidiyorum.",
                                front={"kind": "go_to", "place_id": "none", "person_word": "haberci"})
        self.assertNotIn(FAILED_WALK, self.narration(reply))
        self.assertEqual(self.route(), "front:follow")

    async def test_after_following_oraya_goes_to_that_place(self):
        world = self.session().world_state
        turn = next(t for t in range(1, 20)
                    if everyday_actions.follow_route(world, {"kind": "follow", "word": "haberci"}, turn=t)["place_id"])
        place = everyday_actions.follow_route(world, {"kind": "follow", "word": "haberci"}, turn=turn)["place_id"]
        world.setdefault("flags", {})["turn_index"] = turn - 1
        await self.turn("Habercinin peşinden gidiyorum.",
                        front={"kind": "go_to", "place_id": "none", "person_word": "haberci"})
        self.assertEqual(world["location"], CITY)
        reply = await self.turn("Oraya giriyorum.", front={"kind": "go_to", "place_id": place, "inside": True})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["location"], place)

    async def test_a_walk_to_nowhere_names_the_places_known(self):
        reply = await self.turn("Şuraya gidiyorum.", front={"kind": "go_to", "place_id": "none"})
        text = self.narration(reply)
        self.assertNotIn(FAILED_WALK, text)
        self.assertIn(ASK, text)
        self.assertGreaterEqual(sum(rec["name"] in text for rec in self.town_places().values()), 2, text)

    async def test_a_listed_place_the_line_does_not_name_is_no_failed_walk(self):
        world = self.session().world_state
        workshop = next(key for key, rec in self.town_places().items() if rec.get("place_kind") == "workshop")
        reply = await self.turn("Bakkala gidiyorum.", front={"kind": "go_to", "place_id": workshop})
        text = self.narration(reply)
        self.assertNotEqual(world["location"], workshop)
        self.assertNotIn(FAILED_WALK, text)
        self.assertTrue(text.strip(), text)  # ledger: this line ended on the scene narration, the player did not move

    async def test_a_heard_shop_is_listed_first(self):
        world = self.session().world_state
        threads = [t for t in world_threads.active(world, CITY) if t.get("place_id") in world["locations"]]
        order = list(world["locations"])
        thread = max(threads, key=lambda t: order.index(t["place_id"]))
        template = copy.deepcopy(world["locations"][thread["place_id"]])
        fillers = {}
        for number in range(22):
            record = copy.deepcopy(template)
            record.update(id=f"filler_{number:02d}", name=f"Dolgu Dükkânı {number:02d}", hidden=False)
            fillers[record["id"]] = record
        world["locations"] = {**fillers, **world["locations"]}  # the heard place now stands past the 20th row
        town_knowledge.hear_of(world, thread)
        ids = [row["id"] for row in self.listed()["places"]]
        self.assertIn(thread["place_id"], ids)
        self.assertLess(ids.index(thread["place_id"]), 6)

    async def test_the_kind_walk_step_has_the_keys_the_old_chains_search_by_kind_step_has(self):
        token = game._ACTIVE_SESSION.set(self.session())
        try:
            old = next(step for step in grounded_action.plan(self.session(), "hana gidiyorum")["steps"]
                       if step.get("place_noun"))
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(set(grounded_places._kind_walk_step("han", "tavern")), set(old))

    async def test_a_kind_walk_spends_the_front_reading_and_no_more_than_two_calls(self):
        await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        self.assertLessEqual(len(self.client.kinds), 2, self.client.kinds)
