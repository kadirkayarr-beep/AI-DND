"""D-166 (Kadir kararı 2026-11-15): C5 stays, but limited.

A person may still hand the player coin from their own purse when the player asks (C5), but:
- the engine sets the sum, from the person's purse and their attitude to the player; the figure the model said moves
  nothing ("the model only says it");
- asking for coin takes a Persuasion roll, through the smallest willingness model of guide 4.5 (D-169, kept to this one
  ask): unwilling refuses without a roll, hesitant rolls against max(15, the person's Intelligence score), friendly
  rolls with advantage; a try by the same means waits 24 hours;
- coin never comes from nowhere: the purse pays it, through `economic_actions.npc_gift`, or nothing moves.

No real model is called; rolls are injected.
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import dialogue_runtime
import economic_actions as ea
import game
import influence
import relationships
import town_knowledge
import world_reactions
import world_threads
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town

DAY = 86400


class Ask(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        here = self.w["location"]
        self.w["npcs"] = [
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": here, "current_hp": 10},
            {"id": "sage", "name": "Ilgın", "role": "Bilge", "location": here, "current_hp": 10, "intelligence": 18},
        ]
        self.w["currency"] = {"player": 500, "guest": 100, "sage": 1000}
        self.rolls = []
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def ops(self):
        return self.w.get("flags", {}).get("economic_ledger", {}).get("operations", {})

    def roll(self, success):
        def persuade(dc, advantage):
            self.rolls.append((dc, advantage))
            return {"success": success, "card": {"action": "skill_check", "skill": "Persuasion", "dc": dc}}
        return persuade

    def ask(self, npc_id, amount=5, *, success=True, text="bana biraz para ver hadi"):
        return town_knowledge.settle_reply(self.w, self.npc(npc_id), text, {"kind": "give", "amount_cp": amount},
                                           "Al bakalım.", accept_job=lambda thread: None, persuade=self.roll(success))

    def later(self, seconds):
        clock = self.w.setdefault("campaign_time", {"elapsed_seconds": 0})
        clock["elapsed_seconds"] = clock.get("elapsed_seconds", 0) + seconds


class TheGuideNumbers(Ask):
    def test_dc_is_fifteen_or_the_intelligence_score(self):
        self.assertEqual(influence.dc(self.npc("guest")), 15)
        self.assertEqual(influence.dc(self.npc("sage")), 18)
        self.assertEqual(influence.dc({"id": "x", "intelligence": 12}), 15)

    def test_attitude_follows_the_relationship(self):
        self.assertEqual(influence.attitude(self.w, "guest"), "indifferent")
        relationships.note(self.w, "guest", 1, "yardım")
        self.assertEqual(influence.attitude(self.w, "guest"), "friendly")
        relationships.note(self.w, "guest", -3, "hakaret")
        self.assertEqual(influence.attitude(self.w, "guest"), "hostile")

    def test_the_cap_is_a_share_of_the_purse_with_a_ceiling(self):
        self.assertEqual(influence.gift_cap_cp(100, "indifferent"), 10)
        self.assertEqual(influence.gift_cap_cp(1000, "indifferent"), 10)
        self.assertEqual(influence.gift_cap_cp(100, "friendly"), 20)
        self.assertEqual(influence.gift_cap_cp(1000, "friendly"), 50)
        self.assertEqual(influence.gift_cap_cp(1000, "hostile"), 0)
        self.assertEqual(influence.gift_cap_cp(9, "indifferent"), 0)
        self.assertEqual(influence.gift_cap_cp(0, "friendly"), 0)


class TheEngineSetsTheSum(Ask):
    def test_a_won_roll_moves_the_engines_sum_not_the_models(self):
        for said in (5, 500):
            self.setUp()
            settled = self.ask("guest", said)
            self.assertEqual(self.rolls, [(15, False)])
            self.assertEqual(settled["moved"], 10)
            self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (510, 90))
            [(operation_id, entry)] = self.ops().items()
            self.assertEqual((entry["purpose"], entry["net_debit_cp"]), ("npc_gift", 10))
            self.assertIn("10", settled["note"])
            self.assertEqual(settled["check"], {"action": "skill_check", "skill": "Persuasion", "dc": 15})

    def test_a_lost_roll_moves_nothing(self):
        before = copy.deepcopy(self.w["currency"])
        settled = self.ask("guest", success=False)
        self.assertEqual(self.rolls, [(15, False)])
        self.assertEqual((settled["moved"], settled["note"]), (0, world_threads.job_lines("text", "coin_ask_refused")))
        self.assertTrue(settled["note"])
        self.assertEqual(self.w["currency"], before)
        self.assertEqual(self.ops(), {})
        self.assertEqual(settled["check"]["skill"], "Persuasion")

    def test_no_roll_means_no_coin(self):
        before = copy.deepcopy(self.w["currency"])
        settled = town_knowledge.settle_reply(self.w, self.npc("guest"), "bana biraz para ver hadi",
                                              {"kind": "give", "amount_cp": 5}, "Al.", accept_job=lambda thread: None)
        self.assertEqual(settled["moved"], 0)
        self.assertEqual(self.w["currency"], before)
        self.assertEqual(self.ops(), {})

    def test_the_sages_dc_is_their_intelligence_and_a_friend_rolls_with_advantage(self):
        relationships.note(self.w, "sage", 2, "yardım")
        settled = self.ask("sage")
        self.assertEqual(self.rolls, [(18, True)])
        self.assertEqual(settled["moved"], 50)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["sage"]), (550, 950))


class OnlyAnAskRolls(Ask):
    """Review: the roll is made for a line that asks for coin (`world_threads.asks_for_pay`), never for one that only
    speaks of money: no roll the player did not try, and no day's wait for it."""

    def test_a_line_that_only_speaks_of_money_rolls_nothing_and_moves_nothing(self):
        for line in ("Param kalmadı", "Biraz para lazım"):
            self.setUp()
            before = copy.deepcopy(self.w["currency"])
            settled = self.ask("guest", text=line)
            self.assertEqual((self.rolls, settled["moved"], settled["check"]), ([], 0, None), line)
            self.assertEqual(self.w["currency"], before)
            self.assertEqual(self.ops(), {})
            self.assertNotIn("guest", self.w.get("flags", {}).get(influence.COIN_ASKS) or {})

    def test_a_polite_ask_rolls(self):
        for line in ("Bana biraz para verebilir misin?", "Param kalmadı, bana biraz para verir misin?"):
            self.setUp()
            self.assertEqual(self.ask("guest", text=line)["moved"], 10, line)
            self.assertEqual(self.rolls, [(15, False)])

    def test_an_offer_to_give_coin_is_not_an_ask(self):
        # Re-review: "verebilir" joined the ask verbs; the player offering coin must not roll or be paid by the NPC.
        for line in ("Sana beş bakır verebilir miyim?", "Bu bilgiye karşılık sana 5 bakır verebilir miyim?",
                     "Size biraz para verebilir miyiz?"):
            self.assertFalse(world_threads.asks_for_pay(line), line)
            self.setUp()
            before = copy.deepcopy(self.w["currency"])
            settled = self.ask("guest", text=line)
            self.assertEqual((self.rolls, settled["moved"], settled["check"]), ([], 0, None), line)
            self.assertEqual(self.w["currency"], before)
            self.assertEqual(self.ops(), {})


