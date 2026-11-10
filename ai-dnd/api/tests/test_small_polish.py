"""Task 36 polish: Turkish words where the player read English or a raw code, and two small world rules."""
import copy
import unittest
from unittest.mock import patch

import action_economy as ae
import bold_acts
import economic_actions
import game
import monk_features
import world_happenings
import world_reactions
from api.tests.test_combat_lifecycle import ready


class AGoodsDeclineIsToldInTurkish(unittest.TestCase):
    def test_a_counter_trade_of_goods_declined_today_says_why_in_turkish(self):
        session = game.create_session()
        world = session.world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"],
                          "current_hp": 10}]
        world["currency"] = {"player": 500}
        economic_actions.record_decline(world, "barman", "goods:bira", 4, day=economic_actions.game_day(world),
                                        turn=0)
        before = copy.deepcopy(world)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = session.run_player_turn("/item shop_buy barman bira 1 0 4")
        self.assertEqual(result["action_result"]["reason"], "npc_declined")
        self.assertNotIn("npc_declined", result["narration"])
        self.assertIn("Satıcı bugün bunu sana satmak istemiyor.", result["narration"])
        self.assertEqual(world, before)


class FightWordsAreTurkish(unittest.TestCase):
    def test_the_resolved_steps_use_the_turkish_terms(self):
        session, _ = ready()
        text = ae.resolved_narration(session, [
            {"kind": "second_wind", "result": {"healing": 7, "moved_ft": 10, "uses_remaining": 1}},
            {"kind": "action_surge", "result": {}},
            {"kind": "convert_spell_slot", "result": {"slot_level": 1, "points_gained": 2}},
            {"kind": "move", "distance_ft": 10},
            {"kind": "dash", "movement_added_ft": 30},
        ])
        for part in ("Bonus eylem ile İkinci Nefes kullanırsın: 7 can puanı kazanırsın ve 10 fit ilerlersin; "
                     "kalan kullanım: 1.",
                     "Eylem Atılımı ile bu tur bir ek eylem kazanırsın (Büyü eylemi hariç).",
                     "Bir 1. seviye büyü yuvasını 2 Büyücülük Puanı değerine dönüştürürsün; "
                     "Eylem veya Bonus eylem harcanmaz.",
                     "10 fit ilerlersin.", "Bu tur 30 fit daha hareket edebilirsin."):
            self.assertIn(part, text)
        for english in ("Bonus Action", "Second Wind", "Action Surge", "Magic", "Sorcery Points", "feet"):
            self.assertNotIn(english, text)

    def test_the_monk_moves_use_the_turkish_terms(self):
        session, _ = ready()
        patient = monk_features.narration(session, {"kind": "patient_defense", "result": {"dodge": True}})
        wind = monk_features.narration(session, {"kind": "step_of_the_wind", "result": {"movement_added_ft": 30}})
        self.assertEqual(patient, "Bonus eylem ile Sabırlı Savunma: Disengage ve Dodge.")
        self.assertEqual(wind, "Bonus eylem ile Rüzgâr Adımı: bu tur 30 fit daha hareket edebilirsin.")


class AnUnnamedRivalReadsRight(unittest.TestCase):
    def test_a_rival_whose_name_is_unknown_is_not_called_a_name(self):
        session, known = ready()
        known.update(name="Marek", name_known_to_player=True)
        stranger = session.create_npc_from_ai({"name": "Doran", "role": "Kervancı", "location": "tavern"})
        stranger.update(name_known_to_player=False, role_known_to_player=True)
        stranger.pop("label_shows_trait", None)
        text = session._enemy_exchange_text([
            {"actor_id": stranger["id"], "outcome": "miss"},
            {"actor_id": stranger["id"], "outcome": "critical_hit", "damage": 4},
            {"actor_id": known["id"], "outcome": "hit", "damage": 3},
        ], named=True)
        self.assertNotIn("adlı rakibinin", text.replace("Marek adlı rakibinin", ""))
        self.assertIn("Bir kervancı karşı saldırıya geçer; seni ıskalar.", text)
        self.assertIn("Bir kervancı karşı saldırıya geçer; kritik bir vuruşla sana isabet eder; 4 hasar alırsın.",
                      text)
        self.assertIn("Marek adlı rakibinin karşı saldırısı sana isabet eder; 3 hasar alırsın.", text)


class TheRumourOfABlowReadsRight(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session()
        self.world = self.session.world_state
        here = self.world["location"]
        self.victim = {"id": "victim", "name": "Doran", "role": "Kervancı", "location": here, "current_hp": 8,
                       "max_hp": 8, "name_known_to_player": False, "role_known_to_player": False,
                       "visible_trait": "bakır tokalı"}
        self.world["npcs"] = [self.victim]

    def told_elsewhere(self, deed):
        speaker = {"id": "speaker", "name": "Ilyra", "role": "Satıcı", "location": self.world["location"],
                   "current_hp": 5, "max_hp": 5}
        self.world["npcs"].append(speaker)
        deed.update(location="far_away", heard=["speaker"], witnesses=[], told=[])
        self.victim["location"] = "far_away"
        return " ".join(world_reactions._overheard(self.session))

    def test_an_unknown_person_set_upon_is_in_the_genitive_and_the_rumour_is_hearsay(self):
        bold_acts.attacked(self.session, self.victim)
        deed = self.world["flags"]["deeds"][-1]
        self.assertEqual(deed["text"], "Bakır tokalı birinin üzerine yürüdü")
        self.assertIn("“Biri bakır tokalı birinin üzerine yürümüş, duydun mu?”", self.told_elsewhere(deed))

    def test_a_known_name_takes_the_apostrophe(self):
        self.victim.update(name="Marek", name_known_to_player=True)
        bold_acts.attacked(self.session, self.victim)
        deed = self.world["flags"]["deeds"][-1]
        self.assertEqual(deed["text"], "Marek'in üzerine yürüdü")
        self.assertIn("“Biri Marek'in üzerine yürümüş, duydun mu?”", self.told_elsewhere(deed))


class AFallenMessengerDoesNotWalkAway(unittest.TestCase):
    def caller(self, **state):
        session = game.create_session()
        world = session.world_state
        npc = {"id": "ulak", "name": "Ulak", "role": "Ulak", "caller_of": "link_001", "location": world["location"],
               "came_from": "elsewhere", "leaves_turn": 0, "current_hp": 5, "max_hp": 5, **state}
        world["npcs"] = [npc]
        lines = world_happenings.callers_leave(session, 10 ** 9)
        return npc, lines, world["location"]

    def test_a_messenger_at_zero_hit_points_stays_where_they_fell(self):
        npc, lines, here = self.caller(current_hp=0)
        self.assertEqual((npc["location"], npc.get("came_from"), lines), (here, "elsewhere", []))

    def test_an_unconscious_messenger_stays_where_they_fell(self):
        npc, lines, here = self.caller(combat_status="unconscious")
        self.assertEqual((npc["location"], npc.get("came_from"), lines), (here, "elsewhere", []))

    def test_a_standing_messenger_still_goes_back(self):
        npc, _, _ = self.caller()
        self.assertEqual(npc["location"], "elsewhere")


if __name__ == "__main__":
    unittest.main()
