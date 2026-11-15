"""D-096: a coin card the engine already knows will be refused never opens, and a refusal always says why.

Kadir's playtest (2026-11-14): the person answered a tip with "Parana ihtiyacım yok", yet "teklif hazır, onaylarsan"
came; confirming it said "İşlem gerçekleşmedi; hiçbir şey ödenmedi." with no reason. The reply was recorded as
unclear (`unknown`), which refuses the card's only line, so the card could never be paid.
"""
import copy
import dataclasses
import unittest

import economic_actions as ea
from api.tests.test_economic_offer import OfferFixture, proposal

GENERIC = "İşlem gerçekleşmedi; hiçbir şey ödenmedi."


class DeadCoinCard(OfferFixture):
    def reply(self, status, *, kind="offer", amount=10, npc="barman"):
        person = next(n for n in self.w["npcs"] if n["id"] == npc)
        person.setdefault("coin_responses", {})[f"{kind}:{amount}"] = {
            "status": status, "source_action_id": "action-0", "day": ea.game_day(self.w)}

    def test_unclear_reply_to_the_tip_opens_no_card_and_says_why(self):
        for purpose in ("tip", "gift"):
            with self.subTest(purpose=purpose):
                self.setUp()
                self.reply("unknown")
                before = copy.deepcopy(self.w)
                result = self.prepare(proposal(purpose=purpose, amount_cp=10))
                self.assert_no_trade(result, "refused", "npc_consent_required")
                self.assertNotIn("Onaylarsan", result.public_message)
                self.assertIn("Marek", result.public_message)
                self.assertIn("kesende", result.public_message)
                self.assert_unchanged(before)

    def test_another_amount_still_opens_a_card(self):
        self.reply("unknown")
        self.assertEqual(self.prepare(proposal(purpose="tip", amount_cp=11)).status, "prepared")

    def test_a_stored_dead_card_still_says_why_at_confirmation(self):
        # A card prepared before this fix (an older save): its only line already refused for want of consent.
        offer = self.prepare(proposal(purpose="tip", amount_cp=10)).offer
        refused = [dataclasses.replace(decision, status="refused", reason_code="npc_consent_required")
                   for decision in offer.acceptance.line_decisions]
        offer = dataclasses.replace(offer, acceptance=dataclasses.replace(offer.acceptance, line_decisions=refused))
        resolved = ea.resolve_offer(self.state(), offer, operation_id="op-1", check=lambda *a: None)
        self.assertEqual((resolved.status, resolved.reason_code, resolved.net_debit_cp),
                         ("refused", "npc_consent_required", 0))
        self.assertNotEqual(resolved.public_summary, GENERIC)
        self.assertIn("kesende", resolved.public_summary)

    def test_every_refusal_a_card_can_reach_says_why(self):
        for reason in ("npc_consent_required", "npc_refuses", "npc_declined", "item_not_owned",
                       "no_money", "tender_invalid", "check_failed", "check_required", "stale"):
            with self.subTest(reason=reason):
                text = ea._summary("refused", reason, 0, 0, [])
                self.assertTrue(text)
                self.assertNotEqual(text, GENERIC)


if __name__ == "__main__":
    unittest.main()