class TheAskedSumBounds(Ask):
    """Review: the cap is a ceiling, not the sum: a smaller sum the player names is what moves."""

    def test_a_smaller_sum_asked_is_what_moves(self):
        settled = self.ask("guest", text="Bana 2 bakır ver")
        self.assertEqual(settled["moved"], 2)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (502, 98))
        [entry] = self.ops().values()
        self.assertEqual((entry["purpose"], entry["net_debit_cp"]), ("npc_gift", 2))

    def test_a_larger_sum_asked_moves_only_the_cap(self):
        self.assertEqual(self.ask("guest", text="Bana üç gümüş ver")["moved"], 10)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (510, 90))


class NothingHandedOnARefusal(Ask):
    """Review: the model spoke before the roll; when no coin moves, its handing words leave and the engine says so."""

    def reply(self, spoken, *, success=False):
        return town_knowledge.settle_reply(self.w, self.npc("guest"), "bana biraz para ver hadi",
                                           {"kind": "give", "amount_cp": 5}, spoken,
                                           accept_job=lambda thread: None, persuade=self.roll(success))

    def test_a_lost_roll_takes_the_handing_off_the_reply_and_says_no_coin_came(self):
        settled = self.reply("Hmm. Al bakalım. Yolun açık olsun.")
        self.assertEqual(settled["spoken"], "Hmm. Yolun açık olsun.")
        self.assertEqual(settled["note"], world_threads.job_lines("text", "coin_ask_refused"))

    def test_an_unwilling_person_hands_nothing_either(self):
        relationships.note(self.w, "guest", -1, "hakaret")
        settled = self.reply("Al bakalım. Kesemi uzatıyorum.")
        self.assertEqual((self.rolls, settled["spoken"]), ([], ""))
        self.assertEqual(settled["note"], world_threads.job_lines("text", "coin_ask_refused"))

    def test_a_won_roll_keeps_the_handing(self):
        settled = self.reply("Al bakalım. Yolun açık olsun.", success=True)
        self.assertEqual(settled["spoken"], "Al bakalım. Yolun açık olsun.")
        self.assertIn("10", settled["note"])


