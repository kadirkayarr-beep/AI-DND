"""The owner's first browser play (31 Oct 2026) pinned as regressions.

Every test replays the owner's own sentence, or the exact line the game showed.
The model is mocked, so these prove the deterministic path alone.
"""

from __future__ import annotations

import unittest

import grounded_action
import living_world
import npc_statements
from api.tests import test_lr00_grounded_human as human
from api.tests.test_lr00_grounded_human import CITY, GARRICK, GARRICK_DOOR


class SpokenPlaceNames(unittest.TestCase):
    def names(self, line):
        return [item[0] for item in npc_statements._named_places(line)]

    def test_a_yes_before_the_name_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Bir şey yok, sadece yolculuk. Evet, Veyra Hanı var."), ["Veyra Hanı"])

    def test_a_yes_without_a_comma_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Evet Veyra Hanı var."), ["Veyra Hanı"])

    def test_two_places_in_a_list_stay_two_places(self):
        self.assertEqual(self.names("Kızıl Kule, Veyra Hanı ikisi de yakın."), ["Kızıl Kule", "Veyra Hanı"])

    def test_a_real_two_word_name_keeps_both_words(self):
        self.assertEqual(self.names("Tamam, Gümüş Kılıç Hanı burada."), ["Gümüş Kılıç Hanı"])


class OwnerPlayBase(unittest.IsolatedAsyncioTestCase):
    """The saved owner world, driven through the real HTTP turn with a mocked model."""

    asyncSetUp = human.HumanP6Regressions.asyncSetUp
    asyncTearDown = human.HumanP6Regressions.asyncTearDown
    world = human.HumanP6Regressions.world
    door = human.HumanP6Regressions.door
    turn = human.HumanP6Regressions.turn


class WanderingTheCity(OwnerPlayBase):
    def rumour(self, name):
        state = npc_statements.ensure(self.world)
        npc_statements._add_reference(
            self.world, state, npc_id="npc_001", name=name, noun="han", kind="tavern",
            claims=[], quote=f"{name} var.", turn=1, settlement=CITY,
        )

    async def test_wandering_after_leaving_does_not_walk_back_to_that_inn(self):
        self.world["location"] = GARRICK
        next(d for d in self.world["doors"] if d["id"] == GARRICK_DOOR).update(open=True, locked=False)
        state = npc_statements.ensure(self.world)
        state["references"].clear()
        self.rumour("Garrick Hanı")
        state["references"][-1].update(status="rumor", location_id=None)
        text, _ = await self.turn("handan çıkıyorum ve şehirde geziyorum")
        self.assertEqual(self.world["location"], CITY, text)
        self.assertNotIn("tabelasını", text)
        self.assertEqual(text.count("Garrick Hanı"), 1, text)  # only the leaving sentence
        self.assertNotEqual(grounded_action.near_door_id(self.world), GARRICK_DOOR, text)

    async def test_a_sign_seen_while_wandering_does_not_move_the_player_to_it(self):
        npc_statements.ensure(self.world)["statements"].clear()
        self.rumour("Mavi Kaz Hanı")
        text, _ = await self.turn("şehirde geziyorum")
        self.assertIn("Mavi Kaz Hanı tabelasını", text)
        self.assertNotIn("önüne geliyorsun", text)
        self.assertEqual(self.world["location"], CITY)
        self.assertIsNone(grounded_action.near_door_id(self.world), text)
        follow, _ = await self.turn("Oraya gidiyorum.")
        self.assertIn("Mavi Kaz Hanı", follow)

    async def test_a_new_place_found_wandering_is_named_once(self):
        npc_statements.ensure(self.world)["references"].clear()
        text, _ = await self.turn("şehirde geziyorum")
        self.assertNotIn("önüne çıkarıyor", text)
        self.assertEqual(text.count("önüne"), 1, text)


class AmbientEventsAreNotPeople(OwnerPlayBase):
    EVENT = "İki esnaf kısa bir tartışmaya tutuşur; biri avucunu tezgâha vurur."

    async def test_an_event_does_not_become_the_description_of_a_person(self):
        turn = self.world["flags"].get("turn_index", 0)
        scene = living_world.ensure_scene_record(self.world, CITY, turn)
        scene["materialized"] = True
        scene["referents"].clear()
        scene["last_beat"] = self.EVENT
        living_world.create_scene_referent(self.world, CITY, turn, description=self.EVENT, aliases=["esnaf"])
        await self.turn("Esnaf ile konuşmak istiyorum.")
        npc = next(n for n in self.world["npcs"] if n.get("role") == "Yolcu" and n.get("location") == CITY)
        self.assertNotIn("esnaf", npc.get("appearance", "").casefold())
        await self.turn("Konuşmayı bitiriyorum.")
        text, _ = await self.turn("etrafımı dikkatlice gözlemliyorum")
        self.assertLessEqual(text.count("İki esnaf"), 1, text)
        self.assertNotIn(": İki esnaf", text)

    async def test_a_feature_in_a_look_reads_as_a_sentence(self):
        scene_look = "Gözüne Ahşap masa çarpıyor"
        self.world["features"].append({"id": "f_table", "location": CITY, "name": "Ahşap masa", "kind": "furnishing"})
        text, _ = await self.turn("etrafımı dikkatlice gözlemliyorum")
        self.assertNotIn(scene_look, text)
        self.assertIn("Ahşap masa gözüne çarpıyor.", text)
