"""Dilim 1 Task 12: deterministic, read-only, NPC-scoped truth projections."""
import copy
import unittest

import equipment_economy
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

    def test_someone_with_nothing_in_the_engine_to_sell_or_make_is_told_so(self):
        """Owner decision F: a smith says "körüğü yakıyorum" but no forging exists; the card says what is real."""
        nothing = "motorda sattığın ya da yaptığın bir şey yok"
        smith = {"id": "smith", "name": "Oren", "role": "Demirci", "location": "inn"}
        self.world["npcs"].append(smith)
        self.assertIn(nothing, truth_card.npc_view(self.world, npc=smith))
        self.assertNotIn(nothing, truth_card.npc_view(self.world, npc=self.npc))  # the barman sells: his prices stand
        self.assertNotIn(nothing, truth_card.narrator_view(self.world, npc=smith))  # it is the person's own card only
        self.world["shops"] = [{"id": "shop_forge", "shopkeeper_id": "smith", "location": "inn"}]
        self.assertNotIn(nothing, truth_card.npc_view(self.world, npc=smith))  # a shop's wares are sold through the engine

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


# --- Dilim 2, Task 15: the card's hand line, the quests and trails that fit, and the budget's one contract ---------
import economic_actions
import quest_log
import refusals
import world_happenings
import world_threads
from api.tests.test_trails import TrailCase

_LONG = "uzun ğüşıöç adlı "


def crowd(world, character, *, trails, jobs, items, long_names, open_room_card=False, counterparty_label=None):
    """Load a played world the way a long game does: known trails to live jobs, running quest rows, a full bag, and
    (``open_room_card``) Dilim 1's room card open to the barman here (its active line says the money has not moved).
    Only the product's own records are written; nothing here reads the card."""
    state = world_threads.view(world) or world_threads.ensure(world)
    base = state["threads"][0]
    live = list(state["threads"])                     # the town's live jobs first: the save caps how many may be open
    for i in range(1, trails - len(live) + 1):
        job = copy.deepcopy(base)
        for key in ("offered_at", "offered_turn", "offer_line", "offer_line_turn", "owner_npc_id", "quest_id",
                    "accepted_at", "accepted_turn", "recipient_npc_id"):
            job.pop(key, None)
        job.update(thread_id=f"thread_{900 + i:03d}", status="open")
        state["threads"].append(job)
        live.append(job)
    for i in range(1, trails + 1):
        target = live[i - 1]
        if long_names:
            world["locations"][target["place_id"]]["name"] = ("Rıhtım ardındaki " + _LONG * 6).strip()
        line = (f"İz {i}: " + ("liman yolunda " + _LONG * 4 if long_names else "yol"))
        line = line.encode("utf-8")[:world_happenings.MAX_LINE_BYTES].decode("utf-8", errors="ignore").strip()
        world_happenings.write(state, base, "delivered", i, line, known=True, next_thread_id=target["thread_id"])
    for i in range(1, jobs + 1):
        title = f"Görev {i}" + (" " + _LONG * 5 if long_names else "")
        world.setdefault("quests", []).append({   # an older (legacy) quest record, as the save accepts one
            "quest_id": f"crowd_{i}", "title": title.strip(), "description": "Kalabalık bir günün işi.",
            "giver_npc_id": None, "status": "accepted", "created_turn": 0, "accepted_turn": 0, "updated_turn": 0,
            "objectives": [{"objective_id": f"crowd_{i}_go", "description": "Oraya git.", "type": "visit_location",
                            "target": "Liman", "status": "active", "required_count": 1, "progress": 0}]})
    world["inventory"] = [f"Eşya {i}" + (" " + _LONG * 3 if long_names else "") for i in range(items)]
    world["equipment"] = {"main_hand": None, "off_hand": None}
    if open_room_card:
        here = world["location"]
        world["npcs"] = [n for n in world.get("npcs", []) if n.get("id") != "barman"] + [
            {"id": "barman", "name": counterparty_label or "Marek", "role": "Barmen", "location": here,
             "current_hp": 10}]
        world.setdefault("currency", {})["player"] = max(world.get("currency", {}).get("player", 0), 100)
        proposal = economic_actions.EconomicProposal(
            purpose="room", recipient_id="barman", source_id=None, item_id=None, count=1, amount_cp=None, tip_cp=0,
            tender_cp=None, dependency="base_required", source_action_id="crowd-room", text_span=None)
        result = economic_actions.prepare_from_panel(
            economic_actions.EconomicState(world=world, character=character), proposal, campaign_id="crowd",
            actor_id="player", turn_index=(world.get("flags") or {}).get("turn_index", 0))
        assert result.status == "prepared", (result.status, result.reason_code)
    return world


