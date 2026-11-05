"""Task 20 prerequisite: the unchanged scenario must reach a real engine skill check."""
from dataclasses import replace
from unittest.mock import patch

import game
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class HaggleProbe(JourneyCase):
    async def test_the_haggle_line_rolls_a_persuasion_check_here(self):
        scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        probe = replace(scenario, steps=scenario.steps[:2])
        replies = []
        original_post = self.http.post

        async def capture_post(*args, **kwargs):
            response = await original_post(*args, **kwargs)
            if str(args[0]).endswith("/turn") and response.status_code == 200:
                replies.append(response.json())
            return response

        with patch.object(self.http, "post", new=capture_post), patch.object(
                game, "apply_check_outcome_to_world_state",
                wraps=game.apply_check_outcome_to_world_state) as checks:
            results = await self.run_scenario(probe)
        self.assertEqual(results[0].status, "pass", results)
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[-1]["turn_outcome"]["action"], "skill_check", replies[-1]["turn_outcome"])
        self.assertTrue(checks.call_args_list, "No engine check outcome was applied")
        self.assertEqual(checks.call_args_list[-1].args[1]["skill"], "Persuasion")
import copy
import bold_acts
import economic_actions as ea
import money_owner
import shop_trade
from api.tests.test_spoken_decline import Spoken


class HaggleRules(Spoken):
    def haggle(self, success=True, skill="Persuasion", npc_id="barman"):
        return money_owner.haggle(self.s, self.npc(npc_id),
                                  {"skill": skill, "result": "BAŞARILI" if success else "BAŞARISIZ"})

    def test_a_successful_check_takes_ten_percent_off_the_room_once_a_day(self):
        self.assertEqual(self.prepare("room", "barman").status, "prepared")
        before = self.money()
        self.assertIn("oda artık 45 bakır", self.haggle())
        self.assertEqual(bold_acts.room_price(self.w, self.npc("barman")), 45)
        self.assertIsNone(self.haggle())
        self.assertEqual(sum(line["total_cp"] for line in self.prepared()[0]["lines"]), 45)
        self.assertEqual(self.money(), before)

    def test_a_cut_replaces_and_lasts_only_its_day(self):
        self.prepare("room", "barman")
        self.haggle()
        self.w.setdefault("campaign_time", {})["elapsed_seconds"] = 86400
        self.assertEqual(bold_acts.room_price(self.w, self.npc("barman")), 50)
        self.prepare("room", "barman")
        self.assertIn("45 bakır", self.haggle())
        self.assertEqual(bold_acts.room_price(self.w, self.npc("barman")), 45)

    def test_the_old_room_card_is_cancelled_by_the_new_price(self):
        self.prepare("room", "barman")
        [old] = self.prepared()
        self.haggle()
        self.assertEqual(self.w["flags"]["economic_offers"][old["offer_id"]]["status"], "cancelled")
        before = self.money()
        result = self.confirm(old, "old-haggle-card")
        self.assertEqual((result.status, result.net_debit_cp), ("refused", 0))
        self.assertEqual(self.money(), before)
        [new] = self.prepared()
        paid = self.confirm(new, "new-haggle-card")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 45))
        self.assertEqual(self.w["currency"]["player"], 55)

    def test_a_failed_check_keeps_the_price_and_says_so(self):
        self.prepare("room", "barman")
        before = copy.deepcopy(self.w)
        self.assertEqual(self.haggle(False), "İkna tutmadı: fiyat aynı, oda 50 bakır.")
        self.assertEqual(self.w, before)

    def test_the_counter_price_follows_the_cut(self):
        self.open_counter(amount=0, keep_change=False)
        self.assertIn("3 bakır", self.haggle())
        self.assertEqual(shop_trade.quote(self.w, "barman", "bira", 1)["unit_cp"], 3)
        self.commit_refused("price_changed", 4)
        shop_trade.commit(self.w, "barman", "bira", 1, 0, 3)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (97, 3))

    def test_room_words_and_tender_use_the_discounted_price(self):
        self.prepare("room", "barman")
        self.haggle()
        self.assertIn("45 bakır", bold_acts.room_note(self.npc("barman"), "oda", world=self.w))
        self.assertIn("45 bakır", bold_acts._room_asked(self.s, "oda ne kadar?")["narration"])
        self.hold_out("barman", 45, money_owner.Deal("room", None, False))
        answer = bold_acts._open_room(self.s, self.npc("barman"))
        self.assertIn("Gecelik 45 bakır", answer["line"])
        self.assertEqual(self.prepared()[0]["proposal"]["tender_cp"], 45)
        self.assertEqual(self.w["currency"]["player"], 100)
    def test_wrong_skill_person_or_no_offer_changes_nothing(self):
        before = copy.deepcopy(self.w)
        self.assertIsNone(self.haggle())
        self.assertEqual(self.w, before)
        self.prepare("room", "barman")
        before = copy.deepcopy(self.w)
        self.assertIsNone(self.haggle(skill="Athletics"))
        self.assertIsNone(self.haggle(npc_id="osman"))
        self.assertEqual(self.w, before)


class HaggleJourney(JourneyCase):
    async def test_scenario_03_all_steps_pass_at_the_discounted_price(self):
        scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        self.assertFalse(any(step.known_broken for step in scenario.steps))
        results = await self.run_scenario(scenario)
        self.assertEqual([r.status for r in results], ["pass"] * 6, results)