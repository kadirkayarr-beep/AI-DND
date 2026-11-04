"""Dilim 1 Task 12: deterministic, read-only, NPC-scoped truth projections."""
import copy
import unittest

import truth_card


class TruthCard(unittest.TestCase):
    def setUp(self):
        self.npc = {"id": "barman", "name": "Marek", "role": "Barmen", "location": "inn"}
        self.world = {"location": "inn", "locations": {"inn": {"name": "Göl Hanı"}},
                      "npcs": [self.npc], "currency": {"player": 50}, "inventory": [],
                      "campaign_time": {"elapsed_seconds": 0},
                      "flags": {"turn_index": 4, "inn_room": {"place": "inn", "until": 86400},
                                "economic_ledger": {"operations": {"room": {
                                    "purpose": "room", "net_debit_cp": 50, "label": "Oda (bir gece)",
                                    "payee_id": "barman", "turn_index": 3}}}}}

    def test_card_lines_start_with_their_fixed_words(self):
        card = truth_card.narrator_view(self.world, npc=self.npc)
        for head in ("MOTOR GERÇEĞİ (salt okunur):", "kese: 50 bakır (0 altın 5 gümüş 0 bakır)",
                     "oda tutuldu: ", "açık teklif yok", "ödendi: Oda (bir gece), 50 bakır, Marek",
                     "fiyatlar (motorun; başka fiyat söyleme): bira 4 bakır"):
            self.assertIn(head, card)

    def test_npc_view_never_carries_another_npcs_business(self):
        self.world["flags"]["economic_ledger"]["operations"]["other"] = {
            "purpose": "gift", "net_debit_cp": 5, "label": "Osman hediyesi",
            "payee_id": "osman", "turn_index": 4}
        card = truth_card.npc_view(self.world, npc=self.npc, held_out_cp=3,
                                   this_turn=[("osman", "Osman parayı geri çevirdi"), (None, "Bira içildi")])
        for absent in ("kese:", "çanta:", "Osman", "çıkışlar", "Bira içildi"):
            self.assertNotIn(absent, card)
        self.assertIn("oyuncunun sana uzattığı: 3 bakır", card)
        self.assertIn("sana ödendi: Oda (bir gece), 50 bakır", card)

    def test_npc_view_is_filtered_before_the_budget(self):
        ledger = self.world["flags"]["economic_ledger"]["operations"]
        for i in range(40):
            ledger[str(i)] = {"purpose": "gift", "net_debit_cp": 5, "label": "Osman " * 50,
                              "payee_id": "osman", "turn_index": 4}
        card = truth_card.npc_view(self.world, npc=self.npc)
        self.assertIn("sana ödendi: Oda (bir gece), 50 bakır", card)
        self.assertNotIn("Osman", card)

    def test_cards_are_deterministic_and_do_not_write_world(self):
        before = copy.deepcopy(self.world)
        for view in (truth_card.narrator_view, truth_card.npc_view):
            self.assertEqual(view(self.world, npc=self.npc), view(self.world, npc=self.npc))
        self.assertEqual(self.world, before)

    def test_budget_holds_for_long_turkish_mandatory_fields(self):
        self.npc["name"] = "ğüşıöç uzun isim " * 80
        self.world["locations"]["inn"]["name"] = "ğüşıöç uzun yer " * 80
        self.world["flags"]["counter_offer_v1"] = {"npc_id": "barman", "key": "bira", "seq": 0, "turn": 4}
        notes = [("barman", "ğüşıöç uzun not " * 80)] * 4
        for view in (truth_card.narrator_view(self.world, npc=self.npc, this_turn=notes),
                     truth_card.npc_view(self.world, npc=self.npc, held_out_cp=5, this_turn=notes)):
            self.assertLessEqual(len(view.encode("utf-8")), 600)
            self.assertIn("açık teklif:", view)
            self.assertIn("(kısaltıldı:", view)

    def test_npc_receives_only_its_own_turn_notes(self):
        card = truth_card.npc_view(self.world, npc=self.npc,
                                   this_turn=[("barman", "Sana ödeme yapıldı"), ("other", "Başka sır")])
        self.assertIn("bu tur: Sana ödeme yapıldı", card)
        self.assertNotIn("Başka sır", card)

    def test_no_room_is_shown_to_a_guest(self):
        guest = {"id": "guest", "name": "Oren", "role": "Yolcu", "location": "inn"}
        card = truth_card.npc_view(self.world, npc=guest)
        self.assertNotIn("oda tutuldu", card)
        self.assertNotIn("fiyatların", card)
