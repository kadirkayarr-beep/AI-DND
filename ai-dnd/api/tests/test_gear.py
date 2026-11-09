"""Gear (Dilim 2, Task 14; item 39): an empty hand draws the first weapon in the bag as part of the attack, Ready picks
its weapon the same way instead of looking for the word sword, and a weapon the player does not own is a punch that
says so. The hand changes only through the existing owner (equipment_rules), so save and Undo carry it."""
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import action_economy
import equipment_economy
import game
import gear
import refusals
import weapon_catalog
from api.tests import test_combat_lifecycle as lifecycle
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, read_observed
from api.tests.journeys.schema import load_scenario

SCENARIOS = SCENARIO_DIR


def _world(bag, main=None, off=None):
    w = {"location": "inn", "flags": {"turn_index": 0}, "inventory": list(bag),
         "equipment": {"main_hand": main, "off_hand": off}, "currency": {"player": 0}, "item_sequence": 0,
         "npcs": [], "ground_items_by_location": {"inn": []}}
    equipment_economy.materialize(w)
    return w


w_package_c = None
w_no_weapons = None


class GearRules(JourneyCase):
    def setUp(self):
        global w_package_c, w_no_weapons
        w_package_c = _world(["Greatsword", "Ağır Tatar Yayı & 20 Ok", "Macera Çantası"])
        w_no_weapons = _world(["Macera Çantası"])

    def world(self, bag, main=None, off=None):
        return _world(bag, main, off)

    def item_id(self, w, name):
        return next(item["item_id"] for item in w["inventory"] if item["name"] == name)

    def fight_session(self, bag):
        session, npc = lifecycle.ready()
        session.world_state["inventory"] = list(bag)
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(session.world_state)
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        self._npc = npc
        return session

    def enemy_moves_trigger(self, session):
        return {"event": "actor_moves", "actor_id": self._npc["id"]}

    def ready_record(self, session):
        return action_economy.ensure(session)["player"]["ready"]

    # Step 1: the catalog knows both package C weapons.
    def test_the_catalog_knows_package_c(self):
        self.assertEqual(weapon_catalog.lookup("Greatsword")["weapon_id"], "greatsword")
        crossbow = weapon_catalog.lookup("Ağır Tatar Yayı & 20 Ok")
        self.assertEqual((crossbow["weapon_id"], crossbow["ammunition_type"]), ("heavy_crossbow", "bolt"))

    def test_attack_with_empty_hand_draws_the_first_melee_weapon(self):
        choice = gear.attack_weapon(w_package_c)               # Greatsword and a crossbow in the bag, hands empty
        self.assertEqual((choice.kind, choice.item["name"]), ("drawn", "Greatsword"))
        self.assertEqual(w_package_c["equipment"], {"main_hand": choice.item["item_id"], "off_hand": None})
        crossbow_first = self.world(["Ağır Tatar Yayı & 20 Ok", "Greatsword"])
        self.assertEqual(gear.attack_weapon(crossbow_first).item["name"], "Greatsword")   # melee first, not bag first
        self.assertEqual(gear.attack_weapon(crossbow_first).kind, "held")                 # now it is in hand

    def test_ready_attack_uses_gear_not_the_word_sword(self):
        session = self.fight_session(bag=["Gürz"])                        # EK 5 T8: a mace, no longsword, hands empty
        action_economy.prepare_ready(session, "player", trigger=self.enemy_moves_trigger(session),
                                     response={"kind": "attack", "target_id": self._npc["id"]})
        self.assertEqual(self.ready_record(session)["response"]["kind"], "attack")   # no CombatRequestError("no_weapon")
        session = self.fight_session(bag=[])                              # nothing at all: still a punch, still no no_weapon
        action_economy.prepare_ready(session, "player", trigger=self.enemy_moves_trigger(session),
                                     response={"kind": "attack", "target_id": self._npc["id"]})
        self.assertEqual(self.ready_record(session)["response"]["kind"], "attack")

    def test_a_weapon_not_owned_is_a_punch_that_says_so(self):
        choice = gear.attack_weapon(w_no_weapons, requested_name="kılıç")
        self.assertEqual((choice.kind, choice.missing, choice.item), ("unarmed", "Kılıç", None))  # the player-facing label
        self.assertEqual(refusals.text_for("weapon_not_owned", weapon=choice.missing), "Kılıç yok; yumrukla vuruyorsun.")

    def test_draw_two_handed_clears_the_off_hand(self):
        w = self.world(bag=["Greatsword", "Kalkan"], main=None, off="Kalkan")
        self.assertEqual(w["equipment"]["off_hand"], self.item_id(w, "Kalkan"))
        result = gear.draw(w, self.item_id(w, "Greatsword"))
        self.assertEqual((result.status, result.item["name"]), ("drawn", "Greatsword"))
        self.assertEqual(w["equipment"], {"main_hand": self.item_id(w, "Greatsword"), "off_hand": None})
        self.assertEqual(gear.draw(w, self.item_id(w, "Greatsword")).status, "already_held")

    def test_draw_refuses_what_is_not_a_weapon_or_not_in_the_bag(self):
        w = self.world(bag=["Greatsword", "Macera Çantası"], main=None, off=None)
        before = copy.deepcopy(w)
        self.assertEqual(gear.draw(w, self.item_id(w, "Macera Çantası")).status, "not_a_weapon")
        self.assertEqual(gear.draw(w, "item:not-there").status, "not_in_bag")
        self.assertEqual(w, before)                                       # nothing changed

    def test_a_weapon_named_in_the_attack_that_the_player_lacks_is_a_punch_told_to_both(self):
        session = self.fight_session(bag=["Macera Çantası"])
        session._turn_notes = []
        intent = game.normalize_intent({"intent": "attack", "action": "attack", "weapon_word": " kılıç ",
                                        "target": {"type": "npc", "reference": "Rakip"}, "completion": "completed",
                                        "confidence": 1}, "Rakibe kılıcımla saldırıyorum")
        self.assertEqual(intent["weapon_word"], "kılıç")
        with patch("game.roll_d20", return_value=15):
            result = game.execute_intent(intent, "Rakibe kılıcımla saldırıyorum", npc_target=self._npc)
        self.assertTrue(game._combat_narration(result).startswith("Kılıç yok; yumrukla vuruyorsun. "))
        self.assertEqual(session._turn_notes, [(None, "olmadı: Kılıç yok; yumrukla vuruyorsun.")])
        self.assertEqual(session.world_state["equipment"], {"main_hand": None, "off_hand": None})

    async def test_panel_attack_and_ready_work_with_an_unequipped_greatsword(self):
        results = await self.run_scenario(load_scenario(SCENARIOS / "05_greatsword.json"))   # markers removed in Step 4
        self.assertEqual([r.status for r in results], ["pass"] * 5, results)   # 2 draws and ends the turn, 4 is the readied blow
        self.assertEqual(self.last_observations[1]["elinde"], "Greatsword")
        self.assertTrue(results[1].narration.startswith("Çantandan çektiğin Greatsword ile vuruyorsun. "), results[1])

    def _package_c_fight(self, tail):
        data = json.loads((SCENARIOS / "05_greatsword.json").read_text(encoding="utf-8"))
        data["id"] = "05_gear_case"
        data["steps"] = [data["steps"][0],
                         {"combat_action": {"steps": [{"kind": "attack", "target_id": "bandit"}]},
                          "expect": {"savas": True, "elinde": "Greatsword"}},
                         tail]
        folder = Path(tempfile.mkdtemp())
        path = folder / "05_gear_case.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return load_scenario(path)

    async def test_undo_returns_the_empty_hand(self):
        results = await self.run_scenario(self._package_c_fight({"undo": True, "expect": {"elinde": None}}))
        self.assertEqual([r.status for r in results], ["pass", "pass", "pass"], results)
        self.assertEqual(self.last_observations[1]["elinde"], "Greatsword")   # the attack drew it
        self.assertIsNone(read_observed(self, self.last_session_id)["elinde"])

    async def test_a_save_keeps_the_drawn_weapon(self):
        results = await self.run_scenario(self._package_c_fight({"reload": True, "expect": {"elinde": "Greatsword"}}))
        self.assertEqual([r.status for r in results], ["pass", "pass", "pass"], results)



if __name__ == "__main__":
    import unittest
    unittest.main()
