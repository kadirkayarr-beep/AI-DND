"""W11: the opening keeps the player's choice; lore is the starting ground, not a rail; secrets are not opened early.

`campaign_opening.build_opening(preferences, authorized_lore, backstory)` builds the starting plan from lore the caller has
authorized (the module invents none). The player's own opening text is kept verbatim; an AI opening is built from a verified
location and may or may not link the player's public backstory; no tavern, lost relative or main quest is ever required;
campaign overrides win over the lore baseline (no forced reversion, the baseline object is not mutated); a backstory secret
whose reveal turn has not come is withheld from the opening and the preview; an unverified lore version blocks the opening.
"""
from __future__ import annotations

import copy
import json
import unittest

import campaign_opening

LORE = {
    "version": "fr-2e-test-fixture", "verified": True,
    "locations": {
        "fr:city:neverwinter": {"name": "Neverwinter", "kind": "city", "verified": True},
        "fr:wild:high_road": {"name": "Yüksek Yol", "kind": "road", "verified": True},
        "fr:city:unverified": {"name": "Doğrulanmamış Yer", "kind": "city", "verified": False},
    },
    "facts": {"fr:city:neverwinter.current_lord_id": "fr:person:dagult_neverember"},
}
BACKSTORY = {
    "public": [{"id": "bs:smith_family", "text": "Bir demirci ailesinden geliyorsun."}],
    "secrets": [{"id": "bs:secret_oath", "text": "Gizli bir yemin etmiştin: SIR-OATH-5521.", "reveal_after_turn": 10}],
}


class OpeningTests(unittest.TestCase):
    def test_opening_preserves_player_choice_and_canon_divergence(self):
        own = campaign_opening.build_opening(
            {"mode": "own", "own_text": "Kapı gıcırdayarak açılır ve ben içeri adım atarım.", "link_backstory": False,
             "start_location_id": "fr:wild:high_road"}, LORE, BACKSTORY)
        ai_linked = campaign_opening.build_opening(
            {"mode": "ai", "link_backstory": True, "start_location_id": "fr:city:neverwinter"}, LORE, BACKSTORY)
        ai_free = campaign_opening.build_opening({"mode": "ai", "link_backstory": False}, LORE, BACKSTORY)
        frozen = copy.deepcopy(LORE)
        diverged = campaign_opening.build_opening(
            {"mode": "ai", "start_location_id": "fr:city:neverwinter",
             "campaign_overrides": {"facts": {"fr:city:neverwinter.current_lord_id": "campaign:person:new_lord"}}}, LORE, BACKSTORY)
        plans = [own, ai_linked, ai_free, diverged]
        everything = json.dumps(plans, ensure_ascii=False).casefold()
        obs = {
            "player_opening_preserved": own["opening_text"] == "Kapı gıcırdayarak açılır ve ben içeri adım atarım.",
            "mandatory_tavern_or_main_quest": any(plan["required_elements"] for plan in plans)
                                              or "taverna" in ai_free["opening_text"].casefold()
                                              or any(plan["main_quest"] is not None for plan in plans),
            "canon_divergence_reverted": diverged["canon"]["facts"]["fr:city:neverwinter.current_lord_id"] != "campaign:person:new_lord",
            "backstory_secret_disclosed_early": "sir-oath-5521" in everything or "bs:secret_oath" in
                                                json.dumps([p["backstory_links"] for p in plans]),
        }
        assert obs["player_opening_preserved"] is True
        assert obs["mandatory_tavern_or_main_quest"] is False
        assert obs["canon_divergence_reverted"] is False
        assert obs["backstory_secret_disclosed_early"] is False
        self.assertEqual(LORE, frozen, "the lore baseline is never mutated")
        self.assertEqual(diverged["diverged_keys"], ["fr:city:neverwinter.current_lord_id"])
        self.assertEqual(own["location_id"], "fr:wild:high_road")
        self.assertEqual(ai_linked["backstory_links"], ["bs:smith_family"])
        self.assertEqual(ai_free["backstory_links"], [])
        self.assertEqual(ai_linked["withheld_secret_ids"], ["bs:secret_oath"])
        self.assertIn("Neverwinter", ai_linked["opening_text"])
        self.assertTrue(ai_linked["preview"]["accepted_entity_ids"], "the plan carries preview and accepted entity ids")

    def test_a_secret_is_opened_only_when_its_turn_has_come(self):
        late = campaign_opening.build_opening({"mode": "ai", "link_backstory": True, "current_turn": 12}, LORE, BACKSTORY)
        self.assertEqual(late["withheld_secret_ids"], [])
        self.assertIn("bs:secret_oath", late["revealed_secret_ids"])

    def test_unverified_lore_or_location_does_not_open(self):
        blocked = campaign_opening.build_opening({"mode": "ai"}, {**LORE, "verified": False}, BACKSTORY)
        self.assertEqual((blocked["status"], blocked["reason"]), ("BLOCKED", "lore_version_unverified"))
        unknown = campaign_opening.build_opening({"mode": "ai", "start_location_id": "fr:city:unverified"}, LORE, BACKSTORY)
        self.assertEqual((unknown["status"], unknown["reason"]), ("BLOCKED", "start_location_not_verified"))
        missing = campaign_opening.build_opening({"mode": "ai", "start_location_id": "nowhere"}, LORE, BACKSTORY)
        self.assertEqual(missing["status"], "BLOCKED")

    def test_an_empty_own_opening_is_not_silently_replaced(self):
        result = campaign_opening.build_opening({"mode": "own", "own_text": "  "}, LORE, BACKSTORY)
        self.assertEqual((result["status"], result["reason"]), ("BLOCKED", "own_opening_empty"))


if __name__ == "__main__":
    unittest.main()
