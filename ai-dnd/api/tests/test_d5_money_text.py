"""Wave 5 money-text items (d5-parametin): D-254, D-255, D-264, D-266, D-267, D-268.

Money stays safe both ways: no coin moves without its record, no backed money sentence leaves the line, and no
unbacked amount stays on it. No real model is called; rolls are injected.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import dialogue_runtime
import game
import pocket
import town_knowledge
import world_threads
from api.tests import test_campaign_api
from api.tests import test_coin_ask_persuasion as coin_ask
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town


class UnderItIsNoGold(unittest.TestCase):
    """D-254: 'altına/altında/altından' is 'under it', in town_knowledge as in pocket; with a figure before it, gold."""

    def setUp(self):
        self.s = game.create_session(seed=7)
        self.s.world_state["currency"] = {"player": 7}

    def test_under_the_table_is_not_coin_handed(self):
        for line in ("Al, şunu masanın altına koy.", "İşte, kapının altında bir iz var."):
            with self.subTest(line=line):
                self.assertEqual(town_knowledge.without_unbacked_money(line), line)

    def test_gold_with_a_figure_before_it_is_still_coin(self):
        for line in ("İşte on altından fazlası.", "Al, beş altın.", "Al, 3 altına say bunu."):
            with self.subTest(line=line):
                self.assertEqual(town_knowledge.without_unbacked_money(line), "")

    def test_pocket_reads_a_figure_before_altindan_as_gold_too(self):
        line = "Kesene on altından fazlası giriyor."
        self.assertEqual(pocket.without_false_purse(line, self.s.world_state), "")
        under = "Kesenden bir ip sarkıyor, ucu masanın altına düşüyor."
        self.assertEqual(pocket.without_false_purse(under, self.s.world_state), under)


class PurseSentenceThatMovesNoCoin(unittest.TestCase):
    """D-255: only a sentence that tells coin really moving into or out of the purse leaves the line."""

    def setUp(self):
        self.s = game.create_session(seed=7)
        self.s.world_state["currency"] = {"player": 7}

    def test_a_negative_sentence_stays(self):
        for line in ("Kesenden tek bir bakır bile çıkmıyor.", "Kesene bir gümüş bile girmedi.",
                     "Kesenden tek sikke eksilmez."):
            with self.subTest(line=line):
                self.assertEqual(pocket.without_false_purse(line, self.s.world_state), line)

    def test_metal_as_a_look_is_not_coin(self):
        line = "Kesene giden bir el görüyorsun; gümüş yüzüklü bir hırsız."
        self.assertEqual(pocket.without_false_purse(line, self.s.world_state), line)

    def test_coin_really_moving_still_leaves(self):
        for line in ("Kesenden bakır çıkmıyor; kesene on gümüş giriyor.", "Kesene gümüş dolu bir avuç giriyor.",
                     "Kesene gümüş yüzüklü bir el 5 bakır koyuyor.", "Kesene 20 bakır düşmüş."):
            with self.subTest(line=line):
                self.assertEqual(pocket.without_false_purse(line, self.s.world_state), "")


class LostRoll(coin_ask.Ask):
    def reply(self, spoken, *, success=False, amount=5, stage=None, text="bana biraz para ver hadi"):
        extra = {} if stage is None else {"stage": stage}
        return town_knowledge.settle_reply(self.w, self.npc("guest"), text, {"kind": "give", "amount_cp": amount},
                                           spoken, accept_job=lambda thread: None, persuade=self.roll(success),
                                           **extra)


class OnlyMoneyHandingLeaves(LostRoll):
    """D-266: on a lost roll only a sentence that hands money goes; a refusal opening with 'işte/al/tut' stays."""

    def test_a_refusal_opening_with_iste_al_or_tut_stays(self):
        for line in ("İşte bu yüzden sana para vermem.", "Tut dilini.", "Al başını git buradan."):
            with self.subTest(line=line):
                self.setUp()
                self.assertEqual(self.reply(f"Hmm. {line}")["spoken"], f"Hmm. {line}")

    def test_the_later_money_gate_keeps_the_refusal_too(self):
        # game._with_only_backed_money runs this on the same line after settle_reply, with no coin moved.
        line = "İşte bu yüzden sana para vermem."
        self.assertEqual(town_knowledge.without_unbacked_money(line), line)
        self.assertEqual(town_knowledge.without_unbacked_money("İşte beş bakır, fazlası yok."), "")

    def test_a_handing_still_leaves(self):
        for line in ("Al bakalım.", "Al, senin olsun.", "Tut şunu.", "Buyur.", "Al, beş bakır; fazlası yok.",
                     "İşte paran.", "Kesemi uzatıyorum."):
            with self.subTest(line=line):
                self.setUp()
                self.assertEqual(self.reply(f"Hmm. {line} Yolun açık olsun.")["spoken"], "Hmm. Yolun açık olsun.")


class TheSpokenSumDecides(LostRoll):
    """D-267: after a won roll, the sum the line speaks decides what goes, not the model's proposed figure."""

    def test_a_line_naming_another_sum_goes_even_when_the_proposal_matched(self):
        settled = self.reply("Al bakalım, şu beş bakırı al. Yolun açık olsun.", success=True, amount=10)
        self.assertEqual(settled["moved"], 10)
        self.assertEqual(settled["spoken"], "Yolun açık olsun.")
        self.assertIn("10", settled["note"])

    def test_a_line_naming_the_moved_sum_stays_even_when_the_proposal_differed(self):
        settled = self.reply("İşte on bakır. Yolun açık olsun.", success=True, amount=5)
        self.assertEqual(settled["moved"], 10)
        self.assertEqual(settled["spoken"], "İşte on bakır. Yolun açık olsun.")