from dataclasses import replace
import json
from unittest.mock import patch
import game
import bold_acts
import npc_statements
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class TruthCardJourneys(JourneyCase):
    async def test_speech_note_and_narrator_prompt_carry_the_card(self):
        results = await self.run_scenario(load_scenario(SCENARIO_DIR / "26_truth_card_price.json"))
        self.assertEqual([r.status for r in results], ["pass"] * 3, results)
        self.assertIn("MOTOR GERÇEĞİ", self.last_narrator_input)
        self.assertIn("KOMPAKT", self.last_narrator_input)
        # The existing parsed JSON slice must stay JSON after inserting the card.
        text = self.last_narrator_input
        start = text.index("KOMPAKT")
        fragment = text[start:].split("\n", 1)[1].split("VERIFIED LORE", 1)[0].strip()
        json.loads(fragment)

    async def test_paid_room_reaches_the_next_narrator(self):
        scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        results = await self.run_scenario(replace(scenario, steps=scenario.steps[:4]))
        self.assertEqual(results[3].status, "pass", results)
        self.assertIn("oda tutuldu", self.last_narrator_input)


class CounterRecordedWord(unittest.TestCase):
    def test_the_counters_price_line_is_the_persons_own_recorded_word(self):
        session = game.create_session(seed=7)
        world = session.world_state
        npc = {"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"], "current_hp": 10}
        world["npcs"] = [npc]
        world["currency"] = {"player": 100, "barman": 0}
        with patch("game.ollama.chat", side_effect=AssertionError("No real model")):
            session.run_player_turn("bir bira alayım")
        self.assertEqual(npc_statements.claim_support(world, npc, "bira 4 bakır demiştin")["status"], "supported")
class InteractionCard(unittest.TestCase):
    def test_interaction_shortcut_carries_the_narrator_card(self):
        session = game.create_session(seed=7)
        npc = {"id": "barman", "name": "Marek", "role": "Barmen", "location": session.world_state["location"]}
        session.world_state["npcs"] = [npc]
        captured = []
        def chat(**kwargs):
            captured.extend(m["content"] for m in kwargs["messages"])
            return {"message": {"content": json.dumps({"narration": "Bekliyor.", "world_updates": {}, "lore_claims": []})}}
        token = game._ACTIVE_SESSION.set(session)
        try:
            with patch("game.ollama.chat", side_effect=chat):
                game.ask_dungeon_master([], "Bekliyorum", npc_target=npc,
                                        action_result={"action": "interaction", "operation": "observe"})
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertTrue(captured)
        self.assertIn("MOTOR GERÇEĞİ", "\n".join(captured))
