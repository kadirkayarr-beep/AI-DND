"""D-207 (owner decision C, 2026-11-15): every person gets an identity-bound purse when the town is built; an old save
writes it on its first load, always the same from the campaign seed. Then theft, the spoken economy and the equipment
economy all read the same purse, and undo and reload give it back as it was."""

from __future__ import annotations

import copy
import tempfile
import unittest
import uuid
from pathlib import Path

import bold_acts
import equipment_economy
from api.tests.test_species_traits import make_session
from api.tests.test_three_plays import ROGUE, PlayClient, ThreePlaysTests


class APersonsPurse(unittest.TestCase):
    def setUp(self):
        self.session = make_session("Human")
        self.world = self.session.world_state

    def person(self, name, role):
        npc = self.session.create_npc_from_ai({"name": name, "role": role, "location": self.world["location"]})
        self.assertIsNotNone(npc)
        return npc

    def test_the_purse_is_fixed_by_the_campaign_seed_and_who_they_are(self):
        npc = {"id": "npc_777", "role": "Muhafız"}
        purse = equipment_economy.person_purse(self.world, npc)
        self.assertEqual(purse, equipment_economy.person_purse(copy.deepcopy(self.world), dict(npc)))
        self.assertTrue(5 <= purse <= 40, purse)
        other = copy.deepcopy(self.world)
        other["scene_state"]["campaign_seed"] = "another campaign"
        ids = [f"npc_{n:03d}" for n in range(20)]
        self.assertNotEqual([equipment_economy.person_purse(self.world, {"id": i}) for i in ids],
                            [equipment_economy.person_purse(other, {"id": i}) for i in ids])

    def test_a_shopkeeper_opens_with_the_till(self):
        self.assertEqual(equipment_economy.person_purse(self.world, {"id": "npc_778", "role": "Shopkeeper"}), 1000)

    def test_a_new_person_has_a_written_purse(self):
        guard = self.person("Dorn", "Muhafız")
        self.assertEqual(self.world["currency"][guard["id"]], equipment_economy.person_purse(self.world, guard))

    def test_a_written_purse_is_never_written_again(self):
        npc = {"id": "npc_779", "role": "Muhafız"}
        self.world["currency"]["npc_779"] = 3
        equipment_economy.give_person_purse(self.world, npc)
        self.assertEqual(self.world["currency"]["npc_779"], 3)

    def test_every_path_reads_the_same_purse(self):
        guard = self.person("Dorn", "Muhafız")
        purse = self.world["currency"][guard["id"]]
        self.assertEqual(bold_acts._purse_of(self.world, guard), purse)  # theft
        equipment_economy.pay(self.world, guard["id"], "player", purse)  # the economy owners: wallets[id]
        self.assertEqual(self.world["currency"][guard["id"]], 0)
        with self.assertRaises(equipment_economy.EquipmentError):
            equipment_economy.pay(self.world, guard["id"], "player", 1)

    def test_an_old_save_writes_the_purses_on_its_first_load_and_only_then(self):
        here = self.world["location"]
        self.world["npcs"] = [
            {"id": "npc_old", "name": "Arven", "role": "Muhafız", "location": here},
            {"id": "npc_robbed", "name": "Sera", "role": "Muhafız", "location": here},
            {"id": "npc_dead", "name": "Kalila", "role": "Muhafız", "location": here, "current_hp": 0,
             "combat_status": "dead", "searched": True},
        ]
        self.world["currency"] = {"player": 40, "npc_robbed": 0}
        self.world.pop(equipment_economy.PURSE_WRITTEN, None)  # a save from before D-207
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "old.json"
            self.session.save_game(old)
            reopened = make_session("Human")
            reopened.load_game(old)
            world = reopened.world_state
            arven = world["npcs"][0]
            self.assertEqual(world["currency"]["npc_old"], equipment_economy.person_purse(world, arven))
            self.assertEqual(world["currency"]["npc_robbed"], 0)  # a counted, emptied purse stays empty
            self.assertNotIn("npc_dead", world["currency"])  # its search took all it carried
            self.assertEqual(world["currency"]["player"], 40)
            self.assertIs(world[equipment_economy.PURSE_WRITTEN], True)
            again = Path(directory) / "again.json"
            reopened.save_game(again)
            expected = reopened.serialize_game_state()
            third = make_session("Human")
            third.load_game(again)
            self.assertEqual(third.serialize_game_state(), expected)  # nothing written twice

    def test_a_new_world_is_already_written(self):
        self.assertIs(self.world.get(equipment_economy.PURSE_WRITTEN), True)


class AStolenPurseComesBackOnUndo(ThreePlaysTests):
    async def test_undo_and_reload_give_back_the_purse_the_old_save_wrote(self):
        await self.begin(ROGUE)
        self.world["npcs"].clear()
        self.add_person("Kavsim", "Muhafız", inventory=[])
        self.world["currency"] = {"player": 40}
        self.world.pop(equipment_economy.PURSE_WRITTEN, None)  # an old save, loaded for the first time
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "old.json"
            self.session.save_game(old)
            self.session.load_game(old)
            guard = next(npc for npc in self.world["npcs"] if npc["id"] == "npc_kavsim")
            written = self.world["currency"]["npc_kavsim"]
            self.assertEqual(written, equipment_economy.person_purse(self.world, guard))
            self.session.rng.seed(6)
            await self.say("kesesini fark ettirmeden çalmak için zar atıyorum")
            action = str(uuid.uuid4())
            stolen = await self.post_scene_turn(self.url, PlayClient(), {"message": "evet", "action_id": action})
            self.assertEqual(stolen.status_code, 200, stolen.text)
            taken = written - self.world["currency"]["npc_kavsim"]
            self.assertGreater(taken, 0, stolen.json().get("narration"))
            self.assertEqual(self.world["currency"]["player"], 40 + taken)  # out of the written purse, none made
            undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                          json={"action_id": str(uuid.uuid4()), "target_action_id": action})
            self.assertEqual(undone.status_code, 200, undone.text)
            self.assertEqual(self.world["currency"], {"player": 40, "npc_kavsim": written})
            saved = Path(directory) / "after_undo.json"
            self.session.save_game(saved)
            reloaded = make_session("Human")
            reloaded.load_game(saved)
            self.assertEqual(reloaded.world_state["currency"], {"player": 40, "npc_kavsim": written})


if __name__ == "__main__":
    unittest.main()