class ReviewNegationOnlyInItsOwnClause(LostRoll):
    """Review (YÜKSEK): a 'no' elsewhere in the sentence does not keep a handing of money or the purse."""

    HANDINGS = ("Al şu parayı, ama bir daha vermem.", "Al bu parayı, bir daha gelmiyorsun buraya.",
                "Buyur paran, geri istemem.", "İşte paran, hayır deme.", "Al, bir avuç altın, daha fazlası yok.",
                "Al şu keseyi, kimseye söylemem.")
    REFUSALS = ("İşte bu yüzden sana para vermem.", "Tut dilini.")

    def test_a_lost_ask_drops_each_handing(self):
        for line in self.HANDINGS:
            with self.subTest(line=line):
                self.setUp()
                self.assertEqual(self.reply(f"Hmm. {line} Yolun açık olsun.")["spoken"], "Hmm. Yolun açık olsun.")

    def test_the_no_move_gate_drops_each_handing(self):
        # This gate holds coin only; the purse line with no coin ('Al şu keseyi…') is held by the lost ask above, as
        # it was before D-266.
        for line in self.HANDINGS[:-1]:
            with self.subTest(line=line):
                self.assertEqual(town_knowledge.without_unbacked_money(line), "")

    def test_the_refusals_still_stay(self):
        for line in self.REFUSALS:
            with self.subTest(line=line):
                self.setUp()
                self.assertEqual(self.reply(f"Hmm. {line}")["spoken"], f"Hmm. {line}")
                self.assertEqual(town_knowledge.without_unbacked_money(line), line)


class ReviewAnotherMetalWithoutAFigure(LostRoll):
    """Review (ORTA): after a won roll, a handing that names a metal the engine did not pay goes, figure or not."""

    def test_gold_or_silver_with_no_figure_goes(self):
        for line in ("Al, bir avuç altın.", "Kesesinden bir avuç altın çıkarıp uzatıyor.", "Al, birkaç gümüş."):
            with self.subTest(line=line):
                self.assertEqual(town_knowledge._without_other_sum(f"{line} Gülümsüyor.", 5), "Gülümsüyor.")

    def test_copper_or_bare_coin_with_no_figure_stays(self):
        for line in ("Al, biraz bakır.", "Al, paran burada.", "Al bakalım."):
            with self.subTest(line=line):
                self.assertEqual(town_knowledge._without_other_sum(line, 5), line)


class StageDirectionHanding(LostRoll):
    """D-264: the stage direction goes through the same handing cleanup as the spoken line."""

    def test_a_won_roll_takes_another_sum_off_the_stage(self):
        settled = self.reply("Al bakalım.", success=True, stage="Beş bakır uzatıyor. Gülümsüyor.")
        self.assertEqual((settled["moved"], settled["stage"]), (10, "Gülümsüyor."))

    def test_a_won_roll_keeps_the_moved_sum_on_the_stage(self):
        settled = self.reply("Al bakalım.", success=True, stage="On bakır uzatıyor.")
        self.assertEqual(settled["stage"], "On bakır uzatıyor.")

    def test_a_lost_roll_takes_the_handing_gesture_off_the_stage(self):
        settled = self.reply("Al bakalım.", stage="Kesesinden çıkarıp avucuna bırakıyor. Omuz silkiyor.")
        self.assertEqual((settled["moved"], settled["stage"]), (0, "Omuz silkiyor."))

    def test_no_stage_given_is_none(self):
        self.assertIsNone(self.reply("Al bakalım.", success=True)["stage"])


class HalfACopper(LostRoll):
    """D-268: 'yarım bakır' names less than a coin; the smallest coin moves, never the whole cap."""

    def test_half_a_copper_moves_one_copper(self):
        settled = self.reply("Al bakalım.", success=True, text="Bana yarım bakır ver")
        self.assertEqual(settled["moved"], 1)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (501, 99))
        [entry] = self.ops().values()
        self.assertEqual((entry["purpose"], entry["net_debit_cp"]), ("npc_gift", 1))

    def test_half_a_silver_is_five_copper(self):
        self.assertEqual(self.reply("Al bakalım.", success=True, text="Bana yarım gümüş ver")["moved"], 5)


class StageInATurn(unittest.IsolatedAsyncioTestCase):
    """D-264 through the whole turn: the stage direction the model wrote is cleaned like the spoken line."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def ask(self, d20, stage):
        with fixed_town(self, 166):
            _, self.session_id, session, turn_url, self.npc = await self.campaign_with_npc()
        world = session.world_state
        world.setdefault("currency", {})[self.npc["id"]] = 100
        world["currency"]["player"] = 500
        client = coin_ask.GiveClient("Hmm, bakalım.", stage_direction=stage)
        body = speech.ExperimentalNpcDialogueTests.request(self.npc, message="Marek, bana biraz para verir misin?")
        with patch("game.roll_d20", return_value=d20), \
                patch("dialogue_runtime.observe_turn", wraps=dialogue_runtime.observe_turn):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), session.world_state

    async def test_a_won_roll_shows_no_other_sum_in_the_stage(self):
        reply, world = await self.ask(20, "Beş bakır uzatıyor.")
        self.assertEqual(world["currency"]["player"], 510)
        self.assertIn("10 bakır", reply["narration"])
        self.assertNotIn("Beş bakır", reply["narration"])

    async def test_a_lost_roll_shows_no_handing_gesture(self):
        reply, world = await self.ask(1, "Kesesinden çıkarıp avucuna bırakıyor.")
        self.assertEqual(world["currency"]["player"], 500)
        self.assertNotIn("avucuna bırakıyor", reply["narration"])
        self.assertIn(world_threads.job_lines("text", "coin_ask_refused"), reply["narration"])


if __name__ == "__main__":
    unittest.main()