class TruthCardEdgeCases(TruthCard):
    def test_narrator_keeps_the_paid_room_when_player_steps_outside(self):
        self.world["location"] = "street"
        self.world["locations"]["street"] = {"name": "Sokak"}
        card = truth_card.narrator_view(self.world)
        self.assertIn("oda tutuldu: Göl Hanı", card)
        self.assertNotIn("oda tutulmadı", card)

    def test_expired_room_is_not_shown_as_held(self):
        self.world["campaign_time"]["elapsed_seconds"] = 86400
        self.assertIn("oda tutulmadı", truth_card.narrator_view(self.world))

    def test_thirty_items_three_payments_and_long_exits_stay_inside_budget(self):
        self.world["inventory"] = [f"Türkçe eşya {i}" for i in range(30)]
        self.world["locations"]["inn"]["exit_location_id"] = "exit"
        self.world["locations"]["exit"] = {"name": "Çıkış yeri " * 100}
        ledger = self.world["flags"]["economic_ledger"]["operations"]
        for i in range(2):
            ledger[str(i)] = {"purpose": "gift", "net_debit_cp": 1, "label": f"Hediye {i}", "payee_id": "barman", "turn_index": 3}
        before = copy.deepcopy(self.world)
        card = truth_card.narrator_view(self.world, npc=self.npc)
        self.assertLessEqual(len(card.encode("utf-8")), 600)
        self.assertNotIn("Çıkış yeri", card)
        self.assertIn("kese: 50 bakır", card)
        self.assertIn("oda tutuldu:", card)
        self.assertIn("açık teklif yok", card)
        self.assertEqual(self.world, before)
    def test_hidden_identity_never_appears(self):
        self.npc.update(name="GİZLİ_AD_883", name_known_to_player=False,
                        role="GİZLİ_ROL_884", role_known_to_player=False)
        for view in (truth_card.narrator_view(self.world, npc=self.npc), truth_card.npc_view(self.world, npc=self.npc)):
            self.assertNotIn("GİZLİ_AD_883", view)
            self.assertNotIn("GİZLİ_ROL_884", view)

    def test_unnamed_npc_does_not_receive_everybodys_payments_or_turn_notes(self):
        card = truth_card.npc_view(self.world, npc={"role": "Yolcu"}, this_turn=[(None, "ÖZEL_NOT_885")])
        self.assertNotIn("Oda (bir gece)", card)
        self.assertNotIn("ÖZEL_NOT_885", card)

    def test_old_payment_without_a_label_is_not_counted_twice_in_text(self):
        self.world["flags"]["economic_ledger"]["operations"]["room"]["label"] = None
        card = truth_card.npc_view(self.world, npc=self.npc)
        self.assertIn("sana ödendi: ödeme 50 bakır, 1 tur önce", card)
        self.assertNotIn("ödeme 50 bakır, 50 bakır", card)

    def test_optional_details_drop_before_mandatory_facts(self):
        lines = [truth_card._Line("başlık", "MOTOR GERÇEĞİ (salt okunur):", 4),
                 truth_card._Line("kese", "kese: 50 bakır", 1),
                 truth_card._Line("açık teklif", "açık teklif: bira 4 bakır", 3),
                 truth_card._Line("çıkışlar", "çıkışlar: " + "uzun çıkış " * 100),
                 truth_card._Line("ödemeler", "ödendi: A; B; C", shorter="ödendi: A"),
                 truth_card._Line("çanta", "çanta: bir, iki, üç", shorter="çanta: bir")]
        card = truth_card._fit(lines, 150)
        self.assertNotIn("çıkışlar", card)
        self.assertIn("ödendi: A; B; C", card)
        self.assertIn("çanta: bir, iki, üç", card)
        self.assertIn("kese: 50 bakır", card)
        self.assertNotIn("kısaltıldı", card)


class ScopedSpeechJourney(JourneyCase):
    async def test_the_whole_speech_input_to_b_has_none_of_as_payment(self):
        scenario = load_scenario(SCENARIO_DIR / "26_truth_card_price.json")
        setup = copy.deepcopy(scenario.setup)
        setup["npcs"].append({"id": "osman", "name": "Osman", "role": "Barmen", "current_hp": 10})
        setup["currency"]["osman"] = 0
        buy = replace(scenario.steps[0], command="/item shop_buy osman bira 3 0 12", expect={"kese": 88})
        speak = replace(scenario.steps[1], expect={"konusmaya_giden": ["kayıtta sana ödeme yok"]})
        results = await self.run_scenario(replace(scenario, setup=setup, steps=(buy, speak)))
        self.assertEqual([r.status for r in results], ["pass", "pass"], results)
        self.assertNotIn("12 bakır", self.last_speech_input)
        self.assertNotIn("Osman'e", self.last_speech_input)
        self.assertNotIn("Osman'a", self.last_speech_input)