class Unwilling(Ask):
    def test_a_hostile_person_gives_nothing_and_no_roll_is_made(self):
        relationships.note(self.w, "guest", -1, "hakaret")
        before = copy.deepcopy(self.w["currency"])
        settled = self.ask("guest")
        self.assertEqual(self.rolls, [])
        self.assertEqual(settled["moved"], 0)
        self.assertNotIn("check", {key for key, value in settled.items() if value})
        self.assertEqual(self.w["currency"], before)

    def test_a_purse_too_thin_to_spare_gives_nothing_and_no_roll_is_made(self):
        self.w["currency"]["guest"] = 9
        settled = self.ask("guest")
        self.assertEqual((self.rolls, settled["moved"], self.w["currency"]["guest"]), ([], 0, 9))

    def test_a_try_waits_a_day_whatever_it_rolled(self):
        self.ask("guest", success=False)
        self.later(DAY - 1)
        self.assertEqual(self.ask("guest")["moved"], 0)
        self.assertEqual(len(self.rolls), 1)
        self.later(1)
        self.assertEqual(self.ask("guest")["moved"], 10)
        self.assertEqual(len(self.rolls), 2)
        # A won ask waits a day too: the purse is not drained by asking again.
        self.assertEqual(self.ask("guest")["moved"], 0)
        self.assertEqual(len(self.rolls), 2)
        self.assertEqual(self.w["currency"]["guest"], 90)

    def test_a_wait_on_one_person_does_not_hold_another(self):
        self.ask("guest", success=False)
        self.assertEqual(self.ask("sage")["moved"], 10)


class TheOwnerHoldsTheCap(Ask):
    def test_npc_gift_above_the_cap_is_refused_with_no_delta(self):
        before = copy.deepcopy(self.w)
        resolution = ea.npc_gift(ea.EconomicState(world=self.w, character=None), npc_id="guest", amount_cp=11)
        self.assertEqual((resolution.status, resolution.reason_code, resolution.asset_deltas),
                         ("refused", "over_gift_cap", []))
        self.assertEqual(self.w, before)

    def test_npc_gift_cap_reads_the_live_purse_and_attitude(self):
        self.assertEqual(ea.npc_gift_cap(self.w, "guest"), 10)
        relationships.note(self.w, "guest", 1, "yardım")
        self.assertEqual(ea.npc_gift_cap(self.w, "guest"), 20)
        self.assertEqual(ea.npc_gift_cap(self.w, "nobody"), 0)


class TheTurnsRoll(Ask):
    """`game._coin_persuasion`: this turn's own Persuasion roll is reused, never rerolled; otherwise one fresh roll."""

    def test_a_persuasion_already_rolled_this_turn_is_reused_against_the_persons_dc(self):
        earlier = {"action": "skill_check", "skill": "Persuasion", "total": 16, "status": "resolved"}
        with patch("game.perform_skill_check", side_effect=AssertionError("rerolled")):
            persuade = game._coin_persuasion(earlier)
            self.assertEqual(persuade(15, False), {"success": True})
            self.assertEqual(persuade(18, True), {"success": False})

    def test_another_roll_this_turn_asks_for_no_coin(self):
        earlier = {"action": "skill_check", "skill": "Intimidation", "total": 25, "status": "resolved"}
        with patch("game.perform_skill_check", side_effect=AssertionError("rerolled")):
            self.assertIsNone(game._coin_persuasion(earlier)(15, False))

    def test_the_roll_shows_on_a_talk_that_stays_a_talk(self):
        card = {"action": "skill_check", "skill": "Persuasion", "dice": 4, "total": 6, "dc": 15, "outcome": "failure",
                "success": False, "status": "resolved"}
        turn = {"action": "dialogue", "npc_id": "guest", "success": True, "status": "unverified"}
        game._show_coin_roll(turn, card)
        self.assertEqual((turn["action"], turn["npc_id"], turn["success"], turn["status"]),
                         ("dialogue", "guest", True, "unverified"))
        self.assertEqual((turn["skill"], turn["dice"], turn["total"], turn["dc"], turn["outcome"], turn["coin_ask_roll"]),
                         ("Persuasion", 4, 6, 15, "failure", True))
        rolled = {"action": "skill_check", "skill": "Persuasion", "total": 16}
        game._show_coin_roll(rolled, card)
        self.assertEqual(rolled, {"action": "skill_check", "skill": "Persuasion", "total": 16})

    def test_a_fresh_roll_is_one_persuasion_at_the_persons_dc(self):
        calls = []

        def check(skill, dc, *args, advantage=False, **kwargs):
            calls.append((skill, dc, advantage))
            return {"skill": skill, "ability": "charisma", "dice": 14, "dice_rolls": [9, 14], "modifier": 2,
                    "proficiency_bonus": 0, "expertise": False, "advantage": advantage, "disadvantage": False,
                    "resolution": {"action_id": "a", "resolution_id": "r"}, "total": 16, "dc": dc,
                    "result": "BAŞARILI"}

        with patch("game.perform_skill_check", side_effect=check):
            result = game._coin_persuasion({"action": "dialogue"})(15, True)
        self.assertEqual(calls, [("Persuasion", 15, True)])
        self.assertTrue(result["success"])
        card = result["card"]
        self.assertEqual((card["action"], card["skill"], card["dc"], card["total"], card["outcome"], card["success"],
                          card["dice_rolls"], card["status"]),
                         ("skill_check", "Persuasion", 15, 16, "success", True, [9, 14], "resolved"))


