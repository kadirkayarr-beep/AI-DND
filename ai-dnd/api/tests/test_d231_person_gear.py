"""D-231: a person of the town carries fixed gear by what they are, written once from the campaign seed; a body gives
it up with its purse. An old save writes the gear on its first load. Undo and reload of a body search are pinned by
journey 95."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import equipment_economy
from api.tests.test_species_traits import make_session
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests
from weapon_catalog import lookup


def _gear(npc):
    return [item for item in npc.get("inventory") or [] if isinstance(item, dict)]


class APersonsGear(unittest.TestCase):
    def setUp(self):
        self.session = make_session("Human")
        self.world = self.session.world_state

    def person(self, name, role, **extra):
        npc = self.session.create_npc_from_ai({"name": name, "role": role, "location": self.world["location"]})
        self.assertIsNotNone(npc)
        npc.update(extra)
        return npc

    def test_a_new_person_carries_one_catalog_weapon_fixed_by_who_they_are(self):
        guard = self.person("Dorn", "Muhafız")
        items = _gear(guard)
        self.assertEqual(len(items), 1)
        weapon = lookup(items[0]["name"])
        self.assertIsNotNone(weapon)  # a catalog weapon, so its price is the catalog's
        self.assertEqual(items[0]["weapon_id"], weapon["weapon_id"])
        self.assertIn(items[0]["name"], equipment_economy.PERSON_GEAR["armed"])
        equipment_economy.price(items[0])  # priced from the catalog, no error

    def test_the_same_person_in_the_same_campaign_always_gets_the_same_gear(self):
        record = {"id": "npc_777", "role": "Demirci"}
        first, second = dict(record), dict(record)
        equipment_economy.give_person_gear(self.world, first)
        equipment_economy.give_person_gear(self.world, second)
        self.assertEqual(first["inventory"], second["inventory"])
        self.assertIn(first["inventory"][0]["name"], equipment_economy.PERSON_GEAR["strong"])

    def test_possessions_already_written_are_never_written_again(self):
        for inventory in ([], [{"item_id": "item_900001", "name": "Hançer"}]):
            with self.subTest(inventory=inventory):
                npc = {"id": "npc_778", "role": "Muhafız", "inventory": list(inventory)}
                equipment_economy.give_person_gear(self.world, npc)
                self.assertEqual(npc["inventory"], inventory)

    def test_a_shopkeeper_and_a_stat_block_creature_get_no_gear(self):
        for npc in ({"id": "npc_779", "role": "Shopkeeper"}, {"id": "npc_780", "role": "traveler", "statblock": {}}):
            with self.subTest(npc=npc):
                equipment_economy.give_person_gear(self.world, npc)
                self.assertNotIn("inventory", npc)

    def test_an_old_save_writes_the_gear_on_its_first_load_and_only_then(self):
        self.world["npcs"] = [
            {"id": "npc_old", "name": "Arven", "role": "Muhafız", "location": self.world["location"]},
            {"id": "npc_robbed", "name": "Sera", "role": "Muhafız", "location": self.world["location"], "inventory": []},
        ]
        self.world.pop(equipment_economy.GEAR_WRITTEN, None)  # a save from before D-231
        self.world["currency"] = {"player": 0}  # D-207: the replaced town's people take their purses with them
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "old.json"
            self.session.save_game(old)
            reopened = make_session("Human")
            reopened.load_game(old)
            arven, sera = reopened.world_state["npcs"]
            self.assertEqual(len(_gear(arven)), 1)
            self.assertIn(arven["inventory"][0]["name"], equipment_economy.PERSON_GEAR["armed"])
            self.assertEqual(sera["inventory"], [])  # a counted, emptied bag stays empty
            self.assertIs(reopened.world_state[equipment_economy.GEAR_WRITTEN], True)
            again = Path(directory) / "again.json"
            reopened.save_game(again)
            expected = reopened.serialize_game_state()
            third = make_session("Human")
            third.load_game(again)
            self.assertEqual(third.serialize_game_state(), expected)  # nothing written twice

    def test_an_old_save_writes_no_gear_on_a_body_already_searched(self):
        here = self.world["location"]
        self.world["npcs"] = [
            {"id": "npc_dead", "name": "Kalila", "role": "Muhafız", "location": here, "current_hp": 0,
             "combat_status": "dead", "searched": True},
            {"id": "npc_cold", "name": "Tobin", "role": "Muhafız", "location": here, "current_hp": 1,
             "combat_status": "unconscious", "searched": True},
            {"id": "npc_fresh", "name": "Orrin", "role": "Muhafız", "location": here, "current_hp": 0,
             "combat_status": "dead"},
        ]
        self.world.pop(equipment_economy.GEAR_WRITTEN, None)  # a save from before D-231
        self.world["currency"] = {"player": 0}  # D-207: the replaced town's people take their purses with them
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "old.json"
            self.session.save_game(old)
            reopened = make_session("Human")
            reopened.load_game(old)
            dead, cold, fresh = reopened.world_state["npcs"]
            self.assertNotIn("inventory", dead)  # its search already took all it carried: nothing new to loot
            self.assertNotIn("inventory", cold)
            self.assertEqual(len(_gear(fresh)), 1)  # never searched: the body still carries what the person carried
            self.assertIs(reopened.world_state[equipment_economy.GEAR_WRITTEN], True)

    def test_a_new_world_is_already_written(self):
        self.assertIs(self.world.get(equipment_economy.GEAR_WRITTEN), True)


class ABodyGivesItsGear(ThreePlaysTests):
    async def armed_corpse(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.world.setdefault("currency", {})["player"] = 0
        body = self.add_person("Kalila", "Muhafız", current_hp=0, combat_status="dead", name_known_to_player=True,
                               inventory=[{"item_id": "item_900001", "name": "Mızrak", "weapon_id": "spear"}])
        self.world["currency"][body["id"]] = 12
        return body

    async def test_a_body_search_takes_its_purse_and_its_gear(self):
        body = await self.armed_corpse()
        client = PlayClient(narration="Odada ceset yok.")
        out = await self.say("cesedini arıyorum; kesesindeki parayı ve üzerindeki eşyaları alıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertEqual(body["inventory"], [])
        self.assertIn("item_900001", [item.get("item_id") for item in self.world["inventory"] if isinstance(item, dict)])
        self.assertEqual(self.world["currency"]["player"], 12)
        self.assertEqual(self.world["currency"][body["id"]], 0)
        self.assertIn("12 bakır", out["narration"])
        self.assertIn("Mızrak", out["narration"])

    async def test_a_body_with_no_purse_still_gives_its_gear(self):
        body = await self.armed_corpse()
        self.world["currency"][body["id"]] = 0
        out = await self.say("cesedi arıyorum", PlayClient())
        self.assertIn("Mızrak", out["narration"])
        self.assertNotIn("işe yarar bir şey çıkmıyor", out["narration"])
        self.assertEqual(body["inventory"], [])

    async def test_a_second_search_finds_nothing_more(self):
        await self.armed_corpse()
        await self.say("cesedi arıyorum", PlayClient())
        bag = list(self.world["inventory"])
        out = await self.say("cesedi bir daha arıyorum", PlayClient())
        self.assertIn("kalmamış", out["narration"])
        self.assertEqual(self.world["inventory"], bag)


if __name__ == "__main__":
    unittest.main()
