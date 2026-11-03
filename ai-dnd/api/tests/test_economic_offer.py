"""A1: an economic offer is prepared by the engine alone and preparing it changes nothing.

No model call, no database: the offer is a pure reading of a copy of the world. Only the engine decides
whether a counterparty will take part; the public card carries the label the player knows and never the
inner acceptance, the check difficulty or a refusal reason.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest

from pydantic import ValidationError

import bold_acts
import economic_actions as ea
import game
import shop_trade
import world_reactions
from api.schemas import EconomicProposalIn, PublicEconomicOffer, PublicOfferLine, TextSpan


def proposal(**fields) -> ea.EconomicProposal:
    base = {"purpose": "gift", "recipient_id": "barman", "source_id": None, "item_id": None, "count": 1,
            "amount_cp": None, "tip_cp": 0, "tender_cp": None, "dependency": "base_required",
            "source_action_id": "action-1", "text_span": None}
    base.update(fields)
    return ea.EconomicProposal(**base)


def room(**fields) -> ea.EconomicProposal:
    return proposal(**{"purpose": "room", **fields})


class OfferFixture(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "guard", "name": "Çavuş Hale", "role": "Muhafız", "location": self.here, "current_hp": 10},
            {"id": "farmer", "name": "Ilgın", "role": "Çiftçi", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 500}
        self.w.setdefault("flags", {})["turn_index"] = 3
        self.w["campaign_time"] = {"elapsed_seconds": 3 * 3600}

    def state(self) -> ea.EconomicState:
        return ea.EconomicState(world=self.w, character=self.s.character)

    def prepare(self, value: ea.EconomicProposal, *, offer_id: str = "offer-1") -> ea.PrepareResult:
        return ea.prepare_offer(self.state(), value, offer_id=offer_id, campaign_id="campaign-1",
                                actor_id="player", turn_index=self.w["flags"]["turn_index"])

    def assert_no_trade(self, result: ea.PrepareResult, status: str, reason: str) -> None:
        self.assertEqual((result.status, result.reason_code), (status, reason), result.public_message)
        self.assertIsNone(result.offer)
        self.assertTrue(result.public_message)

    def assert_unchanged(self, before: dict) -> None:
        after = self.w
        self.assertEqual(after["currency"], before["currency"])
        self.assertEqual(after["inventory"], before["inventory"])
        self.assertEqual(after["campaign_time"], before["campaign_time"])
        self.assertEqual(after, before)
        self.assertNotIn("economic_offers", after.get("flags", {}))

    def theft_held_by_guard(self, *, arrest: bool = True) -> dict:
        deed = {"kind": "theft", "at": 120, "location": self.here, "text": "Tezgâhtan kese çalındı",
                "described": ["guard"], "witnesses": [], "told": [], "heard": [], "seen_near": [],
                "hold": {"guard": "guard", "place": self.here, "turn": 2, "arrest": arrest}}
        self.w["flags"].setdefault("deeds", []).append(deed)
        return deed


class PreparingChangesNothing(OfferFixture):
    def test_question_opens_no_trade(self):
        before = copy.deepcopy(self.w)
        counter = shop_trade.counter(self.w)
        self.assertEqual(counter["status"], "ready")
        self.assertIsNotNone(shop_trade.quote(self.w, "barman", "bira", 2))
        self.assertEqual(self.w, before)
        answered = bold_acts.resolve(self.s, "oda ne kadar?")["action_result"]
        self.assertEqual((answered["action"], answered["status"]), ("lodging", "quoted"), answered)
        self.assertEqual(self.w["currency"], before["currency"])
        self.assertEqual(self.w["inventory"], before["inventory"])
        self.assertEqual(self.w["campaign_time"], before["campaign_time"])
        self.assertNotIn("inn_room", self.w["flags"])
        self.assertNotIn("economic_offers", self.w["flags"])

    def test_offer_prepare_changes_no_assets_or_clock(self):
        before = copy.deepcopy(self.w)
        for value in (room(recipient_id="barman", tip_cp=5),
                      proposal(purpose="gift", recipient_id="farmer", amount_cp=20),
                      proposal(purpose="tip", recipient_id="barman", amount_cp=3),
                      proposal(purpose="purchase", recipient_id="barman", item_id="bira", count=2)):
            with self.subTest(purpose=value.purpose):
                result = self.prepare(value)
                self.assertEqual(result.status, "prepared", result.public_message)
                self.assertEqual(result.offer.status, "prepared")
                self.assertIsNone(result.offer.operation_id)
                self.assertIsNone(result.offer.consumed_action_id)
                self.assertEqual(result.offer.prepared_turn, 3)
                self.assert_unchanged(before)

    def test_prepare_does_not_persist_coin_labels(self):
        self.w["currency"] = {"player": 0}
        self.w["inventory"] = [*self.w.get("inventory", []), "8 Altın"]
        before_inventory = json.dumps(self.w["inventory"], ensure_ascii=False, sort_keys=True)
        before_currency = json.dumps(self.w["currency"], sort_keys=True)
        result = self.prepare(room(recipient_id="barman"))
        self.assertEqual(result.status, "prepared", result.public_message)
        self.assertEqual(json.dumps(self.w["inventory"], ensure_ascii=False, sort_keys=True), before_inventory)
        self.assertEqual(json.dumps(self.w["currency"], sort_keys=True), before_currency)


class WhoIsOnTheCard(OfferFixture):
    def test_offer_uses_public_npc_label(self):
        barman = self.w["npcs"][0]
        barman.update(name="Gizli Marek", name_known_to_player=False)
        result = self.prepare(room(recipient_id="barman", tip_cp=5))
        self.assertEqual(result.status, "prepared", result.public_message)
        public = ea.public_offer(self.state(), result.offer)
        self.assertIsInstance(public, ea.PublicEconomicOffer)
        text = json.dumps(dataclasses.asdict(public), ensure_ascii=False)
        self.assertNotIn("Gizli", text)
        self.assertNotIn("Gizli", result.public_message)
        self.assertEqual(public.counterparty_label, "Bir barmen")
        for hidden in ("acceptance", "line_decisions", "reason_code", "check", "difficulty", "context_digest"):
            self.assertNotIn(hidden, text)
        self.assertEqual(public.max_total_cp, 55)
        self.assertEqual(public.offer_id, result.offer.offer_id)
        self.assertEqual(public.confirmation_digest, result.offer.confirmation_digest)
        self.assertEqual([(line.count, line.unit_cp, line.total_cp, line.optional) for line in public.lines],
                         [(1, 50, 50, False), (1, 5, 5, True)])
        # A refused NPC's reason is never put on a card: there is no card.
        self.theft_held_by_guard(arrest=False)
        self.w["flags"]["deeds"][-1].pop("hold")
        self.w["flags"]["deeds"][-1]["described"] = ["barman"]
        refused = self.prepare(room(recipient_id="barman"))
        self.assertEqual(refused.status, "refused")
        self.assertNotIn("Gizli", refused.public_message)
        self.assertNotIn("theft", refused.public_message)

    def test_ambiguous_recipient_requires_clarification(self):
        self.assert_no_trade(self.prepare(proposal(recipient_id="nobody", amount_cp=5)), "clarification", "npc_unknown")
        self.w["npcs"].append({"id": "farmer", "name": "Başka Ilgın", "role": "Çiftçi", "location": self.here,
                               "current_hp": 10})
        self.assert_no_trade(self.prepare(proposal(recipient_id="farmer", amount_cp=5)), "clarification", "npc_unknown")

    def test_absent_npc_offer_is_clarification(self):
        self.w["npcs"][2]["location"] = "somewhere_else"
        self.assert_no_trade(self.prepare(proposal(recipient_id="farmer", amount_cp=5)), "clarification", "npc_not_here")

    def test_refused_npc_gift_has_zero_delta(self):
        self.w["flags"]["deeds"] = [{"kind": "killing", "at": 50, "victim_id": "someone", "location": self.here,
                                     "witnesses": ["farmer"], "told": [], "heard": [], "seen_near": [],
                                     "described": []}]
        self.assertTrue(world_reactions.refuses(self.w, self.w["npcs"][2]))
        before = copy.deepcopy(self.w)
        result = self.prepare(proposal(recipient_id="farmer", amount_cp=20))
        self.assertEqual((result.status, result.reason_code), ("refused", "npc_refuses"))
        self.assertIsNone(result.offer)
        self.assertEqual(result.public_message, world_reactions.refusal_line(self.w["npcs"][2]))
        self.assert_unchanged(before)


class ThePriceIsTheServers(OfferFixture):
    def test_client_price_is_ignored_for_goods_and_room(self):
        for amount in (None, 50):
            result = self.prepare(room(recipient_id="barman", amount_cp=amount))
            self.assertEqual(result.status, "prepared", result.public_message)
            self.assertEqual([(line.kind, line.unit_cp, line.total_cp, line.recipient_id) for line in result.offer.lines],
                             [("room", 50, 50, f"sink:lodging:{self.here}")])
        for amount in (None, 8):
            result = self.prepare(proposal(purpose="purchase", recipient_id="barman", item_id="bira", count=2,
                                           amount_cp=amount))
            self.assertEqual(result.status, "prepared", result.public_message)
            self.assertEqual([(line.kind, line.item_id, line.count, line.unit_cp, line.total_cp, line.recipient_id)
                              for line in result.offer.lines], [("goods", "bira", 2, 4, 8, "barman")])

    def test_client_price_mismatch_is_clarification(self):
        before = copy.deepcopy(self.w)
        self.assert_no_trade(self.prepare(room(recipient_id="barman", amount_cp=1)), "clarification",
                             "client_price_mismatch")
        self.assert_no_trade(self.prepare(proposal(purpose="purchase", recipient_id="barman", item_id="bira",
                                                   amount_cp=1)), "clarification", "client_price_mismatch")
        self.assert_unchanged(before)

    def test_gift_and_tip_require_positive_amount(self):
        for purpose in ("gift", "tip"):
            for amount in (None, 0):
                with self.subTest(purpose=purpose, amount=amount):
                    self.assert_no_trade(self.prepare(proposal(purpose=purpose, recipient_id="farmer", amount_cp=amount)),
                                         "clarification", "amount_required")

    def test_prepare_purse_below_base_is_clarification(self):
        self.w["currency"] = {"player": 49}
        self.assert_no_trade(self.prepare(room(recipient_id="barman")), "clarification", "purse_below_base")
        self.w["currency"] = {"player": 50}
        self.assertEqual(self.prepare(room(recipient_id="barman", tip_cp=5)).status, "prepared")

    def test_combat_or_shop_not_now_is_clarification(self):
        self.w["combat"] = {"active": True}
        self.assert_no_trade(self.prepare(room(recipient_id="barman")), "clarification", "combat_active")
        self.assert_no_trade(self.prepare(proposal(recipient_id="farmer", amount_cp=5)), "clarification", "combat_active")
        self.w["combat"] = {"active": False}
        self.w["death_state"] = {"terminal": True}
        self.assert_no_trade(self.prepare(room(recipient_id="barman")), "clarification", "shop_not_now")
        self.w.pop("death_state")
        self.assert_no_trade(self.prepare(room(recipient_id="farmer")), "clarification", "shop_unavailable")
        self.w["npcs"][0]["current_hp"] = 0
        self.assert_no_trade(self.prepare(room(recipient_id="barman")), "clarification", "shop_unavailable")
        self.w["npcs"][0]["current_hp"] = 10
        self.assert_no_trade(self.prepare(proposal(purpose="purchase", recipient_id="barman", item_id="bira",
                                                   count=shop_trade.DEFAULT_STOCK + 1)),
                             "clarification", "no_stock_or_service")
        self.assert_no_trade(self.prepare(proposal(purpose="purchase", recipient_id="barman", item_id="kılıç")),
                             "clarification", "no_stock_or_service")


class TheBribe(OfferFixture):
    def bribe(self, amount: int = 100) -> ea.PrepareResult:
        return self.prepare(proposal(purpose="gift", recipient_id="guard", amount_cp=amount))

    def test_bribe_offer_carries_persuasion_check_and_effect(self):
        self.theft_held_by_guard()
        result = self.bribe(100)
        self.assertEqual(result.status, "prepared", result.public_message)
        offer = result.offer
        self.assertEqual(offer.acceptance.check, ea.CheckSpec(skill="Persuasion", difficulty="medium"))
        self.assertEqual(offer.acceptance.producer, "engine")
        self.assertEqual(offer.on_accept, [ea.WorldEffect(kind="bribe_accepted", npc_id="guard")])
        self.w["currency"]["player"] = 1000
        self.assertEqual(self.bribe(1000).offer.acceptance.check.difficulty, "easy")
        self.assertEqual(self.bribe(99).offer.acceptance.check.difficulty, "hard")
        public = ea.public_offer(self.state(), offer)
        self.assertTrue(public.may_refuse)
        text = json.dumps(dataclasses.asdict(public), ensure_ascii=False)
        for hidden in ("medium", "Persuasion", "difficulty", "bribe_accepted"):
            self.assertNotIn(hidden, text)

    def test_bribe_to_identifying_guard_opens_card(self):
        deed = self.theft_held_by_guard()
        guard = self.w["npcs"][1]
        self.assertTrue(world_reactions.refuses(self.w, guard))
        self.assertIs(world_reactions.arrester(self.w), guard)
        self.assertEqual(self.bribe(100).status, "prepared")
        deed.pop("hold")
        result = self.bribe(100)
        self.assertEqual((result.status, result.reason_code), ("refused", "npc_refuses"))
        self.assertIsNone(result.offer)

    def test_bribe_context_digest_covers_hold(self):
        deed = self.theft_held_by_guard()
        offer = self.bribe(100).offer
        held = ea.context_digest(self.state(), offer.proposal, offer.lines)
        self.assertEqual(held, offer.context_digest)
        deed["described"] = []  # the guard no longer refuses; the bribe digest does not read it
        self.assertFalse(world_reactions.refuses(self.w, self.w["npcs"][1]))
        self.assertEqual(ea.context_digest(self.state(), offer.proposal, offer.lines), held)
        deed.pop("hold")
        self.assertNotEqual(ea.context_digest(self.state(), offer.proposal, offer.lines), held)


class Digests(OfferFixture):
    def test_confirmation_digest_covers_fields(self):
        offer = self.prepare(room(recipient_id="barman", tip_cp=5, tender_cp=100)).offer
        digest = ea.confirmation_digest(offer)
        self.assertEqual(digest, offer.confirmation_digest)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        changed_line = dataclasses.replace(offer.lines[0], total_cp=49)
        variants = {
            "offer_id": dataclasses.replace(offer, offer_id="offer-2"),
            "actor_id": dataclasses.replace(offer, actor_id="someone"),
            "campaign_id": dataclasses.replace(offer, campaign_id="campaign-2"),
            "place_id": dataclasses.replace(offer, place_id="elsewhere"),
            "proposal": dataclasses.replace(offer, proposal=dataclasses.replace(offer.proposal, tip_cp=6)),
            "recipient": dataclasses.replace(offer, proposal=dataclasses.replace(offer.proposal, recipient_id="farmer")),
            "lines": dataclasses.replace(offer, lines=[changed_line, *offer.lines[1:]]),
            "dependency": dataclasses.replace(offer, proposal=dataclasses.replace(offer.proposal,
                                                                                  dependency="all_or_none")),
            "tender_cp": dataclasses.replace(offer, proposal=dataclasses.replace(offer.proposal, tender_cp=60)),
            "context_digest": dataclasses.replace(offer, context_digest="0" * 64),
        }
        for name, variant in variants.items():
            with self.subTest(field=name):
                self.assertNotEqual(ea.confirmation_digest(variant), digest)
        spanned = dataclasses.replace(offer, proposal=dataclasses.replace(offer.proposal,
                                                                          text_span=ea.TextSpan(start=0, end=4)))
        self.assertEqual(ea.confirmation_digest(spanned), digest)

    def test_unrelated_npc_change_keeps_context_digest(self):
        offer = self.prepare(room(recipient_id="barman")).offer
        digest = offer.context_digest
        farmer = self.w["npcs"][2]
        farmer.update(location="somewhere_else", current_hp=1, hostile=True)
        self.w["npcs"].append({"id": "stranger", "name": "Yolcu", "role": "Yolcu", "location": self.here})
        self.assertEqual(ea.context_digest(self.state(), offer.proposal, offer.lines), digest)
        self.w["npcs"][0]["location"] = "somewhere_else"
        self.assertNotEqual(ea.context_digest(self.state(), offer.proposal, offer.lines), digest)

    def test_new_offer_id_is_server_random(self):
        first, second = ea.new_offer_id(), ea.new_offer_id()
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertNotEqual(first, second)


class ApiShapes(unittest.TestCase):
    def test_proposal_in_has_no_source_action_id(self):
        parsed = EconomicProposalIn(purpose="room", recipient_id="barman")
        self.assertIsNone(parsed.amount_cp)
        self.assertEqual((parsed.count, parsed.tip_cp, parsed.dependency), (1, 0, "base_required"))
        with self.assertRaises(ValidationError):
            EconomicProposalIn(purpose="room", recipient_id="barman", source_action_id="forged")
        for bad in ({"amount_cp": True}, {"amount_cp": 1.5}, {"amount_cp": -1}, {"amount_cp": 1_000_000_000},
                    {"count": 0}, {"tender_cp": -1}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                EconomicProposalIn(purpose="gift", recipient_id="barman", **bad)
        self.assertEqual(EconomicProposalIn(purpose="gift", recipient_id="b", amount_cp=0).amount_cp, 0)
        TextSpan(start=0, end=3)
        line = PublicOfferLine(line_id="room:0", label="Oda", count=1, unit_cp=50, total_cp=50, optional=False)
        PublicEconomicOffer(offer_id="x", confirmation_digest="d", counterparty_label="Bir barmen", lines=[line],
                            dependency="base_required", max_total_cp=50, tender_cp=None, may_refuse=False)


if __name__ == "__main__":
    unittest.main()
