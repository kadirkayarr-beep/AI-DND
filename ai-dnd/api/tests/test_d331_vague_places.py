"""G1.2 (D-331 rest, D-335, D-333, D-299, D-297): vague places and persons, mis-owned lines, heard names.

The town is seed 4401 (barracks, market, workshop, harbor, smithy; no tavern, no archive)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import game
import grounded_action
import heard_rumours
import local_dialogue
import local_places
import npc_statements
from api.tests.test_arrival_wiring import _ArrivalApi

CITY = "fr:city:neverwinter"
FAILED_WALK = "yolu bulamıyorsun"
ASK = "Hangisine gidiyorsun?"
LORE = "söylentiler belirsiz"


class VaguePlaces(_ArrivalApi):
    TOWN_SEED = 4401

    async def asyncSetUp(self):
        await super().asyncSetUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"AI_DND_ROUTE_LOG": str(Path(directory.name) / "routes.jsonl")}))

    def narration(self, reply):
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()["narration"]

    def town_places(self):
        world = self.session().world_state
        return {key: rec for key, rec in world["locations"].items()
                if isinstance(rec, dict) and rec.get("parent_location_id") == CITY}

    def speaker(self):
        world = self.session().world_state
        world["npcs"].append({"id": "npc_talker", "name": "Hadrik", "public_name": "Hadrik", "role": "Nöbetçi çavuş",
                              "reality_layer": "PROCEDURAL_LOCAL_FICTION", "relationship": "neutral",
                              "knowledge": [], "combat_status": "active", "current_hp": 12, "status": "active",
                              "memory": [], "location": world["location"]})
        return world["npcs"][-1]

    def hear_inn(self, name="Kara Kuzgun Hanı"):
        world = self.session().world_state
        npc = self.speaker()
        line = f"{npc['name']}, “Konaklamak istiyorsan {name}'na git, orada oda bulursun.” diye yanıtlıyor."
        npc_statements.record(world, npc, "Kalacak yer var mı?", line, turn=None)
        return npc

    def with_session(self, call):
        token = game._ACTIVE_SESSION.set(self.session())
        try:
            return call()
        finally:
            game._ACTIVE_SESSION.reset(token)

    async def test_listed_place_not_named_by_reading_walks_or_asks(self):
        world = self.session().world_state
        workshop = next(key for key, rec in self.town_places().items() if rec.get("place_kind") == "workshop")
        reply = await self.turn("Bakkala gidiyorum.", front={"kind": "go_to", "place_id": workshop})
        text = self.narration(reply)
        self.assertNotIn(FAILED_WALK, text)
        walked_to_named = world["location"] != CITY and world["location"] != workshop
        self.assertTrue(walked_to_named or ASK in text, (world["location"], text))
        self.assertNotEqual(world["location"], workshop)

    async def test_npc_named_inn_is_an_option(self):
        self.hear_inn()
        session = self.session()
        options = self.with_session(lambda: [c for c in grounded_action.candidates(session)
                                             if c["kind"] in {"place", "reference"}])
        named = self.with_session(lambda: grounded_action.worth_naming(
            session, "Anlattığı yoldan hana gitmeye çalışıyorum.", options))
        self.assertTrue(any("Kara Kuzgun" in o["label"] for o in named), [o["label"] for o in named])

    async def test_a_heard_place_the_narration_never_quoted_is_an_option(self):
        world = self.session().world_state
        npc = self.speaker()
        entry = heard_rumours.record_mention(
            game, world, npc, {"kind": "place", "name": "Kara Kuzgun Kütüphanesi", "place_kind": "library",
                               "about": "eski kitaplar var"}, 1)
        self.assertIsNotNone(entry)
        session = self.session()
        options = self.with_session(lambda: [c for c in grounded_action.candidates(session)
                                             if c["kind"] in {"place", "reference"}])
        named = self.with_session(lambda: grounded_action.worth_naming(session, "Oraya gidiyorum.", options))
        self.assertIn(entry["place_id"], [o["id"] for o in named], [o["label"] for o in named])

    async def test_misrouted_lines(self):
        for line in ("4 bakırım var mı?", "Teşekkür edip tavernaya gidiyorum.", "Teşekkür edip handan çıkıyorum."):
            # the lore gate (turn.py world_subject_question) is this classifier in "do" mode: it must not own these
            self.assertFalse(local_dialogue.is_world_subject_question(line), line)
        world = self.session().world_state
        self.speaker()
        reply = await self.turn("4 bakırım var mı?")
        self.assertNotIn(LORE, self.narration(reply))
        reply = await self.turn("Teşekkür edip tavernaya gidiyorum.")
        self.assertNotIn(LORE, self.narration(reply))
        self.assertNotEqual(world["location"], CITY)
        inn = world["location"]
        reply = await self.turn("Teşekkür edip handan çıkıyorum.")
        self.assertNotIn(LORE, self.narration(reply))
        self.assertEqual(world["location"], CITY)
        self.assertNotEqual(inn, CITY)

    async def test_generic_alias_only_with_one_match(self):
        world = self.session().world_state
        local_places.create_local_place(world, CITY, "archive", name="Eski Arşiv")
        second = local_places.create_local_place(world, CITY, "archive", name="Yeni Arşiv")
        second["rumoured"] = True  # what record_mention writes for a place someone only named
        reply = await self.turn("Arşive gidiyorum.")
        text = self.narration(reply)
        self.assertEqual(world["location"], CITY, text)
        self.assertIn("Hangisine gidiyorsun?", text)
        self.assertIn("Eski Arşiv", text)
        self.assertIn("Yeni Arşiv", text)
        reply = await self.turn("Yeni Arşiv'e gidiyorum.")  # its own name still walks
        self.assertEqual(world["location"], second["id"], self.narration(reply))

    async def test_generic_alias_question_is_recorded_like_other_clarifications(self):
        world = self.session().world_state
        local_places.create_local_place(world, CITY, "archive", name="Eski Arşiv")
        local_places.create_local_place(world, CITY, "archive", name="Yeni Arşiv")["rumoured"] = True
        before = len(self.session().messages)
        reply = await self.turn("Arşive gidiyorum.")
        text = self.narration(reply)
        tail = [m.get("content") for m in self.session().messages[before:]]
        self.assertTrue(any("Arşive gidiyorum." in str(c) for c in tail), tail)
        self.assertEqual(sum("Hangisine gidiyorsun?" in str(c) for c in tail), 1, (tail, text))
        self.assertEqual(world["location"], CITY)

    async def test_a_generic_word_walks_when_the_town_holds_one_such_place(self):
        world = self.session().world_state
        only = local_places.create_local_place(world, CITY, "archive", name="Eski Arşiv")
        reply = await self.turn("Arşive gidiyorum.")
        self.assertEqual(world["location"], only["id"], self.narration(reply))

    async def test_heard_inn_name_routes_to_inn(self):
        world = self.session().world_state
        self.hear_inn()
        reply = await self.turn("Hana gidiyorum.")
        text = self.narration(reply)
        self.assertNotIn("giremiyorsun", text)
        self.assertEqual(world["locations"][world["location"]]["name"], "Kara Kuzgun Hanı", text)
        inn = world["location"]
        world["location"] = CITY
        reply = await self.turn("Kara Kuzgun Hanı'na gidiyorum.")
        self.assertNotIn("giremiyorsun", self.narration(reply))
        self.assertEqual(world["location"], inn)

    async def test_heard_inn_name_routes_to_inn_when_the_front_lists_it(self):
        world = self.session().world_state
        self.hear_inn()
        session = self.session()
        ref = self.with_session(lambda: next(c["id"] for c in grounded_action.candidates(session)
                                             if c["kind"] == "reference"))
        reply = await self.turn("Kara Kuzgun Hanı'na gidiyorum.", front={"kind": "go_to", "place_id": ref})
        self.assertNotIn("giremiyorsun", self.narration(reply))
        self.assertEqual(world["locations"][world["location"]]["name"], "Kara Kuzgun Hanı")