class CardRows(TrailCase):
    """Task 15: narrator and NPC cards on a real campaign's world (scenario 19d's setup)."""

    def crowded_world(self, **load):
        return crowd(copy.deepcopy(self.world), self.session.character, **load)

    def test_card_budget_drops_trails_before_the_refusal(self):
        world = self.crowded_world(trails=6, jobs=4, items=30, long_names=True)   # quest_log rows + bag, no hand
        note = (None, refusals.text_for("nothing_to_draw", have="yok"))
        card = truth_card.narrator_view(world, this_turn=[note], max_bytes=600)
        self.assertLessEqual(len(card.encode("utf-8")), 600)
        self.assertIn("olmadı:", card)
        self.assertIn("elin boş", card)                                   # required line survives
        self.assertNotIn("izler:", card)                                  # first to go
        roomy = truth_card.narrator_view(self.crowded_world(trails=1, jobs=1, items=2, long_names=False), this_turn=[note])
        self.assertIn("izler:", roomy); self.assertIn("görevlerin:", roomy)

    def test_a_long_active_offer_and_several_refusals_follow_d33(self):
        # J-014 #6 (tasarım karar 59): Dilim 1 D33 priority is active deal > this turn's result > person group
        world = self.crowded_world(trails=6, jobs=4, items=30, long_names=True, open_room_card=True)   # a room card is open (active deal)
        first = (None, refusals.text_for("nothing_to_draw", have="yok"))
        second = (None, "olmadı: " + refusals.text_for("which_enemy", names="Haydut mu, Okçu mu"))
        plain = (None, "bu tur: Bira içildi")
        card = truth_card.narrator_view(world, this_turn=[first, plain, second], max_bytes=600)
        lines = card.splitlines()
        self.assertLessEqual(len(card.encode("utf-8")), 600)
        self.assertTrue(any("para henüz el değiştirmedi" in line for line in lines))          # the active deal stays
        self.assertIn(first[1], card)                                                         # the first refusal stays, whole
        self.assertEqual([l for l in lines if l.startswith("izler:")], [])                     # optional lines go before any required one
        self.assertLess(card.index(first[1]), card.index(plain[1]) if plain[1] in card else len(card))   # refusals lead the group
        self.assertEqual(truth_card.narrator_view(world, this_turn=[first, plain, second], max_bytes=600), card)   # deterministic
        # extreme: eight refusal notes (~60 bytes each) next to the open card cannot all fit; the newest drop first, named, never silent
        many = [(None, "olmadı: " + refusals.text_for("which_enemy", names=f"Haydut {i} mu, Okçu {i} mu")) for i in range(8)]
        with self.assertLogs(level="WARNING") as logged:
            cut = truth_card.narrator_view(world, this_turn=many, max_bytes=600)
        lines = cut.splitlines()
        self.assertLessEqual(len(cut.encode("utf-8")), 600)
        self.assertTrue(any("para henüz el değiştirmedi" in line for line in lines))          # the active deal still stays
        self.assertIn(many[0][1], cut)                                                        # the first refusal is the last to go
        self.assertNotIn(many[-1][1], cut)                                                    # the newest went first
        self.assertTrue(lines[-1].startswith("(kısaltıldı: ") and "olmadı notu" in lines[-1], lines[-1])
        self.assertTrue(any("olmadı notu" in entry for entry in logged.output))

    def test_a_long_counterparty_name_keeps_the_money_has_not_moved_words(self):
        # tasarım §3e (2): a long value is shortened, the active deal's own words are not
        world = self.crowded_world(trails=0, jobs=0, items=0, long_names=False, open_room_card=True,
                                   counterparty_label="Han Sahibi " + _LONG * 12)
        card = truth_card.narrator_view(world, this_turn=[(None, refusals.text_for("nothing_to_draw", have="yok"))],
                                        max_bytes=300)
        self.assertLessEqual(len(card.encode("utf-8")), 300)
        self.assertTrue(any(line.startswith("açık teklif: ") and line.endswith("para henüz el değiştirmedi")
                            for line in card.splitlines()), card)

    def test_a_held_weapon_is_named_on_the_narrators_card(self):
        world = self.crowded_world(trails=0, jobs=0, items=0, long_names=False)
        world["inventory"] = ["Greatsword"]
        equipment_economy.materialize(world)
        world["equipment"]["main_hand"] = world["inventory"][0]["item_id"]
        self.assertIn("elinde: Greatsword", truth_card.narrator_view(world))
        self.assertNotIn("elin boş", truth_card.narrator_view(world))

    async def world_with_town_errand_and_sword_in_hand(self):
        await self.accept()
        self.world["inventory"].append("Longsword")
        equipment_economy.materialize(self.world)
        self.world["equipment"]["main_hand"] = next(i["item_id"] for i in self.world["inventory"]
                                                    if i.get("name") == "Longsword")
        self.save()
        return self.world

    async def test_npc_view_carries_only_that_npcs_job_and_no_hand(self):
        world = await self.world_with_town_errand_and_sword_in_hand()
        tuna = self.npc(self.tuna)
        stranger = self.add_npc_at(world["location"], "stranger")
        seen = truth_card.npc_view(world, npc=tuna)
        self.assertIn("görevlerin:", seen); self.assertNotIn("elinde:", seen); self.assertNotIn("elin boş", seen)
        self.assertNotIn("görevlerin:", truth_card.npc_view(world, npc=stranger))
        self.assertNotIn("görevlerin:", truth_card.npc_view(world, npc={"role": "Yolcu"}))   # nameless: nobody's job
        # J-014 #8 (tasarım karar 61): a bystander where the trail points and a private letter's trail
        await self.fresh_campaign()
        await self.deliver()
        await self.accept_sealed_letter(); await self.read_the_letter()
        follow = self.follow_on_thread()
        bystander = self.add_npc_at(follow.get("target_place_id") or follow["place_id"], npc_id="bystander")
        self.assertEqual([l for l in truth_card.npc_view(self.world, npc=bystander).splitlines()
                          if l.startswith(("izler:", "görevlerin:"))], [])
        giver = self.npc(self.delivered_thread()["owner_npc_id"])
        mektup = f"izler: {self.trail('mektup')['what']} → {self.trail('mektup')['where']}"
        self.assertNotIn(mektup, truth_card.npc_view(self.world, npc=giver, max_bytes=4000))
        sender = self.npc(self.letter_thread()["owner_npc_id"])
        self.assertIn(mektup, truth_card.npc_view(self.world, npc=sender, max_bytes=4000))