class AskingInATurn(unittest.IsolatedAsyncioTestCase):
    """The whole turn: a person asked for coin, the model proposing a figure; the roll shows and decides."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def ask(self, d20):
        with fixed_town(self, 166):
            _, self.session_id, session, turn_url, self.npc = await self.campaign_with_npc()
        world = session.world_state
        world.setdefault("currency", {})[self.npc["id"]] = 100
        world["currency"]["player"] = 500
        client = GiveClient("Al bakalım, şu beş bakırı al.")
        self.body = speech.ExperimentalNpcDialogueTests.request(self.npc, message="Marek, bana biraz para verir misin?")
        with patch("game.roll_d20", return_value=d20), \
                patch("dialogue_runtime.observe_turn", wraps=dialogue_runtime.observe_turn) as observed:
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.turns = [call.args[3]["action_result"] for call in observed.call_args_list]
        return response.json(), session.world_state

    def assert_still_a_talk(self, reply):
        """Review: the roll's card does not turn the talk into a check: 'talk to X' objectives and a guard's question
        read action 'dialogue' with the person's id and success True."""
        self.assertEqual(reply["turn_outcome"]["action"], "dialogue")
        [turn] = self.turns
        self.assertEqual((turn["action"], turn["npc_id"], turn["success"]), ("dialogue", self.npc["id"], True))
        self.assertTrue(world_reactions._answered(None, {"id": self.npc["id"]}, {"action_result": turn}))

    async def test_undo_gives_the_coin_back_and_lifts_the_wait(self):
        _, world = await self.ask(20)
        self.assertEqual(world["currency"]["player"], 510)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": self.body["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        world = self.manager.get(self.session_id).game_session.world_state
        self.assertEqual((world["currency"]["player"], world["currency"][self.npc["id"]]), (500, 100))
        self.assertEqual((world.get("flags", {}).get("economic_ledger") or {}).get("operations", {}), {})
        self.assertNotIn(self.npc["id"], world.get("flags", {}).get(influence.COIN_ASKS) or {})

    async def test_a_won_roll_pays_the_engines_sum_and_shows_the_roll(self):
        reply, world = await self.ask(20)
        self.assertEqual((world["currency"]["player"], world["currency"][self.npc["id"]]), (510, 90))
        self.assertEqual((reply["skill_check_result"]["skill"], reply["skill_check_result"]["dc"],
                          reply["skill_check_result"]["outcome"]), ("Persuasion", 15, "success"))
        self.assert_still_a_talk(reply)
        self.assertIn("10 bakır", reply["narration"])
        self.assertNotIn("beş bakır", reply["narration"])  # the model's own figure does not stand beside the real one
        [entry] = world["flags"]["economic_ledger"]["operations"].values()
        self.assertEqual((entry["purpose"], entry["net_debit_cp"]), ("npc_gift", 10))

    async def test_a_lost_roll_pays_nothing_and_shows_the_roll(self):
        reply, world = await self.ask(1)
        self.assertEqual((world["currency"]["player"], world["currency"][self.npc["id"]]), (500, 100))
        self.assertEqual((reply["skill_check_result"]["skill"], reply["skill_check_result"]["outcome"]),
                         ("Persuasion", "failure"))
        self.assertNotIn("beş bakır", reply["narration"])
        self.assertNotIn("Al bakalım", reply["narration"])
        self.assertIn(world_threads.job_lines("text", "coin_ask_refused"), reply["narration"])
        self.assertEqual((world.get("flags", {}).get("economic_ledger") or {}).get("operations", {}), {})
        self.assert_still_a_talk(reply)


class GiveClient(speech.ScriptedNpcSpeechClient):
    """The person's reply proposes handing coin over, with its own figure."""

    def chat(self, *args, **kwargs):
        reply = super().chat(*args, **kwargs)
        properties = (kwargs.get("format") or {}).get("properties") or {}
        if "commitment" in properties:
            import json
            packet = json.loads(reply["message"]["content"])
            packet["commitment"] = {"kind": "give", "amount_cp": 5}
            reply = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return reply


if __name__ == "__main__":
    unittest.main()
